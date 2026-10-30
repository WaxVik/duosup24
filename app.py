# -*- coding: utf-8 -*-
"""
DuoSup — Telegram-бот сообщества HuBBlox (Blox Fruits).
Версия 3.0 — полностью переписанный код.

Переменные Railway: BOT_TOKEN, DATABASE_URL (обязательные),
CREATOR_ID, CREATOR_USERNAME, TOPIC_* (необязательные).
Структура базы совместима с прежней версией — данные сохраняются.

Автосток, несколько аккаунтов Parse.bot (необязательно): STOCK_API_URL / STOCK_API_KEY — аккаунт 1,
STOCK_API_URL_2 / STOCK_API_KEY_2 … STOCK_API_URL_5 / STOCK_API_KEY_5 — запасные.
Когда на аккаунте кончаются кредиты, бот сам переходит на следующий (по кругу) и пишет создателю в ЛС.
ERROR_TTL_SECONDS (по умолчанию 15) — через сколько секунд исчезают ошибки в основном чате.

Как редактировать тексты: в сообщениях и кнопках ({N}) — Premium Emoji по номеру
из словаря PREMIUM_EMOJI. ({1.3.12_2}) — несколько эмодзи: "." = без пробела,
"_" = один пробел. Форматирование пишется обычным HTML: <b> <i> <u> <blockquote>.
"""
import asyncio
import html
import logging
import os
import random
import difflib
import re
import secrets
import string
import time as _time
from collections import deque
from datetime import datetime, timedelta, timezone

import asyncpg
from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    ChatMemberUpdated,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    PollAnswer,
    ReplyKeyboardMarkup,
)

LOG = logging.getLogger("duosup")
BOT_VERSION = "3.11.0"

# ============================ НАСТРОЙКИ ============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Переменная {name} должна быть целым числом") from exc


CREATOR_ID = env_int("CREATOR_ID", 7675985792)
CREATOR_USERNAME = os.getenv("CREATOR_USERNAME", "WaxVik0").lstrip("@").strip()

# Номера тем (message_thread_id). 0 или 1 = общая тема без thread.
TOPICS = {
    # ---- основной чат HuBBlox ----
    "welcome": env_int("TOPIC_WELCOME", 1),            # Добро пожаловать (верификация)
    "chat": env_int("TOPIC_CHAT", 7),                  # Чат: здесь работают варны/баны/разбаны
    "rules": env_int("TOPIC_RULES", 6),                # Правила
    "announce": env_int("TOPIC_ANNOUNCE", 16),         # Оповещения (смена правил и т.п.)
    "modlist_main": env_int("TOPIC_MODLIST_MAIN", 27), # Администрация (состав)
    "trades": env_int("TOPIC_TRADES", 8),
    "raids": env_int("TOPIC_RAIDS", 17),
    "sea_events": env_int("TOPIC_SEA_EVENTS", 1232),
    "trials": env_int("TOPIC_TRIALS", 1762),
    "stock": env_int("TOPIC_STOCK", 1233),             # Стоки 24/7
    # ---- админ-чат ----
    "mod_chat": env_int("TOPIC_MOD_CHAT", 6),          # Чат админов (команды модерации)
    "modlog": env_int("TOPIC_MODLOG", 10),             # Состав + лог варнов/банов/разбанов + эскалации
    "appeals": env_int("TOPIC_APPEALS", 9),
    "questions": env_int("TOPIC_QUESTIONS", 387),
    "reports": env_int("TOPIC_REPORTS", 258),          # только репорты участников
    "redact": env_int("TOPIC_REDACT", 8),              # Редакт (только создатель)
    "search": env_int("TOPIC_SEARCH", env_int("TOPIC_MOD_CHAT", 6)),  # заявки на вступление в администрацию
}

LINKS = {
    "trades": "https://t.me/hubblox/8",
    "raids": "https://t.me/hubblox/17",
    "sea": "https://t.me/hubblox/1232",
    "contact": "https://t.me/duosup_bot",
    "chat": "https://t.me/hubblox",
    "stock": "https://t.me/hubblox/1233",
}

MSK = timezone(timedelta(hours=3))
SEP = "•—-—-—-<\u2060✧>-—-—-—•".replace("<", "&lt;").replace(">", "&gt;")
MAX_REASON = 500
MAX_WARNS = 4
APPEAL_WARN_HOURS = 24

# ========================== PREMIUM EMOJI ==========================
# Номер -> ID премиум-эмодзи (из твоего списка).
PREMIUM_EMOJI: dict[int, str] = {
    1: "5368540868951161541", 2: "5375490808935910925", 3: "5377618883626702636",
    4: "5377503327531601899", 5: "5377844588453073647", 6: "5375173844644433295",
    7: "5377524755123439542", 8: "5447644880824181073", 9: "6071317996704370355",
    10: "5334882760735598374", 11: "5269539162654010758", 12: "5375107603363829951",
    13: "5377782964262307848", 14: "5210952531676504517", 15: "5260293700088511294",
    16: "5240241223632954241", 17: "5253742260054409879", 18: "5377752727692544013",
    19: "5274099962655816924", 20: "5206607081334906820", 21: "5341715473882955310",
    22: "5449683594425410231", 23: "5264919878082509254", 24: "5395444784611480792",
    25: "5397782960512444700", 26: "5271604874419647061", 27: "5445267414562389170",
    28: "5438496463044752972", 29: "5217822164362739968", 30: "5325547803936572038",
    31: "5377756253860693612", 32: "5377656524720083736", 33: "5463258057607760727",
    34: "5416117059207572332", 35: "5377641419320102438", 36: "5377738412566548230",
    37: "5420323339723881652", 38: "5406745015365943482", 39: "5188217332748527444",
    40: "5400250414929041085", 41: "5377304659524357459", 42: "5377653767351079538",
    43: "5377754123556914479", 44: "5373012449597335010", 45: "5357080225463149588",
    46: "5436113877181941026", 47: "5271660086224270191", 48: "5271984412089690485",
    49: "5273980249032405225", 50: "5274178831140301085", 51: "5271495318393889259",
    52: "5272003571938794249", 53: "5274053607073819857", 54: "5274246975091417030",
    55: "5273728031372914774", 56: "5271808786581991719", 57: "5273844996217285360",
    58: "5274109639217163111", 59: "5408935401442267103", 60: "5443038326535759644",
    61: "5433825729060018456", 62: "5416081784641168838", 63: "4949575790002963745",
    64: "5413879192267805083", 65: "5350793372594382678", 66: "5348089965559458267",
    67: "5348136325436451221", 68: "5350657479829141382", 69: "5350770579202944020",
    70: "5350668754118292190", 71: "5350725881478293775", 72: "5350488305362315240",
    73: "5282843764451195532",
    74: "5278702045883292456",  # 🛍
    75: "5427168083074628963",  # 💎
    76: "5411225014148014586",  # 🔴 (для «Истёк»)
}

# Обычный символ, который виден, если премиум-эмодзи не отображается (колонка «если скопировать»).
EMOJI_FALLBACK: dict[int, str] = {
    1: "📍", 2: "▫️", 3: "▫️", 4: "▫️", 5: "▫️", 6: "▫️", 7: "▫️", 8: "⚠️", 9: "🎁",
    10: "📝", 11: "🕐", 12: "▫️", 13: "▫️", 14: "❌", 15: "⛔", 16: "🚫", 17: "✉️",
    18: "▫️", 19: "❗", 20: "✔️", 21: "⚙️", 22: "🔼", 23: "▶️", 24: "✏️", 25: "📌",
    26: "🔗", 27: "🗑", 28: "⭐", 29: "👑", 30: "✨", 31: "▫️", 32: "▫️", 33: "🩸",
    34: "➡️", 35: "▫️", 36: "▫️", 37: "⚠️", 38: "⏬", 39: "🔍", 40: "⚖️", 41: "▫️",
    42: "▫️", 43: "▫️", 44: "👤", 45: "🤝", 46: "❓", 47: "🔴", 48: "😔", 49: "🧭",
    50: "⚓", 51: "🏝", 52: "🌊", 53: "👼", 54: "🦈", 55: "🙍‍♂️", 56: "🤖", 57: "👻",
    58: "🐇", 59: "⚔️", 60: "💬", 61: "🧭", 62: "🟢", 63: "🔙", 64: "🗓", 65: "🔥",
    66: "🌋", 67: "💙", 68: "🪙", 69: "💾", 70: "💾", 71: "⚙️", 72: "🏆", 73: "🖥",
    74: "🛍", 75: "💎", 76: "🔴",
}

_PH = re.compile(r"\(\{([0-9._]+)\}\)")


def tg_emoji(number: int, fallback: str | None = None) -> str:
    emoji_id = PREMIUM_EMOJI.get(number)
    char = fallback or EMOJI_FALLBACK.get(number, "▫️")
    if not emoji_id:
        return char
    return f'<tg-emoji emoji-id="{emoji_id}">{char}</tg-emoji>'


def E(spec: str) -> str:
    """'1.3.12_2' -> эмодзи 1,3,12 слитно, пробел, эмодзи 2."""
    groups = []
    for group in spec.split("_"):
        items = [tg_emoji(int(x)) for x in group.split(".") if x.isdigit()]
        if items:
            groups.append("".join(items))
    return " ".join(groups)


def R(text: str) -> str:
    """Заменяет все ({...}) в готовом HTML-тексте на Premium Emoji."""
    return _PH.sub(lambda m: E(m.group(1)), text)


def esc(value: object) -> str:
    """Экранирует пользовательские данные и гасит ({N}) внутри них."""
    return html.escape(str(value if value is not None else ""), quote=False).replace("({", "(\u200b{")


def custom_emoji_html(emoji_id: str | None, fallback: str) -> str:
    if not emoji_id:
        return fallback
    return f'<tg-emoji emoji-id="{esc(emoji_id)}">{fallback}</tg-emoji>'


def clean_btn_text(text: str) -> str:
    return re.sub(r"\s+", " ", _PH.sub("", text)).strip()


def btn(text: str, cb: str | None = None, url: str | None = None, icon_id: str | None = None) -> InlineKeyboardButton:
    """Кнопка. ({N}) в тексте превращается в icon_custom_emoji_id (Telegram не принимает <tg-emoji> в кнопках)."""
    kwargs: dict = {"text": clean_btn_text(text) or "•"}
    if cb:
        kwargs["callback_data"] = cb
    if url:
        kwargs["url"] = url
    if not icon_id:
        m = _PH.search(text)
        if m:
            first = next((x for x in re.split(r"[._]", m.group(1)) if x.isdigit()), None)
            icon_id = PREMIUM_EMOJI.get(int(first)) if first else None
    if icon_id:
        kwargs["icon_custom_emoji_id"] = icon_id
    return InlineKeyboardButton(**kwargs)


