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
import logging

# ====== إعدادات التسجيل ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== إعدادات البوت ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ====== ثوابت اللعبة ======
CREWMATE_TASKS = [
    {
        "name": "إصلاح الأسلاك",
        "emoji": "🔌",
        "description": "الأسلاك متشابكة! اضغط على الزر الصحيح لتوصيلها",
        "buttons": [
            ["🔵 السلك الأزرق", "🟡 السلك الأصفر"],
            ["🔴 السلك الأحمر", "🟢 السلك الأخضر"]
        ],
        "correct": "🔵 السلك الأزرق",
        "success": "✅ تم إصلاح الأسلاك بنجاح! الأضواء رجعت تشتغل 🎉"
    },
    {
        "name": "مسح بطاقة الدخول",
        "emoji": "💳",
        "description": "اختر السرعة الصحيحة لتمرير البطاقة",
        "buttons": [
            ["🐢 بطيء", "🐇 سريع"],
            ["🏃 سريع جداً", "🚶 متوسط"]
        ],
        "correct": "🚶 متوسط",
        "success": "✅ تم مسح البطاقة! الباب اتفتح 🔓"
    },
    {
        "name": "تفريغ القمامة",
        "emoji": "🗑️",
        "description": "اختر الكيس الصحيح لتفريغه",
        "buttons": [
            ["🟫 كيس بني", "⬛ كيس أسود"],
            ["🟦 كيس أزرق", "🟩 كيس أخضر"]
        ],
        "correct": "⬛ كيس أسود",
        "success": "✅ تم تفريغ القمامة! المكان أنضف 💫"
    },
    {
        "name": "تحميل البيانات",
        "emoji": "📤",
        "description": "اختر السيرفر الصحيح للتحميل",
        "buttons": [
            ["🌍 أوروبا", "🌎 أمريكا"],
            ["🌏 آسيا", "🔒 محلي"]
        ],
        "correct": "🔒 محلي",
        "success": "✅ تم تحميل البيانات! المهمة خلصت 💾"
    },
    {
        "name": "معايرة المحرك",
        "emoji": "⚙️",
        "description": "اختر درجة الحرارة الصحيحة",
        "buttons": [
            ["🌡️ 100°", "🌡️ 200°"],
            ["🌡️ 300°", "🌡️ 150°"]
        ],
        "correct": "🌡️ 150°",
        "success": "✅ تمت معايرة المحرك! السفينة جاهزة 🚀"
    },
    {
        "name": "تنظيف الفلتر",
        "emoji": "🧹",
        "description": "اختر الفلتر اللي يحتاج تنظيف",
        "buttons": [
            ["🔵 فلتر أزرق", "🔴 فلتر أحمر"],
            ["🟡 فلتر أصفر", "⚪ فلتر أبيض"]
        ],
        "correct": "🔴 فلتر أحمر",
        "success": "✅ تم تنظيف الفلتر! الهواء نقي 🌬️"
    }
]

IMPOSTOR_TASKS = [
    {
        "name": "تخريب المفاعل",
        "emoji": "☢️",
        "description": "حاول تخريب المفاعل (ستهزم دائماً)",
        "buttons": [
            ["🔴 زر الطوارئ", "🟢 زر التشغيل"],
            ["🟡 زر التعطيل", "🔵 زر التبريد"]
        ],
        "any_click": True,
        "failure": "❌ فشل التخريب! المفاعل أمان زيادة عن اللزوم 💥"
    },
    {
        "name": "قطع الأكسجين",
        "emoji": "🫁",
        "description": "حاول قطع الأكسجين (ستهزم دائماً)",
        "buttons": [
            ["🔧 صمام 1", "🔧 صمام 2"],
            ["🔧 صمام 3", "🔧 صمام 4"]
        ],
        "any_click": True,
        "failure": "❌ فشل قطع الأكسجين! النظام أمان قوي 🆘"
    }
]

