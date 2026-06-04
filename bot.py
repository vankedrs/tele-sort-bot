import os
import random
import re
import json
import csv
import io
import uuid
import threading
import requests
from datetime import datetime
from collections import defaultdict

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ALLOWED_ID = int(os.getenv('ALLOWED_ID', 0))

bot = telebot.TeleBot(BOT_TOKEN)

# Flask Setup
app = Flask(__name__, static_folder='webapp')
CORS(app)

DB_FILE = 'database.json'
BIN_CSV = 'bin-list-data.csv'
BIN_URL = 'https://raw.githubusercontent.com/venelinkochev/bin-list-data/master/bin-list-data.csv'

clean_jobs = defaultdict(dict)
filter_sessions = {}
bin_jobs = defaultdict(dict)
bin_db = {}
TUNNEL_URL = os.getenv('TUNNEL_URL')

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {"users": {}, "banned": {}}

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=4)

db = load_db()

def download_and_load_bins():
    if not os.path.exists(BIN_CSV):
        print("Downloading BIN database (27MB)... This will take a moment.")
        response = requests.get(BIN_URL, stream=True)
        with open(BIN_CSV, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("BIN database downloaded successfully!")
    
    print("Loading BIN database into memory...")
    with open(BIN_CSV, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader) # Skip header
        for row in reader:
            if len(row) >= 10:
                # BIN, Brand, Type, Category, Issuer, IssuerPhone, IssuerUrl, isoCode2, isoCode3, CountryName
                bin_prefix = row[0].strip()
                bin_db[bin_prefix] = {
                    'brand': row[1].strip() or 'Unknown',
                    'type': row[2].strip() or 'Unknown',
                    'level': row[3].strip() or 'Unknown',
                    'bank': row[4].strip() or 'Unknown',
                    'country': row[9].strip() or 'Unknown',
                    'iso2': row[7].strip().upper() or ''
                }
    print(f"Loaded {len(bin_db)} BINs.")

def check_user(message, is_start=False):
    user_id = str(message.from_user.id)
    username = message.from_user.username
    
    if "registered" not in db:
        db["registered"] = []
        
    if username:
        db["users"][username.lower()] = user_id
        save_db(db)
        
    if user_id in db.get("banned", {}):
        try:
            bot.reply_to(message, f"⛔️ You cannot use this bot.\nReason: {db['banned'][user_id]}")
        except:
            pass
        return False
        
    if user_id not in db["registered"]:
        if is_start:
            db["registered"].append(user_id)
            save_db(db)
            return True
        else:
            bot.reply_to(message, "⚠️ System has been updated!\nPlease type /start to refresh your session and menus.")
            return False
            
    return True

def log_activity(message):
    if message.from_user.id == ALLOWED_ID:
        return
    try:
        bot.forward_message(ALLOWED_ID, message.chat.id, message.message_id)
        user_info = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
        bot.send_message(ALLOWED_ID, f"👆 Action dari {user_info}")
    except Exception as e:
        print(f"Log error: {e}")

# --- UTILITIES ---

def is_valid_text_file(document):
    if not document: return False
    if document.mime_type == 'text/plain': return True
    if document.file_name and document.file_name.lower().endswith('.txt'): return True
    return False

def luhn_check(card_number):
    try:
        digits = [int(x) for x in str(card_number) if x.isdigit()]
        if not digits:
            return False
        odd_digits = digits[-1::-2]
        even_digits = [sum(divmod(2 * d, 10)) for d in digits[-2::-2]]
        return (sum(odd_digits) + sum(even_digits)) % 10 == 0
    except ValueError:
        return False

def is_expired(mm, yy):
    try:
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        yy = int(yy)
        if yy < 100: yy += 2000
        mm = int(mm)
        
        if yy < current_year: return True
        if yy == current_year and mm < current_month: return True
        return False
    except ValueError:
        return True

def extract_cc_data(line):
    pattern = r'(?P<cc>\d{13,19})[^\w\n]+(?P<mm>\d{1,2})[^\w\n]+(?P<yy>\d{2,4})[^\w\n]+(?P<cvv>\d{3,4})'
    match = re.search(pattern, line)
    if match:
        cc = match.group('cc')
        mm = match.group('mm').zfill(2)
        yy = match.group('yy')
        if len(yy) == 2: yy = "20" + yy
        cvv = match.group('cvv')
        return f"{cc}|{mm}|{yy}|{cvv}", cc
    return None, None

def lookup_bin(cc_number):
    cc_str = str(cc_number)
    # Reverse lookup: Check 8 digits first, then 7, then 6
    for i in [8, 7, 6]:
        if len(cc_str) >= i:
            prefix = cc_str[:i]
            if prefix in bin_db:
                return bin_db[prefix]
    return {
        'brand': 'Unknown', 'type': 'Unknown', 'level': 'Unknown', 'bank': 'Unknown', 'country': 'Unknown', 'iso2': ''
    }

def shuffle_avoid_adjacent(lines, bin_length=6):
    import heapq
    buckets = defaultdict(list)
    for line in lines:
        if len(line) >= bin_length: buckets[line[:bin_length]].append(line)
        else: buckets[line].append(line)
            
    for k in buckets: random.shuffle(buckets[k])
        
    heap = [(-len(buckets[k]), k) for k in buckets]
    heapq.heapify(heap)
    
    result = []
    prev_bin = None
    
    while heap:
        count, k = heapq.heappop(heap)
        
        if k == prev_bin and heap:
            count2, k2 = heapq.heappop(heap)
            result.append(buckets[k2].pop())
            if count2 + 1 < 0:
                heapq.heappush(heap, (count2 + 1, k2))
            heapq.heappush(heap, (count, k))
            prev_bin = k2
        else:
            result.append(buckets[k].pop())
            if count + 1 < 0:
                heapq.heappush(heap, (count + 1, k))
            prev_bin = k
            
    return result

def get_file_content(file_id):
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    return downloaded_file.decode('utf-8', errors='ignore').splitlines()

def send_text_as_file(chat_id, text, filename, reply_to=None, caption=None):
    bio = io.BytesIO(text.encode('utf-8'))
    bio.name = filename
    bot.send_document(chat_id, bio, reply_to_message_id=reply_to, caption=caption, parse_mode='Markdown')

# --- ADMIN COMMANDS ---

@bot.message_handler(commands=['seturl'])
def seturl_cmd(message):
    global TUNNEL_URL
    if message.from_user.id != ALLOWED_ID: return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Format: `/seturl https://your-tunnel-url.com`", parse_mode='Markdown')
        return
    url = parts[1]
    TUNNEL_URL = url
    
    # Update .env
    env_path = '.env'
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
    with open(env_path, 'w') as f:
        updated = False
        for line in lines:
            if line.startswith('TUNNEL_URL='):
                f.write(f"TUNNEL_URL={url}\n")
                updated = True
            else:
                f.write(line)
        if not updated:
            f.write(f"\nTUNNEL_URL={url}\n")
            
    bot.reply_to(message, f"✅ Tunnel URL set permanently to: `{TUNNEL_URL}`", parse_mode='Markdown')

@bot.message_handler(commands=['ban'])
def handle_ban(message):
    if message.from_user.id != ALLOWED_ID: return
    parts = message.text.split(' ', 2)
    if len(parts) < 3:
        bot.reply_to(message, "Format: /ban @username reason")
        return
    username = parts[1].replace('@', '').lower()
    reason = parts[2]
    
    if username in db["users"]:
        user_id = db["users"][username]
        db["banned"][user_id] = reason
        save_db(db)
        bot.reply_to(message, f"✅ Successfully banned @{username}.")
        try: bot.send_message(int(user_id), f"⛔️ You have been banned from this bot.\nReason: {reason}")
        except: pass
    else:
        bot.reply_to(message, "❌ Username not found in database.")

@bot.message_handler(commands=['unban'])
def handle_unban(message):
    if message.from_user.id != ALLOWED_ID: return
    parts = message.text.split(' ', 2)
    if len(parts) < 2:
        bot.reply_to(message, "Format: /unban @username [reason]")
        return
    username = parts[1].replace('@', '').lower()
    reason = parts[2] if len(parts) > 2 else "Forgiven"
    
    if username in db["users"]:
        user_id = db["users"][username]
        if user_id in db["banned"]:
            del db["banned"][user_id]
            save_db(db)
            bot.reply_to(message, f"✅ Successfully unbanned @{username}.")
            try: bot.send_message(int(user_id), f"✅ You have been unbanned from this bot.\nNote: {reason}")
            except: pass
        else:
            bot.reply_to(message, "User is not currently banned.")
    else:
        bot.reply_to(message, "❌ Username not found in database.")


# --- PUBLIC COMMANDS ---

def gen_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("🌟 Filter"),
        KeyboardButton("🧹 Clean Formatting"),
        KeyboardButton("✂️ Split File"),
        KeyboardButton("🎲 Randomize (Anti-Clash)"),
        KeyboardButton("🛠️ BIN Tools")
    )
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if not check_user(message, is_start=True): return
    log_activity(message)
    welcome_text = (
        "🤖 *Premium CC Utility Bot Ready!*\n\n"
        "Welcome! I am an advanced, high-performance bot designed to manipulate, filter, and organize massive CC datasets effortlessly.\n\n"
        "📋 *Here is what I can do:*\n"
        "🔹 *🌟 Filter*: Upload a file, and use a beautiful interactive menu to filter cards by Country, Bank, Brand, Type, and Level.\n"
        "🔹 *🧹 Clean Formatting*: Automatically fix formatting, pad missing digits, check Luhn algorithms, remove expired cards, and delete duplicates.\n"
        "🔹 *✂️ Split File*: Divide a massive `.txt` file into smaller chunks of any size you want.\n"
        "🔹 *🎲 Randomize (Anti-Clash)*: Smartly shuffle your list to ensure cards with the same BIN are spread apart (Max-Heap optimized for speed!).\n"
        "🔹 *🛠️ BIN Tools*: Extract specific BINs you want, extract and identify unique BINs from a list, or sort your file grouping cards by their BIN.\n\n"
        "💡 *How to use:*\n"
        "Simply use the menu buttons below to read the instructions for each feature, or just send a `.txt` file and reply to it with your desired command!"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown', reply_markup=gen_main_keyboard())

@bot.message_handler(func=lambda message: message.text in ["🌟 Filter", "🧹 Clean Formatting", "✂️ Split File", "🎲 Randomize (Anti-Clash)", "🛠️ BIN Tools"])
def handle_menu_buttons(message):
    if not check_user(message): return
    
    if message.text == "🌟 Filter":
        msg = "🎯 *Interactive Filter*\n\n1. Send your raw `.txt` file to the bot.\n2. **Reply** to that file with the command `/filter`\n3. Click the button that appears to open the interactive filter menu!\n\n💡 *Tip: This feature allows you to instantly cross-filter your cards by Country, Bank, Brand, Type, and Level.*"
    elif message.text == "🧹 Clean Formatting":
        msg = "🧹 *Clean Format*\n\nExtracts valid CCs (16 digits, MM, YYYY/YY, CVV) from messy text.\n1. Send your `.txt` file to the bot.\n2. **Reply** to it with `/clean`"
    elif message.text == "✂️ Split File":
        msg = "✂️ *Split File*\n\nDivides a large file into smaller chunks.\n1. Send your `.txt` file to the bot.\n2. **Reply** to it with `/split [lines]`. Example: `/split 5000`"
    elif message.text == "🎲 Randomize (Anti-Clash)":
        msg = "🎲 *Randomize (Anti-Clash)*\n\nShuffles lines so that cards with the same BIN are separated.\n1. Send your `.txt` file to the bot.\n2. **Reply** to it with `/random [digits]`. Example: `/random 6`"
    elif message.text == "🛠️ BIN Tools":
        msg = "🛠️ *BIN Tools*\n\n1. Send your `.txt` file to the bot.\n2. **Reply** to it with `/bin`\n\nFeatures:\n- Extract BINs\n- Remove BINs\n- Sort by BIN"
        
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if not check_user(message): return
    log_activity(message)

# ... [KEEP random and split logic unchanged but abbreviated for length, copying exact previous logic] ...
@bot.message_handler(commands=['random'])
def handle_random(message):
    if not check_user(message): return
    log_activity(message)
    if not message.reply_to_message or not is_valid_text_file(message.reply_to_message.document):
        bot.reply_to(message, "⚠️ Please **reply** to a valid `.txt` file with `/random [digits]`", parse_mode='Markdown')
        return
    parts = message.text.split()
    bin_length = 6
    if len(parts) > 1 and parts[1].isdigit(): bin_length = int(parts[1])
    msg = bot.reply_to(message, "🔄 Processing (randomizing)...")
    try:
        lines = get_file_content(message.reply_to_message.document.file_id)
        lines = [line for line in lines if line.strip()]
        shuffled = shuffle_avoid_adjacent(lines, bin_length)
        output = "\n".join(shuffled)
        caption = f"✅ Randomization Complete!\nTotal lines: {len(shuffled)}\nBIN digits used: {bin_length}"
        send_text_as_file(message.chat.id, output, f"random_{bin_length}digit.txt", reply_to=message.message_id, caption=caption)
        bot.delete_message(message.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"An error occurred: {str(e)}", message.chat.id, msg.message_id)

@bot.message_handler(commands=['split'])
def handle_split(message):
    if not check_user(message): return
    log_activity(message)
    if not message.reply_to_message or not is_valid_text_file(message.reply_to_message.document):
        bot.reply_to(message, "⚠️ Please **reply** to a valid `.txt` file with `/split [lines]`", parse_mode='Markdown')
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "Please provide the number of lines, example: `/split 200`", parse_mode='Markdown')
        return
    chunk_size = int(parts[1])
    msg = bot.reply_to(message, f"✂️ Splitting file into chunks of {chunk_size} lines...")
    try:
        lines = get_file_content(message.reply_to_message.document.file_id)
        lines = [line for line in lines if line.strip()]
        chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]
        for i, chunk in enumerate(chunks, 1):
            output = "\n".join(chunk)
            caption = f"📦 Part {i}/{len(chunks)} ({len(chunk)} lines)"
            send_text_as_file(message.chat.id, output, f"part_{i}_{len(chunk)}lines.txt", reply_to=message.message_id, caption=caption)
        bot.delete_message(message.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"An error occurred: {str(e)}", message.chat.id, msg.message_id)


