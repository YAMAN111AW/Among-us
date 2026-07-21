import telebot
import psycopg2
import random
import string
import time
import threading
from datetime import datetime, timedelta

# ============= إعدادات البوت =============
BOT_TOKEN = "8875334916:AAHq6C2F8ujgnlaLGUW3tR1tgdizFE7SdEw"
DATABASE_URL = "postgresql://postgres:YmIsJsiuuOAQpuwJlLgOXqDVHFaLYpeL@sakura.proxy.rlwy.net:43404/railway"

bot = telebot.TeleBot(BOT_TOKEN)
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# ============= إنشاء الجداول =============
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

# ============= المهام الـ 20 المتنوعة =============
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
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, username) VALUES (%s, %s)",
            (user_id, username)
        )
        conn.commit()

def get_game_by_code(code):
    cursor.execute("SELECT * FROM games WHERE code = %s", (code,))
    return cursor.fetchone()

def get_players_count(game_id):
    cursor.execute("SELECT COUNT(*) FROM players WHERE game_id = %s", (game_id,))
    return cursor.fetchone()[0]

def get_alive_players(game_id):
    cursor.execute("SELECT user_id FROM players WHERE game_id = %s AND is_alive = TRUE", (game_id,))
    return [row[0] for row in cursor.fetchall()]

def get_killer(game_id):
    cursor.execute("SELECT user_id FROM players WHERE game_id = %s AND role = 'killer' AND is_alive = TRUE", (game_id,))
    row = cursor.fetchone()
    return row[0] if row else None

def assign_tasks(player_id):
    # اختيار 3 مهام عشوائية للاعب
    selected_tasks = random.sample(TASKS_LIST, 3)
    for task in selected_tasks:
        cursor.execute(
            "INSERT INTO player_tasks (player_id, task_id) VALUES (%s, %s)",
            (player_id, task['task_id'])
        )

def get_player_tasks(player_id):
    cursor.execute("""
        SELECT t.name, t.description, pt.is_completed 
        FROM player_tasks pt
        JOIN tasks t ON pt.task_id = t.task_id
        WHERE pt.player_id = %s
    """, (player_id,))
    return cursor.fetchall()

def complete_task(player_id, task_index):
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

def check_all_tasks_completed(game_id):
    cursor.execute("""
        SELECT COUNT(*) FROM player_tasks pt
        JOIN players p ON pt.player_id = p.player_id
        WHERE p.game_id = %s AND pt.is_completed = FALSE
    """, (game_id,))
    return cursor.fetchone()[0] == 0

# ============= أوامر البوت =============

# أمر بدء اللعبة
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
        "/dotask [رقم] - إنجاز مهمة\n"
        "/kill [@user] - قتل لاعب (للقاتل فقط)\n"
        "/vote [@user] - التصويت لإقصاء لاعب\n"
        "/status - حالة اللعبة\n"
        "/help - عرض المساعدة",
        parse_mode='Markdown'
    )

