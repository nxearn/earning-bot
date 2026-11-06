import time
import os
import threading
import random
from datetime import datetime, timedelta
from flask import Flask
from pymongo import MongoClient
from bson.objectid import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ================= CONFIGURATION =================
TOKEN = os.environ.get("TELEGRAM_TOKEN") 
MONGODB_URI = os.environ.get("MONGODB_URI") 
ADMIN_ID = 6179056395 
SUPPORT_USERNAME = "@nxprimemods1" 
MONETAG_LINK = "https://uplcm.com/4/12203228" 

# MongoDB Connection
client = MongoClient(MONGODB_URI)
db = client['nx_earning_bot'] 
users_collection = db['users']
tasks_collection = db['tasks']
user_tasks_collection = db['user_tasks']
withdraw_collection = db['withdrawals']
gift_codes_collection = db['gift_codes']

# ================= HELPER FUNCTIONS =================
def get_user(user_id):
    return users_collection.find_one({"user_id": user_id})

def add_points(user_id, amount):
    users_collection.update_one({"user_id": user_id}, {"$inc": {"points": amount}}, upsert=True)

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📋 Tasks", callback_data="show_tasks"), InlineKeyboardButton("🎰 Lucky Spin", callback_data="spin")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"), InlineKeyboardButton("🎁 Daily Check-in", callback_data="checkin")],
        [InlineKeyboardButton("🔗 Refer & Earn", callback_data="refer"), InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("🎟️ Redeem Code", callback_data="redeem_code")],
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
        "✅ Minimum Withdrawal: 5000 Pts = 5 USDT\n\n"
        "👇 **Choose an option below to start:**\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "📢 **Notice:** Please complete tasks honestly. Fake accounts will be banned!"
    )
    return text

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Add Task", callback_data="admin_add_task"), InlineKeyboardButton("🗑 Delete Task", callback_data="admin_del_task")],
        [InlineKeyboardButton("🎁 Create Gift Code", callback_data="admin_create_code")],
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
    
    users_collection.update_one({"user_id": user_id}, {"$setOnInsert": {"points": 0, "wallet": None, "referred_by": None, "last_checkin": None, "last_spin": None, "total_referrals": 0, "first_name": first_name}}, upsert=True)
    
    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id:
                user_data = get_user(user_id)
                if user_data and user_data.get("referred_by") is None:
                    users_collection.update_one({"user_id": user_id}, {"$set": {"referred_by": referrer_id}})
                    users_collection.update_one({"user_id": referrer_id}, {"$inc": {"total_referrals": 1}})
                    add_points(referrer_id, 100) 
        except ValueError:
            pass

    await update.message.reply_text(get_main_menu_text(first_name), reply_markup=get_main_menu(), parse_mode='Markdown')

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
        users_collection.insert_one({"user_id": user_id, "points": 0, "first_name": query.from_user.first_name})
        user_data = get_user(user_id)

    if data == "back_to_main":
        await query.message.reply_text(get_main_menu_text(query.from_user.first_name), reply_markup=get_main_menu(), parse_mode='Markdown')
        
    # ---------------- ADMIN BUTTONS ----------------
    elif data == "admin_add_task":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("📝 Send task in format:\n`Task Name | Link | Reward | Wait Time`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'add_task'

    elif data == "admin_del_task":
        if user_id != ADMIN_ID: return
        tasks = list(tasks_collection.find())
        if not tasks:
            await query.message.reply_text("No tasks available to delete.")
            return
        task_list = "🗑 **Active Tasks:**\n\n"
        for t in tasks:
            task_list += f"ID: `{t['_id']}` | {t['title']}\n"
        task_list += "\nSend the **Task ID** to delete."
        await query.message.reply_text(task_list, parse_mode='Markdown')
        context.user_data['admin_action'] = 'delete_task'

    elif data == "admin_create_code":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("🎁 Send Gift Code in this format:\n`CodeName | Points`\n\nExample: `NXGIFT100 | 500`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'create_code'

    elif data == "admin_users":
        if user_id != ADMIN_ID: return
        users = list(users_collection.find().sort("points", -1).limit(20))
        text = f"👥 **Top 20 Users**\n\n"
        for u in users:
            name = u.get("first_name", "Anonymous")
            text += f"👤 {name} | `{u['user_id']}`\n💰 Bal: {u.get('points', 0)} | 🤝 Ref: {u.get('total_referrals', 0)}\n\n"
        await query.message.reply_text(text, reply_markup=get_admin_menu(), parse_mode='Markdown')

    elif data == "admin_edit_balance":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("Format: `UserID | Amount`\nExample: `12345678 | 500`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'edit_balance'
        
    elif data == "admin_broadcast":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("📢 Send the message to broadcast:")
        context.user_data['admin_action'] = 'broadcast'

    # ---------------- USER BUTTONS (WITH ADS & TIMER) ----------------
    
    elif data == "redeem_code":
        await query.message.reply_text("🎟️ **Please send your Gift Code:**")
        context.user_data['awaiting_gift_code'] = True

    elif data == "balance":
        points = user_data.get("points", 0)
        wallet = user_data.get("wallet")
        progress = min(int((points / 5000) * 10), 10)
        bar = "█" * progress + "░" * (10 - progress)
        
        text = (
            f"💰 **Your Balance:** {points} Points\n"
            f"📈 **Withdraw Progress:**\n`[{bar}]` {points}/5000\n\n"
        )
        if wallet:
            text += f"🔗 **Wallet:**\n`{wallet}`\n\n➖➖➖➖➖➖➖➖➖➖\n📢 **Note:** Minimum 5000 Points required."
            keyboard = [[InlineKeyboardButton("🔄 Change Wallet", callback_data="connect_wallet")], [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
        else:
            text += "⚠️ **Wallet Not Connected**\n\n➖➖➖➖➖➖➖➖➖➖\n📢 **Note:** Connect your wallet to receive payments."
            keyboard = [[InlineKeyboardButton("➕ Connect Wallet", callback_data="connect_wallet")], [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "connect_wallet":
        await query.message.reply_text("Send your USDT BEP20 address (Must start with 0x and be 42 characters):")
        context.user_data['awaiting_wallet'] = True

    # ১. চেক-ইনে অ্যাড + টাইমার
    elif data == "checkin":
        last_checkin = user_data.get("last_checkin")
        now = datetime.now()
        if last_checkin:
            last_time = datetime.strptime(last_checkin, '%Y-%m-%d %H:%M:%S')
            if now - last_time < timedelta(hours=24):
                await query.answer("❌ Already checked in! Come back later.", show_alert=True)
                return
        
        context.user_data['ad_start_checkin'] = time.time()
        ad_keyboard = [[InlineKeyboardButton("🎬 Watch Ad to Claim 50 Points", url=MONETAG_LINK)], [InlineKeyboardButton("✅ Claim Now", callback_data="claim_checkin")]]
        await query.message.reply_text("🎁 **Daily Check-in**\n\nWatch a short ad, then return and click 'Claim Now'.", reply_markup=InlineKeyboardMarkup(ad_keyboard), parse_mode='Markdown')

    elif data == "claim_checkin":
        start_time = context.user_data.get('ad_start_checkin')
        if not start_time or time.time() - start_time < 15:
            await query.answer("❌ Too fast! Watch the ad for at least 15 seconds.", show_alert=True)
            return
        
        now = datetime.now()
        add_points(user_id, 50)
        users_collection.update_one({"user_id": user_id}, {"$set": {"last_checkin": now.strftime('%Y-%m-%d %H:%M:%S')}})
        del context.user_data['ad_start_checkin']
        await query.answer("✅ Check-in successful! You earned 50 Points.", show_alert=True)
        await query.message.reply_text("✅ Check-in successful! You earned 50 Points.", reply_markup=get_back_button())

    # ২. স্পিনে অ্যাড + টাইমার
    elif data == "spin":
        last_spin = user_data.get("last_spin")
        now = datetime.now()
        if last_spin:
            last_time = datetime.strptime(last_spin, '%Y-%m-%d %H:%M:%S')
            if now - last_time < timedelta(hours=24):
                await query.answer("❌ You already spun today! Come back tomorrow.", show_alert=True)
                return
        
        context.user_data['ad_start_spin'] = time.time()
        ad_keyboard = [[InlineKeyboardButton("🎬 Watch Ad to Spin", url=MONETAG_LINK)], [InlineKeyboardButton("✅ Spin Now", callback_data="claim_spin")]]
        await query.message.reply_text("🎰 **Lucky Spin**\n\nWatch a short ad, then return and click 'Spin Now'.", reply_markup=InlineKeyboardMarkup(ad_keyboard), parse_mode='Markdown')

    elif data == "claim_spin":
        start_time = context.user_data.get('ad_start_spin')
        if not start_time or time.time() - start_time < 15:
            await query.answer("❌ Too fast! Watch the ad for at least 15 seconds.", show_alert=True)
            return

        won_points = random.choices([1000, 500, 100, 50, 20], weights=[1, 2, 7, 20, 70], k=1)[0]
        now = datetime.now()
        add_points(user_id, won_points)
        users_collection.update_one({"user_id": user_id}, {"$set": {"last_spin": now.strftime('%Y-%m-%d %H:%M:%S')}})
        del context.user_data['ad_start_spin']
        await query.answer(f"🎉 You won {won_points} Points!", show_alert=True)
        await query.message.reply_text(f"🎰 **Spin Result:** You won **{won_points} Points**!", reply_markup=get_back_button())

    elif data == "task_history":
        history = list(user_tasks_collection.find({"user_id": user_id}).sort("date", -1).limit(5))
        if not history:
            await query.message.reply_text("You haven't completed any tasks yet.", reply_markup=get_back_button())
            return
        text = "📜 **Your Last 5 Tasks:**\n\n"
        for h in history:
            text += f"✅ {h.get('task_name', 'Task')} | +{h.get('reward', 0)} Pts | {h.get('date')}\n"
        await query.message.reply_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "wd_history":
        history = list(withdraw_collection.find({"user_id": user_id}).sort("date", -1).limit(5))
        if not history:
            await query.message.reply_text("You have no withdrawal history.", reply_markup=get_back_button())
            return
        text = "📊 **Your Last 5 Withdrawals:**\n\n"
        for h in history:
            status_icon = "✅" if h.get('status') == "Approved" else "❌" if h.get('status') == "Rejected" else "⏳"
            text += f"{status_icon} {h.get('amount')} Pts | {h.get('status')} | {h.get('date')}\n"
        await query.message.reply_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "refer":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        text = f"🔗 **Invite friends and earn 100 points per person!**\n\nYour Referral Link:\n`{ref_link}`"
        await query.message.reply_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif data == "leaderboard":
        users = list(users_collection.find().sort("points", -1).limit(10))
        text = "🏆 **Top 10 Earners** 🏆\n\n"
        for i, u in enumerate(users, start=1):
            text += f"{i}. {u.get('first_name', 'Anonymous')} - {u.get('points', 0)} Points\n"
        await query.message.reply_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    # ৩. টাস্ক ভেরিফাইতে অ্যাড + টাইমার
    elif data == "show_tasks":
        completed_tasks = [t['task_id'] for t in user_tasks_collection.find({"user_id": user_id})]
        tasks = list(tasks_collection.find())
        available_tasks = [t for t in tasks if str(t['_id']) not in completed_tasks]
        
        if not available_tasks:
            await query.message.reply_text("🎉 You have completed all available tasks!", reply_markup=get_back_button())
            return
            
        keyboard = []
        for task in available_tasks:
            keyboard.append([InlineKeyboardButton(f"{task['title']} (+{task['reward']} pts)", callback_data=f"do_task_{task['_id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        await query.message.reply_text("📋 **Available Tasks:**\n\nSelect a task to complete.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith("do_task_"):
        task_id = data.split("_")[2]
        task = tasks_collection.find_one({"_id": ObjectId(task_id)})
        context.user_data[f'task_start_{task_id}'] = time.time()
        keyboard = [
            [InlineKeyboardButton("🔗 Open Link", url=task['link'])],
            [InlineKeyboardButton("✅ Verify", callback_data=f"verify_{task_id}_{task['reward']}_{task['timer']}")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
        ]
        await query.message.reply_text(f"1. Open Link\n2. Wait {task['timer']} seconds\n3. Click Verify", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("verify_"):
        parts = data.split("_")
        task_id, reward, req_time = parts[1], int(parts[2]), int(parts[3])
        
        if user_tasks_collection.find_one({"user_id": user_id, "task_id": task_id}):
            await query.answer("❌ Already completed!", show_alert=True)
            return
        
        start_time = context.user_data.get(f'task_start_{task_id}')
        if not start_time:
            await query.answer("❌ Click 'Open Link' first!", show_alert=True)
            return
            
        if time.time() - start_time < req_time:
            await query.answer("❌ Too fast! Wait a bit.", show_alert=True)
        else:
            context.user_data[f'ad_start_task_{task_id}'] = time.time()
            ad_keyboard = [[InlineKeyboardButton("🎬 Watch Ad to Claim", url=MONETAG_LINK)], [InlineKeyboardButton("✅ Claim Reward", callback_data=f"claim_task_{task_id}_{reward}")]]
            await query.message.reply_text(f"✅ Task time completed!\n\nWatch a short ad, then return and click 'Claim Reward'.", reply_markup=InlineKeyboardMarkup(ad_keyboard))

    elif data.startswith("claim_task_"):
        parts = data.split("_")
        task_id, reward = parts[2], int(parts[3])
        
        if user_tasks_collection.find_one({"user_id": user_id, "task_id": task_id}):
            await query.answer("❌ Already completed!", show_alert=True)
            return

        start_time = context.user_data.get(f'ad_start_task_{task_id}')
        if not start_time or time.time() - start_time < 15:
            await query.answer("❌ Too fast! Watch the ad for at least 15 seconds.", show_alert=True)
            return

        add_points(user_id, reward)
        task = tasks_collection.find_one({"_id": ObjectId(task_id)})
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        user_tasks_collection.insert_one({"user_id": user_id, "task_id": task_id, "task_name": task['title'], "reward": reward, "date": now_str})
        users_collection.update_one({"user_id": user_id}, {"$inc": {"completed_tasks": 1}})
        
        del context.user_data[f'ad_start_task_{task_id}']
        await query.answer(f"✅ Done! You earned {reward} Points.", show_alert=True)
        await query.message.reply_text(f"✅ Task completed! You earned {reward} Points.", reply_markup=get_back_button())

    elif data == "withdraw":
        points = user_data.get("points", 0)
        wallet = user_data.get("wallet")
        
        if not wallet:
            await query.message.reply_text("⚠️ Connect wallet first from Balance menu.", reply_markup=get_back_button())
            return
        if points < 5000:
            await query.message.reply_text(f"❌ Minimum 5000 Points needed. Your Balance: {points}", reply_markup=get_back_button())
            return
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        withdraw_collection.insert_one({"user_id": user_id, "amount": 5000, "wallet": wallet, "status": "Pending", "date": now_str})
        
        await query.message.reply_text("✅ Withdrawal request sent! Please wait for approval.", reply_markup=get_back_button(), parse_mode='Markdown')
        
        admin_keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"wd_approve_{user_id}"), InlineKeyboardButton("❌ Reject", callback_data=f"wd_reject_{user_id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 **Withdraw Request**\nUser: `{user_id}`\nWallet: `{wallet}`\nPoints: 5000", reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode='Markdown')

    elif data.startswith("wd_approve_"):
        if user_id != ADMIN_ID: return
        target_user_id = int(data.split("_")[2])
        users_collection.update_one({"user_id": target_user_id}, {"$inc": {"points": -5000}})
        withdraw_collection.update_many({"user_id": target_user_id, "status": "Pending"}, {"$set": {"status": "Approved"}})
        await query.edit_message_text(f"✅ Approved for `{target_user_id}`.")
        await context.bot.send_message(chat_id=target_user_id, text="✅ Your withdrawal has been approved!")

    elif data.startswith("wd_reject_"):
        if user_id != ADMIN_ID: return
        target_user_id = int(data.split("_")[2])
        withdraw_collection.update_many({"user_id": target_user_id, "status": "Pending"}, {"$set": {"status": "Rejected"}})
        await query.edit_message_text(f"❌ Rejected for `{target_user_id}`.")
        await context.bot.send_message(chat_id=target_user_id, text="❌ Your withdrawal request was rejected.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if context.user_data.get('awaiting_gift_code'):
        code_data = gift_codes_collection.find_one({"code": text.upper()})
        if code_data:
            reward = code_data['points']
            add_points(user_id, reward)
            gift_codes_collection.delete_one({"code": text.upper()})
            await update.message.reply_text(f"🎉 **Congratulations!**\nYou redeemed the code and earned **{reward} Points**!", reply_markup=get_back_button(), parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ **Invalid or Expired Code!**", reply_markup=get_back_button(), parse_mode='Markdown')
        context.user_data['awaiting_gift_code'] = False
        return

    if context.user_data.get('awaiting_wallet'):
        if text.startswith("0x") and len(text) == 42:
            users_collection.update_one({"user_id": user_id}, {"$set": {"wallet": text}})
            await update.message.reply_text(f"✅ Wallet Connected:\n`{text}`", reply_markup=get_back_button(), parse_mode='Markdown')
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
                tasks_collection.insert_one({"title": title, "link": link, "reward": reward, "timer": timer})
                await update.message.reply_text(f"✅ Task Added: {title}")
            except Exception:
                await update.message.reply_text("❌ Format Error! Use: `Name | Link | Reward | Timer`", parse_mode='Markdown')
            context.user_data['admin_action'] = None

        elif action == 'delete_task':
            try:
                task_id = text.strip()
                result = tasks_collection.delete_one({"_id": ObjectId(task_id)})
                await update.message.reply_text(f"✅ Task deleted!" if result.deleted_count > 0 else "❌ Task ID not found.")
            except Exception:
                await update.message.reply_text("❌ Invalid ID!")
            context.user_data['admin_action'] = None

        elif action == 'create_code':
            try:
                parts = text.split("|")
                code_name, points = parts[0].strip().upper(), int(parts[1].strip())
                gift_codes_collection.insert_one({"code": code_name, "points": points})
                await update.message.reply_text(f"✅ **Gift Code Created!**\n\nCode: `{code_name}`\nReward: {points} Points", parse_mode='Markdown')
            except Exception:
                await update.message.reply_text("❌ Format Error! Use: `Code | Points`", parse_mode='Markdown')
            context.user_data['admin_action'] = None

        elif action == 'edit_balance':
            try:
                parts = text.split("|")
                target_id, value = int(parts[0].strip()), int(parts[1].strip())
                users_collection.update_one({"user_id": target_id}, {"$set": {"points": value}})
                await update.message.reply_text(f"✅ User `{target_id}` balance set to {value}.")
            except Exception:
                await update.message.reply_text("❌ Format Error! Use: `UserID | Amount`", parse_mode='Markdown')
            context.user_data['admin_action'] = None

        elif action == 'broadcast':
            users = list(users_collection.find({}, {"user_id": 1}))
            success = 0
            for u in users:
                try:
                    await context.bot.send_message(chat_id=u['user_id'], text=f"📢 **Announcement:**\n\n{text}", parse_mode='Markdown')
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
    if not TOKEN or not MONGODB_URI:
        print("Error: TELEGRAM_TOKEN or MONGODB_URI environment variable is missing!")
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
