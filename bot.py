import telebot
import psycopg2
import random
import string
import time
import threading
import json
import os
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

# ============= إعدادات البوت =============
BOT_TOKEN = "8875334916:AAHq6C2F8ujgnlaLGUW3tR1tgdizFE7SdEw"
DATABASE_URL = "postgresql://postgres:hJjcIviEgMKamNASMYWtKOdmpdzoyPxE@postgres.railway.internal:5432/railway"

bot = telebot.TeleBot(BOT_TOKEN)
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# ============= إعدادات Flask =============
app = Flask(__name__)
CORS(app)

# ============= متغيرات عامة =============
MEETING_ACTIVE = {}
VOTES = {}

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
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(100),
            total_games INT DEFAULT 0,
            wins INT DEFAULT 0,
            kills INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS games (
            game_id SERIAL PRIMARY KEY,
            code VARCHAR(6) UNIQUE NOT NULL,
            host_id BIGINT NOT NULL,
            status VARCHAR(20) DEFAULT 'waiting',
            max_players INT DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
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
            has_knife BOOLEAN DEFAULT FALSE,
            color VARCHAR(20) DEFAULT 'blue',
            pos_x INT DEFAULT 0,
            pos_y INT DEFAULT 0
        );
        
        CREATE TABLE IF NOT EXISTS tasks (
            task_id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            description TEXT,
            task_type VARCHAR(20) DEFAULT 'simple',
            icon VARCHAR(10) DEFAULT '📋',
            difficulty INT DEFAULT 1,
            room VARCHAR(50) DEFAULT 'general'
        );
        
        CREATE TABLE IF NOT EXISTS player_tasks (
            id SERIAL PRIMARY KEY,
            player_id INT REFERENCES players(player_id) ON DELETE CASCADE,
            task_id INT REFERENCES tasks(task_id),
            is_completed BOOLEAN DEFAULT FALSE,
            progress INT DEFAULT 0,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS kills (
            kill_id SERIAL PRIMARY KEY,
            game_id INT REFERENCES games(game_id) ON DELETE CASCADE,
            killer_id BIGINT NOT NULL,
            victim_id BIGINT NOT NULL,
            killed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS meetings (
            meeting_id SERIAL PRIMARY KEY,
            game_id INT REFERENCES games(game_id) ON DELETE CASCADE,
            caller_id BIGINT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            result VARCHAR(20)
        );
        
        CREATE TABLE IF NOT EXISTS votes (
            vote_id SERIAL PRIMARY KEY,
            meeting_id INT REFERENCES meetings(meeting_id) ON DELETE CASCADE,
            voter_id BIGINT NOT NULL,
            target_id BIGINT NOT NULL,
            voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()
        print("✅ Database initialized")
    except Exception as e:
        conn.rollback()
        print(f"❌ DB init error: {e}")

def update_tables():
    try:
        columns = [
            ("players", "has_shield", "BOOLEAN DEFAULT FALSE"),
            ("players", "has_knife", "BOOLEAN DEFAULT FALSE"),
            ("players", "color", "VARCHAR(20) DEFAULT 'blue'"),
            ("players", "pos_x", "INT DEFAULT 0"),
            ("players", "pos_y", "INT DEFAULT 0"),
            ("games", "meeting_active", "BOOLEAN DEFAULT FALSE"),
            ("games", "meeting_end", "TIMESTAMP"),
            ("games", "ended_at", "TIMESTAMP"),
            ("tasks", "task_type", "VARCHAR(20) DEFAULT 'simple'"),
            ("tasks", "icon", "VARCHAR(10) DEFAULT '📋'"),
            ("tasks", "room", "VARCHAR(50) DEFAULT 'general'"),
            ("player_tasks", "progress", "INT DEFAULT 0"),
            ("player_tasks", "started_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("player_tasks", "completed_at", "TIMESTAMP"),
        ]
        
        for table, column, definition in columns:
            try:
                cursor.execute(f"""
                    DO $$ 
                    BEGIN
                        BEGIN
                            ALTER TABLE {table} ADD COLUMN {column} {definition};
                        EXCEPTION
                            WHEN duplicate_column THEN 
                                RAISE NOTICE 'Column {column} already exists';
                        END;
                    END $$;
                """)
                conn.commit()
            except Exception as e:
                print(f"⚠️ Column {column} maybe exists: {e}")
        
        print("✅ Tables updated successfully!")
    except Exception as e:
        conn.rollback()
        print(f"❌ Update tables error: {e}")

init_db()
update_tables()

# ============= المهام =============
TASKS_LIST = [
    {"name": "إصلاح الأسلاك", "desc": "صلح الأسلاك المتقطعة", "type": "simple", "icon": "🔧", "room": "engine", "diff": 1},
    {"name": "تنظيف الفلتر", "desc": "نظف فلتر الأوكسجين", "type": "simple", "icon": "🧹", "room": "storage", "diff": 1},
    {"name": "شحن البطارية", "desc": "شحن بطارية الطوارئ", "type": "simple", "icon": "⚡", "room": "engine", "diff": 1},
    {"name": "تفعيل الدرع", "desc": "فعّل درع الحماية", "type": "simple", "icon": "🛡", "room": "shield", "diff": 2},
    {"name": "معايرة الحساسات", "desc": "عاير حساسات السفينة", "type": "simple", "icon": "⚙️", "room": "control", "diff": 2},
    {"name": "تحليل العينة", "desc": "اختر التحليل الصحيح للعينة", "type": "quiz", "icon": "🔬", "room": "lab", "diff": 2},
    {"name": "فحص البرمجيات", "desc": "اختر البرنامج الصحيح للفحص", "type": "quiz", "icon": "💻", "room": "admin", "diff": 2},
    {"name": "توجيه الإشارة", "desc": "اختر التردد الصحيح للإشارة", "type": "quiz", "icon": "📡", "room": "comms", "diff": 2},
    {"name": "إطفاء الحريق", "desc": "اضغط الأزرار بالترتيب الصحيح", "type": "sequence", "icon": "🔥", "room": "storage", "diff": 3},
    {"name": "صيانة المحرك", "desc": "صلح المحرك باتباع الخطوات", "type": "sequence", "icon": "🛠", "room": "engine", "diff": 3},
    {"name": "التخلص من النفايات", "desc": "اتبع التعليمات للتخلص الآمن", "type": "sequence", "icon": "☢️", "room": "storage", "diff": 3},
    {"name": "تنزيل البيانات", "desc": "حمّل بيانات الرحلة", "type": "simple", "icon": "📊", "room": "admin", "diff": 1},
    {"name": "إرسال إشارة", "desc": "أرسل إشارة استغاثة", "type": "simple", "icon": "📡", "room": "comms", "diff": 1},
    {"name": "تحضير الدواء", "desc": "جهز أدوية الطوارئ", "type": "simple", "icon": "💉", "room": "medbay", "diff": 1},
    {"name": "إذابة الجليد", "desc": "أذب الجليد عن المعدات", "type": "simple", "icon": "🧊", "room": "storage", "diff": 2},
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
    return safe_fetchall("SELECT user_id, username, color FROM players WHERE game_id = %s AND is_alive = TRUE", (game_id,))

def get_all_players(game_id):
    return safe_fetchall("SELECT user_id, username, role, is_alive, color FROM players WHERE game_id = %s", (game_id,))

def get_killer(game_id):
    result = safe_fetchone("SELECT user_id FROM players WHERE game_id = %s AND role = 'killer' AND is_alive = TRUE", (game_id,))
    return result[0] if result else None

def assign_tasks(player_id):
    try:
        cursor.execute("SELECT task_id, task_type FROM tasks")
        all_tasks = cursor.fetchall()
        if not all_tasks:
            return
        selected = random.sample(all_tasks, min(5, len(all_tasks)))
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
        SELECT t.task_id, t.name, t.description, t.task_type, t.icon, t.room,
               pt.is_completed, pt.progress
        FROM player_tasks pt
        JOIN tasks t ON pt.task_id = t.task_id
        WHERE pt.player_id = %s
        ORDER BY pt.id
    """, (player_id,))

def get_player_by_user_id(game_id, user_id):
    return safe_fetchone(
        "SELECT player_id, role, is_alive, has_shield, has_knife FROM players WHERE game_id = %s AND user_id = %s",
        (game_id, user_id)
    )

def complete_task(player_id, task_id):
    try:
        cursor.execute(
            "UPDATE player_tasks SET is_completed = TRUE, progress = 100, completed_at = NOW() WHERE player_id = %s AND task_id = %s AND is_completed = FALSE",
            (player_id, task_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"❌ Error in complete_task: {e}")
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

def is_meeting_active(game_id):
    if game_id not in MEETING_ACTIVE:
        return False
    if datetime.now() > MEETING_ACTIVE[game_id]['end_time']:
        del MEETING_ACTIVE[game_id]
        return False
    return True

def get_meeting_time_left(game_id):
    if game_id not in MEETING_ACTIVE:
        return 0
    remaining = (MEETING_ACTIVE[game_id]['end_time'] - datetime.now()).total_seconds()
    return max(0, int(remaining))

def start_meeting(game_id, chat_id, caller_id):
    MEETING_ACTIVE[game_id] = {
        'end_time': datetime.now() + timedelta(seconds=90),
        'votes': {},
        'voter_ids': [],
        'chat_id': chat_id,
        'caller_id': caller_id
    }
    VOTES[game_id] = {}
    safe_execute("UPDATE games SET meeting_active = TRUE, meeting_end = NOW() + INTERVAL '90 seconds' WHERE game_id = %s", (game_id,))
    
    cursor.execute("INSERT INTO meetings (game_id, caller_id) VALUES (%s, %s) RETURNING meeting_id", (game_id, caller_id))
    meeting_id = cursor.fetchone()[0]
    conn.commit()
    MEETING_ACTIVE[game_id]['meeting_id'] = meeting_id
    
    threading.Timer(90.0, end_meeting, args=[game_id]).start()
    return True

def end_meeting(game_id):
    if game_id in MEETING_ACTIVE:
        votes = MEETING_ACTIVE[game_id].get('votes', {})
        meeting_id = MEETING_ACTIVE[game_id].get('meeting_id')
        
        if votes:
            max_votes = max(votes.values())
            targets = [uid for uid, v in votes.items() if v == max_votes]
            if len(targets) == 1:
                target_id = targets[0]
                safe_execute("UPDATE players SET is_alive = FALSE WHERE user_id = %s AND game_id = %s", (target_id, game_id))
                chat_id = MEETING_ACTIVE[game_id]['chat_id']
                target_info = safe_fetchone("SELECT username FROM players WHERE user_id = %s", (target_id,))
                target_name = target_info[0] if target_info else 'لاعب'
                bot.send_message(chat_id, f"🗳️ **تم إقصاء @{target_name}**")
                if meeting_id:
                    cursor.execute("UPDATE meetings SET ended_at = NOW(), result = 'eliminated' WHERE meeting_id = %s", (meeting_id,))
                    conn.commit()
                check_game_winner(game_id, chat_id)
            else:
                chat_id = MEETING_ACTIVE[game_id]['chat_id']
                bot.send_message(chat_id, "⚖️ **تعادل في الأصوات!**")
                if meeting_id:
                    cursor.execute("UPDATE meetings SET ended_at = NOW(), result = 'tie' WHERE meeting_id = %s", (meeting_id,))
                    conn.commit()
        else:
            chat_id = MEETING_ACTIVE[game_id]['chat_id']
            bot.send_message(chat_id, "⏭️ **لم يصوت أحد!**")
            if meeting_id:
                cursor.execute("UPDATE meetings SET ended_at = NOW(), result = 'skipped' WHERE meeting_id = %s", (meeting_id,))
                conn.commit()
        
        del MEETING_ACTIVE[game_id]
        if game_id in VOTES:
            del VOTES[game_id]
        safe_execute("UPDATE games SET meeting_active = FALSE WHERE game_id = %s", (game_id,))

def check_game_winner(game_id, chat_id):
    alive = get_alive_players(game_id)
    killer = get_killer(game_id)
    if not killer:
        bot.send_message(chat_id, "🎉 **فاز الطاقم!** القاتل مات!")
        safe_execute("UPDATE games SET status = 'ended', ended_at = NOW() WHERE game_id = %s", (game_id,))
        return True
    if len(alive) <= 2:
        bot.send_message(chat_id, "🔪 **فاز القاتل!** لا يوجد عدد كافٍ من الطاقم!")
        safe_execute("UPDATE games SET status = 'ended', ended_at = NOW() WHERE game_id = %s", (game_id,))
        return True
    if check_all_tasks_completed(game_id):
        bot.send_message(chat_id, "🎉 **فاز الطاقم!** أنجزوا جميع المهام!")
        safe_execute("UPDATE games SET status = 'ended', ended_at = NOW() WHERE game_id = %s", (game_id,))
        return True
    return False

# ============================================================
# HTML للعبة (مضمن في الكود)
# ============================================================
GAME_HTML = """
<!DOCTYPE html>
<html lang="ar">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Among Us</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Segoe UI',sans-serif;background:#1a1a2e;color:#fff;overflow:hidden;height:100vh;width:100vw;touch-action:none;}
#app{display:flex;flex-direction:column;height:100vh;max-width:100vw;}
#topBar{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:#16213e;border-bottom:2px solid #0f3460;min-height:44px;flex-shrink:0;}
#gameCode{font-weight:bold;color:#2ecc71;font-size:13px;}
#gameStatus{font-size:11px;padding:3px 10px;border-radius:20px;background:#2ecc71;color:#fff;}
#gameStatus.waiting{background:#f39c12;}
#gameStatus.playing{background:#2ecc71;}
#gameStatus.ended{background:#e74c3c;}
#mapContainer{flex:1;position:relative;background:#0a1a2a;overflow:hidden;min-height:0;}
#mapCanvas{width:100%;height:100%;display:block;touch-action:none;}
#bottomPanel{display:flex;flex-direction:column;background:#16213e;border-top:2px solid #0f3460;max-height:45vh;flex-shrink:0;}
#bottomTabs{display:flex;background:#1a1a2e;border-bottom:1px solid #0f3460;}
.tab-btn{flex:1;padding:8px;border:none;background:transparent;color:#666;font-weight:bold;cursor:pointer;transition:0.3s;font-size:12px;}
.tab-btn.active{color:#fff;border-bottom:3px solid #2ecc71;}
#tabContent{padding:8px 12px;overflow-y:auto;max-height:30vh;flex:1;}
.task-item{display:flex;align-items:center;gap:8px;padding:6px 10px;background:#0f3460;border-radius:6px;margin-bottom:4px;cursor:pointer;transition:0.3s;font-size:12px;}
.task-item:hover{background:#1a4a7a;}
.task-item.completed{opacity:0.5;text-decoration:line-through;}
.task-item .task-icon{font-size:16px;}
.task-item .task-name{flex:1;}
.task-item .task-status{font-size:11px;}
.player-item{display:flex;align-items:center;gap:8px;padding:4px 8px;border-radius:6px;margin-bottom:3px;font-size:12px;}
.player-avatar{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:10px;border:2px solid #666;flex-shrink:0;}
.player-avatar.alive{border-color:#2ecc71;}
.player-avatar.dead{opacity:0.4;border-color:#e74c3c;}
.player-avatar.killer{border-color:#e74c3c;box-shadow:0 0 15px #e74c3c;}
.player-avatar.me{border-color:#f39c12;}
.player-name{flex:1;}
#actionButtons{display:flex;gap:6px;padding:6px 12px;flex-shrink:0;}
.action-btn{flex:1;padding:8px;border:none;border-radius:8px;font-weight:bold;cursor:pointer;transition:0.3s;font-size:12px;color:#fff;}
.action-btn:active{transform:scale(0.95);}
.action-btn:disabled{opacity:0.5;cursor:not-allowed;}
.btn-meeting{background:#e74c3c;}
.btn-kill{background:#c0392b;display:none;}
.btn-refresh{background:#3498db;}
#meetingOverlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.92);z-index:1000;justify-content:center;align-items:center;flex-direction:column;padding:20px;}
#meetingOverlay.active{display:flex;}
#meetingBox{background:#1a1a2e;padding:20px;border-radius:16px;width:100%;max-width:400px;text-align:center;border:2px solid #e74c3c;}
#meetingTimer{font-size:40px;color:#e74c3c;margin:10px 0;font-weight:bold;}
#voteButtons{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:10px 0;}
.vote-btn{padding:8px;border:none;border-radius:8px;cursor:pointer;background:#0f3460;color:#fff;transition:0.3s;font-size:11px;}
.vote-btn:hover{background:#1a4a7a;}
.vote-btn:disabled{opacity:0.3;}
#skipVoteBtn{padding:8px 24px;border:none;border-radius:8px;cursor:pointer;background:#666;color:#fff;font-weight:bold;}
#notification{position:fixed;top:10px;left:50%;transform:translateX(-50%);padding:10px 20px;border-radius:10px;display:none;z-index:2000;font-weight:bold;font-size:13px;max-width:90%;text-align:center;box-shadow:0 4px 15px rgba(0,0,0,0.5);}
#notification.success{background:#2ecc71;color:#fff;}
#notification.error{background:#e74c3c;color:#fff;}
#notification.warning{background:#f39c12;color:#fff;}
#notification.info{background:#3498db;color:#fff;}
#deathOverlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:500;justify-content:center;align-items:center;flex-direction:column;}
#deathOverlay.active{display:flex;}
#deathOverlay h1{font-size:40px;color:#e74c3c;}
#deathOverlay p{font-size:16px;color:#aaa;}
@media(max-width:500px){.task-item{font-size:11px;padding:4px 8px;}#voteButtons{grid-template-columns:1fr 1fr;}#meetingTimer{font-size:32px;}}
</style>
</head>
<body>
<div id="notification"></div>
<div id="app">
<div id="topBar"><span id="gameCode">🎮 {{ game_code }}</span><span id="gameStatus">⏳ جارية</span><span style="font-size:11px;color:#888;" id="playerInfo">{{ username }} | <span id="myRoleText">عادي</span></span></div>
<div id="mapContainer"><canvas id="mapCanvas"></canvas></div>
<div id="bottomPanel">
<div id="bottomTabs"><button class="tab-btn active" data-tab="tasks">📋 مهامي</button><button class="tab-btn" data-tab="players">👥 لاعبين</button></div>
<div id="tabContent"><div id="tasksTab"><div id="tasksList"></div></div><div id="playersTab" style="display:none;"><div id="playersList"></div></div></div>
<div id="actionButtons"><button class="action-btn btn-meeting" id="meetingBtn" onclick="callMeeting()">🚨 اجتماع</button><button class="action-btn btn-kill" id="killBtn" onclick="openKillMenu()">🔪 قتل</button><button class="action-btn btn-refresh" onclick="refreshGame()">🔄</button></div>
</div>
</div>
<div id="meetingOverlay"><div id="meetingBox"><h2 id="meetingTitle">🚨 اجتماع طارئ</h2><div id="meetingCaller">دعا: ...</div><div id="meetingTimer">90</div><p style="color:#aaa;font-size:13px;">صوت على من تريد إقصاءه:</p><div id="voteButtons"></div><button id="skipVoteBtn" onclick="skipVote()">⏭️ تخطي</button></div></div>
<div id="deathOverlay"><h1>💀</h1><p>لقد مت! لا يمكنك اللعب.</p><p style="font-size:13px;color:#666;">تابع اللعبة فقط</p></div>
<script>
const GAME_CODE="{{ game_code }}", USER_ID={{ user_id }}, USERNAME="{{ username }}", MY_ROLE="{{ role }}", IS_ALIVE={{ 'true' if is_alive else 'false' }}, HAS_SHIELD={{ 'true' if has_shield else 'false' }}, HAS_KNIFE={{ 'true' if has_knife else 'false' }}, BOT_USERNAME="{{ bot_username }}";
const INITIAL_PLAYERS={{ players|safe }}, INITIAL_TASKS={{ tasks|safe }}, KILLER_ID={{ killer_id if killer_id else 'null' }}, IS_MEETING={{ 'true' if is_meeting else 'false' }}, MEETING_TIME={{ meeting_time }};
let gameState={players:INITIAL_PLAYERS||[],tasks:INITIAL_TASKS||[],killerId:KILLER_ID,isMeeting:IS_MEETING,meetingTime:MEETING_TIME,isAlive:IS_ALIVE,role:MY_ROLE,hasShield:HAS_SHIELD,hasKnife:HAS_KNIFE,meetingVotes:{},myId:USER_ID,username:USERNAME,code:GAME_CODE,status:'playing'};
function showNotification(m,t='info',d=3000){const e=document.getElementById('notification');e.textContent=m;e.className=t;e.style.display='block';clearTimeout(e._timeout);e._timeout=setTimeout(()=>{e.style.display='none'},d);}
async function fetchGameState(){try{const r=await fetch('/api/game/'+GAME_CODE+'/state?user_id='+USER_ID);if(!r.ok)throw new Error('فشل جلب البيانات');const d=await r.json();gameState.players=d.players||[];gameState.tasks=d.tasks||[];gameState.killerId=d.killerId;gameState.isMeeting=d.isMeeting||false;gameState.meetingTime=d.meetingTime||0;gameState.isAlive=d.isAlive;gameState.role=d.role;gameState.status=d.status||'playing';gameState.meetingVotes=d.meetingVotes||{};renderPlayers();renderTasks();updateUI();updateMap();return d;}catch(e){console.error(e);return null;}}
function renderPlayers(){const c=document.getElementById('playersList');c.innerHTML='';const s=[...gameState.players].sort((a,b)=>{if(a.isAlive===b.isAlive)return 0;return a.isAlive?-1:1;});s.forEach(p=>{const d=document.createElement('div');d.className='player-item';const a=document.createElement('div');a.className='player-avatar '+(p.isAlive?'alive':'dead')+(p.id===gameState.killerId?' killer':'')+(p.id===USER_ID?' me':'');a.style.background=p.color||'#666';a.textContent=(p.username||'?')[0].toUpperCase();const n=document.createElement('span');n.className='player-name';n.textContent=p.username+(p.id===USER_ID?' (أنت)':'');const r=document.createElement('span');r.className='player-role '+(p.role==='killer'?'killer':'crewmate');r.textContent=p.role==='killer'?'🔪 قاتل':'👨‍🚀 عادي';const si=document.createElement('span');si.textContent=p.isAlive?'🟢':'💀';d.appendChild(a);d.appendChild(n);d.appendChild(r);d.appendChild(si);c.appendChild(d);});}
function renderTasks(){const c=document.getElementById('tasksList');c.innerHTML='';if(!gameState.tasks||gameState.tasks.length===0){c.innerHTML='<div style="color:#888;text-align:center;padding:10px;">✅ كل المهام منجزة!</div>';return;}gameState.tasks.forEach((t,i)=>{const d=document.createElement('div');d.className='task-item'+(t.completed?' completed':'');const ic=document.createElement('span');ic.className='task-icon';ic.textContent=t.icon||'📋';const n=document.createElement('span');n.className='task-name';n.textContent=t.name;const s=document.createElement('span');s.className='task-status';s.textContent=t.completed?'✅':(t.progress>0?t.progress+'%':'⏳');d.appendChild(ic);d.appendChild(n);d.appendChild(s);if(!t.completed&&gameState.isAlive&&!gameState.isMeeting){d.style.cursor='pointer';d.onclick=()=>doTask(t.id,i);}c.appendChild(d);});}
function updateUI(){const s=document.getElementById('gameStatus');if(gameState.status==='waiting'){s.textContent='⏳ انتظار';s.className='waiting';}else if(gameState.status==='playing'){s.textContent='🎮 جارية';s.className='playing';}else{s.textContent='🏁 انتهت';s.className='ended';}document.getElementById('myRoleText').textContent=!gameState.isAlive?'💀 ميت':(gameState.role==='killer'?'🔪 قاتل':'👨‍🚀 عادي');const kb=document.getElementById('killBtn');kb.style.display=(gameState.role==='killer'&&gameState.isAlive&&!gameState.isMeeting)?'block':'none';document.getElementById('meetingBtn').disabled=gameState.isMeeting||!gameState.isAlive;document.getElementById('killBtn').disabled=gameState.isMeeting||!gameState.isAlive;document.getElementById('deathOverlay').classList.toggle('active',!gameState.isAlive&&gameState.status==='playing');const mo=document.getElementById('meetingOverlay');if(gameState.isMeeting){mo.classList.add('active');document.getElementById('meetingTimer').textContent=gameState.meetingTime||90;updateVoteButtons();}else{mo.classList.remove('active');}}
function updateVoteButtons(){const c=document.getElementById('voteButtons');c.innerHTML='';const alive=gameState.players.filter(p=>p.isAlive&&p.id!==USER_ID);if(alive.length===0){c.innerHTML='<p style="color:#888;">لا يوجد لاعبين</p>';return;}alive.forEach(p=>{const b=document.createElement('button');b.className='vote-btn';b.textContent='@'+p.username;b.onclick=()=>sendVote(p.id);c.appendChild(b);});}
async function doTask(tid,i){if(!gameState.isAlive){showNotification('💀 أنت ميت!','error');return;}if(gameState.isMeeting){showNotification('❌ لا يمكن تنفيذ المهام أثناء الاجتماع!','error');return;}try{const r=await fetch('/api/game/'+GAME_CODE+'/task/'+tid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({userId:USER_ID})});const d=await r.json();if(d.success){showNotification(d.message||'✅ تم إنجاز المهمة!','success');if(d.gameWon)showNotification('🎉 فاز الطاقم!','success',5000);await fetchGameState();}else{showNotification(d.error||'❌ فشل إنجاز المهمة','error');}}catch(e){showNotification('❌ خطأ في الاتصال','error');console.error(e);}}
async function callMeeting(){if(!gameState.isAlive){showNotification('💀 أنت ميت!','error');return;}if(gameState.role==='killer'){showNotification('🔪 القاتل لا يستطيع دعوة اجتماع!','error');return;}if(gameState.isMeeting){showNotification('❌ يوجد اجتماع نشط!','error');return;}try{const r=await fetch('/api/game/'+GAME_CODE+'/meeting?chat_id='+(window.Telegram?.WebApp?.chatId||0),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({userId:USER_ID,username:USERNAME})});const d=await r.json();if(d.success){showNotification('🚨 تم عقد الاجتماع!','success');await fetchGameState();}else{showNotification(d.error||'❌ فشل عقد الاجتماع','error');}}catch(e){showNotification('❌ خطأ في الاتصال','error');console.error(e);}}
async function sendVote(tid){try{const r=await fetch('/api/game/'+GAME_CODE+'/vote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({voterId:USER_ID,targetId:tid})});const d=await r.json();if(d.success){showNotification('🗳️ تم تسجيل صوتك!','success');document.querySelectorAll('.vote-btn').forEach(b=>b.disabled=true);await fetchGameState();}else{showNotification(d.error||'❌ فشل التصويت','error');}}catch(e){showNotification('❌ خطأ في الاتصال','error');console.error(e);}}
function skipVote(){document.getElementById('meetingOverlay').classList.remove('active');showNotification('⏭️ تم تخطي التصويت','info');}
function openKillMenu(){if(!gameState.isAlive||gameState.role!=='killer'){showNotification('❌ أنت لست القاتل أو ميت!','error');return;}if(gameState.isMeeting){showNotification('❌ لا يمكن القتل أثناء الاجتماع!','error');return;}const alive=gameState.players.filter(p=>p.isAlive&&p.id!==USER_ID);if(alive.length===0){showNotification('❌ لا يوجد ضحايا!','error');return;}const victim=prompt('🔪 اختر ضحية:\n'+alive.map(p=>'@'+p.username).join('\\n')+'\\n\\nاكتب اسم المستخدم:');if(victim){const target=alive.find(p=>p.username.toLowerCase()===victim.replace('@','').toLowerCase());if(target)sendKill(target.id);else showNotification('❌ اللاعب غير موجود','error');}}
async function sendKill(tid){try{const r=await fetch('/api/game/'+GAME_CODE+'/kill?chat_id='+(window.Telegram?.WebApp?.chatId||0),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({killerId:USER_ID,victimId:tid})});const d=await r.json();if(d.success){showNotification(d.message||'💀 قتل!','success');await fetchGameState();}else if(d.shielded){showNotification(d.message||'🛡️ درع!','warning');}else{showNotification(d.error||'❌ فشل القتل','error');}}catch(e){showNotification('❌ خطأ في الاتصال','error');console.error(e);}}
async function refreshGame(){showNotification('🔄 جاري التحديث...','info');await fetchGameState();showNotification('✅ تم التحديث','success');}
const canvas=document.getElementById('mapCanvas'),ctx=canvas.getContext('2d');let mapW=0,mapH=0;
function resizeCanvas(){const c=document.getElementById('mapContainer');canvas.width=c.clientWidth*devicePixelRatio;canvas.height=c.clientHeight*devicePixelRatio;mapW=canvas.width;mapH=canvas.height;ctx.scale(devicePixelRatio,devicePixelRatio);updateMap();}
const ROOMS=[{x:.05,y:.05,w:.20,h:.25,label:'🛸 المحرك',color:'#1a4a7a'},{x:.28,y:.05,w:.20,h:.25,label:'🔬 المختبر',color:'#1a4a7a'},{x:.51,y:.05,w:.20,h:.25,label:'🛡 الدرع',color:'#1a4a7a'},{x:.74,y:.05,w:.20,h:.25,label:'📡 الاتصالات',color:'#1a4a7a'},{x:.05,y:.35,w:.20,h:.25,label:'🧹 المخزن',color:'#1a4a7a'},{x:.28,y:.35,w:.20,h:.25,label:'🎮 التحكم',color:'#1a4a7a'},{x:.51,y:.35,w:.20,h:.25,label:'💊 المستشفى',color:'#1a4a7a'},{x:.74,y:.35,w:.20,h:.25,label:'💀 الموتى',color:'#2a1a3a'}];
function updateMap(){const w=canvas.width/devicePixelRatio,h=canvas.height/devicePixelRatio;ctx.clearRect(0,0,w,h);const g=ctx.createRadialGradient(w/2,h/2,0,w/2,h/2,Math.max(w,h));g.addColorStop(0,'#1a2a4a');g.addColorStop(1,'#0a1a2a');ctx.fillStyle=g;ctx.fillRect(0,0,w,h);ROOMS.forEach(r=>{const x=r.x*w,y=r.y*h,rw=r.w*w,rh=r.h*h;ctx.fillStyle=r.color;ctx.shadowColor='rgba(46,204,113,0.1)';ctx.shadowBlur=15;ctx.beginPath();ctx.roundRect(x,y,rw,rh,8);ctx.fill();ctx.shadowBlur=0;ctx.fillStyle='#fff';ctx.font=(Math.min(14,w*.018))+'px Arial';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(r.label,x+rw/2,y+rh/2);});gameState.players.forEach(p=>{if(!p.isAlive)return;const x=(p.posX||.3+Math.random()*.4)*w,y=(p.posY||.3+Math.random()*.4)*h,r=Math.min(14,w*.025),isK=p.id===gameState.killerId,isM=p.id===USER_ID;ctx.shadowColor=isK?'rgba(231,76,60,0.5)':'rgba(46,204,113,0.3)';ctx.shadowBlur=20;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=isK?'#e74c3c':(isM?'#f39c12':'#2ecc71');ctx.fill();ctx.shadowBlur=0;ctx.strokeStyle='#fff';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#fff';ctx.font=(Math.min(10,w*.016))+'px Arial';ctx.textAlign='center';ctx.textBaseline='bottom';ctx.fillText(p.username,x,y-r-3);if(isK){ctx.font=(Math.min(12,w*.02))+'px Arial';ctx.textBaseline='top';ctx.fillText('🔪',x+r+4,y-r);}if(isM){ctx.font=(Math.min(10,w*.016))+'px Arial';ctx.textBaseline='top';ctx.fillStyle='#f39c12';ctx.fillText('⭐',x-r-12,y-r);}});}
CanvasRenderingContext2D.prototype.roundRect=function(x,y,w,h,r){if(r>w/2)r=w/2;if(r>h/2)r=h/2;this.moveTo(x+r,y);this.lineTo(x+w-r,y);this.quadraticCurveTo(x+w,y,x+w,y+r);this.lineTo(x+w,y+h-r);this.quadraticCurveTo(x+w,y+h,x+w-r,y+h);this.lineTo(x+r,y+h);this.quadraticCurveTo(x,y+h,x,y+h-r);this.lineTo(x,y+r);this.quadraticCurveTo(x,y,x+r,y);this.closePath();return this;};
let touchStartX=0,touchStartY=0,isDragging=false;
canvas.addEventListener('touchstart',e=>{e.preventDefault();const t=e.touches[0],rect=canvas.getBoundingClientRect();touchStartX=(t.clientX-rect.left)*(canvas.width/rect.width/devicePixelRatio);touchStartY=(t.clientY-rect.top)*(canvas.height/rect.height/devicePixelRatio);isDragging=false;},{passive:false});
canvas.addEventListener('touchmove',e=>{e.preventDefault();if(e.touches.length===1){isDragging=true;const t=e.touches[0],rect=canvas.getBoundingClientRect(),x=(t.clientX-rect.left)*(canvas.width/rect.width/devicePixelRatio),y=(t.clientY-rect.top)*(canvas.height/rect.height/devicePixelRatio),w=canvas.width/devicePixelRatio,h=canvas.height/devicePixelRatio,posX=Math.max(0,Math.min(1,x/w)),posY=Math.max(0,Math.min(1,y/h));fetch('/api/game/'+GAME_CODE+'/position',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({userId:USER_ID,posX,posY})}).catch(e=>console.error(e));}},{passive:false});
canvas.addEventListener('touchend',e=>{if(!isDragging)showNotification('📍 انقر على مهمة من القائمة','info');isDragging=false;});
document.querySelectorAll('.tab-btn').forEach(b=>{b.addEventListener('click',function(){document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');const t=this.dataset.tab;document.getElementById('tasksTab').style.display=t==='tasks'?'block':'none';document.getElementById('playersTab').style.display=t==='players'?'block':'none';});});
window.addEventListener('load',()=>{resizeCanvas();fetchGameState().then(()=>{updateUI();updateMap();});setInterval(()=>{fetchGameState().catch(e=>console.error(e));},5000);window.addEventListener('resize',resizeCanvas);});
if(window.Telegram&&window.Telegram.WebApp){window.Telegram.WebApp.ready();window.Telegram.WebApp.expand();}
console.log('🎮 Among Us WebView loaded!');
</script>
</body>
</html>
"""

# ============================================================
# Flask Routes (API للـ WebView)
# ============================================================

@app.route('/web/<code>')
def web_game(code):
    """صفحة اللعبة في الـ WebView"""
    game = get_game_by_code(code)
    if not game:
        return "اللعبة غير موجودة!", 404
    
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return "يرجى تسجيل الدخول!", 401
    
    player = get_player_by_user_id(game[0], user_id)
    if not player:
        return "أنت لست في هذه اللعبة!", 403
    
    player_id, role, is_alive, has_shield, has_knife = player
    
    all_players = get_all_players(game[0])
    tasks = get_player_tasks(player_id)
    
    players_data = []
    for p in all_players:
        players_data.append({
            'id': p[0], 'username': p[1], 'role': p[2],
            'isAlive': p[3], 'color': p[4] if p[4] else 'blue'
        })
    
    tasks_data = []
    for t in tasks:
        tasks_data.append({
            'id': t[0], 'name': t[1], 'description': t[2],
            'type': t[3], 'icon': t[4] if t[4] else '📋',
            'room': t[5] if t[5] else 'general',
            'completed': t[6], 'progress': t[7] if t[7] else 0
        })
    
    return render_template_string(GAME_HTML,
        game_code=code,
        user_id=user_id,
        username=request.args.get('username', 'Player'),
        role=role,
        is_alive=is_alive,
        has_shield=has_shield,
        has_knife=has_knife,
        bot_username=get_bot_username(),
        players=json.dumps(players_data),
        tasks=json.dumps(tasks_data),
        killer_id=get_killer(game[0]),
        is_meeting=is_meeting_active(game[0]),
        meeting_time=get_meeting_time_left(game[0])
    )

@app.route('/api/game/<code>/state')
def api_game_state(code):
    game = get_game_by_code(code)
    if not game:
        return jsonify({'error': 'Game not found'}), 404
    
    game_id = game[0]
    user_id = request.args.get('user_id', type=int)
    
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    
    players = safe_fetchall("""
        SELECT user_id, username, role, is_alive, color, pos_x, pos_y
        FROM players WHERE game_id = %s
    """, (game_id,))
    
    player = get_player_by_user_id(game_id, user_id)
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    
    tasks = get_player_tasks(player[0])
    
    votes_data = {}
    if game_id in MEETING_ACTIVE:
        votes_data = MEETING_ACTIVE[game_id].get('votes', {})
    
    return jsonify({
        'status': game[3],
        'players': [{'id': p[0], 'username': p[1], 'role': p[2], 'isAlive': p[3], 'color': p[4] if p[4] else 'blue', 'posX': p[5] if p[5] else 0, 'posY': p[6] if p[6] else 0} for p in players],
        'tasks': [{'id': t[0], 'name': t[1], 'description': t[2], 'type': t[3], 'icon': t[4] if t[4] else '📋', 'room': t[5] if t[5] else 'general', 'completed': t[6], 'progress': t[7] if t[7] else 0} for t in tasks],
        'killerId': get_killer(game_id),
        'isMeeting': is_meeting_active(game_id),
        'meetingTime': get_meeting_time_left(game_id),
        'meetingVotes': votes_data,
        'isAlive': player[2],
        'role': player[1]
    })

@app.route('/api/game/<code>/task/<int:task_id>', methods=['POST'])
def api_complete_task(code, task_id):
    data = request.json
    user_id = data.get('userId')
    
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    
    game = get_game_by_code(code)
    if not game:
        return jsonify({'error': 'Game not found'}), 404
    
    game_id = game[0]
    
    if is_meeting_active(game_id):
        return jsonify({'error': 'لا يمكن تنفيذ المهام أثناء الاجتماع!'}), 400
    
    player = get_player_by_user_id(game_id, user_id)
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    
    player_id, role, is_alive, has_shield, has_knife = player
    
    if not is_alive:
        return jsonify({'error': 'أنت ميت!'}), 400
    
    if complete_task(player_id, task_id):
        if check_all_tasks_completed(game_id):
            chat_id = MEETING_ACTIVE.get(game_id, {}).get('chat_id', 0)
            if chat_id:
                bot.send_message(chat_id, "🎉 **فاز الطاقم!** أنجزوا جميع المهام!")
            safe_execute("UPDATE games SET status = 'ended', ended_at = NOW() WHERE game_id = %s", (game_id,))
            return jsonify({'success': True, 'gameWon': True, 'message': '🎉 فاز الطاقم!'})
        return jsonify({'success': True, 'message': '✅ تم إنجاز المهمة!'})
    
    return jsonify({'error': 'فشل إنجاز المهمة'}), 400

@app.route('/api/game/<code>/meeting', methods=['POST'])
def api_call_meeting(code):
    data = request.json
    user_id = data.get('userId')
    
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    
    game = get_game_by_code(code)
    if not game:
        return jsonify({'error': 'Game not found'}), 404
    
    game_id = game[0]
    
    player = get_player_by_user_id(game_id, user_id)
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    
    player_id, role, is_alive, has_shield, has_knife = player
    
    if not is_alive:
        return jsonify({'error': 'أنت ميت!'}), 400
    
    if role == 'killer':
        return jsonify({'error': '🔪 القاتل لا يستطيع دعوة اجتماع!'}), 400
    
    if is_meeting_active(game_id):
        return jsonify({'error': 'يوجد اجتماع نشط بالفعل!'}), 400
    
    alive = get_alive_players(game_id)
    if len(alive) < 2:
        return jsonify({'error': 'لا يوجد لاعبين أحياء كافيين!'}), 400
    
    chat_id = request.args.get('chat_id', 0)
    start_meeting(game_id, int(chat_id) if chat_id else 0, user_id)
    
    if chat_id:
        try:
            bot.send_message(int(chat_id), f"🚨 **اجتماع طارئ!**\nدعا للاجتماع: @{data.get('username', 'لاعب')}\n⏰ المدة: 90 ثانية")
        except:
            pass
    
    return jsonify({'success': True, 'message': '🚨 تم عقد الاجتماع!'})

@app.route('/api/game/<code>/vote', methods=['POST'])
def api_vote(code):
    data = request.json
    voter_id = data.get('voterId')
    target_id = data.get('targetId')
    
    if not voter_id or not target_id:
        return jsonify({'error': 'Voter and target IDs required'}), 400
    
    game = get_game_by_code(code)
    if not game:
        return jsonify({'error': 'Game not found'}), 404
    
    game_id = game[0]
    
    if game_id not in MEETING_ACTIVE:
        return jsonify({'error': 'لا يوجد اجتماع نشط!'}), 400
    
    if voter_id in MEETING_ACTIVE[game_id]['voter_ids']:
        return jsonify({'error': 'لقد صوتت بالفعل!'}), 400
    
    MEETING_ACTIVE[game_id]['voter_ids'].append(voter_id)
    if target_id not in MEETING_ACTIVE[game_id]['votes']:
        MEETING_ACTIVE[game_id]['votes'][target_id] = 0
    MEETING_ACTIVE[game_id]['votes'][target_id] += 1
    
    meeting_id = MEETING_ACTIVE[game_id].get('meeting_id')
    if meeting_id:
        cursor.execute("INSERT INTO votes (meeting_id, voter_id, target_id) VALUES (%s, %s, %s)", (meeting_id, voter_id, target_id))
        conn.commit()
    
    return jsonify({'success': True, 'message': '🗳️ تم تسجيل صوتك!'})

@app.route('/api/game/<code>/kill', methods=['POST'])
def api_kill(code):
    data = request.json
    killer_id = data.get('killerId')
    victim_id = data.get('victimId')
    
    if not killer_id or not victim_id:
        return jsonify({'error': 'Killer and victim IDs required'}), 400
    
    game = get_game_by_code(code)
    if not game:
        return jsonify({'error': 'Game not found'}), 404
    
    game_id = game[0]
    
    if is_meeting_active(game_id):
        return jsonify({'error': 'لا يمكن القتل أثناء الاجتماع!'}), 400
    
    killer = get_player_by_user_id(game_id, killer_id)
    if not killer:
        return jsonify({'error': 'Killer not found'}), 404
    
    killer_player_id, killer_role, killer_alive, killer_shield, killer_knife = killer
    
    if killer_role != 'killer' or not killer_alive:
        return jsonify({'error': 'أنت لست القاتل أو ميت!'}), 400
    
    if not killer_knife:
        return jsonify({'error': 'ليس لديك سكين!'}), 400
    
    victim = get_player_by_user_id(game_id, victim_id)
    if not victim:
        return jsonify({'error': 'Victim not found'}), 404
    
    victim_player_id, victim_role, victim_alive, victim_shield, victim_knife = victim
    
    if not victim_alive:
        return jsonify({'error': 'الضحية ميتة!'}), 400
    
    if victim_role == 'killer':
        return jsonify({'error': 'لا يمكن قتل القاتل!'}), 400
    
    if victim_shield:
        safe_execute("UPDATE players SET has_shield = FALSE WHERE user_id = %s AND game_id = %s", (victim_id, game_id))
        return jsonify({'success': False, 'shielded': True, 'message': f'🛡️ درع! @{victim_id} نجا من القتل!'})
    
    try:
        cursor.execute("UPDATE players SET is_alive = FALSE WHERE user_id = %s AND game_id = %s", (victim_id, game_id))
        cursor.execute("UPDATE players SET has_knife = FALSE WHERE user_id = %s AND game_id = %s", (killer_id, game_id))
        cursor.execute("INSERT INTO kills (game_id, killer_id, victim_id) VALUES (%s, %s, %s)", (game_id, killer_id, victim_id))
        cursor.execute("UPDATE users SET kills = kills + 1 WHERE user_id = %s", (killer_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ Kill error: {e}")
        return jsonify({'error': 'فشل القتل'}), 500
    
    chat_id = request.args.get('chat_id', 0)
    if chat_id:
        try:
            bot.send_message(int(chat_id), f"💀 **تم العثور على جثة!**\nالضحية: @{victim_id}\n🔍 من هو القاتل؟")
        except:
            pass
    
    return jsonify({'success': True, 'message': f'💀 قتلت @{victim_id}!', 'victimId': victim_id})

@app.route('/api/game/<code>/position', methods=['POST'])
def api_update_position(code):
    data = request.json
    user_id = data.get('userId')
    pos_x = data.get('posX', 0)
    pos_y = data.get('posY', 0)
    
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    
    game = get_game_by_code(code)
    if not game:
        return jsonify({'error': 'Game not found'}), 404
    
    game_id = game[0]
    
    safe_execute("UPDATE players SET pos_x = %s, pos_y = %s WHERE game_id = %s AND user_id = %s", (pos_x, pos_y, game_id, user_id))
    return jsonify({'success': True})

# ============================================================
# أوامر البوت
# ============================================================

@bot.message_handler(commands=['start'])
def start(message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    bot.reply_to(message, 
        "🎮 **مرحباً في بوت Among Us!**\n\n"
        "📌 الأوامر:\n"
        "/new - إنشاء لعبة\n"
        "/join [كود] - انضمام\n"
        "/startgame - بدء اللعبة (المضيف)\n"
        "/play - فتح WebView 🎯\n"
        "/cancel - إلغاء اللعبة\n"
        "/status - حالة اللعبة\n"
        "/help - المساعدة",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['new'])
def new_game(message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    
    existing = safe_fetchone("""
        SELECT g.code FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE p.user_id = %s AND g.status IN ('waiting', 'playing')
    """, (message.from_user.id,))
    if existing:
        bot.reply_to(message, "❌ لديك لعبة نشطة!")
        return
    
    code = generate_code()
    try:
        cursor.execute("INSERT INTO games (code, host_id, status) VALUES (%s, %s, 'waiting') RETURNING game_id", (code, message.from_user.id))
        game_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO players (game_id, user_id, username, role, color) VALUES (%s, %s, %s, 'crewmate', %s)",
            (game_id, message.from_user.id, message.from_user.username, random.choice(['red','blue','green','yellow','purple','orange'])))
        conn.commit()
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, f"❌ خطأ: {e}")
        return
    
    player = get_player_by_user_id(game_id, message.from_user.id)
    if player:
        assign_tasks(player[0])
    
    bot.reply_to(message, f"✅ **تم إنشاء اللعبة!**\n🔑 الكود: `{code}`\n👥 1/10\n\n/join {code}", parse_mode='Markdown')

@bot.message_handler(commands=['join'])
def join_game(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ استخدم: /join [كود]")
        return
    
    code = args[1].upper()
    game = get_game_by_code(code)
    if not game:
        bot.reply_to(message, "❌ اللعبة غير موجودة!")
        return
    
    game_id = game[0]
    if game[3] != 'waiting':
        bot.reply_to(message, "❌ اللعبة بدأت!")
        return
    
    if get_players_count(game_id) >= 10:
        bot.reply_to(message, "❌ اللعبة ممتلئة!")
        return
    
    if safe_fetchone("SELECT * FROM players WHERE game_id = %s AND user_id = %s", (game_id, message.from_user.id)):
        bot.reply_to(message, "❌ أنت بالفعل في اللعبة!")
        return
    
    try:
        cursor.execute("INSERT INTO players (game_id, user_id, username, role, color) VALUES (%s, %s, %s, 'crewmate', %s)",
            (game_id, message.from_user.id, message.from_user.username, random.choice(['red','blue','green','yellow','purple','orange','pink','brown'])))
        conn.commit()
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, f"❌ خطأ: {e}")
        return
    
    player = get_player_by_user_id(game_id, message.from_user.id)
    if player:
        assign_tasks(player[0])
    
    bot.reply_to(message, f"✅ انضممت للعبة `{code}`\n👥 {get_players_count(game_id)}/10", parse_mode='Markdown')

@bot.message_handler(commands=['startgame'])
def start_game(message):
    game = safe_fetchone("""
        SELECT g.game_id, g.host_id, g.code FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE p.user_id = %s AND g.status = 'waiting'
    """, (message.from_user.id,))
    
    if not game:
        bot.reply_to(message, "❌ ليس لديك لعبة!")
        return
    
    game_id, host_id, code = game
    if host_id != message.from_user.id:
        bot.reply_to(message, "❌ فقط المضيف يمكنه البدء!")
        return
    
    players_count = get_players_count(game_id)
    if players_count < 4:
        bot.reply_to(message, f"❌ نحتاج 4 لاعبين على الأقل! (الآن {players_count})")
        return
    
    all_players = safe_fetchall("SELECT player_id, user_id FROM players WHERE game_id = %s", (game_id,))
    if not all_players:
        bot.reply_to(message, "❌ لا يوجد لاعبين!")
        return
    
    killer_idx = random.randint(0, len(all_players) - 1)
    killer_player_id, killer_user_id = all_players[killer_idx]
    
    try:
        cursor.execute("UPDATE players SET role = 'killer', has_knife = TRUE WHERE player_id = %s", (killer_player_id,))
        cursor.execute("UPDATE games SET status = 'playing', started_at = NOW() WHERE game_id = %s", (game_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, f"❌ خطأ: {e}")
        return
    
    for player_id, user_id in all_players:
        if user_id != killer_user_id:
            cursor.execute("UPDATE players SET has_shield = TRUE WHERE player_id = %s", (player_id,))
        conn.commit()
    
    for player_id, user_id in all_players:
        try:
            role = "قاتل" if user_id == killer_user_id else "عادي"
            emoji = "🔪" if user_id == killer_user_id else "👨‍🚀"
            bot.send_message(user_id, f"{emoji} **دورك في Among Us**\nأنت: **{role}**\n\nالكود: `{code}`\nعدد اللاعبين: {players_count}\n\n📌 استخدم /play لفتح WebView", parse_mode='Markdown')
            if user_id == killer_user_id:
                bot.send_message(user_id, "🔪 **أنت القاتل!**\n🗡️ لديك سكين واحد\n📌 لا تفضح نفسك!")
            else:
                bot.send_message(user_id, "🛡️ **لديك درع واقي!**\nيحميك من قتل واحد.")
        except Exception as e:
            print(f"خطأ في إرسال الرسالة للمستخدم {user_id}: {e}")
    
    markup = InlineKeyboardMarkup()
    web_url = f"https://{get_bot_username()}.render.com/web/{code}?user_id={message.from_user.id}&username={message.from_user.username}"
    btn = InlineKeyboardButton("🎮 افتح اللعبة", web_app=web_url)
    markup.add(btn)
    
    bot.send_message(message.chat.id, f"🎮 **بدأت اللعبة!**\n🔑 الكود: `{code}`\n👥 {players_count}\n\nاضغط الزر لفتح اللعبة:", parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(commands=['play'])
def play_game(message):
    game = safe_fetchone("""
        SELECT g.code, g.game_id FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE p.user_id = %s AND g.status = 'playing'
    """, (message.from_user.id,))
    
    if not game:
        bot.reply_to(message, "❌ أنت لست في لعبة نشطة!")
        return
    
    code = game[0]
    game_id = game[1]
    
    player = get_player_by_user_id(game_id, message.from_user.id)
    if not player or not player[2]:
        bot.reply_to(message, "💀 أنت ميت!")
        return
    
    markup = InlineKeyboardMarkup()
    web_url = f"https://{get_bot_username()}.render.com/web/{code}?user_id={message.from_user.id}&username={message.from_user.username}"
    btn = InlineKeyboardButton("🎮 افتح اللعبة", web_app=web_url)
    markup.add(btn)
    
    bot.reply_to(message, "🎮 **اضغط الزر لفتح اللعبة!**", reply_markup=markup)

@bot.message_handler(commands=['cancel'])
def cancel_game(message):
    result = safe_fetchone("""
        SELECT g.game_id, g.host_id, g.status FROM games g
        JOIN players p ON g.game_id = p.game_id
        WHERE p.user_id = %s AND g.status IN ('waiting', 'playing')
    """, (message.from_user.id,))
    
    if not result:
        bot.reply_to(message, "❌ ليس لديك لعبة!")
        return
    
    game_id, host_id, status = result
    if message.from_user.id != host_id and status == 'playing':
        bot.reply_to(message, "❌ فقط المضيف يمكنه الإلغاء أثناء اللعب!")
        return
    
    safe_execute("DELETE FROM games WHERE game_id = %s", (game_id,))
    if game_id in MEETING_ACTIVE:
        del MEETING_ACTIVE[game_id]
    if game_id in VOTES:
        del VOTES[game_id]
    bot.reply_to(message, "🗑️ **تم إلغاء اللعبة!**")

@bot.message_handler(commands=['status'])
def game_status(message):
    result = safe_fetchone("""
        SELECT g.code, g.status, COUNT(p.player_id), SUM(CASE WHEN p.is_alive THEN 1 ELSE 0 END)
        FROM games g JOIN players p ON g.game_id = p.game_id
        WHERE g.status IN ('waiting', 'playing') AND g.game_id IN (SELECT game_id FROM players WHERE user_id = %s)
        GROUP BY g.game_id
    """, (message.from_user.id,))
    
    if not result:
        bot.reply_to(message, "❌ ليس لديك لعبة!")
        return
    
    code, status, total, alive = result
    status_text = "⏳ انتظار" if status == 'waiting' else "🎮 جارية"
    bot.reply_to(message, f"📊 **حالة اللعبة**\n🔑 `{code}`\n📌 {status_text}\n👥 {total}/10\n💚 {alive}\n💀 {total-alive}", parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_command(message):
    start(message)

# ============================================================
# تشغيل البوت و Flask معاً
# ============================================================

def run_bot():
    print("🤖 Bot is running...")
    
    for task in TASKS_LIST:
        existing = safe_fetchone("SELECT * FROM tasks WHERE name = %s", (task['name'],))
        if not existing:
            safe_execute("INSERT INTO tasks (name, description, task_type, icon, room, difficulty) VALUES (%s, %s, %s, %s, %s, %s)",
                (task['name'], task['desc'], task['type'], task['icon'], task['room'], task['diff']))
    
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"❌ Bot error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    print("🌐 Web server running on port 8080...")
    app.run(host='0.0.0.0', port=8080, debug=False)