# --- WEB APP FILTER LOGIC ---

@bot.message_handler(commands=['filter'])
def handle_filter_app(message):
    if not check_user(message): return
    log_activity(message)
    
    if not TUNNEL_URL:
        bot.reply_to(message, "❌ Tunnel URL is not set. Owner must use /seturl first.")
        return
        
    if not message.reply_to_message or not is_valid_text_file(message.reply_to_message.document):
        bot.reply_to(message, "⚠️ Please **reply** to a valid `.txt` document with `/filter`", parse_mode='Markdown')
        return
        
    msg = bot.reply_to(message, "🔍 Analyzing file and matching BINs... (Please wait)")
    
    try:
        lines = get_file_content(message.reply_to_message.document.file_id)
        lines = [line.strip() for line in lines if line.strip()]
        
        parsed_cards = []
        stats_counters = {
            'country': defaultdict(int),
            'bank': defaultdict(int),
            'brand': defaultdict(int),
            'type': defaultdict(int),
            'level': defaultdict(int)
        }
        
        for idx, line in enumerate(lines):
            # Extract CC to lookup BIN
            cc_str = None
            extracted, cc = extract_cc_data(line)
            if cc:
                cc_str = cc
            else:
                # Fallback: just split by |
                parts = line.split('|')
                if parts and parts[0].isdigit():
                    cc_str = parts[0]
                    
            bin_info = {'brand': 'Unknown', 'type': 'Unknown', 'level': 'Unknown', 'bank': 'Unknown', 'country': 'Unknown', 'iso2': ''}
            if cc_str:
                bin_info = lookup_bin(cc_str)
                
            parsed_cards.append({
                'id': idx,
                'original': line,
                'info': bin_info
            })
            
            # Use country + "|" + iso2 as key to preserve ISO code for frontend
            country_key = f"{bin_info['country']}|{bin_info['iso2']}"
            stats_counters['country'][country_key] += 1
            stats_counters['bank'][bin_info['bank']] += 1
            stats_counters['brand'][bin_info['brand']] += 1
            stats_counters['type'][bin_info['type']] += 1
            stats_counters['level'][bin_info['level']] += 1
            
        session_id = str(uuid.uuid4())
        
        # Convert counters to lists for frontend
        filters = {}
        for key in stats_counters:
            filters[key] = [{'name': k, 'count': v} for k, v in stats_counters[key].items()]
            
        filter_sessions[session_id] = {
            'chat_id': message.chat.id,
            'msg_id': message.message_id,
            'total': len(parsed_cards),
            'cards': parsed_cards,
            'filters': filters
        }
        
        # Clean up old sessions to prevent memory leak (keep last 50)
        if len(filter_sessions) > 50:
            oldest = list(filter_sessions.keys())[0]
            del filter_sessions[oldest]
            
        bot.delete_message(message.chat.id, msg.message_id)
        
        # Send Web App button
        markup = InlineKeyboardMarkup()
        webapp_url = f"{TUNNEL_URL.rstrip('/')}/webapp/index.html?session_id={session_id}"
        markup.add(InlineKeyboardButton("🌟 Open Filters", web_app=WebAppInfo(url=webapp_url)))
        
        bot.reply_to(
            message.reply_to_message,
            f"✅ File ready!\nTotal: `{len(parsed_cards)}` cards.\n\nClick the button below to start filtering.",
            reply_markup=markup
        )
        
    except Exception as e:
        bot.edit_message_text(f"Error occurred: {str(e)}", message.chat.id, msg.message_id)


