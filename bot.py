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

# نظام المهام المطور (مراحل متعددة تعطي شعوراً بالواقعية)
CREWMATE_TASKS = [
    {
        "id": "wires",
        "name": "إصلاح الأسلاك (مرحلة 1/2)",
        "emoji": "🔌",
        "description": "🔌 الأسلاك في الكافتيريا مقطوعة! اختر السلك الصحيح لتوصيله بالطرف الآخر:",
        "buttons": [["🔵 السلك الأزرق", "🟡 السلك الأصفر"], ["🔴 السلك الأحمر", "🟢 السلك الأخضر"]],
        "correct": "🔵 السلك الأزرق",
        "next_step": {
            "name": "إصلاح الأسلاك (مرحلة 2/2)",
            "description": "⚡ المرحلة الأخيرة! اضغط على مفتاح التشغيل لتمرير التيار الكهربائي:",
            "buttons": [["⚙️ تشغيل المولد", "❌ إلغاء"]],
            "correct": "⚙️ تشغيل المولد",
            "success": "✅ تم إصلاح الأسلاك بالكامل وعاد التيار للسفينة! 🎉"
        }
    },
    {
        "id": "card",
        "name": "مسح بطاقة الدخول",
        "emoji": "💳",
        "description": "💳 مرر البطاقة في جهاز القراءة بالمختبر بحذر وسرعة متوسطة:",
        "buttons": [["🐢 بطيء جداً", "🐇 سريع جداً"], ["🚶 سرعة متوسطة", "🛑 إلغاء"]],
        "correct": "🚶 سرعة متوسطة",
        "success": "✅ تم قبول البطاقة بنجاح! انفتح باب المختبر 🔓"
    },
    {
        "id": "garbage",
        "name": "تفريغ القمامة (مرحلة 1/2)",
        "emoji": "🗑️",
        "description": "🗑️ القمامة ممتلئة في المخزن! اضغط على الرافعة لفتح فتحة التهوية:",
        "buttons": [["⚙️ سحب الرافعة", "🔒 قفل الفتحة"]],
        "correct": "⚙️ سحب الرافعة",
        "next_step": {
            "name": "تفريغ القمامة (مرحلة 2/2)",
            "description": "💨 الآن اختر الكيس الممتلئ لرميه خارج السفينة في الفضاء:",
            "buttons": [["🟫 كيس بني", "⬛ كيس أسود"]],
            "correct": "⬛ كيس أسود",
            "success": "✅ تم تفريغ القمامة بنجاح في الفضاء الخارجي! 💫"
        }
    },
    {
        "id": "download",
        "name": "تحميل البيانات (مرحلة 1/2)",
        "emoji": "📤",
        "description": "📡 جاري سحب البيانات من غرفة الاتصالات... اختر السيرفر المحلي الآمن لبدء النقل:",
        "buttons": [["🌍 سيرفر عالمي", "🔒 سيرفر محلي"]],
        "correct": "🔒 سيرفر محلي",
        "next_step": {
            "name": "رفع البيانات (مرحلة 2/2)",
            "description": "💾 تم التنزيل! توجه إلى قاعة الاجتماعات وارفع الملفات إلى لوحة التحكم الرئيسية:",
            "buttons": [["⬆️ رفع الملفات الآن", "🔄 إعادة المحاولة"]],
            "correct": "⬆️ رفع الملفات الآن",
            "success": "✅ اكتمل رفع البيانات 100%! المهمة أنجزت بنجاح. 💾"
        }
    }
]

# مهام تخريبية للـ Impostor تؤثر فعلياً على اللعبة وتحدث فوضى
IMPOSTOR_TASKS = [
    {"id": "sab_reactor", "name": "تخريب المفاعل", "emoji": "☢️", "description": "🔴 هل تريد افتعال أزمة في المفاعل لشل حركة الطاقم؟", "buttons": [["🔥 تفعيل إنذار المفاعل", "❌ إلغاء"]]},
    {"id": "sab_oxygen", "name": "قطع الأكسجين", "emoji": "🫁", "description": "🚨 هل تريد قطع إمدادات الأكسجين لإجبار الطاقم على التفرق؟", "buttons": [["💨 إغلاق محابس الأكسجين", "❌ إلغاء"]]}
]

KILL_SCENARIOS = [
    {"weapon": "خنجر", "emoji": "🗡️", "scene": ["🕵️ *ظل أسود يتحرك في الظلام...*", "👤 *الضحية واقفة لوحدها...*", "💨 *خطوات سريعة من الخلف...*", "🩸 *طعنة صامتة اخترقت الظلام...*", "🤫 *القاتل يختفي كالشبح...*"], "death_message": "🔴💀🔴\n*تم اكتشاف جثة!*\n\n💀 {victim} مات مقتولاً بالخنجر!\n📍 {location}\n\n🚨 *اجتماع طارئ!*"},
    {"weapon": "مسدس", "emoji": "🔫", "scene": ["🎯 *القاتل يصوب من بعيد...*", "😤 *الضحية مشغولة...*", "💥 *طلقة مدوية هزت السفينة!*", "🏃 *القاتل يهرب والدخان يملأ المكان...*"], "death_message": "🔴💀🔴\n*جريمة قتل مروعة!*\n\n💀 {victim} انقتل بالرصاص!\n📍 {location}\n\n🚨 *كل المشتبه بهم إلى قاعة الاجتماعات!*"}
]

RANDOM_EVENTS = [
    {"name": "انقطاع الكهرباء", "emoji": "⚡", "message": "⚡ *انقطعت الكهرباء فجأة!*\n\n🌑 الظلام يخيم على السفينة...\n👀 القاتل يستغل الظلام!"},
    {"name": "زلزال في السفينة", "emoji": "🌋", "message": "🌋 *السفينة بتهتز بعنف!*\n\n💥 كل اللاعبين وقعوا!\n🏃 القاتل بيستغل الفوضى!"},
    {"name": "إنذار حريق", "emoji": "🔥", "message": "🔥🚨🔥 *إنذار حريق!*\n\n🚒 الرشاشات اشتغلت!\n👀 في وسط الفوضى... القاتل بيتحرك!"}
]

# ====== تخزين مؤقت مع قفل للوصول الآمن ======
active_games = {}
user_tools = {}
player_votes = {}  # {message_id: {voter_id: target_id}}
player_current_task = {}  # لتتبع حالة ومراحل مهمة كل لاعب حالياً
vote_locks = set()  # لمنع معالجة نفس التصويت مرتين
processed_callbacks = set()  # لتتبع الـ callbacks المعالجة

