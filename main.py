import sqlite3
import time
import os
import threading
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ================= CONFIGURATION =================
TOKEN = "9049025070:AAFfb9Gyujal8jh1U9WRd7ONtNEt3vQUXRQ"
ADMIN_ID = 6179056395 
# =================================================

# ডাটাবেস অটো-ক্লিনার (প্রতিবার রিস্টার্টে ডাটা মুছে নতুন করে তৈরি হবে, Render-এ ডাটা সেভ রাখতে চাইলে এই ২ লাইন মুছে দেবেন)
if os.path.exists('earn_bot.db'):
    os.remove('earn_bot.db')

conn = sqlite3.connect('earn_bot.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (user_id INTEGER PRIMARY KEY, points INTEGER DEFAULT 0, 
                   wallet TEXT DEFAULT NULL, referred_by INTEGER DEFAULT NULL, 
                   last_checkin TEXT DEFAULT NULL, total_referrals INTEGER DEFAULT 0, 
                   first_name TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS tasks 
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, link TEXT, reward INTEGER, timer INTEGER)''')
conn.commit()

# Helper Functions
def get_user(user_id):
    cursor.execute("SELECT points, wallet, referred_by, last_checkin, total_referrals FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def add_points(user_id, amount):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, points) VALUES (?, 0)", (user_id,))
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📋 Tasks", callback_data="show_tasks")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"), InlineKeyboardButton("🎁 Daily Check-in", callback_data="checkin")],
        [InlineKeyboardButton("🔗 Refer & Earn", callback_data="refer"), InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Add Task", callback_data="admin_add_task")],
        [InlineKeyboardButton("👥 User List", callback_data="admin_users")],
        [InlineKeyboardButton("💰 Edit Balance", callback_data="admin_edit_balance")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔙 Close Panel", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ================= USER COMMANDS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET first_name = ? WHERE user_id = ?", (first_name, user_id))
    conn.commit()
    
    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id:
                cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                if result and result[0] is None:
                    cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
                    cursor.execute("UPDATE users SET total_referrals = total_referrals + 1 WHERE user_id = ?", (referrer_id,))
                    conn.commit()
                    add_points(referrer_id, 100) 
                    await context.bot.send_message(chat_id=referrer_id, text="🎉 **New Referral!**\nSomeone joined using your link. You earned 100 Points.", parse_mode='Markdown')
        except ValueError:
            pass

    welcome_text = (
        f"👋 **Welcome, {first_name}!**\n\n"
        "You have successfully joined our official Earning Platform.\n\n"
        "💎 **Why choose us?**\n"
        "✅ 100% Genuine Payouts\n"
        "✅ Complete Tasks & Earn Points\n"
        "✅ Invite Friends for Bonus\n"
        "✅ Minimum Withdrawal: 1000 Pts = 1 USDT (BEP20)\n\n"
        "Start your earning journey today. Choose an option below:"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu(), parse_mode='Markdown')

# ================= ADMIN COMMANDS =================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    await update.message.reply_text("⚙️ **Welcome to Admin Panel**\nSelect an option:", reply_markup=get_admin_menu(), parse_mode='Markdown')

# ================= BUTTON HANDLER =================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
        
    user_id = query.from_user.id
    data = query.data
    
    user_data = get_user(user_id)
    if not user_data:
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        user_data = get_user(user_id)

    if data == "back_to_main":
        await query.message.reply_text("Choose an option below:", reply_markup=get_main_menu(), parse_mode='Markdown')
        
    # ---------------- ADMIN BUTTONS ----------------
    elif data == "admin_add_task":
        if user_id != ADMIN_ID: return
        await query.message.reply_text(
            "📝 **To add a task, send a message in this exact format:**\n\n"
            "`Task Name | Link | Reward | Wait Time (Seconds)`\n\n"
            "**Example:**\n"
            "`Join Telegram | https://t.me/telegram | 50 | 20`", 
            parse_mode='Markdown'
        )
        context.user_data['admin_action'] = 'add_task'

    elif data == "admin_users":
        if user_id != ADMIN_ID: return
        cursor.execute("SELECT user_id, points, total_referrals FROM users")
        users = cursor.fetchall()
        text = f"👥 **Total Users:** {len(users)}\n\n"
        for u in users[:15]:
            text += f"ID: `{u[0]}` | Bal: {u[1]} | Ref: {u[2]}\n"
        await query.message.reply_text(text, parse_mode='Markdown')

    elif data == "admin_edit_balance":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("Send in this format to edit balance:\n`UserID | Amount`\nExample: `12345678 | 500`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'edit_balance'
        
    elif data == "admin_broadcast":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("📢 **Please send the message you want to broadcast to all users:**")
        context.user_data['admin_action'] = 'broadcast'
        
    # ---------------- USER BUTTONS ----------------
    elif data == "balance":
        points = user_data[0]
        wallet = user_data[1]
        if wallet:
            text = f"💰 **Your Balance:** {points} Points\n\n🔗 **Connected Wallet:**\n`{wallet}`"
            keyboard = [[InlineKeyboardButton("🔄 Change Wallet", callback_data="connect_wallet")], [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
        else:
            text = f"💰 **Your Balance:** {points} Points\n\n⚠️ **Wallet Not Connected**"
            keyboard = [[InlineKeyboardButton("➕ Connect Wallet", callback_data="connect_wallet")], [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "connect_wallet":
        await query.message.reply_text("Please send your USDT BEP20 wallet address now (Must start with 0x and be 42 characters long):")
        context.user_data['awaiting_wallet'] = True

    elif data == "checkin":
        last_checkin = user_data[3]
        now = datetime.now()
        if last_checkin:
            last_time = datetime.strptime(last_checkin, '%Y-%m-%d %H:%M:%S')
            if now - last_time < timedelta(hours=24):
                await query.answer("❌ Already checked in! Come back later.", show_alert=True)
                return
        add_points(user_id, 50)
        cursor.execute("UPDATE users SET last_checkin = ? WHERE user_id = ?", (now.strftime('%Y-%m-%d %H:%M:%S'), user_id))
        conn.commit()
        await query.answer("✅ Daily check-in successful! You earned 50 Points.", show_alert=True)
        await query.message.reply_text("✅ Check-in successful! You earned 50 Points.", reply_markup=get_back_button())

    elif data == "refer":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        text = f"🔗 **Invite friends and earn 100 points per person!**\n\nYour Referral Link:\n`{ref_link}`\n\nShare this link with your friends."
        await query.message.reply_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "leaderboard":
        cursor.execute("SELECT first_name, points FROM users ORDER BY points DESC LIMIT 10")
        top_users = cursor.fetchall()
        text = "🏆 **Top 10 Earners Leaderboard** 🏆\n\n"
        for index, user in enumerate(top_users, start=1):
            name = user[0] if user[0] else "Anonymous"
            text += f"{index}. **{name}** - {user[1]} Points\n"
        await query.message.reply_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "show_tasks":
        cursor.execute("SELECT id, title, reward, timer FROM tasks")
        tasks = cursor.fetchall()
        if not tasks:
            await query.message.reply_text("No tasks available right now.", reply_markup=get_back_button())
            return
        keyboard = [[InlineKeyboardButton(f"{task[1]} (+{task[2]} pts)", callback_data=f"do_task_{task[0]}")] for task in tasks]
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        await query.message.reply_text("Select a task to complete:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("do_task_"):
        task_id = data.split("_")[2]
        cursor.execute("SELECT title, link, reward, timer FROM tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        context.user_data[f'task_start_{task_id}'] = time.time()
        keyboard = [
            [InlineKeyboardButton("🔗 Open Link", url=task[1])],
            [InlineKeyboardButton("✅ Verify", callback_data=f"verify_{task_id}_{task[2]}_{task[3]}")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
        ]
        await query.message.reply_text(
            f"1. Click 'Open Link' and complete the task.\n"
            f"2. Stay for at least **{task[3]} seconds**.\n"
            f"3. Come back and click 'Verify'.", 
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
        )

    elif data.startswith("verify_"):
        parts = data.split("_")
        task_id = parts[1]
        reward = int(parts[2])
        required_time = int(parts[3])
        
        start_time = context.user_data.get(f'task_start_{task_id}')
        if not start_time:
            await query.answer("❌ Please click 'Open Link' first!", show_alert=True)
            return
            
        time_spent = time.time() - start_time
        if time_spent < required_time:
            remaining = int(required_time - time_spent)
            await query.answer(f"❌ Too fast! Please wait {remaining} more seconds.", show_alert=True)
        else:
            add_points(user_id, reward)
            del context.user_data[f'task_start_{task_id}']
            await query.answer(f"✅ Task Verified! You earned {reward} Points.", show_alert=True)
            await query.message.reply_text(f"✅ Task completed! You earned {reward} Points.", reply_markup=get_back_button())

    elif data == "withdraw":
        points = user_data[0]
        wallet = user_data[1]
        if not wallet:
            await query.message.reply_text("⚠️ **Wallet Not Connected!**\nPlease go to Balance menu and connect your wallet first.", reply_markup=get_back_button())
            return
        if points < 1000:
            await query.message.reply_text(f"❌ **Insufficient Balance!**\nMinimum: 1000 Points. Your Balance: {points} Points", reply_markup=get_back_button())
            return
        
        await query.message.reply_text(
            f"✅ **Withdrawal Request Sent!**\n\nAmount: 1 USDT (BEP20)\nWallet: `{wallet}`\nPlease wait for Admin approval.", 
            reply_markup=get_back_button(), parse_mode='Markdown'
        )
        
        admin_keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"wd_approve_{user_id}"), InlineKeyboardButton("❌ Reject", callback_data=f"wd_reject_{user_id}")]
        ]
        await context.bot.send_message(
            chat_id=ADMIN_ID, 
            text=f"🚨 **New Withdrawal Request**\n\nUser ID: `{user_id}`\nWallet: `{wallet}`\nPoints: 1000", 
            reply_markup=InlineKeyboardMarkup(admin_keyboard),
            parse_mode='Markdown'
        )

    elif data.startswith("wd_approve_"):
        if user_id != ADMIN_ID: return
        target_user_id = int(data.split("_")[2])
        cursor.execute("UPDATE users SET points = points - 1000 WHERE user_id = ?", (target_user_id,))
        conn.commit()
        await query.edit_message_text(f"✅ Withdrawal Approved for User `{target_user_id}`.")
        await context.bot.send_message(chat_id=target_user_id, text="✅ **Your withdrawal request has been approved!**\nAdmin will send your USDT soon.")

    elif data.startswith("wd_reject_"):
        if user_id != ADMIN_ID: return
        target_user_id = int(data.split("_")[2])
        await query.edit_message_text(f"❌ Withdrawal Rejected for User `{target_user_id}`.")
        await context.bot.send_message(chat_id=target_user_id, text="❌ **Your withdrawal request has been rejected.**\nPlease contact admin for more info.")

# ================= MESSAGE HANDLER =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if context.user_data.get('awaiting_wallet'):
        if text.startswith("0x") and len(text) == 42:
            cursor.execute("UPDATE users SET wallet = ? WHERE user_id = ?", (text, user_id))
            conn.commit()
            await update.message.reply_text(f"✅ **Wallet Connected Successfully!**\n`{text}`", reply_markup=get_back_button(), parse_mode='Markdown')
            context.user_data['awaiting_wallet'] = False
        else:
            await update.message.reply_text("❌ **Invalid Wallet Address!**\nMust start with `0x` and be exactly 42 characters long.", parse_mode='Markdown')
        return

    if user_id == ADMIN_ID and context.user_data.get('admin_action'):
        action = context.user_data['admin_action']
        
        if action == 'add_task':
            try:
                parts = text.split("|")
                if len(parts) != 4:
                    raise ValueError("Invalid format")
                title = parts[0].strip()
                link = parts[1].strip()
                reward = int(parts[2].strip())
                timer = int(parts[3].strip())
                
                cursor.execute("INSERT INTO tasks (title, link, reward, timer) VALUES (?, ?, ?, ?)", (title, link, reward, timer))
                conn.commit()
                await update.message.reply_text(f"✅ **Task Added Successfully!**\n\nTitle: {title}\nReward: {reward} Points\nTimer: {timer} Seconds", parse_mode='Markdown')
            except Exception:
                await update.message.reply_text("❌ **Task is Invalid!**\n\nPlease use the correct format:\n`Task Name | Link | Reward | Timer`", parse_mode='Markdown')
            
            context.user_data['admin_action'] = None
            return

        elif action == 'edit_balance':
            try:
                parts = text.split("|")
                target_id, value = int(parts[0].strip()), int(parts[1].strip())
                cursor.execute("UPDATE users SET points = ? WHERE user_id = ?", (value, target_id))
                conn.commit()
                await update.message.reply_text(f"✅ Successfully set User `{target_id}` balance to {value} Points.", parse_mode='Markdown')
            except Exception:
                await update.message.reply_text("❌ Format Error! Please try again.")
            
            context.user_data['admin_action'] = None
            return

        elif action == 'broadcast':
            cursor.execute("SELECT user_id FROM users")
            users = cursor.fetchall()
            success = 0
            for u in users:
                try:
                    await context.bot.send_message(chat_id=u[0], text=f"📢 **Announcement:**\n\n{text}", parse_mode='Markdown')
                    success += 1
                except Exception:
                    pass
            
            await update.message.reply_text(f"✅ Broadcast sent to {success} users successfully!")
            context.user_data['admin_action'] = None
            return

# ================= FLASK SERVER FOR RENDER =================
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Bot is running perfectly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ================= MAIN RUNNER =================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Render-এর জন্য Flask সার্ভার চালু
    threading.Thread(target=run_flask, daemon=True).start()

    print("Bot and Web Server are running...")
    app.run_polling()

if __name__ == '__main__':
    main()