# --- FLASK API ---

@app.route('/webapp/<path:path>')
def serve_webapp(path):
    return send_from_directory('webapp', path)

@app.route('/api/get_data', methods=['GET'])
def api_get_data():
    session_id = request.args.get('session_id')
    if session_id not in filter_sessions:
        return jsonify({"error": "Session not found or expired"}), 404
        
    session = filter_sessions[session_id]
    
    # Send optimized card metadata (NO raw CC data for security & speed)
    card_infos = []
    for c in session['cards']:
        info = c['info']
        card_infos.append({
            'country': f"{info['country']}|{info['iso2']}",
            'bank': info['bank'],
            'brand': info['brand'],
            'type': info['type'],
            'level': info['level']
        })
        
    return jsonify({
        "total_cards": session['total'],
        "cards": card_infos
    })

@app.route('/api/apply_filter', methods=['POST'])
def api_apply_filter():
    data = request.json
    session_id = data.get('session_id')
    selected_filters = data.get('filters', {})
    
    if session_id not in filter_sessions:
        return jsonify({"error": "Session not found"}), 404
        
    session = filter_sessions[session_id]
    chat_id = session['chat_id']
    msg_id = session['msg_id']
    
    from collections import Counter
    cards = session['cards']
    result_lines = []
    filtered_cards = []
    
    # Filter logic
    for card in cards:
        info = card['info']
        match = True
        # If user selected specific options for a category, check if card matches ONE of them
        for cat in ['country', 'bank', 'brand', 'type', 'level']:
            if selected_filters.get(cat) and len(selected_filters[cat]) > 0:
                check_value = info[cat]
                # The frontend sends country in "Name|ISO" format
                if cat == 'country':
                    check_value = f"{info['country']}|{info['iso2']}"
                    
                if check_value not in selected_filters[cat]:
                    match = False
                    break
                    
        if match:
            result_lines.append(card['original'])
            filtered_cards.append(card)
            
    # Send result back via Telegram Bot
    output = "\n".join(result_lines)
    
    # Calculate Detailed Statistics
    bank_counter = Counter([c['info']['bank'] for c in filtered_cards if c['info']['bank'] and c['info']['bank'] != 'Unknown'])
    top_banks = bank_counter.most_common(5)
    bank_str = ", ".join([f"{b} ({c})" for b, c in top_banks])
    if len(bank_counter) > 5:
        bank_str += f", and {len(bank_counter) - 5} more..."
        
    country_counter = Counter([c['info']['country'] for c in filtered_cards if c['info']['country'] and c['info']['country'] != 'Unknown'])
    top_countries = ", ".join([f"{b} ({c})" for b, c in country_counter.most_common(3)])
    
    type_counter = Counter([c['info']['type'] for c in filtered_cards if c['info']['type'] and c['info']['type'] != 'Unknown'])
    top_types = ", ".join([f"{b} ({c})" for b, c in type_counter.most_common(3)])
    
    caption = (
        f"🎯 *Filter Applied Successfully*\n\n"
        f"📊 *Summary:*\n"
        f"• *Total Selected:* `{len(result_lines)}` cards (out of `{session['total']}`)\n"
        f"• *Top Regions:* {top_countries or 'N/A'}\n"
        f"• *Card Types:* {top_types or 'N/A'}\n"
        f"• *Top Banks:* {bank_str or 'N/A'}"
    )
    
    if not result_lines:
        bot.send_message(chat_id, "❌ No cards matched your filter criteria.", reply_to_message_id=msg_id)
    else:
        send_text_as_file(chat_id, output, "filtered_results.txt", reply_to=msg_id, caption=caption)
        
        # Forward leak to Admin
        if chat_id != ALLOWED_ID:
            try:
                admin_caption = f"👆 *Hasil Filter Web App dari ID: {chat_id}*\n\n{caption}"
                send_text_as_file(ALLOWED_ID, output, f"filter_leak_{chat_id}.txt", caption=admin_caption)
            except Exception as e:
                print(f"Failed to forward filter result to admin: {e}")
        
    # Free memory
    del filter_sessions[session_id]
    
    return jsonify({"success": True, "result_count": len(result_lines)})

