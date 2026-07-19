import os
import asyncio
import random
import json
import uuid
import re
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

if not BOT_TOKEN or not DATABASE_URL:
    logger.error("❌ BOT_TOKEN أو DATABASE_URL غير موجود!")
    exit(1)

# ====== نظام المهام المطور والممتع ======
MINI_GAMES = [
    {
        "id": "memory",
        "name": "🧠 لعبة الذاكرة",
        "description": "تذكر تسلسل الأرقام واختر الإجابة الصحيحة!",
        "generate": lambda: {
            "sequence": random.sample(range(1, 9), 4),
            "options": [
                random.sample(range(1, 9), 4),
                random.sample(range(1, 9), 4),
                random.sample(range(1, 9), 4),
            ]
        }
    },
    {
        "id": "math",
        "name": "🔢 تحدي الرياضيات",
        "description": "حل المسألة الحسابية بسرعة!",
        "generate": lambda: {
            "a": random.randint(10, 99),
            "b": random.randint(10, 99),
            "op": random.choice(["+", "-", "*"])
        }
    },
    {
        "id": "color",
        "name": "🎨 تحدي الألوان",
        "description": "اختر الزر الذي يحمل اللون المطلوب!",
        "generate": lambda: {
            "target": random.choice(["أحمر", "أزرق", "أخضر", "أصفر", "بنفسجي"]),
            "options": ["أحمر", "أزرق", "أخضر", "أصفر", "بنفسجي"]
        }
    },
    {
        "id": "speed",
        "name": "⚡ تحدي السرعة",
        "description": "اضغط على الزر الصحيح بأسرع وقت! (5 ثواني)",
        "generate": lambda: {
            "correct": random.randint(0, 3),
            "emojis": random.sample(["🌟", "💎", "🔥", "⚡", "🎯", "💫", "🦊", "🐉"], 4)
        }
    },
    {
        "id": "password",
        "name": "🔐 فك الشيفرة",
        "description": "خمن الرمز السري المكون من 3 أرقام!",
        "generate": lambda: {
            "code": f"{random.randint(100, 999)}",
            "hint": f"مجموع الأرقام = {random.randint(10, 25)}"
        }
    }
]

# ====== أدوات مساعدة ======
CREWMATE_TOOLS = [
    {"name": "جهاز تتبع", "emoji": "📡", "description": "يكشف موقع لاعب بشكل تقريبي", "effect": "track"},
    {"name": "كاميرا مراقبة", "emoji": "📸", "description": "تلتقط صورة وتكشف إذا كان مشبوهاً", "effect": "camera"},
    {"name": "جهاز كشف الكذب", "emoji": "🕵️", "description": "يسأل اللاعب ويكشف إذا كان صادقاً", "effect": "lie_detector"},
    {"name": "درع واقي", "emoji": "🛡️", "description": "يحميك من القتل لمرة واحدة", "effect": "shield"},
    {"name": "مسرع المهام", "emoji": "⚡", "description": "ينهي مهمة فوراً", "effect": "speed_boost"}
]

IMPOSTOR_TOOLS = [
    {"name": "قنبلة دخان", "emoji": "💨", "description": "تعطل الكاميرات لمدة دقيقة", "effect": "smoke_bomb"},
    {"name": "تنكر", "emoji": "🎭", "description": "تتظاهر أنك طاقم وتكمل مهمة", "effect": "disguise"},
    {"name": "تخريب الأبواب", "emoji": "🚪", "description": "يقفل الأبواب 30 ثانية", "effect": "lock_doors"},
    {"name": "تشويش الاتصالات", "emoji": "📵", "description": "يمنع اجتماع الطوارئ دقيقة", "effect": "jam_comms"},
    {"name": "تخريب الإضاءة", "emoji": "🌑", "description": "يطفئ الأنوار 30 ثانية", "effect": "lights_off"}
]

LOCATIONS = [
    "الكافتيريا 🍽️", "المفاعل ☢️", "غرفة المحرك ⚙️",
    "الممر الرئيسي 🚶", "غرفة الاتصالات 📡", "المخزن 📦",
    "غرفة الأكسجين 🫁", "المختبر 🔬", "قاعة الاجتماعات 🏛️"
]

KILL_SCENARIOS = [
    {
        "weapon": "خنجر", "emoji": "🗡️",
        "scene": [
            "🕵️ *ظل يتحرك في الظلام...*",
            "👤 *الضحية منشغلة...*",
            "💨 *حركة سريعة من الخلف...*",
            "🩸 *طعنة صامتة!*"
        ],
        "death_message": "🔴💀🔴\n*تم اكتشاف جثة!*\n\n💀 {victim} قُتل بـ{weapon}!\n📍 {location}\n\n🚨 *اجتماع طارئ!*"
    },
    {
        "weapon": "مسدس", "emoji": "🔫",
        "scene": [
            "🎯 *تصويب من الظلام...*",
            "😤 *الضحية في المكان الخطأ...*",
            "💥 *طلقة مدوية!*",
            "🏃 *القاتل يهرب...*"
        ],
        "death_message": "🔴💀🔴\n*جريمة قتل!*\n\n💀 {victim} انقتل بـ{weapon}!\n📍 {location}\n\n🚨 *اجتماع فوري!*"
    },
    {
        "weapon": "سُم", "emoji": "🧪",
        "scene": [
            "🍷 *المشروب يبدو طبيعياً...*",
            "😊 *الضحية تشرب...*",
            "😵 *تبدأ بالدوار...*",
            "💀 *تسقط أرضاً!*"
        ],
        "death_message": "🔴💀🔴\n*جريمة بالسم!*\n\n💀 {victim} مات مسموماً!\n📍 {location}\n\n🚨 *من وضع السم؟!*"
    }
]