# ====== دوال قاعدة البيانات مع معالجة أفضل للأخطاء ======
def get_conn():
    """الحصول على اتصال بقاعدة البيانات مع إعادة المحاولة"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return conn
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"❌ فشل الاتصال بقاعدة البيانات بعد {max_retries} محاولات: {e}")
                raise
            logger.warning(f"⚠️ محاولة {attempt + 1} فشلت، إعادة المحاولة...")
            asyncio.sleep(1)

def init_db():
    """تهيئة قاعدة البيانات"""
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
        logger.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")

def get_user(user_id: int):
    """الحصول على معلومات المستخدم أو إنشاء مستخدم جديد"""
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
    """تحديث نقاط المستخدم"""
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
    """الحصول على قائمة المتصدرين"""
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
    """تسجيل المجموعة في قاعدة البيانات"""
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

async def safe_send_message(context, chat_id, text, parse_mode='Markdown', reply_markup=None):
    """إرسال رسالة بشكل آمن مع معالجة الأخطاء"""
    try:
        return await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except BadRequest as e:
        # محاولة الإرسال بدون parse_mode في حالة وجود أخطاء في التنسيق
        try:
            return await context.bot.send_message(
                chat_id=chat_id,
                text=text.replace('*', '').replace('_', ''),
                reply_markup=reply_markup
            )
        except Exception as e2:
            logger.error(f"❌ فشل إرسال الرسالة: {e2}")
    except Exception as e:
        logger.error(f"❌ خطأ في safe_send_message: {e}")
    return None

async def safe_edit_message(context, chat_id, message_id, text, parse_mode='Markdown', reply_markup=None):
    """تعديل رسالة بشكل آمن"""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.error(f"❌ خطأ في تعديل الرسالة: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في safe_edit_message: {e}")

# ====== معالجات الأوامر ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start"""
    try:
        user = update.effective_user
        get_user(user.id)
        welcome_text = (
            f"🎮 مرحباً {user.first_name}!\n\n"
            f"أنا بوت Among Us في تليجرام!\n"
            f"العب مع أصدقائك في المجموعات واكتشف القاتل!\n\n"
            f"👥 طريقة اللعب:\n"
            f"1. أضفني لمجموعتك وارفعني مشرف\n"
            f"2. اكتب /new_game لبدء جولة\n"
            f"3. استخدم /join للانضمام\n"
            f"4. نفذ المهام بـ /tasks\n"
            f"5. استخدم أدواتك بـ /tools\n\n"
            f"🏆 الأوامر: /new_game /cancel_game /join /tasks /tools /status /emergency /stats /leaderboard /help"
        )
        keyboard = [
            [InlineKeyboardButton("🎮 ابدأ اللعب", callback_data="start_playing"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="view_stats")],
            [InlineKeyboardButton("🏆 المتصدرين", callback_data="view_leaderboard"),
             InlineKeyboardButton("🔗 كود الإحالة", callback_data="referral_code")]
        ]
        await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"❌ خطأ في start: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /help"""
    try:
        help_text = (
            "🎮 دليل اللعب:\n\n"
            "/new_game - بدء لعبة جديدة\n"
            "/cancel_game - إلغاء اللعبة الحالية\n"
            "/join - الانضمام للعبة\n"
            "/leave - مغادرة اللعبة\n"
            "/tasks - تنفيذ المهام التفاعلية\n"
            "/tools - استخدام الأدوات المساعدة\n"
            "/status - معرفة حالة اللعبة\n"
            "/emergency - طلب اجتماع طارئ\n"
            "/kill @user - قتل لاعب (للقاتل في الخاص)\n"
            "/stats - إحصائياتك الشخصية\n"
            "/leaderboard - قائمة المتصدرين\n"
            "/referral - كود الإحالة الخاص بك"
        )
        await update.message.reply_text(help_text)
    except Exception as e:
        logger.error(f"❌ خطأ في help: {e}")

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء لعبة جديدة"""
    try:
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        if update.effective_chat.type == 'private':
            await update.message.reply_text("❌ هذا الأمر يعمل فقط في المجموعات!")
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
            'kill_cooldown': {},
            'emergency_used': False,
            'emergency_blocked': False,
            'smoke_active': False,
            'doors_locked': False,
            'start_votes': {},
            'start_time': datetime.now(),
            'event_tasks': set()  # لتتبع مهام الأحداث العشوائية
        }
        
        keyboard = [[InlineKeyboardButton("🎮 انضم للعبة", callback_data=f"join_{game_id}")]]
        await safe_send_message(
            context,
            chat_id,
            f"🚀 لعبة جديدة!\n\nمعرف: {game_id}\nالمنشئ: {user.first_name}\n\n"
            f"👥 /join للانضمام (الحد الأدنى: 4)\n"
            f"🗑️ /cancel_game لإلغاء اللعبة\n"
            f"⚠️ عند اكتمال 4 لاعبين، سيتم التصويت للبدء!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        register_group(chat_id, update.effective_chat.title or "مجموعة")
    except Exception as e:
        logger.error(f"❌ خطأ في new_game: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء إنشاء اللعبة!")

async def cancel_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء اللعبة"""
    try:
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        if chat_id not in active_games:
            await update.effective_message.reply_text("❌ لا توجد لعبة نشطة لإلغائها!")
            return
        
        game = active_games[chat_id]
        
        # التحقق من الصلاحيات
        is_admin = False
        try:
            member = await context.bot.get_chat_member(chat_id, user.id)
            if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                is_admin = True
        except:
            pass
        
        if user.id != game['creator'] and not is_admin:
            await update.effective_message.reply_text("❌ فقط منشئ اللعبة أو مشرف المجموعة يمكنه إلغاؤها!")
            return
        
        # تنظيف بيانات اللعبة
        await cleanup_game(chat_id)
        del active_games[chat_id]
        await update.effective_message.reply_text("🗑️ تم إلغاء اللعبة بنجاح!")
    except Exception as e:
        logger.error(f"❌ خطأ في cancel_game: {e}")

