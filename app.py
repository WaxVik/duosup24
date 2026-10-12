# -*- coding: utf-8 -*-
"""
DuoSup — Telegram-бот сообщества HuBBlox (Blox Fruits).
Версия 3.0 — полностью переписанный код.

Переменные Railway: BOT_TOKEN, DATABASE_URL (обязательные),
CREATOR_ID, CREATOR_USERNAME, TOPIC_* (необязательные).
Структура базы совместима с прежней версией — данные сохраняются.

Как редактировать тексты: в сообщениях и кнопках ({N}) — Premium Emoji по номеру
из словаря PREMIUM_EMOJI. ({1.3.12_2}) — несколько эмодзи: "." = без пробела,
"_" = один пробел. Форматирование пишется обычным HTML: <b> <i> <u> <blockquote>.
"""
import asyncio
import html
import logging
import os
import re
import secrets
import string
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
    Message,
)

LOG = logging.getLogger("duosup")
BOT_VERSION = "3.0.0"

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
    # ---- админ-чат ----
    "mod_chat": env_int("TOPIC_MOD_CHAT", 6),          # Чат админов (команды модерации)
    "modlog": env_int("TOPIC_MODLOG", 10),             # Состав + лог варнов/банов/разбанов + эскалации
    "appeals": env_int("TOPIC_APPEALS", 9),
    "questions": env_int("TOPIC_QUESTIONS", 387),
    "reports": env_int("TOPIC_REPORTS", 258),          # только репорты участников
    "redact": env_int("TOPIC_REDACT", 8),              # Редакт (только создатель)
}

LINKS = {
    "trades": "https://t.me/hubblox/8",
    "raids": "https://t.me/hubblox/17",
    "sea": "https://t.me/hubblox/1232",
    "contact": "https://t.me/duosup_bot",
}

MSK = timezone(timedelta(hours=3))
SEP = "•—-—-—-—-<\u2060✧>-—-—-—-—•".replace("<", "&lt;").replace(">", "&gt;")
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
    ("tiger", "Tiger"), ("yeti", "Yeti"), ("kitsune", "Kitsune"), ("control", "Control"),
    ("dragon", "Dragon"),
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


