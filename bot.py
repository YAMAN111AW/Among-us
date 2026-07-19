import os
import asyncio
import random
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import psycopg2
import psycopg2.extras
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, TimedOut, NetworkError
import logging
import traceback
import re

# ====== إعدادات التسجيل ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== إعدادات البوت ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ====== التحقق من الإعدادات ======
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN غير موجود في متغيرات البيئة!")
    exit(1)
if not DATABASE_URL:
    logger.error("❌ DATABASE_URL غير موجود في متغيرات البيئة!")
    exit(1)

# ====== أدوات مساعدة ======
CREWMATE_TOOLS = [
    {"name": "جهاز تتبع", "emoji": "📡", "description": "يكشف موقع لاعب واحد بشكل تقريبي", "effect": "track"},
    {"name": "كاميرا مراقبة", "emoji": "📸", "description": "تلتقط صورة للاعب وتكشف إذا كان مشبوهاً", "effect": "camera"},
    {"name": "جهاز كشف الكذب", "emoji": "🕵️", "description": "يسأل اللاعب سؤال ويكشف إذا كان صادقاً", "effect": "lie_detector"},
    {"name": "درع واقي", "emoji": "🛡️", "description": "يحميك من القتل لمرة واحدة", "effect": "shield"},
    {"name": "مسرع المهام", "emoji": "⚡", "description": "ينهي مهمتين دفعة واحدة", "effect": "speed_boost"}
]

IMPOSTOR_TOOLS = [
    {"name": "قنبلة دخان", "emoji": "💨", "description": "تمنع الكاميرات من التصوير لدقيقة", "effect": "smoke_bomb"},
    {"name": "تنكر", "emoji": "🎭", "description": "تتظاهر أنك طاقم وتكمل مهمة حقيقية", "effect": "disguise"},
    {"name": "تخريب الأبواب", "emoji": "🚪", "description": "يقفل الأبواب ويمنع الطاقم من الحركة", "effect": "lock_doors"},
    {"name": "تشويش الاتصالات", "emoji": "📵", "description": "يمنع اجتماع الطوارئ لدقيقة", "effect": "jam_comms"}
]

LOCATIONS = ["الكافتيريا 🍽️", "المفاعل ☢️", "غرفة المحرك ⚙️", "الممر الرئيسي 🚶", "غرفة الاتصالات 📡", "المخزن 📦", "غرفة الأكسجين 🫁", "المختبر 🔬", "قاعة الاجتماعات 🏛️"]

# نظام المهام المطور
CREWMATE_TASKS = [
    {
        "id": "wires",
        "name": "إصلاح الأسلاك",
        "emoji": "🔌",
        "description": "🔌 اختر السلك الصحيح لتوصيل الدائرة الكهربائية:",
        "buttons": [["🔵 أزرق", "🔴 أحمر"], ["🟡 أصفر", "🟢 أخضر"]],
        "correct": "🔵 أزرق",
        "success": "✅ تم الإصلاح! عاد التيار!"
    },
    {
        "id": "card",
        "name": "مسح بطاقة الدخول",
        "emoji": "💳",
        "description": "💳 مرر البطاقة بالسرعة المناسبة:",
        "buttons": [["🐢 بطيء", "🐇 سريع"], ["🚶 متوسط", "🛑 إلغاء"]],
        "correct": "🚶 متوسط",
        "success": "✅ تم قبول البطاقة!"
    },
    {
        "id": "garbage",
        "name": "تفريغ القمامة",
        "emoji": "🗑️",
        "description": "🗑️ اسحب الرافعة لتفريغ القمامة:",
        "buttons": [["⚙️ سحب", "🔒 قفل"]],
        "correct": "⚙️ سحب",
        "success": "✅ تم التفريغ بنجاح!"
    },
    {
        "id": "download",
        "name": "تحميل البيانات",
        "emoji": "📤",
        "description": "📡 اختر السيرفر الآمن لتحميل البيانات:",
        "buttons": [["🌍 عالمي", "🔒 محلي"]],
        "correct": "🔒 محلي",
        "success": "✅ اكتمل التحميل!"
    },
    {
        "id": "fuel",
        "name": "تزويد الوقود",
        "emoji": "⛽",
        "description": "⛽ اختر خزان الوقود الصحيح:",
        "buttons": [["🟢 خزان A", "🔴 خزان B"]],
        "correct": "🟢 خزان A",
        "success": "✅ تم تزويد الوقود!"
    }
]

IMPOSTOR_TASKS = [
    {"id": "sab_reactor", "name": "تخريب المفاعل", "emoji": "☢️", "description": "🔴 افتعل أزمة في المفاعل!", "buttons": [["🔥 تفعيل", "❌ إلغاء"]]},
    {"id": "sab_oxygen", "name": "قطع الأكسجين", "emoji": "🫁", "description": "🚨 اقطع إمدادات الأكسجين!", "buttons": [["💨 إغلاق", "❌ إلغاء"]]},
    {"id": "sab_lights", "name": "تخريب الإضاءة", "emoji": "💡", "description": "🌑 أطفئ الأنوار لإرباك الطاقم!", "buttons": [["🌑 إطفاء", "❌ إلغاء"]]}
]

KILL_SCENARIOS = [
    {
        "weapon": "خنجر",
        "emoji": "🗡️",
        "scene": [
            "🕵️ *ظل يتحرك في الظلام...*",
            "👤 *الضحية منشغلة بالمهام...*",
            "💨 *حركة سريعة من الخلف...*",
            "🩸 *طعنة صامتة!*",
            "🤫 *القاتل يختفي...*"
        ],
        "death_message": "🔴💀🔴\n*تم اكتشاف جثة!*\n\n💀 {victim} قُتل بـ{weapon}!\n📍 {location}\n\n🚨 *اجتماع طارئ!*"
    },
    {
        "weapon": "مسدس",
        "emoji": "🔫",
        "scene": [
            "🎯 *تصويب من الظلام...*",
            "😤 *الضحية في المكان الخطأ...*",
            "💥 *طلقة مدوية!*",
            "🏃 *القاتل يهرب...*"
        ],
        "death_message": "🔴💀🔴\n*جريمة قتل!*\n\n💀 {victim} انقتل بـ{weapon}!\n📍 {location}\n\n🚨 *كل المشتبه بهم إلى الاجتماع!*"
    },
    {
        "weapon": "سلك خنق",
        "emoji": "🪢",
        "scene": [
            "🌑 *الظلام دامس...*",
            "👂 *صوت خطوات خافتة...*",
            "😱 *صرخة مكتومة!*",
            "💀 *جثة على الأرض...*"
        ],
        "death_message": "🔴💀🔴\n*جريمة صامتة!*\n\n💀 {victim} خُنق بـ{weapon}!\n📍 {location}\n\n🚨 *اجتماع فوري!*"
    }
]

