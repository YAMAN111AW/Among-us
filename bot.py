import os
import asyncio
import random
import uuid
from datetime import datetime
import psycopg2
import psycopg2.extras
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
import logging

# ====== إعدادات التسجيل ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== إعدادات البوت ======
BOT_TOKEN = os.getenv("BOT_TOKEN", "ضع_التوكن_هنا_إن_لم_يكن_في_البيئة")
DATABASE_URL = os.getenv("DATABASE_URL")

# ====== أدوات مساعدة ======
CREWMATE_TOOLS = [
    {"name": "جهاز تتبع", "emoji": "📡", "description": "يكشف موقع لاعب واحد", "effect": "track"},
    {"name": "كاميرا مراقبة", "emoji": "📸", "description": "تلتقط صورة للاعب", "effect": "camera"},
    {"name": "جهاز كشف الكذب", "emoji": "🕵️", "description": "يكشف الصادق من الكاذب", "effect": "lie_detector"},
    {"name": "درع واقي", "emoji": "🛡️", "description": "يحميك من القتل لمرة", "effect": "shield"},
    {"name": "مسرع المهام", "emoji": "⚡", "description": "ينهي مهمتين دفعة واحدة", "effect": "speed_boost"}
]

IMPOSTOR_TOOLS = [
    {"name": "قنبلة دخان", "emoji": "💨", "description": "تمنع الكاميرات لدقيقة", "effect": "smoke_bomb"},
    {"name": "تنكر", "emoji": "🎭", "description": "تتظاهر أنك طاقم", "effect": "disguise"},
    {"name": "تخريب الأبواب", "emoji": "🚪", "description": "يقفل الأبواب 30 ثانية", "effect": "lock_doors"},
    {"name": "تشويش الاتصالات", "emoji": "📵", "description": "يمنع الاجتماع لدقيقة", "effect": "jam_comms"}
]

LOCATIONS = ["الكافتيريا 🍽️", "المفاعل ☢️", "غرفة المحرك ⚙️", "الممر الرئيسي 🚶", "غرفة الاتصالات 📡", "المخزن 📦", "غرفة الأكسجين 🫁", "المختبر 🔬", "قاعة الاجتماعات 🏛️"]

# تم تعديل المهام لاستخدام IDs قصيرة للأزرار لتجنب تجاوز حد 64 بايت في تيليجرام
CREWMATE_TASKS = [
    {"id": 0, "name": "إصلاح الأسلاك", "emoji": "🔌", "description": "اضغط على الزر الصحيح لتوصيلها", "buttons": [[("b1","🔵 أزرق"), ("b2","🟡 أصفر")], [("b3","🔴 أحمر"), ("b4","🟢 أخضر")]], "correct": "b1", "success": "✅ تم إصلاح الأسلاك بنجاح!"},
    {"id": 1, "name": "مسح بطاقة الدخول", "emoji": "💳", "description": "اختر السرعة الصحيحة لتمرير البطاقة", "buttons": [[("b1","🐢 بطيء"), ("b2","🐇 سريع")], [("b3","🏃 سريع جداً"), ("b4","🚶 متوسط")]], "correct": "b4", "success": "✅ تم مسح البطاقة!"},
    {"id": 2, "name": "تفريغ القمامة", "emoji": "🗑️", "description": "اختر الكيس الصحيح لتفريغه", "buttons": [[("b1","🟫 بني"), ("b2","⬛ أسود")], [("b3","🟦 أزرق"), ("b4","🟩 أخضر")]], "correct": "b2", "success": "✅ تم تفريغ القمامة!"},
]

IMPOSTOR_TASKS = [
    {"id": 0, "name": "تخريب المفاعل", "emoji": "☢️", "description": "حاول تخريب المفاعل (ستهزم دائماً)", "buttons": [[("b1","🔴 زر الطوارئ"), ("b2","🟢 زر التشغيل")]], "failure": "❌ فشل التخريب! المفاعل أمان."},
]