async def reply(msg: Message, text: str, markup=None, **kwargs):
    return await msg.reply(R(text), reply_markup=markup, **kwargs)


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
    if await rank_of(actor) < 1:
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
    if await rank_of(actor) < 1:
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
    if await rank_of(actor) < 2:
        await reply(msg, "({15})У вас недостаточно прав для снятия варнов.")
        return
    count, token, _ = parse_punish(msg, True)
    target = await resolve_target(msg, token)
    if target is None or target == "bot" or not count:
        await reply(msg, ERR_UNWARN)
        return
    uid, uname, fname = target
    async with lock_for("warn", uid):
        rows = await pool().fetch(
            "SELECT id FROM warn_logs WHERE user_id=$1 AND is_active ORDER BY id DESC LIMIT $2", uid, count)
        if not rows:
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
    if await rank_of(actor) < 2:
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
            await start_verification(msg.chat.id, user)
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
    bot_id = B().id
    new, numbers, ban_no, error = await give_warns(msg.chat.id, user.id, 1, "1.15 Запрещенная ссылка", bot_id, msg.message_id)
    if not numbers:
        return
    m = mention(user.id, user.username, user.full_name)
    await reply(msg, warn_text(m, new, "1.15 Запрещенная ссылка", numbers, None, True),
                appeal_markup([("warn", numbers[0])]))
    await log_action(f"Автоварн {new}/{MAX_WARNS}", bot_id, user.id, user.username, user.full_name,
                     "1.15 Запрещенная ссылка", ", ".join(numbers), msg.chat.id, msg.message_id)
    if ban_no:
        await log_action("Бан (лимит варнов 4/4)", bot_id, user.id, user.username, user.full_name,
                         "Достигнут лимит варнов (4/4)", ban_no, msg.chat.id, msg.message_id)
    if ban_no:
        await say(msg, ban_text(m, "Достигнут лимит варнов (4/4)", ban_no, None), appeal_markup([("ban", ban_no)]))


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
        "SELECT user_id, username, level, role FROM moderators WHERE level>0 ORDER BY level DESC, user_id")
    groups: dict[int, list[str]] = {3: [], 2: [], 1: []}
    for r in rows:
        rank = rank_from_level(int(r["level"]))
        who = mention(r["user_id"], r["username"], None)
        role = f" — {esc(r['role'])}" if r["role"] and rank < 3 else ""
        groups[rank].append(f"{who}{role}")
    out = [f"{e(21)} <b>Состав администрации</b>", SEP]
    if groups[3]:
        out.append(f"{e(29)} <b>Создатель</b>\n" + "\n".join(groups[3]))
    if groups[2]:
        out.append(f"{e(28)} <b>Главные админы</b>\n" + "\n".join(groups[2]))
    if groups[1]:
        out.append(f"{e(45)} <b>Админы</b>\n" + "\n".join(groups[1]))
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
           role=COALESCE(NULLIF(moderators.role,''), $4)""",
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
    uid, uname, _ = target
    if uid == CREATOR_ID:
        await reply(msg, "({14})Ранг создателя изменить нельзя.")
        return
    new = max(0, min(2, await rank_of(uid) + delta))
    await set_rank(uid, uname, new)
    await reply(msg, f"({{20}}){mention(uid, uname, None)} — теперь: <b>{RANK_NAMES[new]}</b>")
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


async def start_verification(chat_id: int, user) -> None:
    """Блокирует писать и показывает кнопку «Я не бот» (не чаще раза в 2 минуты на человека)."""
    import time
    if time.time() - _last_prompt.get(user.id, 0) < 120:
        return
    _last_prompt[user.id] = time.time()
    try:
        await B().restrict_chat_member(chat_id, user.id, permissions=ChatPermissions(can_send_messages=False))
    except Exception:
        pass
    await pool().execute(
        "INSERT INTO captcha_pending (user_id, chat_id, joined_at) VALUES ($1,$2,$3) "
        "ON CONFLICT (user_id) DO UPDATE SET chat_id=$2, joined_at=$3", user.id, chat_id, now_ts())
    m = mention(user.id, user.username, user.full_name)
    text = (f"👋 Добро пожаловать, {m}!\nРады видеть вас в нашем сообществе.\n"
            "Пожалуйста, подтвердите свой профиль.")
    try:
        await B().send_message(chat_id, R(text), message_thread_id=thread(TOPICS["welcome"]),
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
        if row and await rank_of(user.id) > 0:
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
    try:
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
    if not msg.from_user or await rank_of(msg.from_user.id) < 2:
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


def main_menu() -> InlineKeyboardMarkup:
    return kb(
        [btn("({72}) Ивенты", "menu_events")],
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


def back_only() -> InlineKeyboardMarkup:
    return kb([BACK()])


async def private_only(target) -> bool:
    msg = target.message if isinstance(target, CallbackQuery) else target
    if msg.chat.type == "private":
        return True
    if isinstance(target, CallbackQuery):
        await target.answer("Откройте бота в личных сообщениях.", show_alert=True)
    else:
        await reply(msg, "({8})Эта команда работает только в личных сообщениях с ботом.")
    return False


def json_payload(value) -> dict:
    if isinstance(value, str):
        return json.loads(value or "{}")
    return dict(value or {})


# ---------------------------- /start, /cancel ----------------------------
@dp.message(Command("start"))
async def start_cmd(msg: Message, state: FSMContext):
    if msg.chat.type != "private":
        await reply(msg, "({8})Команда /start работает только в личных сообщениях бота.")
        return
    await state.clear()
    args = command_args(msg)
    payload = args[0] if args else ""
    m = re.fullmatch(r"appeal_(warn|ban)_(-\d{5})", payload)
    if m:
        await begin_appeal(msg, state, msg.from_user.id, m.group(1), "#" + m.group(2))
        return
    await say(msg, MAIN_TEXT, main_menu())
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
    await edit(cb, MAIN_TEXT, main_menu())


@dp.callback_query(F.data == "menu_events")
async def menu_events(cb: CallbackQuery):
    await edit(cb, "({72})<b>Ивенты</b>\nСкоро здесь появится новая функция.", back_only())


@dp.callback_query(F.data == "menu_nav")
async def menu_nav(cb: CallbackQuery):
    rules = await pool().fetchval("SELECT rule_text FROM rules ORDER BY created_at DESC LIMIT 1")
    text = (f"({{61}})<b>Навигация и правила</b>\n"
            f"• {link('Рейды', LINKS['raids'])}\n• {link('Трейды', LINKS['trades'])}\n"
            f"• {link('Морские ивенты', LINKS['sea'])}\n• {link('Триалы', LINKS['trials'])}\n")
    if rules:
        text += f"\n<blockquote>{esc(rules)}</blockquote>"
    else:
        text += "\nПравила сообщества опубликованы в теме «Правила»."
    await edit(cb, text, back_only())


async def publish_rules(version: str, text: str) -> None:
    """Правила -> тема «Правила», оповещение -> тема «Оповещения»."""
    chat_id = await main_chat()
    if not chat_id:
        return
    body = R(f"{e(61)} <b>Правила сообщества HuBBlox</b> • v{esc(version)}\n{SEP}\n{esc(text)}")
    posted = None
    saved = await get_config("rules_msg_id")
    if saved:
        try:
            await B().edit_message_text(body, chat_id=chat_id, message_id=int(saved))
            posted = int(saved)
        except Exception as exc:
            if "not modified" in str(exc).lower():
                posted = int(saved)
    try:
        if not posted:
            sent = await B().send_message(chat_id, body, message_thread_id=thread(TOPICS["rules"]))
            posted = sent.message_id
            await set_config("rules_msg_id", posted)
        url = msg_url(chat_id, posted)
        await B().send_message(chat_id, R(f"{e(26)} <b>Правила обновлены</b> (версия {esc(version)})\nОзнакомьтесь с изменениями."),
                               message_thread_id=thread(TOPICS["announce"]),
                               reply_markup=kb([btn("({26}) Открыть правила", url=url)]) if url else None)
    except Exception:
        LOG.exception("publish_rules failed")


@dp.message(Command("setrules"))
async def setrules_cmd(msg: Message, state: FSMContext):
    if not await redact_zone(msg):
        return
    await state.set_state(RulesSt.text)
    await reply(msg, "({24})Отправьте новый текст правил одним сообщением.\n<i>Отмена: /cancel</i>")


@dp.message(RulesSt.text, F.text, ~F.text.startswith("/"))
async def setrules_text(msg: Message, state: FSMContext):
    await state.clear()
    version = str(1 + int(await pool().fetchval("SELECT COUNT(*) FROM rules") or 0))
    await pool().execute("INSERT INTO rules (version, rule_text, created_at) VALUES ($1,$2,$3)",
                         version, msg.text.strip()[:3500], now_ts())
    await reply(msg, f"({{20}})Правила обновлены (версия {version}).")
    await publish_rules(version, msg.text.strip()[:3500])


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
           AND warn_number NOT IN (SELECT violation_number FROM appeals WHERE user_id=$1 AND violation_type='warn')
           ORDER BY id""", user_id, since)
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
    row = await pool().fetchrow(f"SELECT user_id, created_at FROM {table} WHERE {col}=$1", number)
    if not row or row["user_id"] != user_id:
        await say(msg, "({15})Это наказание выдано не вам.")
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
    if await rank_of(cb.from_user.id) < 2:
        await cb.answer("⛔ Апелляции рассматривают главные админы и создатель.", show_alert=True)
        return
    _, verdict, appeal_id = cb.data.split("_")
    async with lock_for("appeal", int(appeal_id)):
        ap = await pool().fetchrow("SELECT * FROM appeals WHERE id=$1", int(appeal_id))
        if not ap or ap["status"] != "pending":
            await cb.answer("Апелляция уже рассмотрена.", show_alert=True)
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
    if await rank_of(cb.from_user.id) < 1:
        await cb.answer("⛔ Недостаточно прав.", show_alert=True)
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
@dp.callback_query(F.data == "menu_question")
async def menu_question(cb: CallbackQuery, state: FSMContext):
    await state.set_state(QuestionSt.text)
    await edit(cb, "({60})<b>Вопрос | ответ</b>\nНапишите ваш вопрос одним сообщением.", back_only())


