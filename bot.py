# ============================================================
# SINGLE FILE BOT HOSTING SYSTEM
# Railway पर upload करो → Auto चलेगा
# Features: File Upload + Auto Host + Admin Panel
# ============================================================

import os
import sys
import subprocess
import json
import logging
import shutil
import re
from datetime import datetime
from pathlib import Path
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler, ConversationHandler
)

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8947957658:AAGhe3Bk1RHeo7fEfa7Qgbmwn1hL-HhHmMM")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "8017090914"))
HOSTING_DIR = "./bot_hosting"
DATA_FILE = os.path.join(HOSTING_DIR, "data.json")

# ================== STATES ==================
UPLOAD_FILE, ASK_NAME, CONFIRM = range(3)
BROADCAST_MSG = 10

# ================== LOGGING ==================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create hosting directory
os.makedirs(HOSTING_DIR, exist_ok=True)


# ================== DATA ==================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"users": {}, "uploads": []}


def save_data(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")


def add_user(user_id, username, first_name):
    data = load_data()
    if str(user_id) not in data["users"]:
        data["users"][str(user_id)] = {
            "id": user_id,
            "username": username or "N/A",
            "first_name": first_name or "N/A",
            "join_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "uploads": 0,
            "banned": False
        }
        save_data(data)
        return True
    return False


def add_upload(user_id, username, bot_name, file_name, file_size):
    data = load_data()
    record = {
        "user_id": user_id,
        "username": username or "N/A",
        "bot_name": bot_name,
        "file_name": file_name,
        "file_size_kb": round(file_size / 1024, 2),
        "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "uploaded",
        "pid": None
    }
    data["uploads"].append(record)
    if str(user_id) in data["users"]:
        data["users"][str(user_id)]["uploads"] += 1
    save_data(data)
    return record


def update_status(bot_name, status, pid=None):
    data = load_data()
    for u in data["uploads"]:
        if u["bot_name"] == bot_name:
            u["status"] = status
            if pid:
                u["pid"] = pid
            if status == "running":
                u["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif status == "stopped":
                u["stop_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            break
    save_data(data)


def is_admin(uid):
    return uid == ADMIN_CHAT_ID


# ================== BOT PROCESS ==================
def start_bot(bot_name):
    try:
        bot_dir = os.path.join(HOSTING_DIR, bot_name)
        if not os.path.exists(bot_dir):
            return False, "❌ Bot directory नहीं मिली"

        # Find .py file
        main_file = None
        for f in os.listdir(bot_dir):
            if f.endswith('.py'):
                main_file = f
                break

        if not main_file:
            return False, "❌ .py file नहीं मिली"

        main_path = os.path.join(bot_dir, main_file)
        log_file = os.path.join(bot_dir, "bot.log")
        pid_file = os.path.join(bot_dir, "bot.pid")

        # Kill old process
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    old_pid = int(f.read().strip())
                os.kill(old_pid, 9)
            except:
                pass

        # Install requirements if exists
        req_file = os.path.join(bot_dir, "requirements.txt")
        if os.path.exists(req_file):
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", req_file],
                    capture_output=True, timeout=180, cwd=bot_dir
                )
            except Exception as e:
                logger.error(f"Pip error: {e}")

        # Start process
        with open(log_file, 'a') as lf:
            proc = subprocess.Popen(
                [sys.executable, main_path],
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=bot_dir,
                start_new_session=True
            )

        with open(pid_file, 'w') as f:
            f.write(str(proc.pid))

        update_status(bot_name, "running", proc.pid)

        return True, (
            f"✅ *Bot शुरू हो गया!*\n\n"
            f"📁 नाम: `{bot_name}`\n"
            f"📄 File: `{main_file}`\n"
            f"🆔 PID: `{proc.pid}`\n"
            f"⏰ Time: `{datetime.now().strftime('%H:%M:%S')}`"
        )

    except Exception as e:
        logger.error(f"Start error: {e}")
        return False, f"❌ Error: {str(e)}"


def stop_bot(bot_name):
    try:
        bot_dir = os.path.join(HOSTING_DIR, bot_name)
        pid_file = os.path.join(bot_dir, "bot.pid")

        if not os.path.exists(pid_file):
            return False, "❌ Bot चल नहीं रहा"

        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())

        try:
            os.kill(pid, 9)
        except:
            pass

        os.remove(pid_file)
        update_status(bot_name, "stopped")
        return True, f"✅ Bot `{bot_name}` बंद हो गया"

    except Exception as e:
        return False, f"❌ Error: {str(e)}"


def bot_status(bot_name):
    bot_dir = os.path.join(HOSTING_DIR, bot_name)
    pid_file = os.path.join(bot_dir, "bot.pid")

    if not os.path.exists(bot_dir):
        return "❌ नहीं मिला"

    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return "🟢 चल रहा है"
        except:
            return "🔴 बंद है"
    return "🔴 बंद है"


def get_logs(bot_name, n=30):
    log_file = os.path.join(HOSTING_DIR, bot_name, "bot.log")
    if not os.path.exists(log_file):
        return "कोई log नहीं"
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            return "".join(lines[-n:]) or "Log खाली है"
    except:
        return "Log पढ़ नहीं सका"


# ================== KEYBOARDS ==================
def main_kb(uid):
    if is_admin(uid):
        kb = [
            [KeyboardButton("📤 Upload Bot"), KeyboardButton("🤖 My Bots")],
            [KeyboardButton("📊 Stats"), KeyboardButton("👥 All Users")],
            [KeyboardButton("📦 All Uploads"), KeyboardButton("📢 Broadcast")],
            [KeyboardButton("📝 Help")]
        ]
    else:
        kb = [
            [KeyboardButton("📤 Upload Bot"), KeyboardButton("🤖 My Bots")],
            [KeyboardButton("📊 Stats"), KeyboardButton("📝 Help")]
        ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def confirm_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes - Host करो", callback_data="yes")],
        [InlineKeyboardButton("❌ No - Cancel", callback_data="no")]
    ])