async def cleanup_game(chat_id: int):
    """تنظيف بيانات اللعبة"""
    if chat_id in active_games:
        game = active_games[chat_id]
        for pid in game['players']:
            if pid in user_tools:
                del user_tools[pid]
            if pid in player_current_task:
                del player_current_task[pid]
        # إلغاء مهام الأحداث العشوائية
        if 'event_tasks' in game:
            for task in game['event_tasks']:
                task.cancel()

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الانضمام للعبة"""
    try:
        query = update.callback_query
        if query:
            await query.answer()
        
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
            await msg.reply_text("❌ اللعبة مكتملة!")
            return
        
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
        await msg.reply_text(f"✅ {user.first_name} انضم! ({player_count}/10)")
        
        if player_count >= 4 and game['status'] == 'waiting':
            # إلغاء مهمة التصويت السابقة إذا وجدت
            if 'start_vote_task' in game:
                game['start_vote_task'].cancel()
            game['start_vote_task'] = asyncio.create_task(ask_start_vote(chat_id, context))
    except Exception as e:
        logger.error(f"❌ خطأ في join_game: {e}")

async def ask_start_vote(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """طلب التصويت لبدء اللعبة"""
    try:
        if chat_id not in active_games:
            return
        
        game = active_games[chat_id]
        game['start_votes'] = {}
        
        player_count = len(game['players'])
        players_list = "\n".join([f"• {get_player_name(p)}" for p in game['players'].values()])
        
        keyboard = [
            [InlineKeyboardButton("✅ نعم، ابدأ!", callback_data=f"startvote_{chat_id}_yes"),
             InlineKeyboardButton("❌ لا، انتظر", callback_data=f"startvote_{chat_id}_no")]
        ]
        
        await safe_send_message(
            context,
            chat_id,
            f"👥 *{player_count} لاعبين انضموا!*\n\n{players_list}\n\n"
            f"🎮 هل تريدون بدء اللعبة الآن؟\n\n"
            f"✅ نعم = موافقة\n"
            f"❌ لا = انتظار المزيد من اللاعبين\n\n"
            f"⏰ التصويت ينتهي بعد 30 ثانية!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        await asyncio.sleep(30)
        await process_start_vote(chat_id, context)
    except asyncio.CancelledError:
        pass  # تم إلغاء المهمة
    except Exception as e:
        logger.error(f"❌ خطأ في ask_start_vote: {e}")

async def handle_start_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة التصويت لبدء اللعبة"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        parts = data.split('_')
        chat_id = int(parts[1])
        vote = parts[2]
        
        if chat_id not in active_games:
            await query.answer("اللعبة غير موجودة!")
            return
        
        game = active_games[chat_id]
        if query.from_user.id not in game['players']:
            await query.answer("أنت لست في اللعبة!")
            return
        
        game['start_votes'][query.from_user.id] = vote
        await query.answer(f"صوتك: {'نعم' if vote == 'yes' else 'لا'}")
    except Exception as e:
        logger.error(f"❌ خطأ في handle_start_vote: {e}")

async def process_start_vote(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """معالجة نتيجة التصويت لبدء اللعبة"""
    try:
        if chat_id not in active_games:
            return
        
        game = active_games[chat_id]
        if game['status'] != 'waiting':
            return
        
        yes_votes = sum(1 for v in game['start_votes'].values() if v == 'yes')
        total_players = len(game['players'])
        
        if yes_votes >= 2 or total_players >= 6:
            await safe_send_message(context, chat_id, f"✅ {yes_votes} لاعبين وافقوا على البدء!\n🎮 جاري بدء اللعبة...")
            await start_game(chat_id, context)
        else:
            await safe_send_message(context, chat_id, "⏳ في انتظار المزيد من اللاعبين...\n👥 اكتب /join للانضمام أو /cancel_game للإلغاء!")
    except Exception as e:
        logger.error(f"❌ خطأ في process_start_vote: {e}")

async def leave_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مغادرة اللعبة"""
    try:
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        if chat_id not in active_games:
            await update.message.reply_text("❌ لا توجد لعبة نشطة!")
            return
        
        game = active_games[chat_id]
        if user.id not in game['players']:
            await update.message.reply_text("❌ أنت لست في اللعبة!")
            return
        
        if game['status'] != 'waiting':
            await update.message.reply_text("❌ لا يمكنك المغادرة بعد بدء اللعبة!")
            return
        
        del game['players'][user.id]
        await update.message.reply_text(f"👋 {user.first_name} غادر اللعبة!")
    except Exception as e:
        logger.error(f"❌ خطأ في leave_game: {e}")

async def game_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معرفة حالة اللعبة"""
    try:
        chat_id = update.effective_chat.id
        
        if chat_id not in active_games:
            await update.effective_message.reply_text("❌ لا توجد لعبة نشطة!")
            return
        
        game = active_games[chat_id]
        status_text = "📊 *حالة اللعبة:*\n\n"
        
        for pid, pdata in game['players'].items():
            name = get_player_name(pdata)
            if pdata['alive']:
                status_text += f"✅ {name}\n"
            else:
                status_text += f"💀 {name}\n"
        
        status_text += f"\n👥 الأحياء: {sum(1 for p in game['players'].values() if p['alive'])}/{len(game['players'])}"
        
        if game.get('smoke_active'):
            status_text += "\n💨 الدخان منتشر!"
        if game.get('doors_locked'):
            status_text += "\n🚪 الأبواب مقفلة!"
        
        await update.effective_message.reply_text(status_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ خطأ في game_status: {e}")

async def emergency_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجتماع طارئ"""
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
            return
        
        if game.get('emergency_blocked'):
            await update.message.reply_text("📵 الاتصالات معطلة!")
            return
        
        if game.get('emergency_used'):
            await update.message.reply_text("❌ تم استخدام الاجتماع الطارئ!")
            return
        
        game['emergency_used'] = True
        game['status'] = 'emergency'
        
        await safe_send_message(
            context,
            chat_id,
            f"🚨🔴🚨 *اجتماع طارئ!*\n\n👤 {user.first_name} طلب اجتماعاً!\n\n⏰ لديكم 90 ثانية للنقاش..."
        )
        
        for remaining in [60, 30, 15, 5]:
            await asyncio.sleep(15)
            if chat_id in active_games and active_games[chat_id]['status'] == 'emergency':
                await safe_send_message(context, chat_id, f"⏰ باقي {remaining} ثانية!")
        
        if chat_id in active_games and active_games[chat_id]['status'] == 'emergency':
            await start_voting(chat_id, context, from_emergency=True)
    except Exception as e:
        logger.error(f"❌ خطأ في emergency_meeting: {e}")