KILL_SCENARIOS = [
    {
        "weapon": "خنجر",
        "emoji": "🗡️",
        "scene": [
            "🕵️ ضحية مشبوهة ظهرت قدامك...",
            "👤 بتتسلل من ورا الضل...",
            "💨 حركة سريعة! الضحية ماخدتش بالها",
            "🩸 طعنة صامتة في الضلمة...",
            "🤫 محدش شاف حاجة! بتختفي بسرعة"
        ],
        "death_message": "💀 {victim} اتطعلن بالخنجر! الجثة في الكافتيريا 🗡️"
    },
    {
        "weapon": "مسدس",
        "emoji": "🔫",
        "scene": [
            "🎯 بتصوب على الهدف...",
            "😤 الضحية واقفة لوحدها في الرواق",
            "💥 طلقة سريعة مدوية!",
            "🏃‍♂️ بتجري بسرعة قبل ما حد يجي",
            "🌫️ الدخان مالي المكان..."
        ],
        "death_message": "💀 {victim} انضرب بالرصاص! الجثة في الرواق 🔫"
    }
]

# ====== تخزين مؤقت للجلسات النشطة ======
active_games = {}
user_tasks = {}  # {user_id: task_message_id}

# ====== دوال قاعدة البيانات ======
def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            first_name VARCHAR(255),
            points INT DEFAULT 0,
            games_played INT DEFAULT 0,
            games_won INT DEFAULT 0,
            crewmate_wins INT DEFAULT 0,
            impostor_wins INT DEFAULT 0,
            total_kills INT DEFAULT 0,
            total_tasks INT DEFAULT 0,
            referral_code VARCHAR(10) UNIQUE,
            referred_by BIGINT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            group_id BIGINT PRIMARY KEY,
            title VARCHAR(255),
            active_game BOOLEAN DEFAULT FALSE,
            total_games INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()
    logger.info("✅ تم تهيئة قاعدة البيانات")

def get_user(user_id: int):
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        referral_code = str(uuid.uuid4())[:8]
        cursor.execute(
            'INSERT INTO users (user_id, referral_code) VALUES (%s, %s) RETURNING *',
            (user_id, referral_code)
        )
        conn.commit()
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
        user = cursor.fetchone()
    
    cursor.close()
    conn.close()
    return user

def update_user_points(user_id: int, points: int, won: bool = False, 
                       role: str = None, kill: bool = False, task: bool = False):
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
    
    query = f"UPDATE users SET {', '.join(update_parts)} WHERE user_id = %s"
    cursor.execute(query, params)
    
    conn.commit()
    cursor.close()
    conn.close()

def get_leaderboard():
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cursor.execute(
        'SELECT user_id, username, first_name, points, games_won FROM users ORDER BY points DESC LIMIT 10'
    )
    leaders = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return leaders

def register_group(group_id: int, title: str):
    conn = get_conn()
    cursor = conn.cursor()
    
    cursor.execute(
        'INSERT INTO groups (group_id, title) VALUES (%s, %s) ON CONFLICT (group_id) DO UPDATE SET title = %s',
        (group_id, title, title)
    )
    
    conn.commit()
    cursor.close()
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

def get_player_name(player_data: dict) -> str:
    """الحصول على اسم اللاعب بشكل آمن"""
    return player_data.get('first_name') or player_data.get('username') or 'لاعب'