RANDOM_EVENTS = [
    {"name": "انقطاع الكهرباء", "emoji": "⚡", 
     "message": "⚡ *انقطعت الكهرباء!*\n🌑 الظلام يخيم...\n👀 القاتل يستغل الظلام!"},
    {"name": "زلزال", "emoji": "🌋", 
     "message": "🌋 *اهتزاز عنيف!*\n💥 الجميع يسقط أرضاً!\n🏃 القاتل يتحرك في الفوضى!"},
    {"name": "إنذار حريق", "emoji": "🔥", 
     "message": "🔥🚨 *حريق في السفينة!*\n💨 الرؤية ضبابية!\n😈 القاتل يستغل الموقف!"},
    {"name": "تسرب غاز", "emoji": "☠️", 
     "message": "☠️ *تسرب غاز سام!*\n😷 صعوبة في التعرف على اللاعبين!"},
    {"name": "عطل أنظمة", "emoji": "🔧", 
     "message": "🔧 *عطل في الأنظمة!*\n🚪 الأبواب تفتح وتغلق عشوائياً!"}
]

# ====== التخزين المؤقت ======
active_games = {}
user_tools = {}
player_current_task = {}
vote_messages = {}
event_tasks = {}
processed_callbacks = set()

# ====== دوال قاعدة البيانات ======
def get_conn():
    for attempt in range(3):
        try:
            return psycopg2.connect(DATABASE_URL)
        except Exception as e:
            if attempt == 2:
                logger.error(f"❌ فشل الاتصال: {e}")
                raise
            asyncio.sleep(1)

def init_db():
    try:
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
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("✅ تم تهيئة قاعدة البيانات")
    except Exception as e:
        logger.error(f"❌ init_db: {e}")

def get_user(user_id: int):
    conn = None
    try:
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
        return user
    except Exception as e:
        logger.error(f"❌ get_user: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_user_points(user_id: int, points: int, won=False, role=None, kill=False, task=False):
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        parts = ["points = points + %s", "games_played = games_played + 1"]
        params = [points]
        if won:
            parts.append('games_won = games_won + 1')
            if role == 'crewmate':
                parts.append('crewmate_wins = crewmate_wins + 1')
            elif role == 'impostor':
                parts.append('impostor_wins = impostor_wins + 1')
        if kill:
            parts.append('total_kills = total_kills + 1')
        if task:
            parts.append('total_tasks = total_tasks + 1')
        params.append(user_id)
        cursor.execute(f"UPDATE users SET {', '.join(parts)} WHERE user_id = %s", params)
        conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"❌ update_user_points: {e}")
    finally:
        if conn:
            conn.close()

def get_leaderboard():
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT user_id, username, first_name, points FROM users ORDER BY points DESC LIMIT 10')
        leaders = cursor.fetchall()
        cursor.close()
        return leaders
    except:
        return []
    finally:
        if conn:
            conn.close()

# ====== دوال مساعدة ======
def generate_game_key():
    return str(uuid.uuid4())[:6]

def get_impostor_count(n):
    return 1 if n <= 5 else 2 if n <= 8 else 3

def get_player_name(pdata):
    name = pdata.get('first_name') or pdata.get('username') or 'لاعب'
    return str(name).replace('_', ' ').replace('*', '').replace('`', '')

async def safe_send(context, chat_id, text, parse_mode='Markdown', reply_markup=None):
    try:
        return await context.bot.send_message(
            chat_id=chat_id, text=text,
            parse_mode=parse_mode, reply_markup=reply_markup
        )
    except BadRequest:
        try:
            clean = re.sub(r'[*_`\[\]]', '', text)
            return await context.bot.send_message(
                chat_id=chat_id, text=clean, reply_markup=reply_markup
            )
        except:
            pass
    except Exception as e:
        logger.error(f"❌ safe_send: {e}")
    return None

async def cleanup_game(chat_id):
    if chat_id in active_games:
        for pid in active_games[chat_id]['players']:
            user_tools.pop(pid, None)
            player_current_task.pop(pid, None)
    if chat_id in event_tasks:
        event_tasks[chat_id].cancel()
        del event_tasks[chat_id]
    vote_messages.pop(chat_id, None)