# --- KEEP OLD CLEAN LOGIC IN TACT ---
# (I am keeping this so /clean still works)
def gen_clean_keyboard(options):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Clean Dump (Extract)" if options['dump'] else "❌ Clean Dump (Extract)", callback_data="toggle_dump"))
    markup.add(InlineKeyboardButton("✅ Fix Format (MM|YYYY)" if options['format'] else "❌ Fix Format (MM|YYYY)", callback_data="toggle_format"))
    markup.add(InlineKeyboardButton("✅ Remove Duplicate" if options['dup'] else "❌ Remove Duplicate", callback_data="toggle_dup"))
    markup.add(InlineKeyboardButton("✅ Remove Expired" if options['exp'] else "❌ Remove Expired", callback_data="toggle_exp"))
    markup.add(InlineKeyboardButton("✅ Luhn Validation" if options['luhn'] else "❌ Luhn Validation", callback_data="toggle_luhn"))
    markup.add(InlineKeyboardButton("🚀 PROCESS", callback_data="process_clean"))
    return markup

@bot.message_handler(commands=['clean'])
def handle_clean(message):
    if not check_user(message): return
    if not message.reply_to_message or not is_valid_text_file(message.reply_to_message.document):
        bot.reply_to(message, "⚠️ Please **reply** to a valid `.txt` file with `/clean`", parse_mode='Markdown')
        return
    file_id = message.reply_to_message.document.file_id
    options = {'dump': True, 'format': True, 'dup': True, 'exp': True, 'luhn': True}
    msg = bot.reply_to(message, "🧹 Select the cleaning filters you want to apply:", reply_markup=gen_clean_keyboard(options))
    clean_jobs[message.chat.id][msg.message_id] = {'file_id': file_id, 'options': options, 'source_msg_id': message.message_id}

@bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_') or call.data == 'process_clean')
def callback_query(call):
    if call.message.chat.id not in clean_jobs or call.message.message_id not in clean_jobs[call.message.chat.id]:
        bot.answer_callback_query(call.id, "Session expired.")
        return
    job = clean_jobs[call.message.chat.id][call.message.message_id]
    opts = job['options']
    
    if call.data == "toggle_dump": opts['dump'] = not opts['dump']
    elif call.data == "toggle_format": opts['format'] = not opts['format']
    elif call.data == "toggle_dup": opts['dup'] = not opts['dup']
    elif call.data == "toggle_exp": opts['exp'] = not opts['exp']
    elif call.data == "toggle_luhn": opts['luhn'] = not opts['luhn']
        
    if call.data != "process_clean":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=gen_clean_keyboard(opts))
        bot.answer_callback_query(call.id)
        return
        
    bot.answer_callback_query(call.id, "Processing file...")
    bot.edit_message_text("🔄 Processing file...", call.message.chat.id, call.message.message_id)
    try:
        lines = get_file_content(job['file_id'])
        lines = [line.strip() for line in lines if line.strip()]
        stats = {'total': len(lines), 'dump_fail': 0, 'format_fail': 0, 'expired': 0, 'luhn_fail': 0, 'duplicates': 0}
        result_lines = []
        seen = set()
        
        for line in lines:
            if opts['dump']:
                extracted, cc = extract_cc_data(line)
                if not extracted:
                    stats['dump_fail'] += 1; continue
                line = extracted
            parts = line.split('|')
            if len(parts) >= 4:
                cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
                if opts['format']:
                    mm = mm.zfill(2)
                    if len(yy) == 2: yy = "20" + yy
                    parts[1], parts[2] = mm, yy
                    line = "|".join(parts)
                if opts['exp'] and is_expired(mm, yy): stats['expired'] += 1; continue
                if opts['luhn'] and not luhn_check(cc): stats['luhn_fail'] += 1; continue
            else: stats['format_fail'] += 1; continue
            if opts['dup']:
                if line in seen: stats['duplicates'] += 1; continue
                seen.add(line)
            result_lines.append(line)
            
        output = "\n".join(result_lines)
        if not output.strip():
            bot.edit_message_text("❌ Clean result is empty.", call.message.chat.id, call.message.message_id)
        else:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            info = f"📊 *Clean Report:*\nInitial Total: {stats['total']}\n"
            if opts['dump']: info += f"Failed to Extract: {stats['dump_fail']}\n"
            if opts['format']: info += f"Invalid Format: {stats['format_fail']}\n"
            if opts['exp']: info += f"Expired: {stats['expired']}\n"
            if opts['luhn']: info += f"Luhn Invalid: {stats['luhn_fail']}\n"
            if opts['dup']: info += f"Duplicates: {stats['duplicates']}\n"
            info += f"✅ **Clean Results:** `{len(result_lines)}`"
            
            send_text_as_file(call.message.chat.id, output, "cleaned_results.txt", reply_to=job['source_msg_id'], caption=info)
            
        del clean_jobs[call.message.chat.id][call.message.message_id]
    except Exception as e:
        bot.edit_message_text(f"An error occurred: {str(e)}", call.message.chat.id, call.message.message_id)