@dp.message(QuestionSt.text, F.text, ~F.text.startswith("/"))
async def question_text(msg: Message, state: FSMContext):
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
    card = (f"{e(60)}<b>Новый вопрос {number}</b>\n{e(44)} {mention(user.id, user.username, user.full_name)}\n"
            f"{e(46)} Вопрос:\n<blockquote>«{esc(text)}»</blockquote>")
    await to_admin_chat("questions", card, kb([btn("({60}) Ответить", f"qans_{qid}")]))
    await reply(msg, f"{e(17)}<b>Вопрос отправлен администрации.</b>\nОжидайте ответа в личных сообщениях бота.", main_menu())


@dp.callback_query(F.data.startswith("qans_"))
async def question_answer_start(cb: CallbackQuery, state: FSMContext):
    if await rank_of(cb.from_user.id) < 2:
        await cb.answer("⛔ На вопросы отвечают главные админы и создатель.", show_alert=True)
        return
    qid = int(cb.data.split("_")[1])
    q = await pool().fetchrow("SELECT * FROM questions WHERE id=$1", qid)
    if not q or q["status"] != "pending":
        await cb.answer("На этот вопрос уже ответили.", show_alert=True)
        return
    await state.set_state(AnswerSt.text)
    await state.update_data(qid=qid, card_chat=cb.message.chat.id, card_id=cb.message.message_id,
                            card_html=cb.message.html_text)
    await cb.message.reply(R(f"({{24}})Напишите ответ на вопрос {q['question_number']} следующим сообщением.\n<i>Отмена: /cancel</i>"))
    await cb.answer()