# ====== معالجات الأوامر ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        f"4. نفذ المهام التفاعلية بـ /tasks\n"
        f"5. صوت لطرد المشتبه بـ /vote\n\n"
        f"🏆 الأوامر الرئيسية:\n"
        f"/start - البدء\n"
        f"/new_game - إنشاء لعبة جديدة\n"
        f"/join - انضمام للعبة\n"
        f"/leave - مغادرة اللعبة\n"
        f"/tasks - تنفيذ مهمة تفاعلية\n"
        f"/status - حالة اللعبة الحالية\n"
        f"/emergency - اجتماع طارئ\n"
        f"/vote - التصويت للطرد\n"
        f"/stats - إحصائياتك\n"
        f"/leaderboard - المتصدرين\n"
        f"/referral - كود الإحالة\n"
        f"/help - المساعدة\n\n"
        f"🎁 نظام الإحالات:\n"
        f"انسخ كود الإحالة خاصتك وشاركه مع أصدقائك\n"
        f"عند استخدامهم للبوت لأول مرة، تكسب 75 نقطة!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎮 ابدأ اللعب", callback_data="start_playing"),
         InlineKeyboardButton("📊 الإحصائيات", callback_data="view_stats")],
        [InlineKeyboardButton("🏆 المتصدرين", callback_data="view_leaderboard"),
         InlineKeyboardButton("🔗 كود الإحالة", callback_data="referral_code")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🎮 دليل اللعب الكامل\n\n"
        "1. بدء اللعبة:\n"
        "- اكتب /new_game في المجموعة\n"
        "- اللعبة تحتاج 4 لاعبين على الأقل\n\n"
        "2. الانضمام:\n"
        "- اكتب /join للانضمام للجولة\n"
        "- الحد الأقصى 10 لاعبين\n\n"
        "3. المهام التفاعلية:\n"
        "- اكتب /tasks لتنفيذ مهمة\n"
        "- اضغط على الأزرار لإكمال المهمة\n"
        "- القاتل: مهامه وهمية وتفشل دائماً\n\n"
        "4. القتل (للقاتل فقط):\n"
        "- اكتب /kill @username في الخاص\n"
        "- تقدر تقتل كل 30 ثانية\n\n"
        "5. التصويت:\n"
        "- عند اكتشاف جثة، يبدأ التصويت تلقائياً\n"
        "- استخدم /emergency لاجتماع طارئ\n\n"
        "6. الفوز:\n"
        "- الطاقم يفوز: عند طرد كل القتلة\n"
        "- القاتل يفوز: عند قتل كل الطاقم\n\n"
        "نظام النقاط:\n"
        "🏆 فوز كطاقم: 100 نقطة\n"
        "🔪 فوز كقاتل: 150 نقطة\n"
        "✅ إكمال مهمة: 15 نقطة\n"
        "🎯 تصويت صحيح: 25 نقطة\n"
        "👥 إحالة صديق: 75 نقطة"
    )
    
    await update.message.reply_text(help_text)

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ هذا الأمر يعمل فقط في المجموعات!")
        return
    
    if chat_id in active_games:
        await update.message.reply_text("⚠️ هناك لعبة جارية بالفعل في هذه المجموعة!")
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
        'tasks_completed': {},
        'votes': {},
        'kill_cooldown': {},
        'emergency_used': False,
        'start_time': datetime.now()
    }
    
    keyboard = [
        [InlineKeyboardButton("🎮 انضم للعبة", callback_data=f"join_{game_id}"),
         InlineKeyboardButton("👀 مشاهدة", callback_data=f"watch_{game_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    game_text = (
        f"🚀 لعبة جديدة قيد الإنشاء!\n\n"
        f"معرف اللعبة: {game_id}\n"
        f"المنشئ: {user.first_name}\n\n"
        f"👥 اكتب /join للانضمام\n"
        f"الحد الأدنى: 4 لاعبين\n"
        f"الحد الأقصى: 10 لاعبين\n\n"
        f"⚠️ اللعبة ستبدأ تلقائياً عند اكتمال العدد!"
    )
    
    await update.message.reply_text(game_text, reply_markup=reply_markup)
    register_group(chat_id, update.effective_chat.title or "مجموعة")

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in active_games:
        await update.message.reply_text("❌ لا توجد لعبة نشطة! اكتب /new_game لبدء واحدة")
        return
    
    game = active_games[chat_id]
    
    if game['status'] != 'waiting':
        await update.message.reply_text("❌ اللعبة بدأت بالفعل!")
        return
    
    if user.id in game['players']:
        await update.message.reply_text("⚠️ أنت منضم بالفعل!")
        return
    
    if len(game['players']) >= 10:
        await update.message.reply_text("❌ اللعبة مكتملة (10 لاعبين كحد أقصى)!")
        return
    
    game['players'][user.id] = {
        'username': user.username or user.first_name,
        'first_name': user.first_name,
        'role': None,
        'alive': True,
        'tasks': 0,
        'total_tasks': 3
    }
    
    get_user(user.id)
    
    player_count = len(game['players'])
    await update.message.reply_text(f"✅ {user.first_name} انضم للعبة! ({player_count}/10)")
    
    if player_count >= 4:
        await update.message.reply_text("🎮 اكتمل العدد! جاري بدء اللعبة...\nسيتم توزيع الأدوار الآن...")
        await start_game(chat_id, context)

async def leave_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def game_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض حالة اللعبة الحالية"""
    chat_id = update.effective_chat.id
    
    if chat_id not in active_games:
        await update.message.reply_text("❌ لا توجد لعبة نشطة!")
        return
    
    game = active_games[chat_id]
    
    status_text = "📊 حالة اللعبة الحالية:\n\n"
    
    for pid, pdata in game['players'].items():
        name = get_player_name(pdata)
        if pdata['alive']:
            status_emoji = "✅"
            status_text += f"{status_emoji} {name} - حي يرزق\n"
        else:
            status_emoji = "💀"
            status_text += f"{status_emoji} {name} - ميت\n"
    
    status_text += f"\n🎮 حالة اللعبة: {game['status']}\n"
    status_text += f"👥 اللاعبين الأحياء: {sum(1 for p in game['players'].values() if p['alive'])}/{len(game['players'])}"
    
    await update.message.reply_text(status_text)

async def emergency_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجتماع طارئ للتشاور"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in active_games:
        await update.message.reply_text("❌ لا توجد لعبة نشطة!")
        return
    
    game = active_games[chat_id]
    
    if game['status'] != 'playing':
        await update.message.reply_text("❌ اللعبة لم تبدأ بعد!")
        return
    
    if user.id not in game['players'] or not game['players'][user.id]['alive']:
        await update.message.reply_text("❌ لا يمكنك استخدام الاجتماع الطارئ!")
        return
    
    if game.get('emergency_used'):
        await update.message.reply_text("❌ تم استخدام الاجتماع الطارئ مسبقاً!")
        return
    
    game['emergency_used'] = True
    game['status'] = 'emergency'
    
    await update.message.reply_text(
        f"🚨 اجتماع طارئ! {user.first_name} طلب اجتماع طارئ!\n\n"
        f"⏰ لديكم 90 ثانية للنقاش...\n"
        f"بعدها سيبدأ التصويت مباشرة!"
    )
    
    await asyncio.sleep(90)
    await start_voting(chat_id, context, from_emergency=True)

async def start_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    game = active_games[chat_id]
    players = list(game['players'].keys())
    impostor_count = get_impostor_count(len(players))
    
    random.shuffle(players)
    impostors = players[:impostor_count]
    crewmates = players[impostor_count:]
    
    for imp_id in impostors:
        game['players'][imp_id]['role'] = 'impostor'
        game['impostors'].append(imp_id)
        
        try:
            imp_text = (
                f"🔪 أنت القاتل!\n\n"
                f"مهمتك: القضاء على كل أفراد الطاقم!\n\n"
                f"🎭 مهامك وهمية (ستفشل دائماً) - لكن اضغط أزرار عشان تتظاهر\n\n"
                f"💀 للقتل: استخدم /kill @username في الخاص\n"
                f"⏰ يمكنك القتل كل 30 ثانية\n\n"
                f"⚠️ كن حذراً: نفذ مهام وهمية لتتظاهر أنك طاقم!"
            )
            await context.bot.send_message(chat_id=imp_id, text=imp_text)
        except:
            pass
    
    for crew_id in crewmates:
        game['players'][crew_id]['role'] = 'crewmate'
        game['alive_crewmates'].append(crew_id)
        
        try:
            crew_text = (
                f"👨‍🚀 أنت فرد طاقم!\n\n"
                f"مهمتك: إكمال المهام التفاعلية واكتشاف القاتل!\n\n"
                f"⚡ استخدم /tasks لتنفيذ مهمة تفاعلية\n"
                f"🔍 راقب اللاعبين لاكتشاف المشتبه بهم\n\n"
                f"🎯 أكمل 3 مهام للفوز مع الطاقم!"
            )
            await context.bot.send_message(chat_id=crew_id, text=crew_text)
        except:
            pass
    
    game['status'] = 'playing'
    game['start_time'] = datetime.now()
    
    game_text = (
        f"🚀 انطلقت اللعبة!\n\n"
        f"👥 عدد اللاعبين: {len(players)}\n"
        f"🔪 عدد القتلة: {impostor_count}\n\n"
        f"⚡ الطاقم: نفذوا مهامكم بـ /tasks\n"
        f"🔪 القاتل: اقتل بهدوء بـ /kill @username في الخاص\n"
        f"🚨 استخدم /emergency لاجتماع طارئ\n"
        f"📊 استخدم /status لمعرفة حالة اللاعبين\n\n"
        f"⚠️ لا تتحدثوا عن أدواركم في المجموعة!"
    )
    
    await context.bot.send_message(chat_id=chat_id, text=game_text)

async def execute_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ مهمة تفاعلية"""
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
        await update.message.reply_text("❌ أنت لست في أي لعبة نشطة!")
        return
    
    if game['status'] != 'playing':
        await update.message.reply_text("❌ اللعبة لم تبدأ بعد!")
        return
    
    player = game['players'][user_id]
    
    if not player['alive']:
        await update.message.reply_text("💀 أنت ميت! لا يمكنك تنفيذ مهام")
        return
    
    if player['tasks'] >= player['total_tasks']:
        await update.message.reply_text("✅ لقد أكملت جميع مهامك!")
        return
    
    if player['role'] == 'crewmate':
        task = random.choice(CREWMATE_TASKS)
        
        keyboard = []
        for row in task['buttons']:
            keyboard.append([InlineKeyboardButton(btn, callback_data=f"task_{group_id}_{user_id}_{btn}") for btn in row])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{task['emoji']} {task['name']}\n\n{task['description']}",
            reply_markup=reply_markup
        )
    
    else:
        task = random.choice(IMPOSTOR_TASKS)
        
        keyboard = []
        for row in task['buttons']:
            keyboard.append([InlineKeyboardButton(btn, callback_data=f"faketask_{group_id}_{user_id}") for btn in row])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{task['emoji']} {task['name']}\n\n{task['description']}",
            reply_markup=reply_markup
        )