def kb(*rows: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


# ============================ КОНСТАНТЫ ============================
FRUITS = [
    ("rocket", "Rocket"), ("spin", "Spin"), ("blade", "Blade"), ("spring", "Spring"),
    ("bomb", "Bomb"), ("smoke", "Smoke"), ("spike", "Spike"), ("flame", "Flame"),
    ("ice", "Ice"), ("sand", "Sand"), ("dark", "Dark"), ("eagle", "Eagle"),
    ("diamond", "Diamond"), ("light", "Light"), ("rubber", "Rubber"), ("ghost", "Ghost"),
    ("magma", "Magma"), ("quake", "Quake"), ("buddha", "Buddha"), ("love", "Love"),
    ("creation", "Creation"), ("spider", "Spider"), ("sound", "Sound"), ("phoenix", "Phoenix"),
    ("portal", "Portal"), ("lightning", "Lightning"), ("pain", "Pain"), ("blizzard", "Blizzard"),
    ("gravity", "Gravity"), ("mammoth", "Mammoth"), ("trex", "T-Rex"), ("dough", "Dough"),
    ("shadow", "Shadow"), ("venom", "Venom"), ("gas", "Gas"), ("spirit", "Spirit"),
    ("tiger", "Leopard"), ("yeti", "Yeti"), ("kitsune", "Kitsune"), ("control", "Control"),
    ("dragon", "Dragon"), ("magnet", "Magnet"),
]

# Фрукты для рейдов: ключ -> (название, {навык: цена}). Порядок навыков = порядок кнопок.
RAID_FRUITS: dict[str, tuple[str, dict[str, int]]] = {
    "flame": ("Пламя", {"Z": 500, "X": 3000, "C": 4000, "V": 5000, "F": 2000}),
    "ice": ("Лёд", {"Z": 500, "X": 3000, "C": 4000, "V": 5000, "F": 2000}),
    "sand": ("Песок", {"Z": 500, "X": 3000, "C": 4000, "V": 5000, "F": 2000}),
    "dark": ("Тьма", {"Z": 500, "X": 3000, "C": 4000, "V": 5000, "F": 2000}),
    "light": ("Свет", {"Z": 500, "X": 3000, "C": 4000, "V": 5000, "F": 2000}),
    "magma": ("Магма", {"Z": 500, "X": 3000, "C": 4000, "V": 5000, "F": 2000}),
    "quake": ("Дрожь", {"Z": 1000, "X": 3000, "C": 5000, "V": 8000}),
    "buddha": ("Будда", {"Z": 500, "X": 3000, "C": 4000, "V": 5000, "F": 2000}),
    "spider": ("Паук", {"Z": 800, "X": 3500, "C": 4500, "V": 6000, "F": 2500}),
    "phoenix": ("Феникс", {"Z": 500, "X": 3000, "C": 4000, "V": 5000, "F": 2000}),
    "dough": ("Тесто", {"Z": 500, "X": 3000, "C": 4000, "M1": 4000, "V": 5000, "F": 2000}),
}
CHIP_FRUITS = {"phoenix", "dough"}

RACES = [("human", "Хуман"), ("cyborg", "Киборг"), ("angel", "Ангел"),
         ("shark", "Шарк"), ("ghoul", "Гуль"), ("mink", "Минк")]

# Морские ивенты: ключ -> (название, номер эмодзи)
SEA_EVENTS = {
    "leviathan": ("Левиафан", 67),
    "volcano": ("Вулканический остров", 66),
    "kitsune": ("Остров Китсуне", 65),
    "seabeast": ("Морской зверь", 52),
    "mirage": ("Остров Мираж", 51),
    "terror": ("Терроршарк", 50),
    "ship": ("Рейд на корабль", 68),
    "other": ("Другое", 0),
}
KIND_EMOJI = {"raid": 69, "trade": 48, "trial": 71, "sea": 49}
KIND_TITLE = {"raid": "Рейд", "trade": "Трейд", "trial": "Триал", "sea": "Морской ивент"}

PERM_RIGHTS = [  # (ключ, название, номер эмодзи, поле Telegram)
    ("info", "Изменение профиля группы", 24, "can_change_info"),
    ("delete", "Удаление сообщений", 27, "can_delete_messages"),
    ("restrict", "Блокировка пользователей", 16, "can_restrict_members"),
    ("invite", "Пригласительные ссылки", 26, "can_invite_users"),
    ("pin", "Закрепление сообщений", 25, "can_pin_messages"),
    ("tags", "Изменение тегов участников", 24, "can_manage_tags"),
    ("video", "Управление трансляциями", 23, "can_manage_video_chats"),
    ("promote", "Назначение администраторов", 22, "can_promote_members"),
    ("topics", "Управление темами", 21, "can_manage_topics"),
]

# ============================ ГЛОБАЛЬНОЕ ============================
db: asyncpg.Pool | None = None
bot: Bot | None = None
BOT_USERNAME = "duosup_bot"

dp = Dispatcher(storage=MemoryStorage())
_locks: dict[tuple, asyncio.Lock] = {}


def lock_for(*key) -> asyncio.Lock:
    return _locks.setdefault(key, asyncio.Lock())


def pool() -> asyncpg.Pool:
    if db is None:
        raise RuntimeError("База данных не инициализирована")
    return db


def B() -> Bot:
    if bot is None:
        raise RuntimeError("Бот не инициализирован")
    return bot


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def fmt_dt(ts: int | None = None) -> str:
    dt = datetime.fromtimestamp(ts or now_ts(), MSK)
    return dt.strftime("%H:%M:%S МСК")


def fmt_date(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, MSK).strftime("%d.%m.%Y")


def num(n: int) -> str:
    """Номер наказания: #-00032."""
    return f"#-{n:05d}"


def app_num(n: int) -> str:
    """Номер заявки: #00045."""
    return f"#{n:05d}"


def thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def thread(topic: int | None) -> int | None:
    return topic if topic and topic > 1 else None


def chat_link_id(chat_id: int) -> str:
    s = str(chat_id)
    return s[4:] if s.startswith("-100") else s.lstrip("-")


def msg_url(chat_id: int, message_id: int | None) -> str | None:
    if not message_id or not str(chat_id).startswith("-100"):
        return None
    return f"https://t.me/c/{chat_link_id(chat_id)}/{message_id}"


def link(label: str, url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{esc(label)}</a>'


def mention(user_id: int, username: str | None = None, name: str | None = None) -> str:
    if username:
        return "@" + esc(username)
    return f'<a href="tg://user?id={user_id}">{esc(name or user_id)}</a>'


CONTACT = "({19})Если нашли ошибки в команде свяжитесь с нами.\n" + f'<u>{link("Contact Us", LINKS["contact"])}</u>'


async def get_config(key: str) -> str | None:
    return await pool().fetchval("SELECT value FROM config WHERE key=$1", key)


async def set_config(key: str, value: object) -> None:
    await pool().execute(
        "INSERT INTO config (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
        key, str(value),
    )


async def next_number(conn, counter: str) -> int:
    return int(await conn.fetchval(
        """INSERT INTO config (key, value) VALUES ($1, '1')
           ON CONFLICT (key) DO UPDATE SET value=(config.value::BIGINT + 1)::TEXT
           RETURNING value::BIGINT""",
        counter,
    ))


async def main_chat() -> int | None:
    v = await get_config("hublox_id")
    return int(v) if v else None


async def admin_chat() -> int | None:
    v = await get_config("hubsup_id")
    return int(v) if v else None


# ============================== БАЗА ==============================
async def init_db() -> None:
    global db
    db = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10, command_timeout=30)
    statements = [
        "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        """CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY, warns INT NOT NULL DEFAULT 0 CHECK (warns >= 0),
            banned BOOL NOT NULL DEFAULT FALSE, ban_until BIGINT)""",
        """CREATE TABLE IF NOT EXISTS warn_logs (
            id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, warn_number TEXT NOT NULL UNIQUE,
            reason TEXT NOT NULL, moderator_id BIGINT NOT NULL, chat_id BIGINT NOT NULL,
            message_id BIGINT, created_at BIGINT NOT NULL, is_active BOOL NOT NULL DEFAULT TRUE)""",
        """CREATE TABLE IF NOT EXISTS ban_logs (
            id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, ban_number TEXT NOT NULL UNIQUE,
            reason TEXT NOT NULL, moderator_id BIGINT NOT NULL, chat_id BIGINT NOT NULL,
            message_id BIGINT, created_at BIGINT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS unban_logs (
            id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, unban_number TEXT NOT NULL UNIQUE,
            moderator_id BIGINT NOT NULL, chat_id BIGINT NOT NULL, message_id BIGINT, created_at BIGINT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS unwarn_logs (
            id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, unwarn_number TEXT NOT NULL UNIQUE,
            moderator_id BIGINT NOT NULL, chat_id BIGINT NOT NULL, message_id BIGINT, created_at BIGINT NOT NULL)""",
        "CREATE TABLE IF NOT EXISTS rules (version TEXT PRIMARY KEY, rule_text TEXT NOT NULL, created_at BIGINT NOT NULL)",
        """CREATE TABLE IF NOT EXISTS appeals (
            id BIGSERIAL PRIMARY KEY, appeal_number TEXT NOT NULL UNIQUE, user_id BIGINT NOT NULL,
            username TEXT, violation_number TEXT NOT NULL, violation_type TEXT NOT NULL DEFAULT 'warn',
            appeal_text TEXT NOT NULL, created_at BIGINT NOT NULL, status TEXT NOT NULL DEFAULT 'pending')""",
        "ALTER TABLE appeals ADD COLUMN IF NOT EXISTS violation_type TEXT NOT NULL DEFAULT 'warn'",
        "CREATE TABLE IF NOT EXISTS appeal_blocks (user_id BIGINT PRIMARY KEY, block_until BIGINT NOT NULL)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS messages_count BIGINT NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS joined_at BIGINT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verified BOOL NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_tag TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_comment TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_username TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_prompt_pending BOOL NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS achievements TEXT",
        "ALTER TABLE rules ADD COLUMN IF NOT EXISTS is_html BOOL NOT NULL DEFAULT FALSE",
        """CREATE TABLE IF NOT EXISTS wiki_entries (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            norm TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL DEFAULT 'Другое',
            aliases TEXT NOT NULL DEFAULT '[]',
            obtain TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            photos TEXT NOT NULL DEFAULT '[]',
            updated_at BIGINT NOT NULL DEFAULT 0)""",
        "ALTER TABLE wiki_entries ADD COLUMN IF NOT EXISTS videos TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE wiki_entries ADD COLUMN IF NOT EXISTS skills TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE wiki_entries ADD COLUMN IF NOT EXISTS stats TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE wiki_entries ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS claimed_by BIGINT",
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS claimed_at BIGINT",
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS dm_msg BIGINT",
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS card_chat BIGINT",
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS card_msg BIGINT",
        """CREATE TABLE IF NOT EXISTS admin_test_q (
            id SERIAL PRIMARY KEY, pos INT NOT NULL DEFAULT 0, kind TEXT NOT NULL, question TEXT NOT NULL,
            options TEXT NOT NULL DEFAULT '[]', correct INT)""",
        """CREATE TABLE IF NOT EXISTS admin_search (
            id SERIAL PRIMARY KEY, opened_at BIGINT NOT NULL, closed_at BIGINT, questions TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS admin_attempt (
            id SERIAL PRIMARY KEY, search_id INT NOT NULL, user_id BIGINT NOT NULL, started_at BIGINT NOT NULL,
            finished_at BIGINT, status TEXT NOT NULL DEFAULT 'in_progress', correct INT, total INT,
            answers TEXT NOT NULL DEFAULT '[]', admin_chat BIGINT, admin_msg BIGINT,
            decision TEXT, decided_by BIGINT, decided_at BIGINT, UNIQUE (search_id, user_id))""",
        """CREATE TABLE IF NOT EXISTS applications (
            id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', chat_message_id BIGINT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb, created_at BIGINT NOT NULL,
            claimed_by BIGINT, claimed_at BIGINT)""",
        "CREATE INDEX IF NOT EXISTS applications_active_idx ON applications(kind, status)",
        "CREATE TABLE IF NOT EXISTS captcha_pending (user_id BIGINT PRIMARY KEY, chat_id BIGINT NOT NULL, joined_at BIGINT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS link_whitelist (id BIGSERIAL PRIMARY KEY, value TEXT NOT NULL UNIQUE, created_at BIGINT NOT NULL)",
        """CREATE TABLE IF NOT EXISTS questions (
            id BIGSERIAL PRIMARY KEY, question_number TEXT NOT NULL UNIQUE, user_id BIGINT NOT NULL,
            username TEXT, question_text TEXT NOT NULL, created_at BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', answered_by BIGINT, answer_text TEXT)""",
        """CREATE TABLE IF NOT EXISTS moderators (
            user_id BIGINT PRIMARY KEY, username TEXT,
            level INT NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 7), role TEXT,
            lives INT NOT NULL DEFAULT 3 CHECK (lives >= 0),
            simulator_data INT NOT NULL DEFAULT 0 CHECK (simulator_data >= 0), activity_month TEXT)""",
        "ALTER TABLE moderators ADD COLUMN IF NOT EXISTS lives INT NOT NULL DEFAULT 3",
        "ALTER TABLE moderators ADD COLUMN IF NOT EXISTS simulator_data INT NOT NULL DEFAULT 0",
        "ALTER TABLE moderators ADD COLUMN IF NOT EXISTS activity_month TEXT",
        """CREATE TABLE IF NOT EXISTS admin_punishment_requests (
            id BIGSERIAL PRIMARY KEY, requester_id BIGINT NOT NULL, target_id BIGINT NOT NULL,
            action TEXT NOT NULL, reason TEXT NOT NULL, chat_id BIGINT NOT NULL,
            source_message_id BIGINT, status TEXT NOT NULL DEFAULT 'pending',
            created_at BIGINT NOT NULL, decided_by BIGINT)""",
        "CREATE TABLE IF NOT EXISTS templates (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        """CREATE TABLE IF NOT EXISTS known_users (
            user_id BIGINT PRIMARY KEY, username TEXT, full_name TEXT, updated_at BIGINT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS known_users_username_lower_idx ON known_users (LOWER(username))",
        """CREATE TABLE IF NOT EXISTS reports (
            id BIGSERIAL PRIMARY KEY, report_number TEXT NOT NULL UNIQUE, reporter_id BIGINT NOT NULL,
            violator_id BIGINT NOT NULL, chat_id BIGINT NOT NULL, message_id BIGINT NOT NULL,
            reason TEXT NOT NULL, created_at BIGINT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            reviewed_by BIGINT, UNIQUE (chat_id, message_id))""",
        """CREATE TABLE IF NOT EXISTS unique_roles (
            user_id BIGINT PRIMARY KEY, username TEXT, role TEXT NOT NULL, created_at BIGINT NOT NULL)""",
        "CREATE TABLE IF NOT EXISTS stock_subs (user_id BIGINT NOT NULL, fruit TEXT NOT NULL, PRIMARY KEY (user_id, fruit))",
        # новое: права, выданные через /premmod
        """CREATE TABLE IF NOT EXISTS admin_rights (
            user_id BIGINT PRIMARY KEY, role TEXT, rights JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at BIGINT NOT NULL)""",
    ]
    async with pool().acquire() as conn:
        for st in statements:
            await conn.execute(st)
        for counter in ("warn_counter", "ban_counter", "unban_counter", "unwarn_counter",
                        "appeal_counter", "report_counter", "question_counter"):
            await conn.execute("INSERT INTO config (key, value) VALUES ($1, '0') ON CONFLICT (key) DO NOTHING", counter)
        for key in ("link_code", "hublox_id", "hubsup_id"):
            await conn.execute("INSERT INTO config (key, value) VALUES ($1, '') ON CONFLICT (key) DO NOTHING", key)
        await conn.execute(
            """INSERT INTO moderators (user_id, username, level, role) VALUES ($1, $2, 7, 'Создатель')
               ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username, level=7, role='Создатель'""",
            CREATOR_ID, CREATOR_USERNAME or None,
        )


# ======================= ПОЛЬЗОВАТЕЛИ И РАНГИ =======================
async def remember_user(user, *, count_message: bool = False, joined: bool = False) -> None:
    if not user or user.is_bot:
        return
    p = pool()
    await p.execute(
        """INSERT INTO known_users (user_id, username, full_name, updated_at) VALUES ($1,$2,$3,$4)
           ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username, full_name=EXCLUDED.full_name,
           updated_at=EXCLUDED.updated_at""",
        user.id, user.username, user.full_name, now_ts(),
    )
    await p.execute(
        """INSERT INTO users (user_id, joined_at, messages_count) VALUES ($1, $2, $3)
           ON CONFLICT (user_id) DO UPDATE SET
             messages_count = users.messages_count + $3,
             joined_at = COALESCE(users.joined_at, $2)""",
        user.id, now_ts(), 1 if count_message else 0,
    )
    if user.username:
        await p.execute("UPDATE moderators SET username=$2 WHERE user_id=$1", user.id, user.username)


class RememberMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            user = getattr(event, "from_user", None)
            if user:
                in_group = isinstance(event, Message) and event.chat.type in ("group", "supergroup")
                await remember_user(user, count_message=in_group)
        except Exception:
            LOG.exception("remember_user failed")
        return await handler(event, data)


def rank_from_level(level: int) -> int:
    """Старые уровни 0–7 -> ранги 0–3 (0 участник, 1 админ, 2 глав. админ, 3 создатель)."""
    if level >= 7:
        return 3
    if level in (2, 6):
        return 2
    if level > 0:
        return 1
    return 0


async def rank_of(user_id: int) -> int:
    if user_id == CREATOR_ID:
        return 3
    level = await pool().fetchval("SELECT level FROM moderators WHERE user_id=$1", user_id)
    return rank_from_level(int(level or 0))


RANK_NAMES = {0: "Участник", 1: "Админ", 2: "Главный админ", 3: "Создатель"}


async def get_rights(user_id: int) -> dict:
    row = await pool().fetchrow("SELECT rights FROM admin_rights WHERE user_id=$1", user_id)
    if not row:
        return {}
    import json
    value = row["rights"]
    return json.loads(value) if isinstance(value, str) else dict(value or {})


async def max_warns_for(user_id: int) -> int:
    """4 — создателю, главным админам и админам с правом блокировки; 3 — остальным админам."""
    rank = await rank_of(user_id)
    if rank >= 2:
        return 4
    if rank == 1 and (await get_rights(user_id)).get("restrict"):
        return 4
    return 3


CMD_PERMS = [  # (ключ, название, ранг, которому команда доступна по умолчанию)
    ("warn", "/warn — выдать варн", 1),
    ("ban", "/ban — выдать бан", 1),
    ("unwarn", "/unwarn — снять варн", 2),
    ("unban", "/unban — снять бан", 2),
    ("del", "/del — удалить сообщение", 2),
    ("award", "Наградить — выдать награду", 1),
    ("appeals", "Апелляции — рассматривать", 2),
    ("reports", "Репорты — рассматривать", 1),
    ("questions", "Вопросы — отвечать", 2),
]
PERMS_DEFAULT_OFF = {"appeals", "reports", "questions"}  # эти права по умолчанию выключены у всех, кроме создателя
PERMS_ALL_OFF = os.getenv("PERMS_ALL_OFF", "").strip().lower() in ("1", "true", "yes")  # =1 — выключить по умолчанию вообще всё


async def perm_default(user_id: int, cmd: str, min_rank: int) -> bool:
    if PERMS_ALL_OFF or cmd in PERMS_DEFAULT_OFF:
        return False
    return await rank_of(user_id) >= min_rank


async def cmd_overrides(user_id: int) -> dict:
    raw = await get_config(f"cmdperm_{user_id}")
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


async def can_use(user_id: int, cmd: str, min_rank: int) -> bool:
    """Можно ли пользователю команду: личная настройка из /adminpanel, иначе — по рангу."""
    if user_id == CREATOR_ID:
        return True
    override = await cmd_overrides(user_id)
    if cmd in override:
        return bool(override[cmd])
    return await perm_default(user_id, cmd, min_rank)


async def user_row(user_id: int):
    return await pool().fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)


async def is_banned(user_id: int) -> bool:
    return bool(await pool().fetchval("SELECT banned FROM users WHERE user_id=$1", user_id))


async def get_warns(user_id: int) -> int:
    return int(await pool().fetchval("SELECT warns FROM users WHERE user_id=$1", user_id) or 0)


async def resolve_target(msg: Message, token: str | None):
    """Возвращает (id, username, full_name) или None. Приоритет: ответ на сообщение, затем @username."""
    reply = msg.reply_to_message
    if reply and reply.from_user:
        u = reply.from_user
        if u.is_bot:
            return "bot"
        await remember_user(u)
        return u.id, u.username, u.full_name
    if token and token.startswith("@"):
        name = token[1:]
        if not re.fullmatch(r"[A-Za-z0-9_]{4,32}", name):
            return None
        row = await pool().fetchrow(
            "SELECT user_id, username, full_name FROM known_users WHERE LOWER(username)=LOWER($1)", name)
        if row:
            return row["user_id"], row["username"], row["full_name"]
        try:
            chat = await B().get_chat("@" + name)
            if chat.type == "private":
                return chat.id, chat.username, chat.full_name
        except Exception:
            pass
    return None


async def default_permissions(chat_id: int) -> ChatPermissions:
    try:
        chat = await B().get_chat(chat_id)
        if chat.permissions:
            return chat.permissions
    except Exception:
        pass
    return ChatPermissions(
        can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True,
        can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True,
        can_send_other_messages=True, can_add_web_page_previews=True, can_invite_users=True,
    )


async def target_chats() -> list[int]:
    return [c for c in (await main_chat(), await admin_chat()) if c]


async def mute_everywhere(user_id: int, until: datetime | None) -> str | None:
    """Мут в основном и админ-чате. Возвращает текст ошибки, если не получилось нигде."""
    error = None
    ok = False
    for chat_id in await target_chats():
        try:
            await B().restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False),
                                           until_date=until)
            ok = True
        except Exception as exc:  # бот не админ, пользователь админ, не участник и т.п.
            error = str(exc)
    return None if ok else error


async def unmute_everywhere(user_id: int) -> None:
    for chat_id in await target_chats():
        try:
            await B().restrict_chat_member(chat_id, user_id, permissions=await default_permissions(chat_id))
        except Exception:
            pass


async def strip_admin(user_id: int) -> None:
    for chat_id in await target_chats():
        try:
            await B().promote_chat_member(chat_id, user_id, can_manage_chat=False)
        except Exception:
            pass


def thread_kwargs(message: Message) -> dict:
    t = getattr(message, "message_thread_id", None) if getattr(message, "is_topic_message", False) else None
    return {"message_thread_id": t} if t else {}


async def say(target, text: str, markup=None, **kwargs):
    """Отправка с рендером Premium Emoji. target: Message | CallbackQuery."""
    message = target.message if isinstance(target, CallbackQuery) else target
    return await message.answer(R(text), reply_markup=markup, **kwargs)


ERROR_TTL = max(5, env_int("ERROR_TTL_SECONDS", 15))  # через сколько секунд исчезают ошибки в основном чате
_bg_tasks: set = set()
_spam_seen: dict[int, int] = {}


def spawn(coro) -> None:
    """Фоновая задача (ссылка хранится, чтобы её не убрал сборщик мусора)."""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _delete_quiet(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _cleanup_later(delay: int, *messages) -> None:
    await asyncio.sleep(delay)
    for m in messages:
        if m is not None:
            await _delete_quiet(m)


def _is_error_text(text: str) -> bool:
    """Ответы, которые начинаются с ⚠️ / ❌ / ⛔ (эмодзи 8, 14, 15), считаются ошибками."""
    return text.lstrip().startswith(("({8})", "({14})", "({15})", tg_emoji(8), tg_emoji(14), tg_emoji(15)))


async def _in_main_chat(msg: Message) -> bool:
    try:
        return msg.chat.type in ("group", "supergroup") and msg.chat.id == await main_chat()
    except Exception:
        return False


async def reply(msg: Message, text: str, markup=None, **kwargs):
    sent = await msg.reply(R(text), reply_markup=markup, **kwargs)
    # В основном чате HuBBlox остаются только выполненные команды: ошибка и неудачная команда исчезают.
    # В админ-чате и в личке ничего не удаляется.
    if _is_error_text(text) and await _in_main_chat(msg):
        own = (msg.text or msg.caption or "").lstrip()
        failed_cmd = msg if (own.startswith("/") or own.lower().startswith("наградить")) else None
        spawn(_cleanup_later(ERROR_TTL, sent, failed_cmd))
    return sent


async def spam_notice(msg: Message, text: str) -> None:
    """Команда не там, где нужно. В основном чате: одно сообщение на 15 секунд, повторы тихо удаляются."""
    if not await _in_main_chat(msg):
        await reply(msg, text)
        return
    uid = msg.from_user.id if msg.from_user else 0
    now = now_ts()
    if len(_spam_seen) > 2000:
        for key in [k for k, v in _spam_seen.items() if now - v > 60]:
            _spam_seen.pop(key, None)
    if now - _spam_seen.get(uid, 0) < ERROR_TTL:
        await _delete_quiet(msg)  # спам: нового уведомления нет, сама команда удаляется
        return
    _spam_seen[uid] = now
    sent = await msg.reply(R(text))
    spawn(_cleanup_later(ERROR_TTL, sent, msg))


async def edit(cb: CallbackQuery, text: str, markup=None):
    try:
        await cb.message.edit_text(R(text), reply_markup=markup)
    except Exception as exc:
        if "not modified" not in str(exc).lower():
            LOG.warning("edit failed: %s", exc)
    try:
        await cb.answer()
    except Exception:
        pass


async def dm(user_id: int, text: str, markup=None) -> bool:
    try:
        await B().send_message(user_id, R(text), reply_markup=markup)
        return True
    except Exception:
        return False


async def to_admin_chat(topic_key: str, text: str, markup=None):
    """Сообщение в админ-чат (нужную тему). Если чат не привязан — в личку создателю."""
    chat_id = await admin_chat()
    if chat_id:
        try:
            return await B().send_message(chat_id, R(text), reply_markup=markup,
                                          message_thread_id=thread(TOPICS.get(topic_key)))
        except Exception:
            LOG.exception("send to admin chat failed")
    try:
        return await B().send_message(CREATOR_ID, R(text), reply_markup=markup)
    except Exception:
        return None


def topic_of(msg: Message) -> int | None:
    """Номер темы, в которой написано сообщение (None — общая тема / обычная группа)."""
    return msg.message_thread_id if getattr(msg, "is_topic_message", False) else None


async def admin_log(text: str, markup=None) -> None:
    """Лог модерации в админ-чат (тема «Состав админ»). Без запасного варианта в ЛС."""
    chat_id = await admin_chat()
    if not chat_id:
        return
    try:
        await B().send_message(chat_id, R(text), reply_markup=markup,
                               message_thread_id=thread(TOPICS["modlog"]))
    except Exception:
        LOG.exception("admin_log failed")


# ============================ МОДЕРАЦИЯ ============================
e = tg_emoji

STAGES = (
    "• 1/4 — предупреждение {w}\n• 2/4 — мут на 5 минут {w}\n"
    "• 3/4 — мут на 24 часа {w}\n• 4/4 — бан {w}"
)


def stages_block() -> str:
    return STAGES.format(w=e(8))


def err_block(title: str, reasons: str, examples: str) -> str:
    return (
        f"{e(8)}<b>{title}</b>\n<blockquote>Возможные причины\n{reasons}\n"
        f"Пример применения команды:\n{examples}</blockquote>\n" + CONTACT
    )


ERR_WARN = err_block(
    "Ошибка выдачи варна",
    "• Не указано имя пользователя.\n    <i>Ответьте на сообщение нарушителя\n    либо укажите @username.</i>\n"
    "• Нет причины:\n    <i>({8})Укажите причину выдачи варна.</i>\n"
    "• Не указано кол-во варнов.\n    <i>({8})Укажите количество варнов.</i>",
    "• С ответом на сообщение:\n    <i>/warn (n) &lt;причина&gt;</i>\n• Без ответа:\n    <i>/warn (n) @username &lt;причина&gt;</i>",
)
ERR_BAN = err_block(
    "Ошибка выдачи бана",
    "• Не указано имя пользователя.\n    <i>Ответьте на сообщение нарушителя\n    либо укажите @username.</i>\n"
    "• Нет причины:\n    <i>({8})Укажите причину выдачи бана.</i>",
    "• С ответом на сообщение:\n    <i>/ban &lt;причина&gt;</i>\n• Без ответа:\n    <i>/ban @username &lt;причина&gt;</i>",
)
ERR_UNWARN = err_block(
    "Ошибка снятие варна",
    "• Не указано имя пользователя.\n    <i>Ответьте на сообщение пользователя\n    либо укажите @username.</i>\n"
    "• Не указано кол-во снятий варнов.\n    <i>({8})Укажите количество снятий варнов.</i>\n"
    "• Нет активных варнов.\n    <i>({8})У пользователя нет активных варнов.</i>",
    "• С ответом на сообщение:\n    <i>/unwarn (n)</i>\n• Без ответа:\n    <i>/unwarn (n) @username</i>",
)
ERR_UNBAN = err_block(
    "Ошибка снятие бана",
    "• Не указано имя пользователя.\n    <i>Ответьте на сообщение пользователя\n    либо укажите @username.</i>\n"
    "• Пользователь не забанен.\n    <i>({8})Пользователя не забанен.</i>",
    "• С ответом на сообщение:\n    <i>/unban</i>\n• Без ответа:\n    <i>/unban @username</i>",
)

RULES_LINE = "Пожалуйста ознакомьтесь с правилами сообщества HuBBlox. ({33})"


def command_args(msg: Message) -> list[str]:
    parts = (msg.text or msg.caption or "").split(maxsplit=1)
    return parts[1].split() if len(parts) > 1 else []


def parse_punish(msg: Message, with_count: bool):
    """-> (count|None, @token|None, reason)."""
    tokens = command_args(msg)
    count = None
    if with_count and tokens and tokens[0].isdigit():
        count = int(tokens.pop(0))
    token = None
    if not msg.reply_to_message and tokens and tokens[0].startswith("@"):
        token = tokens.pop(0)
    return count, token, " ".join(tokens).strip()


async def in_group(msg: Message) -> bool:
    if msg.chat.type in ("group", "supergroup"):
        return True
    await reply(msg, "({8})Команда работает только в группе.")
    return False


async def mod_group(msg: Message) -> bool:
    """Команды наказаний работают в теме «Чат» основного чата и в теме «Чат» админ-чата."""
    if msg.chat.type not in ("group", "supergroup"):
        await reply(msg, "({8})Команда работает только в группе.")
        return False
    topic = topic_of(msg)
    if msg.chat.id == await main_chat() and topic == TOPICS["chat"]:
        return True
    if msg.chat.id == await admin_chat() and topic == TOPICS["mod_chat"]:
        return True
    await reply(msg, "({8})Эта команда работает только в теме «Чат».")
    return False


async def redact_zone(msg: Message) -> bool:
    """Редактор (эмодзи, правила, ссылки): только создатель — в теме «Редакт» админ-чата или в ЛС бота."""
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await reply(msg, "({15})У вас недостаточно прав")
        return False
    if msg.chat.type == "private":
        return True
    if msg.chat.id == await admin_chat() and topic_of(msg) == TOPICS["redact"]:
        return True
    await reply(msg, "({15})Эта команда работает только в теме «Редакт» админ-чата или в личке с ботом.")
    return False


async def log_action(title: str, actor_id: int, uid: int, uname, fname, reason: str | None, ident: str,
                     chat_id: int, msg_id: int | None, extra: str = "") -> None:
    """Запись о наказании в админ-чат."""
    if actor_id == B().id:
        actor = "DuoSup (автоварн)"
    else:
        row = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", actor_id)
        actor = mention(actor_id, row and row["username"], row and row["full_name"])
    text = (f"{e(21)} <b>{esc(title)}</b>\n<blockquote>Модератор: {actor}\n"
            f"Нарушитель: {mention(uid, uname, fname)}\n"
            + (f"Причина: {esc(reason)}\n" if reason else "") + extra +
            f"ID • <i>{esc(ident)}</i>\n{e(11)}{fmt_dt()}</blockquote>")
    url = msg_url(chat_id, msg_id)
    await admin_log(text, kb([btn("({26}) Перейти к сообщению", url=url)]) if url else None)


def appeal_markup(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = []
    for kind, number in items:
        label = "({10}) Подать апелляцию" if len(items) == 1 else f"({{10}}) Подать апелляцию {number}"
        url = f"https://t.me/{BOT_USERNAME}?start=appeal_{kind}_{number[1:]}"
        rows.append([btn(label, url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def warn_text(m: str, count: int, reason: str, numbers: list[str], ts: int | None, auto: bool) -> str:
    title = E("2.3.4.5.3.2.6.7") if auto else E("3.12.13.2.7_3.2.6.7")
    ids = ", ".join(numbers)
    body = (
        f"{title}\n<b>Выдан:</b> {m} ({count}/{MAX_WARNS})\n"
        f"<blockquote><b>Причина:</b> «{esc(reason)}»\n{SEP}\n{stages_block()}\n{SEP}\n"
        f"ID • <i>{ids}</i>"
    )
    if not auto:
        body += f"\n{e(11)}Время выдачи: {fmt_dt(ts)}"
    body += "</blockquote>"
    if not auto:
        body += f"\n{e(9)}<i>Апелляцию можно подать в течение {APPEAL_WARN_HOURS} часов с момента выдачи.</i>"
    return body


def ban_text(m: str, reason: str, number: str, ts: int | None) -> str:
    return (
        f"{E('3.12.13.2.7_18.2.7')}\n{m} получает бан\n"
        f"<blockquote>причина: {esc(reason)}\nID_BAN • <i>{number}</i>\n"
        f"{e(11)}Время выдачи: {fmt_dt(ts)}</blockquote>\n"
        f"Вы можете подать апелляцию в любое время. {e(11)}"
    )


async def escalate(msg: Message, actor_id: int, target_id: int, action: str, reason: str) -> None:
    """Админ пытается наказать равного/старшего — решает создатель."""
    row_id = await pool().fetchval(
        """INSERT INTO admin_punishment_requests
           (requester_id, target_id, action, reason, chat_id, source_message_id, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
        actor_id, target_id, action, reason, msg.chat.id, msg.message_id, now_ts(),
    )
    await reply(msg, f"{e(15)} <b>Вы не можете выдать наказание этому администратору.</b>\n"
                     f"<blockquote>Запрос отправлен создателю на рассмотрение.{e(17)}</blockquote>")
    actor = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", actor_id)
    target = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", target_id)
    a = mention(actor_id, actor and actor["username"], actor and actor["full_name"])
    t = mention(target_id, target and target["username"], target and target["full_name"])
    text = (
        f"<b>Требуется ваше решение</b> @{esc(CREATOR_USERNAME)}\n"
        f"Пожалуйста ознакомьтесь с ситуацией и примите нужные меры наказания, если они есть.\n"
        f"<blockquote>Инициатор: {a}\nНарушитель: {t}\nДействие: {esc(action)}\nПричина: {esc(reason)}</blockquote>"
    )
    url = msg_url(msg.chat.id, msg.message_id)
    rows = []
    if url:
        rows.append([btn("({34}) Перейти к сообщению", url=url)])
    rows.append([btn("Завершить дело ({20})", f"admdone_{row_id}")])
    await to_admin_chat("modlog", text, InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("admdone_"))
async def admin_request_done(cb: CallbackQuery):
    if cb.from_user.id != CREATOR_ID:
        await cb.answer("⛔ Решение доступно только создателю.", show_alert=True)
        return
    rid = int(cb.data.split("_")[1])
    await pool().execute("UPDATE admin_punishment_requests SET status='closed', decided_by=$2 WHERE id=$1",
                         rid, cb.from_user.id)
    try:
        await cb.message.edit_text(cb.message.html_text + f"\n\n{e(20)} <b>Дело завершено.</b>", reply_markup=None)
    except Exception:
        pass
    await cb.answer("Готово")


async def check_target(msg: Message, actor_id: int, target_id: int, action: str, reason: str, verb: str) -> bool:
    """Проверки: бот, сам себя, иерархия. True — можно продолжать."""
    if target_id == actor_id:
        await reply(msg, f"{e(14)}Нельзя {verb} самому себе.")
        return False
    a_rank, t_rank = await rank_of(actor_id), await rank_of(target_id)
    if actor_id != CREATOR_ID and t_rank > 0 and t_rank >= a_rank:
        await escalate(msg, actor_id, target_id, action, reason)
        return False
    return True


# --------------------------- ВАРН ---------------------------
async def give_warns(chat_id: int, user_id: int, n: int, reason: str, moderator_id: int, source_id: int | None):
    """-> (новый счётчик, [номера варнов], номер_бана|None, ошибка|None)."""
    async with lock_for("warn", user_id):
        p = pool()
        current = await get_warns(user_id)
        new = min(MAX_WARNS, current + n)
        numbers, ban_no = [], None
        async with p.acquire() as conn:
            async with conn.transaction():
                await conn.execute("INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
                for _ in range(new - current):
                    number = num(await next_number(conn, "warn_counter"))
                    numbers.append(number)
                    await conn.execute(
                        """INSERT INTO warn_logs (user_id, warn_number, reason, moderator_id, chat_id, message_id, created_at)
                           VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                        user_id, number, reason, moderator_id, chat_id, source_id, now_ts())
                await conn.execute("UPDATE users SET warns=$2 WHERE user_id=$1", user_id, new)
                if new >= MAX_WARNS:
                    ban_no = num(await next_number(conn, "ban_counter"))
                    await conn.execute(
                        """INSERT INTO ban_logs (user_id, ban_number, reason, moderator_id, chat_id, message_id, created_at)
                           VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                        user_id, ban_no, "Достигнут лимит варнов (4/4)", moderator_id, chat_id, source_id, now_ts())
                    await conn.execute("UPDATE users SET banned=TRUE, ban_until=NULL WHERE user_id=$1", user_id)
        error = None
        if new >= 2:
            if await rank_of(user_id) > 0 and user_id != CREATOR_ID:
                await strip_admin(user_id)
            until = None
            if new == 2:
                until = datetime.now(timezone.utc) + timedelta(minutes=5)
            elif new == 3:
                until = datetime.now(timezone.utc) + timedelta(hours=24)
            error = await mute_everywhere(user_id, until)
        return new, numbers, ban_no, error


@dp.message(Command("warn"))
async def warn_cmd(msg: Message):
    if not await mod_group(msg) or not msg.from_user:
        return
    actor = msg.from_user.id
    if not await can_use(actor, "warn", 1):
        await reply(msg, "({15})У вас недостаточно прав")
        return
    count, token, reason = parse_punish(msg, True)
    target = await resolve_target(msg, token)
    if target == "bot":
        await reply(msg, "({14})Нельзя наказать бота.")
        return
    if target is None or count is None or not reason:
        await reply(msg, ERR_WARN)
        return
    uid, uname, fname = target
    if len(reason) > MAX_REASON:
        await reply(msg, f"{e(8)}Причина слишком длинная (максимум {MAX_REASON} символов).")
        return
    if not await check_target(msg, actor, uid, f"/warn {count}", reason, "выдать варн"):
        return
    cap = await max_warns_for(actor)
    if count < 1 or count > cap:
        await reply(msg, f"{e(8)}Количество варнов — от 1 до {cap}.")
        return
    if await is_banned(uid):
        await reply(msg, f"{e(8)} Пользователь уже забанен.")
        return
    current = await get_warns(uid)
    if current + count > MAX_WARNS:
        await reply(msg, f"{e(8)}У пользователя уже {current}/{MAX_WARNS} варнов — можно выдать ещё не более {MAX_WARNS - current}.")
        return
    if current + count > cap:
        await reply(msg, f"{e(15)}У вас недостаточно прав.\nВы не можете довести пользователя до бана (4/4).")
        return
    new, numbers, ban_no, error = await give_warns(msg.chat.id, uid, count, reason, actor, msg.message_id)
    items = [("warn", n) for n in numbers]
    await reply(msg, warn_text(mention(uid, uname, fname), new, reason, numbers, None, False), appeal_markup(items))
    await log_action(f"Варн {new}/{MAX_WARNS}", actor, uid, uname, fname, reason, ", ".join(numbers),
                     msg.chat.id, msg.message_id)
    if ban_no:
        await log_action("Бан (лимит варнов 4/4)", actor, uid, uname, fname, "Достигнут лимит варнов (4/4)",
                         ban_no, msg.chat.id, msg.message_id)
    if ban_no:
        await say(msg, ban_text(mention(uid, uname, fname), "Достигнут лимит варнов (4/4)", ban_no, None),
                  appeal_markup([("ban", ban_no)]))
    if error:
        await say(msg, f"{e(8)}Не удалось применить ограничение в Telegram: <i>{esc(error)}</i>\n"
                       "Проверьте, что бот — администратор с правом блокировки.")


# ---------------------------- БАН ----------------------------
async def give_ban(chat_id: int, user_id: int, reason: str, moderator_id: int, source_id: int | None):
    async with lock_for("ban", user_id):
        if await is_banned(user_id):
            return None, None
        if await rank_of(user_id) > 0 and user_id != CREATOR_ID:
            await strip_admin(user_id)
        async with pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute("INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
                number = num(await next_number(conn, "ban_counter"))
                await conn.execute(
                    """INSERT INTO ban_logs (user_id, ban_number, reason, moderator_id, chat_id, message_id, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                    user_id, number, reason, moderator_id, chat_id, source_id, now_ts())
                await conn.execute("UPDATE users SET banned=TRUE, ban_until=NULL WHERE user_id=$1", user_id)
        return number, await mute_everywhere(user_id, None)


@dp.message(Command("ban"))
async def ban_cmd(msg: Message):
    if not await mod_group(msg) or not msg.from_user:
        return
    actor = msg.from_user.id
    if not await can_use(actor, "ban", 1):
        await reply(msg, "({15})У вас недостаточно прав")
        return
    _, token, reason = parse_punish(msg, False)
    target = await resolve_target(msg, token)
    if target == "bot":
        await reply(msg, "({14})Нельзя наказать бота.")
        return
    if target is None or not reason:
        await reply(msg, ERR_BAN)
        return
    uid, uname, fname = target
    if len(reason) > MAX_REASON:
        await reply(msg, f"{e(8)}Причина слишком длинная (максимум {MAX_REASON} символов).")
        return
    if not await check_target(msg, actor, uid, "/ban", reason, "забанить") :
        return
    if await is_banned(uid):
        await reply(msg, f"{e(8)} Пользователь уже забанен.")
        return
    number, error = await give_ban(msg.chat.id, uid, reason, actor, msg.message_id)
    if not number:
        await reply(msg, f"{e(8)} Пользователь уже забанен.")
        return
    m = mention(uid, uname, fname)
    await reply(msg, ban_text(m, reason, number, None), appeal_markup([("ban", number)]))
    await log_action("Бан", actor, uid, uname, fname, reason, number, msg.chat.id, msg.message_id)
    await dm(uid, ban_text("Вы", reason, number, None).replace("Вы получает бан", "Вы получили бан"),
             appeal_markup([("ban", number)]))
    if error:
        await say(msg, f"{e(8)}Не удалось применить ограничение в Telegram: <i>{esc(error)}</i>")


# --------------------------- UNWARN ---------------------------
@dp.message(Command("unwarn"))
async def unwarn_cmd(msg: Message):
    if not await mod_group(msg) or not msg.from_user:
        return
    actor = msg.from_user.id
    if not await can_use(actor, "unwarn", 2):
        await reply(msg, "({15})У вас недостаточно прав для снятия варнов.")
        return
    count, token, _ = parse_punish(msg, True)
    target = await resolve_target(msg, token)
    if target is None or target == "bot" or not count:
        await reply(msg, ERR_UNWARN)
        return
    uid, uname, fname = target
    async with lock_for("warn", uid):
        if actor == CREATOR_ID:
            rows = await pool().fetch(
                "SELECT id FROM warn_logs WHERE user_id=$1 AND is_active ORDER BY id DESC LIMIT $2", uid, count)
        else:  # автоварны (их выдаёт сам бот) главные админы снять не могут
            rows = await pool().fetch(
                "SELECT id FROM warn_logs WHERE user_id=$1 AND is_active AND moderator_id<>$3 "
                "ORDER BY id DESC LIMIT $2", uid, count, B().id)
        if not rows:
            if actor != CREATOR_ID and await pool().fetchval(
                    "SELECT 1 FROM warn_logs WHERE user_id=$1 AND is_active AND moderator_id=$2 LIMIT 1", uid, B().id):
                await reply(msg, "({15})Варны, выданные автоматически (автоварн), может снять только создатель.")
                return
            await reply(msg, ERR_UNWARN)
            return
        removed = len(rows)
        async with pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE warn_logs SET is_active=FALSE WHERE id = ANY($1::bigint[])",
                                   [r["id"] for r in rows])
                left = await conn.fetchval(
                    "UPDATE users SET warns=GREATEST(warns-$2,0) WHERE user_id=$1 RETURNING warns", uid, removed)
                number = num(await next_number(conn, "unwarn_counter"))
                await conn.execute(
                    """INSERT INTO unwarn_logs (user_id, unwarn_number, moderator_id, chat_id, message_id, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6)""", uid, number, actor, msg.chat.id, msg.message_id, now_ts())
    if left is not None and left < 2 and not await is_banned(uid):
        await unmute_everywhere(uid)
    await log_action("Снятие варнов", actor, uid, uname, fname, None, number, msg.chat.id, msg.message_id,
                     extra=f"Снято: {removed} • Осталось: {left}/{MAX_WARNS}\n")
    await reply(msg, (
        f"{E('31.7.32.4_3.2.6.7')}\nС пользователя {mention(uid, uname, fname)}\n"
        f"<blockquote>Количество снятых варнов: {removed}\nОсталось варнов: {left}/{MAX_WARNS}\n"
        f"ID • <i>{number}</i>\n{SEP}\n{RULES_LINE}</blockquote>"))


# --------------------------- UNBAN ---------------------------
@dp.message(Command("unban"))
async def unban_cmd(msg: Message):
    if not await mod_group(msg) or not msg.from_user:
        return
    actor = msg.from_user.id
    if not await can_use(actor, "unban", 2):
        await reply(msg, "({15})У вас недостаточно прав для разбана.")
        return
    _, token, _ = parse_punish(msg, False)
    target = await resolve_target(msg, token)
    if target is None or target == "bot":
        await reply(msg, ERR_UNBAN)
        return
    uid, uname, fname = target
    async with lock_for("ban", uid):
        if not await is_banned(uid):
            await reply(msg, ERR_UNBAN)
            return
        async with pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE users SET banned=FALSE, ban_until=NULL, warns=0 WHERE user_id=$1", uid)
                await conn.execute("UPDATE warn_logs SET is_active=FALSE WHERE user_id=$1 AND is_active", uid)
                number = num(await next_number(conn, "unban_counter"))
                await conn.execute(
                    """INSERT INTO unban_logs (user_id, unban_number, moderator_id, chat_id, message_id, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6)""", uid, number, actor, msg.chat.id, msg.message_id, now_ts())
    for chat_id in await target_chats():
        try:
            await B().unban_chat_member(chat_id, uid, only_if_banned=True)
        except Exception:
            pass
    await unmute_everywhere(uid)
    await log_action("Разбан", actor, uid, uname, fname, None, number, msg.chat.id, msg.message_id)
    await reply(msg, (
        f"{E('31.7.32.4_18.2.7')}\nС пользователя {mention(uid, uname, fname)}\n"
        f"<blockquote>ID • <i>{number}</i>\n{SEP}\n{RULES_LINE}</blockquote>"))


# --------------------------- АВТОВАРН ---------------------------
URL_RE = re.compile(
    r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/)[^\s<>]+|"
    r"\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:com|net|org|ru|io|gg|me|xyz|tk|ly|info|site|online|club|app|"
    r"dev|co|tv|to|cc|ws|link|click|top|pro|fun|live)\b(?:/[^\s]*)?"
)


def normalize_link(value: str) -> str:
    v = value.strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = re.sub(r"^www\.", "", v)
    v = v.replace("telegram.me/", "t.me/")
    return v.rstrip("/.,;:!?)")


def extract_links(msg: Message) -> list[str]:
    text = msg.text or msg.caption or ""
    entities = msg.entities or msg.caption_entities or []
    found = []
    for ent in entities:
        if ent.type == "text_link" and ent.url:
            found.append(ent.url)
        elif ent.type == "url":
            found.append(text[ent.offset: ent.offset + ent.length])
    found += URL_RE.findall(text)
    return [normalize_link(x) for x in found if x]


async def whitelisted(link_norm: str) -> bool:
    rows = await pool().fetch("SELECT value FROM link_whitelist")
    host = link_norm.split("/")[0]
    for r in rows:
        entry = normalize_link(r["value"])
        if not entry:
            continue
        if "/" in entry:
            if link_norm.startswith(entry):
                return True
        elif host == entry or host.endswith("." + entry):
            return True
    return False


async def autowarn_handler(msg: Message) -> None:
    user = msg.from_user
    if not user or user.is_bot or msg.sender_chat or msg.chat.id != await main_chat():
        return
    # Не прошёл проверку «Я не бот» — сообщение удаляем и просим подтвердиться.
    if await rank_of(user.id) == 0:
        row = await user_row(user.id)
        if not (row and row["verified"]) and not await is_tg_admin(msg.chat.id, user.id):
            try:
                await msg.delete()
            except Exception:
                pass
            await start_verification(msg.chat.id, user, on_write=True, topic=topic_of(msg))
            return
    if not (msg.text or msg.caption):
        return
    links = extract_links(msg)
    if not links or await rank_of(user.id) > 0:
        return
    for item in links:
        if not await whitelisted(item):
            break
    else:
        return
    if await is_banned(user.id):
        return
    await auto_warn(msg, "1.15 Запрещенная ссылка")


# ----------------------- БЕЛЫЙ СПИСОК ССЫЛОК -----------------------
@dp.message(Command("redact"))
async def redact_cmd(msg: Message):
    if not await redact_zone(msg):
        return
    await reply(msg, "({21})<b>Редактор</b>\n<blockquote>/redact_add &lt;домен или t.me/путь&gt; — добавить в белый список\n"
                     "/redact_del &lt;домен&gt; — убрать\n/links — показать белый список\n"
                     "/setrules — изменить текст правил (создатель)</blockquote>")


@dp.message(Command("redact_add"))
async def redact_add(msg: Message):
    if not await redact_zone(msg):
        return
    args = command_args(msg)
    if not args:
        await reply(msg, "({8})Укажите домен: <i>/redact_add roblox.com</i>")
        return
    value = normalize_link(args[0])
    await pool().execute("INSERT INTO link_whitelist (value, created_at) VALUES ($1,$2) ON CONFLICT DO NOTHING", value, now_ts())
    await reply(msg, f"({{20}})В белый список добавлено: <code>{esc(value)}</code>")


@dp.message(Command("redact_del"))
async def redact_del(msg: Message):
    if not await redact_zone(msg):
        return
    args = command_args(msg)
    if not args:
        await reply(msg, "({8})Укажите домен: <i>/redact_del roblox.com</i>")
        return
    value = normalize_link(args[0])
    res = await pool().execute("DELETE FROM link_whitelist WHERE value=$1", value)
    await reply(msg, "({20})Удалено." if res.endswith("1") else "({8})Такой записи нет.")


@dp.message(Command("links"))
async def links_cmd(msg: Message):
    if not await redact_zone(msg):
        return
    rows = await pool().fetch("SELECT value FROM link_whitelist ORDER BY value")
    body = "\n".join(f"• <code>{esc(r['value'])}</code>" for r in rows) or "Список пуст — запрещены все ссылки."
    await reply(msg, f"({{26}})<b>Белый список ссылок</b>\n{body}")


# ============================ ПРИВЯЗКА ЧАТОВ ============================
def generate_code() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(5))


@dp.message(Command("link_hublox"))
async def link_hublox(msg: Message):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await reply(msg, "({15})Связывать чаты может только создатель.")
        return
    if msg.chat.type not in ("group", "supergroup"):
        await reply(msg, "({8})Команда работает только в группе.")
        return
    if await admin_chat():
        await reply(msg, "({8})Чаты уже связаны. Чтобы связать заново — /unlink_chats.")
        return
    code = generate_code()
    await set_config("link_code", code)
    await set_config("hublox_id", msg.chat.id)
    await reply(msg, f"({{26}})<b>Код:</b>\n<code>{code}</code>\n\nВ административном чате выполните:\n<code>/link_hubsup {code}</code>")


@dp.message(Command("link_hubsup"))
async def link_hubsup(msg: Message):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await reply(msg, "({15})Связывать чаты может только создатель.")
        return
    if msg.chat.type not in ("group", "supergroup"):
        await reply(msg, "({8})Команда работает только в группе.")
        return
    if await admin_chat():
        await reply(msg, "({8})Чаты уже связаны.")
        return
    if not await main_chat():
        await reply(msg, "({8})Сначала выполните /link_hublox в основном чате.")
        return
    args = command_args(msg)
    saved = await get_config("link_code")
    if not args or not saved or not secrets.compare_digest(args[0], saved):
        await reply(msg, "({14})Неверный или устаревший код.")
        return
    await set_config("hubsup_id", msg.chat.id)
    await set_config("link_code", "")
    await reply(msg, "({20})Административный чат связан с HuBBlox.")
    try:
        await B().send_message(await main_chat(), R("({26}) <b>Административный чат связан.</b> Бот готов к работе."))
    except Exception:
        pass
    await refresh_admin_list()


@dp.message(Command("unlink_chats"))
async def unlink_chats(msg: Message):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        return
    for key in ("hublox_id", "hubsup_id", "link_code"):
        await set_config(key, "")
    await reply(msg, "({20})Привязка чатов сброшена. Свяжите заново: /link_hublox")


# ======================== СОСТАВ АДМИНИСТРАЦИИ ========================
async def build_admin_list() -> str:
    rows = await pool().fetch(
        """SELECT m.user_id, m.username, m.level, k.full_name FROM moderators m
           LEFT JOIN known_users k ON k.user_id = m.user_id WHERE m.level>0 ORDER BY m.level DESC, m.user_id""")
    groups: dict[int, list[str]] = {3: [], 2: [], 1: []}
    for r in rows:
        groups[rank_from_level(int(r["level"]))].append(mention(r["user_id"], r["username"], r["full_name"]))
    uniques = await pool().fetch(
        """SELECT u.user_id, u.username, u.role, k.full_name FROM unique_roles u
           LEFT JOIN known_users k ON k.user_id = u.user_id ORDER BY u.created_at""")
    out = [f"{e(21)} <b>Состав администрации</b>", SEP]
    if groups[3]:
        out.append(f"{e(29)} <b>Создатель</b>\n" + "\n".join(groups[3]))
    if groups[2]:
        out.append(f"{e(30)} <b>Главные админы</b>\n" + "\n".join(groups[2]))
    if groups[1]:
        out.append(f"{e(28)} <b>Админы</b>\n" + "\n".join(groups[1]))
    if uniques:
        out.append(f"{e(75)} <b>Уникальные роли</b>\n" + "\n".join(
            f"{mention(u['user_id'], u['username'], u['full_name'])} — {esc(u['role'])}" for u in uniques))
    return "\n\n".join(out)


async def refresh_admin_list() -> None:
    text = await build_admin_list()
    for chat_id in await target_chats():
        key = f"adminlist_{chat_id}"
        saved = await get_config(key)
        try:
            if saved:
                await B().edit_message_text(text, chat_id=chat_id, message_id=int(saved))
                continue
        except Exception as exc:
            if "not modified" in str(exc).lower():
                continue
        try:
            topic = TOPICS["modlog"] if chat_id == await admin_chat() else TOPICS["modlist_main"]
            sent = await B().send_message(chat_id, text, message_thread_id=thread(topic))
            await set_config(key, sent.message_id)
        except Exception:
            LOG.warning("admin list send failed for %s", chat_id)


@dp.message(Command("admins"))
async def admins_cmd(msg: Message):
    await reply(msg, await build_admin_list())


async def set_rank(user_id: int, username: str | None, rank: int) -> None:
    level = {0: 0, 1: 1, 2: 2}[rank]
    await pool().execute(
        """INSERT INTO moderators (user_id, username, level, role) VALUES ($1,$2,$3,$4)
           ON CONFLICT (user_id) DO UPDATE SET level=$3, username=COALESCE($2, moderators.username),
           role=$4""",
        user_id, username, level, RANK_NAMES.get(rank) if rank else None)
    if rank == 0:
        await pool().execute("UPDATE moderators SET role=NULL WHERE user_id=$1", user_id)
        await pool().execute("DELETE FROM admin_rights WHERE user_id=$1", user_id)
        await strip_admin(user_id)


async def change_rank(msg: Message, delta: int) -> None:
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await reply(msg, "({15})У вас недостаточно прав")
        return
    if not await mod_group(msg):
        return
    args = command_args(msg)
    target = await resolve_target(msg, args[0] if args else None)
    if target is None or target == "bot":
        await reply(msg, "({8})Ответьте на сообщение пользователя либо укажите @username.")
        return
    uid, uname, fname = target
    if uid == CREATOR_ID:
        await reply(msg, "({14})Ранг создателя изменить нельзя.")
        return
    import json
    new = max(0, min(2, await rank_of(uid) + delta))
    await set_rank(uid, uname, new)
    report: list[str] = []
    if new > 0:
        await pool().execute(
            """INSERT INTO admin_rights (user_id, role, rights, updated_at) VALUES ($1,$2,$3::jsonb,$4)
               ON CONFLICT (user_id) DO UPDATE SET role=$2, updated_at=$4""",
            uid, RANK_NAMES[new], json.dumps(DEFAULT_RIGHTS), now_ts())
        report = await grant_default_access(uid, uname, fname, RANK_NAMES[new], msg)
    text = f"({{20}}){mention(uid, uname, fname)} — теперь: <b>{RANK_NAMES[new]}</b>"
    if report:
        text += "\n" + "\n".join(report)
    await reply(msg, text)
    await refresh_admin_list()


@dp.message(Command("upmod"))
async def upmod_cmd(msg: Message):
    await change_rank(msg, +1)


@dp.message(Command("downmod"))
async def downmod_cmd(msg: Message):
    await change_rank(msg, -1)


# ============================== /premmod ==============================
class PremMod(StatesGroup):
    role = State()
    rights = State()


def premmod_markup(rights: dict) -> InlineKeyboardMarkup:
    rows = []
    for key, title, emoji_n, _ in PERM_RIGHTS:
        mark = "✅ " if rights.get(key) else ""
        rows.append([btn(f"({{{emoji_n}}}) {mark}{title}", f"pm_t_{key}")])
    rows.append([btn("Готово ({20})", "pm_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(Command("premmod"))
async def premmod_cmd(msg: Message, state: FSMContext):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await reply(msg, "({15})У вас недостаточно прав")
        return
    if not await mod_group(msg):
        return
    args = command_args(msg)
    target = await resolve_target(msg, args[0] if args else None)
    if target is None or target == "bot":
        await reply(msg, "({8})Ответьте на сообщение пользователя либо укажите @username.")
        return
    uid, uname, fname = target
    await state.clear()
    await state.set_state(PremMod.role)
    await state.update_data(uid=uid, uname=uname, fname=fname, rights={})
    await reply(msg, "Напишите роль для админа ({24})\n<i>Отмена: /cancel</i>")


@dp.message(PremMod.role, F.text, ~F.text.startswith("/"))
async def premmod_role(msg: Message, state: FSMContext):
    if msg.from_user.id != CREATOR_ID:
        return
    role = msg.text.strip()[:64]
    await state.update_data(role=role)
    await state.set_state(PremMod.rights)
    data = await state.get_data()
    await reply(msg, "Выберите админские права для участника:", premmod_markup(data.get("rights", {})))


@dp.callback_query(F.data.startswith("pm_t_"))
async def premmod_toggle(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != CREATOR_ID:
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    data = await state.get_data()
    if await state.get_state() != PremMod.rights.state or "uid" not in data:
        await cb.answer("Сессия устарела — повторите /premmod.", show_alert=True)
        return
    key = cb.data.removeprefix("pm_t_")
    rights = dict(data.get("rights", {}))
    rights[key] = not rights.get(key)
    await state.update_data(rights=rights)
    await cb.message.edit_reply_markup(reply_markup=premmod_markup(rights))
    await cb.answer()


async def promote_in(chat_id: int, user_id: int, rights: dict, title: str) -> bool:
    kw = {"can_manage_chat": True}
    for key, _, _, field in PERM_RIGHTS:
        kw[field] = bool(rights.get(key))
    attempts = [dict(kw)]
    no_tags = {k: v for k, v in kw.items() if k != "can_manage_tags"}
    attempts.append(no_tags)
    attempts.append({k: v for k, v in no_tags.items() if k != "can_manage_topics"})
    ok = False
    for attempt in attempts:
        try:
            await B().promote_chat_member(chat_id, user_id, **attempt)
            ok = True
            break
        except TypeError:
            continue
        except Exception as exc:
            LOG.warning("promote failed in %s: %s", chat_id, exc)
            continue
    if ok:
        try:
            await B().set_chat_administrator_custom_title(chat_id, user_id, title[:16])
        except Exception:
            pass
    return ok


async def is_member(chat_id: int, user_id: int) -> bool:
    try:
        member = await B().get_chat_member(chat_id, user_id)
        return member.status in ("member", "administrator", "creator", "restricted")
    except Exception:
        return False


DEFAULT_RIGHTS = {"delete": True, "invite": True}  # остальное можно поменять вручную в Telegram


async def grant_default_access(uid: int, uname, fname, title: str, msg: Message) -> list[str]:
    """Админка в обоих чатах с минимальными правами (удаление сообщений + пригласительные ссылки)."""
    report = []
    main_id, adm_id = await main_chat(), await admin_chat()
    for label, chat_id in (("Основной чат", main_id), ("Админ-чат", adm_id)):
        if not chat_id:
            continue
        if await is_member(chat_id, uid):
            if await is_tg_admin(chat_id, uid):
                try:
                    await B().set_chat_administrator_custom_title(chat_id, uid, title[:16])
                except Exception:
                    pass
                report.append(f"{e(20)} {label}: уже администратор, права не менял")
            else:
                ok = await promote_in(chat_id, uid, DEFAULT_RIGHTS, title)
                report.append(f"{e(20) if ok else e(14)} {label}: {'админка выдана' if ok else 'не удалось выдать админку'}")
        elif chat_id == adm_id:
            try:
                invite = await B().create_chat_invite_link(
                    chat_id, member_limit=1, expire_date=datetime.now(timezone.utc) + timedelta(days=3),
                    name=f"admin {uid}")
                if not await dm(uid, f"{e(21)} Вас назначили в администрацию HuBBlox: <b>{esc(title)}</b>\n"
                                     f"Вступите в админ-чат по одноразовой ссылке:\n{invite.invite_link}"):
                    await B().send_message(msg.chat.id, R(
                        f"{e(26)} {mention(uid, uname, fname)}, вступите в админ-чат по одноразовой ссылке:\n{invite.invite_link}"),
                        **thread_kwargs(msg))
                report.append(f"{e(26)} {label}: отправлена одноразовая ссылка")
            except Exception as exc:
                report.append(f"{e(14)} {label}: не удалось создать ссылку ({esc(exc)})")
    return report


@dp.message(Command("uniqrole"))
async def uniqrole_cmd(msg: Message):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await reply(msg, "({15})У вас недостаточно прав")
        return
    if not await mod_group(msg):
        return
    import json
    tokens = command_args(msg)
    token = tokens.pop(0) if (not msg.reply_to_message and tokens and tokens[0].startswith("@")) else None
    role = " ".join(tokens).strip()
    target = await resolve_target(msg, token)
    if target is None or target == "bot" or not role:
        await reply(msg, "({8})<b>Ошибка выдачи уникальной роли</b>\n<blockquote>Ответьте на сообщение участника или укажите @username и напишите роль:\n"
                         "<i>/uniqrole &lt;роль&gt;</i>\n<i>/uniqrole @username &lt;роль&gt;</i></blockquote>")
        return
    uid, uname, fname = target
    role = role[:32]
    await pool().execute(
        """INSERT INTO unique_roles (user_id, username, role, created_at) VALUES ($1,$2,$3,$4)
           ON CONFLICT (user_id) DO UPDATE SET username=COALESCE($2, unique_roles.username), role=$3""",
        uid, uname, role, now_ts())
    await pool().execute(
        """INSERT INTO admin_rights (user_id, role, rights, updated_at) VALUES ($1,$2,$3::jsonb,$4)
           ON CONFLICT (user_id) DO UPDATE SET role=$2, updated_at=$4""",
        uid, role, json.dumps(DEFAULT_RIGHTS), now_ts())
    report = await grant_default_access(uid, uname, fname, role, msg)
    await reply(msg, f"({{20}}){mention(uid, uname, fname)} — уникальная роль: <b>{esc(role)}</b>\n" + "\n".join(report))
    await refresh_admin_list()


@dp.message(Command("uniqrole_del"))
async def uniqrole_del_cmd(msg: Message):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await reply(msg, "({15})У вас недостаточно прав")
        return
    if not await mod_group(msg):
        return
    args = command_args(msg)
    target = await resolve_target(msg, args[0] if args else None)
    if target is None or target == "bot":
        await reply(msg, "({8})Ответьте на сообщение участника или укажите @username.")
        return
    uid, uname, fname = target
    res = await pool().execute("DELETE FROM unique_roles WHERE user_id=$1", uid)
    if not res.endswith("1"):
        await reply(msg, "({8})У этого участника нет уникальной роли.")
        return
    if await rank_of(uid) == 0:
        await pool().execute("DELETE FROM admin_rights WHERE user_id=$1", uid)
        await strip_admin(uid)
    await reply(msg, f"({{20}})Уникальная роль у {mention(uid, uname, fname)} снята.")
    await refresh_admin_list()


@dp.callback_query(F.data == "pm_done")
async def premmod_done(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != CREATOR_ID:
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    data = await state.get_data()
    if await state.get_state() != PremMod.rights.state or "uid" not in data:
        await cb.answer("Сессия устарела — повторите /premmod.", show_alert=True)
        return
    import json
    uid, uname, role, rights = data["uid"], data.get("uname"), data.get("role", "Админ"), data.get("rights", {})
    await state.clear()
    await pool().execute(
        """INSERT INTO moderators (user_id, username, level, role) VALUES ($1,$2,1,$3)
           ON CONFLICT (user_id) DO UPDATE SET username=COALESCE($2, moderators.username), role=$3,
           level=CASE WHEN moderators.level = 0 THEN 1 ELSE moderators.level END""", uid, uname, role)
    await pool().execute(
        """INSERT INTO admin_rights (user_id, role, rights, updated_at) VALUES ($1,$2,$3::jsonb,$4)
           ON CONFLICT (user_id) DO UPDATE SET role=$2, rights=$3::jsonb, updated_at=$4""",
        uid, role, json.dumps(rights), now_ts())
    report = []
    main_id, adm_id = await main_chat(), await admin_chat()
    for label, chat_id in (("Основной чат", main_id), ("Админ-чат", adm_id)):
        if not chat_id:
            continue
        if await is_member(chat_id, uid):
            ok = await promote_in(chat_id, uid, rights, role)
            report.append(f"{e(20) if ok else e(14)} {label}: {'права выданы' if ok else 'не удалось выдать права'}")
        elif chat_id == adm_id:
            try:
                invite = await B().create_chat_invite_link(
                    chat_id, member_limit=1, expire_date=datetime.now(timezone.utc) + timedelta(days=3),
                    name=f"admin {uid}")
                text = (f"{e(21)} Вас назначили администратором HuBBlox: <b>{esc(role)}</b>\n"
                        f"Вступите в чат администрации по одноразовой ссылке:\n{invite.invite_link}")
                sent = await dm(uid, text)
                if not sent:
                    await B().send_message(cb.message.chat.id, R(
                        f"{e(26)} {mention(uid, uname, data.get('fname'))}, вступите в админ-чат по одноразовой ссылке:\n{invite.invite_link}"),
                        **thread_kwargs(cb.message))
                report.append(f"{e(26)} {label}: отправлена одноразовая ссылка")
            except Exception as exc:
                report.append(f"{e(14)} {label}: не удалось создать ссылку ({esc(exc)})")
    chosen = ", ".join(t for k, t, _, _ in PERM_RIGHTS if rights.get(k)) or "без прав"
    await edit(cb, f"{e(20)} <b>{mention(uid, uname, data.get('fname'))}</b> — <b>{esc(role)}</b>\n"
                   f"<blockquote>Права: {esc(chosen)}</blockquote>\n" + "\n".join(report))
    await refresh_admin_list()


# =================== ВХОД В ЧАТЫ: ВЕРИФИКАЦИЯ И АДМИН-ЧАТ ===================
WELCOME_RULES = (
    f"<blockquote>{e(73)}Незнание правил не освобождает от наказания\n"
    f"{e(61)}В ЛС DuoSup доступны:\n• рейды\n• морские ивенты\n\n• трейды\n• триалы\n• профиль\n"
    "• заявки\n• апелляции\n• вопросы\n— Ознакомьтесь с правилами в теме «Правила».</blockquote>"
)


_last_prompt: dict[int, float] = {}


async def start_verification(chat_id: int, user, on_write: bool = False, topic: int | None = None) -> None:
    """Показывает кнопку «Я не бот» (не чаще раза в 2 минуты на человека)."""
    import time
    if time.time() - _last_prompt.get(user.id, 0) < 120:
        return
    _last_prompt[user.id] = time.time()
    await pool().execute(
        "INSERT INTO captcha_pending (user_id, chat_id, joined_at) VALUES ($1,$2,$3) "
        "ON CONFLICT (user_id) DO UPDATE SET chat_id=$2, joined_at=$3", user.id, chat_id, now_ts())
    m = mention(user.id, user.username, user.full_name)
    if on_write:
        text = (f"{e(8)} {m}, подтвердите, что вы не бот.\n"
                "<blockquote>Сообщения неподтверждённых участников удаляются. Нажмите кнопку ниже.</blockquote>")
    else:
        text = (f"👋 Добро пожаловать, {m}!\nРады видеть вас в нашем сообществе.\n"
                "Пожалуйста, подтвердите свой профиль.")
    try:
        # при входе — в тему «Чат»; при сообщении в другом месте — прямо в ту тему, где человек написал
        target_topic = topic if on_write else TOPICS["chat"]
        await B().send_message(chat_id, R(text), message_thread_id=thread(target_topic),
                               reply_markup=kb([btn("({20}) Я не бот", f"verify_{user.id}")]))
    except Exception:
        LOG.exception("welcome send failed")


async def is_tg_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await B().get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


@dp.message(F.new_chat_members)
async def on_new_members(msg: Message):
    if msg.chat.id != await main_chat():
        return
    for user in msg.new_chat_members or []:
        if user.is_bot:
            continue
        await remember_user(user, joined=True)
        if await is_banned(user.id):
            await mute_everywhere(user.id, None)
            continue
        if await rank_of(user.id) > 0:
            continue
        row = await user_row(user.id)
        if row and row["verified"]:
            continue
        await start_verification(msg.chat.id, user)


@dp.chat_member()
async def on_chat_member(update: ChatMemberUpdated):
    old, new = update.old_chat_member.status, update.new_chat_member.status
    joined = old in ("left", "kicked") and new in ("member", "restricted")
    if not joined:
        return
    user = update.new_chat_member.user
    if user.is_bot:
        return
    await remember_user(user, joined=True)
    chat_id = update.chat.id
    if chat_id == await admin_chat():
        row = await pool().fetchrow("SELECT role, rights FROM admin_rights WHERE user_id=$1", user.id)
        if row and (await rank_of(user.id) > 0 or await pool().fetchval("SELECT 1 FROM unique_roles WHERE user_id=$1", user.id)):
            import json
            rights = row["rights"] if isinstance(row["rights"], dict) else json.loads(row["rights"] or "{}")
            if await promote_in(chat_id, user.id, rights, row["role"] or "Админ"):
                try:
                    await B().send_message(chat_id, R(f"{e(20)} {mention(user.id, user.username, user.full_name)} "
                                                      f"вступил в админ-чат. Права выданы: <b>{esc(row['role'])}</b>"),
                                           message_thread_id=thread(TOPICS["mod_chat"]))
                except Exception:
                    pass
        return
    if chat_id != await main_chat():
        return
    if await is_banned(user.id):
        await mute_everywhere(user.id, None)
        return
    if await rank_of(user.id) > 0:
        return
    row = await user_row(user.id)
    if row and row["verified"]:
        return
    await start_verification(chat_id, user)

@dp.callback_query(F.data.startswith("verify_"))
async def verify_cb(cb: CallbackQuery):
    uid = int(cb.data.split("_")[1])
    if cb.from_user.id != uid:
        await cb.answer("Эта кнопка не для вас.", show_alert=True)
        return
    chat_id = cb.message.chat.id
    if not await is_banned(uid) and await get_warns(uid) < 2:
        try:  # снимаем только старое ограничение «до верификации»; муты за варны не трогаем
            await B().restrict_chat_member(chat_id, uid, permissions=await default_permissions(chat_id))
        except Exception:
            pass
    await pool().execute("UPDATE users SET verified=TRUE, roblox_prompt_pending=TRUE WHERE user_id=$1", uid)
    await pool().execute("DELETE FROM captcha_pending WHERE user_id=$1", uid)
    m = mention(uid, cb.from_user.username, cb.from_user.full_name)
    text = f"👋 Добро пожаловать, {m}\nСтатус профиля: {e(20)} Верифицирован\n{WELCOME_RULES}"
    try:
        await cb.message.edit_text(R(text), reply_markup=kb([btn("({44}) Открыть DuoSup", url=f"https://t.me/{BOT_USERNAME}?start=verified")]))
    except Exception:
        pass
    await cb.answer("Профиль подтверждён")
    await dm(uid, "({24})Укажите ваш ник в Roblox.")


# ============================ УДАЛЕНИЕ СООБЩЕНИЙ ============================
@dp.message(Command("del"))
async def del_cmd(msg: Message):
    if not msg.from_user or not await can_use(msg.from_user.id, "del", 2):
        await reply(msg, "({15})У вас недостаточно прав")
        return
    if not await mod_group(msg):
        return
    if not msg.reply_to_message:
        await reply(msg, "({8})Ответьте на сообщение, которое нужно удалить.")
        return
    try:
        await msg.reply_to_message.delete()
        await msg.delete()
    except Exception as exc:
        await reply(msg, f"({{14}})Не удалось удалить: {esc(exc)}")


# ============================ ЛИЧНОЕ МЕНЮ ============================
import json

LINKS["trials"] = "https://t.me/hubblox/1762"
BACK = lambda: btn("({63}) Назад", "menu_back")  # noqa: E731
MAIN_TEXT = f"Добро пожаловать в DuoSup{e(33)}\n<blockquote>Выберите нужный раздел</blockquote>"


class RaidSt(StatesGroup):
    balance = State()
    comment = State()


class SeaSt(StatesGroup):
    name = State()
    count = State()
    details = State()


class TradeSt(StatesGroup):
    create = State()
    find = State()


class TrialSt(StatesGroup):
    comment = State()


class ProfileSt(StatesGroup):
    roblox = State()
    tag = State()
    comment = State()


class AppealSt(StatesGroup):
    text = State()


class QuestionSt(StatesGroup):
    text = State()


class AnswerSt(StatesGroup):
    text = State()


class EmojiSt(StatesGroup):
    fruit = State()
    race = State()


class RulesSt(StatesGroup):
    text = State()


ICON_CACHE: dict[str, str | None] = {"gas": None}  # иконка кнопки «Сток» = эмодзи фрукта Gas из /addemoji


async def refresh_icon_cache() -> None:
    ICON_CACHE["gas"] = (await fruit_icons()).get("gas")


def old_main_menu() -> InlineKeyboardMarkup:
    return kb(
        [btn("({72}) Ивенты", "menu_events")],
        [btn("({74}) Сток", "menu_stock", icon_id=ICON_CACHE.get("gas"))],
        [btn("({49}) Морские ивенты", "menu_sea")],
        [btn("({69}) Создать рейд", "menu_raid")],
        [btn("({48}) Создать трейд", "menu_trade")],
        [btn("({71}) Создать триал", "menu_trial")],
        [btn("({44}) Профиль", "menu_profile")],
        [btn("({10}) Мои заявки", "menu_apps")],
        [btn("({8}) Активные нарушения", "menu_violations")],
        [btn("({10}) Подать апелляцию", "menu_appeal")],
        [btn("({60}) Вопрос | ответ", "menu_question")],
        [btn("({61}) Навигация и правила", "menu_nav")],
    )


def main_menu():
    """Главное меню теперь — кнопки под строкой ввода (reply_menu), инлайн-меню не нужно."""
    return None


def back_only() -> InlineKeyboardMarkup:
    return kb([BACK()])


async def private_only(target) -> bool:
    msg = target.message if isinstance(target, CallbackQuery) else target
    if msg.chat.type == "private":
        return True
    if isinstance(target, CallbackQuery):
        await target.answer("Откройте бота в личных сообщениях.", show_alert=True)
    else:
        await spam_notice(msg, "({8})Эта команда работает только в личных сообщениях с ботом.")
    return False


def json_payload(value) -> dict:
    if isinstance(value, str):
        return json.loads(value or "{}")
    return dict(value or {})



# ======================= МЕНЮ ПОД СТРОКОЙ ВВОДА (reply-клавиатура) =======================
# id Premium Emoji для иконок кнопок. У ✍️ id пока нет — иконка обычным эмодзи.
RM_ICONS = {
    "stock": "5451882707875276247", "notify": "5458603043203327669", "profile": "5413843793147373433",
    "create": "5397916757333654639", "wiki": "5282843764451195532", "lang": "5447410659077661506",
    "nav": "5985479497586053461", "next": "5875506366050734240", "violations": "5771695636411847302",
    "faq": "5314504236132747481", "admin": "5224736245665511429", "find": "5188217332748527444",
    "games": "5361741454685256344", "back": "5875082500023258804", "refresh": "5375338737028841420",
    "history": "5413879192267805083", "roblox": "5220186290456120696",
}
JOIN = "\u2060"  # невидимый символ: отличает «Дальше» на 2-й странице от «Дальше» на 1-й


def rb(label: str, icon: str | None = None, style: str | None = None) -> KeyboardButton:
    """Кнопка reply-меню. style: 'danger' = красная, 'success' = зелёная, None = серая."""
    kwargs: dict = {}
    if icon:
        kwargs["icon_custom_emoji_id"] = RM_ICONS[icon]
    if style:
        kwargs["style"] = style
    return KeyboardButton(text=label, **kwargs)


def reply_menu(page: int = 1) -> ReplyKeyboardMarkup:
    if page == 2:
        rows = [
            [rb("Мои нарушения", "violations"), rb("Вопрос | Ответ", "faq")],
            [rb("✍️ Правила"), rb("О наборах в админ", "admin")],
            [rb("Язык / Language", "lang"), rb("О боте")],
            [rb("Назад", "back", "danger"), rb(f"Дал{JOIN}ьше", "next", "success")],
        ]
    else:
        rows = [
            [rb("Сток", "stock"), rb("Мини игры", "games")],
            [rb("Создать заявку", "create"), rb("Найти заявку", "find")],
            [rb("Профиль", "profile"), rb("Вики", "wiki")],
            [rb("Навигация", "nav"), rb("Дальше", "next", "success")],
        ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


RM_LABELS = {  # текст кнопки (без эмодзи) -> ключ
    "Сток": "stock", "Мини игры": "games", "Создать заявку": "create", "Найти заявку": "find",
    "Профиль": "profile", "Вики": "wiki", "Навигация": "nav", "Дальше": "next1",
    f"Дал{JOIN}ьше": "next2", "Мои нарушения": "violations", "Вопрос | Ответ": "faq", "Правила": "rules",
    "О наборах в админ": "admin", "Язык / Language": "lang", "О боте": "about", "Назад": "back",
}


async def menu_button_filter(msg: Message):
    if msg.chat.type != "private" or not msg.text or msg.text.startswith("/"):
        return False
    key = RM_LABELS.get(re.sub(r"^[^\w]+", "", msg.text).strip())
    return {"menu_key": key} if key else False


class MenuSt(StatesGroup):
    wiki = State()


def type_menu(prefix_cb: dict[str, str], title: str) -> tuple[str, InlineKeyboardMarkup]:
    return title, kb(
        [btn("({49}) Морские ивенты", prefix_cb["sea"])], [btn("({48}) Трейды", prefix_cb["trade"])],
        [btn("({69}) Рейды", prefix_cb["raid"])], [btn("({71}) Триалы", prefix_cb["trial"])], [BACK()])


async def violations_html(uid: int) -> tuple[str, InlineKeyboardMarkup | None]:
    warns = await pool().fetch("SELECT * FROM warn_logs WHERE user_id=$1 AND is_active ORDER BY id", uid)
    ban = None
    if await is_banned(uid):
        ban = await pool().fetchrow("SELECT * FROM ban_logs WHERE user_id=$1 ORDER BY id DESC LIMIT 1", uid)
    if not warns and not ban:
        return "({20})У вас нет активных нарушений.", None
    lines, buttons = [], []
    bot_id = B().id
    for i, w in enumerate(warns, 1):
        lines.append(f"<b>Варн {esc(w['warn_number'])} — {i}/{MAX_WARNS}</b>\n"
                     f"Выдан: {fmt_dt(w['created_at'])}\n<blockquote>{esc(w['reason'])}</blockquote>")
        url = msg_url(w["chat_id"], w["message_id"])
        if url and w["moderator_id"] != bot_id:
            buttons.append([btn(f"({{26}}) Перейти к сообщению {w['warn_number']}", url=url)])
    if ban:
        lines.append(f"<b>Бан {esc(ban['ban_number'])}</b>\nВыдан: {fmt_dt(ban['created_at'])}\n"
                     f"<blockquote>{esc(ban['reason'])}</blockquote>")
        url = msg_url(ban["chat_id"], ban["message_id"])
        if url and ban["moderator_id"] != bot_id:
            buttons.append([btn(f"({{26}}) Перейти к сообщению {ban['ban_number']}", url=url)])
    if await appealable(uid):
        buttons.append([btn("({10}) Подать апелляцию", "menu_appeal")])
    return "({62})<b>Ваши нарушения</b>\n" + "\n".join(lines), (InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None)


@dp.message(menu_button_filter)
async def reply_menu_click(msg: Message, state: FSMContext, menu_key: str):
    if msg.from_user.id in _tests:
        await say(msg, "({8})Сейчас идёт тест набора — сначала завершите его.")
        return
    await state.clear()
    uid = msg.from_user.id
    if menu_key == "next1":
        await say(msg, "<blockquote>Страница 2</blockquote>", reply_menu(2))
    elif menu_key in ("back", "next2"):  # на 2-й странице «Дальше» пока замыкает круг (3-й страницы нет)
        await say(msg, "<blockquote>Страница 1</blockquote>", reply_menu(1))
    elif menu_key == "stock":
        await say(msg, STOCK_MENU_TEXT, await stock_menu_markup(uid))
    elif menu_key == "games":
        await say(msg, "({72})<b>Мини игры</b>\nСкоро: гача, ПВП и комбо-ПВП.")
    elif menu_key == "create":
        t, m = type_menu({"sea": "menu_sea", "trade": "trade_create", "raid": "menu_raid", "trial": "menu_trial"},
                         "({61})<b>Создать заявку</b>\nВыберите тип заявки:")
        await say(msg, t, m)
    elif menu_key == "find":
        t, m = type_menu({"sea": "sea_find", "trade": "trade_find", "raid": "raid_find", "trial": "trial_find"},
                         "({39})<b>Найти заявку</b>\nВыберите тип заявки:")
        await say(msg, t, m)
    elif menu_key == "profile":
        await say(msg, await profile_html(uid), kb([btn("Редактировать профиль ({24})", "profile_edit")], [BACK()]))
    elif menu_key == "wiki":
        idx = await wiki_index()
        if not idx["on"] and uid != CREATOR_ID:
            await say(msg, "({8})Режим вики сейчас выключен.")
            return
        await state.set_state(MenuSt.wiki)
        await say(msg, "({39})<b>Вики</b>\nНазовите предмет, аксессуар или тип — и я расскажу о нём.\n<i>Выйти: /cancel или любая кнопка меню.</i>")
    elif menu_key == "nav":
        await say(msg, await nav_text(), back_only())
    elif menu_key == "violations":
        text, markup = await violations_html(uid)
        await say(msg, text, markup)
    elif menu_key == "faq":
        wait = await question_wait(uid)
        if wait:
            await say(msg, f"⏳ Следующий вопрос можно задать через {-(-wait // 60)} мин.")
            return
        await state.set_state(QuestionSt.text)
        sent = await say(msg, "({60})<b>Вопрос | ответ</b>\nНапишите ваш вопрос одним сообщением.", back_only())
        await state.update_data(prompt_id=sent.message_id)
    elif menu_key == "rules":
        row = await pool().fetchrow("SELECT rule_text, is_html FROM rules ORDER BY created_at DESC LIMIT 1")
        if not row:
            await say(msg, "({8})Правила пока не опубликованы.")
            return
        ver = await pool().fetchval("SELECT version FROM rules ORDER BY created_at DESC LIMIT 1")
        try:
            await send_rich(msg.chat.id, await rules_rich_html(str(ver), row["rule_text"], row["is_html"]), {})
        except Exception as exc:
            LOG.warning("rules in DM: Rich не получился (%s)", exc)
            body = row["rule_text"] if row["is_html"] else esc(row["rule_text"])
            for part in split_html(body):
                await _send_html_safe(msg.chat.id, R(part), None)
    elif menu_key == "admin":
        await search_info(msg)
    elif menu_key == "about":
        await say(msg, about_text())
    elif menu_key == "lang":
        await say(msg, "({8})Выбор языка появится в одном из ближайших обновлений.")


@dp.message(MenuSt.wiki, F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def menu_wiki_query(msg: Message, state: FSMContext):
    idx = await wiki_index()
    eid = idx["keys"].get(wiki_norm(msg.text))
    if not eid:
        await say(msg, f"({{8}})Не нашёл «{esc(msg.text.strip()[:60])}». {esc(wiki_suggest(msg.text, idx['keys']))}")
        return
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", eid)
    await state.clear()
    await wiki_send(msg.chat.id, entry)


# ---------------------------- /start, /cancel ----------------------------
@dp.message(Command("start"))
async def start_cmd(msg: Message, state: FSMContext):
    if msg.chat.type != "private":
        await spam_notice(msg, "({8})Команда /start работает только в личных сообщениях бота.")
        return
    await state.clear()
    args = command_args(msg)
    payload = args[0] if args else ""
    m = re.fullmatch(r"appeal_(warn|ban)_(-\d{5})", payload)
    if m:
        await begin_appeal(msg, state, msg.from_user.id, m.group(1), "#" + m.group(2))
        return
    m = re.fullmatch(r"w_(\d{1,9})", payload)
    if m:  # ссылка из статьи вики: бот рассказывает об этом предмете в личке
        if not (await wiki_index())["on"] and msg.from_user.id != CREATOR_ID:
            await reply(msg, "({8})Режим вики сейчас выключен.")
            return
        entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", int(m.group(1)))
        if entry:
            await wiki_send(msg.chat.id, entry)
        else:
            await reply(msg, "({8})Такой статьи нет.")
        return
    await say(msg, MAIN_TEXT, reply_menu(1))
    row = await user_row(msg.from_user.id)
    if row and row["roblox_prompt_pending"] and not row["roblox_username"]:
        await say(msg, "({24})Укажите ваш ник в Roblox.")


@dp.message(Command("cancel"))
async def cancel_cmd(msg: Message, state: FSMContext):
    if await state.get_state() is None:
        await reply(msg, "({19})Сейчас нет незавершённого действия.")
        return
    await state.clear()
    await reply(msg, "({20})Действие отменено.")


@dp.callback_query(F.data == "menu_back")
async def menu_back(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer()


@dp.callback_query(F.data == "menu_events")
async def menu_events(cb: CallbackQuery):
    await edit(cb, "({72})<b>Ивенты</b>\nСкоро здесь появится новая функция.", back_only())


async def nav_text() -> str:
    rules_row = await pool().fetchrow("SELECT rule_text, is_html FROM rules ORDER BY created_at DESC LIMIT 1")
    text = (f"({{61}})<b>Навигация и правила</b>\n"
            f"• {link('Рейды', LINKS['raids'])}\n• {link('Трейды', LINKS['trades'])}\n"
            f"• {link('Морские ивенты', LINKS['sea'])}\n• {link('Триалы', LINKS['trials'])}\n")
    if rules_row and visible_len(rules_row["rule_text"]) <= 2500:  # длинные правила не помещаются — они в теме «Правила»
        text += (f"\n{rules_row['rule_text']}" if rules_row["is_html"]
                 else f"\n<blockquote>{esc(rules_row['rule_text'])}</blockquote>")
    else:
        text += "\nПравила сообщества опубликованы в теме «Правила»."
    return text


@dp.callback_query(F.data == "menu_nav")
async def menu_nav(cb: CallbackQuery):
    await edit(cb, await nav_text(), back_only())


_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)[^>]*>")


def visible_len(text: str) -> int:
    """Длина текста без HTML-тегов (именно её считает Telegram)."""
    return len(html.unescape(re.sub(r"<[^>]+>", "", text or "")))


def split_html(text: str, limit: int = 3500) -> list[str]:
    """Режет длинный HTML на части по строкам вне открытых тегов — цитаты и форматирование не ломаются."""
    blocks, buf, stack = [], [], []
    for line in text.split("\n"):
        for m in _TAG_RE.finditer(line):
            name = m.group(2).lower()
            if m.group(1):
                if name in stack:
                    del stack[len(stack) - 1 - stack[::-1].index(name)]
            else:
                stack.append(name)
        buf.append(line)
        if not stack:
            blocks.append("\n".join(buf))
            buf = []
    if buf:
        blocks.append("\n".join(buf))
    chunks, cur = [], ""
    for block in blocks:
        cand = f"{cur}\n{block}" if cur else block
        if cur and visible_len(cand) > limit:
            chunks.append(cur)
            cur = block
        else:
            cur = cand
    if cur:
        chunks.append(cur)
    out = []
    for chunk in chunks:  # один сплошной блок длиннее лимита Telegram — режем по пробелам
        while visible_len(chunk) > 3900:
            cut = max(chunk.rfind("\n", 0, 3800), chunk.rfind(" ", 0, 3800))
            cut = cut if cut > 0 else 3800
            out.append(chunk[:cut])
            chunk = chunk[cut:].lstrip()
        out.append(chunk)
    return out or [""]


async def _send_html_safe(chat_id: int, body: str, thread_id: int | None):
    try:
        return await B().send_message(chat_id, body, message_thread_id=thread_id)
    except Exception as exc:
        if "parse" not in str(exc).lower() and "entities" not in str(exc).lower():
            raise
        plain = html.unescape(re.sub(r"<[^>]+>", "", body))  # если разметка сломалась — отправляем без неё
        return await B().send_message(chat_id, plain[:4096], message_thread_id=thread_id, parse_mode=None)


async def publish_rules_html(version: str, text: str, is_html: bool = False) -> None:
    """Правила -> тема «Правила» (длинный текст в нескольких сообщениях), оповещение -> тема «Оповещения»."""
    chat_id = await main_chat()
    if not chat_id:
        return
    shown = text if is_html else esc(text)  # is_html: уже с Premium Emoji и цитатами, как прислал создатель
    header = f"{e(61)} <b>Правила сообщества HuBBlox</b> • v{esc(version)}\n{SEP}\n"
    bodies = [R((header if i == 0 else "") + part) for i, part in enumerate(split_html(shown))]
    raw = await get_config("rules_msg_ids")
    try:
        old_ids = [int(x) for x in json.loads(raw)] if raw else []
    except ValueError:
        old_ids = []
    legacy = await get_config("rules_msg_id")
    if not old_ids and legacy:
        old_ids = [int(legacy)]
    try:
        new_ids = []
        for i, body in enumerate(bodies):
            posted = None
            if i < len(old_ids):
                try:
                    await B().edit_message_text(body, chat_id=chat_id, message_id=old_ids[i])
                    posted = old_ids[i]
                except Exception as exc:
                    if "not modified" in str(exc).lower():
                        posted = old_ids[i]
            if posted is None:
                posted = (await _send_html_safe(chat_id, body, thread(TOPICS["rules"]))).message_id
            new_ids.append(posted)
        for extra in old_ids[len(bodies):]:  # правила стали короче — лишние сообщения убираем
            try:
                await B().delete_message(chat_id, extra)
            except Exception:
                pass
        await set_config("rules_msg_ids", json.dumps(new_ids))
        await set_config("rules_msg_id", new_ids[0])
        url = msg_url(chat_id, new_ids[0])
        await B().send_message(chat_id, R(f"{e(26)} <b>Правила обновлены</b> (версия {esc(version)})\nОзнакомьтесь с изменениями."),
                               message_thread_id=thread(TOPICS["announce"]),
                               reply_markup=kb([btn("({26}) Открыть правила", url=url)]) if url else None)
    except Exception:
        LOG.exception("publish_rules failed")


async def rules_rich_html(version: str, text: str, is_html: bool) -> str:
    shown = text if is_html else esc(text)
    return f"<h2>Правила сообщества HuBBlox</h2><p><i>Версия {esc(version)}</i></p>" + wiki_rich_html(shown, {})


async def publish_rules(version: str, text: str, is_html: bool = False) -> None:
    """Правила — Rich-сообщением (Premium Emoji и цитаты сохраняются). Не получилось — обычным (запасной путь)."""
    chat_id = await main_chat()
    if not chat_id:
        return
    try:
        raw = await get_config("rules_msg_ids")
        old_ids = [int(x) for x in json.loads(raw)] if raw else []
        legacy = await get_config("rules_msg_id")
        if not old_ids and legacy:
            old_ids = [int(legacy)]
        mid = await send_rich(chat_id, await rules_rich_html(version, text, is_html), {}, thread(TOPICS["rules"]))
        for old in old_ids:
            try:
                await B().delete_message(chat_id, old)
            except Exception:
                pass
        await set_config("rules_msg_ids", json.dumps([mid] if mid else []))
        await set_config("rules_msg_id", mid or "")
        url = msg_url(chat_id, mid) if mid else None
        await B().send_message(chat_id, R(f"{e(26)} <b>Правила обновлены</b> (версия {esc(version)})\nОзнакомьтесь с изменениями."),
                               message_thread_id=thread(TOPICS["announce"]),
                               reply_markup=kb([btn("({26}) Открыть правила", url=url)]) if url else None)
        return
    except Exception as exc:
        LOG.warning("rules: Rich не получился (%s), публикую обычным сообщением", exc)
    await publish_rules_html(version, text, is_html)


@dp.message(Command("setrules"))
async def setrules_cmd(msg: Message, state: FSMContext):
    if not await redact_zone(msg):
        return
    await state.set_state(RulesSt.text)
    await reply(msg, "({24})Отправьте новый текст правил одним сообщением.\n<i>Отмена: /cancel</i>")


@dp.message(RulesSt.text, F.text, ~F.text.startswith("/"))
async def setrules_text(msg: Message, state: FSMContext):
    await state.clear()
    rules_html = msg.html_text.strip()  # сохраняет Premium Emoji, цитаты, жирный/курсив и ссылки
    version = str(1 + int(await pool().fetchval("SELECT COUNT(*) FROM rules") or 0))
    await pool().execute("INSERT INTO rules (version, rule_text, created_at, is_html) VALUES ($1,$2,$3,TRUE)",
                         version, rules_html, now_ts())
    await reply(msg, f"({{20}})Правила обновлены (версия {version}).")
    await publish_rules(version, rules_html, True)


# ------------------------------- ПРОФИЛЬ -------------------------------
async def profile_html(user_id: int) -> str:
    row = await user_row(user_id)
    known = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", user_id)
    mod = await pool().fetchrow("SELECT role, level FROM moderators WHERE user_id=$1", user_id)
    username = known["username"] if known else None
    tg = f"@{esc(username)}" if username else mention(user_id, None, known["full_name"] if known else None)
    tag = (row and row["profile_tag"]) or (mod and mod["level"] > 0 and mod["role"]) or "—"
    warns = int(row["warns"]) if row else 0
    comment = (row and row["profile_comment"]) or "—"
    achievements = [x.strip() for x in ((row and row["achievements"]) or "").split("\n") if x.strip()]
    ach = "\n".join(f"• {esc(x)}" for x in achievements) or "• —"
    return (
        f"{e(44)} <b>{tg}</b>\n{SEP}\n"
        f"{e(73)} <b>Ник:</b> {esc((row and row['roblox_username']) or '—')}\n"
        f"{e(25)} <b>Тег:</b> {esc(tag)}\n"
        f"{e(8)} <b>Варны:</b> {warns}/{MAX_WARNS}\n"
        f"{e(60)} <b>Кол-во сообщений:</b> {int(row['messages_count']) if row else 0}\n"
        f"<blockquote><b>Комментарий:</b>\n<i>{esc(comment)}</i>\n"
        f"<b>Награды</b> {e(72)}\n{ach}</blockquote>\n"
        f"{SEP}\n{e(64)} <b>В сообществе с:</b> {fmt_date(row['joined_at'] if row else None)}"
    )


@dp.message(Command("profile"))
async def profile_cmd(msg: Message):
    if not msg.from_user:
        return
    target_id = msg.from_user.id
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        if u.is_bot:
            await reply(msg, "🤖 У ботов нет профиля участника.")
            return
        await remember_user(u)
        target_id = u.id
    owner_dm = msg.chat.type == "private" and target_id == msg.from_user.id
    markup = None
    if owner_dm:
        markup = kb([btn("Редактировать профиль ({24})", "profile_edit")], [btn("Навигация ({61})", "menu_nav")])
    await reply(msg, await profile_html(target_id), markup)


@dp.callback_query(F.data == "menu_profile")
async def menu_profile(cb: CallbackQuery):
    markup = kb([btn("Редактировать профиль ({24})", "profile_edit")], [btn("Навигация ({61})", "menu_nav")], [BACK()])
    await edit(cb, await profile_html(cb.from_user.id), markup)


@dp.callback_query(F.data == "profile_edit")
async def profile_edit(cb: CallbackQuery):
    await edit(cb, "({24})<b>Редактирование профиля</b>\nЧто изменить?", kb(
        [btn("Ник Roblox ({24})", "pset_roblox")], [btn("Тег ({24})", "pset_tag")],
        [btn("Комментарий ({24})", "pset_comment")], [btn("({63}) Назад", "menu_profile")]))


@dp.callback_query(F.data.in_({"pset_roblox", "pset_tag", "pset_comment"}))
async def profile_set(cb: CallbackQuery, state: FSMContext):
    field = cb.data.removeprefix("pset_")
    prompts = {"roblox": "Укажите ваш ник в Roblox.", "tag": "Напишите новый тег (до 32 символов).",
               "comment": "Напишите комментарий для профиля (до 200 символов)."}
    await state.set_state(getattr(ProfileSt, field))
    await edit(cb, f"({{24}}){prompts[field]}\n<i>Отмена: /cancel</i>")


ROBLOX_RE = re.compile(r"[A-Za-z0-9_]{3,20}")


async def save_roblox(msg: Message) -> bool:
    nick = (msg.text or "").strip()
    if not ROBLOX_RE.fullmatch(nick):
        await reply(msg, "({8})Ник должен содержать от 3 до 20 символов: латиница, цифры и «_».")
        return False
    await pool().execute("UPDATE users SET roblox_username=$2, roblox_prompt_pending=FALSE WHERE user_id=$1",
                         msg.from_user.id, nick)
    return True


@dp.message(ProfileSt.roblox, F.text, ~F.text.startswith("/"))
async def profile_roblox_msg(msg: Message, state: FSMContext):
    if await save_roblox(msg):
        await state.clear()
        await reply(msg, "({20})Ник Roblox обновлён.", main_menu())


@dp.message(ProfileSt.tag, F.text, ~F.text.startswith("/"))
async def profile_tag_msg(msg: Message, state: FSMContext):
    if len(msg.text) > 32:
        await reply(msg, "({8})Слишком длинно: максимум 32 символа.")
        return
    await pool().execute("UPDATE users SET profile_tag=$2 WHERE user_id=$1", msg.from_user.id, msg.text.strip())
    await state.clear()
    await reply(msg, "({20})Тег профиля обновлён.", main_menu())


@dp.message(ProfileSt.comment, F.text, ~F.text.startswith("/"))
async def profile_comment_msg(msg: Message, state: FSMContext):
    if len(msg.text) > 200:
        await reply(msg, "({8})Слишком длинно: максимум 200 символов.")
        return
    await pool().execute("UPDATE users SET profile_comment=$2 WHERE user_id=$1", msg.from_user.id, msg.text.strip())
    await state.clear()
    await reply(msg, "({20})Комментарий профиля обновлён.", main_menu())


# ============================== ЗАЯВКИ ==============================
async def fruit_icons() -> dict[str, str]:
    rows = await pool().fetch("SELECT key, value FROM config WHERE key LIKE 'custom_emoji_fruit_%' AND value <> ''")
    return {r["key"].removeprefix("custom_emoji_fruit_"): r["value"] for r in rows}


async def race_icons() -> dict[str, str]:
    rows = await pool().fetch("SELECT key, value FROM config WHERE key LIKE 'custom_emoji_race_%' AND value <> ''")
    return {r["key"].removeprefix("custom_emoji_race_"): r["value"] for r in rows}


def fruit_html(icons: dict, key: str) -> str:
    return custom_emoji_html(icons.get(key), "🍎")


def app_title(app, payload: dict) -> str:
    kind = app["kind"]
    if kind == "raid":
        name = RAID_FRUITS.get(payload.get("fruit"), ("?",))[0]
        return f"Рейд — {name} ({', '.join(payload.get('skills', []))})"
    if kind == "sea":
        return f"Морской ивент — {payload.get('event_name', '')}"
    if kind == "trial":
        return f"Триал — {payload.get('race_name', '')}"
    return "Трейд"


STATUS_LINE = {"active": "({62}) <b>Активна</b>", "taken": "({45}) <b>Помощник найден</b>",
               "closed": "({20}) <b>Завершена</b>"}


async def helpers_html(payload: dict) -> str:
    ids = payload.get("helpers", [])
    if not ids:
        return "пока никого"
    out = []
    for h in ids:
        k = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", h)
        out.append(mention(h, k and k["username"], k and k["full_name"]))
    return ", ".join(out)


async def app_text(app, closed: bool = False) -> str:
    p = json_payload(app["payload"])
    known = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", app["user_id"])
    urow = await user_row(app["user_id"])
    author = mention(app["user_id"], known and known["username"], known and known["full_name"])
    roblox = esc((urow and urow["roblox_username"]) or "—")
    n = num(app["id"])
    kind = app["kind"]
    status = "closed" if closed or app["status"] == "closed" else app["status"]
    comment = p.get("comment")
    people = [f"{e(44)} <b>Автор:</b> {author}", f"{e(73)} <b>Roblox:</b> {roblox}"]
    if kind == "raid":
        icons = await fruit_icons()
        fruit = RAID_FRUITS[p["fruit"]]
        price = sum(fruit[1].get(s, 0) for s in p["skills"])
        header = f"{e(69)} <b>Рейд</b> • <b>{n}</b>"
        details = [f"{fruit_html(icons, p['fruit'])} <b>Фрукт:</b> {esc(fruit[0])}",
                   f"{e(59)} <b>Навыки:</b> {esc(' • '.join(p['skills']))}",
                   f"{e(68)} <b>Баланс:</b> {thousands(p.get('balance', 0))} • <b>Нужно:</b> {thousands(price)}"]
        if p["fruit"] in CHIP_FRUITS:
            details.append(f"{e(70)} <b>Чип:</b> {'да' if p.get('chip') else 'нет'}")
    elif kind == "sea":
        emoji_n = SEA_EVENTS.get(p.get("event"), ("", 0))[1] or 49
        header = f"{e(emoji_n)} <b>{esc(p.get('event_name'))}</b> • <b>{n}</b>"
        details = [f"{e(45)} <b>Участников:</b> {p.get('count')}"]
    elif kind == "trial":
        icons = await race_icons()
        header = f"{e(71)} <b>Триал</b> • <b>{n}</b>"
        details = [f"{custom_emoji_html(icons.get(p.get('race')), '🧬')} <b>Раса:</b> {esc(p.get('race_name'))}"]
    else:
        header = f"{e(48)} <b>Трейд</b> • <b>{n}</b>"
        return (f"{header}\n{SEP}\n{people[0]}\n{SEP}\n<blockquote>{esc(p.get('text'))}</blockquote>\n{SEP}\n"
                f"{STATUS_LINE[status]}")
    out = [header, SEP] + people + details + [SEP]
    if comment:
        out.append(f"<blockquote>{e(25)} {esc(comment)}</blockquote>")
    out.append(f"{e(45)} <b>Помощники:</b> {await helpers_html(p)}")
    out.append(STATUS_LINE[status])
    return "\n".join(out)


def help_markup(app) -> InlineKeyboardMarkup | None:
    if app["kind"] == "trade" or app["status"] == "closed":
        return None
    return kb([btn("({45}) Помочь", f"apph_{app['id']}")])


async def refresh_application_post(app_id: int) -> None:
    """Перерисовывает опубликованную заявку (помощники, статус)."""
    app = await pool().fetchrow("SELECT * FROM applications WHERE id=$1", app_id)
    chat_id = await main_chat()
    if not app or not chat_id or not app["chat_message_id"]:
        return
    try:
        await B().edit_message_text(R(await app_text(app)), chat_id=chat_id, message_id=app["chat_message_id"],
                                    reply_markup=help_markup(app))
    except Exception as exc:
        if "not modified" not in str(exc).lower():
            LOG.warning("refresh post failed: %s", exc)


TOPIC_BY_KIND = {"raid": "raids", "sea": "sea_events", "trade": "trades", "trial": "trials"}


async def create_application(kind: str, user_id: int, payload: dict) -> int | None:
    """Создаёт и публикует заявку. Возвращает id или None, если основной чат не привязан."""
    chat_id = await main_chat()
    if not chat_id:
        return None
    app_id = await pool().fetchval(
        "INSERT INTO applications (user_id, kind, payload, created_at) VALUES ($1,$2,$3::jsonb,$4) RETURNING id",
        user_id, kind, json.dumps(payload), now_ts())
    app = await pool().fetchrow("SELECT * FROM applications WHERE id=$1", app_id)
    sent = await B().send_message(chat_id, R(await app_text(app)), reply_markup=help_markup(app),
                                  message_thread_id=thread(TOPICS[TOPIC_BY_KIND[kind]]))
    await pool().execute("UPDATE applications SET chat_message_id=$2 WHERE id=$1", app_id, sent.message_id)
    return app_id


NO_MAIN = "({8})Основной чат ещё не привязан. Обратитесь к администрации."
SKIP_COMMENT = "<blockquote>Если комментарий не нужен — отправьте <u>-</u></blockquote>"


def clean_comment(text: str) -> str | None:
    t = (text or "").strip()
    return None if t in ("-", "–", "—", "") else t[:500]


# ------------------------------- РЕЙД -------------------------------
@dp.callback_query(F.data == "menu_raid")
async def menu_raid(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    icons = await fruit_icons()
    buttons = [btn(name, f"raid_f_{key}", icon_id=icons.get(key)) for key, (name, _) in RAID_FRUITS.items()]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([btn("({39}) Найти рейд", "raid_find")])
    rows.append([BACK()])
    await edit(cb, "({69})<b>Создание рейда</b>\nВыберите фрукт:", InlineKeyboardMarkup(inline_keyboard=rows))


def skills_markup(fruit: str, selected: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for skill, price in RAID_FRUITS[fruit][1].items():
        mark = "✅ " if skill in selected else ""
        suffix = f" • {thousands(price)}" if price else ""
        rows.append([InlineKeyboardButton(text=f"{mark}{skill}{suffix}", callback_data=f"raid_s_{skill}")])
    rows.append([btn("({63}) Назад", "menu_raid"), btn("Далее ({34})", "raid_next")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def skills_text(fruit: str) -> str:
    icons = await fruit_icons()
    return (f"{fruit_html(icons, fruit)}<b>Выберите навыки для пробуждения.</b>\n"
            f"<blockquote>Можно выбрать от 1 до {len(RAID_FRUITS[fruit][1])} навыков.</blockquote>")


@dp.callback_query(F.data.startswith("raid_f_"))
async def raid_fruit(cb: CallbackQuery, state: FSMContext):
    fruit = cb.data.removeprefix("raid_f_")
    if fruit not in RAID_FRUITS:
        await cb.answer("Неизвестный фрукт", show_alert=True)
        return
    await state.update_data(fruit=fruit, skills=[])
    await edit(cb, await skills_text(fruit), skills_markup(fruit, []))


@dp.callback_query(F.data.startswith("raid_s_"))
async def raid_skill(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    fruit = data.get("fruit")
    skill = cb.data.removeprefix("raid_s_")
    if not fruit or skill not in RAID_FRUITS[fruit][1]:
        await cb.answer("Начните заново: /start", show_alert=True)
        return
    chosen = list(data.get("skills", []))
    chosen = [s for s in chosen if s != skill] if skill in chosen else chosen + [skill]
    order = list(RAID_FRUITS[fruit][1])
    chosen.sort(key=order.index)
    await state.update_data(skills=chosen)
    await cb.message.edit_reply_markup(reply_markup=skills_markup(fruit, chosen))
    await cb.answer()


@dp.callback_query(F.data == "raid_next")
async def raid_next(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("fruit"):
        await cb.answer("Начните заново: /start", show_alert=True)
        return
    if not data.get("skills"):
        await cb.answer("Выберите хотя бы один навык.", show_alert=True)
        return
    await state.set_state(RaidSt.balance)
    await edit(cb, "({24}) <b>Укажите ваш баланс фрагментов.</b>\n"
                   "<blockquote>Баланс будет округлён вниз до 1000-ых.\nОтправьте только число.</blockquote>")


@dp.message(RaidSt.balance, F.text, ~F.text.startswith("/"))
async def raid_balance(msg: Message, state: FSMContext):
    raw = msg.text.strip().replace(" ", "").replace(".", "").replace(",", "")
    if not raw.isdigit():
        await reply(msg, "({8})Отправьте только число.")
        return
    balance = int(raw) // 1000 * 1000
    await state.update_data(balance=balance)
    data = await state.get_data()
    if data["fruit"] in CHIP_FRUITS:
        icons = await fruit_icons()
        text = (f"{fruit_html(icons, 'phoenix')}Феникс/{fruit_html(icons, 'dough')}Тесто\n"
                "Вы можете купить специальный чип?\n<b>Хотите купить чип?</b>")
        await reply(msg, text, kb([btn("({20}) Да", "raid_chip_1"), btn("({14}) Нет", "raid_chip_0")]))
        return
    await state.set_state(RaidSt.comment)
    await reply(msg, f"({{24}})<b>Напишите комментарий к рейду.</b>\n{SKIP_COMMENT}")


@dp.callback_query(F.data.startswith("raid_chip_"))
async def raid_chip(cb: CallbackQuery, state: FSMContext):
    if not (await state.get_data()).get("fruit"):
        await cb.answer("Начните заново: /start", show_alert=True)
        return
    await state.update_data(chip=cb.data.endswith("_1"))
    await state.set_state(RaidSt.comment)
    await edit(cb, f"({{24}})<b>Напишите комментарий к рейду.</b>\n{SKIP_COMMENT}")


@dp.message(RaidSt.comment, F.text, ~F.text.startswith("/"))
async def raid_comment(msg: Message, state: FSMContext):
    data = await state.get_data()
    payload = {"fruit": data["fruit"], "skills": data["skills"], "balance": data.get("balance", 0),
               "chip": bool(data.get("chip")), "comment": clean_comment(msg.text)}
    app_id = await create_application("raid", msg.from_user.id, payload)
    await state.clear()
    if not app_id:
        await reply(msg, NO_MAIN)
        return
    await reply(msg, f"{e(20)} Заявка на рейд опубликована в теме «{link('Рейды', LINKS['raids'])}».", main_menu())


# ---------------------------- МОРСКИЕ ИВЕНТЫ ----------------------------
@dp.callback_query(F.data == "menu_sea")
async def menu_sea(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = []
    for key, (name, emoji_n) in SEA_EVENTS.items():
        label = f"({{{emoji_n}}}) {name}" if emoji_n else f"••• {name}"
        rows.append([btn(label, f"sea_e_{key}")])
    rows.append([btn("({39}) Найти ивент", "sea_find")])
    rows.append([BACK()])
    await edit(cb, "({49})<b>Морские ивенты</b>\nНа какой ивент собираемся?", InlineKeyboardMarkup(inline_keyboard=rows))


def count_markup() -> InlineKeyboardMarkup:
    nums = [InlineKeyboardButton(text=str(i), callback_data=f"sea_n_{i}") for i in range(2, 13)]
    rows = [nums[i:i + 4] for i in range(0, len(nums), 4)]
    rows.append([btn("({63}) Назад", "menu_sea")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


COUNT_TEXT = "<blockquote><i>Выберите количество участников.</i>\nМинимум — 2, максимум — 12.</blockquote>"


@dp.callback_query(F.data.startswith("sea_e_"))
async def sea_event(cb: CallbackQuery, state: FSMContext):
    key = cb.data.removeprefix("sea_e_")
    if key not in SEA_EVENTS:
        await cb.answer("Неизвестный ивент", show_alert=True)
        return
    if key == "other":
        await state.set_state(SeaSt.name)
        await state.update_data(event="other")
        await edit(cb, "({49})Напишите название ивента.\n<i>Отмена: /cancel</i>")
        return
    name, emoji_n = SEA_EVENTS[key]
    await state.update_data(event=key, event_name=name)
    await state.set_state(SeaSt.count)
    await edit(cb, f"({{{emoji_n}}})<b>{esc(name)}</b>\n{COUNT_TEXT}", count_markup())


@dp.message(SeaSt.name, F.text, ~F.text.startswith("/"))
async def sea_name(msg: Message, state: FSMContext):
    name = msg.text.strip()[:60]
    await state.update_data(event="other", event_name=name)
    await state.set_state(SeaSt.count)
    await reply(msg, f"({{49}})<b>{esc(name)}</b>\n{COUNT_TEXT}", count_markup())


async def ask_sea_details(target, state: FSMContext, count: int):
    await state.update_data(count=count)
    await state.set_state(SeaSt.details)
    text = "({10})<b>Напишите комментарий и детали.</b>\nЕсли не нужны — отправьте <u>-</u>."
    if isinstance(target, CallbackQuery):
        await edit(target, text)
    else:
        await reply(target, text)


@dp.callback_query(F.data.startswith("sea_n_"))
async def sea_count_cb(cb: CallbackQuery, state: FSMContext):
    if not (await state.get_data()).get("event_name"):
        await cb.answer("Начните заново: /start", show_alert=True)
        return
    await ask_sea_details(cb, state, int(cb.data.removeprefix("sea_n_")))


@dp.message(SeaSt.count, F.text, ~F.text.startswith("/"))
async def sea_count_msg(msg: Message, state: FSMContext):
    if not msg.text.strip().isdigit() or not 2 <= int(msg.text) <= 12:
        await reply(msg, "({8})Количество участников — от 2 до 12.")
        return
    await ask_sea_details(msg, state, int(msg.text))


@dp.message(SeaSt.details, F.text, ~F.text.startswith("/"))
async def sea_details(msg: Message, state: FSMContext):
    data = await state.get_data()
    payload = {"event": data["event"], "event_name": data["event_name"], "count": data["count"],
               "comment": clean_comment(msg.text)}
    app_id = await create_application("sea", msg.from_user.id, payload)
    await state.clear()
    if not app_id:
        await reply(msg, NO_MAIN)
        return
    await reply(msg, f"{e(20)}Заявка опубликована в теме «{link('Морские ивенты', LINKS['sea'])}».", main_menu())


# ------------------------------- ТРИАЛ -------------------------------
@dp.callback_query(F.data == "menu_trial")
async def menu_trial(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    icons = await race_icons()
    buttons = [btn(name, f"trial_r_{key}", icon_id=icons.get(key)) for key, name in RACES]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([btn("({39}) Найти триал", "trial_find")])
    rows.append([BACK()])
    await edit(cb, "({71})<b>Создание Триала</b>\nВыберите расу:", InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("trial_r_"))
async def trial_race(cb: CallbackQuery, state: FSMContext):
    key = cb.data.removeprefix("trial_r_")
    names = dict(RACES)
    if key not in names:
        await cb.answer("Неизвестная раса", show_alert=True)
        return
    await state.update_data(race=key, race_name=names[key])
    await state.set_state(TrialSt.comment)
    await edit(cb, f"({{24}})<b>Напишите комментарий к триалу.</b>\n{SKIP_COMMENT}")


@dp.message(TrialSt.comment, F.text, ~F.text.startswith("/"))
async def trial_comment(msg: Message, state: FSMContext):
    data = await state.get_data()
    payload = {"race": data["race"], "race_name": data["race_name"], "comment": clean_comment(msg.text)}
    app_id = await create_application("trial", msg.from_user.id, payload)
    await state.clear()
    if not app_id:
        await reply(msg, NO_MAIN)
        return
    await reply(msg, f"{e(20)} Заявка на триал опубликована в теме «{link('Триалы', LINKS['trials'])}».", main_menu())


# ------------------------------- ТРЕЙДЫ -------------------------------
@dp.callback_query(F.data == "menu_trade")
async def menu_trade(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await edit(cb, "({48})<b>Трейды</b>\nВыберите действие:", kb(
        [btn("({48}) Создать трейд", "trade_create")], [btn("({39}) Найти трейд", "trade_find")],
        [btn("({62}) Активные трейды", "trade_active")], [BACK()]))


@dp.callback_query(F.data == "trade_create")
async def trade_create(cb: CallbackQuery, state: FSMContext):
    await state.set_state(TradeSt.create)
    await edit(cb, "({48})<b>Создание трейда</b>\nНапишите, что отдаёте и что хотите получить.\n"
                   "Например: «Китсуне на Дракон».", kb([btn("({63}) Назад", "menu_trade")]))


@dp.message(TradeSt.create, F.text, ~F.text.startswith("/"))
async def trade_create_msg(msg: Message, state: FSMContext):
    text = msg.text.strip()[:500]
    app_id = await create_application("trade", msg.from_user.id, {"text": text})
    await state.clear()
    if not app_id:
        await reply(msg, NO_MAIN)
        return
    await reply(msg, f"{e(20)}Трейд опубликован в теме «{link('Трейды', LINKS['trades'])}».", main_menu())


@dp.callback_query(F.data == "trade_find")
async def trade_find(cb: CallbackQuery, state: FSMContext):
    await state.set_state(TradeSt.find)
    await edit(cb, "({39})<b>Поиск трейда</b>\n<blockquote>Назовите фрукт/геймпас/скин, который вы ищете.\n"
                   "Например: тесто, алмаз, свет, дрожь.</blockquote>", kb([btn("({63}) Назад", "menu_trade")]))


async def trade_card(row) -> tuple[str, InlineKeyboardMarkup | None]:
    p = json_payload(row["payload"])
    known = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", row["user_id"])
    text = (f"{e(48)} <b>Трейд {num(row['id'])}</b>\n{e(44)} Автор: "
            f"{mention(row['user_id'], known and known['username'], known and known['full_name'])}\n{esc(p.get('text'))}")
    url = msg_url(int(await get_config('hublox_id') or 0), row["chat_message_id"])
    return text, kb([btn("({26}) Перейти к сообщению", url=url)]) if url else None


@dp.message(TradeSt.find, F.text, ~F.text.startswith("/"))
async def trade_find_msg(msg: Message, state: FSMContext):
    query = msg.text.strip()[:60]
    rows = await pool().fetch(
        "SELECT * FROM applications WHERE kind='trade' AND status<>'closed' AND payload->>'text' ILIKE $1 "
        "ORDER BY id DESC LIMIT 5", f"%{query}%")
    await state.clear()
    if not rows:
        await reply(msg, "({39}) <b>Найдено трейдов:</b> 0", back_only())
        return
    await reply(msg, f"({{39}}) <b>Найдено трейдов:</b> {len(rows)}\n{SEP}")
    for row in rows:
        text, markup = await trade_card(row)
        await reply(msg, text, markup)
    await say(msg, "({48})Готово.", kb([BACK()]))


@dp.callback_query(F.data == "trade_active")
async def trade_active(cb: CallbackQuery):
    rows = await pool().fetch(
        "SELECT * FROM applications WHERE kind='trade' AND status<>'closed' ORDER BY id DESC LIMIT 5")
    if not rows:
        await edit(cb, "({62})<b>Активные трейды</b>\nСейчас нет активных трейдов.", kb([btn("({63}) Назад", "menu_trade")]))
        return
    await edit(cb, f"({{62}})<b>Активные трейды:</b> {len(rows)}", kb([btn("({63}) Назад", "menu_trade")]))
    for row in rows:
        text, markup = await trade_card(row)
        await say(cb, text, markup)


# ------------------- ПОИСК РЕЙДОВ / ИВЕНТОВ / ТРИАЛОВ -------------------
def result_markup(app, url: str | None) -> InlineKeyboardMarkup:
    rows = []
    if url:
        rows.append([btn("({26}) Перейти к сообщению", url=url)])
    h = help_markup(app)
    if h:
        rows += h.inline_keyboard
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_found(cb: CallbackQuery, title: str, rows, back_cb: str) -> None:
    back = kb([btn("({63}) Назад", back_cb)])
    if not rows:
        await edit(cb, f"{title}\n({{14}}) Подходящих заявок не найдено.", back)
        return
    await edit(cb, f"{title}\nНайдено заявок: <b>{len(rows)}</b>", back)
    chat_id = await main_chat() or 0
    for app in rows:
        await say(cb, await app_text(app), result_markup(app, msg_url(chat_id, app["chat_message_id"])))


@dp.callback_query(F.data == "raid_find")
async def raid_find(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    icons = await fruit_icons()
    buttons = [btn(name, f"rfind_{key}", icon_id=icons.get(key)) for key, (name, _) in RAID_FRUITS.items()]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([btn("({63}) Назад", "menu_raid")])
    await edit(cb, "({39})<b>Поиск рейда</b>\nВыберите фрукт:", InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("rfind_"))
async def raid_find_result(cb: CallbackQuery):
    key = cb.data.removeprefix("rfind_")
    if key not in RAID_FRUITS:
        await cb.answer("Неизвестный фрукт", show_alert=True)
        return
    rows = await pool().fetch(
        "SELECT * FROM applications WHERE kind='raid' AND status<>'closed' AND payload->>'fruit'=$1 "
        "AND user_id<>$2 ORDER BY id DESC LIMIT 5", key, cb.from_user.id)
    await show_found(cb, f"({{39}})<b>Рейды: {esc(RAID_FRUITS[key][0])}</b>", rows, "raid_find")


@dp.callback_query(F.data == "sea_find")
async def sea_find(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = []
    for key, (name, emoji_n) in SEA_EVENTS.items():
        label = f"({{{emoji_n}}}) {name}" if emoji_n else f"••• {name}"
        rows.append([btn(label, f"sfind_{key}")])
    rows.append([btn("({63}) Назад", "menu_sea")])
    await edit(cb, "({39})<b>Поиск морского ивента</b>\nКакой ивент ищете?", InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("sfind_"))
async def sea_find_result(cb: CallbackQuery):
    key = cb.data.removeprefix("sfind_")
    if key not in SEA_EVENTS:
        await cb.answer("Неизвестный ивент", show_alert=True)
        return
    rows = await pool().fetch(
        "SELECT * FROM applications WHERE kind='sea' AND status<>'closed' AND payload->>'event'=$1 "
        "AND user_id<>$2 ORDER BY id DESC LIMIT 5", key, cb.from_user.id)
    await show_found(cb, f"({{39}})<b>Ивенты: {esc(SEA_EVENTS[key][0])}</b>", rows, "sea_find")


@dp.callback_query(F.data == "trial_find")
async def trial_find(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    icons = await race_icons()
    buttons = [btn(name, f"tfind_{key}", icon_id=icons.get(key)) for key, name in RACES]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([btn("({63}) Назад", "menu_trial")])
    await edit(cb, "({39})<b>Поиск триала</b>\nУкажите вашу расу:", InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("tfind_"))
async def trial_find_result(cb: CallbackQuery):
    key = cb.data.removeprefix("tfind_")
    names = dict(RACES)
    if key not in names:
        await cb.answer("Неизвестная раса", show_alert=True)
        return
    rows = await pool().fetch(
        "SELECT * FROM applications WHERE kind='trial' AND status='active' AND payload->>'race'=$1 "
        "AND user_id<>$2 ORDER BY id DESC LIMIT 5", key, cb.from_user.id)
    await show_found(cb, f"({{39}})<b>Свободные триалы: {esc(names[key])}</b>", rows, "trial_find")


# ----------------------- ПОМОЩЬ ПО ЗАЯВКАМ -----------------------
async def delete_later(message: Message, delay: int = 20) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


@dp.callback_query(F.data.startswith("apph_"))
async def app_help(cb: CallbackQuery):
    app_id = int(cb.data.split("_")[1])
    app = await pool().fetchrow("SELECT * FROM applications WHERE id=$1", app_id)
    uid = cb.from_user.id
    if not app or app["status"] == "closed":
        await cb.answer("Заявка уже завершена.", show_alert=True)
        return
    if app["user_id"] == uid:
        await cb.answer("Нельзя откликнуться на свою заявку.", show_alert=True)
        return
    if uid in json_payload(app["payload"]).get("helpers", []):
        await cb.answer("Вы уже откликнулись на эту заявку.", show_alert=True)
        return
    await cb.message.reply(
        R("Вы уверены, что хотите помочь с этой заявкой" + e(46)),
        reply_markup=kb([btn("({20}) Подтвердить", f"apphc_{app_id}_{uid}"), btn("({14}) Отмена", f"apphx_{uid}")]))
    await cb.answer()


@dp.callback_query(F.data.startswith("apphx_"))
async def app_help_cancel(cb: CallbackQuery):
    if cb.from_user.id != int(cb.data.split("_")[1]):
        await cb.answer("Эта кнопка не для вас.", show_alert=True)
        return
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer("Отменено")


@dp.callback_query(F.data.startswith("apphc_"))
async def app_help_confirm(cb: CallbackQuery):
    _, app_id, uid = cb.data.split("_")
    app_id, uid = int(app_id), int(uid)
    if cb.from_user.id != uid:
        await cb.answer("Эта кнопка не для вас.", show_alert=True)
        return
    async with lock_for("app", app_id):
        app = await pool().fetchrow("SELECT * FROM applications WHERE id=$1", app_id)
        if not app or app["status"] == "closed":
            await cb.answer("Заявка уже завершена.", show_alert=True)
            return
        payload = json_payload(app["payload"])
        helpers = payload.get("helpers", [])
        if uid in helpers or app["user_id"] == uid:
            await cb.answer("Вы уже откликнулись.", show_alert=True)
            return
        helpers.append(uid)
        payload["helpers"] = helpers
        await pool().execute(
            "UPDATE applications SET payload=$2::jsonb, status='taken', claimed_by=COALESCE(claimed_by,$3), "
            "claimed_at=COALESCE(claimed_at,$4) WHERE id=$1", app_id, json.dumps(payload), uid, now_ts())
    app = await pool().fetchrow("SELECT * FROM applications WHERE id=$1", app_id)
    try:
        await cb.message.edit_text(R(f"{e(20)} {mention(uid, cb.from_user.username, cb.from_user.full_name)}, вы взяли заявку {num(app_id)}."), reply_markup=None)
        asyncio.create_task(delete_later(cb.message))
    except Exception:
        pass
    await refresh_application_post(app_id)
    urow = await user_row(uid)
    helper = mention(uid, cb.from_user.username, cb.from_user.full_name)
    await dm(app["user_id"], (
        f"{e(19)}На вашу заявку {num(app_id)} откликнулся {helper}.\n"
        f"Roblox: {esc((urow and urow['roblox_username']) or '—')}\n"
        f"<blockquote>Роль/ивент: {esc(app_title(app, payload))}</blockquote>"))
    await cb.answer("Заявка взята")


@dp.callback_query(F.data == "menu_apps")
async def menu_apps(cb: CallbackQuery):
    rows = await pool().fetch(
        "SELECT * FROM applications WHERE user_id=$1 AND status<>'closed' ORDER BY id DESC LIMIT 15", cb.from_user.id)
    if not rows:
        await edit(cb, "({14})У вас нет активных заявок.", back_only())
        return
    lines, buttons = [], []
    for r in rows:
        p = json_payload(r["payload"])
        helpers = p.get("helpers", [])
        if r["kind"] == "sea":
            emoji_n = SEA_EVENTS.get(p.get("event"), ("", 49))[1] or 49
            label = f"{p.get('event_name')} {num(r['id'])}"
        else:
            emoji_n = KIND_EMOJI[r["kind"]]
            label = f"{KIND_TITLE[r['kind']]} {num(r['id'])}"
        if helpers:
            names = []
            for h in helpers:
                k = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", h)
                names.append(mention(h, k and k["username"], k and k["full_name"]))
            lines.append(f"{e(emoji_n)} {esc(label)} — заявка взята\n" + "\n".join(names))
        else:
            lines.append(f"{e(emoji_n)} {esc(label)} — активна{e(62)}")
        buttons.append([InlineKeyboardButton(text=f"Завершить заявку {num(r['id'])}", callback_data=f"appf_{r['id']}")])
    buttons.append([BACK()])
    await edit(cb, f"({{73}})<b>Ваши активные заявки</b>\n<blockquote>" + "\n".join(lines) + "</blockquote>",
               InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("appf_"))
async def app_finish(cb: CallbackQuery):
    app_id = int(cb.data.split("_")[1])
    app = await pool().fetchrow("SELECT * FROM applications WHERE id=$1", app_id)
    if not app or app["user_id"] != cb.from_user.id:
        await cb.answer("Это не ваша заявка.", show_alert=True)
        return
    await pool().execute("UPDATE applications SET status='closed' WHERE id=$1", app_id)
    app = await pool().fetchrow("SELECT * FROM applications WHERE id=$1", app_id)
    await refresh_application_post(app_id)
    await cb.answer(f"Заявка {num(app_id)} завершена")
    await menu_apps(cb)


# ========================= АКТИВНЫЕ НАРУШЕНИЯ =========================
@dp.callback_query(F.data == "menu_violations")
async def menu_violations(cb: CallbackQuery):
    uid = cb.from_user.id
    warns = await pool().fetch("SELECT * FROM warn_logs WHERE user_id=$1 AND is_active ORDER BY id", uid)
    ban = None
    if await is_banned(uid):
        ban = await pool().fetchrow("SELECT * FROM ban_logs WHERE user_id=$1 ORDER BY id DESC LIMIT 1", uid)
    if not warns and not ban:
        await edit(cb, "({20})У вас нет активных нарушений.", back_only())
        return
    lines, buttons = [], []
    bot_id = B().id
    for i, w in enumerate(warns, 1):
        lines.append(f"<b>Варн {esc(w['warn_number'])} — {i}/{MAX_WARNS}</b>\n<blockquote>{esc(w['reason'])}</blockquote>")
        url = msg_url(w["chat_id"], w["message_id"])
        if url and w["moderator_id"] != bot_id:  # у автоварна кнопки нет
            buttons.append([btn(f"({{26}}) Перейти к сообщению {w['warn_number']}", url=url)])
    if ban:
        lines.append(f"<b>Бан {esc(ban['ban_number'])}</b>\n<blockquote>{esc(ban['reason'])}</blockquote>")
        url = msg_url(ban["chat_id"], ban["message_id"])
        if url and ban["moderator_id"] != bot_id:
            buttons.append([btn(f"({{26}}) Перейти к сообщению {ban['ban_number']}", url=url)])
    buttons.append([BACK()])
    await edit(cb, "({62})<b>Ваши активные нарушения</b>\n" + "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons))


# ============================= АПЕЛЛЯЦИИ =============================
async def appealable(user_id: int) -> list[tuple[str, str, str]]:
    """[(тип, номер, подпись)] — варны не старше 24 ч и последний бан, без поданных апелляций."""
    out = []
    since = now_ts() - APPEAL_WARN_HOURS * 3600
    warns = await pool().fetch(
        """SELECT warn_number FROM warn_logs WHERE user_id=$1 AND is_active AND created_at>=$2
           AND moderator_id<>$3
           AND warn_number NOT IN (SELECT violation_number FROM appeals WHERE user_id=$1 AND violation_type='warn')
           ORDER BY id""", user_id, since, B().id)
    out += [("warn", w["warn_number"], f"({{8}}) Варн {w['warn_number']}") for w in warns]
    if await is_banned(user_id):
        ban = await pool().fetchrow(
            """SELECT ban_number FROM ban_logs WHERE user_id=$1
               AND ban_number NOT IN (SELECT violation_number FROM appeals WHERE user_id=$1 AND violation_type='ban')
               ORDER BY id DESC LIMIT 1""", user_id)
        if ban:
            out.append(("ban", ban["ban_number"], f"({{37}}) Бан {ban['ban_number']}"))
    return out


async def begin_appeal(target, state: FSMContext, user_id: int, kind: str, number: str) -> None:
    """Запускает апелляцию на конкретное наказание (если оно принадлежит пользователю и доступно)."""
    msg = target.message if isinstance(target, CallbackQuery) else target
    table, col = ("warn_logs", "warn_number") if kind == "warn" else ("ban_logs", "ban_number")
    row = await pool().fetchrow(f"SELECT user_id, created_at, moderator_id FROM {table} WHERE {col}=$1", number)
    if not row or row["user_id"] != user_id:
        await say(msg, "({15})Это наказание выдано не вам.")
        return
    if kind == "warn" and row["moderator_id"] == B().id:
        await say(msg, "({14})Апелляция на автоматический варн (автоварн) недоступна.")
        return
    if await pool().fetchval("SELECT 1 FROM appeals WHERE violation_number=$1 AND violation_type=$2", number, kind):
        await say(msg, "({8})Апелляция на это наказание уже подана.")
        return
    if kind == "warn" and now_ts() - row["created_at"] > APPEAL_WARN_HOURS * 3600:
        await say(msg, f"({{14}})Срок подачи апелляции на варн истёк ({APPEAL_WARN_HOURS} часа).")
        return
    await state.set_state(AppealSt.text)
    await state.update_data(kind=kind, number=number)
    await say(msg, "({10})<b>Напишите причину, по которой вы считаете наказание несправедливым.</b>\n<i>Отмена: /cancel</i>")


async def show_appeal_choices(target, user_id: int) -> None:
    items = await appealable(user_id)
    if not items:
        text, markup = "({14})У вас нет наказаний, которые можно обжаловать.", back_only()
    else:
        text = "({10})<b>Выберите наказание, которое хотите обжаловать.</b>"
        rows = [[btn(label, f"apsel_{kind}_{number[1:]}")] for kind, number, label in items]
        rows.append([BACK()])
        markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if isinstance(target, CallbackQuery):
        await edit(target, text, markup)
    else:
        await say(target, text, markup)


@dp.message(Command("appeal"))
async def appeal_cmd(msg: Message, state: FSMContext):
    if not await private_only(msg):
        return
    await state.clear()
    await show_appeal_choices(msg, msg.from_user.id)


@dp.callback_query(F.data == "menu_appeal")
async def menu_appeal(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_appeal_choices(cb, cb.from_user.id)


@dp.callback_query(F.data.startswith("apsel_"))
async def appeal_select(cb: CallbackQuery, state: FSMContext):
    _, kind, number = cb.data.split("_", 2)
    await cb.answer()
    await begin_appeal(cb, state, cb.from_user.id, kind, "#" + number)


@dp.message(AppealSt.text, F.text, ~F.text.startswith("/"))
async def appeal_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    kind, number = data["kind"], data["number"]
    text = msg.text.strip()[:1000]
    user = msg.from_user
    async with pool().acquire() as conn:
        async with conn.transaction():
            appeal_no = num(await next_number(conn, "appeal_counter"))
            appeal_id = await conn.fetchval(
                """INSERT INTO appeals (appeal_number, user_id, username, violation_number, violation_type, appeal_text, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""", appeal_no, user.id, user.username, number, kind, text, now_ts())
    await state.clear()
    table, col = ("warn_logs", "warn_number") if kind == "warn" else ("ban_logs", "ban_number")
    created = await pool().fetchval(f"SELECT created_at FROM {table} WHERE {col}=$1", number)
    title = "Варн" if kind == "warn" else "Бан"
    who = mention(user.id, user.username, user.full_name)
    card = (f"{E('40.2.36.35.41.41.32.42.43.32.40')}\n<blockquote>{e(44)}Пользователь {who}\nАпелляция {appeal_no}\n{SEP}\n"
            f"{e(10)}Наказание: {title} {number}\n{e(11)} время выдачи {'варна' if kind == 'warn' else 'бана'} {fmt_dt(created)}\n"
            f"ID {user.id}\n{SEP}\n{e(25)}Комментарий\n«{esc(text)}»</blockquote>")
    await to_admin_chat("appeals", card, kb([btn("({20}) Одобрить", f"apd_y_{appeal_id}"), btn("({14}) Отклонить", f"apd_n_{appeal_id}")]))
    await reply(msg, f"{e(17)}<b>Апелляция {appeal_no} отправлена администрации.</b>\n{e(9)}Ожидайте решения.", main_menu())


@dp.callback_query(F.data.startswith("apd_"))
async def appeal_decide(cb: CallbackQuery):
    if not await can_use(cb.from_user.id, "appeals", 2):
        await cb.answer("⛔ У вас нет права рассматривать апелляции.", show_alert=True)
        return
    _, verdict, appeal_id = cb.data.split("_")
    async with lock_for("appeal", int(appeal_id)):
        ap = await pool().fetchrow("SELECT * FROM appeals WHERE id=$1", int(appeal_id))
        if not ap or ap["status"] != "pending":
            await cb.answer("Апелляция уже рассмотрена.", show_alert=True)
            return
        if ap["user_id"] == cb.from_user.id:  # защита: свою апелляцию рассматривать нельзя
            await cb.answer("⛔ Нельзя рассматривать собственную апелляцию. Её рассмотрит другой админ.", show_alert=True)
            return
        approved = verdict == "y"
        await pool().execute("UPDATE appeals SET status=$2 WHERE id=$1", ap["id"], "approved" if approved else "rejected")
    uid = ap["user_id"]
    if approved:
        if ap["violation_type"] == "warn":
            res = await pool().execute("UPDATE warn_logs SET is_active=FALSE WHERE warn_number=$1 AND is_active", ap["violation_number"])
            if res.endswith("1"):
                left = await pool().fetchval("UPDATE users SET warns=GREATEST(warns-1,0) WHERE user_id=$1 RETURNING warns", uid)
                if left is not None and left < 2 and not await is_banned(uid):
                    await unmute_everywhere(uid)
        else:
            await pool().execute("UPDATE users SET banned=FALSE, ban_until=NULL, warns=0 WHERE user_id=$1", uid)
            await pool().execute("UPDATE warn_logs SET is_active=FALSE WHERE user_id=$1 AND is_active", uid)
            for chat_id in await target_chats():
                try:
                    await B().unban_chat_member(chat_id, uid, only_if_banned=True)
                except Exception:
                    pass
            await unmute_everywhere(uid)
    mod = mention(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    verdict_text = f"{e(20)} <b>Одобрено</b> — {mod}" if approved else f"{e(14)} <b>Отклонено</b> — {mod}"
    try:
        await cb.message.edit_text(cb.message.html_text + "\n\n" + verdict_text, reply_markup=None)
    except Exception:
        pass
    await dm(uid, (f"{e(20)}Ваша апелляция {ap['appeal_number']} одобрена. Наказание {ap['violation_number']} снято." if approved
                   else f"{e(14)}Ваша апелляция {ap['appeal_number']} отклонена."))
    await cb.answer("Готово")


# ================================ РЕПОРТ ================================
@dp.message(Command("report"))
async def report_cmd(msg: Message):
    if not msg.from_user or msg.chat.type not in ("group", "supergroup"):
        await reply(msg, "({8})Команда работает только в группе.")
        return
    target = msg.reply_to_message
    if not target or not target.from_user:
        await reply(msg, "({8})Команда /report работает только ответом на сообщение нарушителя.")
        return
    if target.from_user.is_bot:
        await reply(msg, "({14})Нельзя отправить репорт на сообщение бота.")
        return
    if target.from_user.id == msg.from_user.id:
        await reply(msg, "({14})Нельзя отправить репорт на своё сообщение.")
        return
    if await pool().fetchval("SELECT 1 FROM reports WHERE chat_id=$1 AND message_id=$2", msg.chat.id, target.message_id):
        await reply(msg, "<blockquote>Это сообщение уже отправлено на рассмотрение</blockquote>")
        return
    await remember_user(target.from_user)
    try:
        async with pool().acquire() as conn:
            async with conn.transaction():
                number = num(await next_number(conn, "report_counter"))
                await conn.execute(
                    """INSERT INTO reports (report_number, reporter_id, violator_id, chat_id, message_id, reason, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                    number, msg.from_user.id, target.from_user.id, msg.chat.id, target.message_id, "Репорт на сообщение", now_ts())
                report_id = await conn.fetchval("SELECT id FROM reports WHERE report_number=$1", number)
    except asyncpg.UniqueViolationError:
        await reply(msg, "<blockquote>Это сообщение уже отправлено на рассмотрение</blockquote>")
        return
    await reply(msg, f"{e(17)}<b>Репорт отправлен администрации.</b>\n<blockquote>Команда администраторов рассмотрит сообщение "
                     "в ближайшее время.\nПосле рассмотрения репорта будут применены меры наказания, если есть нарушение правил."
                     "</blockquote>\nСтатус: в очереди")
    excerpt = (target.text or target.caption or "[медиа без текста]")[:300]
    rep = mention(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    vio = mention(target.from_user.id, target.from_user.username, target.from_user.full_name)
    card = (f"{E('1.6.35.36.5.6.4.1')}\n<blockquote>Репорт {number}\nОт: {rep}\nНа: {vio}\n{SEP}\n«{esc(excerpt)}»</blockquote>")
    rows = []
    url = msg_url(msg.chat.id, target.message_id)
    if url:
        rows.append([btn("({26}) Перейти к сообщению", url=url)])
    rows.append([btn("({20}) Рассмотрено", f"rep_done_{report_id}")])
    await to_admin_chat("reports", card, InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("rep_done_"))
async def report_done(cb: CallbackQuery):
    if not await can_use(cb.from_user.id, "reports", 1):
        await cb.answer("⛔ У вас нет права рассматривать репорты.", show_alert=True)
        return
    rid = int(cb.data.split("_")[2])
    row = await pool().fetchrow("SELECT * FROM reports WHERE id=$1", rid)
    if not row or row["status"] != "pending":
        await cb.answer("Репорт уже рассмотрен.", show_alert=True)
        return
    await pool().execute("UPDATE reports SET status='reviewed', reviewed_by=$2 WHERE id=$1", rid, cb.from_user.id)
    mod = mention(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    try:
        await cb.message.edit_text(cb.message.html_text + f"\n\n{e(20)} <b>Рассмотрен</b> — {mod}", reply_markup=None)
    except Exception:
        pass
    await dm(row["reporter_id"], f"{e(20)}Ваш репорт {row['report_number']} рассмотрен администрацией.")
    await cb.answer("Готово")


# ============================ ВОПРОС | ОТВЕТ ============================
QUESTION_COOLDOWN = 15 * 60  # вопрос можно задавать раз в 15 минут


async def question_wait(user_id: int) -> int:
    """Сколько секунд осталось до следующего вопроса (0 — можно)."""
    if user_id == CREATOR_ID:
        return 0
    last = await pool().fetchval("SELECT MAX(created_at) FROM questions WHERE user_id=$1", user_id)
    return max(0, int(last) + QUESTION_COOLDOWN - now_ts()) if last else 0


@dp.callback_query(F.data == "menu_question")
async def menu_question(cb: CallbackQuery, state: FSMContext):
    wait = await question_wait(cb.from_user.id)
    if wait:
        await cb.answer(f"⏳ Следующий вопрос можно задать через {-(-wait // 60)} мин.", show_alert=True)
        return
    await state.set_state(QuestionSt.text)
    await state.update_data(prompt_id=cb.message.message_id)  # потом уберём, чтобы в личке был порядок
    await edit(cb, "({60})<b>Вопрос | ответ</b>\nНапишите ваш вопрос одним сообщением.", back_only())


async def question_card_html(q, claimer: str | None = None, answer_html: str | None = None,
                             answered_by: str | None = None) -> str:
    k = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", q["user_id"])
    who = mention(q["user_id"], q["username"], k and k["full_name"])
    title = "Новый вопрос" if not (claimer or answer_html) else "Вопрос"
    text = (f"{e(60)}<b>{title} {q['question_number']}</b>\n{e(44)} {who}\n"
            f"{e(46)} Вопрос:\n<blockquote>«{esc(q['question_text'])}»</blockquote>")
    if answer_html:
        wrapped = answer_html if "<blockquote" in answer_html else f"<blockquote>{answer_html}</blockquote>"
        text += f"\n\n{e(20)} <b>Ответ на вопрос:</b>\n{wrapped}\n<i>Взял и ответил:</i> {answered_by}"
    elif claimer:
        text += f"\n\n🔒 <b>Взял:</b> {claimer}. Отвечает только он."
    return text


def question_markup(q):
    if q["status"] != "pending":
        return None
    if not q["claimed_by"]:
        return kb([btn("({60}) Взять вопрос", f"qans_{q['id']}")])
    return kb([btn("({24}) Написать ответ", f"qwrite_{q['id']}"), btn("({63}) Отпустить", f"qrel_{q['id']}")])


async def person_mention(uid: int) -> str:
    k = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", uid)
    return mention(uid, k and k["username"], k and k["full_name"])


async def question_refresh_card(q, **kw) -> None:
    if not q["card_chat"] or not q["card_msg"]:
        return
    try:
        await B().edit_message_text(R(await question_card_html(q, **kw)), chat_id=q["card_chat"],
                                    message_id=q["card_msg"], reply_markup=question_markup(q))
    except Exception as exc:
        if "not modified" not in str(exc).lower():
            LOG.warning("question card edit failed: %s", exc)


@dp.message(QuestionSt.text, F.text, ~F.text.startswith("/"))
async def question_text(msg: Message, state: FSMContext):
    wait = await question_wait(msg.from_user.id)
    if wait:
        await state.clear()
        await reply(msg, f"({{8}})Следующий вопрос можно задать через {-(-wait // 60)} мин.", main_menu())
        return
    data = await state.get_data()
    text = msg.text.strip()[:1000]
    user = msg.from_user
    async with pool().acquire() as conn:
        async with conn.transaction():
            qn = await next_number(conn, "question_counter")
            number = f"#{qn:05d}"
            qid = await conn.fetchval(
                "INSERT INTO questions (question_number, user_id, username, question_text, created_at) VALUES ($1,$2,$3,$4,$5) RETURNING id",
                number, user.id, user.username, text, now_ts())
    await state.clear()
    q = await pool().fetchrow("SELECT * FROM questions WHERE id=$1", qid)
    card = await to_admin_chat("questions", await question_card_html(q), question_markup(q))
    # порядок в личке: убираем приглашение и сообщение с вопросом, остаётся одна короткая отметка
    await _delete_quiet(msg)
    if data.get("prompt_id"):
        try:
            await B().delete_message(msg.chat.id, data["prompt_id"])
        except Exception:
            pass
    conf = await msg.answer(R(f"{e(17)}<b>Вопрос {number} отправлен администрации.</b>\n"
                              "Ответ придёт сюда одним сообщением."), reply_markup=main_menu())
    await pool().execute("UPDATE questions SET dm_msg=$2, card_chat=$3, card_msg=$4 WHERE id=$1", qid, conf.message_id,
                         card.chat.id if card else None, card.message_id if card else None)


async def start_answering(cb: CallbackQuery, state: FSMContext, q) -> None:
    await state.set_state(AnswerSt.text)
    hint = await cb.message.reply(R(f"({{24}})Напишите ответ на вопрос {q['question_number']} следующим сообщением. "
                                    "Я скопирую его как есть, а ваше сообщение уберу.\n<i>Отмена: /cancel</i>"))
    await state.update_data(qid=q["id"], hint_id=hint.message_id, hint_chat=hint.chat.id)


@dp.callback_query(F.data.startswith("qans_"))
async def question_take(cb: CallbackQuery, state: FSMContext):
    if not await can_use(cb.from_user.id, "questions", 2):
        await cb.answer("⛔ У вас нет права отвечать на вопросы.", show_alert=True)
        return
    qid = int(cb.data.split("_")[1])
    q = await pool().fetchrow("SELECT * FROM questions WHERE id=$1", qid)
    if not q or q["status"] != "pending":
        await cb.answer("На этот вопрос уже ответили.", show_alert=True)
        return
    res = await pool().execute("UPDATE questions SET claimed_by=$2, claimed_at=$3 "
                               "WHERE id=$1 AND status='pending' AND claimed_by IS NULL", qid, cb.from_user.id, now_ts())
    q = await pool().fetchrow("SELECT * FROM questions WHERE id=$1", qid)
    if q["claimed_by"] != cb.from_user.id:  # взял другой — перебить нельзя
        k = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", q["claimed_by"])
        who = (k and (k["full_name"] or (k["username"] and f"@{k['username']}"))) or str(q["claimed_by"])
        await cb.answer(f"Этот вопрос уже взял(а) {who}. Перебить нельзя.", show_alert=True)
        return
    await question_refresh_card(q, claimer=await person_mention(cb.from_user.id))
    await cb.answer("Вы взяли вопрос.")
    await start_answering(cb, state, q)


@dp.callback_query(F.data.startswith("qwrite_"))
async def question_write(cb: CallbackQuery, state: FSMContext):
    q = await pool().fetchrow("SELECT * FROM questions WHERE id=$1", int(cb.data.split("_")[1]))
    if not q or q["status"] != "pending":
        await cb.answer("На этот вопрос уже ответили.", show_alert=True)
        return
    if q["claimed_by"] != cb.from_user.id:
        await cb.answer("Отвечать может только админ, который взял вопрос.", show_alert=True)
        return
    await cb.answer()
    await start_answering(cb, state, q)


@dp.callback_query(F.data.startswith("qrel_"))
async def question_release(cb: CallbackQuery, state: FSMContext):
    q = await pool().fetchrow("SELECT * FROM questions WHERE id=$1", int(cb.data.split("_")[1]))
    if not q or q["status"] != "pending":
        await cb.answer("На этот вопрос уже ответили.", show_alert=True)
        return
    if cb.from_user.id not in (q["claimed_by"], CREATOR_ID):
        await cb.answer("Отпустить вопрос может только тот, кто его взял (или создатель).", show_alert=True)
        return
    was_claimer = q["claimed_by"]
    await pool().execute("UPDATE questions SET claimed_by=NULL, claimed_at=NULL WHERE id=$1", q["id"])
    q = await pool().fetchrow("SELECT * FROM questions WHERE id=$1", q["id"])
    await question_refresh_card(q)
    if cb.from_user.id == was_claimer:
        await state.clear()
    await cb.answer("Вопрос свободен.")


@dp.message(AnswerSt.text, F.text, ~F.text.startswith("/"))
async def question_answer_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    q = await pool().fetchrow("SELECT * FROM questions WHERE id=$1", data["qid"])
    if not q or q["status"] != "pending":
        await state.clear()
        await _delete_quiet(msg)
        sent = await msg.answer(R("({8})На этот вопрос уже ответили."), **thread_kwargs(msg))
        spawn(_cleanup_later(8, sent))
        return
    if q["claimed_by"] != msg.from_user.id:  # защита: ответ принимается только от того, кто взял
        await state.clear()
        await _delete_quiet(msg)
        sent = await msg.answer(R("({8})Этот вопрос взял другой админ — отвечать может только он."), **thread_kwargs(msg))
        spawn(_cleanup_later(8, sent))
        return
    if len(msg.text) > 1500:
        await reply(msg, "({8})Ответ слишком длинный (максимум 1500 символов). Сократите и отправьте снова.")
        return
    await state.clear()
    answer_html = msg.html_text.strip()  # как написал админ: Premium Emoji, цитаты, ссылки
    await pool().execute("UPDATE questions SET status='answered', answered_by=$2, answer_text=$3 WHERE id=$1",
                         q["id"], msg.from_user.id, answer_html)
    q = await pool().fetchrow("SELECT * FROM questions WHERE id=$1", q["id"])
    mod = mention(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    # в админ-чате ответ перенесён в карточку вопроса, а сообщение админа и подсказка убраны
    await _delete_quiet(msg)
    if data.get("hint_id"):
        try:
            await B().delete_message(data["hint_chat"], data["hint_id"])
        except Exception:
            pass
    await question_refresh_card(q, answer_html=answer_html, answered_by=mod)
    # в личке: убираем отметку «вопрос отправлен», приходит один аккуратный ответ
    if q["dm_msg"]:
        try:
            await B().delete_message(q["user_id"], q["dm_msg"])
        except Exception:
            pass
    wrapped = answer_html if "<blockquote" in answer_html else f"<blockquote>{answer_html}</blockquote>"
    sent = await dm(q["user_id"], f"{e(60)}<b>Ответ на ваш вопрос {q['question_number']}</b>\n"
                                  f"<blockquote>«{esc(q['question_text'])}»</blockquote>\n"
                                  f"<b>Ответ на вопрос:</b>\n{wrapped}\n<i>Ответил(а): {esc(msg.from_user.full_name)}</i>",
                    main_menu())
    if not sent:
        warn = await msg.answer(R("({8})Ответ записан в карточке, но отправить его пользователю не удалось: он не запускал бота."),
                                **thread_kwargs(msg))
        spawn(_cleanup_later(20, warn))


# ============================ PREMIUM EMOJI ============================
def custom_emoji_id_of(msg: Message) -> str | None:
    for ent in (msg.entities or []):
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            return ent.custom_emoji_id
    return None


def emoji_center_markup() -> InlineKeyboardMarkup:
    return kb(
        [InlineKeyboardButton(text="🍎 Эмодзи фруктов", callback_data="em_fruits")],
        [InlineKeyboardButton(text="🧲 Эмодзи Magnet (только он)", callback_data="em_magnet")],
        [InlineKeyboardButton(text="🧬 Эмодзи рас триалов", callback_data="em_races")],
        [InlineKeyboardButton(text="📋 Установленные эмодзи", callback_data="em_list")],
        [InlineKeyboardButton(text="🗑 Сбросить эмодзи фруктов", callback_data="em_reset")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="em_close")],
    )


EMOJI_CENTER_TEXT = "🎨 <b>Центр Premium Emoji DuoSup</b>\nВыберите раздел:"


@dp.message(Command("addemoji"))
async def addemoji_cmd(msg: Message, state: FSMContext):
    if not await redact_zone(msg):
        return
    await state.clear()
    await msg.answer(EMOJI_CENTER_TEXT, reply_markup=emoji_center_markup())


def creator_cb(cb: CallbackQuery) -> bool:
    return cb.from_user.id == CREATOR_ID


@dp.callback_query(F.data == "em_close")
async def em_close(cb: CallbackQuery, state: FSMContext):
    if not creator_cb(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    await state.clear()
    if cb.message.chat.type == "private":
        await edit(cb, MAIN_TEXT, main_menu())
    else:
        await cb.message.delete()


@dp.callback_query(F.data.in_({"em_fruits", "em_races"}))
async def em_start(cb: CallbackQuery, state: FSMContext):
    if not creator_cb(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    fruits = cb.data == "em_fruits"
    await state.set_state(EmojiSt.fruit if fruits else EmojiSt.race)
    await state.update_data(idx=0)
    await cb.message.edit_text(emoji_prompt(fruits, 0))
    await cb.answer()


@dp.callback_query(F.data == "em_magnet")
async def em_magnet(cb: CallbackQuery, state: FSMContext):
    if not creator_cb(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    idx = next(i for i, (k, _) in enumerate(FRUITS) if k == "magnet")
    await state.set_state(EmojiSt.fruit)
    await state.update_data(idx=idx, only=True)
    await cb.message.edit_text(emoji_prompt(True, idx))
    await cb.answer()


def emoji_prompt(fruits: bool, idx: int) -> str:
    items = FRUITS if fruits else RACES
    key, name = items[idx]
    head = "🍎 <b>Настройка Premium Emoji фруктов</b>" if fruits else "🧬 <b>Настройка Premium Emoji рас</b>"
    src = "\nОтправьте одним сообщением <b>Premium Emoji</b> из набора BloxFruitEmodge." if fruits else \
        "\nОтправьте одним сообщением <b>Premium Emoji</b> — он будет на кнопке расы и в заявках."
    return (f"{head}\n{SEP}\nЭмодзи <b>{idx + 1}/{len(items)}</b>\n{'Фрукт' if fruits else 'Раса'}: <b>{esc(name)}</b>{src}\n"
            "Пропустить: отправьте <code>-</code>\nДля отмены: /cancel")


async def emoji_save(msg: Message, state: FSMContext, fruits: bool) -> None:
    if msg.from_user.id != CREATOR_ID:
        return
    items = FRUITS if fruits else RACES
    data = await state.get_data()
    idx = data.get("idx", 0)
    only = bool(data.get("only"))
    key, name = items[idx]
    if (msg.text or "").strip() != "-":
        emoji_id = custom_emoji_id_of(msg)
        if not emoji_id:
            await reply(msg, "({8})Это не Premium Emoji. Отправьте именно премиум-эмодзи или <code>-</code> чтобы пропустить.")
            return
        await set_config(f"custom_emoji_{'fruit' if fruits else 'race'}_{key}", emoji_id)
        await refresh_icon_cache()
    if only:  # режим «только один фрукт» (Magnet)
        await state.clear()
        await reply(msg, f"({{20}})Premium Emoji для <b>{esc(name)}</b> сохранён.", emoji_center_markup())
        return
    idx += 1
    if idx >= len(items):
        await state.clear()
        await reply(msg, f"({{20}})Все {len(items)} Premium Emoji {'фруктов' if fruits else 'рас'} сохранены.", emoji_center_markup())
        return
    await state.update_data(idx=idx)
    await msg.answer(emoji_prompt(fruits, idx))


@dp.message(EmojiSt.fruit, F.text)
async def em_fruit_msg(msg: Message, state: FSMContext):
    if (msg.text or "").startswith("/") and msg.text.strip() != "-":
        return
    await emoji_save(msg, state, True)


@dp.message(EmojiSt.race, F.text)
async def em_race_msg(msg: Message, state: FSMContext):
    if (msg.text or "").startswith("/") and msg.text.strip() != "-":
        return
    await emoji_save(msg, state, False)


@dp.callback_query(F.data == "em_list")
async def em_list(cb: CallbackQuery):
    if not creator_cb(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    f_icons, r_icons = await fruit_icons(), await race_icons()
    lines = ["📋 <b>Установленные Premium Emoji</b>", SEP, "<b>🍎 Фрукты:</b>"]
    lines += [f"{custom_emoji_html(f_icons[k], '🍎')} {esc(n)}" for k, n in FRUITS if k in f_icons] or ["— пока нет"]
    lines.append(f"Установлено: <b>{sum(1 for k, _ in FRUITS if k in f_icons)}/{len(FRUITS)}</b>")
    lines.append("\n<b>🧬 Расы:</b>")
    for k, n in RACES:
        lines.append(f"{custom_emoji_html(r_icons.get(k), '▫️')} {esc(n)}")
    await cb.message.edit_text("\n".join(lines), reply_markup=kb([InlineKeyboardButton(text="⬅️ Назад", callback_data="em_back")]))
    await cb.answer()


@dp.callback_query(F.data == "em_back")
async def em_back(cb: CallbackQuery):
    if not creator_cb(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    await cb.message.edit_text(EMOJI_CENTER_TEXT, reply_markup=emoji_center_markup())
    await cb.answer()


@dp.callback_query(F.data == "em_reset")
async def em_reset(cb: CallbackQuery):
    if not creator_cb(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    await pool().execute("DELETE FROM config WHERE key LIKE 'custom_emoji_fruit_%'")
    await refresh_icon_cache()
    await cb.answer("Эмодзи фруктов сброшены", show_alert=True)


# ============================== НАГРАДЫ ==============================
MAX_AWARDS = 20


@dp.message(F.text.regexp(r"(?i)^\s*наградить(?:\s|$)"))
async def award_cmd(msg: Message):
    """Ответом на сообщение: «Наградить <название>» — награда появляется в профиле."""
    if not msg.from_user or not await can_use(msg.from_user.id, "award", 1):
        return  # обычные участники пишут это в разговоре — не реагируем
    if not await mod_group(msg):
        return
    award = re.sub(r"(?i)^\s*наградить\s*", "", msg.text or "").strip()
    target_msg = msg.reply_to_message
    if not target_msg or not target_msg.from_user or not award:
        await reply(msg, "({8})<b>Ошибка выдачи награды</b>\n<blockquote>Ответьте на сообщение участника и напишите:\n"
                         "<i>Наградить &lt;название награды&gt;</i></blockquote>")
        return
    target = target_msg.from_user
    if target.is_bot:
        await reply(msg, "({14})Нельзя наградить бота.")
        return
    if target.id == msg.from_user.id:
        await reply(msg, "({14})Нельзя наградить самого себя.")
        return
    if len(award) > 40:
        await reply(msg, "({8})Название награды — не длиннее 40 символов.")
        return
    await remember_user(target)
    async with lock_for("award", target.id):
        row = await user_row(target.id)
        current = [x.strip() for x in ((row and row["achievements"]) or "").split("\n") if x.strip()]
        if any(x.lower() == award.lower() for x in current):
            await reply(msg, "({8})У участника уже есть такая награда.")
            return
        if len(current) >= MAX_AWARDS:
            await reply(msg, f"({{8}})У участника уже максимум наград ({MAX_AWARDS}).")
            return
        current.append(award)
        await pool().execute("UPDATE users SET achievements=$2 WHERE user_id=$1", target.id, "\n".join(current))
    await reply(msg, f"{e(72)} {mention(target.id, target.username, target.full_name)} получает награду: "
                     f"<b>«{esc(award)}»</b>")


# =================== ПРИВАТНЫЙ ТЕКСТ БЕЗ СОСТОЯНИЯ ===================
@dp.message(StateFilter(None), F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def private_text(msg: Message):
    row = await user_row(msg.from_user.id)
    if row and row["roblox_prompt_pending"]:
        if await save_roblox(msg):
            await reply(msg, f"({{20}})Ник Roblox сохранён: <b>{esc(msg.text.strip())}</b>", main_menu())
        return
    await say(msg, MAIN_TEXT, reply_menu(1))


# ================================ СТОК ================================
import aiohttp

# Источник данных (Railway Variables). Без STOCK_API_URL автосток выключен, остаётся ручная /stock.
STOCK_API_URL = os.getenv("STOCK_API_URL", "").strip()
STOCK_API_KEY = os.getenv("STOCK_API_KEY", "").strip()


def _load_stock_accounts() -> list[dict]:
    """Аккаунт 1 = STOCK_API_URL/KEY, запасные = STOCK_API_URL_2/KEY_2 … STOCK_API_URL_5/KEY_5."""
    found = []
    for n in range(1, 6):
        suffix = "" if n == 1 else f"_{n}"
        url = os.getenv(f"STOCK_API_URL{suffix}", "").strip()
        if url:
            found.append({"n": n, "url": url, "key": os.getenv(f"STOCK_API_KEY{suffix}", "").strip()})
    return found


STOCK_ACCOUNTS = _load_stock_accounts()
STOCK_API_KEY_HEADER = os.getenv("STOCK_API_KEY_HEADER", "X-API-Key").strip() or "X-API-Key"
STOCK_POLL_SECONDS = max(60, env_int("STOCK_POLL_SECONDS", 14400))  # запасной интервал, если источник не отдаёт время смены
STOCK_MONTHLY_LIMIT = env_int("STOCK_MONTHLY_LIMIT", 190)  # лимит запросов НА КАЖДЫЙ аккаунт (у бесплатного плана Parse их 200)
STOCK_FULL_MODE = os.getenv("STOCK_FULL_MODE", "").strip().lower() in ("1", "true", "yes")  # проверять каждые 2 часа, пока хватает лимита
STOCK_DELAY_SECONDS = max(0, env_int("STOCK_DELAY_SECONDS", 120))    # сколько ждать после смены стока до проверки (если источник обновляется с задержкой)
STOCK_RETRY_SECONDS = max(60, env_int("STOCK_RETRY_SECONDS", 300))  # повтор, если после смены данные ещё старые
STOCK_RETRY_TRIES = max(1, env_int("STOCK_RETRY_TRIES", 3))         # сколько раз повторять (каждый повтор = 1 кредит)
STOCK_MIN_ITEMS = 3  # меньше фруктов — считаем ответ источника сбойным и ничего не публикуем
STOCK_NEXT_HOURS = {"normal": 4, "mirage": 2}
_stock_task = None

# Цены в Beli. Если источник отдаёт свою цену — берётся она. Таблицу можно править.
PRICES = {
    "rocket": 5000, "spin": 7500, "blade": 30000, "spring": 60000, "bomb": 80000, "smoke": 100000,
    "spike": 180000, "flame": 250000, "ice": 350000, "sand": 420000, "dark": 500000, "eagle": 550000,
    "diamond": 600000, "light": 650000, "rubber": 750000, "ghost": 940000, "magma": 960000,
    "quake": 1000000, "buddha": 1200000, "love": 1300000, "creation": 1400000, "spider": 1500000,
    "sound": 1700000, "phoenix": 1800000, "portal": 1900000, "lightning": 2100000, "pain": 2300000,
    "blizzard": 2400000, "gravity": 2500000, "mammoth": 2700000, "trex": 2700000, "dough": 2800000,
    "shadow": 2900000, "venom": 3000000, "control": 3200000, "gas": 3200000, "spirit": 3400000,
    "tiger": 5000000, "yeti": 5000000, "kitsune": 8000000, "dragon": 15000000,
}


def _norm(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


FRUIT_BY_NAME: dict[str, str] = {_norm(name): key for key, name in FRUITS}
FRUIT_BY_NAME.update({_norm(key): key for key, _ in FRUITS})
FRUIT_BY_NAME.update({"leopard": "tiger", "trex": "trex", "tyrannosaurus": "trex"})

NAME_KEYS = ("name", "fruit", "fruitName", "fruit_name", "title", "displayName")
PRICE_KEYS = ("money_price", "price", "beli", "cost", "money", "priceBeli", "price_beli")


def _lookup(name) -> str | None:
    n = _norm(name)
    key = FRUIT_BY_NAME.get(n) or FRUIT_BY_NAME.get(n.removesuffix("fruit"))
    if key:
        return key
    first = re.split(r"[-\s]+", str(name).strip())[0]  # «Kitsune-Kitsune Fruit» -> «Kitsune»
    return FRUIT_BY_NAME.get(_norm(first))


def _to_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value)
        return int(digits) if digits else None
    return None


def _parse_item(item, fallback_name=None):
    name, price = fallback_name, None
    if isinstance(item, str):
        name = item
    elif isinstance(item, dict):
        for k in NAME_KEYS:
            if isinstance(item.get(k), str):
                name = item[k]
                break
        for k in PRICE_KEYS:
            v = item.get(k)
            if isinstance(v, dict):
                v = v.get("beli") or v.get("Beli") or v.get("price")
            price = _to_int(v)
            if price is not None:
                break
    elif fallback_name is not None:
        price = _to_int(item)
    key = _lookup(name) if name else None
    return (key, price) if key else None


def _items(value) -> list:
    out: list = []
    if isinstance(value, list):
        out = [x for x in (_parse_item(i) for i in value) if x]
    elif isinstance(value, dict):
        for inner in ("fruits", "items", "stock", "list", "data"):
            if isinstance(value.get(inner), (list, dict)):
                out = _items(value[inner])
                if out:
                    return out
        out = [x for x in (_parse_item(i, fallback_name=n) for n, i in value.items()) if x]
    seen, res = set(), []
    for key, price in out:
        if key not in seen:
            seen.add(key)
            res.append((key, price))
    return res


def extract_stock(data) -> dict[str, list]:
    """Ищет в JSON источника списки обычного и миражного стока. -> {'normal': [(ключ, цена|None)], 'mirage': [...]}."""
    found: dict[str, list] = {}

    def kind_of(label):
        low = str(label).lower()
        if any(w in low for w in ("previous", "prev", "old", "last")):
            return None  # прошлый сток не берём
        if "mirage" in low or "advanced" in low:
            return "mirage"
        if "normal" in low or "regular" in low:
            return "normal"
        return None

    def walk(obj, kind=None):
        if isinstance(obj, dict):
            for k, v in obj.items():
                sub = kind_of(k) or kind
                if sub and sub not in found and isinstance(v, (list, dict)):
                    items = _items(v)
                    if items:
                        found[sub] = items
                        continue
                walk(v, sub)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, kind)

    walk(data)
    return found


def extract_resets(data) -> dict[str, int]:
    """Время следующей смены стока (unix) из ответа источника: {'normal': ..., 'mirage': ...}."""
    out: dict[str, int] = {}

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                low = str(k).lower()
                if low.endswith("resets_at_epoch") and isinstance(v, (int, float)):
                    kind = "mirage" if "mirage" in low else "normal" if "normal" in low else None
                    if kind:
                        out[kind] = int(v)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    return out


def _month_key(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc):%Y%m}"


class StockCreditsOut(Exception):
    """У текущего аккаунта Parse.bot закончились кредиты."""


class StockAllExhausted(Exception):
    """Кредиты закончились на всех аккаунтах."""


def _calls_key(acc: int) -> str:
    return _month_key("stock_calls") if acc == 1 else _month_key(f"stock_calls_a{acc}")


async def stock_current_acc() -> int:
    n = int(await get_config("stock_acc") or 1)
    return n if any(a["n"] == n for a in STOCK_ACCOUNTS) else STOCK_ACCOUNTS[0]["n"]


async def stock_calls_used(acc: int | None = None) -> int:
    if acc is None:
        acc = await stock_current_acc()
    return int(await get_config(_calls_key(acc)) or 0)


async def stock_count_call(acc: int | None = None) -> None:
    if acc is None:
        acc = await stock_current_acc()
    await set_config(_calls_key(acc), await stock_calls_used(acc) + 1)


async def _acc_usable(acc: dict) -> bool:
    if await get_config(_month_key(f"stock_dead_a{acc['n']}")):
        return False  # источник сам сказал, что кредиты кончились (до начала следующего месяца)
    return await stock_calls_used(acc["n"]) < STOCK_MONTHLY_LIMIT


async def pick_account() -> dict | None:
    """Текущий аккаунт, а если его кредиты кончились — следующий по кругу (1→2→3→4→1). None — не осталось ни одного."""
    if not STOCK_ACCOUNTS:
        return None
    async with lock_for("stock_acc"):
        order = sorted(STOCK_ACCOUNTS, key=lambda a: a["n"])
        current = await stock_current_acc()
        start = next(i for i, a in enumerate(order) if a["n"] == current)
        for step in range(len(order)):
            acc = order[(start + step) % len(order)]
            if await _acc_usable(acc):
                if acc["n"] != current:
                    await set_config("stock_acc", acc["n"])
                    await dm(CREATOR_ID, f"{e(8)} <b>Parse.bot: переход на аккаунт {acc['n']}</b>\n"
                                         f"<blockquote>На аккаунте {current} закончились кредиты. "
                                         f"Проверка стока продолжается с аккаунта {acc['n']} из {len(order)}.</blockquote>")
                return acc
        return None


def _credits_exhausted(status: int, body: str) -> bool:
    low = body.lower()
    words = ("credit", "quota", "limit", "balance", "payment", "insufficient", "exhaust")
    if status == 402:
        return True
    if status in (401, 403, 429) and any(w in low for w in words):
        return True
    return status >= 400 and ("credit" in low or "quota" in low)


async def _request_stock(acc: dict):
    headers = {STOCK_API_KEY_HEADER: acc["key"]} if acc["key"] else {}
    snapshot = os.getenv("STOCK_API_SNAPSHOT", "").strip()  # нужен только если в curl-примере API есть API-Snapshot-Version
    if snapshot:
        headers["API-Snapshot-Version"] = snapshot
    for pair in filter(None, (x.strip() for x in os.getenv("STOCK_API_EXTRA_HEADERS", "").split(","))):
        name, _, value = pair.partition(":")  # формат: Имя:значение,Имя2:значение2
        if name.strip() and value.strip():
            headers[name.strip()] = value.strip()
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(acc["url"], headers=headers) as resp:
            body = await resp.text()
            if _credits_exhausted(resp.status, body):
                raise StockCreditsOut()
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}: {body[:200]}")
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise RuntimeError(f"источник вернул не JSON: {body[:200]}") from exc
    if isinstance(data, dict) and str(data.get("status", "success")).lower() not in ("success", "ok") \
            and any(w in body.lower() for w in ("credit", "quota")):
        raise StockCreditsOut()
    return data


async def fetch_stock_json():
    if not STOCK_ACCOUNTS:
        return None
    for _ in range(len(STOCK_ACCOUNTS)):
        acc = await pick_account()
        if acc is None:
            break
        try:
            data = await _request_stock(acc)
        except StockCreditsOut:
            await set_config(_month_key(f"stock_dead_a{acc['n']}"), 1)
            LOG.warning("stock: на аккаунте %s закончились кредиты", acc["n"])
            continue  # pick_account на следующем круге переключит на другой аккаунт и напишет создателю
        await stock_count_call(acc["n"])
        return data
    raise StockAllExhausted("кредиты закончились на всех аккаунтах Parse.bot")


async def _all_exhausted() -> int:
    warn_key = _month_key("stock_budget_warned")
    if not await get_config(warn_key):
        await set_config(warn_key, 1)
        await dm(CREATOR_ID, f"{e(8)} <b>Автосток остановлен:</b> кредиты закончились на всех аккаунтах Parse.bot "
                             f"({len(STOCK_ACCOUNTS)}). Возобновится в начале следующего месяца. "
                             "Чтобы добавить аккаунт: STOCK_API_URL_N и STOCK_API_KEY_N в Railway Variables.")
    LOG.warning("stock: кредиты закончились на всех аккаунтах")
    return 6 * 3600


# ---------------------------- оформление ----------------------------
async def stock_state(kind: str) -> dict:
    import json
    raw = await get_config(f"stock_{kind}")
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def stock_footer() -> str:
    return (f"<b>{e(60)}<u>{link('Чат по Blox Fruits', LINKS['chat'])}</u> | "
            f"{e(11)} <u>{link('стоки 24/7', LINKS['stock'])}</u></b>")


async def stock_text(kind: str, state: dict, active: bool) -> str:
    icons = await fruit_icons()
    names = dict(FRUITS)
    lines = []
    for key, price in sorted(state["items"], key=lambda x: x[1]):
        price_text = f"${price:,}" if price else "—"
        lines.append(f"{custom_emoji_html(icons.get(key), '▪️')} {esc(names.get(key, key))} • {price_text}")
    body = "\n".join(lines)
    head = f"Активен {e(62)}" if active else f"Истёк {e(76)}"
    title = (f"{e(30)} Mirage Stock" if kind == "mirage" else f"{e(74)} Normal Stock") + f" ({esc(state['time'])} МСК)"
    if active:
        hours = STOCK_NEXT_HOURS[kind]
        return (f"{head}\n{title}\n<blockquote>{body}</blockquote>\n\n{stock_footer()}\n\n"
                f"{e(11)} <i>Следующее обновление через {hours} часа!</i>")
    return f"{head}\n{title}\n<blockquote>{body}</blockquote>\n{stock_footer()}"


async def load_board() -> dict:
    import json
    raw = await get_config("stock_board")
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


async def save_board(board: dict) -> None:
    import json
    await set_config("stock_board", json.dumps(board))


def _stock_block(kind: str, state: dict, active: bool, icons: dict, names: dict) -> str:
    lines = []
    for key, price in sorted(state["items"], key=lambda x: x[1]):
        price_text = f"${price:,}" if price else "—"
        lines.append(f"{custom_emoji_html(icons.get(key), '▪️')} {esc(names.get(key, key))} • {price_text}")
    head = f"Активен {e(62)}" if active else f"Истёк {e(76)}"
    title = (f"{e(30)} Mirage Stock" if kind == "mirage" else f"{e(74)} Normal Stock") + f" ({esc(state['time'])} МСК)"
    return f"{head}\n{title}\n<blockquote>" + "\n".join(lines) + "</blockquote>"


async def render_board(board: dict, closed: bool = False) -> str | None:
    """Одно сообщение периода Normal: Normal + Mirage этого периода (прошлый Mirage — «Истёк», текущий — «Активен»)."""
    icons = await fruit_icons()
    names = dict(FRUITS)
    now = now_ts()
    parts, upcoming = [], []
    normal = board.get("normal")
    if normal and normal.get("items"):
        alive = not closed and not (normal.get("epoch") and normal["epoch"] <= now)
        parts.append(_stock_block("normal", normal, alive, icons, names))
        if alive and normal.get("epoch"):
            upcoming.append(f"Normal в {datetime.fromtimestamp(normal['epoch'], MSK).strftime('%H:%M')}")
    mirages = board.get("mirages") or []
    for i, m in enumerate(mirages):
        last = i == len(mirages) - 1
        alive = not closed and last and not (m.get("epoch") and m["epoch"] <= now)
        parts.append(_stock_block("mirage", m, alive, icons, names))
        if alive and m.get("epoch"):
            upcoming.append(f"Mirage в {datetime.fromtimestamp(m['epoch'], MSK).strftime('%H:%M')}")
    if not parts:
        return None
    text = "\n\n".join(parts) + f"\n\n{stock_footer()}"
    if upcoming:
        text += f"\n\n{e(11)} <i>Следующее обновление: {' • '.join(upcoming)} МСК</i>"
    return text


async def render_stock_message() -> str | None:
    return await render_board(await load_board())


async def _send_board_message(chat_id: int, board: dict, text: str) -> None:
    sent = await B().send_message(chat_id, R(text), message_thread_id=thread(TOPICS["stock"]))
    board["msg"] = sent.message_id
    await save_board(board)


async def _edit_board_message(chat_id: int, board: dict, text: str) -> bool:
    """True — сообщение обновлено. False — его нет (удалено), нужно отправить заново."""
    try:
        await B().edit_message_text(R(text), chat_id=chat_id, message_id=board["msg"], reply_markup=None)
        return True
    except Exception as exc:
        low = str(exc).lower()
        if "not modified" in low:
            return True
        if any(w in low for w in ("not found", "can't be edited", "message_id_invalid")):
            return False
        raise  # временный сбой — новое сообщение не плодим


async def _cleanup_legacy_stock_posts(chat_id: int) -> None:
    """Убирает посты прежних форматов (отдельные сообщения, единое сообщение 3.5.x)."""
    legacy = await get_config("stock_msg")
    if legacy:
        try:
            await B().delete_message(chat_id, int(legacy))
        except Exception:
            pass
        await set_config("stock_msg", "")
    for kind in ("normal", "mirage"):
        st = await stock_state(kind)
        if st.get("msg"):
            try:
                await B().delete_message(chat_id, st["msg"])
            except Exception:
                pass
            st["msg"] = None
            await set_config(f"stock_{kind}", json.dumps(st))


async def board_update(chat_id: int, kind: str, state: dict) -> None:
    """Новый Normal -> новое сообщение (прошлое закрывается). Новый Mirage -> дописывается в текущее сообщение."""
    async with lock_for("stock_board"):
        board = await load_board()
        if kind == "normal":
            if board.get("msg"):  # прошлое сообщение: всё в нём теперь «Истёк»
                try:
                    old_text = await render_board(board, closed=True)
                    if old_text:
                        await _edit_board_message(chat_id, board, old_text)
                except Exception as exc:
                    LOG.warning("stock: не удалось закрыть прошлое сообщение: %s", exc)
            new_board = {"msg": None, "normal": state, "mirages": []}
            mir = await stock_state("mirage")  # Mirage, который уже начался в этом периоде Normal
            if mir.get("items") and mir.get("epoch") and state.get("epoch") \
                    and mir["epoch"] - STOCK_NEXT_HOURS["mirage"] * 3600 >= state["epoch"] - STOCK_NEXT_HOURS["normal"] * 3600:
                new_board["mirages"].append(mir)
            await _cleanup_legacy_stock_posts(chat_id)
            await _send_board_message(chat_id, new_board, await render_board(new_board))
            return
        if not board.get("msg"):  # сообщения ещё нет — начинаем с текущего Normal
            normal = await stock_state("normal")
            board = {"msg": None, "normal": normal if normal.get("items") else None, "mirages": [state]}
            await _cleanup_legacy_stock_posts(chat_id)
            await _send_board_message(chat_id, board, await render_board(board))
            return
        mirages = board.get("mirages") or []
        if mirages and mirages[-1].get("epoch") == state.get("epoch") and state.get("epoch"):
            mirages[-1] = state
        else:
            mirages.append(state)
        board["mirages"] = mirages[-3:]
        text = await render_board(board)
        if not await _edit_board_message(chat_id, board, text):
            await _send_board_message(chat_id, board, text)
        else:
            await save_board(board)


async def refresh_stock_message(chat_id: int | None, resend: bool = False) -> int | None:
    """Перерисовывает текущее сообщение стока (чтобы закончившийся сток стал «Истёк»); resend — отправить заново."""
    if not chat_id:
        return None
    async with lock_for("stock_board"):
        board = await load_board()
        text = await render_board(board)
        if not text:
            return None
        if board.get("msg") and not resend:
            if await _edit_board_message(chat_id, board, text):
                return board["msg"]
        elif board.get("msg"):
            try:
                await B().delete_message(chat_id, board["msg"])
            except Exception:
                pass
        await _send_board_message(chat_id, board, text)
        return board["msg"]


async def publish_stock(kind: str, items: list, force: bool = False, epoch: int | None = None) -> bool:
    """Обновляет единое сообщение стока: прошлый сток этого вида -> «Истёк 🔴», новый -> «Активен 🟢». False, если сток не изменился."""
    import json
    chat_id = await main_chat()
    if not chat_id:
        return False
    resolved = [[key, price or PRICES.get(key, 0)] for key, price in items]
    keys = sorted(k for k, _ in resolved)
    async with lock_for("stock", kind):
        old = await stock_state(kind)
        if not force:
            if epoch is not None and old.get("epoch") and epoch < old["epoch"]:
                return False  # это более старый сток, чем уже опубликованный
            if epoch is not None and old.get("epoch") is None and old.get("keys") == keys and old.get("items"):
                old["epoch"] = epoch  # тот же сток, опубликованный вручную — не дублируем
                await set_config(f"stock_{kind}", json.dumps(old))
                return False
            if epoch is not None and old.get("epoch") == epoch:
                return False
            if epoch is None and old.get("keys") == keys:
                return False
        if epoch:  # сток начался за период до следующей смены
            started = datetime.fromtimestamp(epoch - STOCK_NEXT_HOURS[kind] * 3600, MSK).strftime("%H:%M")
        else:
            started = datetime.now(MSK).strftime("%H:00")
        prev = {"items": old["items"], "time": old["time"]} if old.get("items") else None
        state = {"keys": keys, "items": resolved, "time": started, "epoch": epoch, "msg": None, "prev": prev}
        await set_config(f"stock_{kind}", json.dumps(state))
        try:
            await board_update(chat_id, kind, state)
        except Exception:
            await set_config(f"stock_{kind}", json.dumps(old))  # откат — повторим при следующей проверке
            raise
        old_dms = await take_stock_dms(kind)  # личные уведомления о прошлом стоке
    try:
        await expire_stock_dms(kind, old, old_dms)
    except Exception:
        LOG.exception("stock dm expire failed")
    try:
        await notify_stock_subscribers(kind, state)
    except Exception:
        LOG.exception("stock notify failed")
    return True


_stale = 0
_cached: tuple[int, object] | None = None
_stock_status: dict = {"last_check": None, "next_check": None, "error": None}
_err_notice: dict[str, int] = {}


async def stock_tick() -> int:
    """Одна проверка источника. Возвращает, через сколько секунд проверять снова."""
    global _stale, _cached
    now = now_ts()
    if await get_config("stock_paused") == "1":
        return 600  # остановлено командой /stopstock
    if not await main_chat():
        return 60  # чаты ещё не связаны — ничего не тратим, проверим снова через минуту
    if STOCK_ACCOUNTS and await pick_account() is None:
        return await _all_exhausted()  # кредиты кончились на всех аккаунтах
    if _cached and now - _cached[0] < 1200:  # повтор после сбоя публикации — без нового запроса
        data = _cached[1]
    else:
        try:
            data = await fetch_stock_json()
        except StockAllExhausted:
            return await _all_exhausted()
        if data is None:
            return STOCK_POLL_SECONDS
        _cached = (now, data)
    parsed = extract_stock(data)
    resets = extract_resets(data)  # источник может не отдавать время смены — тогда считаем по часам
    stale_clock = False
    stale_src = False
    for kind in ("normal", "mirage"):
        items = parsed.get(kind) or []
        if len(items) < STOCK_MIN_ITEMS:
            if items:
                LOG.warning("stock %s: слишком мало фруктов (%s) — пропускаю", kind, len(items))
            continue
        epoch = resets.get(kind)
        if epoch is not None and epoch <= now:
            # источник отдал сток, у которого время смены уже прошло, — это прошлый сток, не публикуем
            stale_src = True
            LOG.warning("stock %s: источник вернул уже закончившийся сток — пропускаю", kind)
            continue
        if epoch is None:
            period = STOCK_NEXT_HOURS[kind] * 3600
            epoch = (now // period + 1) * period  # ближайшая смена (Normal каждые 4 ч, Mirage каждые 2 ч по UTC)
            old = await stock_state(kind)
            if old.get("keys") == sorted(k for k, _ in items):
                if old.get("epoch") and old["epoch"] <= now:
                    stale_clock = True  # время смены прошло, а список прежний — сайт ещё не обновился
                continue
        if await publish_stock(kind, items, epoch=epoch):
            LOG.info("stock %s опубликован: %s", kind, ", ".join(k for k, _ in items))
    try:  # сток, у которого время смены прошло, помечается «Истёк» в едином сообщении
        await refresh_stock_message(await main_chat())
    except Exception as exc:
        LOG.warning("stock message refresh failed: %s", exc)
    if stale_src and _stale < STOCK_RETRY_TRIES:  # источник ещё не обновился — быстро проверим снова
        _stale += 1
        _cached = None
        return STOCK_RETRY_SECONDS
    anchor = await get_config("stock_anchor")
    if anchor:  # расписание задано командой /startstock: проверки каждые 2 часа от указанной минуты (МСК)
        if stale_clock and _stale < STOCK_RETRY_TRIES:
            _stale += 1
            _cached = None
            return STOCK_RETRY_SECONDS
        _stale = 0
        return max(60, next_anchor_slot(anchor, now) - now)
    economy = STOCK_MONTHLY_LIMIT * max(1, len(STOCK_ACCOUNTS)) < 360 and not STOCK_FULL_MODE
    if resets:
        boundaries = resets
    else:
        if stale_clock and _stale < STOCK_RETRY_TRIES:
            _stale += 1
            _cached = None
            return STOCK_RETRY_SECONDS
        boundaries = {k: (now // (h * 3600) + 1) * (h * 3600) for k, h in STOCK_NEXT_HOURS.items()}
    targets = [boundaries["normal"]] if economy and "normal" in boundaries else list(boundaries.values())
    future = [t for t in targets if t > now]
    if not future:  # источник ещё не обновил данные — повторим чуть позже
        _stale += 1
        _cached = None
        return STOCK_RETRY_SECONDS if _stale <= STOCK_RETRY_TRIES else 1800
    _stale = 0
    return max(120, min(future) - now + STOCK_DELAY_SECONDS)


_stock_wake = asyncio.Event()  # будит цикл, когда меняется расписание (/startstock, /stopstock)


def next_anchor_slot(anchor: str, now: int) -> int:
    """Ближайшее время проверки после now: «anchor» по МСК и далее каждые 2 часа (11:02, 13:02, 15:02 …)."""
    hour, minute = (int(x) for x in anchor.split(":"))
    base = int(datetime.fromtimestamp(now, MSK).replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp())
    return base + ((now - base) // 7200 + 1) * 7200


async def stock_idle_wait() -> int:
    """Сколько ждать до следующей проверки по текущему расписанию (без запроса к источнику)."""
    if await get_config("stock_paused") == "1":
        return 600
    anchor = await get_config("stock_anchor")
    if anchor:
        return max(60, next_anchor_slot(anchor, now_ts()) - now_ts())
    return 60


async def _sleep_or_wake(seconds: int) -> bool:
    """True, если проснулись досрочно из-за смены расписания."""
    try:
        await asyncio.wait_for(_stock_wake.wait(), timeout=max(60, seconds))
    except asyncio.TimeoutError:
        return False
    _stock_wake.clear()
    return True


def next_stock_slot(now: int | None = None) -> int:
    """Секунд до ближайшей плановой проверки: нечётные часы по МСК в :02 (01:02, 03:02, 05:02 … 23:02)."""
    now_dt = datetime.fromtimestamp(now or now_ts(), MSK)
    slot = now_dt.replace(minute=2, second=0, microsecond=0)
    if slot.hour % 2 == 0:
        slot += timedelta(hours=1)
    while slot <= now_dt:
        slot += timedelta(hours=2)
    return max(60, int((slot - now_dt).total_seconds()))


async def _notify_stock_error(text: str) -> None:
    """Сообщает создателю об ошибке автостока. Повторных попыток нет: обновить можно вручную или дождаться плановой проверки."""
    now = now_ts()
    if now - _err_notice.get(text, 0) < 3600:
        return
    _err_notice[text] = now
    nxt = datetime.fromtimestamp(now + next_stock_slot(now), MSK).strftime("%H:%M")
    await dm(CREATOR_ID, f"{e(8)} <b>Автосток: ошибка</b>\n<blockquote>{esc(text)[:600]}</blockquote>\n"
                         f"Повторных попыток не будет. Обновить сейчас: /stocknow (1 кредит). "
                         f"Если не обновите, бот сам проверит в {nxt} МСК.")


async def stock_loop() -> None:
    await asyncio.sleep(15)
    LOG.info("Автосток запущен")
    run, wait = True, 60
    while True:
        if run:
            wait = 900
            try:
                wait = await stock_tick()
                _stock_status["error"] = None
            except Exception as exc:
                text = f"{type(exc).__name__}: {exc}"
                _stock_status["error"] = text
                LOG.warning("stock tick failed: %s", text)
                await _notify_stock_error(text)
                wait = next_stock_slot()  # без повторов: ручное обновление или плановая проверка (нечётные часы МСК, :02)
            _stock_status["last_check"] = now_ts()
        _stock_status["next_check"] = now_ts() + max(60, wait)
        LOG.info("stock: следующая проверка через %s мин", max(1, wait // 60))
        if await _sleep_or_wake(wait):  # расписание изменили — пересчитываем без запроса к источнику
            wait, run = await stock_idle_wait(), False
        else:
            run = True


# ------------------------------ команды ------------------------------
@dp.message(Command("stock"))
async def stock_cmd(msg: Message):
    """Ручной сток: /stock normal rocket, spin, blade  (запасной вариант, если источник недоступен)."""
    if not await redact_zone(msg):
        return
    parts = (msg.text or "").split(maxsplit=2)
    kind = parts[1].lower() if len(parts) > 1 else ""
    if kind not in STOCK_NEXT_HOURS or len(parts) < 3:
        await reply(msg, "({8})<b>Ошибка</b>\n<blockquote>Формат:\n<i>/stock normal rocket, spin, blade</i>\n"
                         "<i>/stock mirage flame, buddha, dough</i></blockquote>")
        return
    names = [x.strip() for x in re.split(r"[,\n;]+", parts[2]) if x.strip()]
    items, unknown = [], []
    for name in names:
        key = _lookup(name)
        (items if key else unknown).append((key, None) if key else name)
    if unknown or not items:
        await reply(msg, "({8})Не распознал: <b>" + esc(", ".join(unknown) or "пусто") + "</b>\nПишите названия фруктов по-английски.")
        return
    period = STOCK_NEXT_HOURS[kind] * 3600
    await publish_stock(kind, items, force=True, epoch=(now_ts() // period + 1) * period)
    await reply(msg, f"({{20}})Сток {kind} опубликован.")


@dp.message(Command("stockpublish"))
async def stockpublish_cmd(msg: Message):
    """/stockpublish — отправить единое сообщение стока ещё раз. Время, таймер и автопроверка не меняются."""
    if not await redact_zone(msg):
        return
    chat_id = await main_chat()
    if not chat_id:
        await reply(msg, "({8})Основной чат ещё не привязан (/link_hublox).")
        return
    if not await render_stock_message():
        await reply(msg, "({8})Сток ещё не публиковался.")
        return
    states = [await stock_state(k) for k in ("normal", "mirage")]
    if all((st.get("epoch") and st["epoch"] <= now_ts()) for st in states if st.get("items")):
        await reply(msg, "({8})Сохранённый сток уже закончился, повторять нечего. "
                         "Чтобы получить и опубликовать новый, отправьте /stocknow (1 кредит). "
                         "/stockcheck только показывает данные источника и ничего не публикует.")
        return
    await refresh_stock_message(chat_id, resend=True)
    await reply(msg, "({20})Сток отправлен ещё раз одним сообщением. Таймер не менялся.")


@dp.message(Command("startstock"))
async def startstock_cmd(msg: Message):
    """/startstock 11:02 — проверять сток каждые 2 часа от указанного времени по МСК."""
    if not await redact_zone(msg):
        return
    if not STOCK_ACCOUNTS:
        await reply(msg, "({8})Источник не настроен: добавьте STOCK_API_URL и STOCK_API_KEY в Railway Variables.")
        return
    args = command_args(msg)
    m = re.fullmatch(r"([01]?\d|2[0-3])[:.]([0-5]\d)", args[0]) if args else None
    if not m:
        current = await get_config("stock_anchor")
        await reply(msg, "({8})<b>Укажите время по МСК</b>\n<blockquote>Формат: <i>/startstock 11:02</i>\n"
                         "Бот будет проверять сток каждые 2 часа начиная с этой минуты (11:02, 13:02, 15:02 …).\n"
                         "Ставьте время сразу после смены стока, например на 1–2 минуты позже.</blockquote>"
                         + (f"\nСейчас: <b>{esc(current)} МСК</b>" if current else ""))
        return
    anchor = f"{int(m.group(1)):02d}:{m.group(2)}"
    await set_config("stock_anchor", anchor)
    await set_config("stock_paused", "0")
    _stock_wake.set()
    first = next_anchor_slot(anchor, now_ts())
    slots = ", ".join(datetime.fromtimestamp(first + 7200 * i, MSK).strftime("%H:%M") for i in range(4))
    left = max(1, (first - now_ts()) // 60)
    await reply(msg, f"({{20}})<b>Автосток запущен</b>\n<blockquote>Проверки каждые 2 часа по МСК: {slots} …\n"
                     f"Первая проверка через {left} мин.\nNormal обновится на тех проверках, где он реально сменился (каждые 4 часа).</blockquote>")


@dp.message(Command("stopstock"))
async def stopstock_cmd(msg: Message):
    if not await redact_zone(msg):
        return
    await set_config("stock_paused", "1")
    _stock_wake.set()
    await reply(msg, "({20})Автосток остановлен. Запустить снова: <i>/startstock 11:02</i>")


@dp.message(Command("stocknow"))
async def stocknow_cmd(msg: Message):
    """Принудительная проверка источника и публикация, если сток сменился (тратит 1 кредит)."""
    if not await redact_zone(msg):
        return
    if not STOCK_ACCOUNTS:
        await reply(msg, "({8})Источник не настроен: добавьте STOCK_API_URL и STOCK_API_KEY в Railway Variables.")
        return
    async def snapshot() -> dict:
        out = {}
        for k in ("normal", "mirage"):
            st = await stock_state(k)
            out[k] = (st.get("keys"), st.get("epoch"), st.get("time"))
        return out

    before = await snapshot()
    try:
        wait = await stock_tick()
    except Exception as exc:
        await reply(msg, f"({{14}})Ошибка: <code>{esc(f'{type(exc).__name__}: {exc}')}</code>")
        return
    after = await snapshot()
    changed = [k for k in before if before[k] != after[k]]
    if changed:
        result = f"({{20}})Опубликован новый сток: <b>{esc(', '.join(changed))}</b> (тема «Стоки 24/7»)."
    else:
        result = ("({8})Новый сток не опубликован: источник отдал тот же сток или данные ещё не обновились "
                  "(время смены у него уже прошло). Попробуйте позже.")
    await reply(msg, f"{result}\nАвтопроверка снова через {max(1, wait // 60)} мин.")


@dp.message(Command("stockstatus"))
async def stockstatus_cmd(msg: Message):
    """Состояние автостока без запроса к источнику (кредиты не тратит)."""
    if not await redact_zone(msg):
        return
    fmt = lambda ts: datetime.fromtimestamp(ts, MSK).strftime("%d.%m %H:%M МСК") if ts else "—"  # noqa: E731
    anchor = await get_config("stock_anchor")
    paused = await get_config("stock_paused") == "1"
    mode = ("экономный (только смены Normal)" if STOCK_MONTHLY_LIMIT * max(1, len(STOCK_ACCOUNTS)) < 360 and not STOCK_FULL_MODE
            else "полный (каждые 2 часа)")
    lines = [f"Источник: {'настроен' if STOCK_ACCOUNTS else 'НЕ настроен'}",
             f"Цикл запущен: {'да' if _stock_task and not _stock_task.done() else 'нет'}",
             f"Режим: {mode}",
             f"Расписание: {'каждые 2 ч от ' + anchor + ' МСК' if anchor else 'по часам (чётные часы UTC)'}" + (" — ОСТАНОВЛЕНО" if paused else ""),
             f"Последняя проверка: {fmt(_stock_status['last_check'])}",
             f"Следующая проверка: {fmt(_stock_status['next_check'])}",
             f"Аккаунт Parse: №{await stock_current_acc() if STOCK_ACCOUNTS else '—'} (подключено: {len(STOCK_ACCOUNTS)})",
             f"Ошибка: {_stock_status['error'] or 'нет'}"]
    for acc in STOCK_ACCOUNTS:
        dead = " — кредиты кончились" if await get_config(_month_key(f"stock_dead_a{acc['n']}")) else ""
        lines.append(f"Аккаунт {acc['n']}: запросов {await stock_calls_used(acc['n'])}/{STOCK_MONTHLY_LIMIT}{dead}")
    chat_id = await main_chat()
    for kind in ("normal", "mirage"):
        st = await stock_state(kind)
        if st.get("items"):
            nxt = fmt(st["epoch"]) if st.get("epoch") else "—"
            lines.append(f"{kind}: сток {st['time']} МСК, след. смена {nxt}")
        else:
            lines.append(f"{kind}: ещё не публиковался")
    stock_mid = (await load_board()).get("msg")
    if stock_mid and chat_id and msg_url(chat_id, int(stock_mid)):
        lines.append(f"Сообщение стока: {msg_url(chat_id, int(stock_mid))}")
    if not chat_id:
        lines.append("ВНИМАНИЕ: основной чат не привязан (/link_hublox)")
    await reply(msg, "({21})<b>Автосток</b>\n<blockquote>" + "\n".join(esc(x) for x in lines) + "</blockquote>")


@dp.message(Command("stockcheck"))
async def stockcheck_cmd(msg: Message):
    """Проверка источника: что вернул и как бот это разобрал."""
    if not await redact_zone(msg):
        return
    if not STOCK_ACCOUNTS:
        await reply(msg, "({8})Источник не настроен. Добавьте в Railway Variables <code>STOCK_API_URL</code> "
                         "(и <code>STOCK_API_KEY</code>, если нужен ключ).")
        return
    import json
    try:
        data = await fetch_stock_json()
    except Exception as exc:
        await reply(msg, f"({{14}})Источник не ответил: <code>{esc(exc)}</code>")
        return
    parsed = extract_stock(data)
    resets = extract_resets(data)
    names = dict(FRUITS)
    lines = [f"{kind}: " + (", ".join(names[k] for k, _ in items) or "—") for kind, items in parsed.items()] or ["ничего не распознано"]
    raw = esc(json.dumps(data, ensure_ascii=False)[:1200])
    for kind, ts in resets.items():
        lines.append(f"{kind}: следующая смена {datetime.fromtimestamp(ts, MSK):%d.%m %H:%M} МСК")
    cur = await stock_current_acc()
    lines.append(f"аккаунт №{cur}: запросов в этом месяце {await stock_calls_used(cur)}/{STOCK_MONTHLY_LIMIT}")
    await reply(msg, "({39})<b>Проверка источника</b>\n<blockquote>" + "\n".join(esc(x) for x in lines) +
                     f"</blockquote>\n<b>Сырой ответ (начало):</b>\n<pre>{raw}</pre>")


# ------------------- подписки на фрукты (кнопка «Сток») -------------------
async def notify_stock_subscribers(kind: str, state: dict) -> None:
    """Личное уведомление тем, кто отметил фрукт, который появился в стоке."""
    rows = await pool().fetch("SELECT DISTINCT user_id FROM stock_subs WHERE fruit = ANY($1::text[])", state["keys"])
    if not rows:
        return
    body = await stock_text(kind, state, True)
    sent_ids: dict[str, int] = {}
    for r in rows:
        uid = r["user_id"]
        known = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", uid)
        who = mention(uid, known and known["username"], known and known["full_name"])
        try:
            sent = await B().send_message(uid, R(f"{who} фрукт в стоке!\n{body}"))
            sent_ids[str(uid)] = sent.message_id
        except Exception:
            pass
        await asyncio.sleep(0.05)  # не упираемся в лимиты Telegram
    await set_config(f"stock_dm_{kind}", json.dumps(sent_ids))  # чтобы потом пометить сток как истёкший


async def take_stock_dms(kind: str) -> dict[str, int]:
    """Забирает (и стирает) список личных уведомлений о прошлом стоке этого типа."""
    raw = await get_config(f"stock_dm_{kind}")
    if not raw:
        return {}
    await set_config(f"stock_dm_{kind}", "")
    try:
        return json.loads(raw)
    except ValueError:
        return {}


async def expire_stock_dms(kind: str, old: dict, sent: dict[str, int]) -> None:
    """Личные уведомления о стоке, который истёк: «Истёк 🔴», как в группе."""
    if not sent or not old.get("items"):
        return
    body = await stock_text(kind, old, False)
    for uid, message_id in sent.items():
        known = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", int(uid))
        who = mention(int(uid), known and known["username"], known and known["full_name"])
        try:
            await B().edit_message_text(R(f"{who} этот сток больше не активен.\n{body}"),
                                        chat_id=int(uid), message_id=message_id)
        except Exception as exc:
            if "not modified" not in str(exc).lower():
                LOG.debug("expire stock dm failed: %s", exc)
        await asyncio.sleep(0.05)


STOCK_MENU_TEXT = (f"{e(74)} <b>Сток</b>\n<blockquote>Отметьте фрукты. Когда любой из них появится в Normal "
                   "или Mirage стоке, бот пришлёт уведомление сюда, в личные сообщения.</blockquote>")


async def stock_menu_markup(user_id: int) -> InlineKeyboardMarkup:
    icons = await fruit_icons()
    chosen = {r["fruit"] for r in await pool().fetch("SELECT fruit FROM stock_subs WHERE user_id=$1", user_id)}
    buttons = [btn(f"{name}✅" if key in chosen else name, f"ssub_{key}", icon_id=icons.get(key))
               for key, name in FRUITS]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([btn("({14}) Очистить выбор", "stock_clear")])
    rows.append([BACK()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data == "menu_stock")
async def menu_stock(cb: CallbackQuery):
    await edit(cb, STOCK_MENU_TEXT, await stock_menu_markup(cb.from_user.id))


@dp.callback_query(F.data.startswith("ssub_"))
async def stock_toggle(cb: CallbackQuery):
    key = cb.data.removeprefix("ssub_")
    names = dict(FRUITS)
    if key not in names:
        await cb.answer("Неизвестный фрукт", show_alert=True)
        return
    uid = cb.from_user.id
    res = await pool().execute("DELETE FROM stock_subs WHERE user_id=$1 AND fruit=$2", uid, key)
    if res.endswith(" 0"):
        await pool().execute("INSERT INTO stock_subs (user_id, fruit) VALUES ($1,$2) ON CONFLICT DO NOTHING", uid, key)
        toast = f"{names[key]}: уведомления включены"
    else:
        toast = f"{names[key]}: уведомления выключены"
    try:
        await cb.message.edit_reply_markup(reply_markup=await stock_menu_markup(uid))
    except Exception:
        pass
    await cb.answer(toast)


@dp.callback_query(F.data == "stock_clear")
async def stock_clear(cb: CallbackQuery):
    await pool().execute("DELETE FROM stock_subs WHERE user_id=$1", cb.from_user.id)
    try:
        await cb.message.edit_reply_markup(reply_markup=await stock_menu_markup(cb.from_user.id))
    except Exception:
        pass
    await cb.answer("Выбор очищен")
# ===================== АВТОВАРН (ссылки, спам) =====================
async def auto_warn(msg: Message, reason: str) -> None:
    """Варн от имени бота. Кнопки апелляции у автоварна нет, главные админы его не снимают."""
    user = msg.from_user
    bot_id = B().id
    new, numbers, ban_no, error = await give_warns(msg.chat.id, user.id, 1, reason, bot_id, msg.message_id)
    if not numbers:
        return
    m = mention(user.id, user.username, user.full_name)
    await reply(msg, warn_text(m, new, reason, numbers, None, True))
    await log_action(f"Автоварн {new}/{MAX_WARNS}", bot_id, user.id, user.username, user.full_name,
                     reason, ", ".join(numbers), msg.chat.id, msg.message_id)
    if ban_no:
        await log_action("Бан (лимит варнов 4/4)", bot_id, user.id, user.username, user.full_name,
                         "Достигнут лимит варнов (4/4)", ban_no, msg.chat.id, msg.message_id)
        await say(msg, ban_text(m, "Достигнут лимит варнов (4/4)", ban_no, None), appeal_markup([("ban", ban_no)]))


SPAM_MSGS = 5        # больше 4 сообщений
SPAM_WINDOW = 5.0    # за 5 секунд
SPAM_TYPES = {"text", "sticker", "animation", "voice", "video_note", "audio",
              "document", "dice", "poll", "contact", "location", "venue"}  # фото и видео не считаются  # служебные сообщения не считаются
_spam_hist: dict[tuple, deque] = {}
_spam_group: dict[tuple, str] = {}


async def spam_check(msg: Message) -> None:
    user = msg.from_user
    if not user or user.is_bot or msg.sender_chat or msg.chat.type not in ("group", "supergroup"):
        return
    if str(getattr(msg.content_type, "value", msg.content_type)) not in SPAM_TYPES:
        return
    key = (msg.chat.id, user.id)
    if msg.media_group_id:  # альбом из нескольких фото — это одно сообщение
        if _spam_group.get(key) == msg.media_group_id:
            return
        _spam_group[key] = msg.media_group_id
    now = _time.monotonic()
    hist = _spam_hist.setdefault(key, deque(maxlen=SPAM_MSGS))
    hist.append(now)
    if len(_spam_hist) > 5000:
        for k in [k for k, v in _spam_hist.items() if not v or now - v[-1] > 10]:
            _spam_hist.pop(k, None)
            _spam_group.pop(k, None)
    if len(hist) < SPAM_MSGS or now - hist[0] > SPAM_WINDOW:
        return
    hist.clear()
    if msg.chat.id != await main_chat():
        return
    if user.id == CREATOR_ID:  # создатель неприкосновенен; админы и главные админы проверяются как все
        return
    if await rank_of(user.id) == 0:
        row = await user_row(user.id)
        if not (row and row["verified"]):
            return
    if await is_banned(user.id):
        return
    await auto_warn(msg, "1.16 Спам")


class SpamMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            if isinstance(event, Message):
                await spam_check(event)
        except Exception:
            LOG.exception("spam check failed")
        return await handler(event, data)


# ===================== /off и автозавершение заявок =====================
APP_TTL_HOURS = 24


async def close_application(app_id: int) -> bool:
    res = await pool().execute("UPDATE applications SET status='closed' WHERE id=$1 AND status<>'closed'", app_id)
    if res.endswith(" 0"):
        return False
    await refresh_application_post(app_id)
    return True


@dp.message(Command("off"))
async def off_cmd(msg: Message):
    """/off #-00045 — создатель завершает заявку; владельцу приходит сообщение в ЛС."""
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await reply(msg, "({15})У вас недостаточно прав")
        return
    args = command_args(msg)
    m = re.fullmatch(r"#?-?(\d{1,9})", args[0]) if args else None
    if not m:
        await reply(msg, "({8})<b>Ошибка завершения заявки</b>\n<blockquote>Укажите номер заявки:\n<i>/off #-00045</i></blockquote>")
        return
    app_id = int(m.group(1))
    app = await pool().fetchrow("SELECT * FROM applications WHERE id=$1", app_id)
    if not app:
        await reply(msg, f"({{8}})Заявка {num(app_id)} не найдена.")
        return
    if app["status"] == "closed":
        await reply(msg, f"({{8}})Заявка {num(app_id)} уже завершена.")
        return
    await close_application(app_id)
    sent = await dm(app["user_id"], f"{e(20)} Ваша заявка <b>{num(app_id)}</b> была завершена @{esc(CREATOR_USERNAME)}")
    await reply(msg, f"({{20}})Заявка {num(app_id)} завершена." +
                ("" if sent else "\nВладельцу не удалось отправить сообщение (он не запускал бота)."))


async def applications_expiry_loop() -> None:
    """Заявка завершается сама через 24 часа после создания."""
    await asyncio.sleep(30)
    while True:
        try:
            rows = await pool().fetch(
                "UPDATE applications SET status='closed' WHERE status<>'closed' AND created_at<$1 RETURNING id",
                now_ts() - APP_TTL_HOURS * 3600)
            for r in rows:
                await refresh_application_post(r["id"])
                await asyncio.sleep(0.3)
        except Exception:
            LOG.exception("applications expiry failed")
        await asyncio.sleep(300)


# ============================= /adminpanel =============================
async def person_html(uid: int) -> str:
    k = await pool().fetchrow("SELECT username, full_name FROM known_users WHERE user_id=$1", uid)
    return mention(uid, k and k["username"], k and k["full_name"])


async def panel_list():
    rows = await pool().fetch(
        """SELECT m.user_id, m.username, m.level, m.role, k.full_name FROM moderators m
           LEFT JOIN known_users k ON k.user_id = m.user_id
           WHERE m.level>0 AND m.user_id<>$1 ORDER BY m.level DESC, m.user_id""", CREATOR_ID)
    uniques = await pool().fetch(
        """SELECT u.user_id, u.username, u.role, k.full_name FROM unique_roles u
           LEFT JOIN known_users k ON k.user_id = u.user_id ORDER BY u.created_at""")
    buttons, seen = [], {CREATOR_ID}

    def label(r, role):
        name = r["full_name"] or (f"@{r['username']}" if r["username"] else str(r["user_id"]))
        return f"{name} — {role}"[:60]

    for r in rows:
        seen.add(r["user_id"])
        rank = rank_from_level(int(r["level"]))
        buttons.append([btn(label(r, r["role"] or RANK_NAMES[rank]), f"ap_u_{r['user_id']}",
                            icon_id=PREMIUM_EMOJI[30 if rank == 2 else 28])])
    for r in uniques:  # люди с уникальными ролями — тоже в списке
        if r["user_id"] in seen:
            continue
        seen.add(r["user_id"])
        buttons.append([btn(label(r, r["role"] or "Уникальная роль"), f"ap_u_{r['user_id']}", icon_id=PREMIUM_EMOJI[75])])
    buttons.append([btn("({14}) Закрыть", "ap_close")])
    text = (f"{e(21)} <b>Админ-панель</b>\n<blockquote>Выберите человека: админы, главные админы и уникальные роли.</blockquote>"
            if len(buttons) > 1 else f"{e(21)} <b>Админ-панель</b>\nСписок пуст.")
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


def panel_creator(cb: CallbackQuery) -> bool:
    return cb.from_user.id == CREATOR_ID


@dp.message(Command("adminpanel"))
async def adminpanel_cmd(msg: Message):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await reply(msg, "({15})У вас недостаточно прав")
        return
    if msg.chat.id != await admin_chat():
        await reply(msg, "({8})Админ-панель работает только в чате администрации.")
        return
    text, markup = await panel_list()
    # панель — в той теме админ-чата, где написана команда; из общей темы — в тему «Чат админов»
    tid = topic_of(msg) or thread(TOPICS["mod_chat"])
    await B().send_message(msg.chat.id, R(text), reply_markup=markup, message_thread_id=tid)


@dp.callback_query(F.data == "ap_close")
async def ap_close(cb: CallbackQuery):
    if not panel_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    await _delete_quiet(cb.message)
    await cb.answer()


@dp.callback_query(F.data == "ap_list")
async def ap_list(cb: CallbackQuery):
    if not panel_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    text, markup = await panel_list()
    await edit(cb, text, markup)


@dp.callback_query(F.data.startswith("ap_u_"))
async def ap_user(cb: CallbackQuery):
    if not panel_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    uid = int(cb.data.removeprefix("ap_u_"))
    markup = kb([btn("({21}) Telegram разрешения", f"ap_tg_{uid}")],
                [btn("({40}) DuoSup разрешения", f"ap_ds_{uid}")],
                [btn("({63}) Назад", "ap_list")])
    await edit(cb, f"{e(21)} <b>Админ:</b> {await person_html(uid)}\n<blockquote>Выберите раздел разрешений.</blockquote>", markup)


async def tg_rights_view(uid: int):
    rights = await get_rights(uid)
    rows = []
    for key, title, emoji_n, _ in PERM_RIGHTS:
        mark = "✅ " if rights.get(key) else "❌ "
        rows.append([btn(f"({{{emoji_n}}}) {mark}{title}", f"ap_tgt_{uid}_{key}")])
    rows.append([btn("({63}) Назад", f"ap_u_{uid}")])
    text = (f"{e(21)} <b>Telegram разрешения</b>\n{await person_html(uid)}\n"
            "<blockquote>Нажмите на право, чтобы включить или выключить. "
            "Изменения сразу применяются во всех чатах.</blockquote>")
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data.startswith("ap_tg_"))
async def ap_tg(cb: CallbackQuery):
    if not panel_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    text, markup = await tg_rights_view(int(cb.data.removeprefix("ap_tg_")))
    await edit(cb, text, markup)


@dp.callback_query(F.data.startswith("ap_tgt_"))
async def ap_tg_toggle(cb: CallbackQuery):
    if not panel_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    _, _, uid_s, key = cb.data.split("_", 3)
    uid = int(uid_s)
    if key not in {k for k, *_ in PERM_RIGHTS}:
        await cb.answer("Неизвестное право", show_alert=True)
        return
    rights = await get_rights(uid)
    rights[key] = not rights.get(key)
    role = (await pool().fetchval("SELECT role FROM admin_rights WHERE user_id=$1", uid)
            or await pool().fetchval("SELECT role FROM moderators WHERE user_id=$1", uid)
            or await pool().fetchval("SELECT role FROM unique_roles WHERE user_id=$1", uid) or "Админ")
    await pool().execute(
        """INSERT INTO admin_rights (user_id, role, rights, updated_at) VALUES ($1,$2,$3::jsonb,$4)
           ON CONFLICT (user_id) DO UPDATE SET rights=$3::jsonb, updated_at=$4""",
        uid, role, json.dumps(rights), now_ts())
    results = []
    for chat_id in await target_chats():
        if await is_member(chat_id, uid):
            results.append(await promote_in(chat_id, uid, rights, role))
    toast = ("Применено во всех чатах" if results and all(results)
             else "Не удалось обновить права в части чатов" if results else "Сохранено (админа нет в чатах)")
    text, markup = await tg_rights_view(uid)
    await edit(cb, text, markup)
    await cb.answer(toast)


async def ds_view(uid: int):
    override = await cmd_overrides(uid)
    rows = []
    for key, title, min_rank in CMD_PERMS:
        allowed = override.get(key, await perm_default(uid, key, min_rank))
        rows.append([btn(f"({{{20 if allowed else 14}}}) {title}", f"ap_dst_{uid}_{key}")])
    rows.append([btn("({63}) Назад", f"ap_u_{uid}")])
    text = (f"{e(21)} <b>DuoSup разрешения</b>\n{await person_html(uid)}\n"
            "<blockquote>✅ — разрешено, ❌ — запрещено. Нажмите, чтобы переключить.\n"
            "Апелляции, репорты и вопросы по умолчанию выключены.</blockquote>")
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data.startswith("ap_ds_"))
async def ap_ds(cb: CallbackQuery):
    if not panel_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    text, markup = await ds_view(int(cb.data.removeprefix("ap_ds_")))
    await edit(cb, text, markup)


@dp.callback_query(F.data.startswith("ap_dst_"))
async def ap_ds_toggle(cb: CallbackQuery):
    if not panel_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    _, _, uid_s, key = cb.data.split("_", 3)
    uid = int(uid_s)
    spec = next((x for x in CMD_PERMS if x[0] == key), None)
    if not spec:
        await cb.answer("Неизвестная команда", show_alert=True)
        return
    override = await cmd_overrides(uid)
    default = await perm_default(uid, key, spec[2])
    now_allowed = override.get(key, default)
    new = not now_allowed
    if new == default:
        override.pop(key, None)
    else:
        override[key] = new
    await set_config(f"cmdperm_{uid}", json.dumps(override) if override else "")
    text, markup = await ds_view(uid)
    await edit(cb, text, markup)
    await cb.answer(f"{spec[1]}: {'разрешено' if new else 'запрещено'}")


# ================================== ВИКИ ==================================
WIKI_CATEGORIES = ["Фрукт", "Аксессуар", "Предмет", "Меч", "Оружие", "Боевой стиль", "NPC", "Босс", "Остров", "Событие", "Другое"]
WIKI_SECTIONS = [("description", "Описание"), ("obtain", "Как получить"), ("stats", "Характеристика"), ("notes", "Примечания")]
SKILL_LABELS = ["Клики M1", "Z", "X", "C", "V", "F"]
WIKI_COOLDOWN = 10  # секунд между автоответами вики одному человеку
WIKI_MAX_MEDIA = 10
WIKI_MAX_SKILLS = 30
WIKI_SEED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wiki_seed.json")
_wiki_index: dict = {"at": 0, "keys": {}, "on": False}
_wiki_last: dict[int, int] = {}


class WikiSt(StatesGroup):
    title = State()
    category = State()
    aliases = State()
    obtain = State()
    description = State()
    photos = State()
    edit_value = State()
    edit_photos = State()
    import_file = State()
    stats = State()
    notes = State()
    sk_form = State()
    sk_label = State()
    sk_text = State()
    sk_media = State()


def wiki_norm(text: str) -> str:
    t = (text or "").lower().replace("ё", "е")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def wiki_dirty() -> None:
    _wiki_index["at"] = 0


async def wiki_index() -> dict:
    """Режим вики и словарь «название/псевдоним -> id записи» (кэш на 20 секунд)."""
    now = now_ts()
    if now - _wiki_index["at"] > 20:
        keys: dict[str, int] = {}
        for r in await pool().fetch("SELECT id, title, aliases FROM wiki_entries ORDER BY id"):
            try:
                names = [r["title"], *json.loads(r["aliases"] or "[]")]
            except ValueError:
                names = [r["title"]]
            for name in names:
                n = wiki_norm(name)
                if n:
                    keys.setdefault(n, r["id"])
        _wiki_index.update(at=now, keys=keys, on=(await get_config("wiki_on")) == "1")
    return _wiki_index


def wiki_split_aliases(text: str) -> list[str]:
    return [a.strip() for a in re.split(r"[,\n;]", text or "") if a.strip()][:20]


def wiki_text_html(raw: str, keys: dict) -> str:
    """[[Название]] и [[Название|подпись]] превращаются в ссылку: она открывает ЛС бота, и бот рассказывает об этом предмете."""
    def repl(m):
        target, _, label = m.group(1).partition("|")
        label = label or target
        eid = keys.get(wiki_norm(target))
        return f'<a href="https://t.me/{BOT_USERNAME}?start=w_{eid}">{label}</a>' if eid else label
    return re.sub(r"\[\[([^\[\]]{1,80})\]\]", repl, raw or "")


def wiki_rich_html(raw: str, keys: dict) -> str:
    """Текст, скопированный как есть (Premium Emoji, цитаты, ссылки), -> блоки Rich HTML.
    Строки идут абзацами, цитата — blockquote (многострочная — по абзацу на строку), сворачиваемая цитата — раскрывающийся блок."""
    raw = wiki_text_html(raw, keys)
    blocks, buf, stack = [], [], []
    for line in raw.split("\n"):
        for m in _TAG_RE.finditer(line):
            if m.group(0).endswith("/>"):
                continue
            name = m.group(2).lower()
            if m.group(1):
                if name in stack:
                    del stack[len(stack) - 1 - stack[::-1].index(name)]
            else:
                stack.append(name)
        buf.append(line)
        if not stack:
            blocks.append("\n".join(buf))
            buf = []
    if buf:
        blocks.append("\n".join(buf))
    out = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        q = re.match(r"<blockquote([^>]*)>(.*)</blockquote>\s*$", block, re.S)
        if q:
            inner = "".join(f"<p>{ln}</p>" for ln in q.group(2).split("\n") if ln.strip())
            out.append(f"<details><summary>Подробнее</summary>{inner}</details>" if "expandable" in q.group(1)
                       else f"<blockquote>{inner}</blockquote>")
        elif block.startswith("<pre"):
            out.append(block)
        else:
            out.append("<p>" + block.replace("\n", " ") + "</p>")
    return "".join(out)


def wiki_media_of(entry) -> list[tuple[str, str]]:
    items = [("photo", fid) for fid in json.loads(entry["photos"] or "[]")]
    items += [(m.get("t", "video"), m["id"]) for m in json.loads(entry["videos"] or "[]")
              if isinstance(m, dict) and m.get("id")]
    return items[:WIKI_MAX_MEDIA]


def wiki_split_media(items: list) -> tuple[list, list]:
    return ([i for t, i in items if t == "photo"],
            [{"t": t, "id": i} for t, i in items if t != "photo"])


def wiki_media_html(items: list, prefix: str, caption: str) -> tuple[str, dict]:
    """Фото и видео -> слайдшоу (листается в сторону); одно вложение — обычный блок с подписью."""
    if not items:
        return "", {}
    media, tags = {}, []
    for i, (t, fid) in enumerate(items):
        key = f"{prefix}{i}"
        media[key] = (t, fid)
        tags.append(f'<img src="tg://photo?id={key}"/>' if t == "photo" else f'<video src="tg://video?id={key}"/>')
    tag = "tg-slideshow" if len(items) > 1 else "figure"
    return f"<{tag}>{''.join(tags)}<figcaption>{esc(caption)}</figcaption></{tag}>", media


async def wiki_rich_payload(entry) -> tuple[str, dict]:
    """Карточка: название, фото/видео слайдшоу, затем описание, как получить, характеристика, примечания."""
    keys = (await wiki_index())["keys"]
    parts = [f"<h2>{esc(entry['title'])}</h2>", f"<p><i>{esc(entry['category'])}</i></p>"]
    media_html, media = wiki_media_html(wiki_media_of(entry), "m", entry["title"])
    parts.append(media_html)
    filled = False
    for field, title in WIKI_SECTIONS:
        if (entry[field] or "").strip():
            parts.append(f"<h3>{title}</h3>" + wiki_rich_html(entry[field], keys))
            filled = True
    if not filled:
        parts.append("<p><i>Информация пока не добавлена.</i></p>")
    return "".join(parts), media


SKILL_ORDER = ["M1", "Z", "X", "C", "V", "F"]
_LOOKALIKE = str.maketrans({"М": "M", "С": "C", "Х": "X", "Ф": "F"})


def skill_rank(label: str) -> int:
    t = (label or "").strip().upper().translate(_LOOKALIKE)
    if t.startswith("КЛИК") or t.startswith("M1") or t.startswith("M 1"):
        return 0
    for i, k in enumerate(SKILL_ORDER[1:], 1):
        if t[:1] == k and (len(t) == 1 or not t[1].isalnum()):
            return i
    return 50


def wiki_skill_pages(entry, form: int) -> list:
    pages = [sk for sk in json.loads(entry["skills"] or "[]") if int(sk.get("form", 1)) == form]
    return sorted(pages, key=lambda sk: skill_rank(sk.get("label", "")))  # порядок M1, Z, X, C, V, F; остальное — как добавили


def wiki_forms(entry) -> list:
    return sorted({int(sk.get("form", 1)) for sk in json.loads(entry["skills"] or "[]")})


async def wiki_skill_payload(entry, form: int) -> tuple[str, dict]:
    """Одно Rich-сообщение: у каждого приёма заголовок, несколько фото/видео и описание (характеристика, урон)."""
    keys = (await wiki_index())["keys"]
    pages = wiki_skill_pages(entry, form)
    parts, media = [f"<h2>{esc(entry['title'])} — скиллы{' (V2)' if form == 2 else ''}</h2>"], {}
    for i, sk in enumerate(pages):
        parts.append(f"<h3>{esc(sk['label'])}</h3>")
        items = [(m.get("t", "video"), m["id"]) for m in sk.get("media", []) if isinstance(m, dict) and m.get("id")]
        media_html, m = wiki_media_html(items[:WIKI_MAX_MEDIA], f"s{i}_", sk["label"])
        parts.append(media_html)
        media.update(m)
        if (sk.get("text") or "").strip():
            parts.append(wiki_rich_html(sk["text"], keys))
    return "".join(parts), media


async def wiki_plain_html(entry) -> str:
    """Запасной вариант (обычное сообщение), если Rich-сообщение не отправилось."""
    keys = (await wiki_index())["keys"]
    text = f"<b>{esc(entry['title'])}</b>\n<i>{esc(entry['category'])}</i>"
    for field, title in WIKI_SECTIONS:
        if (entry[field] or "").strip():
            text += f"\n\n<b>{title}</b>\n" + wiki_text_html(entry[field], keys)
    return text[:4000]


def wiki_entry_markup(entry, viewer: int = 0):
    """Под карточкой — кнопка «Посмотреть скиллы» (если они есть). viewer: чужие нажатия не принимаются."""
    forms = wiki_forms(entry)
    if not forms:
        return None
    return kb([btn("({21}) Посмотреть скиллы", f"wk_s_{entry['id']}_{forms[0]}_{viewer}")])


def wiki_skill_nav(entry, form: int, viewer: int):
    forms = wiki_forms(entry)
    rows = []
    if form == 1 and 2 in forms:
        rows.append([btn("({21}) Посмотреть V2 форму", f"wk_s_{entry['id']}_2_{viewer}")])
    if form == 2 and 1 in forms:
        rows.append([btn("({21}) Вернуться к V1", f"wk_s_{entry['id']}_1_{viewer}")])
    rows.append([btn("({63}) Назад", f"wk_b_{entry['id']}_{viewer}")])
    return kb(*rows)


def _rich_body(html_text: str, media: dict) -> dict:
    rich: dict = {"html": html_text, "skip_entity_detection": True}
    if media:
        rich["media"] = [{"id": k, "media": {"type": (v[0] if isinstance(v, tuple) else "photo"),
                                              "media": (v[1] if isinstance(v, tuple) else v)}} for k, v in media.items()]
    return rich


async def _tg_call(method: str, payload: dict) -> dict:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload) as resp:
            data = await resp.json(content_type=None)
    if not data.get("ok"):
        raise RuntimeError(data.get("description", f"{method} failed"))
    return data


async def send_rich(chat_id: int, html_text: str, media: dict, thread_id: int | None = None,
                    reply_to: int | None = None, markup=None) -> int | None:
    """sendRichMessage (Bot API 10.1+) напрямую: библиотека может его не знать."""
    payload: dict = {"chat_id": chat_id, "rich_message": _rich_body(html_text, media)}
    if thread_id:
        payload["message_thread_id"] = thread_id
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to}
    if markup is not None:
        payload["reply_markup"] = markup.model_dump(exclude_none=True)
    data = await _tg_call("sendRichMessage", payload)
    result = data.get("result")
    return result.get("message_id") if isinstance(result, dict) else None


async def edit_rich(chat_id: int, message_id: int, html_text: str, media: dict, markup=None) -> None:
    payload: dict = {"chat_id": chat_id, "message_id": message_id, "rich_message": _rich_body(html_text, media)}
    if markup is not None:
        payload["reply_markup"] = markup.model_dump(exclude_none=True)
    await _tg_call("editMessageText", payload)


async def wiki_send(chat_id: int, entry, thread_id: int | None = None, reply_to: int | None = None,
                    viewer: int = 0) -> None:
    markup = wiki_entry_markup(entry, viewer)
    try:
        html_text, media = await wiki_rich_payload(entry)
        await send_rich(chat_id, html_text, media, thread_id, reply_to, markup)
        return
    except Exception as exc:
        LOG.warning("wiki: Rich-сообщение не отправилось (%s), отправляю обычным", exc)
    from aiogram.types import InputMediaPhoto
    extra: dict = {}
    if thread_id:
        extra["message_thread_id"] = thread_id
    if reply_to:
        extra["reply_parameters"] = {"message_id": reply_to}
    try:
        items = wiki_media_of(entry)
        photos = [i for t, i in items if t == "photo"]
        if len(photos) == 1:
            await B().send_photo(chat_id, photos[0], **extra)
        elif photos:
            await B().send_media_group(chat_id, [InputMediaPhoto(media=f) for f in photos], **extra)
        for t, fid in items:
            if t == "video":
                await B().send_video(chat_id, fid, **extra)
            elif t == "animation":
                await B().send_animation(chat_id, fid, **extra)
    except Exception:
        LOG.exception("wiki: медиа не отправились")
    await B().send_message(chat_id, R(await wiki_plain_html(entry)), reply_markup=markup, **extra)


def wiki_suggest(query: str, keys: dict) -> str:
    near = difflib.get_close_matches(wiki_norm(query), list(keys), n=3, cutoff=0.55)
    return ("Возможно, вы искали: " + ", ".join(near)) if near else "Проверьте название."


async def wiki_where_ok(msg: Message) -> bool:
    """Вики работает в личке и в основном чате (во всех темах); создателю — ещё и в админ-чате."""
    if msg.chat.type == "private":
        return True
    if msg.chat.id == await main_chat():
        return True
    return bool(msg.from_user) and msg.from_user.id == CREATOR_ID and msg.chat.id == await admin_chat()


# ---------- ответы пользователям ----------
@dp.message(Command("wiki"))
async def wiki_cmd(msg: Message):
    args = command_args(msg)
    uid = msg.from_user.id if msg.from_user else 0
    if len(args) == 1 and args[0].lower() in ("on", "off", "вкл", "выкл"):
        if uid != CREATOR_ID:
            await reply(msg, "({15})У вас недостаточно прав")
            return
        on = args[0].lower() in ("on", "вкл")
        await set_config("wiki_on", "1" if on else "0")
        wiki_dirty()
        await reply(msg, f"({{20}})Режим вики {'включён' if on else 'выключен'}.")
        return
    if not await wiki_where_ok(msg):
        return
    idx = await wiki_index()
    if not idx["on"] and uid != CREATOR_ID:
        await reply(msg, "({8})Режим вики сейчас выключен.")
        return
    query = " ".join(args)
    if not query:
        await reply(msg, f"({{39}})<b>Вики</b>\nНапишите <code>/wiki название</code>. В базе записей: {len(set(idx['keys'].values()))}.")
        return
    eid = idx["keys"].get(wiki_norm(query))
    if not eid:
        await reply(msg, f"({{8}})Не нашёл «{esc(query)}». {esc(wiki_suggest(query, idx['keys']))}")
        return
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", eid)
    await wiki_send(msg.chat.id, entry, topic_of(msg), msg.message_id, uid if msg.chat.type != "private" else 0)


async def wiki_trigger(msg: Message):
    """Режим вики включён: сообщение, которое целиком совпадает с названием записи, получает ответ."""
    if not msg.text or not msg.from_user or msg.from_user.is_bot or msg.text.startswith("/") or len(msg.text) > 60:
        return False
    idx = await wiki_index()
    eid = idx["keys"].get(wiki_norm(msg.text)) if idx["on"] else None
    if not eid or not await wiki_where_ok(msg):
        return False
    return {"wiki_id": eid}


@dp.message(wiki_trigger)
async def wiki_auto(msg: Message, wiki_id: int):
    uid = msg.from_user.id
    now = now_ts()
    if uid != CREATOR_ID and now - _wiki_last.get(uid, 0) < WIKI_COOLDOWN:
        return
    _wiki_last[uid] = now
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", wiki_id)
    if entry:
        await wiki_send(msg.chat.id, entry, topic_of(msg), msg.message_id, uid if msg.chat.type != "private" else 0)


async def wiki_edit_view(cb: CallbackQuery, html_text: str, media: dict, markup, plain: str) -> None:
    """Сообщение «проявляет» другую страницу: правим его Rich-сообщением (запасной вариант — обычный текст)."""
    try:
        await edit_rich(cb.message.chat.id, cb.message.message_id, html_text, media, markup)
    except Exception as exc:
        if "not modified" not in str(exc).lower():
            LOG.warning("wiki: edit_rich не удалось (%s), правлю обычным текстом", exc)
            try:
                await cb.message.edit_text(R(plain[:4000]), reply_markup=markup)
            except Exception:
                pass
    try:
        await cb.answer()
    except Exception:
        pass


@dp.callback_query(F.data.startswith("wk_s_"))
async def wk_skill_view(cb: CallbackQuery):
    _, _, eid_s, form_s, viewer_s = cb.data.split("_", 4)
    viewer = int(viewer_s)
    if viewer and cb.from_user.id not in (viewer, CREATOR_ID):
        await cb.answer("Это сообщение открыл другой участник. Напишите свой запрос.", show_alert=True)
        return
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", int(eid_s))
    form = int(form_s)
    pages = wiki_skill_pages(entry, form) if entry else []
    if not pages:
        await cb.answer("Скиллов пока нет.", show_alert=True)
        return
    html_text, media = await wiki_skill_payload(entry, form)
    keys = (await wiki_index())["keys"]
    plain = f"<b>{esc(entry['title'])}</b> — скиллы{' (V2)' if form == 2 else ''}" + "".join(
        f"\n\n<b>{esc(sk['label'])}</b>\n" + wiki_text_html(sk.get("text", ""), keys) for sk in pages)
    await wiki_edit_view(cb, html_text, media, wiki_skill_nav(entry, form, viewer), plain)


@dp.callback_query(F.data.startswith("wk_b_"))
async def wk_back_to_entry(cb: CallbackQuery):
    _, _, eid_s, viewer_s = cb.data.split("_", 3)
    viewer = int(viewer_s)
    if viewer and cb.from_user.id not in (viewer, CREATOR_ID):
        await cb.answer("Это сообщение открыл другой участник.", show_alert=True)
        return
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", int(eid_s))
    if not entry:
        await cb.answer("Записи уже нет", show_alert=True)
        return
    html_text, media = await wiki_rich_payload(entry)
    await wiki_edit_view(cb, html_text, media, wiki_entry_markup(entry, viewer), await wiki_plain_html(entry))


# ---------- наполнение: только создатель ----------
def wk_creator(cb: CallbackQuery) -> bool:
    return cb.from_user.id == CREATOR_ID


def wk_category_markup(prefix: str) -> InlineKeyboardMarkup:
    rows, row = [], []
    for i, name in enumerate(WIKI_CATEGORIES):
        row.append(InlineKeyboardButton(text=name, callback_data=f"{prefix}{i}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wk_media_item(msg: Message):
    if msg.photo:
        return ("photo", msg.photo[-1].file_id)
    if msg.video:
        return ("video", msg.video.file_id)
    if msg.animation:
        return ("animation", msg.animation.file_id)
    return None


async def wiki_upsert(title: str, category: str, aliases: list, obtain: str, description: str, photos: list,
                      videos: list | None = None, skills: list | None = None,
                      stats: str | None = None, notes: str | None = None) -> int:
    """videos / skills / stats / notes = None — оставить как есть у существующей записи."""
    row = await pool().fetchrow(
        """INSERT INTO wiki_entries (title, norm, category, aliases, obtain, description, photos, videos, skills,
                                     stats, notes, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,COALESCE($8,'[]'),COALESCE($9,'[]'),COALESCE($10,''),COALESCE($11,''),$12)
           ON CONFLICT (norm) DO UPDATE SET title=$1, category=$3, aliases=$4, obtain=$5, description=$6, photos=$7,
                videos=COALESCE($8, wiki_entries.videos), skills=COALESCE($9, wiki_entries.skills),
                stats=COALESCE($10, wiki_entries.stats), notes=COALESCE($11, wiki_entries.notes), updated_at=$12
           RETURNING id""",
        title, wiki_norm(title), category, json.dumps(aliases, ensure_ascii=False), obtain, description,
        json.dumps(photos), None if videos is None else json.dumps(videos),
        None if skills is None else json.dumps(skills, ensure_ascii=False), stats, notes, now_ts())
    wiki_dirty()
    return row["id"]


async def wiki_find(msg: Message, query: str):
    idx = await wiki_index()
    eid = idx["keys"].get(wiki_norm(query))
    if not eid:
        await reply(msg, f"({{8}})Не нашёл «{esc(query)}». {esc(wiki_suggest(query, idx['keys']))}")
        return None
    return await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", eid)


async def wiki_finish_add(msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    photos, videos = wiki_split_media(data.get("media", []))
    eid = await wiki_upsert(data["title"], data.get("category", "Другое"), data.get("aliases", []),
                            data.get("obtain", ""), data.get("description", ""), photos, videos,
                            stats=data.get("stats", ""), notes=data.get("notes", ""))
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", eid)
    await reply(msg, f"({{20}})Запись <b>{esc(entry['title'])}</b> сохранена. Так она выглядит у участников:")
    await wiki_send(msg.chat.id, entry, topic_of(msg))


@dp.message(Command("wikiadd"))
async def wikiadd_cmd(msg: Message, state: FSMContext):
    if not await redact_zone(msg):
        return
    await state.clear()
    title = " ".join(command_args(msg)).strip()[:80]
    if title:
        await state.update_data(title=title)
        await state.set_state(WikiSt.category)
        await reply(msg, f"({{39}})<b>{esc(title)}</b>\nВыберите категорию (или напишите свою).", wk_category_markup("wk_cat_"))
    else:
        await state.set_state(WikiSt.title)
        await reply(msg, "({39})Название новой записи? (/cancel — отмена)")


@dp.message(WikiSt.title, F.text, ~F.text.startswith("/"))
async def wk_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text.strip()[:80])
    await state.set_state(WikiSt.category)
    await reply(msg, "({39})Выберите категорию (или напишите свою).", wk_category_markup("wk_cat_"))


async def wk_to_aliases(msg: Message, state: FSMContext, category: str) -> None:
    await state.update_data(category=category[:30])
    await state.set_state(WikiSt.aliases)
    await reply(msg, "({39})Другие названия для поиска (через запятую: русское, сокращения). «-» — пропустить.")


@dp.callback_query(WikiSt.category, F.data.startswith("wk_cat_"))
async def wk_cat_cb(cb: CallbackQuery, state: FSMContext):
    if not wk_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    await cb.answer()
    await wk_to_aliases(cb.message, state, WIKI_CATEGORIES[int(cb.data.removeprefix("wk_cat_"))])


@dp.message(WikiSt.category, F.text, ~F.text.startswith("/"))
async def wk_cat_text(msg: Message, state: FSMContext):
    await wk_to_aliases(msg, state, msg.text.strip())


@dp.message(WikiSt.aliases, F.text, ~F.text.startswith("/"))
async def wk_aliases(msg: Message, state: FSMContext):
    await state.update_data(aliases=[] if msg.text.strip() == "-" else wiki_split_aliases(msg.text))
    await state.set_state(WikiSt.description)
    await reply(msg, "({39})<b>Описание</b> — бот скопирует сообщение как есть (Premium Emoji, цитаты, ссылки). "
                     "Ссылки на другие записи: <code>[[Mirror Fractal]]</code>. «-» — пропустить.")


@dp.message(WikiSt.description, F.text, ~F.text.startswith("/"))
async def wk_description(msg: Message, state: FSMContext):
    await state.update_data(description="" if msg.text.strip() == "-" else msg.html_text.strip())
    await state.set_state(WikiSt.obtain)
    await reply(msg, "({39})<b>Как получить</b> — коротко и понятно. «-» — пропустить.")


@dp.message(WikiSt.obtain, F.text, ~F.text.startswith("/"))
async def wk_obtain(msg: Message, state: FSMContext):
    await state.update_data(obtain="" if msg.text.strip() == "-" else msg.html_text.strip())
    await state.set_state(WikiSt.stats)
    await reply(msg, "({39})<b>Характеристика</b> (например бонусы аксессуара, урон, кулдаун). «-» — пропустить.")


@dp.message(WikiSt.stats, F.text, ~F.text.startswith("/"))
async def wk_stats(msg: Message, state: FSMContext):
    await state.update_data(stats="" if msg.text.strip() == "-" else msg.html_text.strip())
    await state.set_state(WikiSt.notes)
    await reply(msg, "({39})<b>Примечания</b>. «-» — пропустить.")


@dp.message(WikiSt.notes, F.text, ~F.text.startswith("/"))
async def wk_notes(msg: Message, state: FSMContext):
    await state.update_data(notes="" if msg.text.strip() == "-" else msg.html_text.strip(), media=[])
    await state.set_state(WikiSt.photos)
    await reply(msg, "({39})Отправьте <b>фото и видео</b> по одному (они будут слайд-шоу). Когда закончите — /done. «-» — без медиа.")


@dp.message(WikiSt.photos, F.photo | F.video | F.animation)
async def wk_photo(msg: Message, state: FSMContext):
    media = (await state.get_data()).get("media", [])
    media.append(list(wk_media_item(msg)))
    media = media[:WIKI_MAX_MEDIA]
    await state.update_data(media=media)
    await reply(msg, f"({{20}})Принято: {len(media)}/{WIKI_MAX_MEDIA}. Ещё или /done.")


@dp.message(WikiSt.photos, Command("done"))
async def wk_photos_done(msg: Message, state: FSMContext):
    await wiki_finish_add(msg, state)


@dp.message(WikiSt.photos, F.text == "-")
async def wk_photos_skip(msg: Message, state: FSMContext):
    await wiki_finish_add(msg, state)


def wiki_card(entry) -> str:
    aliases = ", ".join(json.loads(entry["aliases"] or "[]")) or "—"
    media = len(wiki_media_of(entry))
    def has(field: str) -> str:
        return "есть" if (entry[field] or "").strip() else "нет"
    skills = json.loads(entry["skills"] or "[]")
    v2 = sum(1 for sk in skills if int(sk.get("form", 1)) == 2)
    return (f"({{39}})<b>{esc(entry['title'])}</b> • {esc(entry['category'])}\n"
            f"<blockquote>Другие названия: {esc(aliases)}\nФото и видео: {media}\n"
            f"Описание: {has('description')} • Как получить: {has('obtain')}\n"
            f"Характеристика: {has('stats')} • Примечания: {has('notes')}\n"
            f"Скиллы: {len(skills) - v2} (V2: {v2})</blockquote>")


def wiki_edit_markup(eid: int) -> InlineKeyboardMarkup:
    def b(text, field):
        return InlineKeyboardButton(text=text, callback_data=f"wk_e_{eid}_{field}")
    return InlineKeyboardMarkup(inline_keyboard=[
        [b("✏️ Название", "title"), b("🏷 Др. названия", "aliases")],
        [b("📂 Категория", "category"), b("⚔️ Скиллы", "skills")],
        [b("📝 Описание", "description"), b("🧭 Как получить", "obtain")],
        [b("📊 Характеристика", "stats"), b("🗒 Примечания", "notes")],
        [b("🖼 Медиа: заменить", "photos"), b("➕ Медиа: добавить", "photosadd")],
        [b("👁 Показать как у участников", "show"), b("🗑 Удалить", "del")],
    ])


@dp.message(Command("wikiedit"))
async def wikiedit_cmd(msg: Message, state: FSMContext):
    if not await redact_zone(msg):
        return
    await state.clear()
    query = " ".join(command_args(msg))
    if not query:
        await reply(msg, "({8})Укажите запись: <code>/wikiedit Kitsune</code>")
        return
    entry = await wiki_find(msg, query)
    if entry:
        await reply(msg, wiki_card(entry), wiki_edit_markup(entry["id"]))


@dp.message(Command("wikidel"))
async def wikidel_cmd(msg: Message, state: FSMContext):
    if not await redact_zone(msg):
        return
    query = " ".join(command_args(msg))
    entry = await wiki_find(msg, query) if query else None
    if not entry:
        if not query:
            await reply(msg, "({8})Укажите запись: <code>/wikidel Kitsune</code>")
        return
    await reply(msg, f"({{8}})Удалить запись <b>{esc(entry['title'])}</b>?",
                kb([btn("({20}) Да, удалить", f"wk_del_{entry['id']}"), btn("({14}) Отмена", "wk_cancel")]))


@dp.callback_query(F.data == "wk_cancel")
async def wk_cancel(cb: CallbackQuery):
    if wk_creator(cb):
        await cb.answer("Отменено")
        await _delete_quiet(cb.message)


@dp.callback_query(F.data.startswith("wk_del_"))
async def wk_del(cb: CallbackQuery):
    if not wk_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    await pool().execute("DELETE FROM wiki_entries WHERE id=$1", int(cb.data.removeprefix("wk_del_")))
    wiki_dirty()
    await cb.answer("Удалено")
    await edit(cb, "({20})Запись удалена.", None)


def wk_thread(cb: CallbackQuery) -> dict:
    return {"message_thread_id": cb.message.message_thread_id} if cb.message.is_topic_message else {}


@dp.callback_query(F.data.startswith("wk_e_"))
async def wk_edit_cb(cb: CallbackQuery, state: FSMContext):
    if not wk_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    _, _, eid_s, field = cb.data.split("_", 3)
    eid = int(eid_s)
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", eid)
    if not entry:
        await cb.answer("Записи уже нет", show_alert=True)
        return
    await cb.answer()
    if field == "show":
        await wiki_send(cb.message.chat.id, entry, cb.message.message_thread_id if cb.message.is_topic_message else None)
    elif field == "del":
        await cb.message.answer(R(f"({{8}})Удалить запись <b>{esc(entry['title'])}</b>?"),
                                reply_markup=kb([btn("({20}) Да, удалить", f"wk_del_{eid}"), btn("({14}) Отмена", "wk_cancel")]),
                                **wk_thread(cb))
    elif field == "category":
        await cb.message.edit_reply_markup(reply_markup=wk_category_markup(f"wk_ec_{eid}_"))
    elif field == "skills":
        text, markup = wiki_skills_manager(entry)
        await edit(cb, text, markup)
    elif field in ("photos", "photosadd"):
        await state.set_state(WikiSt.edit_photos)
        await state.update_data(eid=eid, media=[], add=(field == "photosadd"))
        await cb.message.answer(R("({39})Отправляйте фото и видео по одному, затем /done. "
                                  + ("Они добавятся к текущим." if field == "photosadd" else "Они заменят текущие.")),
                                **wk_thread(cb))
    else:
        await state.set_state(WikiSt.edit_value)
        await state.update_data(eid=eid, field=field)
        hint = {"title": "новое название", "aliases": "другие названия через запятую",
                "obtain": "текст «Как получить» (скопирую как есть)", "description": "текст описания (скопирую как есть)",
                "stats": "текст «Характеристика» (скопирую как есть)", "notes": "текст «Примечания» (скопирую как есть)"}[field]
        await cb.message.answer(R(f"({{39}})Отправьте {hint}. «-» — очистить."), **wk_thread(cb))


@dp.callback_query(F.data.startswith("wk_ec_"))
async def wk_edit_category(cb: CallbackQuery):
    if not wk_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    _, _, eid_s, idx_s = cb.data.split("_", 3)
    await pool().execute("UPDATE wiki_entries SET category=$1, updated_at=$2 WHERE id=$3",
                         WIKI_CATEGORIES[int(idx_s)], now_ts(), int(eid_s))
    wiki_dirty()
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", int(eid_s))
    await cb.answer("Готово")
    await edit(cb, wiki_card(entry), wiki_edit_markup(int(eid_s)))


@dp.message(WikiSt.edit_value, F.text, ~F.text.startswith("/"))
async def wk_edit_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    eid, field = data["eid"], data["field"]
    text = msg.text.strip()
    if field == "title":
        if text == "-":
            await reply(msg, "({8})Название нельзя очистить.")
            return
        norm = wiki_norm(text[:80])
        taken = await pool().fetchval("SELECT id FROM wiki_entries WHERE norm=$1 AND id<>$2", norm, eid)
        if taken:
            await reply(msg, "({8})Запись с таким названием уже есть.")
            return
        await pool().execute("UPDATE wiki_entries SET title=$1, norm=$2, updated_at=$3 WHERE id=$4",
                             text[:80], norm, now_ts(), eid)
    elif field == "aliases":
        await pool().execute("UPDATE wiki_entries SET aliases=$1, updated_at=$2 WHERE id=$3",
                             json.dumps([] if text == "-" else wiki_split_aliases(text), ensure_ascii=False), now_ts(), eid)
    else:  # obtain / description: сохраняем как прислали (Premium Emoji, цитаты, жирный, ссылки)
        value = "" if text == "-" else msg.html_text.strip()
        await pool().execute(f"UPDATE wiki_entries SET {field}=$1, updated_at=$2 WHERE id=$3", value, now_ts(), eid)
    wiki_dirty()
    await state.clear()
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", eid)
    await reply(msg, wiki_card(entry), wiki_edit_markup(eid))


@dp.message(WikiSt.edit_photos, F.photo | F.video | F.animation)
async def wk_edit_photo(msg: Message, state: FSMContext):
    media = (await state.get_data()).get("media", [])
    media.append(list(wk_media_item(msg)))
    media = media[:WIKI_MAX_MEDIA]
    await state.update_data(media=media)
    await reply(msg, f"({{20}})Принято: {len(media)}/{WIKI_MAX_MEDIA}. Ещё или /done.")


@dp.message(WikiSt.edit_photos, Command("done"))
async def wk_edit_photos_done(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    new = [tuple(i) for i in data.get("media", [])]
    if not new:
        await reply(msg, "({8})Ничего не получено, ничего не изменено.")
        return
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", data["eid"])
    items = (wiki_media_of(entry) + new)[:WIKI_MAX_MEDIA] if data.get("add") else new
    photos, videos = wiki_split_media(items)
    await pool().execute("UPDATE wiki_entries SET photos=$1, videos=$2, updated_at=$3 WHERE id=$4",
                         json.dumps(photos), json.dumps(videos), now_ts(), data["eid"])
    wiki_dirty()
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", data["eid"])
    await reply(msg, wiki_card(entry), wiki_edit_markup(data["eid"]))
    await wiki_send(msg.chat.id, entry, topic_of(msg))


# ---------- скиллы: приёмы (Клики M1, Z, X, C, V, F), форма V1 и V2 ----------
def wiki_skills_manager(entry):
    skills = json.loads(entry["skills"] or "[]")
    lines = [f"{'V2' if int(sk.get('form', 1)) == 2 else 'V1'} • {esc(sk['label'])} — медиа: {len(sk.get('media', []))}"
             for sk in skills]
    text = (f"({{39}})<b>{esc(entry['title'])}</b> — скиллы\n"
            f"<blockquote>{chr(10).join(lines) if lines else 'Приёмов пока нет.'}</blockquote>")
    rows = [[InlineKeyboardButton(text=f"🗑 {'V2' if int(sk.get('form', 1)) == 2 else 'V1'} {sk['label'][:22]}",
                                  callback_data=f"wk_skdel_{entry['id']}_{i}")] for i, sk in enumerate(skills)]
    if len(skills) < WIKI_MAX_SKILLS:
        rows.append([InlineKeyboardButton(text="➕ Добавить приём", callback_data=f"wk_skadd_{entry['id']}")])
    rows.append([InlineKeyboardButton(text="⬅️ К записи", callback_data=f"wk_card_{entry['id']}")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data.startswith("wk_card_"))
async def wk_card_cb(cb: CallbackQuery):
    if not wk_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    eid = int(cb.data.removeprefix("wk_card_"))
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", eid)
    if entry:
        await edit(cb, wiki_card(entry), wiki_edit_markup(eid))


@dp.callback_query(F.data.startswith("wk_skdel_"))
async def wk_skill_delete(cb: CallbackQuery):
    if not wk_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    _, _, eid_s, idx_s = cb.data.split("_", 3)
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", int(eid_s))
    skills = json.loads(entry["skills"] or "[]")
    if 0 <= int(idx_s) < len(skills):
        skills.pop(int(idx_s))
        await pool().execute("UPDATE wiki_entries SET skills=$1, updated_at=$2 WHERE id=$3",
                             json.dumps(skills, ensure_ascii=False), now_ts(), entry["id"])
        entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", entry["id"])
    text, markup = wiki_skills_manager(entry)
    await edit(cb, text, markup)


@dp.callback_query(F.data.startswith("wk_skadd_"))
async def wk_skill_add(cb: CallbackQuery, state: FSMContext):
    if not wk_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    await state.set_state(WikiSt.sk_form)
    await state.update_data(eid=int(cb.data.removeprefix("wk_skadd_")))
    await cb.answer()
    await cb.message.answer(R("({39})Для какой формы фрукта этот приём?"),
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                InlineKeyboardButton(text="V1 (обычная)", callback_data="wk_skf_1"),
                                InlineKeyboardButton(text="V2 (пробуждённая)", callback_data="wk_skf_2")]]),
                            **wk_thread(cb))


@dp.callback_query(WikiSt.sk_form, F.data.startswith("wk_skf_"))
async def wk_sk_form(cb: CallbackQuery, state: FSMContext):
    if not wk_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    await state.update_data(form=int(cb.data.removeprefix("wk_skf_")))
    await state.set_state(WikiSt.sk_label)
    await cb.answer()
    rows, row = [], []
    for i, name in enumerate(SKILL_LABELS):
        row.append(InlineKeyboardButton(text=name, callback_data=f"wk_skl_{i}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    await cb.message.answer(R("({39})Выберите приём или напишите своё название (например <code>X — в воздухе</code>)."),
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), **wk_thread(cb))


async def wk_sk_ask_text(message: Message, state: FSMContext, label: str) -> None:
    await state.update_data(label=label[:40])
    await state.set_state(WikiSt.sk_text)
    await message.answer(R(f"({{39}})<b>{esc(label)}</b>: описание, характеристика и урон одним сообщением. "
                           "Скопирую как есть (Premium Emoji, цитаты, ссылки). «-» — только медиа."),
                         **({"message_thread_id": message.message_thread_id} if message.is_topic_message else {}))


@dp.callback_query(WikiSt.sk_label, F.data.startswith("wk_skl_"))
async def wk_sk_label_cb(cb: CallbackQuery, state: FSMContext):
    if not wk_creator(cb):
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    await cb.answer()
    await wk_sk_ask_text(cb.message, state, SKILL_LABELS[int(cb.data.removeprefix("wk_skl_"))])


@dp.message(WikiSt.sk_label, F.text, ~F.text.startswith("/"))
async def wk_sk_label(msg: Message, state: FSMContext):
    await wk_sk_ask_text(msg, state, msg.text.strip())


@dp.message(WikiSt.sk_text, F.text, ~F.text.startswith("/"))
async def wk_sk_text(msg: Message, state: FSMContext):
    await state.update_data(text="" if msg.text.strip() == "-" else msg.html_text.strip(), media=[])
    await state.set_state(WikiSt.sk_media)
    await reply(msg, "({39})Теперь несколько фото или видео этого приёма по одному, затем /done. «-» — без медиа.")


@dp.message(WikiSt.sk_media, F.photo | F.video | F.animation)
async def wk_sk_media(msg: Message, state: FSMContext):
    media = (await state.get_data()).get("media", [])
    media.append(list(wk_media_item(msg)))
    media = media[:WIKI_MAX_MEDIA]
    await state.update_data(media=media)
    await reply(msg, f"({{20}})Принято: {len(media)}/{WIKI_MAX_MEDIA}. Ещё или /done.")


async def wk_sk_finish(msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", data["eid"])
    if not entry:
        return
    skills = json.loads(entry["skills"] or "[]")
    skills.append({"form": data.get("form", 1), "label": data["label"], "text": data.get("text", ""),
                   "media": [{"t": t, "id": i} for t, i in data.get("media", [])]})
    await pool().execute("UPDATE wiki_entries SET skills=$1, updated_at=$2 WHERE id=$3",
                         json.dumps(skills[:WIKI_MAX_SKILLS], ensure_ascii=False), now_ts(), entry["id"])
    entry = await pool().fetchrow("SELECT * FROM wiki_entries WHERE id=$1", entry["id"])
    text, markup = wiki_skills_manager(entry)
    await reply(msg, text, markup)


@dp.message(WikiSt.sk_media, Command("done"))
async def wk_sk_done(msg: Message, state: FSMContext):
    await wk_sk_finish(msg, state)


@dp.message(WikiSt.sk_media, F.text == "-")
async def wk_sk_skip(msg: Message, state: FSMContext):
    await wk_sk_finish(msg, state)


@dp.message(Command("wikilist"))
async def wikilist_cmd(msg: Message):
    if not await redact_zone(msg):
        return
    cat = " ".join(command_args(msg)).strip().lower()
    rows = await pool().fetch("SELECT title, category, obtain, description, photos, videos, skills FROM wiki_entries ORDER BY category, title")
    rows = [r for r in rows if not cat or r["category"].lower() == cat]
    if not rows:
        await reply(msg, "({8})Записей нет.")
        return
    lines, last = [], None
    for r in rows:
        if r["category"] != last:
            lines.append(f"\n<b>{esc(r['category'])}</b>")
            last = r["category"]
        has_media = bool(json.loads(r["photos"] or "[]") or json.loads(r["videos"] or "[]"))
        flags = (("🖼" if has_media else "▫️") + ("🧭" if r["obtain"].strip() else "▫️")
                 + ("📝" if r["description"].strip() else "▫️") + ("⚔️" if json.loads(r["skills"] or "[]") else "▫️"))
        lines.append(f"{flags} {esc(r['title'])}")
    chunk = []
    for line in lines:
        if len("\n".join(chunk + [line])) > 3500:
            await reply(msg, "\n".join(chunk))
            chunk = []
        chunk.append(line)
    header = f"({{39}})<b>Вики: записей {len(rows)}</b> (🖼 медиа • 🧭 как получить • 📝 описание • ⚔️ скиллы)"
    await reply(msg, header + "\n" + "\n".join(chunk))


async def wiki_import(entries: list) -> tuple[int, int, int]:
    """Загрузка из JSON. Поля, которых нет в записи, не трогаются. format: "html" — текст уже с разметкой."""
    added = updated = skipped = 0
    for e_ in entries:
        if not isinstance(e_, dict) or not str(e_.get("title", "")).strip():
            skipped += 1
            continue
        title = str(e_["title"]).strip()[:80]
        old = await pool().fetchrow("SELECT * FROM wiki_entries WHERE norm=$1", wiki_norm(title))
        as_html = str(e_.get("format", "")).lower() == "html"

        def text_of(key: str, current: str) -> str:
            if key not in e_ or not str(e_[key] or "").strip():
                return current  # пустое поле в файле не стирает уже написанный текст
            value = str(e_[key] or "").strip()
            return value if as_html else esc(value)

        aliases = e_["aliases"] if "aliases" in e_ else (json.loads(old["aliases"]) if old else [])
        if isinstance(aliases, str):
            aliases = wiki_split_aliases(aliases)
        if str(e_.get("ru", "")).strip():  # русское название — тоже название для поиска
            aliases = [*aliases, str(e_["ru"]).strip()]
        aliases = list(dict.fromkeys(str(a) for a in aliases))
        photos = e_["photos"] if isinstance(e_.get("photos"), list) else (json.loads(old["photos"]) if old else [])
        videos = None
        if isinstance(e_.get("videos"), list):
            videos = [{"t": str(v.get("t", "video")), "id": str(v["id"])} for v in e_["videos"] if isinstance(v, dict) and v.get("id")]
        skills = None
        if isinstance(e_.get("skills"), list):
            skills = []
            for sk in e_["skills"][:WIKI_MAX_SKILLS]:
                if isinstance(sk, dict) and str(sk.get("label", "")).strip():
                    text = str(sk.get("text", "") or "").strip()
                    skills.append({"form": 2 if int(sk.get("form", 1) or 1) == 2 else 1,
                                   "label": str(sk["label"]).strip()[:40], "text": text if as_html else esc(text),
                                   "media": [{"t": str(m.get("t", "video")), "id": str(m["id"])}
                                             for m in sk.get("media", []) if isinstance(m, dict) and m.get("id")]})
        await wiki_upsert(title, str(e_.get("category") or (old["category"] if old else "Другое"))[:30],
                          [str(a) for a in aliases][:20], text_of("obtain", old["obtain"] if old else ""),
                          text_of("description", old["description"] if old else ""), [str(p) for p in photos][:10],
                          videos, skills,
                          stats=text_of("stats", old["stats"] if old else "") if ("stats" in e_ or old) else "",
                          notes=text_of("notes", old["notes"] if old else "") if ("notes" in e_ or old) else "")
        if old:
            updated += 1
        else:
            added += 1
    return added, updated, skipped


async def wiki_seed_if_empty() -> None:
    """Первый запуск: если база вики пуста и рядом лежит wiki_seed.json — загружаем заготовку (фрукты, аксессуары)."""
    if await pool().fetchval("SELECT COUNT(*) FROM wiki_entries") or not os.path.exists(WIKI_SEED):
        return
    with open(WIKI_SEED, encoding="utf-8") as f:
        added, updated, skipped = await wiki_import(json.load(f))
    LOG.info("wiki: загружена заготовка: %s записей", added + updated)


@dp.message(Command("wikiimport"))
async def wikiimport_cmd(msg: Message, state: FSMContext):
    if not await redact_zone(msg):
        return
    await state.set_state(WikiSt.import_file)
    await reply(msg, "({39})Отправьте файл <b>.json</b> со списком записей (как в /wikiexport). /cancel — отмена.")


@dp.message(WikiSt.import_file, F.document)
async def wiki_import_file(msg: Message, state: FSMContext):
    try:
        file = await B().get_file(msg.document.file_id)
        raw = (await B().download_file(file.file_path)).read()
        entries = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(entries, list):
            raise ValueError("ожидается список записей [ {...}, {...} ]")
    except Exception as exc:
        await reply(msg, f"({{14}})Не удалось прочитать файл: <code>{esc(exc)}</code>")
        return
    await state.clear()
    added, updated, skipped = await wiki_import(entries)
    await reply(msg, f"({{20}})Импорт завершён: добавлено {added}, обновлено {updated}, пропущено {skipped}.")


@dp.message(Command("wikiexport"))
async def wikiexport_cmd(msg: Message):
    if not await redact_zone(msg):
        return
    from aiogram.types import BufferedInputFile
    rows = await pool().fetch("SELECT * FROM wiki_entries ORDER BY category, title")
    out = [{"title": r["title"], "category": r["category"], "aliases": json.loads(r["aliases"] or "[]"),
            "obtain": r["obtain"], "description": r["description"], "photos": json.loads(r["photos"] or "[]"),
            "stats": r["stats"], "notes": r["notes"],
            "videos": json.loads(r["videos"] or "[]"), "skills": json.loads(r["skills"] or "[]"),
            "format": "html"} for r in rows]
    data = json.dumps(out, ensure_ascii=False, indent=1).encode("utf-8")
    await B().send_document(msg.chat.id, BufferedInputFile(data, filename="wiki_export.json"),
                            caption=f"Записей: {len(out)}. Текст в формате html (Premium Emoji и цитаты сохранены).",
                            **({"message_thread_id": topic_of(msg)} if topic_of(msg) else {}))


# ============================ НАБОР В АДМИНИСТРАЦИЮ ============================
SEARCH_SECONDS = env_int("SEARCH_QUESTION_SECONDS", 60)       # на каждый опрос
SEARCH_OPEN_SECONDS = env_int("SEARCH_OPEN_SECONDS", SEARCH_SECONDS)  # на развёрнутый вопрос
SEARCH_MAX_QUESTIONS = 30
_tests: dict[int, dict] = {}  # user_id -> идущее прохождение теста (в памяти)


class SearchSt(StatesGroup):
    ct_poll_q = State()
    ct_poll_a = State()
    ct_open_q = State()


def sbtn(text: str, cb: str, style: str | None = None) -> InlineKeyboardButton:
    """Инлайн-кнопка с цветом (style: success — зелёная, danger — красная) и Premium-иконкой из ({N})."""
    b = btn(text, cb)
    kwargs = {"text": b.text, "callback_data": cb}
    if b.icon_custom_emoji_id:
        kwargs["icon_custom_emoji_id"] = b.icon_custom_emoji_id
    if style:
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


async def test_questions() -> list[dict]:
    rows = await pool().fetch("SELECT * FROM admin_test_q ORDER BY pos, id")
    return [{"id": r["id"], "kind": r["kind"], "question": r["question"],
             "options": json.loads(r["options"] or "[]"), "correct": r["correct"]} for r in rows]


def test_summary(qs: list) -> str:
    if not qs:
        return "Вопросов пока нет."
    lines = []
    for i, q in enumerate(qs, 1):
        plain = html.unescape(re.sub(r"<[^>]+>", "", q["question"]))[:50]
        kind = f"опрос, ответов: {len(q['options'])}" if q["kind"] == "poll" else "развёрнутый"
        lines.append(f"{i}. {esc(plain)}… ({kind})")
    return "\n".join(lines)


def createsearch_markup() -> InlineKeyboardMarkup:
    return kb([btn("({39}) Добавить опрос", "ct_add_poll")], [btn("({39}) Добавить развёрнутый вопрос", "ct_add_open")],
              [btn("({14}) Удалить вопрос", "ct_del")], [btn("({39}) Предпросмотр", "ct_view")], [btn("({14}) Закрыть", "ct_close")])


async def createsearch_menu_text() -> str:
    qs = await test_questions()
    polls = sum(1 for q in qs if q["kind"] == "poll")
    return (f"({{61}})<b>Тест для набора в администрацию</b>\n<blockquote>{test_summary(qs)}</blockquote>\n"
            f"Опросов: {polls}, развёрнутых: {len(qs) - polls}. На вопрос — {SEARCH_SECONDS} сек.")


def private_creator(msg: Message) -> bool:
    return msg.chat.type == "private" and bool(msg.from_user) and msg.from_user.id == CREATOR_ID


@dp.message(Command("createsearch"))
async def createsearch_cmd(msg: Message, state: FSMContext):
    if not private_creator(msg):
        await reply(msg, "({15})Эта команда доступна только создателю и только в личке с ботом.")
        return
    await state.clear()
    await say(msg, await createsearch_menu_text(), createsearch_markup())


async def ct_show_menu(msg: Message) -> None:
    await say(msg, await createsearch_menu_text(), createsearch_markup())


@dp.callback_query(F.data == "ct_close")
async def ct_close(cb: CallbackQuery):
    if cb.from_user.id == CREATOR_ID:
        await _delete_quiet(cb.message)
    await cb.answer()


@dp.callback_query(F.data == "ct_add_poll")
async def ct_add_poll(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != CREATOR_ID:
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    if len(await test_questions()) >= SEARCH_MAX_QUESTIONS:
        await cb.answer("Достигнут максимум вопросов.", show_alert=True)
        return
    await state.set_state(SearchSt.ct_poll_q)
    await cb.answer()
    await say(cb, "({39})<b>Опрос</b>\nПришлите <b>вопрос</b> (до 300 символов).\n"
              f"<i>Бот отправит его опросом на {SEARCH_SECONDS} сек: один ответ, ответы перемешиваются. /cancel — отмена.</i>")


@dp.message(SearchSt.ct_poll_q, F.text, ~F.text.startswith("/"))
async def ct_poll_question(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if len(text) > 300:
        await reply(msg, "({8})Слишком длинный вопрос (максимум 300 символов). Сократите и отправьте снова.")
        return
    await state.update_data(q=text)
    await state.set_state(SearchSt.ct_poll_a)
    await reply(msg, "({39})<b>Ответы</b> — каждый с новой строки (от 2 до 10).\n"
                     "<b>Верный ответ отметьте плюсом в начале</b>, например:\n<blockquote>+Выдать варн по пункту 1.2\nПроигнорировать\nПригласить в личку</blockquote>")


@dp.message(SearchSt.ct_poll_a, F.text, ~F.text.startswith("/"))
async def ct_poll_answers(msg: Message, state: FSMContext):
    lines = [ln.strip() for ln in msg.text.split("\n") if ln.strip()]
    correct = [i for i, ln in enumerate(lines) if ln.startswith("+")]
    options = [ln[1:].strip() if ln.startswith("+") else ln for ln in lines]
    if not 2 <= len(options) <= 10:
        await reply(msg, "({8})Нужно от 2 до 10 ответов, каждый с новой строки.")
        return
    if len(correct) != 1:
        await reply(msg, "({8})Отметьте <b>ровно один</b> верный ответ плюсом в начале строки.")
        return
    if any(len(o) > 100 or not o for o in options):
        await reply(msg, "({8})Каждый ответ — от 1 до 100 символов.")
        return
    data = await state.get_data()
    await state.clear()
    pos = int(await pool().fetchval("SELECT COALESCE(MAX(pos), 0) + 1 FROM admin_test_q"))
    await pool().execute("INSERT INTO admin_test_q (pos, kind, question, options, correct) VALUES ($1,'poll',$2,$3,$4)",
                         pos, data["q"], json.dumps(options, ensure_ascii=False), correct[0])
    await reply(msg, "({20})Опрос добавлен.")
    await ct_show_menu(msg)


@dp.callback_query(F.data == "ct_add_open")
async def ct_add_open(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != CREATOR_ID:
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    if len(await test_questions()) >= SEARCH_MAX_QUESTIONS:
        await cb.answer("Достигнут максимум вопросов.", show_alert=True)
        return
    await state.set_state(SearchSt.ct_open_q)
    await cb.answer()
    await say(cb, "({39})<b>Развёрнутый вопрос</b>\nПришлите ситуацию и вопрос одним сообщением: человек должен описать свои действия. "
                  f"Бот скопирует текст как есть (Premium Emoji, цитаты).\n<i>На ответ — {SEARCH_OPEN_SECONDS} сек. /cancel — отмена.</i>")


@dp.message(SearchSt.ct_open_q, F.text, ~F.text.startswith("/"))
async def ct_open_question(msg: Message, state: FSMContext):
    if len(msg.text) > 2500:
        await reply(msg, "({8})Слишком длинно (максимум 2500 символов).")
        return
    await state.clear()
    pos = int(await pool().fetchval("SELECT COALESCE(MAX(pos), 0) + 1 FROM admin_test_q"))
    await pool().execute("INSERT INTO admin_test_q (pos, kind, question, options, correct) VALUES ($1,'open',$2,'[]',NULL)",
                         pos, msg.html_text.strip())
    await reply(msg, "({20})Развёрнутый вопрос добавлен.")
    await ct_show_menu(msg)


@dp.callback_query(F.data == "ct_del")
async def ct_delete_list(cb: CallbackQuery):
    if cb.from_user.id != CREATOR_ID:
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    qs = await test_questions()
    if not qs:
        await cb.answer("Вопросов нет.", show_alert=True)
        return
    rows = [[InlineKeyboardButton(text=f"🗑 {i}. {html.unescape(re.sub(r'<[^>]+>', '', q['question']))[:30]}",
                                  callback_data=f"ct_rm_{q['id']}")] for i, q in enumerate(qs, 1)]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="ct_menu")])
    await cb.answer()
    await edit(cb, "({14})<b>Какой вопрос удалить?</b>", InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("ct_rm_"))
async def ct_remove(cb: CallbackQuery):
    if cb.from_user.id != CREATOR_ID:
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    await pool().execute("DELETE FROM admin_test_q WHERE id=$1", int(cb.data.removeprefix("ct_rm_")))
    await cb.answer("Удалено")
    await edit(cb, await createsearch_menu_text(), createsearch_markup())


@dp.callback_query(F.data == "ct_menu")
async def ct_menu(cb: CallbackQuery):
    if cb.from_user.id == CREATOR_ID:
        await cb.answer()
        await edit(cb, await createsearch_menu_text(), createsearch_markup())


@dp.callback_query(F.data == "ct_view")
async def ct_view(cb: CallbackQuery):
    if cb.from_user.id != CREATOR_ID:
        await cb.answer("⛔ Только создатель.", show_alert=True)
        return
    qs = await test_questions()
    await cb.answer()
    if not qs:
        await say(cb, "({8})Вопросов пока нет.")
        return
    parts = []
    for i, q in enumerate(qs, 1):
        if q["kind"] == "poll":
            opts = "\n".join(f"{'✅' if j == q['correct'] else '▫️'} {esc(o)}" for j, o in enumerate(q["options"]))
            parts.append(f"<b>{i}. Опрос:</b> {esc(q['question'])}\n{opts}")
        else:
            parts.append(f"<b>{i}. Развёрнутый вопрос:</b>\n<blockquote expandable>{q['question']}</blockquote>")
    text = "\n\n".join(parts)
    for chunk in split_html(text, 3500):
        await say(cb, chunk)


# ---------- открыть / закрыть набор ----------
async def current_search():
    sid = await get_config("search_open")
    return await pool().fetchrow("SELECT * FROM admin_search WHERE id=$1 AND closed_at IS NULL", int(sid)) if sid else None


@dp.message(Command("opensearch", "opensearh"))
async def opensearch_cmd(msg: Message):
    if not private_creator(msg):
        await reply(msg, "({15})Эта команда доступна только создателю и только в личке с ботом.")
        return
    if await current_search():
        await say(msg, "({8})Набор уже открыт. Закрыть: /closesearch")
        return
    qs = await test_questions()
    if not qs:
        await say(msg, "({8})Сначала создайте тест: /createsearch")
        return
    sid = await pool().fetchval("INSERT INTO admin_search (opened_at, questions) VALUES ($1,$2) RETURNING id",
                                now_ts(), json.dumps(qs, ensure_ascii=False))
    await set_config("search_open", sid)
    polls = sum(1 for q in qs if q["kind"] == "poll")
    await say(msg, f"({{20}})<b>Набор открыт.</b>\nВопросов: {len(qs)} (опросов: {polls}, развёрнутых: {len(qs) - polls}), "
                   f"на каждый {SEARCH_SECONDS} сек.\nУчастники начинают через кнопку «О наборах в админ». Закрыть досрочно: /closesearch")


@dp.message(Command("closesearch", "closesearh"))
async def closesearch_cmd(msg: Message):
    if not private_creator(msg):
        await reply(msg, "({15})Эта команда доступна только создателю и только в личке с ботом.")
        return
    s = await current_search()
    if not s:
        await say(msg, "({8})Набор сейчас не открыт.")
        return
    await pool().execute("UPDATE admin_search SET closed_at=$2 WHERE id=$1", s["id"], now_ts())
    await set_config("search_open", "")
    done = await pool().fetchval("SELECT COUNT(*) FROM admin_attempt WHERE search_id=$1 AND status='finished'", s["id"])
    await say(msg, f"({{20}})<b>Набор закрыт.</b> Прошли тест: {done}. Кто уже начал — сможет закончить.")


# ---------- прохождение теста ----------
async def search_info(msg: Message) -> None:
    s = await current_search()
    if not s:
        await say(msg, "({61})<b>О наборах в админ</b>\nСейчас набор закрыт. Когда он откроется — бот напишет об этом.")
        return
    qs = json.loads(s["questions"])
    await say(msg, f"({{61}})<b>Набор в администрацию открыт</b>\n<blockquote>Вопросов: {len(qs)}. На каждый — "
                   f"{SEARCH_SECONDS} сек, возвращаться назад нельзя.\nУсловие: ни одного активного варна.\n"
                   "Опросы проверяются автоматически, развёрнутые ответы читает создатель.</blockquote>",
              kb([sbtn("({20}) Пройти тест", "srch_start", "success")]))


async def search_blockers(uid: int, s) -> str | None:
    """Почему человеку нельзя проходить тест (None — можно)."""
    if not s:
        return "Набор сейчас закрыт."
    if uid in _tests:
        return "Вы уже проходите тест."
    if uid == CREATOR_ID or await rank_of(uid) > 0:
        return "Вы уже в администрации."
    if await is_banned(uid):
        return "Вы заблокированы и не можете участвовать в наборе."
    if await pool().fetchval("SELECT COUNT(*) FROM warn_logs WHERE user_id=$1 AND is_active", uid):
        return "У вас есть активный варн. Пройти тест можно только без варнов."
    att = await pool().fetchrow("SELECT status FROM admin_attempt WHERE search_id=$1 AND user_id=$2", s["id"], uid)
    if att and att["status"] != "in_progress":
        return "Вы уже проходили тест в этом наборе."
    return None


@dp.callback_query(F.data == "srch_start")
async def srch_start(cb: CallbackQuery):
    s = await current_search()
    why = await search_blockers(cb.from_user.id, s)
    if why:
        await cb.answer()
        await say(cb, f"({{8}}){why}")
        return
    await cb.answer()
    n = len(json.loads(s["questions"]))
    await edit(cb, f"({{61}})<b>Готовы?</b>\n<blockquote>{n} вопросов, на каждый {SEARCH_SECONDS} сек. Паузы и возврата нет. "
                   "Пока идёт тест, другие кнопки меню не работают.</blockquote>",
               kb([sbtn("({20}) Начать", "srch_go", "success")], [BACK()]))


@dp.callback_query(F.data == "srch_go")
async def srch_go(cb: CallbackQuery):
    uid = cb.from_user.id
    s = await current_search()
    why = await search_blockers(uid, s)
    if why:
        await cb.answer()
        await say(cb, f"({{8}}){why}")
        return
    await cb.answer()
    await _delete_quiet(cb.message)
    row = await pool().fetchrow(
        """INSERT INTO admin_attempt (search_id, user_id, started_at, status) VALUES ($1,$2,$3,'in_progress')
           ON CONFLICT (search_id, user_id) DO UPDATE SET started_at=$3, status='in_progress', answers='[]'
           RETURNING id""", s["id"], uid, now_ts())
    _tests[uid] = {"attempt": row["id"], "mode": None, "event": asyncio.Event(), "poll_id": None, "got": None}
    spawn(run_test(uid, cb.message.chat.id, row["id"], json.loads(s["questions"]), cb.from_user))


async def run_test(uid: int, chat_id: int, attempt_id: int, qs: list, user) -> None:
    ses = _tests[uid]
    answers, sent_ids = [], []
    try:
        for i, q in enumerate(qs, 1):
            ses.update(event=asyncio.Event(), poll_id=None, got=None, mode=q["kind"], order=None)
            if q["kind"] == "poll":
                order = list(range(len(q["options"])))
                random.shuffle(order)  # разный порядок ответов
                ses["order"] = order
                poll = await B().send_poll(chat_id, question=f"{i}/{len(qs)}. {q['question']}"[:300],
                                           options=[q["options"][j][:100] for j in order], is_anonymous=False,
                                           allows_multiple_answers=False, type="regular", open_period=SEARCH_SECONDS)
                ses["poll_id"] = poll.poll.id
                sent_ids.append(poll.message_id)
                limit = SEARCH_SECONDS
            else:
                sent = await B().send_message(chat_id, R(f"{e(61)}<b>Вопрос {i}/{len(qs)} — развёрнутый</b>\n"
                                                         f"<i>Напишите ответ одним сообщением, у вас {SEARCH_OPEN_SECONDS} сек.</i>\n\n{q['question']}"))
                sent_ids.append(sent.message_id)
                limit = SEARCH_OPEN_SECONDS
            try:
                await asyncio.wait_for(ses["event"].wait(), timeout=limit + 4)
            except asyncio.TimeoutError:
                pass
            if q["kind"] == "poll":
                try:
                    await B().stop_poll(chat_id, sent_ids[-1])
                except Exception:
                    pass
                got = ses["got"]
                shown_correct = ses["order"].index(q["correct"])
                chosen = q["options"][ses["order"][got[0]]] if got else None
                answers.append({"kind": "poll", "question": q["question"], "chosen": chosen,
                                "correct": bool(got) and got[0] == shown_correct})
            else:
                answers.append({"kind": "open", "question": q["question"], "text": ses["got"]})
            ses["mode"] = None
        await pool().execute("UPDATE admin_attempt SET status='finished', finished_at=$2, answers=$3 WHERE id=$1",
                             attempt_id, now_ts(), json.dumps(answers, ensure_ascii=False))
        for mid in sent_ids:  # порядок в личке: вопросы теста убираем
            try:
                await B().delete_message(chat_id, mid)
            except Exception:
                pass
        await B().send_message(chat_id, R(f"{e(20)}<b>Тест завершён.</b> Ответы отправлены администрации, результат придёт сюда."))
        await send_search_result(attempt_id, user, answers)
    except Exception:
        LOG.exception("search test failed")
        await pool().execute("UPDATE admin_attempt SET status='in_progress' WHERE id=$1", attempt_id)
        try:
            await B().send_message(chat_id, R("({8})Тест прервался из-за ошибки. Сообщите создателю."))
        except Exception:
            pass
    finally:
        _tests.pop(uid, None)


async def send_search_result(attempt_id: int, user, answers: list) -> None:
    """Всё одним сообщением в админ-чат + кнопки «Принять» / «Отказать»."""
    polls = [a for a in answers if a["kind"] == "poll"]
    right = sum(1 for a in polls if a["correct"])
    wrong_nums = [str(i) for i, a in enumerate(answers, 1) if a["kind"] == "poll" and not a["correct"]]
    opens = [(i, a) for i, a in enumerate(answers, 1) if a["kind"] == "open"]
    head = (f"{e(61)}<b>Заявка в администрацию #{attempt_id}</b>\n{e(44)} {mention(user.id, user.username, user.full_name)}\n"
            f"Опросы: <b>{right}/{len(polls)}</b>" + (f" (ошибки в №{', '.join(wrong_nums)})" if wrong_nums else "") + "\n")
    budget = 3700 - len(head)
    blocks = []
    for i, a in opens:
        situation = html.unescape(re.sub(r"<[^>]+>", "", a["question"]))
        ans = html.unescape(re.sub(r"<[^>]+>", "", a["text"] or "")) if a["text"] else "— нет ответа —"
        blocks.append((i, esc(situation[:200]), ans))
    per = max(150, budget // max(1, len(blocks)) - 120)  # делим место между ответами
    body = "".join(f"\n<b>Вопрос {i}:</b> <i>{sit}…</i>\n<blockquote expandable>{esc(ans[:per])}</blockquote>" for i, sit, ans in blocks)
    markup = InlineKeyboardMarkup(inline_keyboard=[[sbtn("({20}) Принять", f"srch_ok_{attempt_id}", "success"),
                                                    sbtn("({14}) Отказать", f"srch_no_{attempt_id}", "danger")]])
    card = await to_admin_chat("search", head + body, markup)
    if card:
        await pool().execute("UPDATE admin_attempt SET correct=$2, total=$3, admin_chat=$4, admin_msg=$5 WHERE id=$1",
                             attempt_id, right, len(polls), card.chat.id, card.message_id)


@dp.callback_query(F.data.startswith("srch_ok_") | F.data.startswith("srch_no_"))
async def srch_decide(cb: CallbackQuery):
    if cb.from_user.id != CREATOR_ID:
        await cb.answer("⛔ Решение принимает создатель.", show_alert=True)
        return
    accept = cb.data.startswith("srch_ok_")
    att = await pool().fetchrow("SELECT * FROM admin_attempt WHERE id=$1", int(cb.data.rsplit("_", 1)[1]))
    if not att or att["decision"]:
        await cb.answer("Решение уже принято.", show_alert=True)
        return
    await pool().execute("UPDATE admin_attempt SET decision=$2, decided_by=$3, decided_at=$4 WHERE id=$1",
                         att["id"], "accepted" if accept else "declined", cb.from_user.id, now_ts())
    mark = "✅ <b>Принят(а)</b>" if accept else "❌ <b>Отказано</b>"
    try:
        await cb.message.edit_text(R(cb.message.html_text + f"\n\n{mark} — решил(а) {esc(cb.from_user.full_name)}"), reply_markup=None)
    except Exception:
        pass
    await cb.answer("Готово")
    await dm(att["user_id"], (f"{e(20)}<b>Поздравляем!</b> Вы прошли отбор в администрацию HuBBlox. Скоро с вами свяжутся."
                              if accept else
                              f"{e(14)}<b>К сожалению, отбор в администрацию вы не прошли.</b>\nМожно попробовать в следующем наборе."))


@dp.poll_answer()
async def search_poll_answer(pa: PollAnswer):
    ses = _tests.get(pa.user.id)
    if ses and ses.get("mode") == "poll" and ses.get("poll_id") == pa.poll_id and pa.option_ids:
        ses["got"] = list(pa.option_ids)
        ses["event"].set()


async def open_answer_filter(msg: Message):
    if msg.chat.type != "private" or not msg.text or msg.text.startswith("/") or not msg.from_user:
        return False
    ses = _tests.get(msg.from_user.id)
    return bool(ses and ses.get("mode") == "open" and not ses["event"].is_set())


@dp.message(open_answer_filter)
async def search_open_answer(msg: Message):
    ses = _tests[msg.from_user.id]
    ses["got"] = msg.html_text.strip()[:3000]
    ses["event"].set()


# ============================ О БОТЕ ============================
CHANGELOG = [
    ("3.11", "Набор в администрацию: /createsearch, /opensearch, /closesearch, тест опросами и развёрнутыми ответами; правила в Rich-формате; «О боте»."),
    ("3.10", "Меню под строкой ввода (2 страницы), «Мои нарушения» с датами, кнопка «Вики»."),
    ("3.9", "Вики: фото, видео, скиллы (V1/V2), характеристики, русские названия, ссылки между статьями."),
    ("3.8", "Вопрос-ответ: админ берёт вопрос, ответ оформляется цитатой; чистая личка."),
    ("3.6", "Сток одним сообщением на период Normal (Mirage дописывается в него)."),
    ("3.5", "Права админов в /adminpanel, защита апелляций, антиспам, КД на вопросы."),
    ("3.2", "/off для заявок, автозавершение заявок через 24 часа, /adminpanel, антиспам."),
    ("3.1", "Несколько аккаунтов Parse.bot с переключением, уведомления «сток истёк», Magnet."),
]


def about_text() -> str:
    recent = "\n".join(f"<b>v{v}</b> — {esc(t)}" for v, t in CHANGELOG[:3])
    older = "\n".join(f"<b>v{v}</b> — {esc(t)}" for v, t in CHANGELOG[3:])
    return (f"({{61}})<b>DuoSup</b> • версия {BOT_VERSION}\n"
            f"Владелец: @{CREATOR_USERNAME}\nРазработка: Claude (Anthropic) по заданию владельца\n"
            "Технологии: Python, aiogram 3, PostgreSQL, Railway\n\n<b>Что нового</b>\n"
            f"{recent}\n<blockquote expandable>{older}</blockquote>")


@dp.message(Command("about"))
async def about_cmd(msg: Message):
    await say(msg, about_text())


# Автоварн — самым последним: он реагирует на любые групповые сообщения со ссылками.
dp.message.register(autowarn_handler, F.chat.type.in_({"group", "supergroup"}))


# ================================ ЗАПУСК ================================
async def main() -> None:
    global bot, BOT_USERNAME, _stock_task
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в Railway Variables")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задан в Railway Variables")
    try:
        props = DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True)
    except TypeError:  # старая версия aiogram
        props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot = Bot(token=BOT_TOKEN, default=props)
    dp.message.outer_middleware(RememberMiddleware())
    dp.message.outer_middleware(SpamMiddleware())
    dp.callback_query.outer_middleware(RememberMiddleware())
    try:
        await init_db()
        await refresh_icon_cache()
        me = await bot.get_me()
        BOT_USERNAME = me.username or BOT_USERNAME
        await bot.set_my_commands([
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="profile", description="Профиль"),
            BotCommand(command="appeal", description="Подать апелляцию"),
            BotCommand(command="report", description="Репорт (ответом на сообщение)"),
            BotCommand(command="cancel", description="Отменить действие"),
        ])
        if STOCK_ACCOUNTS:
            _stock_task = asyncio.create_task(stock_loop())
        else:
            LOG.info("STOCK_API_URL не задан — автосток выключен (работает ручная команда /stock)")
        spawn(applications_expiry_loop())
        try:
            await wiki_seed_if_empty()
        except Exception:
            LOG.exception("wiki seed failed")
        LOG.info("DuoSup %s запущен как @%s (id=%s)", BOT_VERSION, BOT_USERNAME, me.id)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if db is not None:
            await db.close()
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    asyncio.run(main())