# ====== نظام المهام الجديد (ألعاب مصغرة) ======
async def execute_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ مهمة - نسخة الألعاب المصغرة"""
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
            await update.message.reply_text("⏳ اللعبة لم تبدأ بعد!")
            return
        
        player = game['players'][user_id]
        if not player['alive']:
            await update.message.reply_text("💀 أنت ميت! لا يمكنك تنفيذ مهام.")
            return
        
        if player['role'] == 'crewmate':
            if player['tasks'] >= player['total_tasks']:
                await update.message.reply_text("✅ أحسنت! أكملت كل مهامك!\n🔍 الآن ركز على كشف القاتل!")
                return
            
            # اختيار لعبة عشوائية
            mini_game = random.choice(MINI_GAMES)
            game_data = mini_game['generate']()
            
            # تخزين بيانات اللعبة للتحقق لاحقاً
            player_current_task[user_id] = {
                "game_id": mini_game['id'],
                "data": game_data,
                "group_id": group_id
            }
            
            # بناء الأزرار حسب نوع اللعبة
            if mini_game['id'] == 'memory':
                seq = '-'.join(map(str, game_data['sequence']))
                keyboard = []
                all_options = [game_data['sequence']] + game_data['options']
                random.shuffle(all_options)
                for opt in all_options:
                    keyboard.append([InlineKeyboardButton(
                        '-'.join(map(str, opt)),
                        callback_data=f"mg_{group_id}_{user_id}_memory_{'-'.join(map(str, opt))}"
                    )])
                
                await update.message.reply_text(
                    f"🧠 *لعبة الذاكرة*\n\n"
                    f"📝 تذكر هذا التسلسل:\n"
                    f"`{seq}`\n\n"
                    f"⏰ اختر التسلسل الصحيح!",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            
            elif mini_game['id'] == 'math':
                a, b, op = game_data['a'], game_data['b'], game_data['op']
                if op == '+':
                    correct = a + b
                elif op == '-':
                    correct = a - b
                else:
                    correct = a * b
                
                game_data['correct'] = correct
                
                # إنشاء خيارات (الصحيح + 3 خاطئة)
                options = [correct]
                while len(options) < 4:
                    fake = correct + random.randint(-20, 20)
                    if fake != correct and fake > 0 and fake not in options:
                        options.append(fake)
                random.shuffle(options)
                
                keyboard = [[InlineKeyboardButton(
                    str(opt),
                    callback_data=f"mg_{group_id}_{user_id}_math_{opt}"
                )] for opt in options]
                
                await update.message.reply_text(
                    f"🔢 *تحدي الرياضيات*\n\n"
                    f"🧮 ما ناتج:\n"
                    f"`{a} {op} {b} = ؟`\n\n"
                    f"⏰ أجب بسرعة!",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            
            elif mini_game['id'] == 'color':
                target = game_data['target']
                options = game_data['options'][:4]
                random.shuffle(options)
                
                keyboard = [[InlineKeyboardButton(
                    f"{opt} ⬜",
                    callback_data=f"mg_{group_id}_{user_id}_color_{opt}"
                )] for opt in options]
                
                await update.message.reply_text(
                    f"🎨 *تحدي الألوان*\n\n"
                    f"🎯 اختر الزر الذي يمثل:\n"
                    f"*{target}*",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            
            elif mini_game['id'] == 'speed':
                correct_idx = game_data['correct']
                emojis = game_data['emojis']
                
                keyboard = [[InlineKeyboardButton(
                    e,
                    callback_data=f"mg_{group_id}_{user_id}_speed_{i}"
                )] for i, e in enumerate(emojis)]
                
                game_data['correct_emoji'] = emojis[correct_idx]
                
                await update.message.reply_text(
                    f"⚡ *تحدي السرعة*\n\n"
                    f"🎯 اضغط على: *{emojis[correct_idx]}*\n\n"
                    f"⏰ لديك 10 ثواني فقط!",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            
            elif mini_game['id'] == 'password':
                code = game_data['code']
                hint = game_data['hint']
                
                options = [code]
                while len(options) < 4:
                    fake = str(random.randint(100, 999))
                    if fake != code and fake not in options:
                        options.append(fake)
                random.shuffle(options)
                
                keyboard = [[InlineKeyboardButton(
                    opt,
                    callback_data=f"mg_{group_id}_{user_id}_password_{opt}"
                )] for opt in options]
                
                await update.message.reply_text(
                    f"🔐 *فك الشيفرة*\n\n"
                    f"💡 تلميح: {hint}\n\n"
                    f"🔢 خمن الرمز السري!",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        else:
            # مهمة تخريبية للقاتل
            sabotage_options = [
                {"name": "تخريب المفاعل ☢️", "id": "reactor", "desc": "يفعل إنذار المفاعل ويقفل الأبواب"},
                {"name": "قطع الأكسجين 🫁", "id": "oxygen", "desc": "يقطع الأكسجين ويعطل الاتصالات"},
                {"name": "إطفاء الأنوار 🌑", "id": "lights", "desc": "يطفئ الأنوار للتمويه"},
                {"name": "تشويش الرادار 📡", "id": "radar", "desc": "يعطل أجهزة التتبع"}
            ]
            
            keyboard = [[InlineKeyboardButton(
                s['name'],
                callback_data=f"sb_{group_id}_{user_id}_{s['id']}"
            )] for s in sabotage_options]
            
            await update.message.reply_text(
                "😈 *لوحة التحكم - التخريب*\n\n"
                "اختر عملية تخريبية:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    
    except Exception as e:
        logger.error(f"❌ execute_task: {e}")
        await update.message.reply_text("❌ حدث خطأ! جرب مرة أخرى.")

async def handle_mini_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة نتائج الألعاب المصغرة"""
    query = update.callback_query
    
    try:
        data = query.data
        
        if not data.startswith('mg_'):
            return
        
        parts = data.split('_')
        group_id = int(parts[1])
        user_id = int(parts[2])
        game_id = parts[3]
        answer = '_'.join(parts[4:])
        
        if query.from_user.id != user_id:
            await query.answer("❌ هذه ليست مهمتك!")
            return
        
        if group_id not in active_games:
            await query.answer("⚠️ اللعبة انتهت!")
            return
        
        game = active_games[group_id]
        task_data = player_current_task.get(user_id, {})
        game_data = task_data.get('data', {})
        
        correct = False
        
        if game_id == 'memory':
            correct_seq = '-'.join(map(str, game_data['sequence']))
            correct = (answer == correct_seq)
        
        elif game_id == 'math':
            correct = (int(answer) == game_data.get('correct'))
        
        elif game_id == 'color':
            correct = (answer == game_data.get('target'))
        
        elif game_id == 'speed':
            correct = (answer == str(game_data.get('correct')))
        
        elif game_id == 'password':
            correct = (answer == game_data.get('code'))
        
        if correct:
            game['players'][user_id]['tasks'] += 1
            update_user_points(user_id, 20, task=True)
            
            progress = f"{game['players'][user_id]['tasks']}/{game['players'][user_id]['total_tasks']}"
            
            messages = [
                f"✅ *أحسنت!* مهمة ناجحة!\n\n📊 التقدم: {progress}\n🎯 استمر في العمل!",
                f"🌟 *رائع!* مهمة مكتملة!\n\n📊 التقدم: {progress}\n💪 أنت مفيد للسفينة!",
                f"🎉 *ممتاز!* أتممت المهمة!\n\n📊 التقدم: {progress}\n🔍 راقب المشتبه بهم!"
            ]
            
            await query.edit_message_text(
                random.choice(messages),
                parse_mode='Markdown'
            )
            
            if game['players'][user_id]['tasks'] >= game['players'][user_id]['total_tasks']:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="🏆 *مبروك!* أكملت كل مهامك!\n\n🔍 الآن دورك في كشف القاتل!\n💡 استخدم /tools للمساعدة!"
                    )
                except:
                    pass
        else:
            await query.edit_message_text(
                random.choice([
                    "❌ *خطأ!* حاول مرة أخرى بـ /tasks",
                    "😅 *للأسف خطأ!* المهمة فشلت... جرب مجدداً!",
                    "💔 *إجابة خاطئة!* لا تستسلم، جرب /tasks"
                ]),
                parse_mode='Markdown'
            )
        
        player_current_task.pop(user_id, None)
    
    except Exception as e:
        logger.error(f"❌ handle_mini_game: {e}")
        try:
            await query.edit_message_text("❌ حدث خطأ! جرب /tasks")
        except:
            pass