@dp.message(AnswerSt.text, F.text, ~F.text.startswith("/"))
async def question_answer_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    q = await pool().fetchrow("SELECT * FROM questions WHERE id=$1", data["qid"])
    await state.clear()
    if not q or q["status"] != "pending":
        await reply(msg, "({8})На этот вопрос уже ответили.")
        return
    answer = msg.text.strip()[:2000]
    await pool().execute("UPDATE questions SET status='answered', answered_by=$2, answer_text=$3 WHERE id=$1",
                         q["id"], msg.from_user.id, answer)
    sent = await dm(q["user_id"], f"{e(60)}<b>Ответ на ваш вопрос {q['question_number']}</b>\n"
                                  f"<blockquote>{esc(answer)}</blockquote>")
    mod = mention(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    try:
        await B().edit_message_text(data["card_html"] + f"\n\n{e(20)} <b>Отвечено</b> — {mod}",
                                    chat_id=data["card_chat"], message_id=data["card_id"], reply_markup=None)
    except Exception:
        pass
    await reply(msg, "({20})Ответ отправлен." if sent else "({8})Не удалось отправить ответ: пользователь не запускал бота.")


# ============================ PREMIUM EMOJI ============================
def custom_emoji_id_of(msg: Message) -> str | None:
    for ent in (msg.entities or []):
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            return ent.custom_emoji_id
    return None


def emoji_center_markup() -> InlineKeyboardMarkup:
    return kb(
        [InlineKeyboardButton(text="🍎 Эмодзи фруктов", callback_data="em_fruits")],
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
    idx = (await state.get_data()).get("idx", 0)
    key, name = items[idx]
    if (msg.text or "").strip() != "-":
        emoji_id = custom_emoji_id_of(msg)
        if not emoji_id:
            await reply(msg, "({8})Это не Premium Emoji. Отправьте именно премиум-эмодзи или <code>-</code> чтобы пропустить.")
            return
        await set_config(f"custom_emoji_{'fruit' if fruits else 'race'}_{key}", emoji_id)
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
    await cb.answer("Эмодзи фруктов сброшены", show_alert=True)


# =================== ПРИВАТНЫЙ ТЕКСТ БЕЗ СОСТОЯНИЯ ===================
@dp.message(StateFilter(None), F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def private_text(msg: Message):
    row = await user_row(msg.from_user.id)
    if row and row["roblox_prompt_pending"]:
        if await save_roblox(msg):
            await reply(msg, f"({{20}})Ник Roblox сохранён: <b>{esc(msg.text.strip())}</b>", main_menu())
        return
    await say(msg, MAIN_TEXT, main_menu())


# Автоварн — самым последним: он реагирует на любые групповые сообщения со ссылками.
dp.message.register(autowarn_handler, F.chat.type.in_({"group", "supergroup"}))


# ================================ ЗАПУСК ================================
async def main() -> None:
    global bot, BOT_USERNAME
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
    dp.callback_query.outer_middleware(RememberMiddleware())
    try:
        await init_db()
        me = await bot.get_me()
        BOT_USERNAME = me.username or BOT_USERNAME
        await bot.set_my_commands([
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="profile", description="Профиль"),
            BotCommand(command="appeal", description="Подать апелляцию"),
            BotCommand(command="report", description="Репорт (ответом на сообщение)"),
            BotCommand(command="cancel", description="Отменить действие"),
        ])
        LOG.info("DuoSup %s запущен как @%s (id=%s)", BOT_VERSION, BOT_USERNAME, me.id)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if db is not None:
            await db.close()
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    asyncio.run(main())