RANDOM_EVENTS = [
    {"name": "انقطاع الكهرباء", "emoji": "⚡", "message": "⚡ *انقطعت الكهرباء!*\n\n🌑 الظلام يخيم على السفينة...\n👀 القاتل يستغل الظلام!\n💡 الطاقم: أسرعوا لإصلاح الإضاءة!"},
    {"name": "زلزال", "emoji": "🌋", "message": "🌋 *اهتزاز عنيف!*\n\n💥 كل اللاعبين وقعوا أرضاً!\n🏃 القاتل يتحرك في الفوضى!\n⚠️ هذا وقت خطير!"},
    {"name": "إنذار حريق", "emoji": "🔥", "message": "🔥🚨🔥 *حريق في السفينة!*\n\n🚒 الرشاشات تعمل!\n👀 وسط الفوضى... القاتل يستغل الموقف!\n💨 الرؤية ضبابية!"},
    {"name": "تسرب غاز", "emoji": "☠️", "message": "☠️ *تسرب غاز سام!*\n\n😷 الطاقم يضع الأقنعة\n👤 صعوبة في التعرف على اللاعبين!\n🔪 القاتل يستغل التشويش!"},
    {"name": "عطل أنظمة", "emoji": "🔧", "message": "🔧 *عطل في الأنظمة!*\n\n📡 الاتصالات مشوشة\n🚪 الأبواب تفتح وتغلق عشوائياً!\n😈 القاتل سعيد بهذه الفوضى!"}
]

# ====== تخزين مؤقت مع تحسينات ======
active_games = {}
user_tools = {}
player_votes = {}
player_current_task = {}
vote_messages = {}  # {chat_id: message_id}
event_tasks = {}  # {chat_id: asyncio.Task}

# ====== دوال قاعدة البيانات ======
def get_conn():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return conn
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"❌ فشل الاتصال: {e}")
                raise
            logger.warning(f"⚠️ محاولة {attempt + 1} فشلت...")
            asyncio.sleep(1)

def init_db():
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, username VARCHAR(255), first_name VARCHAR(255),
                points INT DEFAULT 0, games_played INT DEFAULT 0, games_won INT DEFAULT 0,
                crewmate_wins INT DEFAULT 0, impostor_wins INT DEFAULT 0,
                total_kills INT DEFAULT 0, total_tasks INT DEFAULT 0,
                referral_code VARCHAR(10) UNIQUE, referred_by BIGINT, created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                group_id BIGINT PRIMARY KEY, title VARCHAR(255),
                active_game BOOLEAN DEFAULT FALSE, total_games INT DEFAULT 0, created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("✅ تم تهيئة قاعدة البيانات")
    except Exception as e:
        logger.error(f"❌ خطأ في init_db: {e}")

def get_user(user_id: int):
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
        user = cursor.fetchone()
        if not user:
            referral_code = str(uuid.uuid4())[:8]
            cursor.execute('INSERT INTO users (user_id, referral_code) VALUES (%s, %s) RETURNING *', (user_id, referral_code))
            conn.commit()
            cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
            user = cursor.fetchone()
        cursor.close()
        return user
    except Exception as e:
        logger.error(f"❌ خطأ في get_user: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_user_points(user_id: int, points: int, won: bool = False, role: str = None, kill: bool = False, task: bool = False):
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        update_parts = ["points = points + %s", "games_played = games_played + 1"]
        params = [points]
        if won:
            update_parts.append('games_won = games_won + 1')
            if role == 'crewmate':
                update_parts.append('crewmate_wins = crewmate_wins + 1')
            elif role == 'impostor':
                update_parts.append('impostor_wins = impostor_wins + 1')
        if kill:
            update_parts.append('total_kills = total_kills + 1')
        if task:
            update_parts.append('total_tasks = total_tasks + 1')
        params.append(user_id)
        cursor.execute(f"UPDATE users SET {', '.join(update_parts)} WHERE user_id = %s", params)
        conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"❌ خطأ في update_user_points: {e}")
    finally:
        if conn:
            conn.close()

def get_leaderboard():
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT user_id, username, first_name, points, games_won FROM users ORDER BY points DESC LIMIT 10')
        leaders = cursor.fetchall()
        cursor.close()
        return leaders
    except Exception as e:
        logger.error(f"❌ خطأ في get_leaderboard: {e}")
        return []
    finally:
        if conn:
            conn.close()

def register_group(group_id: int, title: str):
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO groups (group_id, title) VALUES (%s, %s) ON CONFLICT (group_id) DO UPDATE SET title = %s', (group_id, title, title))
        conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"❌ خطأ في register_group: {e}")
    finally:
        if conn:
            conn.close()

# ====== دوال مساعدة ======
def generate_game_key() -> str:
    return str(uuid.uuid4())[:6]

def get_impostor_count(player_count: int) -> int:
    if player_count <= 5:
        return 1
    elif player_count <= 8:
        return 2
    else:
        return 3

def get_player_name(pdata: dict) -> str:
    name = pdata.get('first_name') or pdata.get('username') or 'لاعب'
    return str(name).replace('_', ' ').replace('*', '').replace('`', '').replace('[', '').replace(']', '')

def sanitize_callback_data(text: str) -> str:
    """تنظيف النص للاستخدام في callback data"""
    # إزالة الرموز الخاصة والايموجي
    return re.sub(r'[^\w\s]', '', text).strip()[:20]

async def safe_send(context, chat_id, text, parse_mode='Markdown', reply_markup=None):
    """إرسال رسالة بشكل آمن"""
    try:
        return await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except BadRequest as e:
        try:
            # محاولة بدون parse_mode
            return await context.bot.send_message(
                chat_id=chat_id,
                text=text.replace('*', '').replace('_', '').replace('`', ''),
                reply_markup=reply_markup
            )
        except Exception as e2:
            logger.error(f"❌ فشل الإرسال: {e2}")
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
    return None