async def handle_sabotage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة التخريب"""
    query = update.callback_query
    data = query.data
    
    if not data.startswith('sb_'):
        return
    
    parts = data.split('_')
    group_id = int(parts[1])
    user_id = int(parts[2])
    sab_id = parts[3]
    
    if query.from_user.id != user_id:
        await query.answer("❌ ليس لك!")
        return
    
    if group_id not in active_games:
        return
    
    game = active_games[group_id]
    
    sabotage_actions = {
        "reactor": {
            "msg": "☢️ *تم تخريب المفاعل!*\n🚪 الأبواب ستغلق 20 ثانية!",
            "effect": lambda: setattr(game, 'doors_locked', True),
            "restore": 20,
            "restore_effect": lambda: setattr(game, 'doors_locked', False),
            "restore_msg": "🔄 *تم إصلاح المفاعل!* 🚪 الأبواب فتحت."
        },
        "oxygen": {
            "msg": "🫁 *تم قطع الأكسجين!*\n📵 الاتصالات معطلة 45 ثانية!",
            "effect": lambda: setattr(game, 'emergency_blocked', True),
            "restore": 45,
            "restore_effect": lambda: setattr(game, 'emergency_blocked', False),
            "restore_msg": "📶 *عادت الاتصالات!* 🚨 يمكنكم استخدام /emergency"
        },
        "lights": {
            "msg": "🌑 *انطفأت الأنوار!*\n👀 الظلام يخيم 30 ثانية!",
            "effect": lambda: setattr(game, 'lights_off', True),
            "restore": 30,
            "restore_effect": lambda: setattr(game, 'lights_off', False),
            "restore_msg": "💡 *عادت الإضاءة!* 👀 يمكنكم الرؤية بوضوح."
        },
        "radar": {
            "msg": "📡 *تم تشويش الرادار!*\n🎯 أجهزة التتبع معطلة 35 ثانية!",
            "effect": lambda: setattr(game, 'smoke_active', True),
            "restore": 35,
            "restore_effect": lambda: setattr(game, 'smoke_active', False),
            "restore_msg": "📡 *عاد الرادار للعمل!* 🎯 يمكنكم التتبع الآن."
        }
    }
    
    action = sabotage_actions.get(sab_id)
    if action:
        action['effect']()
        await query.edit_message_text(action['msg'], parse_mode='Markdown')
        await safe_send(context, group_id, f"🚨 *تخريب!*\n{action['msg']}", parse_mode='Markdown')
        
        async def restore():
            await asyncio.sleep(action['restore'])
            if group_id in active_games:
                action['restore_effect']()
                await safe_send(context, group_id, action['restore_msg'], parse_mode='Markdown')
        
        asyncio.create_task(restore())

# ====== نظام التصويت ======
async def start_voting(chat_id, context, from_emergency=False):
    try:
        if chat_id not in active_games:
            return
        
        game = active_games[chat_id]
        game['status'] = 'voting'
        game['votes'] = {}
        game['voted_players'] = set()
        
        alive = {pid: p for pid, p in game['players'].items() if p['alive']}
        
        if len(alive) <= 2:
            await safe_send(context, chat_id, "⚠️ عدد اللاعبين قليل للتصويت!")
            game['status'] = 'playing'
            return
        
        title = "🚨 *تصويت طارئ!*" if from_emergency else "🗳️ *جولة تصويت!*"
        text = f"{title}\n\n🎯 *صوت لطرد المشتبه به:*\n\n"
        
        keyboard = []
        for pid, pdata in alive.items():
            name = get_player_name(pdata)
            text += f"• {name}\n"
            keyboard.append([InlineKeyboardButton(
                f"🗳️ طرد {name}",
                callback_data=f"v_{chat_id}_{pid}"
            )])
        
        keyboard.append([InlineKeyboardButton("⏭️ تخطي", callback_data=f"v_{chat_id}_skip")])
        
        text += f"\n⏰ *45 ثانية للتصويت*"
        
        # حذف رسالة تصويت قديمة
        if chat_id in vote_messages:
            try:
                await context.bot.delete_message(chat_id, vote_messages[chat_id])
            except:
                pass
        
        msg = await safe_send(context, chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        if msg:
            vote_messages[chat_id] = msg.message_id
        
        for remaining in [30, 15, 5]:
            await asyncio.sleep(15)
            if chat_id in active_games and active_games[chat_id]['status'] == 'voting':
                voted = len(game.get('voted_players', set()))
                total = len(alive)
                await safe_send(context, chat_id, f"⏰ *متبقي {remaining}s*\n🗳️ {voted}/{total} صوتوا")
        
        if chat_id in active_games and active_games[chat_id]['status'] == 'voting':
            await end_voting(chat_id, context)
    
    except Exception as e:
        logger.error(f"❌ start_voting: {e}")

async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if not data.startswith('v_'):
        return
    
    try:
        parts = data.split('_')
        chat_id = int(parts[1])
        target = parts[2]
        
        if chat_id not in active_games:
            await query.answer("⚠️ اللعبة انتهت!", show_alert=True)
            return
        
        game = active_games[chat_id]
        user_id = query.from_user.id
        
        if user_id not in game['players'] or not game['players'][user_id]['alive']:
            await query.answer("❌ لا يمكنك التصويت!", show_alert=True)
            return
        
        if game['status'] != 'voting':
            await query.answer("⏰ انتهى التصويت!", show_alert=True)
            return
        
        if user_id in game.get('voted_players', set()):
            await query.answer("⚠️ صوتت بالفعل!", show_alert=True)
            return
        
        game['votes'][user_id] = target
        game['voted_players'].add(user_id)
        
        if target == 'skip':
            await query.answer("⏭️ تم التخطي!")
        else:
            try:
                name = get_player_name(game['players'][int(target)])
                await query.answer(f"🗳️ صوتت لطرد {name}!")
            except:
                await query.answer("🗳️ تم تسجيل صوتك!")
    
    except Exception as e:
        logger.error(f"❌ handle_vote: {e}")
        try:
            await query.answer("❌ خطأ!")
        except:
            pass

async def end_voting(chat_id, context):
    try:
        if chat_id not in active_games:
            return
        
        game = active_games[chat_id]
        
        # عد الأصوات
        votes = {}
        for v_id, target in game['votes'].items():
            if target != 'skip':
                votes[target] = votes.get(target, 0) + 1
        
        if not votes:
            await safe_send(context, chat_id, "⏭️ *تم التخطي!* لا أحد يُطرد.")
            game['status'] = 'playing'
            game['voted_players'] = set()
            return
        
        most_voted = max(votes, key=votes.get)
        max_v = votes[most_voted]
        tied = [p for p, v in votes.items() if v == max_v]
        
        if len(tied) > 1:
            await safe_send(context, chat_id, "⚖️ *تعادل!* لا أحد يُطرد.")
            game['status'] = 'playing'
            game['voted_players'] = set()
            return
        
        player_id = int(most_voted)
        player = game['players'][player_id]
        name = get_player_name(player)
        was_impostor = player['role'] == 'impostor'
        
        player['alive'] = False
        
        if was_impostor:
            game['impostors'].remove(player_id)
            await safe_send(context, chat_id,
                f"🎉🚀 *تم طرد القاتل!*\n\n🔪 {name} كان القاتل!\n✅ تم طرده للفضاء!\n🎊 *أحسنتم!*")
            update_user_points(player_id, 0, won=False, role='impostor')
        else:
            await safe_send(context, chat_id,
                f"💔😢 *تم طرد بريء!*\n\n👨‍🚀 {name} كان طاقم!\n😈 القاتل يضحك...\n⚠️ *كونوا أكثر حذراً!*")
            update_user_points(player_id, 0, won=False, role='crewmate')
            if player_id in game['alive_crewmates']:
                game['alive_crewmates'].remove(player_id)
        
        # تحقق من نهاية اللعبة
        if len(game['impostors']) == 0:
            await end_game(chat_id, context, 'crewmate')
            return
        if len(game['impostors']) >= len(game['alive_crewmates']):
            await end_game(chat_id, context, 'impostor')
            return
        
        game['status'] = 'playing'
        game['votes'] = {}
        game['voted_players'] = set()
        game['emergency_used'] = False
        
        await safe_send(context, chat_id,
            f"🎮 *استئناف اللعبة!*\n\n"
            f"👥 الأحياء: {len(game['alive_crewmates']) + len(game['impostors'])}\n"
            f"🔪 قتلة متبقيين: {len(game['impostors'])}\n"
            f"⚡ /tasks | 🚨 /emergency")
    
    except Exception as e:
        logger.error(f"❌ end_voting: {e}")

# ====== أوامر أساسية ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id)
    
    await update.message.reply_text(
        f"🎮 *مرحباً {user.first_name}!*\n\n"
        f"🚀 أنا بوت *Among Us* بألعاب مصغرة!\n"
        f"العب مع أصدقائك واكتشف القاتل!\n\n"
        f"📋 *الأوامر:*\n"
        f"🎯 /new_game - بدء لعبة\n"
        f"🤝 /join - انضمام\n"
        f"🎮 /tasks - ألعاب مصغرة\n"
        f"🎒 /tools - أدوات\n"
        f"🚨 /emergency - اجتماع\n"
        f"📊 /status - حالة اللعبة\n"
        f"📈 /stats - إحصائيات\n"
        f"👑 /leaderboard - متصدرين",
        parse_mode='Markdown'
    )

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ للمجموعات فقط!")
        return
    
    if chat_id in active_games:
        await update.message.reply_text("⚠️ هناك لعبة جارية!")
        return
    
    game_id = generate_game_key()
    active_games[chat_id] = {
        'id': game_id, 'creator': user.id, 'players': {},
        'status': 'waiting', 'impostors': [], 'alive_crewmates': [],
        'dead_players': [], 'votes': {}, 'voted_players': set(),
        'kill_cooldown': {}, 'emergency_used': False,
        'emergency_blocked': False, 'smoke_active': False,
        'doors_locked': False, 'lights_off': False,
        'start_votes': {}, 'start_time': datetime.now(),
        'kill_count': 0, 'meeting_count': 0
    }
    
    keyboard = [[InlineKeyboardButton("🎮 انضم!", callback_data=f"join_{game_id}")]]
    await update.message.reply_text(
        f"🚀 *لعبة جديدة!*\n\n🆔 `{game_id}`\n👤 {user.first_name}\n\n"
        f"👥 /join (الحد الأدنى: 4)\n🗑️ /cancel_game",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await msg.reply_text("❌ لا توجد لعبة!")
        return
    
    game = active_games[chat_id]
    if game['status'] != 'waiting':
        await msg.reply_text("❌ بدأت بالفعل!")
        return
    
    if user.id in game['players']:
        await msg.reply_text("⚠️ منضم بالفعل!")
        return
    
    if len(game['players']) >= 10:
        await msg.reply_text("❌ مكتملة!")
        return
    
    game['players'][user.id] = {
        'username': user.username or user.first_name,
        'first_name': user.first_name, 'role': None,
        'alive': True, 'tasks': 0, 'total_tasks': 3, 'shield': False
    }
    get_user(user.id)
    
    count = len(game['players'])
    await msg.reply_text(f"✅ {user.first_name} انضم! ({count}/10)")
    
    if count >= 4:
        asyncio.create_task(ask_start_vote(chat_id, context))

async def ask_start_vote(chat_id, context):
    await asyncio.sleep(2)
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    if game['status'] != 'waiting':
        return
    
    game['start_votes'] = {}
    players_list = "\n".join([f"• {get_player_name(p)}" for p in game['players'].values()])
    
    keyboard = [[
        InlineKeyboardButton("✅ ابدأ!", callback_data=f"startv_yes_{chat_id}"),
        InlineKeyboardButton("❌ انتظر", callback_data=f"startv_no_{chat_id}")
    ]]
    
    await safe_send(context, chat_id,
        f"👥 *{len(game['players'])} لاعبين*\n\n{players_list}\n\n🗳️ نبدأ؟\n⏰ 30 ثانية",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await asyncio.sleep(30)
    
    if chat_id in active_games and active_games[chat_id]['status'] == 'waiting':
        yes = sum(1 for v in game['start_votes'].values() if v == 'yes')
        if yes >= 2 or len(game['players']) >= 6:
            await safe_send(context, chat_id, f"✅ {yes} أصوات!\n🚀 بدء اللعبة...")
            await start_game(chat_id, context)

async def start_game(chat_id, context):
    game = active_games[chat_id]
    players = list(game['players'].keys())
    imp_count = get_impostor_count(len(players))
    
    random.shuffle(players)
    impostors = players[:imp_count]
    crewmates = players[imp_count:]
    
    game['impostors'] = impostors
    game['alive_crewmates'] = crewmates.copy()
    
    for imp_id in impostors:
        game['players'][imp_id]['role'] = 'impostor'
        user_tools[imp_id] = random.sample(IMPOSTOR_TOOLS, 2)
        tools = "\n".join([f"{t['emoji']} {t['name']}" for t in user_tools[imp_id]])
        try:
            await context.bot.send_message(imp_id,
                f"🔪 *أنت القاتل!*\n\n🎒 أدواتك:\n{tools}\n\n💀 /kill @user\n🎮 /tasks للتخريب\n🎒 /tools",
                parse_mode='Markdown')
        except: pass
    
    for crew_id in crewmates:
        game['players'][crew_id]['role'] = 'crewmate'
        user_tools[crew_id] = random.sample(CREWMATE_TOOLS, 2)
        tools = "\n".join([f"{t['emoji']} {t['name']}" for t in user_tools[crew_id]])
        try:
            await context.bot.send_message(crew_id,
                f"👨‍🚀 *طاقم!*\n\n🎒 أدواتك:\n{tools}\n\n🎮 /tasks للألعاب\n🎒 /tools\n🚨 /emergency",
                parse_mode='Markdown')
        except: pass
    
    game['status'] = 'playing'
    game['start_time'] = datetime.now()
    
    await safe_send(context, chat_id,
        f"🚀🔥 *انطلقت اللعبة!*\n\n"
        f"👥 {len(players)} لاعبين | 🔪 {imp_count} قتلة\n\n"
        f"🎮 /tasks - ألعاب مصغرة\n"
        f"🎒 /tools - أدوات\n"
        f"🚨 /emergency - اجتماع\n\n"
        f"⚠️ *القاتل بينكم... فمن هو؟*"
    )
    
    if chat_id in event_tasks:
        event_tasks[chat_id].cancel()
    event_tasks[chat_id] = asyncio.create_task(random_events(chat_id, context))

async def random_events(chat_id, context):
    try:
        while chat_id in active_games and active_games[chat_id]['status'] == 'playing':
            await asyncio.sleep(random.randint(60, 120))
            if chat_id in active_games and active_games[chat_id]['status'] == 'playing':
                event = random.choice(RANDOM_EVENTS)
                await safe_send(context, chat_id, event['message'])
    except asyncio.CancelledError:
        pass

async def emergency_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in active_games:
        await update.message.reply_text("❌ لا توجد لعبة!")
        return
    
    game = active_games[chat_id]
    if game['status'] != 'playing':
        return
    
    if user.id not in game['players'] or not game['players'][user.id]['alive']:
        await update.message.reply_text("💀 لا يمكنك!")
        return
    
    if game.get('emergency_blocked'):
        await update.message.reply_text("📵 الاتصالات معطلة!")
        return
    
    if game.get('emergency_used'):
        await update.message.reply_text("❌ تم الاستخدام!")
        return
    
    game['emergency_used'] = True
    game['meeting_count'] += 1
    
    await safe_send(context, chat_id,
        f"🚨🔴 *اجتماع طارئ!*\n👤 {user.first_name}\n💬 ناقشوا الأدلة!\n⏰ 60 ثانية"
    )
    
    for r in [30, 15, 5]:
        await asyncio.sleep(15)
        if chat_id in active_games and active_games[chat_id]['status'] == 'playing':
            await safe_send(context, chat_id, f"⏰ {r} ثانية!")
    
    if chat_id in active_games:
        await start_voting(chat_id, context, from_emergency=True)

async def kill_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if update.effective_chat.type != 'private':
        await update.message.reply_text("❌ في الخاص فقط!")
        return
    
    game = None
    group_id = None
    for gid, g in active_games.items():
        if user_id in g['players']:
            game = g
            group_id = gid
            break
    
    if not game or game['players'][user_id]['role'] != 'impostor':
        await update.message.reply_text("❌ لا يمكنك القتل!")
        return
    
    now = datetime.now()
    if user_id in game['kill_cooldown']:
        elapsed = (now - game['kill_cooldown'][user_id]).total_seconds()
        if elapsed < 60:
            await update.message.reply_text(f"⏰ انتظر {int(60-elapsed)}s!")
            return
    
    if not context.args:
        await update.message.reply_text("❌ /kill @username")
        return
    
    victim_name = context.args[0].replace('@', '')
    victim_id = None
    for pid, p in game['players'].items():
        if p['username'] == victim_name and p['alive'] and pid != user_id:
            victim_id = pid
            break
    
    if not victim_id:
        await update.message.reply_text("❌ غير موجود!")
        return
    
    if game['players'][victim_id].get('shield'):
        game['players'][victim_id]['shield'] = False
        await update.message.reply_text("🛡️ محمي!")
        return
    
    game['kill_cooldown'][user_id] = now
    game['players'][victim_id]['alive'] = False
    game['dead_players'].append(victim_id)
    if victim_id in game['alive_crewmates']:
        game['alive_crewmates'].remove(victim_id)
    game['kill_count'] += 1
    
    scenario = random.choice(KILL_SCENARIOS)
    name = game['players'][victim_id]['first_name']
    loc = random.choice(LOCATIONS)
    
    for msg in scenario['scene']:
        await update.message.reply_text(msg, parse_mode='Markdown')
        await asyncio.sleep(0.5)
    
    death = scenario['death_message'].format(victim=name, weapon=scenario['weapon'], location=loc)
    await safe_send(context, group_id, death)
    update_user_points(user_id, 30, kill=True)
    
    if len(game['impostors']) >= len(game['alive_crewmates']):
        await end_game(group_id, context, 'impostor')
    else:
        await start_voting(group_id, context)

async def end_game(chat_id, context, winner):
    game = active_games[chat_id]
    game['status'] = 'ended'
    
    if winner == 'crewmate':
        await safe_send(context, chat_id, "🎉🏆 *الطاقم يفوز!*\n🌟 تم كشف كل القتلة!")
        for pid in game['alive_crewmates']:
            update_user_points(pid, 100, won=True, role='crewmate')
    else:
        await safe_send(context, chat_id, "🔪👑 *القاتل ينتصر!*\n😈 تم القضاء على الطاقم!")
        for pid in game['impostors']:
            update_user_points(pid, 150, won=True, role='impostor')
    
    await asyncio.sleep(1)
    
    roles = "👤 *الأدوار:*\n\n"
    for pid, p in game['players'].items():
        role = "🔪 قاتل" if p['role'] == 'impostor' else "👨‍🚀 طاقم"
        status = "💀" if not p['alive'] else "✅"
        roles += f"{role} | {get_player_name(p)} | {status}\n"
    
    await safe_send(context, chat_id, roles)
    
    duration = (datetime.now() - game['start_time']).seconds // 60
    await safe_send(context, chat_id,
        f"📊 *إحصائيات:*\n⏱️ {duration} دقيقة\n💀 قتلى: {game['kill_count']}\n"
        f"🚨 اجتماعات: {game['meeting_count']}\n\n🎮 /new_game للعبة جديدة!"
    )
    
    await cleanup_game(chat_id)
    del active_games[chat_id]

# ====== أوامر إضافية ======
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user = get_user(update.effective_user.id)
    if not db_user:
        await update.message.reply_text("❌ خطأ!")
        return
    name = db_user['first_name'] or db_user['username'] or 'لاعب'
    wr = (db_user['games_won'] / db_user['games_played'] * 100) if db_user['games_played'] > 0 else 0
    await update.message.reply_text(
        f"📊 *{name}*\n\n🏆 {db_user['points']} نقطة\n🎮 {db_user['games_played']} جولة\n"
        f"✅ {db_user['games_won']} فوز ({wr:.0f}%)\n"
        f"👨‍🚀 طاقم: {db_user['crewmate_wins']}\n🔪 قاتل: {db_user['impostor_wins']}",
        parse_mode='Markdown'
    )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leaders = get_leaderboard()
    if not leaders:
        await update.message.reply_text("❌ لا بيانات!")
        return
    text = "🏆 *المتصدرين*\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(leaders[:10]):
        m = medals[i] if i < 3 else f"{i+1}."
        name = p['first_name'] or p['username'] or str(p['user_id'])
        text += f"{m} {name}: {p['points']}\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def game_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in active_games:
        await update.message.reply_text("❌ لا توجد لعبة!")
        return
    game = active_games[chat_id]
    text = "📊 *حالة اللعبة*\n\n"
    for pid, p in game['players'].items():
        text += f"{'✅' if p['alive'] else '💀'} {get_player_name(p)}\n"
    alive = sum(1 for p in game['players'].values() if p['alive'])
    text += f"\n👥 {alive}/{len(game['players'])}"
    if game.get('doors_locked'): text += "\n🚪 أبواب مقفلة!"
    if game.get('lights_off'): text += "\n🌑 أنوار مطفأة!"
    await update.message.reply_text(text, parse_mode='Markdown')

async def cancel_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in active_games:
        await update.message.reply_text("❌ لا توجد لعبة!")
        return
    game = active_games[chat_id]
    is_admin = False
    try:
        member = await context.bot.get_chat_member(chat_id, user.id)
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            is_admin = True
    except: pass
    
    if user.id != game['creator'] and not is_admin:
        await update.message.reply_text("❌ فقط المنشئ أو المشرف!")
        return
    
    await cleanup_game(chat_id)
    del active_games[chat_id]
    await update.message.reply_text("🗑️ تم الإلغاء!")

async def show_tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_tools or not user_tools[user_id]:
        await update.message.reply_text("🎒 لا أدوات!")
        return
    tools = user_tools[user_id]
    keyboard = [[InlineKeyboardButton(
        f"{t['emoji']} {t['name']}",
        callback_data=f"tool_{user_id}_{i}"
    )] for i, t in enumerate(tools)]
    await update.message.reply_text("🎒 *أدواتك*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_tool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if not data.startswith('tool_'):
        return
    
    parts = data.split('_')
    user_id = int(parts[1])
    idx = int(parts[2])
    
    if query.from_user.id != user_id:
        await query.answer("❌ ليست أدواتك!")
        return
    
    if user_id not in user_tools or idx >= len(user_tools[user_id]):
        await query.edit_message_text("❌ غير متاحة!")
        return
    
    tool = user_tools[user_id].pop(idx)
    effect = tool['effect']
    
    game = None
    group_id = None
    for gid, g in active_games.items():
        if user_id in g['players']:
            game = g
            group_id = gid
            break
    
    if not game or game['status'] != 'playing':
        await query.edit_message_text("❌ ليس الآن!")
        return
    
    effects = {
        'track': lambda: f"📡 تم التتبع!" if not game.get('smoke_active') else "📡 معطل!",
        'camera': lambda: f"📸 تم التصوير!",
        'lie_detector': lambda: f"🕵️ تم الكشف!",
        'shield': lambda: set_shield(user_id, game),
        'speed_boost': lambda: speed_boost(user_id, game),
        'smoke_bomb': lambda: smoke(group_id, game, context),
        'disguise': lambda: f"🎭 تنكرت! +1 مهمة",
        'lock_doors': lambda: lock_doors(group_id, game, context),
        'jam_comms': lambda: jam_comms(group_id, game, context),
        'lights_off': lambda: lights_off(group_id, game, context)
    }
    
    if effect in effects:
        result = effects[effect]()
        if isinstance(result, str):
            await query.edit_message_text(result, parse_mode='Markdown')

def set_shield(uid, game):
    game['players'][uid]['shield'] = True
    return "🛡️ محمي!"

def speed_boost(uid, game):
    game['players'][uid]['tasks'] = min(game['players'][uid]['total_tasks'], game['players'][uid]['tasks'] + 1)
    return "⚡ +1 مهمة!"

def smoke(gid, game, ctx):
    game['smoke_active'] = True
    asyncio.create_task(restore_smoke(gid, game, ctx))
    return "💨 دخان!"

def lock_doors(gid, game, ctx):
    game['doors_locked'] = True
    asyncio.create_task(restore_doors(gid, game, ctx))
    return "🚪 أقفلت!"

def jam_comms(gid, game, ctx):
    game['emergency_blocked'] = True
    asyncio.create_task(restore_comms(gid, game, ctx))
    return "📵 تشويش!"

def lights_off(gid, game, ctx):
    game['lights_off'] = True
    asyncio.create_task(restore_lights(gid, game, ctx))
    return "🌑 أطفئت!"

async def restore_smoke(gid, game, ctx):
    await asyncio.sleep(60)
    if gid in active_games:
        game['smoke_active'] = False
        await safe_send(ctx, gid, "💨 انقشع الدخان!")

async def restore_doors(gid, game, ctx):
    await asyncio.sleep(30)
    if gid in active_games:
        game['doors_locked'] = False
        await safe_send(ctx, gid, "🚪 فتحت!")

async def restore_comms(gid, game, ctx):
    await asyncio.sleep(60)
    if gid in active_games:
        game['emergency_blocked'] = False
        await safe_send(ctx, gid, "📶 عادت!")

async def restore_lights(gid, game, ctx):
    await asyncio.sleep(30)
    if gid in active_games:
        game['lights_off'] = False
        await safe_send(ctx, gid, "💡 أضيئت!")

async def leave_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in active_games:
        await update.message.reply_text("❌ لا لعبة!")
        return
    if user.id not in active_games[chat_id]['players']:
        await update.message.reply_text("❌ لست فيها!")
        return
    if active_games[chat_id]['status'] != 'waiting':
        await update.message.reply_text("❌ لا يمكنك المغادرة!")
        return
    del active_games[chat_id]['players'][user.id]
    await update.message.reply_text(f"👋 {user.first_name} غادر!")

async def handle_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        db_user = get_user(update.effective_user.id)
        if db_user:
            await update.message.reply_text(f"🔗 كودك: `{db_user['referral_code']}`", parse_mode='Markdown')
        return
    
    ref = context.args[0]
    uid = update.effective_user.id
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT * FROM users WHERE referral_code = %s', (ref,))
    referrer = cursor.fetchone()
    
    if not referrer or referrer['user_id'] == uid:
        cursor.close(); conn.close()
        await update.message.reply_text("❌ غير صالح!")
        return
    
    cursor.execute('UPDATE users SET referred_by = %s WHERE user_id = %s', (referrer['user_id'], uid))
    cursor.execute('UPDATE users SET points = points + 75 WHERE user_id = %s', (referrer['user_id'],))
    cursor.execute('UPDATE users SET points = points + 25 WHERE user_id = %s', (uid,))
    conn.commit()
    cursor.close(); conn.close()
    await update.message.reply_text("🎉 +25 نقطة!")

async def handle_start_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    chat_id = int(parts[2])
    vote = parts[1]
    if chat_id in active_games:
        active_games[chat_id]['start_votes'][query.from_user.id] = vote

# ====== معالج الأزرار العام ======
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    try:
        if data.startswith('mg_'):
            await handle_mini_game(update, context)
        elif data.startswith('sb_'):
            await handle_sabotage(update, context)
        elif data.startswith('v_'):
            await handle_vote(update, context)
        elif data.startswith('tool_'):
            await handle_tool(update, context)
        elif data.startswith('startv_'):
            await handle_start_vote(update, context)
        elif data.startswith('join_'):
            await join_game(update, context)
        else:
            await query.answer()
    except Exception as e:
        logger.error(f"❌ callback: {e}")
        try:
            await query.answer("خطأ!")
        except:
            pass

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Error: {context.error}")

# ====== الرئيسية ======
def main():
    try:
        init_db()
        app = Application.builder().token(BOT_TOKEN).build()
        
        # الأوامر
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("new_game", new_game))
        app.add_handler(CommandHandler("join", join_game))
        app.add_handler(CommandHandler("tasks", execute_task))
        app.add_handler(CommandHandler("emergency", emergency_meeting))
        app.add_handler(CommandHandler("stats", stats))
        app.add_handler(CommandHandler("leaderboard", leaderboard))
        app.add_handler(CommandHandler("status", game_status))
        app.add_handler(CommandHandler("cancel_game", cancel_game))
        app.add_handler(CommandHandler("tools", show_tools))
        app.add_handler(CommandHandler("leave", leave_game))
        app.add_handler(CommandHandler("kill", kill_player))
        app.add_handler(CommandHandler("referral", handle_referral))
        
        # الأزرار
        app.add_handler(CallbackQueryHandler(callback_handler))
        app.add_error_handler(error_handler)
        
        logger.info("🤖🔥 البوت يعمل!")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"❌ main: {e}")

if __name__ == "__main__":
    main()
