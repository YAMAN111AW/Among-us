import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import psycopg2
import random
import os

# ================= الإعدادات (جاهزة لـ Railway) =================
# هنا البوت سيأخذ التوكن ورابط قاعدة البيانات من إعدادات Railway مباشرة
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')

bot = telebot.TeleBot(BOT_TOKEN)

# ================= إعداد قاعدة البيانات =================
def get_db_connection():
    # الاتصال بقاعدة البيانات عبر الرابط السحابي
    return psycopg2.connect(DATABASE_URL)

def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    # جدول الألعاب (المجموعات)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            chat_id BIGINT PRIMARY KEY,
            status VARCHAR(20) DEFAULT 'lobby' -- lobby, playing, voting
        )
    ''')
    # جدول اللاعبين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id BIGINT,
            chat_id BIGINT,
            username VARCHAR(100),
            role VARCHAR(20),
            is_alive BOOLEAN DEFAULT TRUE,
            tasks_left INT DEFAULT 3,
            PRIMARY KEY (user_id, chat_id)
        )
    ''')
    # جدول التصويت
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            chat_id BIGINT,
            voter_id BIGINT,
            voted_for_id BIGINT,
            PRIMARY KEY (chat_id, voter_id)
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

setup_database()

# ================= أوامر اللوبي =================

@bot.message_handler(commands=['create'])
def create_game(message):
    chat_id = message.chat.id
    if message.chat.type == 'private':
        bot.reply_to(message, "⚠️ يجب إنشاء اللعبة داخل مجموعة (Group) وليس في الخاص.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM games WHERE chat_id = %s", (chat_id,))
    game = cursor.fetchone()
    
    if game:
        cursor.execute("UPDATE games SET status = 'lobby' WHERE chat_id = %s", (chat_id,))
        cursor.execute("DELETE FROM players WHERE chat_id = %s", (chat_id,))
        cursor.execute("DELETE FROM votes WHERE chat_id = %s", (chat_id,))
    else:
        cursor.execute("INSERT INTO games (chat_id, status) VALUES (%s, 'lobby')", (chat_id,))
        
    conn.commit()
    cursor.close()
    conn.close()
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎮 انضمام للعبة", callback_data=f"join_{chat_id}"))
    bot.send_message(chat_id, "🚀 **تم فتح لوبي Among Us!**\nاضغط على الزر أدناه للانضمام. (يجب أن تكون قد راسلت البوت في الخاص أولاً)", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('join_'))