KILL_SCENARIOS = [
    {"death_message": "🔴💀🔴\n*تم اكتشاف جثة!*\n\n💀 {victim} مات مقتولاً!\n📍 {location}\n\n🚨 *اجتماع طارئ!*"},
]

RANDOM_EVENTS = [
    {"message": "⚡ *انقطعت الكهرباء فجأة!*\n\n🌑 الظلام يخيم على السفينة..."},
    {"message": "🌋 *السفينة بتهتز بعنف!*\n\n💥 كل اللاعبين وقعوا!"}
]

# ====== تخزين مؤقت ======
active_games = {}
user_tools = {}

# ====== دوال قاعدة البيانات (تعمل بالخلفية Async) ======
def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def run_db_query(func, *args):
    return await asyncio.to_thread(func, *args)

def _init_db():
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

def _get_user(user_id: int):
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
    conn.close()
    return user

def _update_user_points(user_id: int, points: int, won: bool = False, role: str = None, kill: bool = False, task: bool = False):
    conn = get_conn()
    cursor = conn.cursor()
    update_parts = ["points = points + %s", "games_played = games_played + 1"]
    params = [points]
    if won:
        update_parts.append('games_won = games_won + 1')
        if role == 'crewmate': update_parts.append('crewmate_wins = crewmate_wins + 1')
        elif role == 'impostor': update_parts.append('impostor_wins = impostor_wins + 1')
    if kill: update_parts.append('total_kills = total_kills + 1')
    if task: update_parts.append('total_tasks = total_tasks + 1')
    params.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(update_parts)} WHERE user_id = %s", params)
    conn.commit()
    cursor.close()
    conn.close()

def _register_group(group_id: int, title: str):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO groups (group_id, title) VALUES (%s, %s) ON CONFLICT (group_id) DO UPDATE SET title = %s', (group_id, title, title))
    conn.commit()
    cursor.close()
    conn.close()

# ====== دوال مساعدة ======
def generate_game_key() -> str: return str(uuid.uuid4())[:6]
def get_impostor_count(player_count: int) -> int:
    if player_count <= 5: return 1
    elif player_count <= 8: return 2
    else: return 3
def get_player_name(pdata: dict) -> str: return pdata.get('first_name') or pdata.get('username') or 'لاعب'