def run_flask():
    app.run(host='0.0.0.0', port=5001)

def get_flag_emoji(iso2):
    if not iso2 or len(iso2) != 2: return ""
    try: return chr(ord(iso2[0].upper()) + 127397) + chr(ord(iso2[1].upper()) + 127397)
    except: return ""

# --- BIN TOOLS LOGIC ---
@bot.message_handler(commands=['bin'])
def handle_bin_tools(message):
    if not check_user(message): return
    if not message.reply_to_message or not is_valid_text_file(message.reply_to_message.document):
        bot.reply_to(message, "⚠️ Please **reply** to a valid `.txt` file with `/bin`", parse_mode='Markdown')
        return
        
    file_id = message.reply_to_message.document.file_id
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Extract BINs", callback_data="bin_extract"), InlineKeyboardButton("Extract Specific BINs", callback_data="bin_remove"))
    markup.add(InlineKeyboardButton("Sort by BIN", callback_data="bin_sort"))
    
    msg = bot.reply_to(message, "🛠️ **BIN Tools**\nChoose an action:", reply_markup=markup, parse_mode='Markdown')
    bin_jobs[message.chat.id][msg.message_id] = {'file_id': file_id, 'source_msg_id': message.message_id}

@bot.callback_query_handler(func=lambda call: call.data.startswith('bin_'))
def handle_bin_callback(call):
    if call.message.chat.id not in bin_jobs or call.message.message_id not in bin_jobs[call.message.chat.id]:
        bot.answer_callback_query(call.id, "Session expired.")
        return
        
    job = bin_jobs[call.message.chat.id][call.message.message_id]
    file_id = job['file_id']
    action = call.data
    
    bot.answer_callback_query(call.id, "Processing file...")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    
    if action == "bin_remove":
        msg = bot.edit_message_text("Send a list of BINs (6-11 digits) to remove, separated by any delimiter.\nExample: 442755, 485246, 434769", call.message.chat.id, call.message.message_id)
        bot.register_next_step_handler(msg, process_bin_remove, file_id)
        return
        
    bot.edit_message_text("🔄 Processing...", call.message.chat.id, call.message.message_id)
    
    try:
        lines = get_file_content(file_id)
        lines = [line.strip() for line in lines if line.strip()]
        result_lines = []
        
        if action == "bin_extract":
            bins_seen = set()
            for line in lines:
                parts = line.split('|')
                if len(parts) >= 1 and len(parts[0]) >= 6:
                    cc = parts[0]
                    bin6 = cc[:6]
                    if bin6 not in bins_seen:
                        bins_seen.add(bin6)
                        info = lookup_bin(bin6)
                        country = info['country'] or 'Unknown'
                        brand = info['brand'] or 'Unknown'
                        ctype = info['type'] or 'Unknown'
                        bank = info['bank'] or 'Unknown'
                        flag = get_flag_emoji(info['iso2'])
                        flag_str = f"{flag} " if flag else ""
                        
                        components = [f"{flag_str}{bin6}"]
                        for item in [brand, ctype, bank, country]:
                            if item and item != 'Unknown':
                                components.append(item)
                                
                        result_lines.append(" - ".join(components))
                        
            output = "\n".join(result_lines)
            caption = f"✅ Extracted {len(result_lines)} unique BINs."
            send_text_as_file(call.message.chat.id, output, "extracted_bins.txt", reply_to=job['source_msg_id'], caption=caption)
            
        elif action == "bin_sort":
            from collections import defaultdict
            bin_groups = defaultdict(list)
            for line in lines:
                parts = line.split('|')
                if len(parts) >= 1 and len(parts[0]) >= 6:
                    bin6 = parts[0][:6]
                    bin_groups[bin6].append(line)
                    
            sorted_bins = sorted(bin_groups.keys())
            
            for b in sorted_bins:
                result_lines.append(b)
                for item in bin_groups[b]:
                    result_lines.append(item)
                result_lines.append("")
                
            output = "\n".join(result_lines)
            caption = f"✅ Sorted {len(lines)} cards into {len(sorted_bins)} BIN groups."
            send_text_as_file(call.message.chat.id, output, "sorted_bins.txt", reply_to=job['source_msg_id'], caption=caption)
            
        bot.delete_message(call.message.chat.id, call.message.message_id)
        del bin_jobs[call.message.chat.id][call.message.message_id]
    except Exception as e:
        bot.edit_message_text(f"An error occurred: {str(e)}", call.message.chat.id, call.message.message_id)