async def cleanup_game(chat_id: int):
    """تنظيف بيانات اللعبة"""
    if chat_id in active_games:
        game = active_games[chat_id]
        for pid in game['players']:
            if pid in user_tools:
                del user_tools[pid]
            if pid in player_current_task:
                del player_current_task[pid]
    
    # إلغاء مهمة الأحداث
    if chat_id in event_tasks:
        event_tasks[chat_id].cancel()
        del event_tasks[chat_id]
    
    # حذف رسالة التصويت القديمة
    if chat_id in vote_messages:
        del vote_messages[chat_id]

# ====== الأوامر الأساسية ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        get_user(user.id)
        welcome_text = (
            f"🎮 *مرحباً {user.first_name}!*\n\n"
            f"🚀 أنا بوت *Among Us* المتطور!\n"
            f"العب مع أصدقائك واكتشف القاتل!\n\n"
            f"📋 *الأوامر الأساسية:*\n"
            f"🎯 /new_game - بدء لعبة جديدة\n"
            f"🤝 /join - انضمام للعبة\n"
            f"⚡ /tasks - تنفيذ مهام\n"
            f"🎒 /tools - أدواتك الخاصة\n"
            f"🚨 /emergency - اجتماع طارئ\n"
            f"📊 /status - حالة اللعبة\n\n"
            f"🏆 /stats - إحصائياتك\n"
            f"👑 /leaderboard - المتصدرين\n"
            f"🔗 /referral - كود الإحالة"
        )
        keyboard = [
            [InlineKeyboardButton("🎮 ابدأ اللعب", callback_data="start_playing"),
             InlineKeyboardButton("📊 إحصائياتي", callback_data="view_stats")],
            [InlineKeyboardButton("🏆 المتصدرين", callback_data="view_leaderboard"),
             InlineKeyboardButton("🔗 كود الإحالة", callback_data="referral_code")]
        ]
        await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ start: {e}")

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        if update.effective_chat.type == 'private':
            await update.message.reply_text("❌ هذا الأمر للمجموعات فقط!")
            return
        
        if chat_id in active_games:
            await update.message.reply_text("⚠️ هناك لعبة جارية بالفعل!")
            return
        
        game_id = generate_game_key()
        active_games[chat_id] = {
            'id': game_id,
            'creator': user.id,
            'players': {},
            'status': 'waiting',
            'impostors': [],
            'alive_crewmates': [],
            'dead_players': [],
            'votes': {},
            'voted_players': set(),  # تتبع من صوت
            'kill_cooldown': {},
            'emergency_used': False,
            'emergency_blocked': False,
            'smoke_active': False,
            'doors_locked': False,
            'lights_off': False,
            'start_votes': {},
            'start_time': datetime.now(),
            'kill_count': 0,  # عدد القتلى
            'meeting_count': 0  # عدد الاجتماعات
        }
        
        keyboard = [[InlineKeyboardButton("🎮 انضم للعبة", callback_data=f"join_{game_id}")]]
        await update.message.reply_text(
            f"🚀 *لعبة جديدة!*\n\n"
            f"🆔 معرف: `{game_id}`\n"
            f"👤 المنشئ: {user.first_name}\n\n"
            f"👥 /join للانضمام (الحد الأدنى: 4)\n"
            f"🗑️ /cancel_game للإلغاء\n\n"
            f"⚠️ عند اكتمال 4 لاعبين، يبدأ التصويت للانطلاق!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        register_group(chat_id, update.effective_chat.title or "مجموعة")
    except Exception as e:
        logger.error(f"❌ new_game: {e}")

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # دعم الانضمام عبر callback و command
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            chat_id = query.message.chat.id
            user = query.from_user
            msg = query.message
        else:
            chat_id = update.effective_chat.id
            user = update.effective_user
            msg = update.effective_message
        
        if chat_id not in active_games:
            await msg.reply_text("❌ لا توجد لعبة نشطة!")
            return
        
        game = active_games[chat_id]
        if game['status'] != 'waiting':
            await msg.reply_text("❌ اللعبة بدأت بالفعل!")
            return
        
        if user.id in game['players']:
            await msg.reply_text("⚠️ أنت منضم بالفعل!")
            return
        
        if len(game['players']) >= 10:
            await msg.reply_text("❌ اللعبة مكتملة (10 لاعبين كحد أقصى)!")
            return
        
        # إضافة اللاعب
        game['players'][user.id] = {
            'username': user.username or user.first_name,
            'first_name': user.first_name,
            'role': None,
            'alive': True,
            'tasks': 0,
            'total_tasks': 3,
            'shield': False
        }
        get_user(user.id)
        
        player_count = len(game['players'])
        
        # رسالة ترحيب حسب عدد اللاعبين
        if player_count == 1:
            await msg.reply_text(f"✅ *{user.first_name}* أول المنضمين! ({player_count}/10)\n👥 نحتاج 3 لاعبين آخرين على الأقل!", parse_mode='Markdown')
        elif player_count < 4:
            await msg.reply_text(f"✅ *{user.first_name}* انضم! ({player_count}/10)\n👥 باقي {4-player_count} لاعبين للبدء!", parse_mode='Markdown')
        else:
            await msg.reply_text(f"✅ *{user.first_name}* انضم! ({player_count}/10)\n🎮 جاري التصويت للبدء...", parse_mode='Markdown')
        
        # بدء التصويت إذا اكتمل العدد
        if player_count >= 4 and game['status'] == 'waiting':
            asyncio.create_task(ask_start_vote(chat_id, context))
    except Exception as e:
        logger.error(f"❌ join_game: {e}")

async def ask_start_vote(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """طلب التصويت لبدء اللعبة"""
    try:
        await asyncio.sleep(2)  # انتظار قصير لتجنب التكرار
        
        if chat_id not in active_games:
            return
        
        game = active_games[chat_id]
        if game['status'] != 'waiting':
            return
        
        game['start_votes'] = {}
        
        player_count = len(game['players'])
        players_list = "\n".join([f"• {get_player_name(p)}" for p in game['players'].values()])
        
        keyboard = [
            [InlineKeyboardButton("✅ ابدأ اللعبة!", callback_data=f"startv_yes_{chat_id}"),
             InlineKeyboardButton("❌ انتظر", callback_data=f"startv_no_{chat_id}")]
        ]
        
        await safe_send(
            context, chat_id,
            f"🎮 *{player_count} لاعبين جاهزين!*\n\n{players_list}\n\n"
            f"🗳️ هل تريدون بدء اللعبة الآن؟\n\n"
            f"✅ ابدأ = موافقة\n"
            f"❌ انتظر = انتظار المزيد\n\n"
            f"⏰ ينتهي التصويت خلال 30 ثانية!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        await asyncio.sleep(30)
        
        if chat_id in active_games and active_games[chat_id]['status'] == 'waiting':
            yes_votes = sum(1 for v in game['start_votes'].values() if v == 'yes')
            total = len(game['players'])
            
            if yes_votes >= 2 or total >= 6:
                await safe_send(context, chat_id, f"✅ *{yes_votes} أصوات بالموافقة!*\n🚀 انطلاق اللعبة...", parse_mode='Markdown')
                await start_game(chat_id, context)
            else:
                await safe_send(context, chat_id, "⏳ في انتظار المزيد من اللاعبين...\n👥 /join للانضمام", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ ask_start_vote: {e}")

async def start_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """بدء اللعبة مع رسائل مشوقة"""
    try:
        game = active_games[chat_id]
        players = list(game['players'].keys())
        impostor_count = get_impostor_count(len(players))
        
        random.shuffle(players)
        impostors = players[:impostor_count]
        crewmates = players[impostor_count:]
        
        game['impostors'] = impostors
        game['alive_crewmates'] = crewmates.copy()
        
        # إرسال الأدوار برسائل مشوقة
        for imp_id in impostors:
            game['players'][imp_id]['role'] = 'impostor'
            user_tools[imp_id] = random.sample(IMPOSTOR_TOOLS, random.randint(1, 2))
            tools_names = "\n".join([f"{t['emoji']} {t['name']}" for t in user_tools[imp_id]])
            
            # قصة تشويقية للقاتل
            story = random.choice([
                "أنت المطلوب رقم 1 في المجرة...",
                "القبطان يثق بك... لكنه لا يعلم الحقيقة!",
                "خطتك محكمة... لا أحد يشك بك!"
            ])
            
            try:
                await context.bot.send_message(
                    chat_id=imp_id,
                    text=f"🔪 *أنت القاتل!*\n\n{story}\n\n"
                         f"🎒 *أدواتك:*\n{tools_names}\n\n"
                         f"💀 للقتل: /kill @username\n"
                         f"🎒 للأدوات: /tools\n"
                         f"😈 للتخريب: /tasks\n\n"
                         f"⚠️ *تحذير:* استخدم أدواتك بحكمة!",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        for crew_id in crewmates:
            game['players'][crew_id]['role'] = 'crewmate'
            user_tools[crew_id] = random.sample(CREWMATE_TOOLS, random.randint(1, 2))
            tools_names = "\n".join([f"{t['emoji']} {t['name']}" for t in user_tools[crew_id]])
            
            try:
                await context.bot.send_message(
                    chat_id=crew_id,
                    text=f"👨‍🚀 *أنت فرد طاقم!*\n\n"
                         f"السفينة تعتمد عليك لاكتشاف القاتل!\n\n"
                         f"🎒 *أدواتك:*\n{tools_names}\n\n"
                         f"⚡ للمهام: /tasks\n"
                         f"🎒 للأدوات: /tools\n"
                         f"🚨 للاجتماع: /emergency\n\n"
                         f"💡 *نصيحة:* أكمل مهامك وراقب المشتبه بهم!",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        game['status'] = 'playing'
        game['start_time'] = datetime.now()
        
        # رسالة انطلاق مشوقة
        await safe_send(
            context, chat_id,
            f"🚀🔥🚀 *انطلقت اللعبة!*\n\n"
            f"👥 *{len(players)} لاعبين*\n"
            f"👨‍🚀 *{len(crewmates)} طاقم*\n"
            f"🔪 *{impostor_count} قتلة*\n\n"
            f"📋 *المهام المطلوبة:*\n"
            f"⚡ /tasks لإنجاز المهام\n"
            f"🎒 /tools لاستخدام الأدوات\n"
            f"📊 /status لمعرفة حالة اللعبة\n"
            f"🚨 /emergency لاجتماع طارئ\n\n"
            f"⚠️ *القاتل بينكم... فمن هو؟*"
        )
        
        # بدء الأحداث العشوائية
        if chat_id in event_tasks:
            event_tasks[chat_id].cancel()
        event_tasks[chat_id] = asyncio.create_task(random_events(chat_id, context))
        
        # مؤقت للاجتماع التلقائي بعد فترة
        asyncio.create_task(auto_meeting_reminder(chat_id, context))
        
    except Exception as e:
        logger.error(f"❌ start_game: {e}")

async def auto_meeting_reminder(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """تذكير بالاجتماع بعد فترة"""
    await asyncio.sleep(180)  # 3 دقائق
    if chat_id in active_games and active_games[chat_id]['status'] == 'playing':
        game = active_games[chat_id]
        if game['kill_count'] >= 1 and not game['emergency_used']:
            await safe_send(
                context, chat_id,
                "⏰ *تنبيه:* مر وقت على آخر جريمة!\n"
                "🚨 يمكنكم استخدام /emergency لاجتماع طارئ\n"
                "🕵️ ناقشوا أدلة الجريمة واتهموا المشتبه بهم!"
            )

async def random_events(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """أحداث عشوائية مثيرة"""
    try:
        while chat_id in active_games and active_games[chat_id]['status'] == 'playing':
            await asyncio.sleep(random.randint(45, 90))
            if chat_id in active_games and active_games[chat_id]['status'] == 'playing':
                event = random.choice(RANDOM_EVENTS)
                await safe_send(context, chat_id, event['message'])
                
                # تأثيرات إضافية
                if event['name'] == 'انقطاع الكهرباء':
                    active_games[chat_id]['lights_off'] = True
                    asyncio.create_task(restore_lights(chat_id, context))
                elif event['name'] == 'تسرب غاز':
                    active_games[chat_id]['smoke_active'] = True
                    asyncio.create_task(clear_gas(chat_id, context))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"❌ random_events: {e}")

async def restore_lights(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(30)
    if chat_id in active_games:
        active_games[chat_id]['lights_off'] = False
        await safe_send(context, chat_id, "💡 *عادت الإضاءة!*\n👀 يمكنكم الرؤية بوضوح الآن!")

async def clear_gas(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(25)
    if chat_id in active_games:
        active_games[chat_id]['smoke_active'] = False
        await safe_send(context, chat_id, "💨 *انقشع الغاز السام!*\n😷 يمكنكم التنفس بأمان!")

# ====== نظام التصويت المصلح ======
async def start_voting(chat_id: int, context: ContextTypes.DEFAULT_TYPE, from_emergency: bool = False):
    """بدء جولة تصويت - النسخة المصلحة"""
    try:
        if chat_id not in active_games:
            return
        
        game = active_games[chat_id]
        game['status'] = 'voting'
        game['votes'] = {}
        game['voted_players'] = set()
        
        alive_players = {pid: p for pid, p in game['players'].items() if p['alive']}
        
        if len(alive_players) <= 2:
            await safe_send(context, chat_id, "⚠️ عدد اللاعبين قليل جداً للتصويت!")
            game['status'] = 'playing'
            return
        
        # بناء رسالة التصويت
        vote_text = "🗳️ *جولة تصويت!*\n\n"
        if from_emergency:
            vote_text = "🚨 *تصويت طارئ!*\n\n"
        
        vote_text += "🎯 *صوت لطرد المشتبه به:*\n\n"
        
        # إنشاء أزرار التصويت - استخدام معرفات رقمية بسيطة
        keyboard = []
        for pid, pdata in alive_players.items():
            name = get_player_name(pdata)
            vote_text += f"• {name}\n"
            # استخدام callback data بسيط: vote_{chat_id}_{player_id}
            keyboard.append([InlineKeyboardButton(
                f"🗳️ طرد {name}", 
                callback_data=f"v_{chat_id}_{pid}"
            )])
        
        keyboard.append([InlineKeyboardButton("⏭️ تخطي التصويت", callback_data=f"v_{chat_id}_skip")])
        
        vote_text += f"\n⏰ *الوقت المتبقي: 45 ثانية*"
        vote_text += f"\n👥 *الأحياء:* {len(alive_players)}/{len(game['players'])}"
        
        # حذف رسالة التصويت القديمة
        if chat_id in vote_messages:
            try:
                await context.bot.delete_message(chat_id, vote_messages[chat_id])
            except:
                pass
        
        # إرسال رسالة التصويت
        msg = await safe_send(
            context, chat_id, vote_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        if msg:
            vote_messages[chat_id] = msg.message_id
        
        # مؤقت التصويت مع تحديثات
        for remaining in [30, 15, 10, 5]:
            await asyncio.sleep(15)
            if chat_id in active_games and active_games[chat_id]['status'] == 'voting':
                # تحديث رسالة التصويت
                voted_count = len(game.get('voted_players', set()))
                total_alive = len([p for p in game['players'].values() if p['alive']])
                
                update_text = (
                    f"⏰ *متبقي {remaining} ثانية!*\n\n"
                    f"🗳️ تم التصويت: {voted_count}/{total_alive}\n"
                    f"🤔 المترددين: {total_alive - voted_count}"
                )
                await safe_send(context, chat_id, update_text)
        
        # إنهاء التصويت
        if chat_id in active_games and active_games[chat_id]['status'] == 'voting':
            await end_voting(chat_id, context)
            
    except Exception as e:
        logger.error(f"❌ start_voting: {e}")

async def handle_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة التصويت - نسخة مبسطة ومضمونة"""
    query = update.callback_query
    
    try:
        data = query.data
        
        # التحقق من صيغة callback data
        if not data.startswith('v_'):
            return
        
        parts = data.split('_')
        if len(parts) < 3:
            await query.answer("❌ بيانات غير صالحة!")
            return
        
        chat_id = int(parts[1])
        vote_target = parts[2]
        
        # التحقق من وجود اللعبة
        if chat_id not in active_games:
            await query.answer("⚠️ اللعبة انتهت!", show_alert=True)
            return
        
        game = active_games[chat_id]
        user_id = query.from_user.id
        
        # التحقق من صلاحية اللاعب
        if user_id not in game['players']:
            await query.answer("❌ لست في اللعبة!", show_alert=True)
            return
        
        if not game['players'][user_id]['alive']:
            await query.answer("💀 الموتى لا يصوتون!", show_alert=True)
            return
        
        if game['status'] != 'voting':
            await query.answer("⏰ التصويت انتهى!", show_alert=True)
            return
        
        # التحقق من التصويت المزدوج
        if user_id in game.get('voted_players', set()):
            await query.answer("⚠️ لقد صوتت بالفعل!", show_alert=True)
            return
        
        # تسجيل التصويت
        game['votes'][user_id] = vote_target
        game['voted_players'].add(user_id)
        
        # رسالة تأكيد
        if vote_target == 'skip':
            await query.answer("⏭️ تم تخطي التصويت!", show_alert=True)
        else:
            try:
                target_id = int(vote_target)
                if target_id in game['players']:
                    target_name = get_player_name(game['players'][target_id])
                    await query.answer(f"🗳️ صوتت لطرد {target_name}!", show_alert=True)
                else:
                    await query.answer("🗳️ تم تسجيل تصويتك!", show_alert=True)
            except:
                await query.answer("🗳️ تم تسجيل تصويتك!", show_alert=True)
        
        # تحديث رسالة التصويت إذا أمكن
        if chat_id in vote_messages:
            try:
                voted_count = len(game['voted_players'])
                total_alive = len([p for p in game['players'].values() if p['alive'])
                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=vote_messages[chat_id],
                    caption=f"🗳️ *التصويت جارٍ...*\n\n✅ تم التصويت: {voted_count}/{total_alive}",
                    parse_mode='Markdown'
                )
            except:
                pass
        
    except Exception as e:
        logger.error(f"❌ handle_vote_callback: {e}")
        try:
            await query.answer("❌ حدث خطأ في التصويت!", show_alert=True)
        except:
            pass

async def end_voting(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """إنهاء التصويت وإعلان النتيجة"""
    try:
        if chat_id not in active_games:
            return
        
        game = active_games[chat_id]
        
        # عد الأصوات
        vote_count = {}
        for voter_id, target_id in game['votes'].items():
            if target_id != 'skip':
                vote_count[target_id] = vote_count.get(target_id, 0) + 1
        
        # رسالة نتائج التصويت
        result_text = "📊 *نتائج التصويت:*\n\n"
        
        if not vote_count:
            result_text += "⏭️ *تم تخطي التصويت!*\nلا أحد يُطرد اليوم..."
            await safe_send(context, chat_id, result_text)
            game['status'] = 'playing'
            game['emergency_used'] = False
            game['voted_players'] = set()
            return
        
        # عرض توزيع الأصوات
        for target_id, count in vote_count.items():
            try:
                target_name = get_player_name(game['players'][int(target_id)])
                result_text += f"• {target_name}: {count} صوت\n"
            except:
                pass
        
        # تحديد الأكثر تصويتاً
        most_voted = max(vote_count, key=vote_count.get)
        max_votes = vote_count[most_voted]
        
        # التحقق من التعادل
        tied = [pid for pid, v in vote_count.items() if v == max_votes]
        
        if len(tied) > 1:
            result_text += "\n⚖️ *تعادل في الأصوات!*\nلا أحد يُطرد."
            await safe_send(context, chat_id, result_text)
            game['status'] = 'playing'
            game['emergency_used'] = False
            game['voted_players'] = set()
            return
        
        # تنفيذ الطرد
        player_id = int(most_voted)
        player_data = game['players'][player_id]
        player_name = get_player_name(player_data)
        was_impostor = player_data['role'] == 'impostor'
        
        game['players'][player_id]['alive'] = False
        
        if was_impostor:
            game['impostors'].remove(player_id)
            result_text += (
                f"\n🎉🚀 *تم طرد القاتل!*\n\n"
                f"🔪 {player_name} كان القاتل!\n"
                f"✅ تم طرده إلى الفضاء!\n\n"
                f"🎊 *أحسنتم!* نجحتم في كشفه!"
            )
            update_user_points(player_id, 0, won=False, role='impostor')
        else:
            result_text += (
                f"\n💔😢 *تم طرد بريء!*\n\n"
                f"👨‍🚀 {player_name} كان من الطاقم!\n"
                f"😈 القاتل الحقيقي يضحك...\n\n"
                f"⚠️ *كونوا أكثر حذراً في المرة القادمة!*"
            )
            update_user_points(player_id, 0, won=False, role='crewmate')
            if player_id in game['alive_crewmates']:
                game['alive_crewmates'].remove(player_id)
        
        await safe_send(context, chat_id, result_text)
        
        # إضافة مشهد درامي للطرد
        await asyncio.sleep(1)
        if was_impostor:
            await safe_send(context, chat_id, 
                f"🚀 *{player_name}* يطفو في الفضاء...\n"
                f"👋 وداعاً أيها القاتل!\n"
                f"🌟 السفينة أصبحت أكثر أماناً!")
        else:
            await safe_send(context, chat_id,
                f"💫 *{player_name}* يطفو في الفضاء...\n"
                f"🕯️ روحه تذكرنا بأن نكون أكثر حذراً\n"
                f"🔪 القاتل الحقيقي لا يزال بينكم!")
        
        # التحقق من نهاية اللعبة
        if len(game['impostors']) == 0:
            await end_game(chat_id, context, 'crewmate')
            return
        
        if len(game['impostors']) >= len(game['alive_crewmates']):
            await end_game(chat_id, context, 'impostor')
            return
        
        # استئناف اللعبة
        game['status'] = 'playing'
        game['votes'] = {}
        game['voted_players'] = set()
        game['emergency_used'] = False
        
        await safe_send(context, chat_id, 
            f"🎮 *استئناف اللعبة!*\n\n"
            f"👥 الأحياء: {len(game['alive_crewmates']) + len(game['impostors'])}/{len(game['players'])}\n"
            f"🔪 قتلة متبقيين: {len(game['impostors'])}\n\n"
            f"⚡ /tasks للمهام\n"
            f"🚨 /emergency للاجتماع\n"
            f"⚠️ *كونوا حذرين... القاتل يتربص!*")
        
    except Exception as e:
        logger.error(f"❌ end_voting: {e}")

# ====== المهام والأدوات ======
async def execute_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_id = user.id
        game = None
        group_id = None
        
        for gid, g in active_games.items():
            if user_id in g['players']:
                game = g
                group_id = gid
                break
        
        if not game:
            await update.message.reply_text("❌ لست في لعبة حالياً!")
            return
        
        if game['status'] != 'playing':
            await update.message.reply_text("❌ اللعبة لم تبدأ بعد!")
            return
        
        player = game['players'][user_id]
        if not player['alive']:
            await update.message.reply_text("💀 أنت ميت! لا يمكنك تنفيذ مهام.")
            return
        
        if game.get('doors_locked') and player['role'] == 'crewmate':
            await update.message.reply_text("🚪 الأبواب مقفلة! لا يمكنك العمل الآن.")
            return
        
        if player['role'] == 'crewmate':
            if player['tasks'] >= player['total_tasks']:
                await update.message.reply_text("✅ أحسنت! أكملت كل مهامك!\n🔍 الآن ركز على كشف القاتل!")
                return
            
            task = random.choice(CREWMATE_TASKS)
            player_current_task[user_id] = {"task_id": task['id']}
            
            # إنشاء أزرار بسيطة
            keyboard = []
            for row in task['buttons']:
                btn_row = []
                for btn in row:
                    # استخدام نص بسيط للـ callback data
                    safe_btn = sanitize_callback_data(btn)
                    btn_row.append(InlineKeyboardButton(
                        btn, 
                        callback_data=f"t_{group_id}_{user_id}_{task['id']}_{safe_btn}"
                    ))
                keyboard.append(btn_row)
            
            await update.message.reply_text(
                f"{task['emoji']} *{task['name']}*\n\n{task['description']}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            # مهمة تخريبية للقاتل
            task = random.choice(IMPOSTOR_TASKS)
            keyboard = []
            for row in task['buttons']:
                btn_row = []
                for btn in row:
                    btn_row.append(InlineKeyboardButton(
                        btn,
                        callback_data=f"s_{group_id}_{user_id}_{task['id']}"
                    ))
                keyboard.append(btn_row)
            
            await update.message.reply_text(
                f"😈 *تخريب:* {task['name']}\n{task['emoji']} {task['description']}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"❌ execute_task: {e}")

async def handle_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أزرار المهام"""
    query = update.callback_query
    
    try:
        data = query.data
        
        if data.startswith('t_'):  # مهمة طاقم
            await handle_crewmate_task(update, context)
        elif data.startswith('s_'):  # مهمة تخريب
            await handle_sabotage(update, context)
    except Exception as e:
        logger.error(f"❌ handle_task_callback: {e}")
        try:
            await query.answer("❌ حدث خطأ!")
        except:
            pass

async def handle_crewmate_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة مهمة الطاقم"""
    query = update.callback_query
    data = query.data
    
    parts = data.split('_')
    if len(parts) < 5:
        await query.answer("❌ بيانات غير مكتملة!")
        return
    
    group_id = int(parts[1])
    user_id = int(parts[2])
    task_id = parts[3]
    answer = '_'.join(parts[4:])
    
    if query.from_user.id != user_id:
        await query.answer("❌ هذه ليست مهمتك!")
        return
    
    if group_id not in active_games:
        await query.answer("⚠️ اللعبة انتهت!")
        return
    
    game = active_games[group_id]
    
    # البحث عن المهمة
    task = next((t for t in CREWMATE_TASKS if t['id'] == task_id), None)
    if not task:
        await query.answer("❌ مهمة غير معروفة!")
        return
    
    # التحقق من الإجابة
    correct_answer = sanitize_callback_data(task['correct'])
    
    if answer == correct_answer:
        game['players'][user_id]['tasks'] += 1
        update_user_points(user_id, 15, task=True)
        
        await query.edit_message_text(
            f"{task['emoji']} *{task['name']}*\n\n{task['success']}\n\n"
            f"📊 تقدم المهام: {game['players'][user_id]['tasks']}/{game['players'][user_id]['total_tasks']}",
            parse_mode='Markdown'
        )
        
        if game['players'][user_id]['tasks'] >= game['players'][user_id]['total_tasks']:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🎉 *مبروك!* أكملت كل مهامك!\n🔍 الآن ساعد في كشف القاتل!"
                )
            except:
                pass
    else:
        await query.edit_message_text(
            "❌ *خطأ!*\n\nالمهمة فشلت... حاول مرة أخرى بـ /tasks",
            parse_mode='Markdown'
        )

async def handle_sabotage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة التخريب"""
    query = update.callback_query
    data = query.data
    
    parts = data.split('_')
    group_id = int(parts[1])
    user_id = int(parts[2])
    sab_id = parts[3]
    
    if query.from_user.id != user_id:
        return
    
    if group_id not in active_games:
        return
    
    game = active_games[group_id]
    
    if sab_id == "sab_reactor":
        await query.edit_message_text("☢️ *تم تخريب المفاعل!*\n⚠️ الأبواب ستغلق!", parse_mode='Markdown')
        game['doors_locked'] = True
        await safe_send(context, group_id, "🚨 *خطر!* المفاعل يذوب!\n🚪 الأبواب ستغلق لمدة 20 ثانية!")
        asyncio.create_task(restore_reactor(group_id, context))
    
    elif sab_id == "sab_oxygen":
        await query.edit_message_text("🫁 *تم قطع الأكسجين!*\n📵 الاتصالات معطلة!", parse_mode='Markdown')
        game['emergency_blocked'] = True
        await safe_send(context, group_id, "🚨 *خطر!* تسرب أكسجين!\n📵 الاجتماعات معطلة لمدة 45 ثانية!")
        asyncio.create_task(restore_oxygen(group_id, context))
    
    elif sab_id == "sab_lights":
        await query.edit_message_text("💡 *تم إطفاء الأنوار!*\n🌑 الظلام يخيم!", parse_mode='Markdown')
        game['lights_off'] = True
        await safe_send(context, group_id, "🌑 *انطفأت الأنوار!*\n👀 صعوبة في الرؤية لمدة 30 ثانية!")
        asyncio.create_task(restore_lights(group_id, context))

async def restore_reactor(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(20)
    if chat_id in active_games:
        active_games[chat_id]['doors_locked'] = False
        await safe_send(context, chat_id, "🔄 *تم إصلاح المفاعل!*\n🚪 الأبواب فتحت.")

async def restore_oxygen(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(45)
    if chat_id in active_games:
        active_games[chat_id]['emergency_blocked'] = False
        await safe_send(context, chat_id, "📶 *عادت الاتصالات!*\n🚨 يمكنكم استخدام /emergency الآن.")

async def emergency_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        if chat_id not in active_games:
            await update.message.reply_text("❌ لا توجد لعبة نشطة!")
            return
        
        game = active_games[chat_id]
        if game['status'] != 'playing':
            return
        
        if user.id not in game['players'] or not game['players'][user.id]['alive']:
            await update.message.reply_text("💀 الموتى لا يمكنهم طلب اجتماع!")
            return
        
        if game.get('emergency_blocked'):
            await update.message.reply_text("📵 الاتصالات معطلة! لا يمكنك طلب اجتماع الآن.")
            return
        
        if game.get('emergency_used'):
            await update.message.reply_text("❌ تم استخدام الاجتماع الطارئ مسبقاً!")
            return
        
        game['emergency_used'] = True
        game['meeting_count'] += 1
        
        await safe_send(
            context, chat_id,
            f"🚨🔴🚨 *اجتماع طارئ!*\n\n"
            f"👤 {user.first_name} طلب اجتماعاً!\n"
            f"🔍 الاجتماع رقم #{game['meeting_count']}\n\n"
            f"💬 *ناقشوا الأدلة:*\n"
            f"- من كان قريباً من الضحية؟\n"
            f"- من يتصرف بشكل مريب؟\n"
            f"- من لديه أدوات تخريب؟\n\n"
            f"⏰ لديكم 60 ثانية للنقاش..."
        )
        
        # مؤقت للنقاش
        for remaining in [30, 15, 10]:
            await asyncio.sleep(15)
            if chat_id in active_games and active_games[chat_id]['status'] == 'playing':
                await safe_send(context, chat_id, f"⏰ *{remaining} ثانية متبقية للنقاش!*")
        
        if chat_id in active_games:
            await start_voting(chat_id, context, from_emergency=True)
    except Exception as e:
        logger.error(f"❌ emergency_meeting: {e}")

async def end_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE, winner: str):
    try:
        game = active_games[chat_id]
        game['status'] = 'ended'
        
        # رسالة فوز مشوقة
        if winner == 'crewmate':
            await safe_send(context, chat_id,
                "🎉🏆✨\n\n"
                "*الطاقم يفوز!*\n\n"
                "🌟 تم اكتشاف كل القتلة!\n"
                "🚀 السفينة في أيد أمينة!\n"
                "👨‍🚀 الطاقم يستحق التقدير!\n\n"
                "🎊 *مبروك للناجين!*"
            )
            for pid in game['alive_crewmates']:
                update_user_points(pid, 100, won=True, role='crewmate')
        else:
            await safe_send(context, chat_id,
                "🔪👑💀\n\n"
                "*القاتل ينتصر!*\n\n"
                "😈 تم القضاء على الطاقم!\n"
                "🌑 الظلام يخيم على السفينة!\n"
                "💀 القاتل يفلت بجريمته!\n\n"
                "😱 *يا للهول!*"
            )
            for imp_id in game['impostors']:
                update_user_points(imp_id, 150, won=True, role='impostor')
        
        # كشف الأدوار
        await asyncio.sleep(2)
        roles_text = "👤 *كشف الأدوار:*\n\n"
        for pid, pdata in game['players'].items():
            role_emoji = "🔪 قاتل" if pdata['role'] == 'impostor' else "👨‍🚀 طاقم"
            status = "💀 ميت" if not pdata['alive'] else "✅ ناجي"
            roles_text += f"{role_emoji} | {get_player_name(pdata)} | {status}\n"
        
        await safe_send(context, chat_id, roles_text)
        
        # إحصائيات اللعبة
        game_duration = (datetime.now() - game['start_time']).seconds // 60
        stats_text = (
            f"📊 *إحصائيات الجولة:*\n\n"
            f"⏱️ المدة: {game_duration} دقيقة\n"
            f"💀 عدد القتلى: {game['kill_count']}\n"
            f"🚨 عدد الاجتماعات: {game['meeting_count']}\n"
            f"🎮 /new_game للعبة جديدة!"
        )
        await safe_send(context, chat_id, stats_text)
        
        await cleanup_game(chat_id)
        del active_games[chat_id]
    except Exception as e:
        logger.error(f"❌ end_game: {e}")

# ====== معالج الأزرار العام ======
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج عام لجميع الأزرار"""
    query = update.callback_query
    
    try:
        data = query.data
        
        # تصنيف نوع الـ callback
        if data.startswith('v_'):  # تصويت
            await handle_vote_callback(update, context)
        elif data.startswith('t_'):  # مهمة طاقم
            await handle_task_callback(update, context)
        elif data.startswith('s_'):  # تخريب
            await handle_task_callback(update, context)
        elif data.startswith('startv_'):  # تصويت البداية
            await handle_start_vote(update, context)
        elif data.startswith('join_'):  # انضمام
            await join_game(update, context)
        elif data.startswith('usetool_'):  # استخدام أداة
            await handle_tool_use(update, context)
        else:
            # أزرار القائمة الرئيسية
            await query.answer()
            if data == "start_playing":
                await query.message.reply_text(
                    "🎮 *للبدء:*\n\n"
                    "1️⃣ أضفني لمجموعة\n"
                    "2️⃣ ارفعني مشرف\n"
                    "3️⃣ اكتب /new_game\n"
                    "4️⃣ اطلب من أصدقائك /join\n\n"
                    "🎯 استمتعوا باللعبة!",
                    parse_mode='Markdown'
                )
            elif data == "view_stats":
                db_user = get_user(query.from_user.id)
                if db_user:
                    await query.message.reply_text(
                        f"📊 *إحصائياتك:*\n\n"
                        f"🏆 النقاط: {db_user['points']}\n"
                        f"🎮 الجولات: {db_user['games_played']}\n"
                        f"✅ الفوز: {db_user['games_won']}\n"
                        f"👨‍🚀 فوز كطاقم: {db_user['crewmate_wins']}\n"
                        f"🔪 فوز كقاتل: {db_user['impostor_wins']}",
                        parse_mode='Markdown'
                    )
            elif data == "view_leaderboard":
                leaders = get_leaderboard()
                if leaders:
                    text = "🏆 *المتصدرين:*\n\n"
                    for i, p in enumerate(leaders[:5], 1):
                        name = p['first_name'] or p['username'] or str(p['user_id'])
                        text += f"{i}. {name}: {p['points']} نقطة\n"
                    await query.message.reply_text(text, parse_mode='Markdown')
            elif data == "referral_code":
                db_user = get_user(query.from_user.id)
                if db_user:
                    await query.message.reply_text(
                        f"🔗 *كود الإحالة الخاص بك:*\n\n"
                        f"`{db_user['referral_code']}`\n\n"
                        f"📤 شاركه مع أصدقائك!\n"
                        f"💎 تكسب 75 نقطة لكل صديق",
                        parse_mode='Markdown'
                    )
    except Exception as e:
        logger.error(f"❌ callback_handler: {e}")
        try:
            await query.answer("حدث خطأ!")
        except:
            pass

# ====== معالج الأخطاء ======
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ خطأ: {context.error}")
    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ حدث خطأ غير متوقع! جاري استكشاف المشكلة..."
            )
    except:
        pass

# ====== الدالة الرئيسية ======
def main():
    try:
        init_db()
        
        app = Application.builder().token(BOT_TOKEN).build()
        
        # إضافة معالجات الأوامر
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("new_game", new_game))
        app.add_handler(CommandHandler("join", join_game))
        app.add_handler(CommandHandler("tasks", execute_task))
        app.add_handler(CommandHandler("emergency", emergency_meeting))
        app.add_handler(CommandHandler("stats", stats))
        app.add_handler(CommandHandler("leaderboard", leaderboard))
        app.add_handler(CommandHandler("referral", handle_referral_code))
        app.add_handler(CommandHandler("cancel_game", cancel_game))
        app.add_handler(CommandHandler("status", game_status))
        app.add_handler(CommandHandler("tools", show_tools))
        app.add_handler(CommandHandler("leave", leave_game))
        app.add_handler(CommandHandler("kill", kill_player))
        
        # معالج الأزرار
        app.add_handler(CallbackQueryHandler(callback_handler))
        
        # معالج الأخطاء
        app.add_error_handler(error_handler)
        
        logger.info("🤖🔥 بوت Among Us يعمل الآن!")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"❌ main: {e}")

if __name__ == "__main__":
    main()