async def handle_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغطات أزرار المهام"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    if data.startswith('task_'):
        parts = data.split('_')
        group_id = int(parts[1])
        user_id = int(parts[2])
        answer = '_'.join(parts[3:])
        
        if user.id != user_id:
            await query.answer("❌ هذه المهمة ليست لك!", show_alert=True)
            return
        
        if group_id not in active_games:
            await query.edit_message_text("❌ اللعبة انتهت!")
            return
        
        game = active_games[group_id]
        
        # البحث عن المهمة الصحيحة
        task = None
        for t in CREWMATE_TASKS:
            if t['correct'] == answer:
                task = t
                break
        
        if task:
            await query.edit_message_text(f"{task['emoji']} {task['name']}\n\n{task['success']}")
            game['players'][user_id]['tasks'] += 1
            update_user_points(user_id, 15, task=True)
            
            await context.bot.send_message(
                chat_id=group_id,
                text=f"✅ {game['players'][user_id]['first_name']} أكمل مهمة: {task['emoji']} {task['name']} ({game['players'][user_id]['tasks']}/{game['players'][user_id]['total_tasks']})"
            )
            
            if game['players'][user_id]['tasks'] >= game['players'][user_id]['total_tasks']:
                await context.bot.send_message(chat_id=user_id, text="🎉 لقد أكملت جميع مهامك! أحسنت!")
        else:
            await query.edit_message_text("❌ إجابة خاطئة! حاول مرة أخرى بـ /tasks")
    
    elif data.startswith('faketask_'):
        parts = data.split('_')
        group_id = int(parts[1])
        user_id = int(parts[2])
        
        if user.id != user_id:
            await query.answer("❌ هذه المهمة ليست لك!", show_alert=True)
            return
        
        # مهمة وهمية - تفشل دائماً
        task = random.choice(IMPOSTOR_TASKS)
        await query.edit_message_text(f"{task['emoji']} {task['name']}\n\n{task['failure']}")