# أمر إنشاء لعبة
@bot.message_handler(commands=['new'])
def new_game(message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    
    # التحقق من عدم وجود لعبة نشطة للمستخدم
    cursor.execute("""
        SELECT g.code FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE p.user_id = %s AND g.status IN ('waiting', 'playing')
    """, (message.from_user.id,))
    if cursor.fetchone():
        bot.reply_to(message, "❌ لديك لعبة نشطة حالياً!")
        return
    
    code = generate_code()
    cursor.execute(
        "INSERT INTO games (code, host_id, status) VALUES (%s, %s, 'waiting') RETURNING game_id",
        (code, message.from_user.id)
    )
    game_id = cursor.fetchone()[0]
    
    cursor.execute(
        "INSERT INTO players (game_id, user_id, role) VALUES (%s, %s, 'crewmate')",
        (game_id, message.from_user.id)
    )
    conn.commit()
    
    # إضافة المهام
    cursor.execute("SELECT player_id FROM players WHERE game_id = %s AND user_id = %s", (game_id, message.from_user.id))
    player_id = cursor.fetchone()[0]
    assign_tasks(player_id)
    conn.commit()
    
    bot.reply_to(message, 
        f"✅ **تم إنشاء اللعبة!**\n"
        f"🔑 الكود: `{code}`\n"
        f"👥 عدد اللاعبين: 1/10\n\n"
        f"شارك الكود مع أصدقائك:\n"
        f"/join {code}\n\n"
        f"عند اكتمال العدد استخدم:\n"
        f"/startgame لبدء اللعبة",
        parse_mode='Markdown'
    )

# أمر الانضمام
@bot.message_handler(commands=['join'])
def join_game(message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    
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
        bot.reply_to(message, "❌ اللعبة ممتلئة! (حد أقصى 10 لاعبين)")
        return
    
    # التحقق من عدم انضمامه مسبقاً
    cursor.execute("SELECT * FROM players WHERE game_id = %s AND user_id = %s", (game_id, message.from_user.id))
    if cursor.fetchone():
        bot.reply_to(message, "❌ أنت بالفعل في هذه اللعبة!")
        return
    
    cursor.execute(
        "INSERT INTO players (game_id, user_id, role) VALUES (%s, %s, 'crewmate')",
        (game_id, message.from_user.id)
    )
    conn.commit()
    
    # إضافة مهام للاعب الجديد
    cursor.execute("SELECT player_id FROM players WHERE game_id = %s AND user_id = %s", (game_id, message.from_user.id))
    player_id = cursor.fetchone()[0]
    assign_tasks(player_id)
    conn.commit()
    
    new_count = get_players_count(game_id)
    bot.reply_to(message, f"✅ انضممت للعبة `{code}`\n👥 عدد اللاعبين: {new_count}/10", parse_mode='Markdown')

# أمر بدء اللعبة
@bot.message_handler(commands=['startgame'])
def start_game(message):
    cursor.execute("""
        SELECT g.game_id, g.host_id, g.code FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE p.user_id = %s AND g.status = 'waiting'
    """, (message.from_user.id,))
    game = cursor.fetchone()
    
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
    
    # اختيار القاتل عشوائياً
    cursor.execute("SELECT player_id, user_id FROM players WHERE game_id = %s", (game_id,))
    all_players = cursor.fetchall()
    
    killer_idx = random.randint(0, len(all_players) - 1)
    killer_player_id, killer_user_id = all_players[killer_idx]
    
    cursor.execute("UPDATE players SET role = 'killer' WHERE player_id = %s", (killer_player_id,))
    cursor.execute("UPDATE games SET status = 'playing', started_at = NOW() WHERE game_id = %s", (game_id,))
    conn.commit()
    
    # إرسال الأدوار للجميع
    for player_id, user_id in all_players:
        try:
            role = "قاتل" if user_id == killer_user_id else "عادي"
            emoji = "🔪" if user_id == killer_user_id else "👨‍🚀"
            
            # إرسال رسالة خاصة لكل لاعب
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
        except:
            pass
    
    bot.send_message(message.chat.id, 
        f"🎮 **بدأت اللعبة!**\n"
        f"🔑 الكود: `{code}`\n"
        f"👥 عدد اللاعبين: {players_count}\n\n"
        f"📨 تم إرسال الأدوار في الخاص\n"
        f"🔪 القاتل بينكم... احذروا!",
        parse_mode='Markdown'
    )

# أمر عرض المهام
@bot.message_handler(commands=['tasks'])
def show_tasks(message):
    cursor.execute("""
        SELECT p.player_id, g.game_id, g.status 
        FROM players p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.user_id = %s AND g.status = 'playing'
    """, (message.from_user.id,))
    result = cursor.fetchone()
    
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

# أمر إنجاز مهمة
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
    
    cursor.execute("""
        SELECT p.player_id, g.game_id 
        FROM players p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.user_id = %s AND g.status = 'playing'
    """, (message.from_user.id,))
    result = cursor.fetchone()
    
    if not result:
        bot.reply_to(message, "❌ أنت لست في لعبة نشطة!")
        return
    
    player_id = result[0]
    
    if complete_task(player_id, task_num):
        bot.reply_to(message, "✅ **أنجزت المهمة!** +10 نقاط")
        
        # التحقق من فوز الطاقم
        if check_all_tasks_completed(result[1]):
            bot.send_message(message.chat.id, "🎉 **فاز الطاقم!** أنجزوا جميع المهام!")
            cursor.execute("UPDATE games SET status = 'ended' WHERE game_id = %s", (result[1],))
            conn.commit()
    else:
        bot.reply_to(message, "❌ المهمة غير موجودة أو منجزة مسبقاً!")

# أمر القتل (للقاتل فقط)
@bot.message_handler(commands=['kill'])
def kill_player(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ استخدم: /kill @username")
        return
    
    target = args[1].replace('@', '')
    
    # التحقق من أن المرسل هو القاتل
    cursor.execute("""
        SELECT p.game_id, p.user_id 
        FROM players p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.user_id = %s AND g.status = 'playing' AND p.role = 'killer' AND p.is_alive = TRUE
    """, (message.from_user.id,))
    killer = cursor.fetchone()
    
    if not killer:
        bot.reply_to(message, "❌ إما أنت لست القاتل، أو لست في لعبة، أو ميت!")
        return
    
    game_id = killer[0]
    
    # البحث عن الضحية
    cursor.execute("""
        SELECT user_id FROM players 
        WHERE game_id = %s AND username = %s AND is_alive = TRUE AND role != 'killer'
    """, (game_id, target))
    victim = cursor.fetchone()
    
    if not victim:
        bot.reply_to(message, "❌ اللاعب غير موجود أو ميت أو هو القاتل!")
        return
    
    victim_id = victim[0]
    
    # تنفيذ القتل
    cursor.execute("UPDATE players SET is_alive = FALSE WHERE user_id = %s AND game_id = %s", (victim_id, game_id))
    cursor.execute(
        "INSERT INTO kills (game_id, killer_id, victim_id) VALUES (%s, %s, %s)",
        (game_id, message.from_user.id, victim_id)
    )
    cursor.execute("UPDATE users SET kills = kills + 1 WHERE user_id = %s", (message.from_user.id,))
    conn.commit()
    
    bot.send_message(message.chat.id, 
        f"💀 **تم العثور على جثة!**\n"
        f"الضحية: @{target}\n"
        f"🔍 من هو القاتل؟ صوتوا الآن!\n"
        f"استخدم /vote @username للتصويت"
    )
    
    # إرسال للميت
    try:
        bot.send_message(victim_id, "💀 **لقد قُتلت!**\nأنت خارج اللعبة. تابع فقط.")
    except:
        pass

# أمر التصويت
@bot.message_handler(commands=['vote'])
def vote(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ استخدم: /vote @username")
        return
    
    target = args[1].replace('@', '')
    
    # منطق التصويت (سيتم تطويره لاحقاً)
    bot.reply_to(message, f"🗳️ تم تسجيل صوتك ضد @{target}\n(سيتم تطبيق نظام التصويت في التحديث القادم)")

# أمر حالة اللعبة
@bot.message_handler(commands=['status'])
def game_status(message):
    cursor.execute("""
        SELECT g.code, g.status, 
               COUNT(p.player_id) as total,
               SUM(CASE WHEN p.is_alive = TRUE THEN 1 ELSE 0 END) as alive
        FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE g.status IN ('waiting', 'playing')
        GROUP BY g.game_id
        HAVING COUNT(CASE WHEN p.user_id = %s THEN 1 END) > 0
    """, (message.from_user.id,))
    
    game = cursor.fetchone()
    if not game:
        bot.reply_to(message, "❌ ليس لديك لعبة نشطة!")
        return
    
    code, status, total, alive = game
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

# أمر إلغاء اللعبة
@bot.message_handler(commands=['cancel'])
def cancel_game(message):
    cursor.execute("""
        SELECT g.game_id, g.host_id, g.status 
        FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE p.user_id = %s AND g.status IN ('waiting', 'playing')
    """, (message.from_user.id,))
    game = cursor.fetchone()
    
    if not game:
        bot.reply_to(message, "❌ ليس لديك لعبة نشطة لإلغائها!")
        return
    
    game_id, host_id, status = game
    
    if message.from_user.id != host_id and status == 'playing':
        bot.reply_to(message, "❌ فقط المضيف يمكنه إلغاء اللعبة أثناء اللعب!")
        return
    
    # حذف اللعبة وكل البيانات المرتبطة
    cursor.execute("DELETE FROM games WHERE game_id = %s", (game_id,))
    conn.commit()
    
    bot.reply_to(message, "🗑️ **تم إلغاء اللعبة!**\nتم حذف جميع البيانات.")

# أمر المساعدة
@bot.message_handler(commands=['help'])
def help_command(message):
    start(message)

# ============= تشغيل البوت =============
if __name__ == "__main__":
    print("🤖 البوت شغال...")
    print(f"👥 عدد المهام المسجلة: {len(TASKS_LIST)}")
    
    # إدخال المهام في قاعدة البيانات إذا لم تكن موجودة
    for task in TASKS_LIST:
        cursor.execute("SELECT * FROM tasks WHERE name = %s", (task['name'],))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO tasks (name, description, difficulty) VALUES (%s, %s, %s)",
                (task['name'], task['desc'], task['diff'])
            )
    conn.commit()
    
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