def action_kb(bot_name):
    st = bot_status(bot_name)
    kb = []
    if "चल रहा" in st:
        kb.append([InlineKeyboardButton("🛑 Stop", callback_data=f"stop_{bot_name}")])
    else:
        kb.append([InlineKeyboardButton("🚀 Start", callback_data=f"start_{bot_name}")])
    kb.append([InlineKeyboardButton("📋 Logs", callback_data=f"logs_{bot_name}")])
    kb.append([InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{bot_name}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
    return InlineKeyboardMarkup(kb)


# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    new = add_user(u.id, u.username, u.first_name)

    txt = f"""
{'🎉 स्वागत है!' if new else '👋 वापस स्वागत!'}

🤖 *Bot Hosting System*

नमस्ते *{u.first_name}*!

*आप ये कर सकते हो:*
• 📤 अपनी Python file upload करो
• 🤖 अपने bots देखो
• 🚀 Bot start/stop करो
• 📋 Logs देखो

🆔 *Your ID:* `{u.id}`
{'🔐 Role: ADMIN' if is_admin(u.id) else '👤 Role: USER'}

*शुरू करने के लिए "📤 Upload Bot" दबाओ*
"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb(u.id))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = """
📝 *Help — Bot Hosting System*

*📤 Bot Upload करने के लिए:*
1️⃣ "📤 Upload Bot" दबाओ
2️⃣ `.py` file भेजो (10MB तक)
3️⃣ Bot का नाम बताओ
4️⃣ Yes दबाओ
5️⃣ Bot auto चालू हो जाएगा ✅

*🎛️ Bot Control:*
• 🚀 Start — चालू करो
• 🛑 Stop — बंद करो
• 📋 Logs — Error देखो
• 🗑️ Delete — हटाओ

*⚠️ ध्यान दें:*
• सिर्फ `.py` files
• Max 10 MB
• Requirements.txt भी भेज सकते हो
"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb(update.effective_user.id))


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = load_data()
    total_u = len(d["users"])
    total_b = len(d["uploads"])
    running = sum(1 for x in d["uploads"] if "चल रहा" in bot_status(x["bot_name"]))

    txt = f"""
📊 *Statistics*

• 👥 Total Users: `{total_u}`
• 📦 Total Uploads: `{total_b}`
• 🟢 Running Bots: `{running}`
• 🔴 Stopped Bots: `{total_b - running}`
"""
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb(update.effective_user.id))


# ================== UPLOAD FLOW ==================
async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📤 *Python file भेजो*\n\n"
        "• सिर्फ `.py` format\n"
        "• Max size: 10 MB\n"
        "• साथ में `requirements.txt` भी भेज सकते हो\n\n"
        "*📎 Attach button दबाकर file भेजो*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Cancel")]],
            resize_keyboard=True
        )
    )
    return UPLOAD_FILE


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("❌ Cancel", reply_markup=main_kb(update.effective_user.id))
        return ConversationHandler.END

    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ कोई file नहीं मिली। दोबारा भेजो।")
        return UPLOAD_FILE

    file_name = doc.file_name or "bot.py"

    if not file_name.endswith(".py"):
        await update.message.reply_text(
            "❌ सिर्फ `.py` file accept होती है!\n\n"
            "Python file भेजो।"
        )
        return UPLOAD_FILE

    if doc.file_size and doc.file_size > 10 * 1024 * 1024:
        await update.message.reply_text("❌ File 10 MB से बड़ी है!")
        return UPLOAD_FILE

    context.user_data["file_id"] = doc.file_id
    context.user_data["file_name"] = file_name
    context.user_data["file_size"] = doc.file_size or 0

    await update.message.reply_text(
        f"✅ File मिल गई: `{file_name}`\n\n"
        f"अब *Bot का नाम* भेजो:\n\n"
        f"Example: `mybot`, `salebot`, `test123`\n\n"
        f"⚠️ सिर्फ letters, digits, `_` allowed",
        parse_mode="Markdown"
    )
    return ASK_NAME


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()

    if not name or len(name) > 30:
        await update.message.reply_text("❌ नाम खाली या 30 chars से बड़ा है। दोबारा भेजो:")
        return ASK_NAME

    if not re.match(r'^[a-zA-Z0-9_]+$', name):
        await update.message.reply_text("❌ सिर्फ letters, digits, `_` allowed. दोबारा:")
        return ASK_NAME

    if os.path.exists(os.path.join(HOSTING_DIR, name)):
        await update.message.reply_text(f"❌ `{name}` नाम पहले से है! दूसरा भेजो:")
        return ASK_NAME

    context.user_data["bot_name"] = name
    fn = context.user_data.get("file_name", "bot.py")

    await update.message.reply_text(
        f"📋 *Confirm करें*\n\n"
        f"📄 File: `{fn}`\n"
        f"🤖 Bot Name: `{name}`\n\n"
        f"Host करना है?",
        parse_mode="Markdown",
        reply_markup=confirm_kb()
    )
    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    u = update.effective_user

    if q.data == "no":
        await q.edit_message_text("❌ Upload cancel")
        context.user_data.clear()
        await q.message.reply_text("मुख्य मेनू:", reply_markup=main_kb(u.id))
        return ConversationHandler.END

    await q.edit_message_text("⏳ Upload हो रहा है...")

    try:
        fid = context.user_data["file_id"]
        fname = context.user_data["file_name"]
        bname = context.user_data["bot_name"]
        fsize = context.user_data["file_size"]

        bdir = os.path.join(HOSTING_DIR, bname)
        os.makedirs(bdir, exist_ok=True)

        f = await context.bot.get_file(fid)
        fpath = os.path.join(bdir, fname)
        await f.download_to_drive(fpath)

        add_upload(u.id, u.username or u.first_name, bname, fname, fsize)

        await q.edit_message_text(
            f"✅ *File upload हो गई!*\n\n"
            f"📁 Bot: `{bname}`\n"
            f"📄 File: `{fname}`\n\n"
            f"🚀 अब start कर रहा हूं...",
            parse_mode="Markdown"
        )

        success, msg = start_bot(bname)
        await q.message.reply_text(msg, parse_mode="Markdown")

        # Notify admin
        try:
            admin_msg = (
                f"🔔 *नया Upload!*\n\n"
                f"👤 User: {u.first_name}\n"
                f"🆔 ID: `{u.id}`\n"
                f"📛 Username: @{u.username or 'N/A'}\n"
                f"📁 Bot: `{bname}`\n"
                f"📄 File: `{fname}`\n"
                f"🕐 Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"📊 Status: {'🟢 Running' if success else '🔴 Failed'}"
            )
            await context.bot.send_message(ADMIN_CHAT_ID, admin_msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Admin notify: {e}")

        context.user_data.clear()

    except Exception as e:
        logger.error(f"Upload error: {e}")
        await q.edit_message_text(f"❌ Error: {str(e)}")

    await q.message.reply_text("मुख्य मेनू:", reply_markup=main_kb(u.id))
    return ConversationHandler.END


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancel", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END


# ================== MY BOTS ==================
async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    d = load_data()

    if is_admin(uid):
        uploads = d["uploads"]
    else:
        uploads = [u for u in d["uploads"] if u["user_id"] == uid]

    if not uploads:
        await update.message.reply_text(
            "📭 कोई bot नहीं है\n\n📤 'Upload Bot' दबाकर upload करो",
            reply_markup=main_kb(uid)
        )
        return

    txt = f"🤖 *आपके Bots ({len(uploads)})*\n\n"
    for i, u in enumerate(uploads[-15:], 1):
        st = bot_status(u["bot_name"])
        txt += f"{i}. *{u['bot_name']}* — {st}\n"
        txt += f"   📅 {u['upload_time'][:10]}\n\n"

    kb = []
    for u in uploads[-10:]:
        kb.append([InlineKeyboardButton(f"⚙️ {u['bot_name']}", callback_data=f"manage_{u['bot_name']}")])

    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    name = q.data.replace("manage_", "")
    st = bot_status(name)

    await q.edit_message_text(
        f"🤖 *Bot: {name}*\n\n📊 Status: {st}",
        parse_mode="Markdown",
        reply_markup=action_kb(name)
    )


async def action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data

    if d == "back":
        await q.edit_message_text("मुख्य मेनू के लिए /start दबाओ")
        return

    if d.startswith("start_"):
        name = d.replace("start_", "")
        await q.edit_message_text(f"⏳ `{name}` start हो रहा है...", parse_mode="Markdown")
        _, msg = start_bot(name)
        await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=action_kb(name))

    elif d.startswith("stop_"):
        name = d.replace("stop_", "")
        _, msg = stop_bot(name)
        await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=action_kb(name))

    elif d.startswith("logs_"):
        name = d.replace("logs_", "")
        logs = get_logs(name, 25)
        if len(logs) > 3500:
            logs = logs[-3500:]
        await q.edit_message_text(
            f"📋 *Logs: {name}*\n\n```\n{logs}\n```",
            parse_mode="Markdown"
        )

    elif d.startswith("del_"):
        name = d.replace("del_", "")
        stop_bot(name)
        bdir = os.path.join(HOSTING_DIR, name)
        if os.path.exists(bdir):
            shutil.rmtree(bdir, ignore_errors=True)
        data = load_data()
        data["uploads"] = [u for u in data["uploads"] if u["bot_name"] != name]
        save_data(data)
        await q.edit_message_text(f"🗑️ `{name}` delete हो गया", parse_mode="Markdown")


