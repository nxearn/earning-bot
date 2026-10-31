import sqlite3
import time
import os
import threading
import random
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ================= CONFIGURATION =================
TOKEN = os.environ.get("TELEGRAM_TOKEN") 
ADMIN_ID = 6179056395 
SUPPORT_USERNAME = "@YourSupportUsername" # এখানে আপনার টেলিগ্রাম ইউজারনেম দিন
# =================================================

if os.path.exists('earn_bot.db'):
    os.remove('earn_bot.db')

conn = sqlite3.connect('earn_bot.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (user_id INTEGER PRIMARY KEY, points INTEGER DEFAULT 0, 
                   wallet TEXT DEFAULT NULL, referred_by INTEGER DEFAULT NULL, 
                   last_checkin TEXT DEFAULT NULL, last_spin TEXT DEFAULT NULL,
                   total_referrals INTEGER DEFAULT 0, first_name TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS tasks 
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, link TEXT, reward INTEGER, timer INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS user_tasks 
                  (user_id INTEGER, task_id INTEGER, completed_at TEXT, UNIQUE(user_id, task_id))''')
cursor.execute('''CREATE TABLE IF NOT EXISTS task_history 
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_name TEXT, reward INTEGER, date TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS withdraw_history 
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, wallet TEXT, status TEXT, date TEXT)''')
conn.commit()

def get_user(user_id):
    cursor.execute("SELECT points, wallet, referred_by, last_checkin, last_spin, total_referrals FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def add_points(user_id, amount):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, points) VALUES (?, 0)", (user_id,))
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

# মেইন মেনুর ডিজাইন (নিচে নোটিশ বোর্ড যুক্ত)
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📋 Tasks", callback_data="show_tasks"), InlineKeyboardButton("🎰 Lucky Spin", callback_data="spin")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"), InlineKeyboardButton("🎁 Daily Check-in", callback_data="checkin")],
        [InlineKeyboardButton("🔗 Refer & Earn", callback_data="refer"), InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("📜 Task History", callback_data="task_history"), InlineKeyboardButton("📊 Withdraw History", callback_data="wd_history")],
        [InlineKeyboardButton("🆘 Support", url="https://t.me/" + SUPPORT_USERNAME.replace("@", "")), InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_menu_text(first_name="User"):
    text = (
        f"👋 **Welcome, {first_name}!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🟢 **Server Status:** Online\n"
        "💎 **Platform:** 100% Genuine & Trusted\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 **Earn free USDT by completing simple tasks.**\n\n"
        "✅ Complete Tasks & Earn Points\n"
        "✅ Invite Friends for Bonus\n"
        "✅ Minimum Withdrawal: 1000 Pts = 1 USDT\n\n"
        "👇 **Choose an option below to start:**\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "📢 **Notice:** Please complete tasks honestly. Fake accounts will be banned!\n"
        "❓ Need help? Contact Support."
    )
    return text

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Add Task", callback_data="admin_add_task"), InlineKeyboardButton("🗑 Delete Task", callback_data="admin_del_task")],
        [InlineKeyboardButton("👥 User List", callback_data="admin_users"), InlineKeyboardButton("🔄 Refresh Users", callback_data="admin_users")],
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
                    try:
                        await context.bot.send_message(chat_id=referrer_id, text=f"🎉 **New Referral!**\n{first_name} joined using your link. You earned 100 Points.", parse_mode='Markdown')
                    except: pass
        except ValueError:
            pass

    # নোটিশ বোর্ডসহ মেইন মেনু পাঠানো
    await update.message.reply_text(get_main_menu_text(first_name), reply_markup=get_main_menu(), parse_mode='Markdown')

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

    # মেইন মেনুতে ফেরার সময়ও নোটিশ বোর্ড দেখাবে
    if data == "back_to_main":
        first_name = query.from_user.first_name
        await query.message.reply_text(get_main_menu_text(first_name), reply_markup=get_main_menu(), parse_mode='Markdown')
        
    # ---------------- ADMIN BUTTONS ----------------
    elif data == "admin_add_task":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("📝 Send task in format:\n`Task Name | Link | Reward | Wait Time`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'add_task'

    elif data == "admin_del_task":
        if user_id != ADMIN_ID: return
        cursor.execute("SELECT id, title FROM tasks")
        tasks = cursor.fetchall()
        if not tasks:
            await query.message.reply_text("No tasks available to delete.")
            return
        task_list = "🗑 **Active Tasks:**\n\n"
        for t in tasks:
            task_list += f"ID: `{t[0]}` | {t[1]}\n"
        task_list += "\nSend the **Task ID** to delete."
        await query.message.reply_text(task_list, parse_mode='Markdown')
        context.user_data['admin_action'] = 'delete_task'

    elif data == "admin_users":
        if user_id != ADMIN_ID: return
        cursor.execute("SELECT user_id, first_name, points, total_referrals FROM users ORDER BY points DESC LIMIT 20")
        users = cursor.fetchall()
        text = f"👥 **Top 20 Users**\n\n"
        for u in users:
            name = u[1] if u[1] else "Anonymous"
            text += f"👤 {name} | `{u[0]}`\n💰 Bal: {u[2]} | 🤝 Ref: {u[3]}\n\n"
        await query.message.reply_text(text, reply_markup=get_admin_menu(), parse_mode='Markdown')

    elif data == "admin_edit_balance":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("Format: `UserID | Amount`\nExample: `12345678 | 500`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'edit_balance'
        
    elif data == "admin_broadcast":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("📢 Send the message to broadcast:")
        context.user_data['admin_action'] = 'broadcast'
        
    # ---------------- USER BUTTONS ----------------
    elif data == "balance":
        points = user_data[0]
        wallet = user_data[1]
        
        progress = min(int((points / 1000) * 10), 10)
        bar = "█" * progress + "░" * (10 - progress)
        
        if wallet:
            text = (
                f"💰 **Your Balance:** {points} Points\n"
                f"📈 **Withdraw Progress:**\n`[{bar}]` {points}/1000\n\n"
                f"🔗 **Wallet:**\n`{wallet}`\n\n"
                "➖➖➖➖➖➖➖➖➖➖\n"
                "📢 **Note:** Minimum 1000 Points required for withdrawal."
            )
            keyboard = [[InlineKeyboardButton("🔄 Change Wallet", callback_data="connect_wallet")], [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
        else:
            text = (
                f"💰 **Your Balance:** {points} Points\n"
                f"📈 **Withdraw Progress:**\n`[{bar}]` {points}/1000\n\n"
                f"⚠️ **Wallet Not Connected**\n\n"
                "➖➖➖➖➖➖➖➖➖➖\n"
                "📢 **Note:** Connect your BEP20 wallet to receive payments."
            )
            keyboard = [[InlineKeyboardButton("➕ Connect Wallet", callback_data="connect_wallet")], [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "connect_wallet":
        await query.message.reply_text("Send your USDT BEP20 address (Must start with 0x and be 42 characters):\n\n➖➖➖➖➖➖➖➖➖➖\n📢 **Note:** Please double-check your address. Wrong address will result in lost funds.")
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
        await query.answer("✅ Check-in successful! You earned 50 Points.", show_alert=True)
        await query.message.reply_text("✅ Check-in successful! You earned 50 Points.\n\n➖➖➖➖➖➖➖➖➖➖\nCome back tomorrow for another 50 points!", reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "spin":
        last_spin = user_data[4]
        now = datetime.now()
        if last_spin:
            last_time = datetime.strptime(last_spin, '%Y-%m-%d %H:%M:%S')
            if now - last_time < timedelta(hours=24):
                await query.answer("❌ You already spun today! Come back tomorrow.", show_alert=True)
                return
        
        won_points = random.choices([1000, 500, 100, 50, 20], weights=[1, 2, 7, 20, 70], k=1)[0]
        
        add_points(user_id, won_points)
        cursor.execute("UPDATE users SET last_spin = ? WHERE user_id = ?", (now.strftime('%Y-%m-%d %H:%M:%S'), user_id))
        conn.commit()
        await query.answer(f"🎉 You won {won_points} Points!", show_alert=True)
        await query.message.reply_text(f"🎰 **Spin Result:** You won **{won_points} Points**!\n\n➖➖➖➖➖➖➖➖➖➖\nCome back tomorrow for another spin.", reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "task_history":
        cursor.execute("SELECT task_name, reward, date FROM task_history WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
        history = cursor.fetchall()
        if not history:
            await query.message.reply_text("You haven't completed any tasks yet.", reply_markup=get_back_button())
            return
        text = "📜 **Your Last 5 Tasks:**\n\n"
        for h in history:
            text += f"✅ {h[0]} | +{h[1]} Pts | {h[2]}\n"
        await query.message.reply_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "wd_history":
        cursor.execute("SELECT amount, wallet, status, date FROM withdraw_history WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
        history = cursor.fetchall()
        if not history:
            await query.message.reply_text("You have no withdrawal history.", reply_markup=get_back_button())
            return
        text = "📊 **Your Last 5 Withdrawals:**\n\n"
        for h in history:
            status_icon = "✅" if h[2] == "Approved" else "❌" if h[2] == "Rejected" else "⏳"
            text += f"{status_icon} {h[0]} Pts | {h[2]} | {h[3]}\n"
        await query.message.reply_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "refer":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        text = f"🔗 **Invite friends and earn 100 points per person!**\n\nYour Referral Link:\n`{ref_link}`\n\n➖➖➖➖➖➖➖➖➖➖\n📢 **Note:** Your friend must complete at least one task for you to get the bonus."
        await query.message.reply_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "leaderboard":
        cursor.execute("SELECT first_name, points FROM users ORDER BY points DESC LIMIT 10")
        top_users = cursor.fetchall()
        text = "🏆 **Top 10 Earners** 🏆\n\n"
        for i, u in enumerate(top_users, start=1):
            text += f"{i}. {u[0]} - {u[1]} Points\n"
        text += "\n➖➖➖➖➖➖➖➖➖➖\nKeep earning to secure your spot in the Top 10!"
        await query.message.reply_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "show_tasks":
        cursor.execute("SELECT task_id FROM user_tasks WHERE user_id = ?", (user_id,))
        completed_tasks = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT id, title, reward, timer FROM tasks")
        tasks = cursor.fetchall()
        
        if not tasks:
            await query.message.reply_text("No tasks available right now. Please check back later.", reply_markup=get_back_button())
            return
            
        keyboard = []
        for task in tasks:
            if task[0] in completed_tasks:
                keyboard.append([InlineKeyboardButton(f"✅ {task[1]} (Completed)", callback_data="already_done")])
            else:
                keyboard.append([InlineKeyboardButton(f"{task[1]} (+{task[2]} pts)", callback_data=f"do_task_{task[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        await query.message.reply_text("📋 **Available Tasks:**\n\nSelect a task to complete. Make sure to follow the timer rules.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "already_done":
        await query.answer("✅ You have already completed this task!", show_alert=True)

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
        await query.message.reply_text(f"1. Open Link\n2. Wait {task[3]} seconds\n3. Click Verify\n\n➖➖➖➖➖➖➖➖➖➖\n📢 **Note:** Clicking Verify too early will fail.", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("verify_"):
        parts = data.split("_")
        task_id, reward, req_time = parts[1], int(parts[2]), int(parts[3])
        
        cursor.execute("SELECT * FROM user_tasks WHERE user_id = ? AND task_id = ?", (user_id, task_id))
        if cursor.fetchone():
            await query.answer("❌ Already completed!", show_alert=True)
            return
        
        start_time = context.user_data.get(f'task_start_{task_id}')
        if not start_time:
            await query.answer("❌ Click 'Open Link' first!", show_alert=True)
            return
            
        if time.time() - start_time < req_time:
            await query.answer("❌ Too fast! Wait a bit.", show_alert=True)
        else:
            add_points(user_id, reward)
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (?, ?, ?)", (user_id, task_id, now_str))
            cursor.execute("SELECT title FROM tasks WHERE id = ?", (task_id,))
            task_title = cursor.fetchone()[0]
            cursor.execute("INSERT INTO task_history (user_id, task_name, reward, date) VALUES (?, ?, ?, ?)", (user_id, task_title, reward, now_str))
            conn.commit()
            
            del context.user_data[f'task_start_{task_id}']
            await query.answer(f"✅ Done! You earned {reward} Points.", show_alert=True)
            await query.message.reply_text(f"✅ Task completed! You earned {reward} Points.\n\n➖➖➖➖➖➖➖➖➖➖\nCheck your balance to see progress.", reply_markup=get_back_button())

            # অ্যাডমিনকে লাইভ নোটিফিকেশন
            try:
                cursor.execute("SELECT first_name FROM users WHERE user_id = ?", (user_id,))
                user_name = cursor.fetchone()[0]
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"📢 **Live Update:**\nUser {user_name} just completed a task and earned {reward} Points!")
            except: pass

    elif data == "withdraw":
        points, wallet = user_data[0], user_data[1]
        if not wallet:
            await query.message.reply_text("⚠️ Connect wallet first from Balance menu.\n\n➖➖➖➖➖➖➖➖➖➖\n📢 **Note:** Your BEP20 wallet is required to receive USDT.", reply_markup=get_back_button())
            return
        if points < 1000:
            await query.message.reply_text(f"❌ Minimum 1000 Points needed. Your Balance: {points}\n\n➖➖➖➖➖➖➖➖➖➖\nComplete more tasks to reach the minimum.", reply_markup=get_back_button())
            return
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("INSERT INTO withdraw_history (user_id, amount, wallet, status, date) VALUES (?, 1000, ?, 'Pending', ?)", (user_id, wallet, now_str))
        conn.commit()
        
        await query.message.reply_text("✅ Withdrawal request sent! Please wait for approval.\n\n➖➖➖➖➖➖➖➖➖➖\n📢 **Note:** Payments are processed within 24 hours.", reply_markup=get_back_button(), parse_mode='Markdown')
        
        admin_keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"wd_approve_{user_id}"), InlineKeyboardButton("❌ Reject", callback_data=f"wd_reject_{user_id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 **Withdraw Request**\nUser: `{user_id}`\nWallet: `{wallet}`\nPoints: 1000", reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode='Markdown')

    elif data.startswith("wd_approve_"):
        if user_id != ADMIN_ID: return
        target_user_id = int(data.split("_")[2])
        cursor.execute("UPDATE users SET points = points - 1000 WHERE user_id = ?", (target_user_id,))
        cursor.execute("UPDATE withdraw_history SET status = 'Approved' WHERE user_id = ? AND status = 'Pending'", (target_user_id,))
        conn.commit()
        await query.edit_message_text(f"✅ Approved for `{target_user_id}`.")
        await context.bot.send_message(chat_id=target_user_id, text="✅ Your withdrawal has been approved!\n\n➖➖➖➖➖➖➖➖➖➖\nThank you for using our platform.")

    elif data.startswith("wd_reject_"):
        if user_id != ADMIN_ID: return
        target_user_id = int(data.split("_")[2])
        cursor.execute("UPDATE withdraw_history SET status = 'Rejected' WHERE user_id = ? AND status = 'Pending'", (target_user_id,))
        conn.commit()
        await query.edit_message_text(f"❌ Rejected for `{target_user_id}`.")
        await context.bot.send_message(chat_id=target_user_id, text="❌ Your withdrawal request was rejected.\n\n➖➖➖➖➖➖➖➖➖➖\nPlease contact support for more info.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if context.user_data.get('awaiting_wallet'):
        if text.startswith("0x") and len(text) == 42:
            cursor.execute("UPDATE users SET wallet = ? WHERE user_id = ?", (text, user_id))
            conn.commit()
            await update.message.reply_text(f"✅ Wallet Connected:\n`{text}`\n\n➖➖➖➖➖➖➖➖➖➖\nYou can now withdraw once you reach 1000 points.", reply_markup=get_back_button(), parse_mode='Markdown')
            context.user_data['awaiting_wallet'] = False
        else:
            await update.message.reply_text("❌ Invalid Address! Must start with 0x and be 42 chars.")
        return

    if user_id == ADMIN_ID and context.user_data.get('admin_action'):
        action = context.user_data['admin_action']
        
        if action == 'add_task':
            try:
                parts = text.split("|")
                title, link = parts[0].strip(), parts[1].strip()
                reward, timer = int(parts[2].strip()), int(parts[3].strip())
                cursor.execute("INSERT INTO tasks (title, link, reward, timer) VALUES (?, ?, ?, ?)", (title, link, reward, timer))
                conn.commit()
                await update.message.reply_text(f"✅ Task Added: {title}")
            except Exception:
                await update.message.reply_text("❌ Format Error! Use: `Name | Link | Reward | Timer`", parse_mode='Markdown')
            context.user_data['admin_action'] = None

        elif action == 'delete_task':
            try:
                task_id = int(text.strip())
                cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
                await update.message.reply_text(f"✅ Task ID `{task_id}` deleted." if cursor.rowcount > 0 else "❌ Task ID not found.")
            except Exception:
                await update.message.reply_text("❌ Send only the Task ID number.")
            context.user_data['admin_action'] = None

        elif action == 'edit_balance':
            try:
                parts = text.split("|")
                target_id, value = int(parts[0].strip()), int(parts[1].strip())
                cursor.execute("UPDATE users SET points = ? WHERE user_id = ?", (value, target_id))
                conn.commit()
                await update.message.reply_text(f"✅ User `{target_id}` balance set to {value}.")
            except Exception:
                await update.message.reply_text("❌ Format Error! Use: `UserID | Amount`", parse_mode='Markdown')
            context.user_data['admin_action'] = None

        elif action == 'broadcast':
            cursor.execute("SELECT user_id FROM users")
            users = cursor.fetchall()
            success = 0
            for u in users:
                try:
                    await context.bot.send_message(chat_id=u[0], text=f"📢 **Announcement:**\n\n{text}", parse_mode='Markdown')
                    success += 1
                except: pass
            await update.message.reply_text(f"✅ Broadcast sent to {success} users.")
            context.user_data['admin_action'] = None

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
    if not TOKEN:
        print("Error: TELEGRAM_TOKEN environment variable is missing!")
        return
        
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    threading.Thread(target=run_flask, daemon=True).start()

    print("Bot and Web Server are running...")
    app.run_polling()

if __name__ == '__main__':
    main()
