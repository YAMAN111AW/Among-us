import telebot
import psycopg2
import random
import string
import time
import threading
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============= إعدادات البوت =============
BOT_TOKEN = "8875334916:AAHq6C2F8ujgnlaLGUW3tR1tgdizFE7SdEw"
DATABASE_URL = "postgresql://postgres:FTiUAIDFQjLnLIebBxkIFprvrHrqfeDs@sakura.proxy.rlwy.net:41714/railway"

bot = telebot.TeleBot(BOT_TOKEN)
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# ============= متغيرات عامة =============
MEETING_ACTIVE = {}  # game_id -> {end_time, votes, voter_ids}
VOTES = {}  # game_id -> {target_id: [voter_ids]}

# ============= دوال مساعدة قاعدة البيانات =============
def safe_execute(query, params=None):
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ DB Error: {e}")
        return False

def safe_fetchone(query, params=None):
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchone()
    except Exception as e:
        conn.rollback()
        print(f"❌ DB Error: {e}")
        return None

def safe_fetchall(query, params=None):
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchall()
    except Exception as e:
        conn.rollback()
        print(f"❌ DB Error: {e}")
        return []

# ============= إنشاء الجداول =============
def init_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username VARCHAR(100),
        total_games INT DEFAULT 0,
        wins INT DEFAULT 0,
        kills INT DEFAULT 0
    );
    
    CREATE TABLE IF NOT EXISTS games (
        game_id SERIAL PRIMARY KEY,
        code VARCHAR(6) UNIQUE NOT NULL,
        host_id BIGINT NOT NULL,
        status VARCHAR(20) DEFAULT 'waiting',
        max_players INT DEFAULT 10,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        meeting_active BOOLEAN DEFAULT FALSE,
        meeting_end TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS players (
        player_id SERIAL PRIMARY KEY,
        game_id INT REFERENCES games(game_id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL,
        username VARCHAR(100),
        role VARCHAR(20) DEFAULT 'crewmate',
        is_alive BOOLEAN DEFAULT TRUE,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        has_shield BOOLEAN DEFAULT FALSE,
        has_knife BOOLEAN DEFAULT FALSE
    );
    
    CREATE TABLE IF NOT EXISTS tasks (
        task_id SERIAL PRIMARY KEY,
        name VARCHAR(100),
        description TEXT,
        task_type VARCHAR(20) DEFAULT 'simple',
        difficulty INT DEFAULT 1
    );
    
    CREATE TABLE IF NOT EXISTS player_tasks (
        id SERIAL PRIMARY KEY,
        player_id INT REFERENCES players(player_id) ON DELETE CASCADE,
        task_id INT REFERENCES tasks(task_id),
        is_completed BOOLEAN DEFAULT FALSE,
        progress INT DEFAULT 0
    );
    
    CREATE TABLE IF NOT EXISTS kills (
        kill_id SERIAL PRIMARY KEY,
        game_id INT REFERENCES games(game_id) ON DELETE CASCADE,
        killer_id BIGINT NOT NULL,
        victim_id BIGINT NOT NULL,
        killed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    print("✅ Database initialized")

init_db()

# ============= المهام التفاعلية =============
TASKS_LIST = [
    # مهام بسيطة (زر واحد)
    {"name": "🔧 إصلاح الأسلاك", "desc": "صلح الأسلاك المتقطعة", "type": "button", "data": "wire", "diff": 1},
    {"name": "🧹 تنظيف الفلتر", "desc": "نظف فلتر الأوكسجين", "type": "button", "data": "filter", "diff": 1},
    {"name": "⚡ شحن البطارية", "desc": "شحن بطارية الطوارئ", "type": "button", "data": "battery", "diff": 1},
    
    # مهام ألغاز (اختيار من متعدد)
    {"name": "🔬 تحليل العينة", "desc": "اختر التحليل الصحيح للعينة", "type": "quiz", "data": "sample", "diff": 2},
    {"name": "💻 فحص البرمجيات", "desc": "اختر البرنامج الصحيح للفحص", "type": "quiz", "data": "software", "diff": 2},
    {"name": "📡 توجيه الإشارة", "desc": "اختر التردد الصحيح للإشارة", "type": "quiz", "data": "signal", "diff": 2},
    
    # مهام متعددة الخطوات
    {"name": "🔥 إطفاء الحريق", "desc": "اضغط الأزرار بالترتيب الصحيح", "type": "sequence", "data": "fire", "diff": 3},
    {"name": "🛠 صيانة المحرك", "desc": "صلح المحرك باتباع الخطوات", "type": "sequence", "data": "engine", "diff": 3},
    {"name": "☢️ التخلص من النفايات", "desc": "اتبع التعليمات للتخلص الآمن", "type": "sequence", "data": "waste", "diff": 3},
]

# ============= دوال مساعدة =============
def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_or_create_user(user_id, username):
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (user_id, username) VALUES (%s, %s)", (user_id, username))
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ Error in get_or_create_user: {e}")

def get_game_by_code(code):
    return safe_fetchone("SELECT * FROM games WHERE code = %s", (code,))

def get_players_count(game_id):
    result = safe_fetchone("SELECT COUNT(*) FROM players WHERE game_id = %s", (game_id,))
    return result[0] if result else 0

def get_alive_players(game_id):
    return safe_fetchall("SELECT user_id, username FROM players WHERE game_id = %s AND is_alive = TRUE", (game_id,))

def get_killer(game_id):
    result = safe_fetchone("SELECT user_id FROM players WHERE game_id = %s AND role = 'killer' AND is_alive = TRUE", (game_id,))
    return result[0] if result else None

def assign_tasks(player_id):
    try:
        cursor.execute("SELECT task_id, task_type FROM tasks")
        all_tasks = cursor.fetchall()
        if not all_tasks:
            return
        
        # اختيار 3 مهام عشوائية
        selected = random.sample(all_tasks, min(3, len(all_tasks)))
        for task_id, task_type in selected:
            cursor.execute(
                "INSERT INTO player_tasks (player_id, task_id, progress) VALUES (%s, %s, %s)",
                (player_id, task_id, 0 if task_type != 'simple' else 100)
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ Error in assign_tasks: {e}")

def get_player_tasks(player_id):
    return safe_fetchall("""
        SELECT t.task_id, t.name, t.description, t.task_type, pt.is_completed, pt.progress
        FROM player_tasks pt
        JOIN tasks t ON pt.task_id = t.task_id
        WHERE pt.player_id = %s
        ORDER BY pt.id
    """, (player_id,))

def complete_task(player_id, task_index):
    try:
        cursor.execute("""
            SELECT id, is_completed, task_id FROM player_tasks 
            WHERE player_id = %s ORDER BY id LIMIT 1 OFFSET %s
        """, (player_id, task_index))
        task = cursor.fetchone()
        if task and not task[1]:
            cursor.execute("UPDATE player_tasks SET is_completed = TRUE, progress = 100 WHERE id = %s", (task[0],))
            conn.commit()
            return True, task[2]
        return False, None
    except Exception as e:
        conn.rollback()
        print(f"❌ Error in complete_task: {e}")
        return False, None

def check_all_tasks_completed(game_id):
    result = safe_fetchone("""
        SELECT COUNT(*) FROM player_tasks pt
        JOIN players p ON pt.player_id = p.player_id
        WHERE p.game_id = %s AND pt.is_completed = FALSE
    """, (game_id,))
    return result[0] == 0 if result else False

def get_bot_username():
    try:
        return bot.get_me().username
    except:
        return "AmongUsBot"

def is_meeting_active(game_id):
    if game_id not in MEETING_ACTIVE:
        return False
    meeting = MEETING_ACTIVE[game_id]
    if datetime.now() > meeting['end_time']:
        del MEETING_ACTIVE[game_id]
        return False
    return True

def start_meeting(game_id, chat_id, caller_id):
    """بدء اجتماع لمدة 90 ثانية"""
    MEETING_ACTIVE[game_id] = {
        'end_time': datetime.now() + timedelta(seconds=90),
        'votes': {},
        'voter_ids': [],
        'chat_id': chat_id,
        'caller_id': caller_id
    }
    VOTES[game_id] = {}
    
    # تحديث حالة الاجتماع في قاعدة البيانات
    safe_execute("UPDATE games SET meeting_active = TRUE, meeting_end = NOW() + INTERVAL '90 seconds' WHERE game_id = %s", (game_id,))
    
    # جدولة إنهاء الاجتماع تلقائياً
    threading.Timer(90.0, end_meeting, args=[game_id]).start()
    
    return True

def end_meeting(game_id):
    """إنهاء الاجتماع"""
    if game_id in MEETING_ACTIVE:
        # حساب نتيجة التصويت
        votes = MEETING_ACTIVE[game_id].get('votes', {})
        if votes:
            max_votes = max(votes.values())
            targets = [uid for uid, v in votes.items() if v == max_votes]
            
            if len(targets) == 1:
                # إقصاء اللاعب
                target_id = targets[0]
                safe_execute("UPDATE players SET is_alive = FALSE WHERE user_id = %s AND game_id = %s", (target_id, game_id))
                
                chat_id = MEETING_ACTIVE[game_id]['chat_id']
                target_username = safe_fetchone("SELECT username FROM players WHERE user_id = %s", (target_id,))
                bot.send_message(chat_id, f"🗳️ **تم إقصاء @{target_username[0] if target_username else 'لاعب'}**\nتم التصويت عليه من قبل الأغلبية!")
                
                # التحقق من فوز الطاقم أو القاتل
                check_game_winner(game_id, chat_id)
            else:
                chat_id = MEETING_ACTIVE[game_id]['chat_id']
                bot.send_message(chat_id, "⚖️ **تعادل في الأصوات!**\nلم يتم إقصاء أحد.")
        
        del MEETING_ACTIVE[game_id]
        if game_id in VOTES:
            del VOTES[game_id]
        
        safe_execute("UPDATE games SET meeting_active = FALSE WHERE game_id = %s", (game_id,))

def check_game_winner(game_id, chat_id):
    """التحقق من فوز الطاقم أو القاتل"""
    alive = get_alive_players(game_id)
    killer = get_killer(game_id)
    
    if not killer:
        bot.send_message(chat_id, "🎉 **فاز الطاقم!** القاتل مات!")
        safe_execute("UPDATE games SET status = 'ended' WHERE game_id = %s", (game_id,))
        return True
    
    if len(alive) <= 2:
        bot.send_message(chat_id, "🔪 **فاز القاتل!** لا يوجد عدد كافٍ من الطاقم!")
        safe_execute("UPDATE games SET status = 'ended' WHERE game_id = %s", (game_id,))
        return True
    
    if check_all_tasks_completed(game_id):
        bot.send_message(chat_id, "🎉 **فاز الطاقم!** أنجزوا جميع المهام!")
        safe_execute("UPDATE games SET status = 'ended' WHERE game_id = %s", (game_id,))
        return True
    
    return False

# ============= مهام تفاعلية =============
def start_interactive_task(message, task_id, player_id):
    """بدء مهمة تفاعلية بناءً على نوعها"""
    cursor.execute("SELECT name, task_type, description FROM tasks WHERE task_id = %s", (task_id,))
    task = cursor.fetchone()
    if not task:
        return
    
    task_name, task_type, description = task
    
    if task_type == 'button':
        # مهمة زر واحد
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton("✅ إنجاز المهمة", callback_data=f"do_task_{player_id}_{task_id}")
        markup.add(btn)
        bot.send_message(
            message.chat.id,
            f"📋 **{task_name}**\n{description}\n\nاضغط الزر لإنجاز المهمة",
            reply_markup=markup
        )
    
    elif task_type == 'quiz':
        # مهمة اختيار من متعدد
        quiz_data = get_quiz_data(task_id)
        markup = InlineKeyboardMarkup()
        for i, option in enumerate(quiz_data['options']):
            btn = InlineKeyboardButton(option, callback_data=f"quiz_{player_id}_{task_id}_{i}")
            markup.add(btn)
        bot.send_message(
            message.chat.id,
            f"📋 **{task_name}**\n{description}\n\nاختر الإجابة الصحيحة:",
            reply_markup=markup
        )
    
    elif task_type == 'sequence':
        # مهمة متعددة الخطوات
        sequence_data = get_sequence_data(task_id)
        markup = InlineKeyboardMarkup()
        for i, step in enumerate(sequence_data['steps']):
            btn = InlineKeyboardButton(step, callback_data=f"seq_{player_id}_{task_id}_{i}")
            markup.add(btn)
        bot.send_message(
            message.chat.id,
            f"📋 **{task_name}**\n{description}\n\nاضغط الأزرار بالترتيب الصحيح:",
            reply_markup=markup
        )

def get_quiz_data(task_id):
    """بيانات الأسئلة للمهام من نوع quiz"""
    quizzes = {
        1: {"options": ["🔴 A", "🟢 B", "🔵 C"], "correct": 1},
        2: {"options": ["Windows", "Linux", "macOS"], "correct": 1},
        3: {"options": ["2.4 GHz", "5 GHz", "6 GHz"], "correct": 0},
    }
    return quizzes.get(task_id, {"options": ["خيار 1", "خيار 2", "خيار 3"], "correct": 0})

def get_sequence_data(task_id):
    """بيانات التسلسل للمهام من نوع sequence"""
    sequences = {
        1: {"steps": ["🔴 فتح الصمام", "🟢 تشغيل المضخة", "🔵 إغلاق الصمام"], "order": [0, 1, 2]},
        2: {"steps": ["🔧 فك البراغي", "🛠 استبدال القطع", "🔩 إعادة التركيب"], "order": [0, 1, 2]},
        3: {"steps": ["☢️ ارتداء البدلة", "🧪 جمع العينة", "🗑️ التخلص الآمن"], "order": [0, 1, 2]},
    }
    return sequences.get(task_id, {"steps": ["خطوة 1", "خطوة 2", "خطوة 3"], "order": [0, 1, 2]})

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """معالج الأزرار التفاعلية"""
    data = call.data.split('_')
    
    if data[0] == 'do_task':
        # إنجاز مهمة زر
        player_id = int(data[2])
        task_id = int(data[3])
        cursor.execute("UPDATE player_tasks SET is_completed = TRUE, progress = 100 WHERE player_id = %s AND task_id = %s", (player_id, task_id))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ تم إنجاز المهمة!")
        bot.edit_message_text("✅ تم إنجاز المهمة بنجاح!", call.message.chat.id, call.message.message_id)
    
    elif data[0] == 'quiz':
        # معالج مهمة اختيار من متعدد
        player_id = int(data[1])
        task_id = int(data[2])
        choice = int(data[3])
        
        quiz_data = get_quiz_data(task_id)
        if choice == quiz_data['correct']:
            cursor.execute("UPDATE player_tasks SET is_completed = TRUE, progress = 100 WHERE player_id = %s AND task_id = %s", (player_id, task_id))
            conn.commit()
            bot.answer_callback_query(call.id, "✅ إجابة صحيحة!")
            bot.edit_message_text("✅ **أحسنت!** إجابة صحيحة! تم إنجاز المهمة.", call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "❌ إجابة خاطئة! حاول مرة أخرى.")
    
    elif data[0] == 'seq':
        # معالج مهمة التسلسل
        # (سيتم تطويره لاحقاً)
        bot.answer_callback_query(call.id, "✅ تم!")
    
    elif data[0] == 'vote':
        # معالج التصويت
        game_id = int(data[1])
        target_id = int(data[2])
        voter_id = call.from_user.id
        
        if game_id not in MEETING_ACTIVE:
            bot.answer_callback_query(call.id, "❌ لا يوجد اجتماع نشط!")
            return
        
        if voter_id in MEETING_ACTIVE[game_id]['voter_ids']:
            bot.answer_callback_query(call.id, "❌ لقد صوتت بالفعل!")
            return
        
        MEETING_ACTIVE[game_id]['voter_ids'].append(voter_id)
        if target_id not in MEETING_ACTIVE[game_id]['votes']:
            MEETING_ACTIVE[game_id]['votes'][target_id] = 0
        MEETING_ACTIVE[game_id]['votes'][target_id] += 1
        
        bot.answer_callback_query(call.id, "🗳️ تم تسجيل صوتك!")
        
        # تحديث رسالة التصويت
        votes_msg = "🗳️ **نتائج التصويت الحالية:**\n\n"
        for uid, count in MEETING_ACTIVE[game_id]['votes'].items():
            username = safe_fetchone("SELECT username FROM players WHERE user_id = %s", (uid,))
            votes_msg += f"@{username[0] if username else 'لاعب'}: {count} صوت\n"
        
        bot.edit_message_text(
            votes_msg,
            call.message.chat.id,
            call.message.message_id
        )

# ============= أوامر البوت =============

@bot.message_handler(commands=['start'])
def start(message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    bot.reply_to(message, 
        "🎮 **مرحباً في بوت Among Us!**\n\n"
        "📌 الأوامر المتاحة:\n"
        "/new - إنشاء لعبة جديدة\n"
        "/join [كود] - الانضمام للعبة\n"
        "/startgame - بدء اللعبة (للمضيف فقط)\n"
        "/cancel - إلغاء اللعبة الحالية\n"
        "/tasks - عرض مهامي\n"
        "/dotask [رقم] - بدء مهمة تفاعلية\n"
        "/kill [@user] - قتل لاعب (للقاتل فقط)\n"
        "/meeting - دعوة اجتماع طارئ 🚨\n"
        "/status - حالة اللعبة\n"
        "/help - عرض المساعدة",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['new'])
def new_game(message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    
    # التحقق من عدم وجود لعبة نشطة
    existing = safe_fetchone("""
        SELECT g.code FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE p.user_id = %s AND g.status IN ('waiting', 'playing')
    """, (message.from_user.id,))
    if existing:
        bot.reply_to(message, "❌ لديك لعبة نشطة حالياً!")
        return
    
    code = generate_code()
    try:
        cursor.execute(
            "INSERT INTO games (code, host_id, status) VALUES (%s, %s, 'waiting') RETURNING game_id",
            (code, message.from_user.id)
        )
        game_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO players (game_id, user_id, username, role) VALUES (%s, %s, %s, 'crewmate')",
            (game_id, message.from_user.id, message.from_user.username)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, f"❌ خطأ في إنشاء اللعبة: {e}")
        return
    
    # إضافة المهام
    player_result = safe_fetchone("SELECT player_id FROM players WHERE game_id = %s AND user_id = %s", (game_id, message.from_user.id))
    if player_result:
        assign_tasks(player_result[0])
    
    bot.reply_to(message, 
        f"✅ **تم إنشاء اللعبة!**\n"
        f"🔑 الكود: `{code}`\n"
        f"👥 عدد اللاعبين: 1/10\n\n"
        f"شارك الكود مع أصدقائك:\n"
        f"/join {code}",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['join'])
def join_game(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ استخدم: /join [كود اللعبة]")
        return
    
    code = args[1].upper()
    game = get_game_by_code(code)
    
    if not game:
        bot.reply_to(message, "❌ اللعبة غير موجودة!")
        return
    
    game_id = game[0]
    if game[3] != 'waiting':
        bot.reply_to(message, "❌ اللعبة بدأت بالفعل!")
        return
    
    players_count = get_players_count(game_id)
    if players_count >= 10:
        bot.reply_to(message, "❌ اللعبة ممتلئة!")
        return
    
    existing = safe_fetchone("SELECT * FROM players WHERE game_id = %s AND user_id = %s", (game_id, message.from_user.id))
    if existing:
        bot.reply_to(message, "❌ أنت بالفعل في هذه اللعبة!")
        return
    
    try:
        cursor.execute(
            "INSERT INTO players (game_id, user_id, username, role) VALUES (%s, %s, %s, 'crewmate')",
            (game_id, message.from_user.id, message.from_user.username)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, f"❌ خطأ في الانضمام: {e}")
        return
    
    player_result = safe_fetchone("SELECT player_id FROM players WHERE game_id = %s AND user_id = %s", (game_id, message.from_user.id))
    if player_result:
        assign_tasks(player_result[0])
    
    new_count = get_players_count(game_id)
    bot.reply_to(message, f"✅ انضممت للعبة `{code}`\n👥 عدد اللاعبين: {new_count}/10", parse_mode='Markdown')

@bot.message_handler(commands=['startgame'])
def start_game(message):
    game = safe_fetchone("""
        SELECT g.game_id, g.host_id, g.code FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE p.user_id = %s AND g.status = 'waiting'
    """, (message.from_user.id,))
    
    if not game:
        bot.reply_to(message, "❌ ليس لديك لعبة في وضع الانتظار!")
        return
    
    game_id, host_id, code = game
    
    if host_id != message.from_user.id:
        bot.reply_to(message, "❌ فقط مضيف اللعبة يمكنه البدء!")
        return
    
    players_count = get_players_count(game_id)
    if players_count < 4:
        bot.reply_to(message, f"❌ نحتاج 4 لاعبين على الأقل! (الآن {players_count})")
        return
    
    # اختيار القاتل
    all_players = safe_fetchall("SELECT player_id, user_id FROM players WHERE game_id = %s", (game_id,))
    if not all_players:
        bot.reply_to(message, "❌ لا يوجد لاعبين!")
        return
    
    killer_idx = random.randint(0, len(all_players) - 1)
    killer_player_id, killer_user_id = all_players[killer_idx]
    
    # منح القاتل سكين
    try:
        cursor.execute("UPDATE players SET role = 'killer', has_knife = TRUE WHERE player_id = %s", (killer_player_id,))
        cursor.execute("UPDATE games SET status = 'playing', started_at = NOW() WHERE game_id = %s", (game_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, f"❌ خطأ في بدء اللعبة: {e}")
        return
    
    # إرسال الأدوار
    for player_id, user_id in all_players:
        try:
            role = "قاتل" if user_id == killer_user_id else "عادي"
            emoji = "🔪" if user_id == killer_user_id else "👨‍🚀"
            
            bot.send_message(
                user_id,
                f"{emoji} **دورك في لعبة Among Us**\n"
                f"أنت: **{role}**\n\n"
                f"الكود: `{code}`\n"
                f"عدد اللاعبين: {players_count}\n\n"
                f"📌 الأوامر الخاصة:\n"
                f"/tasks - عرض مهامك\n"
                f"/dotask [رقم] - بدء مهمة تفاعلية\n"
                f"/meeting - دعوة اجتماع طارئ (إن كنت عادي)",
                parse_mode='Markdown'
            )
            
            if user_id == killer_user_id:
                bot.send_message(
                    user_id,
                    "🔪 **أنت القاتل!**\n"
                    "استخدم /kill @username لقتل لاعب\n"
                    "🗡️ لديك سكين واحد لكل قتل\n"
                    "📌 تذكر: لا تفضح نفسك!"
                )
            else:
                # منح الطاقم درع (حماية من قتل واحد)
                cursor.execute("UPDATE players SET has_shield = TRUE WHERE player_id = %s", (player_id,))
                conn.commit()
                bot.send_message(
                    user_id,
                    "🛡️ **لديك درع واقي!**\n"
                    "يحميك من قتل واحد فقط.\n"
                    "استخدمه بحكمة!"
                )
        except Exception as e:
            print(f"خطأ في إرسال الرسالة للمستخدم {user_id}: {e}")
    
    bot.send_message(message.chat.id, 
        f"🎮 **بدأت اللعبة!**\n"
        f"🔑 الكود: `{code}`\n"
        f"👥 عدد اللاعبين: {players_count}\n\n"
        f"📨 تم إرسال الأدوار في الخاص\n"
        f"🔪 القاتل بينكم... احذروا!",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['tasks'])
def show_tasks(message):
    result = safe_fetchone("""
        SELECT p.player_id, g.game_id, g.status 
        FROM players p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.user_id = %s AND g.status = 'playing'
    """, (message.from_user.id,))
    
    if not result:
        bot.reply_to(message, "❌ أنت لست في لعبة نشطة!")
        return
    
    player_id = result[0]
    tasks = get_player_tasks(player_id)
    
    if not tasks:
        bot.reply_to(message, "✅ لا توجد مهام متبقية! أنجزت كل شيء.")
        return
    
    msg = "📋 **مهامي:**\n\n"
    for i, (task_id, name, desc, task_type, done, progress) in enumerate(tasks, 1):
        status = "✅" if done else f"⏳ {progress}%"
        msg += f"{i}. {status} {name}\n   `{desc}`\n\n"
    
    msg += "\nاستخدم /dotask [الرقم] لبدء المهمة"
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['dotask'])
def do_task(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ استخدم: /dotask [رقم المهمة]")
        return
    
    try:
        task_num = int(args[1]) - 1
    except:
        bot.reply_to(message, "❌ الرقم غير صحيح!")
        return
    
    # التحقق من اللاعب
    result = safe_fetchone("""
        SELECT p.player_id, g.game_id, g.status 
        FROM players p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.user_id = %s AND g.status = 'playing'
    """, (message.from_user.id,))
    
    if not result:
        bot.reply_to(message, "❌ أنت لست في لعبة نشطة!")
        return
    
    player_id = result[0]
    
    # جلب المهمة
    tasks = get_player_tasks(player_id)
    if task_num >= len(tasks) or task_num < 0:
        bot.reply_to(message, "❌ رقم المهمة غير موجود!")
        return
    
    task_id = tasks[task_num][0]
    if tasks[task_num][4]:  # is_completed
        bot.reply_to(message, "❌ هذه المهمة منجزة بالفعل!")
        return
    
    # بدء المهمة التفاعلية
    start_interactive_task(message, task_id, player_id)

@bot.message_handler(commands=['kill'])
def kill_player(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ استخدم: /kill @username")
        return
    
    target = args[1].replace('@', '')
    
    # التحقق من أن المرسل هو القاتل
    killer = safe_fetchone("""
        SELECT p.game_id, p.user_id, p.has_knife
        FROM players p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.user_id = %s AND g.status = 'playing' AND p.role = 'killer' AND p.is_alive = TRUE
    """, (message.from_user.id,))
    
    if not killer:
        bot.reply_to(message, "❌ إما أنت لست القاتل، أو لست في لعبة، أو ميت!")
        return
    
    game_id, killer_id, has_knife = killer
    
    # التحقق من وجود اجتماع نشط
    if is_meeting_active(game_id):
        bot.reply_to(message, "❌ لا يمكن القتل أثناء الاجتماع!")
        return
    
    if not has_knife:
        bot.reply_to(message, "❌ ليس لديك سكين! استخدم /meeting لتجديد السكاكين")
        return
    
    # البحث عن الضحية
    victim = safe_fetchone("""
        SELECT user_id, has_shield FROM players 
        WHERE game_id = %s AND username = %s AND is_alive = TRUE AND role != 'killer'
    """, (game_id, target))
    
    if not victim:
        bot.reply_to(message, "❌ اللاعب غير موجود أو ميت أو هو القاتل!")
        return
    
    victim_id, has_shield = victim
    
    # تنفيذ القتل
    if has_shield:
        # الدرع يحمي من القتل
        safe_execute("UPDATE players SET has_shield = FALSE WHERE user_id = %s AND game_id = %s", (victim_id, game_id))
        bot.send_message(message.chat.id, f"🛡️ **درع!** @{target} نجا من القتل بفضل الدرع!")
        return
    
    try:
        cursor.execute("UPDATE players SET is_alive = FALSE WHERE user_id = %s AND game_id = %s", (victim_id, game_id))
        cursor.execute("UPDATE players SET has_knife = FALSE WHERE user_id = %s AND game_id = %s", (killer_id, game_id))
        cursor.execute(
            "INSERT INTO kills (game_id, killer_id, victim_id) VALUES (%s, %s, %s)",
            (game_id, killer_id, victim_id)
        )
        cursor.execute("UPDATE users SET kills = kills + 1 WHERE user_id = %s", (killer_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, f"❌ خطأ في القتل: {e}")
        return
    
    bot.send_message(message.chat.id, 
        f"💀 **تم العثور على جثة!**\n"
        f"الضحية: @{target}\n"
        f"🔍 من هو القاتل؟ صوتوا الآن!\n"
        f"استخدم /meeting لدعوة اجتماع"
    )
    
    try:
        bot.send_message(victim_id, "💀 **لقد قُتلت!**\nأنت خارج اللعبة. تابع فقط.")
    except:
        pass

@bot.message_handler(commands=['meeting'])
def call_meeting(message):
    # التحقق من وجود اللاعب
    result = safe_fetchone("""
        SELECT p.user_id, g.game_id, g.status, p.is_alive, p.role
        FROM players p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.user_id = %s AND g.status = 'playing' AND p.is_alive = TRUE
    """, (message.from_user.id,))
    
    if not result:
        bot.reply_to(message, "❌ أنت لست في لعبة نشطة، أو ميت!")
        return
    
    user_id, game_id, status, is_alive, role = result
    
    # منع القاتل من دعوة الاجتماع
    if role == 'killer':
        bot.reply_to(message, "🔪 **القاتل لا يستطيع دعوة اجتماع!**")
        return
    
    # التحقق من عدم وجود اجتماع نشط
    if is_meeting_active(game_id):
        bot.reply_to(message, "❌ يوجد اجتماع نشط بالفعل!")
        return
    
    # جلب جميع اللاعبين الأحياء للتصويت
    alive = get_alive_players(game_id)
    if len(alive) < 2:
        bot.reply_to(message, "❌ لا يوجد لاعبين أحياء كافيين!")
        return
    
    # بدء الاجتماع
    start_meeting(game_id, message.chat.id, message.from_user.id)
    
    # إرسال رسالة الاجتماع مع أزرار التصويت
    msg = f"🚨 **اجتماع طارئ!**\n"
    msg += f"👤 دعا للاجتماع: @{message.from_user.username}\n"
    msg += f"⏰ مدة الاجتماع: 90 ثانية\n\n"
    msg += "🗳️ **صوت على من تريد إقصاءه:**\n"
    
    markup = InlineKeyboardMarkup()
    for uid, username in alive:
        if uid != message.from_user.id:
            btn = InlineKeyboardButton(f"@{username}", callback_data=f"vote_{game_id}_{uid}")
            markup.add(btn)
    
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode='Markdown')
    
    # إرسال إشعار للجميع
    for uid, username in alive:
        try:
            bot.send_message(
                uid,
                f"🚨 **اجتماع طارئ!**\n"
                f"قام @{message.from_user.username} بدعوة الجميع للاجتماع.\n"
                f"⏰ المدة: 90 ثانية\n"
                f"استخدم /vote @username للتصويت",
                parse_mode='Markdown'
            )
        except:
            pass
    
    bot.reply_to(message, "✅ تم عقد الاجتماع بنجاح! ⏰ 90 ثانية للتصويت.")

@bot.message_handler(commands=['status'])
def game_status(message):
    result = safe_fetchone("""
        SELECT g.code, g.status, 
               COUNT(p.player_id) as total,
               SUM(CASE WHEN p.is_alive = TRUE THEN 1 ELSE 0 END) as alive
        FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE g.status IN ('waiting', 'playing')
        GROUP BY g.game_id
        HAVING COUNT(CASE WHEN p.user_id = %s THEN 1 END) > 0
    """, (message.from_user.id,))
    
    if not result:
        bot.reply_to(message, "❌ ليس لديك لعبة نشطة!")
        return
    
    code, status, total, alive = result
    status_text = "⏳ في الانتظار" if status == 'waiting' else "🎮 جارية"
    
    bot.reply_to(message,
        f"📊 **حالة اللعبة**\n"
        f"🔑 الكود: `{code}`\n"
        f"📌 الحالة: {status_text}\n"
        f"👥 اللاعبين: {total}/10\n"
        f"💚 الأحياء: {alive}\n"
        f"💀 الأموات: {total - alive}",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['cancel'])
def cancel_game(message):
    result = safe_fetchone("""
        SELECT g.game_id, g.host_id, g.status 
        FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE p.user_id = %s AND g.status IN ('waiting', 'playing')
    """, (message.from_user.id,))
    
    if not result:
        bot.reply_to(message, "❌ ليس لديك لعبة نشطة لإلغائها!")
        return
    
    game_id, host_id, status = result
    
    if message.from_user.id != host_id and status == 'playing':
        bot.reply_to(message, "❌ فقط المضيف يمكنه إلغاء اللعبة أثناء اللعب!")
        return
    
    safe_execute("DELETE FROM games WHERE game_id = %s", (game_id,))
    if game_id in MEETING_ACTIVE:
        del MEETING_ACTIVE[game_id]
    if game_id in VOTES:
        del VOTES[game_id]
    bot.reply_to(message, "🗑️ **تم إلغاء اللعبة!**")

@bot.message_handler(commands=['help'])
def help_command(message):
    start(message)

# ============= تشغيل البوت =============
if __name__ == "__main__":
    print("🤖 البوت شغال...")
    
    # إدخال المهام في قاعدة البيانات
    for task in TASKS_LIST:
        existing = safe_fetchone("SELECT * FROM tasks WHERE name = %s", (task['name'],))
        if not existing:
            safe_execute(
                "INSERT INTO tasks (name, description, task_type, difficulty) VALUES (%s, %s, %s, %s)",
                (task['name'], task['desc'], task['type'], task['diff'])
            )
    
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"❌ خطأ في البوت: {e}")
            time.sleep(5)