# ====== معالجات الأوامر ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await run_db_query(_get_user, user.id)
    welcome_text = (f"🎮 مرحباً {user.first_name}!\n\nأنا بوت Among Us في تليجرام!\nالعب مع أصدقائك في المجموعات واكتشف القاتل!")
    keyboard = [[InlineKeyboardButton("🎮 الإحصائيات", callback_data="view_stats")]]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        'id': game_id, 'creator': user.id, 'players': {}, 'status': 'waiting',
        'impostors': [], 'alive_crewmates': [], 'dead_players': [],
        'votes': {}, 'kill_cooldown': {}, 'emergency_used': False,
        'emergency_blocked': False, 'smoke_active': False, 'doors_locked': False,
        'start_votes': {}
    }
    
    await run_db_query(_register_group, chat_id, update.effective_chat.title or "مجموعة")
    
    keyboard = [[InlineKeyboardButton("🎮 انضم للعبة", callback_data=f"join_{chat_id}")]]
    await update.message.reply_text(
        f"🚀 لعبة جديدة!\n\nمعرف: {game_id}\nالمنشئ: {user.first_name}\n\n👥 اضغط على الزر أدناه للانضمام!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def process_join(chat_id: int, user, context: ContextTypes.DEFAULT_TYPE) -> str:
    if chat_id not in active_games: return "❌ لا توجد لعبة نشطة!"
    game = active_games[chat_id]
    if game['status'] != 'waiting': return "❌ اللعبة بدأت بالفعل!"
    if user.id in game['players']: return "⚠️ أنت منضم بالفعل!"
    if len(game['players']) >= 10: return "❌ اللعبة مكتملة!"
    
    game['players'][user.id] = {
        'username': user.username or user.first_name, 'first_name': user.first_name,
        'role': None, 'alive': True, 'tasks': 0, 'total_tasks': 3, 'shield': False
    }
    await run_db_query(_get_user, user.id)
    
    player_count = len(game['players'])
    
    if player_count >= 4 and not game.get('vote_started'):
        game['vote_started'] = True
        asyncio.create_task(ask_start_vote(chat_id, context))
        
    return f"✅ تم الانضمام! ({player_count}/10)"

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await process_join(update.effective_chat.id, update.effective_user, context)
    await update.message.reply_text(msg)

async def ask_start_vote(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    game = active_games.get(chat_id)
    if not game: return
    
    keyboard = [
        [InlineKeyboardButton("✅ نعم، ابدأ!", callback_data=f"startvote_{chat_id}_yes"),
         InlineKeyboardButton("❌ لا، انتظر", callback_data=f"startvote_{chat_id}_no")]
    ]
    await context.bot.send_message(chat_id=chat_id, text="🎮 هل تريدون بدء اللعبة الآن؟\n\n⏰ التصويت ينتهي بعد 30 ثانية!", reply_markup=InlineKeyboardMarkup(keyboard))
    await asyncio.sleep(30)
    
    # بعد انتهاء الـ 30 ثانية
    if chat_id in active_games and active_games[chat_id]['status'] == 'waiting':
        yes_votes = sum(1 for v in active_games[chat_id]['start_votes'].values() if v == 'yes')
        if yes_votes >= 2 or len(active_games[chat_id]['players']) >= 6:
            await context.bot.send_message(chat_id=chat_id, text="✅ جاري بدء اللعبة...")
            await start_game(chat_id, context)
        else:
            await context.bot.send_message(chat_id=chat_id, text="⏳ في انتظار المزيد من اللاعبين... لم يوافق العدد الكافي.")
            active_games[chat_id]['vote_started'] = False # إعادة السماح بالتصويت

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
        user_tools[imp_id] = random.sample(IMPOSTOR_TOOLS, random.randint(1, 2))
        try: await context.bot.send_message(chat_id=imp_id, text=f"🔪 *أنت القاتل!*\nاستخدم /kill لقتل الطاقم", parse_mode='Markdown')
        except: pass
    
    for crew_id in crewmates:
        game['players'][crew_id]['role'] = 'crewmate'
        game['alive_crewmates'].append(crew_id)
        user_tools[crew_id] = random.sample(CREWMATE_TOOLS, random.randint(1, 2))
        try: await context.bot.send_message(chat_id=crew_id, text=f"👨‍🚀 *أنت فرد طاقم!*\nاستخدم /tasks للمهام", parse_mode='Markdown')
        except: pass
    
    game['status'] = 'playing'
    await context.bot.send_message(chat_id=chat_id, text=f"🚀🔥🚀 *انطلقت اللعبة!*\n👥 {len(players)} لاعبين\n🔪 {impostor_count} قتلة", parse_mode='Markdown')

async def execute_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    game = None; group_id = None
    for gid, g in active_games.items():
        if user_id in g['players']: game = g; group_id = gid; break
        
    if not game or game['status'] != 'playing' or not game['players'][user_id]['alive']: return
    
    player = game['players'][user_id]
    if player['role'] == 'crewmate':
        task = random.choice(CREWMATE_TASKS)
        # استخدام IDs قصيرة: cb_t_{chat_id}_{task_id}_{btn_id}
        keyboard = [[InlineKeyboardButton(txt, callback_data=f"cb_t_{group_id}_{task['id']}_{btn_id}") for btn_id, txt in row] for row in task['buttons']]
        await update.message.reply_text(f"{task['emoji']} *{task['name']}*\n\n{task['description']}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        task = random.choice(IMPOSTOR_TASKS)
        keyboard = [[InlineKeyboardButton(txt, callback_data=f"cb_f_{group_id}") for btn_id, txt in row] for row in task['buttons']]
        await update.message.reply_text(f"{task['emoji']} *{task['name']}*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_task_callback(query, context, data):
    parts = data.split('_')
    if data.startswith('cb_t_'):
        group_id, task_id, btn_id = int(parts[2]), int(parts[3]), parts[4]
        if group_id not in active_games: return await query.edit_message_text("❌ اللعبة انتهت!")
        game = active_games[group_id]
        user_id = query.from_user.id
        
        task = next((t for t in CREWMATE_TASKS if t['id'] == task_id), None)
        if task and task['correct'] == btn_id:
            await query.edit_message_text(f"{task['emoji']} *{task['name']}*\n\n{task['success']}", parse_mode='Markdown')
            game['players'][user_id]['tasks'] += 1
            await run_db_query(_update_user_points, user_id, 15, False, None, False, True)
            if game['players'][user_id]['tasks'] >= game['players'][user_id]['total_tasks']:
                await context.bot.send_message(chat_id=user_id, text="🎉 أكملت جميع مهامك!")
        else:
            await query.edit_message_text("❌ إجابة خاطئة!")
            
    elif data.startswith('cb_f_'):
        await query.edit_message_text("❌ فشل التخريب! (أنت قاتل، هذه مهمة وهمية)")

async def kill_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.effective_chat.type != 'private':
        return await update.message.reply_text("❌ استخدم هذا الأمر في الخاص فقط!")
        
    game = None; group_id = None
    for gid, g in active_games.items():
        if user_id in g['players']: game = g; group_id = gid; break
        
    if not game or game['players'][user_id]['role'] != 'impostor' or not game['players'][user_id]['alive']: return
    
    if not context.args: return await update.message.reply_text("❌ اكتب /kill @username")
    victim_username = context.args[0].replace('@', '')
    
    victim_id = next((pid for pid, p in game['players'].items() if p['username'] == victim_username and p['alive'] and pid != user_id), None)
    if not victim_id: return await update.message.reply_text("❌ لم يتم العثور على اللاعب!")
    
    game['players'][victim_id]['alive'] = False
    game['dead_players'].append(victim_id)
    if victim_id in game['alive_crewmates']: game['alive_crewmates'].remove(victim_id)
    
    await run_db_query(_update_user_points, user_id, 30, False, None, True, False)
    await update.message.reply_text("✅ تم القتل!")
    await context.bot.send_message(chat_id=group_id, text=KILL_SCENARIOS[0]['death_message'].format(victim=game['players'][victim_id]['first_name'], location=random.choice(LOCATIONS)), parse_mode='Markdown')
    
    if len(game['impostors']) >= len(game['alive_crewmates']):
        await end_game(group_id, context, 'impostor')

async def end_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE, winner: str):
    game = active_games[chat_id]
    game['status'] = 'ended'
    win_text = "🎉🏆 *الطاقم يفوز!*" if winner == 'crewmate' else "🔪👑 *القاتل ينتصر!*"
    await context.bot.send_message(chat_id=chat_id, text=f"{win_text}\n\n🏆 *نهاية الجولة!*\n\n🎮 /new_game لجولة جديدة!", parse_mode='Markdown')
    del active_games[chat_id]

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()
    
    if data.startswith('cb_t_') or data.startswith('cb_f_'):
        await handle_task_callback(query, context, data)
    elif data.startswith('join_'):
        chat_id = int(data.split('_')[1])
        msg = await process_join(chat_id, query.from_user, context)
        try: await context.bot.send_message(chat_id=chat_id, text=f"👤 {query.from_user.first_name} - {msg}")
        except: pass
    elif data.startswith('startvote_'):
        parts = data.split('_')
        chat_id = int(parts[1])
        if chat_id in active_games:
            active_games[chat_id]['start_votes'][query.from_user.id] = parts[2]
            await query.answer("تم تسجيل صوتك!")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new_game", new_game))
    app.add_handler(CommandHandler("join", join_command))
    app.add_handler(CommandHandler("tasks", execute_task))
    app.add_handler(CommandHandler("kill", kill_player))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🤖🔥 بوت Among Us يعمل!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    _init_db()
    main()