async def show_tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الأدوات"""
    try:
        user_id = update.effective_user.id
        
        if user_id not in user_tools or not user_tools[user_id]:
            await update.message.reply_text("🎒 ليس لديك أدوات حالياً!")
            return
        
        tools = user_tools[user_id]
        keyboard = [[InlineKeyboardButton(f"{t['emoji']} {t['name']}", callback_data=f"usetool_{user_id}_{i}")] for i, t in enumerate(tools)]
        await update.message.reply_text("🎒 *أدواتك:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ خطأ في show_tools: {e}")

async def handle_tool_use(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استخدام أداة"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        if not data.startswith('usetool_'):
            return
        
        parts = data.split('_')
        user_id = int(parts[1])
        tool_index = int(parts[2])
        
        if query.from_user.id != user_id:
            await query.answer("❌ ليست أدواتك!")
            return
        
        if user_id not in user_tools or tool_index >= len(user_tools[user_id]):
            await query.edit_message_text("❌ غير متاحة!")
            return
        
        tool = user_tools[user_id].pop(tool_index)
        game = None
        group_id = None
        
        for gid, g in active_games.items():
            if user_id in g['players']:
                game = g
                group_id = gid
                break
        
        if not game or game['status'] != 'playing':
            await query.edit_message_text("❌ لا يمكنك الآن!")
            return
        
        effect = tool['effect']
        
        if effect == 'track':
            alive = [pid for pid, p in game['players'].items() if p['alive'] and pid != user_id]
            if alive:
                target_id = random.choice(alive)
                target_name = get_player_name(game['players'][target_id])
                location = random.choice(LOCATIONS)
                await query.edit_message_text(f"📡 *جهاز التتبع:*\n\n{target_name} شوهد في: {location}", parse_mode='Markdown')
        
        elif effect == 'camera':
            alive = [pid for pid, p in game['players'].items() if p['alive'] and pid != user_id and not game.get('smoke_active')]
            if alive:
                target_id = random.choice(alive)
                target_name = get_player_name(game['players'][target_id])
                is_imp = game['players'][target_id]['role'] == 'impostor'
                status = "😈 مشبوه!" if is_imp else "👨‍🚀 طبيعي"
                await query.edit_message_text(f"📸 *كاميرا:*\n\n{target_name}: {status}", parse_mode='Markdown')
        
        elif effect == 'lie_detector':
            alive = [pid for pid, p in game['players'].items() if p['alive'] and pid != user_id]
            if alive:
                target_id = random.choice(alive)
                target_name = get_player_name(game['players'][target_id])
                is_imp = game['players'][target_id]['role'] == 'impostor'
                status = "😰 يكذب!" if is_imp else "😊 صادق"
                await query.edit_message_text(f"🕵️ *كشف الكذب:*\n\n{target_name}: {status}", parse_mode='Markdown')
        
        elif effect == 'shield':
            game['players'][user_id]['shield'] = True
            await query.edit_message_text("🛡️ *درع واقي!*\n\nأنت محمي من القتل لمرة واحدة", parse_mode='Markdown')
        
        elif effect == 'speed_boost':
            game['players'][user_id]['tasks'] = min(game['players'][user_id]['total_tasks'], game['players'][user_id]['tasks'] + 2)
            await query.edit_message_text("⚡ *مسرع المهام!*\n\nأنهيت مهمتين!", parse_mode='Markdown')
        
        elif effect == 'smoke_bomb':
            game['smoke_active'] = True
            await safe_send_message(context, group_id, "💨 دخان كثيف! الكاميرات تعطلت دقيقة")
            asyncio.create_task(clear_smoke(group_id, context))
            await query.edit_message_text("💨 تم تفعيل قنبلة الدخان!")
        
        elif effect == 'disguise':
            game['players'][user_id]['tasks'] += 1
            task = random.choice(CREWMATE_TASKS)
            await query.edit_message_text(f"🎭 *تنكر!*\n\nأكملت مهمة: {task['emoji']} {task['name']}", parse_mode='Markdown')
        
        elif effect == 'lock_doors':
            game['doors_locked'] = True
            await safe_send_message(context, group_id, "🚪🔒 الأبواب اتقفلت! الطاقم محبوس 30 ثانية!")
            asyncio.create_task(unlock_doors(group_id, context))
            await query.edit_message_text("🚪 تم قفل الأبواب!")
        
        elif effect == 'jam_comms':
            game['emergency_blocked'] = True
            await safe_send_message(context, group_id, "📵 تشويش! ممنوع اجتماع الطوارئ دقيقة")
            asyncio.create_task(restore_comms(group_id, context))
            await query.edit_message_text("📵 تم التشويش!")
    except Exception as e:
        logger.error(f"❌ خطأ في handle_tool_use: {e}")

async def clear_smoke(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """إزالة الدخان بعد فترة"""
    await asyncio.sleep(60)
    if chat_id in active_games:
        active_games[chat_id]['smoke_active'] = False
        await safe_send_message(context, chat_id, "💨 انقشع الدخان!")

async def unlock_doors(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """فتح الأبواب بعد فترة"""
    await asyncio.sleep(30)
    if chat_id in active_games:
        active_games[chat_id]['doors_locked'] = False
        await safe_send_message(context, chat_id, "🚪🔓 الأبواب اتفتحت!")

async def restore_comms(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """استعادة الاتصالات بعد فترة"""
    await asyncio.sleep(60)
    if chat_id in active_games:
        active_games[chat_id]['emergency_blocked'] = False
        await safe_send_message(context, chat_id, "📶 عادت الاتصالات!")

async def start_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """بدء اللعبة"""
    try:
        game = active_games[chat_id]
        players = list(game['players'].keys())
        impostor_count = get_impostor_count(len(players))
        
        random.shuffle(players)
        impostors = players[:impostor_count]
        crewmates = players[impostor_count:]
        
        game['impostors'] = impostors
        game['alive_crewmates'] = crewmates.copy()
        
        for imp_id in impostors:
            game['players'][imp_id]['role'] = 'impostor'
            user_tools[imp_id] = random.sample(IMPOSTOR_TOOLS, random.randint(1, 2))
            tools_names = "\n".join([f"{t['emoji']} {t['name']}" for t in user_tools[imp_id]])
            try:
                await context.bot.send_message(
                    chat_id=imp_id,
                    text=f"🔪 *أنت القاتل!*\n\n🎒 أدواتك:\n{tools_names}\n\n💀 /kill @username (مرة كل 60 ثانية)\n🎒 /tools للأدوات",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"⚠️ لم يتم إرسال رسالة للقاتل {imp_id}: {e}")
        
        for crew_id in crewmates:
            game['players'][crew_id]['role'] = 'crewmate'
            user_tools[crew_id] = random.sample(CREWMATE_TOOLS, random.randint(1, 2))
            tools_names = "\n".join([f"{t['emoji']} {t['name']}" for t in user_tools[crew_id]])
            try:
                await context.bot.send_message(
                    chat_id=crew_id,
                    text=f"👨‍🚀 *أنت فرد طاقم!*\n\n🎒 أدواتك:\n{tools_names}\n\n⚡ /tasks للمهام\n🎒 /tools للأدوات\n🚨 /emergency للاجتماع",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"⚠️ لم يتم إرسال رسالة للطاقم {crew_id}: {e}")
        
        game['status'] = 'playing'
        game['start_time'] = datetime.now()
        
        await safe_send_message(
            context,
            chat_id,
            f"🚀🔥🚀 *انطلقت اللعبة!*\n\n👥 {len(players)} لاعبين\n🔪 {impostor_count} قتلة\n\n"
            f"⚡ /tasks للمهام\n🎒 /tools للأدوات\n📊 /status للحالة\n🚨 /emergency للاجتماع"
        )
        
        # بدء الأحداث العشوائية
        event_task = asyncio.create_task(random_events(chat_id, context))
        if 'event_tasks' not in game:
            game['event_tasks'] = set()
        game['event_tasks'].add(event_task)
    except Exception as e:
        logger.error(f"❌ خطأ في start_game: {e}")

async def random_events(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """الأحداث العشوائية"""
    try:
        while chat_id in active_games and active_games[chat_id]['status'] == 'playing':
            await asyncio.sleep(random.randint(60, 120))
            if chat_id in active_games and active_games[chat_id]['status'] == 'playing':
                event = random.choice(RANDOM_EVENTS)
                await safe_send_message(context, chat_id, event['message'])
    except asyncio.CancelledError:
        pass  # تم إلغاء المهمة
    except Exception as e:
        logger.error(f"❌ خطأ في random_events: {e}")

# ====== نظام المهام المطور تفاعلياً وعميقاً ======
async def execute_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ مهمة"""
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
        
        if not game or game['status'] != 'playing':
            await update.message.reply_text("❌ لا توجد لعبة نشطة حالياً!")
            return
        
        if game.get('doors_locked') and game['players'][user_id]['role'] == 'crewmate':
            await update.message.reply_text("🚪 الأبواب مقفلة بفعل التخريب! لا يمكنك العمل الآن.")
            return
        
        player = game['players'][user_id]
        if not player['alive']:
            return
        
        if player['tasks'] >= player['total_tasks']:
            await update.message.reply_text("✅ رائع! لقد أنجزت جميع مهامك الموكلة إليك لحماية السفينة.")
            return
        
        if player['role'] == 'crewmate':
            # سحب مهمة عشوائية والبدء بالمرحلة الأولى
            task = random.choice(CREWMATE_TASKS)
            player_current_task[user_id] = {"task_id": task['id'], "step": 1}
            
            keyboard = [[InlineKeyboardButton(btn, callback_data=f"task_{group_id}_{user_id}_step1_{btn}") for btn in row] for row in task['buttons']]
            await update.message.reply_text(
                f"{task['emoji']} *{task['name']}*\n\n{task['description']}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            # مهام الـ Impostor التخريبية الحقيقية
            task = random.choice(IMPOSTOR_TASKS)
            keyboard = [[InlineKeyboardButton(btn, callback_data=f"sabotage_{group_id}_{user_id}_{task['id']}") for btn in row] for row in task['buttons']]
            await update.message.reply_text(
                f"😈 *غرفة تحكم التخريب الخاص بالقاتل*:\n\n{task['description']}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"❌ خطأ في execute_task: {e}")

async def handle_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ردود المهام"""
    try:
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if data.startswith('task_'):
            await handle_crewmate_task(update, context)
        elif data.startswith('sabotage_'):
            await handle_impostor_task(update, context)
    except Exception as e:
        logger.error(f"❌ خطأ في handle_task_callback: {e}")

async def handle_crewmate_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة مهمة الطاقم"""
    query = update.callback_query
    data = query.data
    
    parts = data.split('_')
    group_id = int(parts[1])
    user_id = int(parts[2])
    step = parts[3]
    answer = '_'.join(parts[4:])
    
    if query.from_user.id != user_id:
        await query.answer("❌ هذه ليست لوحة المهام الخاصة بك!")
        return
    
    if group_id not in active_games:
        return
    
    game = active_games[group_id]
    
    # العثور على المهمة الحالية للاعب
    current_info = player_current_task.get(user_id)
    if not current_info:
        return
    
    task = next((t for t in CREWMATE_TASKS if t['id'] == current_info['task_id']), None)
    if not task:
        return
    
    if step == "step1":
        if task['correct'] == answer:
            if "next_step" in task:
                # نقل اللاعب للمرحلة الثانية
                player_current_task[user_id]['step'] = 2
                next_step = task['next_step']
                keyboard = [[InlineKeyboardButton(btn, callback_data=f"task_{group_id}_{user_id}_step2_{btn}") for btn in row] for row in next_step['buttons']]
                await query.edit_message_text(
                    f"🔄 *{next_step['name']}*\n\n{next_step['description']}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            else:
                # مهمة من مرحلة واحدة نجحت مباشرة
                await query.edit_message_text(
                    f"{task['emoji']} *{task['name']}*\n\n{task.get('success', '✅ تم إنجاز المهمة!')}",
                    parse_mode='Markdown'
                )
                game['players'][user_id]['tasks'] += 1
                update_user_points(user_id, 15, task=True)
                await safe_send_message(
                    context,
                    group_id,
                    f"🛠️ {game['players'][user_id]['first_name']} أنجز مهمة بنجاح "
                    f"({game['players'][user_id]['tasks']}/{game['players'][user_id]['total_tasks']})"
                )
        else:
            await query.edit_message_text("❌ خطأ غير متوقع! تعطل النظام بالخطأ. حاول مجدداً عبر /tasks")
    
    elif step == "step2":
        next_step = task['next_step']
        if next_step['correct'] == answer:
            await query.edit_message_text(
                f"✨ *{next_step['name']}*\n\n{next_step['success']}",
                parse_mode='Markdown'
            )
            game['players'][user_id]['tasks'] += 1
            update_user_points(user_id, 15, task=True)
            await safe_send_message(
                context,
                group_id,
                f"🛠️ {game['players'][user_id]['first_name']} أتم مهمة معقدة من مرحلتين! "
                f"({game['players'][user_id]['tasks']}/{game['players'][user_id]['total_tasks']})"
            )
            if game['players'][user_id]['tasks'] >= game['players'][user_id]['total_tasks']:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="🎉 ممتاز! لقد أنهيت كل مهامك الرسمية بنجاح."
                    )
                except:
                    pass
        else:
            await query.edit_message_text("❌ فشلت في المرحلة الثانية! أعد المحاولة من البداية بـ /tasks")

async def handle_impostor_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة مهمة المخرب"""
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
        await query.edit_message_text("☢️ المفاعل تم تخريبه بنجاح! سيتم إحداث الفوضى!")
        await safe_send_message(context, group_id, "🚨🚨 *تحذير أمني*: المفاعل يذوب! الأبواب ستغلق تلقائياً بعد قليل!")
        game['doors_locked'] = True
        asyncio.create_task(restore_reactor(group_id, context))
    
    elif sab_id == "sab_oxygen":
        await query.edit_message_text("🫁 تم قطع خط الأكسجين بنجاح!")
        game['emergency_blocked'] = True
        await safe_send_message(context, group_id, "🚨🚨 *خطر*: تسريب في الأكسجين وتوقف أنظمة الاتصالات والاجتماعات لمدة 45 ثانية!")
        asyncio.create_task(restore_oxygen(group_id, context))

async def restore_reactor(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """استعادة المفاعل"""
    await asyncio.sleep(20)
    if chat_id in active_games:
        active_games[chat_id]['doors_locked'] = False
        await safe_send_message(context, chat_id, "🔄 إعادة ضبط نظام أمان المفاعل وفتح الأبواب.")

async def restore_oxygen(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """استعادة الأكسجين"""
    await asyncio.sleep(45)
    if chat_id in active_games:
        active_games[chat_id]['emergency_blocked'] = False
        await safe_send_message(context, chat_id, "📶 عادت أنظمة الطوارئ للعمل مجدداً.")

async def kill_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قتل لاعب"""
    try:
        user = update.effective_user
        user_id = user.id
        
        if update.effective_chat.type != 'private':
            await update.message.reply_text("❌ استخدم هذا الأمر في الخاص فقط!")
            return
        
        game = None
        group_id = None
        for gid, g in active_games.items():
            if user_id in g['players']:
                game = g
                group_id = gid
                break
        
        if not game:
            await update.message.reply_text("❌ لست في أي لعبة حالياً!")
            return
        
        player = game['players'][user_id]
        if player['role'] != 'impostor' or not player['alive']:
            await update.message.reply_text("❌ لا يمكنك القتل!")
            return
        
        now = datetime.now()
        if user_id in game['kill_cooldown']:
            elapsed = (now - game['kill_cooldown'][user_id]).total_seconds()
            if elapsed < 60:
                remaining = int(60 - elapsed)
                await update.message.reply_text(f"⏰ انتظر {remaining} ثانية قبل القتل مرة أخرى!")
                return
        
        if not context.args:
            await update.message.reply_text("❌ استخدم: /kill @username")
            return
        
        victim_username = context.args[0].replace('@', '')
        
        victim_id = None
        for pid, pdata in game['players'].items():
            if pdata['username'] == victim_username and pdata['alive'] and pid != user_id:
                victim_id = pid
                break
        
        if not victim_id:
            await update.message.reply_text("❌ لم يتم العثور على اللاعب!")
            return
        
        if game['players'][victim_id].get('shield'):
            game['players'][victim_id]['shield'] = False
            await update.message.reply_text("🛡️ الضحية محمية بدرع!")
            await safe_send_message(context, group_id, f"🛡️ حاول أحدهم قتل {game['players'][victim_id]['first_name']} لكن الدرع حماه!")
            return
        
        game['kill_cooldown'][user_id] = now
        
        scenario = random.choice(KILL_SCENARIOS)
        victim_name = game['players'][victim_id]['first_name']
        location = random.choice(LOCATIONS)
        
        for msg in scenario['scene']:
            await update.message.reply_text(msg, parse_mode='Markdown')
            await asyncio.sleep(1)
        
        game['players'][victim_id]['alive'] = False
        game['dead_players'].append(victim_id)
        if victim_id in game['alive_crewmates']:
            game['alive_crewmates'].remove(victim_id)
        
        death_msg = scenario['death_message'].format(victim=victim_name, location=location)
        await safe_send_message(context, group_id, death_msg)
        update_user_points(user_id, 30, kill=True)
        await update.message.reply_text("✅ تم القتل!")
        
        # التحقق من نهاية اللعبة
        if len(game['impostors']) >= len(game['alive_crewmates']):
            await end_game(group_id, context, 'impostor')
        else:
            await start_voting(group_id, context)
    except Exception as e:
        logger.error(f"❌ خطأ في kill_player: {e}")

async def start_voting(chat_id: int, context: ContextTypes.DEFAULT_TYPE, from_emergency: bool = False):
    """بدء التصويت"""
    try:
        if chat_id not in active_games:
            return
        
        game = active_games[chat_id]
        game['status'] = 'voting'
        game['votes'] = {}
        
        alive_players = {pid: p for pid, p in game['players'].items() if p['alive']}
        
        vote_text = "🚨 *انتهى وقت النقاش!*\n\n🗳️ *جولة تصويت!*\n\n" if from_emergency else "🗳️ *جولة تصويت!*\n\n"
        vote_text += "صوتوا لطرد المشتبه به:\n\n"
        
        keyboard = []
        for pid, pdata in alive_players.items():
            name = get_player_name(pdata)
            vote_text += f"• {name} (@{pdata['username']})\n"
            keyboard.append([InlineKeyboardButton(f"🗳️ طرد {name}", callback_data=f"vote_{chat_id}_{pid}")])
        
        keyboard.append([InlineKeyboardButton("⏭️ تخطي التصويت", callback_data=f"vote_{chat_id}_skip")])
        
        msg = await safe_send_message(
            context,
            chat_id,
            vote_text + "\n⏰ *لديكم 45 ثانية!*",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        if msg:
            player_votes[msg.message_id] = {'chat_id': chat_id, 'votes': {}}
        
        for remaining in [30, 15, 5]:
            await asyncio.sleep(15)
            if chat_id in active_games and active_games[chat_id]['status'] == 'voting':
                await safe_send_message(context, chat_id, f"⏰ باقي {remaining} ثانية!")
        
        if chat_id in active_games and active_games[chat_id]['status'] == 'voting':
            await end_voting(chat_id, context)
    except Exception as e:
        logger.error(f"❌ خطأ في start_voting: {e}")

async def handle_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة التصويت"""
    try:
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if not data.startswith('vote_'):
            return
        
        # منع المعالجة المتكررة
        callback_id = f"{query.from_user.id}_{data}"
        if callback_id in processed_callbacks:
            await query.answer("تم معالجة تصويتك بالفعل!")
            return
        
        processed_callbacks.add(callback_id)
        
        parts = data.split('_')
        chat_id = int(parts[1])
        vote_target = parts[2]
        
        if chat_id not in active_games:
            await query.answer("اللعبة انتهت!")
            return
        
        game = active_games[chat_id]
        if query.from_user.id not in game['players'] or not game['players'][query.from_user.id]['alive']:
            await query.answer("❌ لا يمكنك التصويت!", show_alert=True)
            return
        
        # تسجيل التصويت
        game['votes'][query.from_user.id] = vote_target
        
        if vote_target == 'skip':
            await query.answer("⏭️ تم تخطي التصويت!")
        else:
            target_name = get_player_name(game['players'][int(vote_target)])
            await query.answer(f"🗳️ صوتت لطرد {target_name}")
    except Exception as e:
        logger.error(f"❌ خطأ في handle_vote_callback: {e}")

async def end_voting(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """إنهاء التصويت"""
    try:
        if chat_id not in active_games:
            return
        
        game = active_games[chat_id]
        
        vote_count = {}
        for voter_id, target_id in game['votes'].items():
            if target_id != 'skip':
                vote_count[target_id] = vote_count.get(target_id, 0) + 1
        
        if not vote_count:
            await safe_send_message(context, chat_id, "⏭️ تم تخطي التصويت!")
            game['status'] = 'playing'
            return
        
        most_voted = max(vote_count, key=vote_count.get)
        max_votes = vote_count[most_voted]
        
        # التحقق من التعادل
        tied = [pid for pid, v in vote_count.items() if v == max_votes]
        if len(tied) > 1:
            await safe_send_message(context, chat_id, "⚖️ تعادل! لا أحد يُطرد")
            game['status'] = 'playing'
            return
        
        player_id = int(most_voted)
        player_data = game['players'][player_id]
        player_name = get_player_name(player_data)
        
        game['players'][player_id]['alive'] = False
        
        if player_data['role'] == 'impostor':
            game['impostors'].remove(player_id)
            await safe_send_message(
                context,
                chat_id,
                f"🎉🚀 *تم طرد القاتل!*\n\n🔪 {player_name} كان القاتل!\n✅ تم طرده للفضاء!"
            )
            update_user_points(player_id, 0, won=False, role='impostor')
            
            if len(game['impostors']) == 0:
                await end_game(chat_id, context, 'crewmate')
                return
        else:
            await safe_send_message(
                context,
                chat_id,
                f"😢💔 *تم طرد بريء!*\n\n👨‍🚀 {player_name} كان طاقم!\n😈 القاتل يضحك..."
            )
            update_user_points(player_id, 0, won=False, role='crewmate')
            if player_id in game['alive_crewmates']:
                game['alive_crewmates'].remove(player_id)
        
        # التحقق من نهاية اللعبة
        if len(game['impostors']) >= len(game['alive_crewmates']):
            await end_game(chat_id, context, 'impostor')
            return
        
        game['status'] = 'playing'
        game['votes'] = {}
        game['emergency_used'] = False
    except Exception as e:
        logger.error(f"❌ خطأ في end_voting: {e}")

async def end_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE, winner: str):
    """إنهاء اللعبة"""
    try:
        game = active_games[chat_id]
        game['status'] = 'ended'
        
        if winner == 'crewmate':
            win_text = "🎉🏆 *الطاقم يفوز!* تم اكتشاف كل القتلة!"
            for pid in game['alive_crewmates']:
                update_user_points(pid, 100, won=True, role='crewmate')
            for imp_id in game['impostors']:
                update_user_points(imp_id, 0, won=False, role='impostor')
        else:
            win_text = "🔪👑 *القاتل ينتصر!* تم القضاء على الطاقم!"
            for imp_id in game['impostors']:
                update_user_points(imp_id, 150, won=True, role='impostor')
            for pid in game['players']:
                if pid not in game['impostors']:
                    update_user_points(pid, 0, won=False, role='crewmate')
        
        await safe_send_message(
            context,
            chat_id,
            f"{win_text}\n\n🏆 *نهاية الجولة!*\n\n🎮 /new_game لجولة جديدة!"
        )
        
        roles_text = "👤 *الأدوار:*\n\n"
        for pid, pdata in game['players'].items():
            role_emoji = "🔪" if pdata['role'] == 'impostor' else "👨‍🚀"
            status = "💀 ميت" if not pdata['alive'] else "✅ حي"
            roles_text += f"{role_emoji} {get_player_name(pdata)} - {status}\n"
        
        await safe_send_message(context, chat_id, roles_text)
        
        # تنظيف البيانات
        await cleanup_game(chat_id)
        del active_games[chat_id]
        
        # تنظيف الـ callbacks المعالجة
        processed_callbacks.clear()
    except Exception as e:
        logger.error(f"❌ خطأ في end_game: {e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الإحصائيات"""
    try:
        db_user = get_user(update.effective_user.id)
        if not db_user:
            await update.message.reply_text("❌ حدث خطأ في جلب الإحصائيات!")
            return
        
        name = db_user['first_name'] or db_user['username'] or 'لاعب'
        win_rate = (db_user['games_won'] / db_user['games_played'] * 100) if db_user['games_played'] > 0 else 0
        
        stats_text = (
            f"📊 *{name}*\n\n"
            f"🏆 نقاط: {db_user['points']}\n"
            f"🎮 جولات: {db_user['games_played']}\n"
            f"✅ فوز: {db_user['games_won']}\n"
            f"📈 نسبة: {win_rate:.1f}%\n"
            f"👨‍🚀 فوز كطاقم: {db_user['crewmate_wins']}\n"
            f"🔪 فوز كقاتل: {db_user['impostor_wins']}\n"
            f"💀 عمليات قتل: {db_user['total_kills']}\n"
            f"🛠️ مهام منجزة: {db_user['total_tasks']}"
        )
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ خطأ في stats: {e}")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المتصدرين"""
    try:
        leaders = get_leaderboard()
        if not leaders:
            await update.message.reply_text("❌ لا توجد بيانات حالياً!")
            return
        
        lb = "🏆 *المتصدرين*\n\n"
        medals = ["🥇", "🥈", "🥉"]
        
        for i, p in enumerate(leaders[:10]):
            m = medals[i] if i < 3 else f"{i+1}."
            name = p['first_name'] or p['username'] or str(p['user_id'])
            lb += f"{m} {name}: {p['points']} نقطة\n"
        
        await update.message.reply_text(lb, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ خطأ في leaderboard: {e}")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض كود الإحالة"""
    try:
        db_user = get_user(update.effective_user.id)
        if db_user:
            await update.message.reply_text(
                f"🔗 كود الإحالة الخاص بك: `{db_user['referral_code']}`\n\n"
                f"🎁 أرسل هذا الكود لأصدقائك لاستخدامه مع /referral CODE\n"
                f"💎 ستحصل على 75 نقطة وسيحصل صديقك على 25 نقطة!",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"❌ خطأ في referral: {e}")

async def handle_referral_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استخدام كود إحالة"""
    try:
        if not context.args:
            await update.message.reply_text("❌ استخدم: /referral CODE")
            return
        
        ref_code = context.args[0]
        user_id = update.effective_user.id
        
        conn = get_conn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # البحث عن صاحب الكود
        cursor.execute('SELECT * FROM users WHERE referral_code = %s', (ref_code,))
        referrer = cursor.fetchone()
        
        if not referrer:
            await update.message.reply_text("❌ كود غير صالح!")
            cursor.close()
            conn.close()
            return
        
        if referrer['user_id'] == user_id:
            await update.message.reply_text("❌ لا يمكنك استخدام كودك الخاص!")
            cursor.close()
            conn.close()
            return
        
        # التحقق من عدم استخدام كود سابق
        cursor.execute('SELECT referred_by FROM users WHERE user_id = %s', (user_id,))
        user = cursor.fetchone()
        if user and user['referred_by']:
            await update.message.reply_text("❌ لقد استخدمت كود إحالة من قبل!")
            cursor.close()
            conn.close()
            return
        
        # تحديث البيانات
        cursor.execute('UPDATE users SET referred_by = %s WHERE user_id = %s', (referrer['user_id'], user_id))
        cursor.execute('UPDATE users SET points = points + 75 WHERE user_id = %s', (referrer['user_id'],))
        cursor.execute('UPDATE users SET points = points + 25 WHERE user_id = %s', (user_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        await update.message.reply_text("🎉 تم تفعيل كود الإحالة بنجاح!\n💎 حصلت على 25 نقطة!")
    except Exception as e:
        logger.error(f"❌ خطأ في handle_referral_code: {e}")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج عام للـ callbacks"""
    try:
        query = update.callback_query
        data = query.data
        
        # منع معالجة callbacks المتعددة في نفس الوقت
        callback_id = f"{query.from_user.id}_{data}_{query.message.message_id}"
        if callback_id in vote_locks:
            await query.answer("جاري المعالجة...")
            return
        
        vote_locks.add(callback_id)
        
        try:
            if data.startswith('task_'):
                await handle_task_callback(update, context)
            elif data.startswith('sabotage_'):
                await handle_task_callback(update, context)
            elif data.startswith('vote_'):
                await handle_vote_callback(update, context)
            elif data.startswith('usetool_'):
                await handle_tool_use(update, context)
            elif data.startswith('startvote_'):
                await handle_start_vote(update, context)
            elif data.startswith('join_'):
                await join_game(update, context)
            else:
                await query.answer()
                if data == "start_playing":
                    await query.message.reply_text("🎮 أضفني لمجموعة وارفعني مشرف!")
                elif data == "view_stats":
                    db_user = get_user(query.from_user.id)
                    if db_user:
                        await query.message.reply_text(f"📊 نقاطك: {db_user['points']}")
                elif data == "view_leaderboard":
                    leaders = get_leaderboard()
                    text = "🏆 المتصدرين:\n"
                    for i, p in enumerate(leaders[:5], 1):
                        name = p['first_name'] or p['username'] or str(p['user_id'])
                        text += f"{i}. {name}: {p['points']}\n"
                    await query.message.reply_text(text)
                elif data == "referral_code":
                    db_user = get_user(query.from_user.id)
                    if db_user:
                        await query.message.reply_text(f"🔗 كودك: {db_user['referral_code']}")
        finally:
            # إزالة القفل بعد المعالجة
            vote_locks.discard(callback_id)
    except Exception as e:
        logger.error(f"❌ خطأ في callback_handler: {e}")
        try:
            await query.answer("حدث خطأ، حاول مرة أخرى!")
        except:
            pass

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء العام"""
    try:
        logger.error(f"❌ خطأ: {context.error}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ حدث خطأ داخلي! جاري إصلاح المشكلة..."
            )
    except Exception as e:
        logger.error(f"❌ خطأ في error_handler: {e}")

def main():
    """الدالة الرئيسية"""
    try:
        # تهيئة قاعدة البيانات
        init_db()
        
        # إنشاء التطبيق
        app = Application.builder().token(BOT_TOKEN).build()
        
        # إضافة معالجات الأوامر
        commands = [
            CommandHandler("start", start),
            CommandHandler("help", help_command),
            CommandHandler("new_game", new_game),
            CommandHandler("cancel_game", cancel_game),
            CommandHandler("join", join_game),
            CommandHandler("leave", leave_game),
            CommandHandler("tasks", execute_task),
            CommandHandler("status", game_status),
            CommandHandler("emergency", emergency_meeting),
            CommandHandler("tools", show_tools),
            CommandHandler("kill", kill_player),
            CommandHandler("stats", stats),
            CommandHandler("leaderboard", leaderboard),
            CommandHandler("referral", handle_referral_code),
        ]
        
        for handler in commands:
            app.add_handler(handler)
        
        # إضافة معالج الـ callbacks
        app.add_handler(CallbackQueryHandler(callback_handler))
        
        # إضافة معالج الأخطاء
        app.add_error_handler(error_handler)
        
        logger.info("🤖🔥 بوت Among Us المطور يعمل الآن!")
        
        # تشغيل البوت
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"❌ خطأ في main: {e}")

if __name__ == "__main__":
    main()
