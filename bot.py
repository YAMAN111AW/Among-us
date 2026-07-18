import os
import asyncio
import random
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncpg
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
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/amongus")

# ====== ثوابت اللعبة ======
CREWMATE_TASKS = [
    {
        "name": "إصلاح الأسلاك",
        "emoji": "🔌",
        "messages": [
            "⚡ الأسلاك متشابكة.. بتحاول تصلحها",
            "🔧 لقيت السلك الأزرق مقطوع!",
            "💡 وصلت الكهرباء أخيراً",
            "✨ الأسلاك اتصدعت.. بتجرب توصيلها من جديد",
            "🛠️ بتفك الأسلاك وتربطها صح"
        ],
        "success": "✅ تم إصلاح الأسلاك بنجاح! الأضواء رجعت تشتغل 🎉"
    },
    {
        "name": "مسح بطاقة الدخول",
        "emoji": "💳",
        "messages": [
            "🔄 بتمرر البطاقة... مرة تانية",
            "⚠️ البطاقة مش مقروءة! جرب بسرعة أقل",
            "🔍 بيقرأ البيانات... 45%",
            "💢 الجهاز طلب كلمة سر قديمة!",
            "📡 بيحاول يتواصل مع السيرفر المركزي"
        ],
        "success": "✅ تم مسح البطاقة! الباب اتفتح 🔓"
    },
    {
        "name": "تفريغ القمامة",
        "emoji": "🗑️",
        "messages": [
            "♻️ القمامة مليانة.. بتسحب الكيس",
            "🤢 ريحة غريبة طالعة من الكيس!",
            "🦠 بتشوف عفن عالكيس.. بتلبس قفازات",
            "📦 بتربط الكيس وتحطه عند المخرج",
            "🧹 بتنضف المكان بعد ما شلت القمامة"
        ],
        "success": "✅ تم تفريغ القمامة! المكان أنضف 💫"
    },
    {
        "name": "تحميل البيانات",
        "emoji": "📤",
        "messages": [
            "📡 بيحمل البيانات للسحابة... 20%",
            "🐌 النت بطيء! بيحول يغير السيرفر",
            "⚡ السرعة اتحسنت! 67%",
            "🔐 بيشفر الملفات قبل الرفع",
            "📊 بيضغط البيانات عشان تخلص بسرعة"
        ],
        "success": "✅ تم تحميل البيانات! المهمة خلصت 💾"
    }
]