async def kill_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text("❌ أنت لست في أي لعبة نشطة!")
        return
    
    player = game['players'][user_id]
    
    if player['role'] != 'impostor':
        await update.message.reply_text("❌ فقط القاتل يمكنه القتل!")
        return
    
    if not player['alive']:
        await update.message.reply_text("💀 أنت ميت!")
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
        await update.message.reply_text("❌ لم يتم العثور على اللاعب أو هو ميت بالفعل!")
        return
    
    scenario = random.choice(KILL_SCENARIOS)
    victim_name = game['players'][victim_id]['first_name']
    
    for msg in scenario['scene']:
        await update.message.reply_text(msg)
        await asyncio.sleep(1)
    
    game['players'][victim_id]['alive'] = False
    game['dead_players'].append(victim_id)
    if victim_id in game['alive_crewmates']:
        game['alive_crewmates'].remove(victim_id)
    
    death_msg = scenario['death_message'].format(victim=victim_name)
    await context.bot.send_message(chat_id=group_id, text=death_msg)
    
    update_user_points(user_id, 30, kill=True)
    
    await update.message.reply_text("✅ تم القتل بنجاح!")
    await start_voting(group_id, context)

async def start_voting(chat_id: int, context: ContextTypes.DEFAULT_TYPE, from_emergency: bool = False):
    game = active_games[chat_id]
    game['status'] = 'voting'
    game['votes'] = {}
    
    alive_players = {pid: p for pid, p in game['players'].items() if p['alive']}
    
    if from_emergency:
        vote_text = "🚨 انتهى وقت النقاش! جولة تصويت!\n\nصوتوا لطرد المشتبه به:\n\n"
    else:
        vote_text = "🗳️ جولة تصويت!\n\nتم اكتشاف جثة! صوتوا لطرد المشتبه به:\n\n"
    
    keyboard = []
    for pid, pdata in alive_players.items():
        name = get_player_name(pdata)
        vote_text += f"• {name} (@{pdata['username']})\n"
        keyboard.append([InlineKeyboardButton(
            f"🗳️ {name}", 
            callback_data=f"vote_{chat_id}_{pid}"
        )])
    
    keyboard.append([InlineKeyboardButton("⏭️ تخطي التصويت", callback_data=f"vote_{chat_id}_skip")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=vote_text + "\n⏰ لديكم 60 ثانية للتصويت!",
        reply_markup=reply_markup
    )
    
    await asyncio.sleep(60)
    await end_voting(chat_id, context)

async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🗳️ استخدم أزرار التصويت في رسالة التصويت!")

async def handle_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    data = query.data
    
    if not data.startswith('vote_'):
        return
    
    parts = data.split('_')
    group_id = int(parts[1])
    vote_target = parts[2]
    
    if group_id not in active_games:
        await query.edit_message_text("❌ اللعبة انتهت!")
        return
    
    game = active_games[group_id]
    
    if user.id not in game['players'] or not game['players'][user.id]['alive']:
        await query.answer("❌ لا يمكنك التصويت!", show_alert=True)
        return
    
    game['votes'][user.id] = vote_target
    
    if vote_target == 'skip':
        await query.answer("⏭️ تم تخطي التصويت!")
    else:
        target_name = get_player_name(game['players'][int(vote_target)])
        await query.answer(f"🗳️ صوتت لطرد {target_name}")

async def end_voting(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    vote_count = {}
    for voter_id, target_id in game['votes'].items():
        if target_id != 'skip':
            if target_id not in vote_count:
                vote_count[target_id] = 0
            vote_count[target_id] += 1
    
    if not vote_count:
        await context.bot.send_message(chat_id=chat_id, text="⏭️ تم تخطي التصويت!")
        game['status'] = 'playing'
        return
    
    most_voted = max(vote_count, key=vote_count.get)
    max_votes = vote_count[most_voted]
    
    tie_players = [pid for pid, votes in vote_count.items() if votes == max_votes]
    
    if len(tie_players) > 1:
        await context.bot.send_message(chat_id=chat_id, text="⚖️ تعادل في الأصوات! لا أحد يُطرد")
        game['status'] = 'playing'
        return
    
    player_id = int(most_voted)
    player_data = game['players'][player_id]
    player_name = get_player_name(player_data)
    
    game['players'][player_id]['alive'] = False
    
    if player_data['role'] == 'impostor':
        game['impostors'].remove(player_id)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🎉 تم طرد القاتل!\n\n"
                f"🔪 {player_name} كان القاتل!\n\n"
                f"✅ تم طرده من السفينة"
            )
        )
        
        update_user_points(player_id, 0, won=False, role='impostor')
        
        if len(game['impostors']) == 0:
            await end_game(chat_id, context, 'crewmate')
            return
    
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"😢 تم طرد بريء!\n\n"
                f"👨‍🚀 {player_name} كان فرد طاقم!\n\n"
                f"💔 الطاقم خسر عضواً"
            )
        )
        
        update_user_points(player_id, 0, won=False, role='crewmate')
        if player_id in game['alive_crewmates']:
            game['alive_crewmates'].remove(player_id)
    
    if len(game['impostors']) >= len(game['alive_crewmates']):
        await end_game(chat_id, context, 'impostor')
        return
    
    game['status'] = 'playing'
    game['votes'] = {}

