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
DATABASE_URL = "postgresql://postgres:KjoMokHsrqRSWXIJAQqptaxVaaxrTLnS@sakura.proxy.rlwy.net:19327/railway"

bot = telebot.TeleBot(BOT_TOKEN)
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# ============= دوال مساعدة لقاعدة البيانات =============
def safe_execute(query, params=None):
    """تنفيذ استعلام مع حماية من الأخطاء"""
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ خطأ في قاعدة البيانات: {e}")
        return False

def safe_fetchone(query, params=None):
    """جلب صف واحد مع حماية"""
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchone()
    except Exception as e:
        conn.rollback()
        print(f"❌ خطأ في fetchone: {e}")
        return None

def safe_fetchall(query, params=None):
    """جلب كل الصفوف مع حماية"""
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchall()
    except Exception as e:
        conn.rollback()
        print(f"❌ خطأ في fetchall: {e}")
        return []

# ============= إنشاء الجداول =============
def init_db():
    try:
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
            started_at TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS players (
            player_id SERIAL PRIMARY KEY,
            game_id INT REFERENCES games(game_id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            username VARCHAR(100),
            role VARCHAR(20) DEFAULT 'crewmate',
            is_alive BOOLEAN DEFAULT TRUE,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS tasks (
            task_id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            description TEXT,
            difficulty INT DEFAULT 1
        );
        
        CREATE TABLE IF NOT EXISTS player_tasks (
            id SERIAL PRIMARY KEY,
            player_id INT REFERENCES players(player_id) ON DELETE CASCADE,
            task_id INT REFERENCES tasks(task_id),
            is_completed BOOLEAN DEFAULT FALSE
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
        print("✅ تم إنشاء الجداول بنجاح")
    except Exception as e:
        conn.rollback()
        print(f"❌ خطأ في إنشاء الجداول: {e}")

init_db()

# ============= المهام الـ 20 =============
TASKS_LIST = [
    {"name": "🔧 إصلاح الأسلاك", "desc": "صلح 3 أسلاك كهربائية", "diff": 1},
    {"name": "🧹 تنظيف الفلتر", "desc": "نظف فلتر الأوكسجين", "diff": 1},
    {"name": "📡 توجيه الطبق", "desc": "وجه طبق الاستقبال", "diff": 2},
    {"name": "💻 فحص البرمجيات", "desc": "شغل برنامج الفحص", "diff": 2},
    {"name": "🧪 تحليل العينة", "desc": "حلل عينة من المختبر", "diff": 2},
    {"name": "⚡ شحن البطارية", "desc": "شحن بطارية الطوارئ", "diff": 1},
    {"name": "🔥 إطفاء الحريق", "desc": "استخدم طفاية الحريق", "diff": 3},
    {"name": "💀 التخلص من الجثة", "desc": "أخفي الجثة في غرفة النفايات", "diff": 3},
    {"name": "🛠 صيانة المحرك", "desc": "أصلح عطل في المحرك الرئيسي", "diff": 2},
    {"name": "📊 تنزيل البيانات", "desc": "حمّل بيانات الرحلة", "diff": 1},
    {"name": "🚀 ضبط الملاحة", "desc": "اضبط مسار السفينة", "diff": 2},
    {"name": "💉 تحضير الدواء", "desc": "جهز أدوية الطوارئ", "diff": 1},
    {"name": "🔬 فحص الأشعة", "desc": "افحص عينة بالأشعة", "diff": 3},
    {"name": "🧊 إذابة الجليد", "desc": "أذب الجليد عن المعدات", "diff": 2},
    {"name": "📡 إرسال إشارة", "desc": "أرسل إشارة استغاثة", "diff": 1},
    {"name": "🔋 تبديل البطارية", "desc": "بدل بطارية الاحتياط", "diff": 2},
    {"name": "🧹 تنظيف الغرفة", "desc": "نظف غرفة المعيشة", "diff": 1},
    {"name": "🛡 تفعيل الدرع", "desc": "فعّل درع الحماية", "diff": 3},
    {"name": "⚙️ معايرة الحساسات", "desc": "عاير حساسات السفينة", "diff": 2},
    {"name": "☢️ التخلص من النفايات", "desc": "تخلص من النفايات المشعة", "diff": 3}
]

# ============= دوال مساعدة =============
def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_or_create_user(user_id, username):
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (user_id, username) VALUES (%s, %s)",
                (user_id, username)
            )
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ خطأ في get_or_create_user: {e}")

def get_game_by_code(code):
    return safe_fetchone("SELECT * FROM games WHERE code = %s", (code,))

def get_players_count(game_id):
    result = safe_fetchone("SELECT COUNT(*) FROM players WHERE game_id = %s", (game_id,))
    return result[0] if result else 0

def assign_tasks(player_id):
    try:
        cursor.execute("SELECT task_id FROM tasks")
        all_tasks = cursor.fetchall()
        if not all_tasks:
            return
        selected_tasks = random.sample(all_tasks, min(3, len(all_tasks)))
        for task in selected_tasks:
            cursor.execute(
                "INSERT INTO player_tasks (player_id, task_id) VALUES (%s, %s)",
                (player_id, task[0])
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ خطأ في assign_tasks: {e}")

def get_player_tasks(player_id):
    return safe_fetchall("""
        SELECT t.name, t.description, pt.is_completed 
        FROM player_tasks pt
        JOIN tasks t ON pt.task_id = t.task_id
        WHERE pt.player_id = %s
        ORDER BY pt.id
    """, (player_id,))

def complete_task(player_id, task_index):
    try:
        cursor.execute("""
            SELECT id, is_completed FROM player_tasks 
            WHERE player_id = %s ORDER BY id LIMIT 1 OFFSET %s
        """, (player_id, task_index))
        task = cursor.fetchone()
        if task and not task[1]:
            cursor.execute("UPDATE player_tasks SET is_completed = TRUE WHERE id = %s", (task[0],))
            conn.commit()
            return True
        return False
    except Exception as e:
        conn.rollback()
        print(f"❌ خطأ في complete_task: {e}")
        return False

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

# ============= أوامر البوت =============

@bot.message_handler(commands=['start'])
def start(message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('join_'):
        code = args[1].replace('join_', '').upper()
        join_with_code(message, code)
        return
    
    bot.reply_to(message, 
        "🎮 **مرحباً في بوت Among Us!**\n\n"
        "📌 الأوامر المتاحة:\n"
        "/new - إنشاء لعبة جديدة\n"
        "/join [كود] - الانضمام للعبة\n"
        "/startgame - بدء اللعبة (للمضيف فقط)\n"
        "/cancel - إلغاء اللعبة الحالية\n"
        "/tasks - عرض مهامي\n"
        "/dotask [رقم] - إنجاز مهمة\n"
        "/kill [@user] - قتل لاعب (للقاتل فقط)\n"
        "/vote [@user] - التصويت لإقصاء لاعب\n"
        "/meeting - دعوة لعقد اجتماع طارئ 🚨\n"
        "/status - حالة اللعبة\n"
        "/help - عرض المساعدة",
        parse_mode='Markdown'
    )

def join_with_code(message, code):
    """دالة مساعدة للانضمام برمز"""
    get_or_create_user(message.from_user.id, message.from_user.username)
    
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
        bot.reply_to(message, "❌ اللعبة ممتلئة! (حد أقصى 10 لاعبين)")
        return
    
    # التحقق من عدم انضمامه مسبقاً
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
    
    # إضافة مهام
    player_result = safe_fetchone("SELECT player_id FROM players WHERE game_id = %s AND user_id = %s", (game_id, message.from_user.id))
    if player_result:
        assign_tasks(player_result[0])
    
    new_count = get_players_count(game_id)
    
    # زر لفتح الخاص
    bot_username = get_bot_username()
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton("🎮 افتح البوت", url=f"https://t.me/{bot_username}?start=join_{code}")
    markup.add(btn)
    
    bot.reply_to(
        message, 
        f"✅ انضممت للعبة `{code}`\n👥 عدد اللاعبين: {new_count}/10",
        parse_mode='Markdown',
        reply_markup=markup
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
    
    bot_username = get_bot_username()
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton("🎮 افتح البوت", url=f"https://t.me/{bot_username}?start=join_{code}")
    markup.add(btn)
    
    bot.reply_to(message, 
        f"✅ **تم إنشاء اللعبة!**\n"
        f"🔑 الكود: `{code}`\n"
        f"👥 عدد اللاعبين: 1/10\n\n"
        f"شارك الكود مع أصدقائك:\n"
        f"/join {code}\n\n"
        f"عند اكتمال العدد استخدم:\n"
        f"/startgame لبدء اللعبة",
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.message_handler(commands=['join'])
def join_game(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ استخدم: /join [كود اللعبة]")
        return
    
    code = args[1].upper()
    join_with_code(message, code)

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
        bot.reply_to(message, f"❌ عدد اللاعبين {players_count}، نحتاج 4 لاعبين على الأقل!")
        return
    
    # اختيار القاتل
    all_players = safe_fetchall("SELECT player_id, user_id FROM players WHERE game_id = %s", (game_id,))
    if not all_players:
        bot.reply_to(message, "❌ لا يوجد لاعبين!")
        return
    
    killer_idx = random.randint(0, len(all_players) - 1)
    killer_player_id, killer_user_id = all_players[killer_idx]
    
    try:
        cursor.execute("UPDATE players SET role = 'killer' WHERE player_id = %s", (killer_player_id,))
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
                f"/dotask [رقم] - إنجاز مهمة",
                parse_mode='Markdown'
            )
            
            if user_id == killer_user_id:
                bot.send_message(
                    user_id,
                    "🔪 **أنت القاتل!**\n"
                    "استخدم /kill @username لقتل لاعب\n"
                    "📌 تذكر: لا تفضح نفسك!"
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
    for i, (name, desc, done) in enumerate(tasks, 1):
        status = "✅" if done else "⏳"
        msg += f"{i}. {status} {name}\n   `{desc}`\n\n"
    
    msg += "\nاستخدم /dotask [الرقم] لإنجاز مهمة"
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
    
    result = safe_fetchone("""
        SELECT p.player_id, g.game_id 
        FROM players p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.user_id = %s AND g.status = 'playing'
    """, (message.from_user.id,))
    
    if not result:
        bot.reply_to(message, "❌ أنت لست في لعبة نشطة!")
        return
    
    player_id = result[0]
    
    if complete_task(player_id, task_num):
        bot.reply_to(message, "✅ **أنجزت المهمة!** +10 نقاط")
        
        if check_all_tasks_completed(result[1]):
            bot.send_message(message.chat.id, "🎉 **فاز الطاقم!** أنجزوا جميع المهام!")
            safe_execute("UPDATE games SET status = 'ended' WHERE game_id = %s", (result[1],))
    else:
        bot.reply_to(message, "❌ المهمة غير موجودة أو منجزة مسبقاً!")

@bot.message_handler(commands=['kill'])
def kill_player(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ استخدم: /kill @username")
        return
    
    target = args[1].replace('@', '')
    
    killer = safe_fetchone("""
        SELECT p.game_id, p.user_id 
        FROM players p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.user_id = %s AND g.status = 'playing' AND p.role = 'killer' AND p.is_alive = TRUE
    """, (message.from_user.id,))
    
    if not killer:
        bot.reply_to(message, "❌ إما أنت لست القاتل، أو لست في لعبة، أو ميت!")
        return
    
    game_id = killer[0]
    
    victim = safe_fetchone("""
        SELECT user_id FROM players 
        WHERE game_id = %s AND username = %s AND is_alive = TRUE AND role != 'killer'
    """, (game_id, target))
    
    if not victim:
        bot.reply_to(message, "❌ اللاعب غير موجود أو ميت أو هو القاتل!")
        return
    
    victim_id = victim[0]
    
    try:
        cursor.execute("UPDATE players SET is_alive = FALSE WHERE user_id = %s AND game_id = %s", (victim_id, game_id))
        cursor.execute(
            "INSERT INTO kills (game_id, killer_id, victim_id) VALUES (%s, %s, %s)",
            (game_id, message.from_user.id, victim_id)
        )
        cursor.execute("UPDATE users SET kills = kills + 1 WHERE user_id = %s", (message.from_user.id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, f"❌ خطأ في القتل: {e}")
        return
    
    bot.send_message(message.chat.id, 
        f"💀 **تم العثور على جثة!**\n"
        f"الضحية: @{target}\n"
        f"🔍 من هو القاتل؟ صوتوا الآن!\n"
        f"استخدم /vote @username للتصويت"
    )
    
    try:
        bot.send_message(victim_id, "💀 **لقد قُتلت!**\nأنت خارج اللعبة. تابع فقط.")
    except:
        pass

@bot.message_handler(commands=['vote'])
def vote(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ استخدم: /vote @username")
        return
    
    target = args[1].replace('@', '')
    bot.reply_to(message, f"🗳️ تم تسجيل صوتك ضد @{target}\n(سيتم تطبيق نظام التصويت في التحديث القادم)")

# ============= 🆕 أمر الاجتماع =============
@bot.message_handler(commands=['meeting'])
def call_meeting(message):
    # التحقق من وجود اللاعب في لعبة نشطة
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
    
    # جلب جميع اللاعبين الأحياء
    alive_players = safe_fetchall("""
        SELECT user_id, username FROM players 
        WHERE game_id = %s AND is_alive = TRUE AND user_id != %s
    """, (game_id, message.from_user.id))
    
    if not alive_players:
        bot.reply_to(message, "❌ لا يوجد لاعبين أحياء غيرك!")
        return
    
    # رسالة الاجتماع
    msg = f"🚨 **اجتماع طارئ!**\n"
    msg += f"👤 دعا للاجتماع: @{message.from_user.username}\n\n"
    msg += "📌 اكتب رأيك أو صوت ضد أحد المشتبه بهم:\n"
    msg += "استخدم /vote @username للتصويت\n\n"
    msg += "✅ **اللاعبين الأحياء:**\n"
    
    for uid, username in alive_players:
        msg += f"- @{username}\n"
    
    # إرسال الاجتماع للجميع (المجموعة أو الخاص)
    bot.send_message(message.chat.id, msg, parse_mode='Markdown')
    
    # إرسال تنبيه خاص لكل لاعب حي
    for uid, username in alive_players:
        try:
            bot.send_message(
                uid,
                f"🚨 **اجتماع طارئ!**\n"
                f"قام @{message.from_user.username} بدعوة الجميع للاجتماع.\n"
                f"استخدم /vote @username للتصويت",
                parse_mode='Markdown'
            )
        except:
            pass
    
    bot.reply_to(message, "✅ تم عقد الاجتماع بنجاح!")

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
    bot.reply_to(message, "🗑️ **تم إلغاء اللعبة!**\nتم حذف جميع البيانات.")

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
                "INSERT INTO tasks (name, description, difficulty) VALUES (%s, %s, %s)",
                (task['name'], task['desc'], task['diff'])
            )
    
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"❌ خطأ في البوت: {e}")
            time.sleep(5)