IMPOSTOR_TASKS = [
    {
        "name": "تخريب المفاعل",
        "emoji": "☢️",
        "messages": [
            "💢 المفاعل سخن أوي! مش قادر تلمسه",
            "⚠️ إنذار حريق اشتغل فجأة!",
            "🔥 دخان طالع من الماكينة!",
            "⚡ صعقة كهربا ضربتك!",
            "🚨 كل الأضواء الحمرا اشتغلت!"
        ],
        "failure": "❌ فشل التخريب! المفاعل أمان زيادة عن اللزوم 💥"
    },
    {
        "name": "قطع الأكسجين",
        "emoji": "🫁",
        "messages": [
            "🌀 صمام الأكسجين متجمد!",
            "💨 الهوا بيهرب من فتحة تانية!",
            "🔧 المفتاح اتكسر جوا القفل!",
            "😤 الضغط عالي ومش قادر تتحكم فيه",
            "🆘 نظام الطوارئ اشتغل لوحده!"
        ],
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
active_games = {}  # {group_id: game_data}
user_sessions = {}  # {user_id: group_id}

# ====== دوال قاعدة البيانات ======
async def init_db():
    """تهيئة قاعدة البيانات"""
    conn = await asyncpg.connect(DATABASE_URL)
    
    await conn.execute('''
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
    
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            group_id BIGINT PRIMARY KEY,
            title VARCHAR(255),
            active_game BOOLEAN DEFAULT FALSE,
            total_games INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    
    await conn.close()
    logger.info("✅ تم تهيئة قاعدة البيانات")

async def get_user(user_id: int):
    """جلب بيانات المستخدم"""
    conn = await asyncpg.connect(DATABASE_URL)
    user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
    
    if not user:
        # إنشاء مستخدم جديد مع كود إحالة
        referral_code = str(uuid.uuid4())[:8]
        user = await conn.fetchrow(
            'INSERT INTO users (user_id, referral_code) VALUES ($1, $2) RETURNING *',
            user_id, referral_code
        )
    
    await conn.close()
    return user

async def update_user_points(user_id: int, points: int, won: bool = False, 
                            role: str = None, kill: bool = False, task: bool = False):
    """تحديث نقاط وإحصائيات المستخدم"""
    conn = await asyncpg.connect(DATABASE_URL)
    
    update_query = '''
        UPDATE users SET 
            points = points + $1,
            games_played = games_played + 1
    '''
    params = [points, user_id]
    
    if won:
        update_query += ', games_won = games_won + 1'
        if role == 'crewmate':
            update_query += ', crewmate_wins = crewmate_wins + 1'
        elif role == 'impostor':
            update_query += ', impostor_wins = impostor_wins + 1'
    
    if kill:
        update_query += ', total_kills = total_kills + 1'
    
    if task:
        update_query += ', total_tasks = total_tasks + 1'
    
    update_query += ' WHERE user_id = $' + str(len(params))
    
    await conn.execute(update_query, *params)
    await conn.close()

async def get_leaderboard():
    """جلب قائمة المتصدرين"""
    conn = await asyncpg.connect(DATABASE_URL)
    leaders = await conn.fetch(
        'SELECT user_id, username, first_name, points, games_won FROM users ORDER BY points DESC LIMIT 10'
    )
    await conn.close()
    return leaders

async def register_group(group_id: int, title: str):
    """تسجيل مجموعة جديدة"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        'INSERT INTO groups (group_id, title) VALUES ($1, $2) ON CONFLICT (group_id) DO UPDATE SET title = $2',
        group_id, title
    )
    await conn.close()

# ====== دوال مساعدة ======
def generate_game_key() -> str:
    """توليد مفتاح لعبة فريد"""
    return str(uuid.uuid4())[:6]

def get_impostor_count(player_count: int) -> int:
    """تحديد عدد القتلة حسب عدد اللاعبين"""
    if player_count <= 5:
        return 1
    elif player_count <= 8:
        return 2
    else:
        return 3

async def send_delayed_message(context: ContextTypes.DEFAULT_TYPE, 
                              chat_id: int, text: str, delay: float):
    """إرسال رسالة متأخرة"""
    await asyncio.sleep(delay)
    await context.bot.send_message(chat_id=chat_id, text=text)

# ====== معالجات الأوامر ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البدء"""
    user = update.effective_user
    await get_user(user.id)
    
    welcome_text = f"""
🎮 *مرحباً {user.first_name}!*

أنا بوت *Among Us* في تليجرام!
العب مع أصدقائك في المجموعات واكتشف القاتل!

👥 *طريقة اللعب:*
1. أضفني لمجموعتك
2. اكتب `/new_game` لبدء جولة
3. استخدم `/join` للانضمام
4. نفذ المهام بـ `/tasks`
5. صوت لطرد المشتبه بـ `/vote`

🏆 *الأوامر الرئيسية:*
/start - البدء
/new_game - إنشاء لعبة جديدة
/join - انضمام للعبة
/leave - مغادرة اللعبة
/tasks - تنفيذ مهمة
/vote - التصويت للطرد
/stats - إحصائياتك
/leaderboard - المتصدرين
/referral - كود الإحالة الخاص بك
/help - المساعدة

🎁 *نظام الإحالات:*
انسخ كود الإحالة خاصتك وشاركه مع أصدقائك
عند استخدامهم للبوت لأول مرة، تكسب 75 نقطة!
    """
    
    keyboard = [
        [InlineKeyboardButton("🎮 ابدأ اللعب", callback_data="start_playing"),
         InlineKeyboardButton("📊 الإحصائيات", callback_data="view_stats")],
        [InlineKeyboardButton("🏆 المتصدرين", callback_data="view_leaderboard"),
         InlineKeyboardButton("🔗 كود الإحالة", callback_data="referral_code")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المساعدة"""
    help_text = """
🎮 *دليل اللعب الكامل*

*1. بدء اللعبة:*
- اكتب `/new_game` في المجموعة
- اللعبة تحتاج 4 لاعبين على الأقل

*2. الانضمام:*
- اكتب `/join` للانضمام للجولة
- الحد الأقصى 10 لاعبين

*3. المهام:*
- أفراد الطاقم: استخدم `/tasks` لتنفيذ المهام
- القاتل: مهامه وهمية وتفشل دائماً

*4. القتل (للقاتل فقط):*
- اكتب `/kill @username` في الخاص
- تقدر تقتل كل 30 ثانية

*5. التصويت:*
- عند اكتشاف جثة، يبدأ التصويت تلقائياً
- استخدم `/vote @username` للتصويت

*6. الفوز:*
- الطاقم يفوز: عند طرد كل القتلة
- القاتل يفوز: عند قتل كل الطاقم

*نظام النقاط:*
🏆 فوز كطاقم: 100 نقطة
🔪 فوز كقاتل: 150 نقطة
✅ إكمال مهمة: 15 نقطة
🎯 تصويت صحيح: 25 نقطة
👥 إحالة صديق: 75 نقطة
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء لعبة جديدة"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # التحقق من نوع المحادثة
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ هذا الأمر يعمل فقط في المجموعات!")
        return
    
    # التحقق من عدم وجود لعبة نشطة
    if chat_id in active_games:
        await update.message.reply_text("⚠️ هناك لعبة جارية بالفعل في هذه المجموعة!")
        return
    
    # إنشاء لعبة جديدة
    game_id = generate_game_key()
    active_games[chat_id] = {
        'id': game_id,
        'creator': user.id,
        'players': {},
        'status': 'waiting',  # waiting, playing, voting, ended
        'impostors': [],
        'alive_crewmates': [],
        'dead_players': [],
        'tasks_completed': {},
        'votes': {},
        'kill_cooldown': {},
        'start_time': datetime.now()
    }
    
    keyboard = [
        [InlineKeyboardButton("🎮 انضم للعبة", callback_data=f"join_{game_id}"),
         InlineKeyboardButton("👀 مشاهدة", callback_data=f"watch_{game_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"""
🚀 *لعبة جديدة قيد الإنشاء!*

معرف اللعبة: `{game_id}`
المنشئ: {user.first_name}

👥 اكتب `/join` للانضمام
الحد الأدنى: 4 لاعبين
الحد الأقصى: 10 لاعبين

⚠️ اللعبة ستبدأ تلقائياً عند اكتمال العدد!
        """,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    await register_group(chat_id, update.effective_chat.title or "مجموعة")

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الانضمام للعبة"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in active_games:
        await update.message.reply_text("❌ لا توجد لعبة نشطة! اكتب `/new_game` لبدء واحدة")
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
    
    # إضافة اللاعب
    game['players'][user.id] = {
        'username': user.username or user.first_name,
        'first_name': user.first_name,
        'role': None,
        'alive': True,
        'tasks': 0,
        'total_tasks': 3
    }
    
    # تسجيل المستخدم
    await get_user(user.id)
    
    player_count = len(game['players'])
    await update.message.reply_text(
        f"✅ {user.first_name} انضم للعبة! ({player_count}/10)"
    )
    
    # بدء اللعبة تلقائياً عند اكتمال 4 لاعبين
    if player_count >= 4:
        await update.message.reply_text(
            "🎮 اكتمل العدد! جاري بدء اللعبة...\n"
            "سيتم توزيع الأدوار الآن..."
        )
        await start_game(chat_id, context)

async def leave_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مغادرة اللعبة"""
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

async def start_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """بدء اللعبة وتوزيع الأدوار"""
    game = active_games[chat_id]
    players = list(game['players'].keys())
    impostor_count = get_impostor_count(len(players))
    
    # توزيع الأدوار عشوائياً
    random.shuffle(players)
    impostors = players[:impostor_count]
    crewmates = players[impostor_count:]
    
    # تعيين الأدوار
    for imp_id in impostors:
        game['players'][imp_id]['role'] = 'impostor'
        game['impostors'].append(imp_id)
        
        # إرسال دور القاتل بالخاص
        try:
            imp_tasks_list = "\n".join([f"{t['emoji']} {t['name']}" for t in IMPOSTOR_TASKS])
            await context.bot.send_message(
                chat_id=imp_id,
                text=f"""
🔪 *أنت القاتل!*

مهمتك: القضاء على كل أفراد الطاقم!

🎭 *مهامك الوهمية (ستفشل دائماً):*
{imp_tasks_list}

💀 *للقتل:* استخدم `/kill @username`
⏰ يمكنك القتل كل 30 ثانية

⚠️ *كن حذراً:* نفذ مهام وهمية لتتظاهر أنك طاقم!
                """,
                parse_mode='Markdown'
            )
        except:
            pass
    
    for crew_id in crewmates:
        game['players'][crew_id]['role'] = 'crewmate'
        game['alive_crewmates'].append(crew_id)
        
        # إرسال دور الطاقم بالخاص
        try:
            crew_tasks_list = "\n".join([f"{t['emoji']} {t['name']}" for t in CREWMATE_TASKS])
            await context.bot.send_message(
                chat_id=crew_id,
                text=f"""
👨‍🚀 *أنت فرد طاقم!*

مهمتك: إكمال المهام واكتشاف القاتل!

✅ *مهامك:*
{crew_tasks_list}

⚡ استخدم `/tasks` لتنفيذ المهام
🔍 راقب اللاعبين لاكتشاف المشتبه بهم

🎯 أكمل {3} مهام للفوز مع الطاقم!
                """,
                parse_mode='Markdown'
            )
        except:
            pass
    
    game['status'] = 'playing'
    game['start_time'] = datetime.now()
    
    # إعلان بدء اللعبة في المجموعة
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"""
🚀 *انطلقت اللعبة!*

👥 عدد اللاعبين: {len(players)}
🔪 عدد القتلة: {impostor_count}

⚡ *الطاقم:* نفذوا مهامكم بـ `/tasks`
🔪 *القاتل:* اقتل بهدوء بـ `/kill @username`

🎭 تذكروا: القاتل يتظاهر بتنفيذ المهام لكنها تفشل دائماً!

⚠️ لا تتحدثوا عن أدواركم في المجموعة!
        """,
        parse_mode='Markdown'
    )

async def execute_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ مهمة"""
    user = update.effective_user
    user_id = user.id
    
    # معرفة مجموعة اللاعب
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
    
    # تنفيذ المهمة حسب الدور
    if player['role'] == 'crewmate':
        # مهمة حقيقية تنجح
        task = random.choice(CREWMATE_TASKS)
        message = random.choice(task['messages'])
        
        await update.message.reply_text(f"{task['emoji']} *{task['name']}*\n\n{message}", parse_mode='Markdown')
        await asyncio.sleep(2)
        await update.message.reply_text(task['success'])
        
        player['tasks'] += 1
        await update_user_points(user_id, 15, task=True)
        
        # إرسال تحديث للمجموعة
        await context.bot.send_message(
            chat_id=group_id,
            text=f"✅ {player['first_name']} أكمل مهمة: {task['emoji']} {task['name']} ({player['tasks']}/{player['total_tasks']})"
        )
        
        # التحقق من إكمال جميع المهام
        if player['tasks'] >= player['total_tasks']:
            await update.message.reply_text("🎉 لقد أكملت جميع مهامك! أحسنت!")
            
            # التحقق من فوز الطاقم (إذا أكملوا جميعاً)
            all_crew_done = all(
                game['players'][pid]['tasks'] >= game['players'][pid]['total_tasks']
                for pid in game['alive_crewmates']
            )
            if all_crew_done:
                await end_game(group_id, context, 'crewmate')
    
    else:
        # مهمة وهمية تفشل دائماً
        task = random.choice(IMPOSTOR_TASKS)
        message = random.choice(task['messages'])
        
        await update.message.reply_text(f"{task['emoji']} *{task['name']}*\n\n{message}", parse_mode='Markdown')
        await asyncio.sleep(2)
        await update.message.reply_text(task['failure'])
        
        # إرسال تحديث للمجموعة (يبدو كأنه مهمة حقيقية)
        await context.bot.send_message(
            chat_id=group_id,
            text=f"🔄 {player['first_name']} يحاول تنفيذ مهمة: {task['emoji']} {task['name']}"
        )

async def kill_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """القاتل يقتل لاعباً"""
    user = update.effective_user
    user_id = user.id
    
    # يجب أن يكون في الخاص
    if update.effective_chat.type != 'private':
        await update.message.reply_text("❌ استخدم هذا الأمر في الخاص فقط!")
        return
    
    # البحث عن لعبة اللاعب
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
    
    # التحقق من وجود ضحية
    if not context.args:
        await update.message.reply_text("❌ استخدم: `/kill @username`")
        return
    
    victim_username = context.args[0].replace('@', '')
    
    # البحث عن الضحية
    victim_id = None
    for pid, pdata in game['players'].items():
        if pdata['username'] == victim_username and pdata['alive'] and pid != user_id:
            victim_id = pid
            break
    
    if not victim_id:
        await update.message.reply_text("❌ لم يتم العثور على اللاعب أو هو ميت بالفعل!")
        return
    
    # تنفيذ القتل
    scenario = random.choice(KILL_SCENARIOS)
    victim_name = game['players'][victim_id]['first_name']
    
    for msg in scenario['scene']:
        await update.message.reply_text(msg)
        await asyncio.sleep(1)
    
    # قتل الضحية
    game['players'][victim_id]['alive'] = False
    game['dead_players'].append(victim_id)
    if victim_id in game['alive_crewmates']:
        game['alive_crewmates'].remove(victim_id)
    
    # إرسال للمجموعة
    death_msg = scenario['death_message'].format(victim=victim_name)
    await context.bot.send_message(chat_id=group_id, text=death_msg)
    
    # تحديث نقاط القاتل
    await update_user_points(user_id, 30, kill=True)
    
    # بدء التصويت
    await update.message.reply_text("✅ تم القتل بنجاح!")
    await start_voting(group_id, context)

async def start_voting(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """بدء جولة تصويت"""
    game = active_games[chat_id]
    game['status'] = 'voting'
    game['votes'] = {}
    
    alive_players = {pid: p for pid, p in game['players'].items() if p['alive']}
    
    vote_text = "🗳️ *جولة تصويت!*\n\nصوتوا لطرد المشتبه به:\n\n"
    
    keyboard = []
    for pid, pdata in alive_players.items():
        vote_text += f"• {pdata['first_name']} (@{pdata['username']})\n"
        keyboard.append([InlineKeyboardButton(
            f"🗳️ {pdata['first_name']}", 
            callback_data=f"vote_{chat_id}_{pid}"
        )])
    
    keyboard.append([InlineKeyboardButton("⏭️ تخطي التصويت", callback_data=f"vote_{chat_id}_skip")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=vote_text + "\n⏰ لديكم 45 ثانية للتصويت!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    # إنهاء التصويت بعد 45 ثانية
    await asyncio.sleep(45)
    await end_voting(chat_id, context)

async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التصويت عبر الأمر"""
    # هذا الأمر تم استبداله بالأزرار
    await update.message.reply_text("🗳️ استخدم أزرار التصويت في رسالة التصويت!")

async def handle_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة التصويت عبر الأزرار"""
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
        target_name = game['players'][int(vote_target)]['first_name']
        await query.answer(f"🗳️ صوتت لطرد {target_name}")

async def end_voting(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """إنهاء التصويت وطرد اللاعب"""
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    # عد الأصوات
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
    
    # اللاعب الأكثر تصويتاً
    most_voted = max(vote_count, key=vote_count.get)
    max_votes = vote_count[most_voted]
    
    # التحقق من التعادل
    tie_players = [pid for pid, votes in vote_count.items() if votes == max_votes]
    
    if len(tie_players) > 1:
        await context.bot.send_message(chat_id=chat_id, text="⚖️ تعادل في الأصوات! لا أحد يُطرد")
        game['status'] = 'playing'
        return
    
    # طرد اللاعب
    player_id = int(most_voted)
    player_data = game['players'][player_id]
    player_name = player_data['first_name']
    
    game['players'][player_id]['alive'] = False
    
    if player_data['role'] == 'impostor':
        game['impostors'].remove(player_id)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""
🎉 *تم طرد القاتل!*

🔪 {player_name} كان القاتل!

✅ تم طرده من السفينة
            """,
            parse_mode='Markdown'
        )
        
        await update_user_points(player_id, 0, won=False, role='impostor')
        
        # التحقق من فوز الطاقم
        if len(game['impostors']) == 0:
            await end_game(chat_id, context, 'crewmate')
            return
    
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""
😢 *تم طرد بريء!*

👨‍🚀 {player_name} كان فرد طاقم!

💔 الطاقم خسر عضواً
            """,
            parse_mode='Markdown'
        )
        
        await update_user_points(player_id, 0, won=False, role='crewmate')
        if player_id in game['alive_crewmates']:
            game['alive_crewmates'].remove(player_id)
    
    # التحقق من فوز القتلة
    if len(game['impostors']) >= len(game['alive_crewmates']):
        await end_game(chat_id, context, 'impostor')
        return
    
    game['status'] = 'playing'
    game['votes'] = {}

async def end_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE, winner: str):
    """إنهاء اللعبة"""
    game = active_games[chat_id]
    game['status'] = 'ended'
    
    if winner == 'crewmate':
        win_text = "🎉 *الطاقم يفوز!* تم اكتشاف كل القتلة!"
        win_points = 100
        
        # نقاط للطاقم الفائز
        for pid in game['alive_crewmates']:
            await update_user_points(pid, win_points, won=True, role='crewmate')
        
        # نقاط أقل للقتلة
        for imp_id in game['impostors']:
            await update_user_points(imp_id, 0, won=False, role='impostor')
    
    else:
        win_text = "🔪 *القاتل يفوز!* تم القضاء على الطاقم!"
        win_points = 150
        
        # نقاط للقتلة
        for imp_id in game['impostors']:
            await update_user_points(imp_id, win_points, won=True, role='impostor')
        
        # نقاط أقل للطاقم الميت
        for pid in game['players']:
            if pid not in game['impostors']:
                await update_user_points(pid, 0, won=False, role='crewmate')
    
    # إعلان النتيجة
    result_text = f"""
{win_text}

🏆 *نهاية الجولة!*

📊 *الإحصائيات:*
• المدة: {datetime.now() - game['start_time']}
• القتلة: {len(game['impostors'])}
• الطاقم: {len(game['players']) - len(game['impostors'])}

🎮 اكتب `/new_game` لجولة جديدة!
    """
    
    await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode='Markdown')
    
    # إظهار أدوار الجميع
    roles_text = "👤 *الأدوار:*\n\n"
    for pid, pdata in game['players'].items():
        role_emoji = "🔪" if pdata['role'] == 'impostor' else "👨‍🚀"
        alive_status = "💀 ميت" if not pdata['alive'] else "✅ حي"
        roles_text += f"{role_emoji} {pdata['first_name']} - {alive_status}\n"
    
    await context.bot.send_message(chat_id=chat_id, text=roles_text, parse_mode='Markdown')
    
    # حذف اللعبة
    del active_games[chat_id]

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات المستخدم"""
    user = update.effective_user
    db_user = await get_user(user.id)
    
    stats_text = f"""
📊 *إحصائيات {db_user['first_name'] or 'لاعب'}*

🏆 النقاط: {db_user['points']}
🎮 عدد الجولات: {db_user['games_played']}
✅ مرات الفوز: {db_user['games_won']}

👨‍🚀 فوز كطاقم: {db_user['crewmate_wins']}
🔪 فوز كقاتل: {db_user['impostor_wins']}

💀 عدد القتلى: {db_user['total_kills']}
⚡ المهام المكتملة: {db_user['total_tasks']}

📈 نسبة الفوز: {(db_user['games_won'] / db_user['games_played'] * 100) if db_user['games_played'] > 0 else 0:.1f}%
    """
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المتصدرين"""
    leaders = await get_leaderboard()
    
    if not leaders:
        await update.message.reply_text("🏆 لا يوجد متصدرين بعد!")
        return
    
    lb_text = "🏆 *قائمة المتصدرين*\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, player in enumerate(leaders[:10]):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = player['first_name'] or player['username'] or str(player['user_id'])
        lb_text += f"{medal} {name}: {player['points']} نقطة | {player['games_won']} فوز\n"
    
    await update.message.reply_text(lb_text, parse_mode='Markdown')

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض كود الإحالة"""
    user = update.effective_user
    db_user = await get_user(user.id)
    
    ref_text = f"""
🔗 *كود الإحالة الخاص بك*

`{db_user['referral_code']}`

📢 شارك هذا الكود مع أصدقائك!
عند استخدامهم للبوت، اربح 75 نقطة لكل صديق!

🎁 للاستفادة من كود صديق:
اكتب `/referral كود_الصديق`
    """
    
    await update.message.reply_text(ref_text, parse_mode='Markdown')

async def handle_referral_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استخدام كود إحالة"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("❌ استخدم: `/referral كود_الإحالة`")
        return
    
    ref_code = context.args[0]
    
    conn = await asyncpg.connect(DATABASE_URL)
    referrer = await conn.fetchrow('SELECT * FROM users WHERE referral_code = $1', ref_code)
    
    if not referrer:
        await conn.close()
        await update.message.reply_text("❌ كود إحالة غير صالح!")
        return
    
    if referrer['user_id'] == user.id:
        await conn.close()
        await update.message.reply_text("❌ لا يمكنك استخدام كودك الخاص!")
        return
    
    # التحقق من عدم استخدام إحالة سابقة
    current_user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user.id)
    if current_user['referred_by']:
        await conn.close()
        await update.message.reply_text("❌ لقد استخدمت كود إحالة من قبل!")
        return
    
    # تطبيق الإحالة
    await conn.execute('UPDATE users SET referred_by = $1 WHERE user_id = $2', 
                      referrer['user_id'], user.id)
    await conn.execute('UPDATE users SET points = points + 75 WHERE user_id = $1', 
                      referrer['user_id'])
    await conn.execute('UPDATE users SET points = points + 25 WHERE user_id = $1', 
                      user.id)
    
    await conn.close()
    
    await update.message.reply_text(
        f"🎉 تم تفعيل كود الإحالة!\n"
        f"ربحت 25 نقطة، و{referrer['first_name'] or 'صديقك'} ربح 75 نقطة!"
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأزرار العامة"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('vote_'):
        await handle_vote_callback(update, context)
    elif data == "start_playing":
        await query.message.reply_text(
            "🎮 أضفني لمجموعتك وابدأ اللعب!\n"
            "اكتب `/new_game` في المجموعة لبدء جولة"
        )
    elif data == "view_stats":
        user = query.from_user
        db_user = await get_user(user.id)
        await query.message.reply_text(
            f"📊 نقاطك: {db_user['points']}\n"
            f"🎮 جولاتك: {db_user['games_played']}\n"
            f"✅ فوزك: {db_user['games_won']}"
        )
    elif data == "view_leaderboard":
        leaders = await get_leaderboard()
        text = "🏆 المتصدرين:\n"
        for i, p in enumerate(leaders[:5], 1):
            name = p['first_name'] or p['username'] or str(p['user_id'])
            text += f"{i}. {name}: {p['points']} نقطة\n"
        await query.message.reply_text(text)
    elif data == "referral_code":
        user = query.from_user
        db_user = await get_user(user.id)
        await query.message.reply_text(
            f"🔗 كود الإحالة: `{db_user['referral_code']}`\n"
            "شاركه مع أصدقائك لتربح 75 نقطة!"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأخطاء"""
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
    """تشغيل البوت"""
    app = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("new_game", new_game))
    app.add_handler(CommandHandler("join", join_game))
    app.add_handler(CommandHandler("leave", leave_game))
    app.add_handler(CommandHandler("tasks", execute_task))
    app.add_handler(CommandHandler("kill", kill_player))
    app.add_handler(CommandHandler("vote", vote_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("referral", handle_referral_code))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_error_handler(error_handler)
    
    # بدء البوت
    logger.info("🤖 بوت Among Us يعمل الآن!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # تهيئة قاعدة البيانات
    asyncio.get_event_loop().run_until_complete(init_db())
    
    # تشغيل البوت
    main()