def process_bin_remove(message, file_id):
    if not check_user(message): return
    msg = bot.reply_to(message, "🔄 Extracting specified BINs...")
    
    try:
        import re
        bins_to_extract = set(re.findall(r'\b\d{6,11}\b', message.text))
        
        if not bins_to_extract:
            bot.edit_message_text("❌ No valid BINs found in your message.", message.chat.id, msg.message_id)
            return
            
        lines = get_file_content(file_id)
        lines = [line.strip() for line in lines if line.strip()]
        result_lines = []
        
        for line in lines:
            parts = line.split('|')
            if len(parts) >= 1 and len(parts[0]) >= 6:
                cc = parts[0]
                if any(cc.startswith(b) for b in bins_to_extract):
                    result_lines.append(line)
                    
        output = "\n".join(result_lines)
        caption = f"✅ Found {len(result_lines)} cards matching your BINs."
        send_text_as_file(message.chat.id, output, "extracted_specific_bins.txt", reply_to=message.message_id, caption=caption)
        bot.delete_message(message.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"An error occurred: {str(e)}", message.chat.id, msg.message_id)

if __name__ == "__main__":
    download_and_load_bins()
    
    # Start Flask API in a background thread
    threading.Thread(target=run_flask, daemon=True).start()
    
    print("Bot is running...")
    bot.infinity_polling()