async def end_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE, winner: str):
    game = active_games[chat_id]
    game['status'] = 'ended'
    
    if winner == 'crewmate':
        win_text = "🎉 الطاقم يفوز! تم اكتشاف كل القتلة!"
        win_points = 100
        
        for pid in game['alive_crewmates']:
            update_user_points(pid, win_points, won=True, role='crewmate')
        
        for imp_id in game['impostors']:
            update_user_points(imp_id, 0, won=False, role='impostor')
    
    else:
        win_text = "🔪 القاتل يفوز! تم القضاء على الطاقم!"
        win_points = 150
        
        for imp_id in game['impostors']:
            update_user_points(imp_id, win_points, won=True, role='impostor')
        
        for pid in game['players']:
            if pid not in game['impostors']:
                update_user_points(pid, 0, won=False, role='crewmate')
    
    duration = datetime.now() - game['start_time']
    result_text = (
        f"{win_text}\n\n"
        f"🏆 نهاية الجولة!\n\n"
        f"📊 الإحصائيات:\n"
        f"• المدة: {duration}\n"
        f"• القتلة: {len(game['impostors'])}\n"
        f"• الطاقم: {len(game['players']) - len(game['impostors'])}\n\n"
        f"🎮 اكتب /new_game لجولة جديدة!"
    )
    
    await context.bot.send_message(chat_id=chat_id, text=result_text)
    
    roles_text = "👤 الأدوار:\n\n"
    for pid, pdata in game['players'].items():
        role_emoji = "🔪" if pdata['role'] == 'impostor' else "👨‍🚀"
        alive_status = "💀 ميت" if not pdata['alive'] else "✅ حي"
        name = get_player_name(pdata)
        roles_text += f"{role_emoji} {name} - {alive_status}\n"
    
    await context.bot.send_message(chat_id=chat_id, text=roles_text)
    
    del active_games[chat_id]

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_user(user.id)
    
    win_rate = (db_user['games_won'] / db_user['games_played'] * 100) if db_user['games_played'] > 0 else 0
    name = db_user['first_name'] or db_user['username'] or 'لاعب'
    
    stats_text = (
        f"📊 إحصائيات {name}\n\n"
        f"🏆 النقاط: {db_user['points']}\n"
        f"🎮 عدد الجولات: {db_user['games_played']}\n"
        f"✅ مرات الفوز: {db_user['games_won']}\n\n"
        f"👨‍🚀 فوز كطاقم: {db_user['crewmate_wins']}\n"
        f"🔪 فوز كقاتل: {db_user['impostor_wins']}\n\n"
        f"💀 عدد القتلى: {db_user['total_kills']}\n"
        f"⚡ المهام المكتملة: {db_user['total_tasks']}\n\n"
        f"📈 نسبة الفوز: {win_rate:.1f}%"
    )
    
    await update.message.reply_text(stats_text)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leaders = get_leaderboard()
    
    if not leaders:
        await update.message.reply_text("🏆 لا يوجد متصدرين بعد!")
        return
    
    lb_text = "🏆 قائمة المتصدرين\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, player in enumerate(leaders[:10]):
        medal = medals[i] if i < 3 else f"{i+1}."
        # استخدام الاسم الأول أو اليوزرنيم
        name = player['first_name'] or player['username'] or f"لاعب {player['user_id']}"
        lb_text += f"{medal} {name}: {player['points']} نقطة | {player['games_won']} فوز\n"
    
    await update.message.reply_text(lb_text)

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_user(user.id)
    
    ref_text = (
        f"🔗 كود الإحالة الخاص بك\n\n"
        f"{db_user['referral_code']}\n\n"
        f"📢 شارك هذا الكود مع أصدقائك!\n"
        f"عند استخدامهم للبوت، اربح 75 نقطة لكل صديق!\n\n"
        f"🎁 للاستفادة من كود صديق:\n"
        f"اكتب /referral كود_الصديق"
    )
    
    await update.message.reply_text(ref_text)