# ================== ADMIN ==================
async def all_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only!")
        return

    users = load_data()["users"]
    if not users:
        await update.message.reply_text("कोई user नहीं")
        return

    txt = f"👥 *Total Users: {len(users)}*\n\n"
    for uid, u in list(users.items())[:40]:
        txt += f"• `{uid}` — {u.get('first_name', 'N/A')} (@{u.get('username', 'N/A')})\n"
        txt += f"  📅 {u.get('join_date', '')[:10]} | 📦 {u.get('uploads', 0)}\n\n"

    if len(txt) > 4000:
        txt = txt[:4000] + "..."
    await update.message.reply_text(txt, parse_mode="Markdown")


async def all_uploads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only!")
        return

    ups = load_data()["uploads"]
    if not ups:
        await update.message.reply_text("कोई upload नहीं")
        return

    txt = f"📦 *Total Uploads: {len(ups)}*\n\n"
    for i, u in enumerate(ups[-25:], 1):
        st = bot_status(u["bot_name"])
        txt += f"*{i}. {u['bot_name']}* {st}\n"
        txt += f"👤 `{u['user_id']}` — {u.get('username', 'N/A')}\n"
        txt += f"📄 `{u['file_name']}` ({u.get('file_size_kb', 0)} KB)\n"
        txt += f"🕐 {u['upload_time']}\n\n"

    if len(txt) > 4000:
        txt = txt[:4000] + "..."
    await update.message.reply_text(txt, parse_mode="Markdown")


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only!")
        return ConversationHandler.END

    await update.message.reply_text(
        "📢 *Broadcast*\n\nजो message सबको भेजना है वो भेजो:\n\nCancel: /cancel",
        parse_mode="Markdown"
    )
    return BROADCAST_MSG


async def broadcast_send(update: Update, context: ContextTypes.DEFA