def join_game(call):
    chat_id = int(call.data.split('_')[1])
    user_id = call.from_user.id
    username = call.from_user.first_name

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT status FROM games WHERE chat_id = %s", (chat_id,))
    game = cursor.fetchone()
    if not game or game[0] != 'lobby':
        bot.answer_callback_query(call.id, "⚠️ اللعبة قد بدأت بالفعل أو غير موجودة!", show_alert=True)
        return

    try:
        cursor.execute("INSERT INTO players (user_id, chat_id, username) VALUES (%s, %s, %s)", (user_id, chat_id, username))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ تم انضمامك بنجاح!")
        
        # تحديث رسالة اللوبي
        cursor.execute("SELECT username FROM players WHERE chat_id = %s", (chat_id,))
        players = cursor.fetchall()
        players_list = "\n".join([f"👤 {p[0]}" for p in players])
        bot.edit_message_text(f"🚀 **لوبي Among Us**\n\nاللاعبين المنضمين ({len(players)}):\n{players_list}\n\nلبدء اللعبة، اكتب /startgame", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")
    except psycopg2.IntegrityError:
        bot.answer_callback_query(call.id, "⚠️ أنت منضم بالفعل!", show_alert=True)
    finally:
        cursor.close()
        conn.close()

# ================= بدء اللعبة وتوزيع الأدوار =================

@bot.message_handler(commands=['startgame'])
def start_game(message):
    chat_id = message.chat.id
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id, username FROM players WHERE chat_id = %s", (chat_id,))
    players = cursor.fetchall()
    
    if len(players) < 4:
        bot.reply_to(message, "⚠️ تحتاج اللعبة إلى 4 لاعبين على الأقل للبدء.")
        return

    # توزيع الأدوار
    impostor = random.choice(players)
    
    for p in players:
        role = 'Impostor' if p[0] == impostor[0] else 'Crewmate'
        cursor.execute("UPDATE players SET role = %s WHERE user_id = %s AND chat_id = %s", (role, p[0], chat_id))
        
        # إرسال الدور في الخاص
        try:
            if role == 'Impostor':
                bot.send_message(p[0], "🔪 **أنت الـ Impostor!**\nمهمتك قتل الطاقم دون أن يكتشفوك. استخدم الأمر `/kill` في المجموعة للقتل.", parse_mode="Markdown")
            else:
                bot.send_message(p[0], "👨‍🚀 **أنت Crewmate!**\nمهمتك إنهاء مهامك واكتشاف المحتال. استخدم الأمر `/task` في المجموعة لإنجاز المهام.", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"⚠️ فشل إرسال الدور إلى {p[1]}. تأكد أنه بدأ محادثة مع البوت في الخاص.")
            return

    cursor.execute("UPDATE games SET status = 'playing' WHERE chat_id = %s", (chat_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    bot.send_message(chat_id, "🚨 **بدأت اللعبة!** 🚨\nتفقّدوا رسائل البوت في الخاص لمعرفة أدواركم.\n- Crewmates: اكتبوا `/task` لإنجاز المهام.\n- Impostor: اكتب `/kill` للقتل.\n- للتبليغ عن جثة: `/report`.")

# ================= المهام والقتل =================

@bot.message_handler(commands=['task'])
def do_task(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT role, is_alive, tasks_left FROM players WHERE user_id = %s AND chat_id = %s", (user_id, chat_id))
    player = cursor.fetchone()
    
    if not player or player[0] != 'Crewmate' or not player[1]:
        bot.reply_to(message, "⚠️ هذا الأمر لأفراد الطاقم الأحياء فقط.")
        return
        
    tasks_left = player[2]
    if tasks_left > 0:
        cursor.execute("UPDATE players SET tasks_left = tasks_left - 1 WHERE user_id = %s AND chat_id = %s", (user_id, chat_id))
        conn.commit()
        tasks_left -= 1
        bot.reply_to(message, f"✅ قمت بإنجاز مهمة! متبقي لك {tasks_left} مهام.")
        check_win_conditions(chat_id)
    else:
        bot.reply_to(message, "✅ لقد أنهيت جميع مهامك!")
        
    cursor.close()
    conn.close()

@bot.message_handler(commands=['kill'])
def kill_player(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT role, is_alive FROM players WHERE user_id = %s AND chat_id = %s", (user_id, chat_id))
    impostor = cursor.fetchone()
    
    if not impostor or impostor[0] != 'Impostor' or not impostor[1]:
        try:
            bot.delete_message(chat_id, message.message_id) # إخفاء الأمر حتى لا ينفضح
        except:
            pass
        return

    # اختيار ضحية عشوائية حية
    cursor.execute("SELECT user_id, username FROM players WHERE chat_id = %s AND is_alive = TRUE AND role = 'Crewmate'", (chat_id,))
    targets = cursor.fetchall()
    
    if targets:
        victim = random.choice(targets)
        cursor.execute("UPDATE players SET is_alive = FALSE WHERE user_id = %s AND chat_id = %s", (victim[0], chat_id))
        conn.commit()
        bot.send_message(chat_id, f"👻 **شخص ما قُتل في الظلام!**")
        check_win_conditions(chat_id)
    
    try:
        bot.delete_message(chat_id, message.message_id)
    except:
        pass
    cursor.close()
    conn.close()

# ================= الاجتماعات والتصويت =================

@bot.message_handler(commands=['report', 'meeting'])
def call_meeting(message):
    chat_id = message.chat.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM games WHERE chat_id = %s", (chat_id,))
    game = cursor.fetchone()
    
    if not game or game[0] != 'playing':
        return
        
    cursor.execute("UPDATE games SET status = 'voting' WHERE chat_id = %s", (chat_id,))
    cursor.execute("DELETE FROM votes WHERE chat_id = %s", (chat_id,))
    
    cursor.execute("SELECT user_id, username FROM players WHERE chat_id = %s AND is_alive = TRUE", (chat_id,))
    alive_players = cursor.fetchall()
    conn.commit()
    
    markup = InlineKeyboardMarkup(row_width=2)
    for p in alive_players:
        markup.add(InlineKeyboardButton(p[1], callback_data=f"vote_{chat_id}_{p[0]}"))
    markup.add(InlineKeyboardButton("⏭️ تخطي التصويت", callback_data=f"vote_{chat_id}_skip"))
    
    bot.send_message(chat_id, "📢 **اجتماع طارئ!**\nتناقشوا ثم صوّتوا لمن تعتقدون أنه المحتال:", reply_markup=markup, parse_mode="Markdown")
    cursor.close()
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('vote_'))
def handle_vote(call):
    data = call.data.split('_')
    chat_id = int(data[1])
    voted_for = data[2]
    voter_id = call.from_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # التأكد أن المصوت حي
    cursor.execute("SELECT is_alive FROM players WHERE user_id = %s AND chat_id = %s", (voter_id, chat_id))
    voter = cursor.fetchone()
    if not voter or not voter[0]:
        bot.answer_callback_query(call.id, "👻 الأشباح لا يمكنهم التصويت!", show_alert=True)
        return
        
    try:
        voted_for_id = int(voted_for) if voted_for != 'skip' else 0
        cursor.execute("INSERT INTO votes (chat_id, voter_id, voted_for_id) VALUES (%s, %s, %s)", (chat_id, voter_id, voted_for_id))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ تم تسجيل تصويتك!")
        check_voting_results(chat_id, call.message.message_id)
    except psycopg2.IntegrityError:
        bot.answer_callback_query(call.id, "⚠️ لقد قمت بالتصويت بالفعل!", show_alert=True)
    finally:
        cursor.close()
        conn.close()

def check_voting_results(chat_id, message_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM players WHERE chat_id = %s AND is_alive = TRUE", (chat_id,))
    alive_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM votes WHERE chat_id = %s", (chat_id,))
    votes_count = cursor.fetchone()[0]
    
    if votes_count >= alive_count:
        # فرز الأصوات
        cursor.execute("SELECT voted_for_id, COUNT(*) as c FROM votes WHERE chat_id = %s GROUP BY voted_for_id ORDER BY c DESC LIMIT 1", (chat_id,))
        top_vote = cursor.fetchone()
        
        if top_vote and top_vote[0] != 0:
            kicked_id = top_vote[0]
            cursor.execute("SELECT username, role FROM players WHERE user_id = %s AND chat_id = %s", (kicked_id, chat_id))
            kicked_player = cursor.fetchone()
            
            cursor.execute("UPDATE players SET is_alive = FALSE WHERE user_id = %s AND chat_id = %s", (kicked_id, chat_id))
            bot.send_message(chat_id, f"💨 تم طرد **{kicked_player[0]}** إلى الفضاء.\nهل كان المحتال؟ {'نعم!' if kicked_player[1] == 'Impostor' else 'لا، كان بريئاً.'}", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "⚖️ تم تخطي التصويت أو تعادلت الأصوات. لم يتم طرد أحد.")
            
        cursor.execute("UPDATE games SET status = 'playing' WHERE chat_id = %s", (chat_id,))
        cursor.execute("DELETE FROM votes WHERE chat_id = %s", (chat_id,))
        conn.commit()
        check_win_conditions(chat_id)
        
    cursor.close()
    conn.close()

# ================= شروط الفوز =================

def check_win_conditions(chat_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT role, is_alive, tasks_left FROM players WHERE chat_id = %s", (chat_id,))
    players = cursor.fetchall()
    
    alive_impostors = sum(1 for p in players if p[0] == 'Impostor' and p[1])
    alive_crewmates = sum(1 for p in players if p[0] == 'Crewmate' and p[1])
    total_tasks = sum(p[2] for p in players if p[0] == 'Crewmate')
    
    game_over = False
    
    if alive_impostors == 0:
        bot.send_message(chat_id, "🎉 **فوز الـ CREWMATES!** 🎉\nتم التخلص من جميع المحتالين.")
        game_over = True
    elif alive_impostors >= alive_crewmates:
        bot.send_message(chat_id, "😈 **فوز الـ IMPOSTORS!** 😈\nالمحتالون سيطروا على السفينة.")
        game_over = True
    elif total_tasks == 0:
        bot.send_message(chat_id, "🛠️ **فوز الـ CREWMATES!** 🛠️\nتم إنجاز جميع المهام بنجاح.")
        game_over = True
        
    if game_over:
        cursor.execute("DELETE FROM games WHERE chat_id = %s", (chat_id,))
        cursor.execute("DELETE FROM players WHERE chat_id = %s", (chat_id,))
        cursor.execute("DELETE FROM votes WHERE chat_id = %s", (chat_id,))
        conn.commit()
        
    cursor.close()
    conn.close()

# ================= تشغيل البوت =================
print("Bot is running...")
bot.infinity_polling()