async def handle_referral_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("❌ استخدم: /referral كود_الإحالة")
        return
    
    ref_code = context.args[0]
    
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cursor.execute('SELECT * FROM users WHERE referral_code = %s', (ref_code,))
    referrer = cursor.fetchone()
    
    if not referrer:
        cursor.close()
        conn.close()
        await update.message.reply_text("❌ كود إحالة غير صالح!")
        return
    
    if referrer['user_id'] == user.id:
        cursor.close()
        conn.close()
        await update.message.reply_text("❌ لا يمكنك استخدام كودك الخاص!")
        return
    
    cursor.execute('SELECT * FROM users WHERE user_id = %s', (user.id,))
    current_user = cursor.fetchone()
    
    if current_user['referred_by']:
        cursor.close()
        conn.close()
        await update.message.reply_text("❌ لقد استخدمت كود إحالة من قبل!")
        return
    
    cursor.execute('UPDATE users SET referred_by = %s WHERE user_id = %s', 
                   (referrer['user_id'], user.id))
    cursor.execute('UPDATE users SET points = points + 75 WHERE user_id = %s', 
                   (referrer['user_id'],))
    cursor.execute('UPDATE users SET points = points + 25 WHERE user_id = %s', 
                   (user.id,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    referrer_name = referrer['first_name'] or referrer['username'] or 'صديقك'
    
    await update.message.reply_text(
        f"🎉 تم تفعيل كود الإحالة!\n"
        f"ربحت 25 نقطة، و{referrer_name} ربح 75 نقطة!"
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('task_') or data.startswith('faketask_'):
        await handle_task_callback(update, context)
    elif data.startswith('vote_'):
        await handle_vote_callback(update, context)
    elif data == "start_playing":
        await query.message.reply_text(
            "🎮 أضفني لمجموعتك وارفعني مشرف وابدأ اللعب!\n"
            "اكتب /new_game في المجموعة لبدء جولة"
        )
    elif data == "view_stats":
        user = query.from_user
        db_user = get_user(user.id)
        await query.message.reply_text(
            f"📊 نقاطك: {db_user['points']}\n"
            f"🎮 جولاتك: {db_user['games_played']}\n"
            f"✅ فوزك: {db_user['games_won']}"
        )
    elif data == "view_leaderboard":
        leaders = get_leaderboard()
        text = "🏆 المتصدرين:\n"
        for i, p in enumerate(leaders[:5], 1):
            name = p['first_name'] or p['username'] or f"لاعب {p['user_id']}"
            text += f"{i}. {name}: {p['points']} نقطة\n"
        await query.message.reply_text(text)
    elif data == "referral_code":
        user = query.from_user
        db_user = get_user(user.id)
        await query.message.reply_text(
            f"🔗 كود الإحالة: {db_user['referral_code']}\n"
            "شاركه مع أصدقائك لتربح 75 نقطة!"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ حدث خطأ ما! جرب مرة أخرى"
            )
    except:
        pass

# ====== بدء البوت ======
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("new_game", new_game))
    app.add_handler(CommandHandler("join", join_game))
    app.add_handler(CommandHandler("leave", leave_game))
    app.add_handler(CommandHandler("tasks", execute_task))
    app.add_handler(CommandHandler("status", game_status))
    app.add_handler(CommandHandler("emergency", emergency_meeting))
    app.add_handler(CommandHandler("kill", kill_player))
    app.add_handler(CommandHandler("vote", vote_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("referral", handle_referral_code))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_error_handler(error_handler)
    
    logger.info("🤖 بوت Among Us يعمل الآن!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    init_db()
    main()
