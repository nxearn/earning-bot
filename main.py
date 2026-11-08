import os
import time
import requests
from flask import Flask
from pymongo import MongoClient
from bson.objectid import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ================= CONFIGURATION =================
TOKEN = os.environ.get("TELEGRAM_TOKEN") 
MONGODB_URI = os.environ.get("MONGODB_URI") 
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") 
ADMIN_ID = 6179056395 
SUPPORT_USERNAME = "@nxprimemods1" 
MONETAG_LINK = "https://uplcm.com/4/12203228" 

# MongoDB Connection
client = MongoClient(MONGODB_URI)
db = client['nx_panel_store'] 
panels_collection = db['panels'] 
settings_collection = db['settings']
users_collection = db['users']

# ================= AI & HELPER FUNCTIONS =================
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🎁 Free Panels", callback_data="list_free_panels")],
        [InlineKeyboardButton("💎 Paid Panels", callback_data="list_paid_panels")],
        [InlineKeyboardButton("📺 How to Download (Video)", callback_data="watch_tutorial")],
        [InlineKeyboardButton("🤖 AI Support", callback_data="ai_support")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Add Free Panel", callback_data="admin_add_free"), InlineKeyboardButton("➕ Add Paid Panel", callback_data="admin_add_paid")],
        [InlineKeyboardButton("⚙️ Set Payment Info", callback_data="admin_set_payment")],
        [InlineKeyboardButton("📺 Set Tutorial Video", callback_data="admin_set_video")], # নতুন বাটন
        [InlineKeyboardButton("🗑 Delete Panel", callback_data="admin_del_panel")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔙 Close Panel", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def ask_groq_ai(user_text):
    if not GROQ_API_KEY:
        return "AI Support is currently offline. Please contact admin."
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama3-8b-8192", 
        "messages": [
            {
                "role": "system", 
                "content": "You are a helpful support assistant for 'NX Panel Store' Telegram bot. Users can download Free Panels by watching ads, and buy Paid Panels using Bkash or USDT. Answer their questions politely in English or Bangla."
            },
            {"role": "user", "content": user_text}
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        return data['choices'][0]['message']['content']
    except Exception:
        return "Sorry, I am facing some issues right now. Please try again later."

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    
    users_collection.update_one({"user_id": user_id}, {"$set": {"first_name": first_name}}, upsert=True)
    
    welcome_text = (
        "👋 **Welcome to NX Panel Store!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🟢 **Server Status:** Online\n"
        "💎 **Platform:** 100% Genuine & Trusted\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 **Download premium and free panels easily.**\n\n"
        "👇 **Choose an option below:**"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu(), parse_mode='Markdown')

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

    if data == "back_to_main":
        await query.message.reply_text("👇 **Choose an option below:**", reply_markup=get_main_menu(), parse_mode='Markdown')
        
    # ---------------- ADMIN BUTTONS ----------------
    elif data == "admin_add_free":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("📥 Send Free Panel Details:\n`Panel Name | Link | Image URL`\n*(Image optional)*", parse_mode='Markdown')
        context.user_data['admin_action'] = 'add_free'

    elif data == "admin_add_paid":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("📥 Send Paid Panel Details:\n`Panel Name | Link | Image URL`\n*(Image optional)*", parse_mode='Markdown')
        context.user_data['admin_action'] = 'add_paid'

    elif data == "admin_set_payment":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("💳 Send Payment Details:\n`Bkash Number | USDT BEP20 Address`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'set_payment'

    # নতুন: টিউটোরিয়াল ভিডিও সেট করা
    elif data == "admin_set_video":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("📺 Send the Tutorial Video URL:\n*(Example: https://youtube.com/watch?v=...)*", parse_mode='Markdown')
        context.user_data['admin_action'] = 'set_video'

    elif data == "admin_broadcast":
        if user_id != ADMIN_ID: return
        await query.message.reply_text("📢 Send the message you want to broadcast to all users:")
        context.user_data['admin_action'] = 'broadcast'

    elif data == "admin_del_panel":
        if user_id != ADMIN_ID: return
        panels = list(panels_collection.find())
        if not panels:
            await query.message.reply_text("No panels available to delete.")
            return
        panel_list = "🗑 **All Panels:**\n\n"
        for p in panels:
            p_type = "Paid" if p.get('is_paid') else "Free"
            panel_list += f"ID: `{p['_id']}` | {p['name']} ({p_type})\n"
        panel_list += "\nSend the **Panel ID** to delete."
        await query.message.reply_text(panel_list, parse_mode='Markdown')
        context.user_data['admin_action'] = 'delete_panel'

    # ---------------- USER: TUTORIAL VIDEO ----------------
    elif data == "watch_tutorial":
        video_info = settings_collection.find_one({"_id": "video_info"})
        if video_info and video_info.get('link'):
            video_link = video_info['link']
            keyboard = [[InlineKeyboardButton("▶️ Watch Video Now", url=video_link)]]
            await query.message.reply_text("📺 **How to Download Panel**\n\nClick the button below to watch the tutorial video.", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text("⚠️ Tutorial video is not set by admin yet.", reply_markup=get_back_button())

    # ---------------- USER: AI SUPPORT ----------------
    elif data == "ai_support":
        await query.message.reply_text("🤖 **AI Support**\n\nAsk me anything about this bot (e.g., How to download panels, payment methods, etc.)")
        context.user_data['in_ai_chat'] = True

    # ---------------- USER: FREE PANELS ----------------
    elif data == "list_free_panels":
        panels = list(panels_collection.find({"is_paid": False}))
        if not panels:
            await query.message.reply_text("No Free Panels available.", reply_markup=get_back_button())
            return
        keyboard = []
        for p in panels:
            # নাম ছোট করে দেখানো হচ্ছে (বাটনে বেশি লেখা গেলে কেটে যায়)
            short_name = p['name'][:20] + "..." if len(p['name']) > 20 else p['name']
            keyboard.append([InlineKeyboardButton(f"🎁 {short_name}", callback_data=f"get_free_{p['_id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        await query.message.reply_text("🎁 **Free Panels**\n\nSelect a panel:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith("get_free_"):
        panel_id = data.split("_")[2]
        panel = panels_collection.find_one({"_id": ObjectId(panel_id)})
        if not panel: return
        
        # এখানে প্যানেলের পুরো নাম এবং ডিটেইলস দেখানো হচ্ছে
        text = (
            f"🎁 **Panel Name:** {panel['name']}\n\n"
            f"🎬 To download this panel, you need to watch a short ad."
        )
        keyboard = [
            [InlineKeyboardButton("🎬 Watch Ad", url=MONETAG_LINK)],
            [InlineKeyboardButton("✅ CLICK HERE", callback_data=f"claim_free_{panel_id}")]
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith("claim_free_"):
        panel_id = data.split("_")[2]
        panel = panels_collection.find_one({"_id": ObjectId(panel_id)})
        if not panel: return
        
        text = f"✅ **Ad verified!**\n\nClick the button below to download {panel['name']}:"
        keyboard = [[InlineKeyboardButton(f"📥 Download {panel['name']}", url=panel['link'])]]
        
        if panel.get('image'):
            await query.message.reply_photo(photo=panel['image'], caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # ---------------- USER: PAID PANELS ----------------
    elif data == "list_paid_panels":
        panels = list(panels_collection.find({"is_paid": True}))
        if not panels:
            await query.message.reply_text("No Paid Panels available.", reply_markup=get_back_button())
            return
        keyboard = []
        for p in panels:
            short_name = p['name'][:20] + "..." if len(p['name']) > 20 else p['name']
            keyboard.append([InlineKeyboardButton(f"💎 {short_name}", callback_data=f"buy_paid_{p['_id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        await query.message.reply_text("💎 **Paid Panels**\n\nSelect a panel to buy:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith("buy_paid_"):
        panel_id = data.split("_")[2]
        panel = panels_collection.find_one({"_id": ObjectId(panel_id)})
        if not panel: return
        
        payment_info = settings_collection.find_one({"_id": "payment_info"})
        bkash_num = payment_info.get('bkash', 'Not Set') if payment_info else 'Not Set'
        usdt_addr = payment_info.get('usdt', 'Not Set') if payment_info else 'Not Set'

        text = (
            f"💎 **Panel Name:** {panel['name']}\n\n"
            f"💳 **Payment Options:**\n"
            f"📱 Bkash (Bangladesh): `{bkash_num}`\n"
            f"🪙 USDT (BEP20): `{usdt_addr}`\n\n"
            f"After payment, send the screenshot here to get the panel link."
        )
        await query.message.reply_text(text, parse_mode='Markdown')
        context.user_data['buying_panel_id'] = panel_id

    # ---------------- ADMIN: APPROVE / REJECT PAYMENT ----------------
    elif data.startswith("approve_order_"):
        if user_id != ADMIN_ID: return
        parts = data.split("_")
        target_user_id = int(parts[2])
        panel_id = parts[3]
        
        panel = panels_collection.find_one({"_id": ObjectId(panel_id)})
        if not panel: return
            
        text = f"✅ **Payment Verified!**\n\nYour panel '{panel['name']}' is ready to download:"
        keyboard = [[InlineKeyboardButton(f"📥 Download {panel['name']}", url=panel['link'])]]
        
        await context.bot.send_message(chat_id=target_user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        await query.edit_message_text(f"✅ Order for User `{target_user_id}` has been Approved and link sent!")

    elif data.startswith("reject_order_"):
        if user_id != ADMIN_ID: return
        parts = data.split("_")
        target_user_id = int(parts[2])
        
        await query.edit_message_text(f"❌ Order for User `{target_user_id}` has been Rejected.")
        await context.bot.send_message(chat_id=target_user_id, text="❌ **Payment Rejected!**\nYour payment screenshot was invalid or not received. Please contact support.")

# ================= MESSAGE HANDLER =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # AI চ্যাটের জন্য
    if context.user_data.get('in_ai_chat'):
        if text.lower() in ['exit', 'back', 'stop']:
            context.user_data['in_ai_chat'] = False
            await update.message.reply_text("Exited AI Support. Back to Main Menu.", reply_markup=get_main_menu())
            return
            
        await update.message.reply_chat_action(action="typing")
        ai_reply = ask_groq_ai(text)
        await update.message.reply_text(f"🤖 **AI Support:**\n\n{ai_reply}", reply_markup=get_back_button(), parse_mode='Markdown')
        return

    # ইউজার যদি প্যানেল কিনতে চায় এবং স্ক্রিনশট পাঠায়
    if context.user_data.get('buying_panel_id'):
        if update.message.photo:
            panel_id = context.user_data['buying_panel_id']
            panel = panels_collection.find_one({"_id": ObjectId(panel_id)})
            
            admin_keyboard = [
                [InlineKeyboardButton("✅ Approve", callback_data=f"approve_order_{user_id}_{panel_id}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"reject_order_{user_id}")]
            ]
            
            await context.bot.send_photo(
                chat_id=ADMIN_ID, 
                photo=update.message.photo[-1].file_id,
                caption=f"🚨 **New Payment Screenshot**\nUser: {update.effective_user.first_name} (`{user_id}`)\nPanel: {panel['name']}",
                reply_markup=InlineKeyboardMarkup(admin_keyboard)
            )
            
            await update.message.reply_text("⏳ **Pending!**\nYour payment screenshot has been sent to Admin. Please wait for approval.")
            context.user_data['buying_panel_id'] = None
            
        else:
            await update.message.reply_text("❌ Please send a **Screenshot** of your payment.")
        return

    # অ্যাডমিনের অ্যাকশন হ্যান্ডলিং
    if user_id == ADMIN_ID and context.user_data.get('admin_action'):
        action = context.user_data['admin_action']
        
        if action in ['add_free', 'add_paid']:
            try:
                parts = text.split("|")
                name = parts[0].strip()
                link = parts[1].strip()
                image = parts[2].strip() if len(parts) > 2 and parts[2].strip() != "" else ""
                
                is_paid = True if action == 'add_paid' else False
                panels_collection.insert_one({"name": name, "link": link, "image": image, "is_paid": is_paid})
                await update.message.reply_text(f"✅ **Panel Added!**", parse_mode='Markdown')
            except Exception:
                await update.message.reply_text("❌ Format Error! Use: `Name | Link | Image URL`", parse_mode='Markdown')
            context.user_data['admin_action'] = None

        elif action == 'set_payment':
            try:
                parts = text.split("|")
                bkash = parts[0].strip()
                usdt = parts[1].strip()
                settings_collection.update_one({"_id": "payment_info"}, {"$set": {"bkash": bkash, "usdt": usdt}}, upsert=True)
                await update.message.reply_text(f"✅ **Payment Info Updated!**", parse_mode='Markdown')
            except Exception:
                await update.message.reply_text("❌ Format Error! Use: `Bkash Number | USDT Address`", parse_mode='Markdown')
            context.user_data['admin_action'] = None

        # নতুন: ভিডিও লিংক সেভ করা
        elif action == 'set_video':
            if text.startswith("http"):
                settings_collection.update_one({"_id": "video_info"}, {"$set": {"link": text.strip()}}, upsert=True)
                await update.message.reply_text(f"✅ **Tutorial Video Updated!**", parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Invalid URL! Please send a valid video link.")
            context.user_data['admin_action'] = None

        elif action == 'delete_panel':
            try:
                panel_id = text.strip()
                result = panels_collection.delete_one({"_id": ObjectId(panel_id)})
                await update.message.reply_text(f"✅ Panel deleted!" if result.deleted_count > 0 else "❌ Panel ID not found.")
            except Exception:
                await update.message.reply_text("❌ Invalid ID!")
            context.user_data['admin_action'] = None

        elif action == 'broadcast':
            users = list(users_collection.find({}, {"user_id": 1}))
            success = 0
            await update.message.reply_text("⏳ Broadcasting message to all users...")
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
    return "Panel Store Bot is running perfectly!"

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
    app.add_handler(MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), handle_message))

    import threading
    threading.Thread(target=run_flask, daemon=True).start()

    print("Panel Store Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
