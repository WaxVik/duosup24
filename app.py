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
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

LOGGER = logging.getLogger(__name__)

# ========================== НАСТРОЙКИ ==========================
# Секреты должны храниться только в Variables сервиса Railway.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Переменная {name} должна быть целым числом") from exc


CREATOR_ID = env_int("CREATOR_ID", 7675985792)
CREATOR_USERNAME = os.getenv("CREATOR_USERNAME", "WaxVik0").lstrip("@").strip()

TOPICS = {
    "mod_chat": env_int("TOPIC_MOD_CHAT", 6),
    "appeals": env_int("TOPIC_APPEALS", 9),
    "modlist": env_int("TOPIC_MODLIST", 10),
    "redact": env_int("TOPIC_REDACT", 8),
    "reports": env_int("TOPIC_REPORTS", 258),
    "announcements": env_int("TOPIC_ANNOUNCEMENTS", 16),
    "rules": env_int("TOPIC_RULES", 6),
    "chat": env_int("TOPIC_CHAT", 7),
    "appeals_hublox": env_int("TOPIC_APPEALS_HUBLOX", 20),
    "welcome": env_int("TOPIC_WELCOME", 1),
    "admin": env_int("TOPIC_ADMIN", 27),
    "raids": env_int("TOPIC_RAIDS", 17),
    "trades": env_int("TOPIC_TRADES", 8),
}
IGNORED_TOPICS = {TOPICS["admin"], TOPICS["appeals_hublox"]}

MSK = timezone(timedelta(hours=3))
MAX_REASON_LENGTH = 500
MAX_RULES_LENGTH = 3500

db: asyncpg.Pool | None = None
bot: Bot | None = None
BOT_USERNAME = "duosup_bot"

warning_record_locks: dict[tuple[int, int], asyncio.Lock] = {}
ban_target_locks: dict[tuple[int, int], asyncio.Lock] = {}

storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ========================== ОБЩИЕ ФУНКЦИИ ==========================
def require_db() -> asyncpg.Pool:
    if db is None:
        raise RuntimeError("База данных ещё не инициализирована")
    return db


def require_bot() -> Bot:
    if bot is None:
        raise RuntimeError("Бот ещё не инициализирован")
    return bot


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def msk_time() -> str:
    return datetime.now(MSK).strftime("%H:%M:%S")


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def user_mention(
    user_id: int, username: str | None = None, name: str | None = None
) -> str:
    if username:
        return f"@{esc(username.lstrip('@'))}"
    label = esc(name or user_id)
    return f'<a href="tg://user?id={user_id}">{label}</a>'


def command_payload(message: Message) -> str:
    text = message.text or ""
    return text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) == 2 else ""


def validate_reason(reason: str) -> str | None:
    reason = reason.strip()
    if not reason:
        return "⚠️ Укажите причину."
    if len(reason) > MAX_REASON_LENGTH:
        return f"⚠️ Причина слишком длинная: максимум {MAX_REASON_LENGTH} символов."
    return None


def message_url(chat_id: int, message_id: int) -> str | None:
    value = str(chat_id)
    if not value.startswith("-100"):
        return None
    return f"https://t.me/c/{value[4:]}/{message_id}"


def appeal_keyboard(violation_number: str, violation_type: str = "warn") -> InlineKeyboardMarkup:
    payload = violation_number.replace("#", "")
    kind = "ban" if violation_type == "ban" else "warn"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Подать апелляцию",
                    url=f"https://t.me/{BOT_USERNAME}?start=appeal_{kind}_{payload}",
                )
            ]
        ]
    )


async def remember_user(user) -> None:
    if user is None or user.is_bot:
        return
    pool = require_db()
    await pool.execute(
        """
        INSERT INTO known_users (user_id, username, full_name, updated_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE
        SET username=EXCLUDED.username,
            full_name=EXCLUDED.full_name,
            updated_at=EXCLUDED.updated_at
        """,
        user.id,
        user.username,
        user.full_name,
        now_ts(),
    )


class RememberUserMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        try:
            await remember_user(user)
        except Exception:
            LOGGER.exception("Не удалось обновить профиль пользователя")
        return await handler(event, data)


dp.message.outer_middleware(RememberUserMiddleware())
dp.callback_query.outer_middleware(RememberUserMiddleware())


# ========================== ИНИЦИАЛИЗАЦИЯ БД ==========================
async def init_db() -> None:
    global db

    db = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )
    pool = require_db()

    statements = [
        "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            warns INT NOT NULL DEFAULT 0 CHECK (warns >= 0),
            banned BOOL NOT NULL DEFAULT FALSE,
            ban_until BIGINT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS warn_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            warn_number TEXT NOT NULL UNIQUE,
            reason TEXT NOT NULL,
            moderator_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            message_id BIGINT,
            created_at BIGINT NOT NULL,
            is_active BOOL NOT NULL DEFAULT TRUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ban_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            ban_number TEXT NOT NULL UNIQUE,
            reason TEXT NOT NULL,
            moderator_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            message_id BIGINT,
            created_at BIGINT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS unban_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            unban_number TEXT NOT NULL UNIQUE,
            moderator_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            message_id BIGINT,
            created_at BIGINT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS unwarn_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            unwarn_number TEXT NOT NULL UNIQUE,
            moderator_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            message_id BIGINT,
            created_at BIGINT NOT NULL
        )
        """,
        "CREATE TABLE IF NOT EXISTS rules (version TEXT PRIMARY KEY, rule_text TEXT NOT NULL, created_at BIGINT NOT NULL)",
        """
        CREATE TABLE IF NOT EXISTS appeals (
            id BIGSERIAL PRIMARY KEY,
            appeal_number TEXT NOT NULL UNIQUE,
            user_id BIGINT NOT NULL,
            username TEXT,
            violation_number TEXT NOT NULL,
            violation_type TEXT NOT NULL DEFAULT 'warn',
            appeal_text TEXT NOT NULL,
            created_at BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )
        """,
        "ALTER TABLE appeals ADD COLUMN IF NOT EXISTS violation_type TEXT NOT NULL DEFAULT 'warn'",
        "CREATE TABLE IF NOT EXISTS appeal_blocks (user_id BIGINT PRIMARY KEY, block_until BIGINT NOT NULL)",
        """
        CREATE TABLE IF NOT EXISTS moderators (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            level INT NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 7),
            role TEXT
        )
        """,
        "CREATE TABLE IF NOT EXISTS templates (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        """
        CREATE TABLE IF NOT EXISTS known_users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            updated_at BIGINT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS known_users_username_lower_idx ON known_users (LOWER(username))",
        """
        CREATE TABLE IF NOT EXISTS reports (
            id BIGSERIAL PRIMARY KEY,
            report_number TEXT NOT NULL UNIQUE,
            reporter_id BIGINT NOT NULL,
            violator_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            reason TEXT NOT NULL,
            created_at BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            reviewed_by BIGINT,
            UNIQUE (chat_id, message_id)
        )
        """,
    ]

    async with pool.acquire() as conn:
        for statement in statements:
            await conn.execute(statement)

        defaults = {
            "welcome_template": "{user}\nДобро пожаловать в HuBBlox!\nПожалуйста, ознакомьтесь с правилами сообщества.",
            "rules_version": "1.0",
        }
        for key, value in defaults.items():
            await conn.execute(
                "INSERT INTO templates (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                key,
                value,
            )

        for counter in (
            "warn_counter",
            "ban_counter",
            "unban_counter",
            "unwarn_counter",
            "appeal_counter",
            "report_counter",
        ):
            await conn.execute(
                "INSERT INTO config (key, value) VALUES ($1, '0') ON CONFLICT (key) DO NOTHING",
                counter,
            )

        for key in ("link_code", "hublox_id", "hubsup_id"):
            await conn.execute(
                "INSERT INTO config (key, value) VALUES ($1, '') ON CONFLICT (key) DO NOTHING",
                key,
            )

        await conn.execute(
            """
            INSERT INTO moderators (user_id, username, level, role)
            VALUES ($1, $2, 7, 'Создатель')
            ON CONFLICT (user_id) DO UPDATE
            SET username=EXCLUDED.username, level=7, role='Создатель'
            """,
            CREATOR_ID,
            CREATOR_USERNAME or None,
        )


async def get_config(key: str) -> str | None:
    row = await require_db().fetchrow("SELECT value FROM config WHERE key=$1", key)
    return row["value"] if row else None


async def set_config(key: str, value: object) -> None:
    await require_db().execute(
        """
        INSERT INTO config (key, value) VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
        """,
        key,
        str(value),
    )


async def get_template(key: str) -> str | None:
    row = await require_db().fetchrow("SELECT value FROM templates WHERE key=$1", key)
    return row["value"] if row else None


async def set_template(key: str, value: str) -> None:
    await require_db().execute(
        """
        INSERT INTO templates (key, value) VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
        """,
        key,
        value,
    )


async def next_number(conn, counter_name: str) -> int:
    value = await conn.fetchval(
        """
        INSERT INTO config (key, value) VALUES ($1, '1')
        ON CONFLICT (key) DO UPDATE
        SET value=(config.value::BIGINT + 1)::TEXT
        RETURNING value::BIGINT
        """,
        counter_name,
    )
    return int(value)


def format_number(number: int) -> str:
    return f"#-{number:05d}"


async def get_user_warns(user_id: int) -> int:
    """Возвращает текущее количество варнов пользователя.

    Основной счётчик хранится в users.warns, потому что именно он
    увеличивается при выдаче варна и сбрасывается при /unwarn и /unban.
    Для совместимости со старыми/частично заполненными данными есть
    безопасный fallback на активные записи warn_logs.
    """
    pool = require_db()
    row = await pool.fetchrow(
        "SELECT warns FROM users WHERE user_id=$1", user_id
    )
    if row is not None and int(row["warns"] or 0) > 0:
        return int(row["warns"])

    active_logs = await pool.fetchval(
        "SELECT COUNT(*) FROM warn_logs WHERE user_id=$1 AND is_active=TRUE",
        user_id,
    )
    return int(active_logs or 0)


async def add_warn(
    user_id: int,
    reason: str,
    moderator_id: int,
    chat_id: int,
    message_id: int | None = None,
) -> tuple[int, str] | None:
    pool = require_db()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO users (user_id, warns, banned)
            VALUES ($1, 1, FALSE)
            ON CONFLICT (user_id) DO UPDATE
            SET warns=users.warns + 1
            WHERE users.banned=FALSE AND users.warns < 4
            RETURNING warns
            """,
            user_id,
        )
        if row is None:
            return None

        new_warns = int(row["warns"])
        warn_number = format_number(await next_number(conn, "warn_counter"))
        await conn.execute(
            """
            INSERT INTO warn_logs
                (user_id, warn_number, reason, moderator_id, chat_id, message_id, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            user_id,
            warn_number,
            reason,
            moderator_id,
            chat_id,
            message_id,
            now_ts(),
        )
        return new_warns, warn_number


async def remove_all_warns(user_id: int) -> None:
    pool = require_db()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
                INSERT INTO users (user_id, warns) VALUES ($1, 0)
                ON CONFLICT (user_id) DO UPDATE SET warns=0
                """,
            user_id,
        )
        await conn.execute(
            "UPDATE warn_logs SET is_active=FALSE WHERE user_id=$1 AND is_active=TRUE",
            user_id,
        )


async def is_banned(user_id: int) -> bool:
    row = await require_db().fetchrow(
        "SELECT banned, ban_until FROM users WHERE user_id=$1",
        user_id,
    )
    if not row:
        return False
    banned = bool(row["banned"])
    until = row["ban_until"]
    if banned and until is not None and now_ts() > int(until):
        await require_db().execute(
            "UPDATE users SET banned=FALSE, ban_until=NULL WHERE user_id=$1",
            user_id,
        )
        return False
    return banned


async def get_moderator_level(user_id: int) -> int:
    value = await require_db().fetchval(
        "SELECT level FROM moderators WHERE user_id=$1",
        user_id,
    )
    return int(value or 0)


def get_role_name(level: int) -> str:
    roles = {
        0: "Участник",
        1: "Младший модератор",
        2: "Модератор",
        3: "Младший администратор",
        4: "Администратор",
        5: "Старший администратор",
        6: "Главный администратор",
        7: "Создатель",
    }
    return roles.get(level, f"Уровень {level}")


def get_admin_title(level: int) -> str:
    # Telegram разрешает не более 16 символов в должности администратора.
    titles = {
        1: "Мл. модератор",
        2: "Модератор",
        3: "Мл. админ",
        4: "Администратор",
        5: "Старший админ",
        6: "Главный админ",
        7: "Создатель",
    }
    return titles[level]


async def set_moderator_level(
    user_id: int, level: int, username: str | None = None
) -> None:
    if level == 0:
        await require_db().execute("DELETE FROM moderators WHERE user_id=$1", user_id)
        return
    await require_db().execute(
        """
        INSERT INTO moderators (user_id, username, level, role)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE
        SET username=EXCLUDED.username, level=EXCLUDED.level, role=EXCLUDED.role
        """,
        user_id,
        username,
        level,
        get_role_name(level),
    )


async def check_permission(user_id: int, min_level: int) -> bool:
    return user_id == CREATOR_ID or await get_moderator_level(user_id) >= min_level


async def can_punish(moderator_id: int, target_id: int):
    mod_level = await get_moderator_level(moderator_id)
    target_level = await get_moderator_level(target_id)
    if moderator_id == CREATOR_ID or mod_level == 7:
        return True, None, mod_level, target_level
    if mod_level < 1:
        return (
            False,
            "⛔ Ваш ранг слишком низок для выдачи наказаний.",
            mod_level,
            target_level,
        )
    if target_level >= mod_level:
        error = (
            "❌ Нельзя применить наказание к пользователю с таким же или более высоким "
            f"рангом: цель — {target_level}, ваш ранг — {mod_level}."
        )
        return False, error, mod_level, target_level
    return True, None, mod_level, target_level


async def resolve_user(message: Message, token: str | None = None):
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        await remember_user(user)
        if user.id == require_bot().id:
            return None, None, None
        return user.id, user.username, user.full_name

    if not token:
        return None, None, None

    token = token.strip()
    pool = require_db()
    if token.startswith("@"): 
        username = token[1:].strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
            return None, None, None

        actor = message.from_user
        actor_id = actor.id if actor else None
        normalized = username.casefold()
        bot_id = require_bot().id

        row = await pool.fetchrow(
            """
            SELECT user_id, username, full_name
            FROM known_users
            WHERE LOWER(TRIM(BOTH '@' FROM username)) = LOWER($1)
              AND user_id <> $2
              AND ($3::BIGINT IS NULL OR user_id <> $3)
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            username,
            bot_id,
            actor_id,
        )
        if row:
            return row["user_id"], row["username"], row["full_name"]

        # Если совпадение есть только с автором команды, разрешаем его
        # лишь для реального текущего username. Дальше обычная проверка
        # команды не даст применить наказание к самому себе.
        if actor and actor.id != bot_id and (actor.username or "").lstrip("@").casefold() == normalized:
            return actor.id, actor.username, actor.full_name

        return None, None, None

    numeric = token.lstrip("-")
    if numeric.isdigit():
        user_id = int(token)
        if user_id == require_bot().id:
            return None, None, None
        row = await pool.fetchrow(
            "SELECT username, full_name FROM known_users WHERE user_id=$1",
            user_id,
        )
        return (
            user_id,
            (row["username"] if row else None),
            (row["full_name"] if row else None),
        )

    return None, None, None


def get_warn_lock(chat_id: int, user_id: int) -> asyncio.Lock:
    return warning_record_locks.setdefault((chat_id, user_id), asyncio.Lock())


def get_ban_lock(chat_id: int, user_id: int) -> asyncio.Lock:
    return ban_target_locks.setdefault((chat_id, user_id), asyncio.Lock())


async def moderation_chat_id(fallback_chat_id: int) -> int:
    configured = await get_config("hublox_id")
    return int(configured) if configured else fallback_chat_id


async def issue_warning(
    chat_id: int,
    user_id: int,
    reason: str,
    admin_id: int,
    source_message_id: int | None = None,
) -> tuple[bool, int | None, str | None, str | None, str | None]:
    """Выдаёт варн и на 4/4 автоматически оформляет вечный бан.

    Возвращает: issued, warn_count, warn_number, action_error, ban_number.
    """
    lock = get_warn_lock(chat_id, user_id)
    async with lock:
        result = await add_warn(
            user_id,
            reason,
            admin_id,
            chat_id,
            source_message_id,
        )
        if result is None:
            return False, None, None, None, None

        warn_count, warn_number = result
        action_error = None
        ban_number = None
        try:
            if warn_count == 2:
                await require_bot().restrict_chat_member(
                    chat_id,
                    user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
            elif warn_count == 3:
                await require_bot().restrict_chat_member(
                    chat_id,
                    user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=datetime.now(timezone.utc) + timedelta(hours=24),
                )
            elif warn_count == 4:
                # Четвёртый варн = автоматический вечный бан.
                await require_bot().ban_chat_member(
                    chat_id, user_id, revoke_messages=True
                )
                pool = require_db()
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute(
                            """
                            INSERT INTO users (user_id, banned, ban_until)
                            VALUES ($1, TRUE, NULL)
                            ON CONFLICT (user_id) DO UPDATE
                            SET banned=TRUE, ban_until=NULL
                            """,
                            user_id,
                        )
                        ban_number = format_number(await next_number(conn, "ban_counter"))
                        await conn.execute(
                            """
                            INSERT INTO ban_logs
                                (user_id, ban_number, reason, moderator_id, chat_id, message_id, created_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            """,
                            user_id,
                            ban_number,
                            "Достигнут лимит варнов (4/4)",
                            admin_id,
                            chat_id,
                            source_message_id,
                            now_ts(),
                        )
        except Exception as exc:
            action_error = str(exc)
            LOGGER.exception("Не удалось применить ступень наказания %s/4", warn_count)

        return True, warn_count, warn_number, action_error, ban_number


async def apply_ban(
    chat_id: int,
    user_id: int,
    reason: str,
    moderator_id: int,
    source_message_id: int | None = None,
):
    lock = get_ban_lock(chat_id, user_id)
    async with lock:
        if await is_banned(user_id):
            return False, None

        await require_bot().ban_chat_member(chat_id, user_id, revoke_messages=True)
        pool = require_db()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO users (user_id, banned, ban_until) VALUES ($1, TRUE, NULL)
                    ON CONFLICT (user_id) DO UPDATE SET banned=TRUE, ban_until=NULL
                    """,
                    user_id,
                )
                ban_number = format_number(await next_number(conn, "ban_counter"))
                await conn.execute(
                    """
                    INSERT INTO ban_logs
                        (user_id, ban_number, reason, moderator_id, chat_id, message_id, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    user_id,
                    ban_number,
                    reason,
                    moderator_id,
                    chat_id,
                    source_message_id,
                    now_ts(),
                )
        return True, ban_number


async def apply_unban(chat_id: int, user_id: int, moderator_id: int):
    lock = get_ban_lock(chat_id, user_id)
    async with lock:
        if not await is_banned(user_id):
            return False, None
        await require_bot().unban_chat_member(chat_id, user_id, only_if_banned=True)
        pool = require_db()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE users SET banned=FALSE, ban_until=NULL, warns=0 WHERE user_id=$1",
                    user_id,
                )
                await conn.execute(
                    "UPDATE warn_logs SET is_active=FALSE WHERE user_id=$1 AND is_active=TRUE",
                    user_id,
                )
                number = format_number(await next_number(conn, "unban_counter"))
                await conn.execute(
                    """
                    INSERT INTO unban_logs
                        (user_id, unban_number, moderator_id, chat_id, message_id, created_at)
                    VALUES ($1, $2, $3, $4, NULL, $5)
                    """,
                    user_id,
                    number,
                    moderator_id,
                    chat_id,
                    now_ts(),
                )
        return True, number


async def clear_restrictions(chat_id: int, user_id: int) -> None:
    bot_instance = require_bot()
    if user_id == bot_instance.id:
        raise RuntimeError("целью оказался сам бот; ограничение не изменено")
    await bot_instance.restrict_chat_member(
        chat_id,
        user_id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_invite_users=True,
        ),
    )


# ========================== СООБЩЕНИЯ И ЛОГИ ==========================
SEPARATOR = "— • — • — • — • — • — • —"


def build_warn_msg(mention: str, warn_count: int, reason: str, warn_number: str) -> str:
    levels = ("предупреждение", "мут на 5 минут", "мут на 24 часа", "бан")
    lines = [
        f" • {index}/4 — {level}{' ⚠️' if index == warn_count else ''}"
        for index, level in enumerate(levels, start=1)
    ]
    return (
        f"⚠️ {mention} получает варн ({warn_count}/4)\n"
        f"Причина: «{esc(reason)}»\n"
        f"{SEPARATOR}\n"
        + "\n".join(lines)
        + f"\n{SEPARATOR}\n"
        f"🆔 {esc(warn_number)}\n"
        "⏳ Апелляцию можно подать в течение 24 часов с момента выдачи.\n"
        f"{SEPARATOR}"
    )


def build_ban_msg(mention: str, reason: str, ban_number: str) -> str:
    return (
        f"🔨 {mention} получает вечный бан\n"
        f"Причина: «{esc(reason)}»\n"
        f"{SEPARATOR}\n"
        f"🆔 {esc(ban_number)}\n"
        "⏳ Апелляцию можно подать в течение 24 часов с момента выдачи.\n"
        f"{SEPARATOR}"
    )


def build_ban_dm_msg(reason: str, ban_number: str) -> str:
    return (
        "🔨 <b>Вам выдан вечный бан</b>\n"
        f"Причина: «{esc(reason)}»\n"
        f"{SEPARATOR}\n"
        f"🆔 {esc(ban_number)}\n"
        "⏳ Апелляцию можно подать в течение 24 часов с момента выдачи.\n"
        f"{SEPARATOR}\n"
        "💬 Если вы считаете бан ошибочным, нажмите кнопку ниже и подайте апелляцию."
    )


async def notify_ban_in_dm(user_id: int, reason: str, ban_number: str) -> None:
    try:
        await require_bot().send_message(
            user_id,
            build_ban_dm_msg(reason, ban_number),
            reply_markup=appeal_keyboard(ban_number, "ban"),
        )
    except Exception:
        # Бот не может написать пользователю первым, если тот не открыл ЛС с ботом
        # или заблокировал его. Бан при этом уже остаётся применённым в чате.
        LOGGER.info("Не удалось отправить ЛС о бане пользователю %s", user_id, exc_info=True)


def build_unwarn_msg(mention: str, unwarn_number: str) -> str:
    return (
        f"💚 С пользователя {mention} сняты все варны (0/4)\n"
        "— • — • — • — • — • — • —\n"
        f"🆔 Номер снятия: {esc(unwarn_number)}\n"
        "— • — • — • — • — • — • —"
    )


async def send_admin_log(
    text: str, source_chat_id: int | None = None, source_message_id: int | None = None
) -> None:
    hubsup = await get_config("hubsup_id")
    if not hubsup:
        return
    keyboard = None
    if source_chat_id is not None and source_message_id is not None:
        url = message_url(source_chat_id, source_message_id)
        if url:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔗 Перейти к сообщению", url=url)]
                ]
            )
    try:
        await require_bot().send_message(
            int(hubsup),
            text,
            message_thread_id=TOPICS["mod_chat"],
            reply_markup=keyboard,
        )
    except Exception:
        LOGGER.exception("Не удалось отправить запись в административный чат")


async def log_forbidden_attempt(
    action: str,
    actor,
    target_id: int,
    target_username: str | None,
    mod_level: int,
    target_level: int,
    error: str,
) -> None:
    hubsup = await get_config("hubsup_id")
    if not hubsup:
        return
    text = (
        f"🚨 <b>Попытка: {esc(action)}</b>\n"
        f"Модератор: {user_mention(actor.id, actor.username, actor.full_name)} (ранг {mod_level})\n"
        f"Цель: {user_mention(target_id, target_username)} (ранг {target_level})\n"
        f"Ошибка: {esc(error)}"
    )
    try:
        await require_bot().send_message(
            int(hubsup),
            text,
            message_thread_id=TOPICS["reports"],
        )
    except Exception:
        LOGGER.exception("Не удалось записать запрещённую попытку")


async def update_admin_list() -> None:
    rows = await require_db().fetch(
        "SELECT user_id, username, level, role FROM moderators WHERE level > 0 ORDER BY level DESC, user_id"
    )
    if not rows:
        text = "👥 Список администраторов пуст."
    else:
        lines = [
            f"{user_mention(row['user_id'], row['username'])} — {esc(row['role'] or get_role_name(row['level']))}"
            for row in rows
        ]
        text = "👥 <b>Состав администрации:</b>\n" + "\n".join(lines)

    for chat_key, topic in (
        ("hubsup_id", TOPICS["modlist"]),
        ("hublox_id", TOPICS["admin"]),
    ):
        chat_id = await get_config(chat_key)
        if not chat_id:
            continue
        message_key = f"adminlist_msg_{chat_key}"
        old_message_id = await get_config(message_key)
        if old_message_id:
            try:
                await require_bot().edit_message_text(
                    text,
                    chat_id=int(chat_id),
                    message_id=int(old_message_id),
                )
                continue
            except Exception as exc:
                if "message is not modified" in str(exc).lower():
                    continue
                LOGGER.warning("Не удалось обновить старый список админов: %s", exc)
        try:
            sent = await require_bot().send_message(
                int(chat_id),
                text,
                message_thread_id=topic,
            )
            await set_config(message_key, sent.message_id)
        except Exception:
            LOGGER.exception(
                "Не удалось опубликовать список администраторов в %s", chat_key
            )


# ========================== FSM ==========================
class AppealState(StatesGroup):
    waiting_text = State()


class RuleState(StatesGroup):
    waiting_text = State()


# ========================== БАЗОВЫЕ КОМАНДЫ ==========================
@dp.message(Command("cancel"))
async def cancel_cmd(msg: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await msg.answer("ℹ️ Сейчас нет незавершённого действия.")
        return
    await state.clear()
    await msg.answer("✅ Действие отменено.")


@dp.message(Command("start"))
async def start_cmd(msg: Message, state: FSMContext):
    payload = command_payload(msg)
    if msg.chat.type == "private" and (payload == "appeal" or payload.startswith("appeal_")):
        expected_violation = None
        expected_type = None
        if payload.startswith("appeal_"):
            raw = payload.removeprefix("appeal_")
            typed_match = re.fullmatch(r"(warn|ban)_(-\d{5})", raw)
            legacy_match = re.fullmatch(r"-\d{5}", raw)
            if typed_match:
                expected_type, raw_number = typed_match.groups()
                expected_violation = f"#{raw_number}"
            elif legacy_match:
                expected_violation = f"#{raw}"
        await appeal_start(msg, state, expected_violation, expected_type)
        return
    await state.clear()
    await msg.answer(
        "👋 <b>Duosup Bot</b>\n\n"
        "Я модерирую сообщество HuBBlox.\n"
        "Для связи чатов создатель использует:\n"
        "• в HuBBlox: /link_hublox\n"
        "• в администрации: /link_hubsup &lt;код&gt;"
    )


def generate_link_code() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "-".join(
        "".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(5)
    )


@dp.message(Command("link_hublox"))
async def link_hublox(msg: Message):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await msg.answer("⛔ Связывать чаты может только создатель.")
        return
    if msg.chat.type not in ("group", "supergroup"):
        await msg.answer("⚠️ Команда работает только в группе.")
        return
    current_main = await get_config("hublox_id")
    current_admin = await get_config("hubsup_id")
    if current_admin:
        await msg.answer("⚠️ Чаты уже связаны.")
        return
    if current_main and int(current_main) != msg.chat.id:
        await msg.answer(
            "⚠️ Основной чат уже выбран. Сначала очистите старую привязку в базе."
        )
        return
    code = generate_link_code()
    await set_config("link_code", code)
    await set_config("hublox_id", msg.chat.id)
    await msg.answer(
        f"🔗 <b>Код:</b>\n<code>{esc(code)}</code>\n\n"
        f"В административном чате выполните:\n<code>/link_hubsup {esc(code)}</code>"
    )


@dp.message(Command("link_hubsup"))
async def link_hubsup(msg: Message):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await msg.answer("⛔ Связывать чаты может только создатель.")
        return
    if msg.chat.type not in ("group", "supergroup"):
        await msg.answer("⚠️ Команда работает только в группе.")
        return
    if await get_config("hubsup_id"):
        await msg.answer("⚠️ Чаты уже связаны.")
        return
    if not await get_config("hublox_id"):
        await msg.answer("⚠️ Сначала выполните /link_hublox в основном чате.")
        return
    code = command_payload(msg).split(maxsplit=1)[0] if command_payload(msg) else ""
    saved = await get_config("link_code")
    if not saved or not secrets.compare_digest(code, saved):
        await msg.answer("❌ Неверный или устаревший код.")
        return
    await set_config("hubsup_id", msg.chat.id)
    await set_config("link_code", "")
    await msg.answer("✅ Административный чат связан с HuBBlox.")
    hublox = await get_config("hublox_id")
    if hublox:
        await require_bot().send_message(
            int(hublox), "🔗 <b>Административный чат связан.</b> Бот готов к работе."
        )
    await update_admin_list()


async def save_rules(text: str, msg: Message) -> None:
    text = text.strip()
    if not text:
        await msg.answer("⚠️ Правила не могут быть пустыми.")
        return
    if len(text) > MAX_RULES_LENGTH:
        await msg.answer(
            f"⚠️ Текст слишком длинный: максимум {MAX_RULES_LENGTH} символов."
        )
        return
    current = await get_template("rules_version") or "1.0"
    try:
        major, minor = map(int, current.split(".", 1))
    except (TypeError, ValueError):
        major, minor = 1, 0
    new_version = f"{major}.{minor + 1}"
    pool = require_db()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
                INSERT INTO templates (key, value) VALUES ('rules_version', $1)
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
                """,
            new_version,
        )
        await conn.execute(
            "INSERT INTO rules (version, rule_text, created_at) VALUES ($1, $2, $3)",
            new_version,
            text,
            now_ts(),
        )
    hublox = await get_config("hublox_id")
    if hublox:
        await require_bot().send_message(
            int(hublox),
            f"📜 <b>Правила сообщества HuBBlox (v{esc(new_version)})</b>\n\n{esc(text)}",
            message_thread_id=TOPICS["rules"],
        )
        for topic in (
            TOPICS["chat"],
            TOPICS["trades"],
            TOPICS["raids"],
            TOPICS["announcements"],
        ):
            try:
                await require_bot().send_message(
                    int(hublox),
                    f"🔔 <b>Обновление правил.</b> Версия {esc(new_version)}. Ознакомьтесь в теме «Правила».",
                    message_thread_id=topic,
                )
            except Exception:
                LOGGER.exception(
                    "Не удалось уведомить тему %s об обновлении правил", topic
                )
    await msg.answer(f"✅ Правила обновлены до версии {esc(new_version)}.")


@dp.message(Command("redactrule"))
async def redact_rule(msg: Message, state: FSMContext):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await msg.answer("⛔ Доступно только создателю.")
        return
    text = command_payload(msg)
    if text:
        await save_rules(text, msg)
        await state.clear()
        return
    await msg.answer("📝 Отправьте полный текст новых правил одним сообщением.")
    await state.set_state(RuleState.waiting_text)


@dp.message(RuleState.waiting_text, F.text)
async def rule_text(msg: Message, state: FSMContext):
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await state.clear()
        return
    await save_rules(msg.text or "", msg)
    await state.clear()


async def sync_telegram_admin(chat_id: int, user_id: int, level: int) -> None:
    is_admin = level > 0
    await require_bot().promote_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        can_manage_chat=is_admin,
        can_delete_messages=is_admin,
        can_restrict_members=is_admin,
        can_invite_users=False,
        can_change_info=False,
        can_pin_messages=False,
        can_promote_members=False,
        can_manage_topics=False,
        can_manage_video_chats=False,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
    )
    if is_admin:
        await require_bot().set_chat_administrator_custom_title(
            chat_id,
            user_id,
            get_admin_title(level),
        )


async def change_mod_level(msg: Message, delta: int) -> None:
    if not msg.from_user or msg.from_user.id != CREATOR_ID:
        await msg.answer("⛔ Изменять ранги может только создатель.")
        return
    payload = command_payload(msg)
    token = payload.split()[0] if payload else None
    target_id, username, full_name = await resolve_user(msg, token)
    if target_id is None:
        await msg.answer(
            "⚠️ Ответьте на сообщение пользователя либо укажите известный боту @username или ID."
        )
        return
    if target_id in (msg.from_user.id, CREATOR_ID):
        await msg.answer("❌ Нельзя изменить ранг создателя.")
        return
    current = await get_moderator_level(target_id)
    new_level = current + delta
    if not 0 <= new_level <= 6:
        await msg.answer("⚠️ Дальше изменить ранг нельзя.")
        return
    await set_moderator_level(target_id, new_level, username)

    failures = []
    for config_key, label in (("hublox_id", "HuBBlox"), ("hubsup_id", "админ-чате")):
        chat_id = await get_config(config_key)
        if not chat_id:
            continue
        try:
            await sync_telegram_admin(int(chat_id), target_id, new_level)
        except Exception as exc:
            LOGGER.exception("Не удалось синхронизировать права в %s", config_key)
            failures.append(f"{label}: {exc}")

    await update_admin_list()
    action = "повышен" if delta > 0 else "понижен"
    mention = user_mention(target_id, username, full_name)
    response = f"✅ {mention} {action} до уровня {new_level} ({esc(get_role_name(new_level))})."
    if failures:
        response += "\n⚠️ Telegram-права синхронизированы не везде:\n" + "\n".join(
            esc(x) for x in failures
        )
    await msg.answer(response)


@dp.message(Command("upmod"))
async def upmod_cmd(msg: Message):
    await change_mod_level(msg, 1)


@dp.message(Command("downmod"))
async def downmod_cmd(msg: Message):
    await change_mod_level(msg, -1)


# ========================== НАКАЗАНИЯ ==========================
async def parse_target_and_reason(msg: Message):
    payload = command_payload(msg)
    if msg.reply_to_message:
        target_id, username, full_name = await resolve_user(msg)
        reason = payload
        return target_id, username, full_name, reason.strip()

    parts = payload.split(maxsplit=1)
    if not parts:
        return None, None, None, ""

    target_token = parts[0].strip()
    reason = parts[1] if len(parts) == 2 else ""

    # Если Telegram прислал target как text_mention, берём настоящий user_id
    # из entity, а не пытаемся угадывать его по username.
    entities = msg.entities or []
    text = msg.text or ""
    offset = text.find(target_token)
    if offset >= 0:
        for entity in entities:
            if getattr(entity, "type", None) == "text_mention" and entity.offset == offset:
                mentioned = getattr(entity, "user", None)
                if mentioned and not mentioned.is_bot and mentioned.id != require_bot().id:
                    await remember_user(mentioned)
                    return mentioned.id, mentioned.username, mentioned.full_name, reason.strip()

    target_id, username, full_name = await resolve_user(msg, target_token)
    return target_id, username, full_name, reason.strip()


@dp.message(Command("warn"))
async def warn_cmd(msg: Message):
    actor = msg.from_user
    if not actor or not await check_permission(actor.id, 4):
        await msg.answer("⛔ Выдавать варны могут только администраторы (ранг 4+).")
        return
    target_id, username, full_name, reason = await parse_target_and_reason(msg)
    if target_id is None:
        await msg.answer(
            "⚠️ Не удалось найти пользователя по @username. Бот может использовать только "
            "username, который уже видел и сохранил, Telegram ID или пользователя из ответа."
        )
        return
    if target_id == actor.id:
        await msg.answer("❌ Нельзя выдать варн самому себе.")
        return
    error = validate_reason(reason)
    if error:
        await msg.answer(error)
        return
    allowed, permission_error, mod_level, target_level = await can_punish(
        actor.id, target_id
    )
    if not allowed:
        await log_forbidden_attempt(
            "выдать варн",
            actor,
            target_id,
            username,
            mod_level,
            target_level,
            permission_error,
        )
        await msg.answer(permission_error)
        return

    target_chat = await moderation_chat_id(msg.chat.id)
    source_id = (
        msg.reply_to_message.message_id
        if msg.reply_to_message and msg.chat.id == target_chat
        else None
    )
    issued, count, number, action_error, ban_number = await issue_warning(
        target_chat,
        target_id,
        reason,
        actor.id,
        source_id,
    )
    if not issued:
        await msg.answer("⚠️ Пользователь уже забанен или имеет 4/4 варна.")
        return
    mention = user_mention(target_id, username, full_name)
    await msg.reply(
        build_warn_msg(mention, count, reason, number),
        reply_markup=None if ban_number else appeal_keyboard(number, "warn"),
    )
    if ban_number:
        auto_ban_reason = "Достигнут лимит варнов (4/4)"
        await msg.reply(
            build_ban_msg(mention, auto_ban_reason, ban_number),
            reply_markup=appeal_keyboard(ban_number, "ban"),
        )
        await notify_ban_in_dm(target_id, auto_ban_reason, ban_number)
        await send_admin_log(
            "◆<b>ВЫДАН БАН ⚠️</b>◆\n"
            f"{SEPARATOR}\n"
            f"Причина: {esc(auto_ban_reason)}\n"
            f"𝐈𝐃: {esc(ban_number)}\n"
            f"Пользователь: {mention}\n"
            f"𝐈𝐃: {target_id}\n"
            f"Кем выдан: {user_mention(actor.id, actor.username, actor.full_name)}\n"
            f"Чат 𝐈𝐃 {target_chat}\n"
            f"Время: {msk_time()} МСК",
            msg.chat.id if source_id else None,
            source_id,
        )
    if action_error:
        await msg.answer(
            "⚠️ Наказание записано, но автоматическое ограничение Telegram не применилось. "
            f"Проверьте права бота. Ошибка: {esc(action_error)}"
        )
    await send_admin_log(
        "◆<b>ВЫДАН ВАРН ⚠️</b>◆\n"
        f"{SEPARATOR}\n"
        f"Причина: {esc(reason)}\n"
        f"𝐈𝐃: {esc(number)}\n"
        f"Пользователь: {mention}\n"
        f"𝐈𝐃: {target_id}\n"
        f"Кем выдан: {user_mention(actor.id, actor.username, actor.full_name)}\n"
        f"Чат 𝐈𝐃 {target_chat}\n"
        f"Время: {msk_time()} МСК",
        msg.chat.id if source_id else None,
        source_id,
    )


@dp.message(Command("ban"))
async def ban_cmd(msg: Message):
    actor = msg.from_user
    if not actor or not await check_permission(actor.id, 6):
        await msg.answer(
            "⛔ Выдавать баны могут только главный администратор и создатель (ранг 6+)."
        )
        return
    target_id, username, full_name, reason = await parse_target_and_reason(msg)
    if target_id is None:
        await msg.answer(
            "⚠️ Ответьте на сообщение пользователя либо укажите известный боту @username или ID."
        )
        return
    if target_id == actor.id:
        await msg.answer("❌ Нельзя забанить самого себя.")
        return
    error = validate_reason(reason)
    if error:
        await msg.answer(error)
        return
    allowed, permission_error, mod_level, target_level = await can_punish(
        actor.id, target_id
    )
    if not allowed:
        await log_forbidden_attempt(
            "выдать бан",
            actor,
            target_id,
            username,
            mod_level,
            target_level,
            permission_error,
        )
        await msg.answer(permission_error)
        return
    target_chat = await moderation_chat_id(msg.chat.id)
    source_id = (
        msg.reply_to_message.message_id
        if msg.reply_to_message and msg.chat.id == target_chat
        else None
    )
    try:
        success, number = await apply_ban(
            target_chat, target_id, reason, actor.id, source_id
        )
    except Exception as exc:
        LOGGER.exception("Ошибка при выдаче бана")
        await msg.answer(f"❌ Telegram не применил бан: {esc(exc)}")
        return
    if not success:
        await msg.answer("⚠️ Пользователь уже забанен.")
        return
    mention = user_mention(target_id, username, full_name)
    await msg.reply(
        build_ban_msg(mention, reason, number), reply_markup=appeal_keyboard(number, "ban")
    )
    await notify_ban_in_dm(target_id, reason, number)
    await send_admin_log(
        "◆<b>ВЫДАН БАН ⚠️</b>◆\n"
        f"{SEPARATOR}\n"
        f"Причина: {esc(reason)}\n"
        f"𝐈𝐃: {esc(number)}\n"
        f"Пользователь: {mention}\n"
        f"𝐈𝐃: {target_id}\n"
        f"Кем выдан: {user_mention(actor.id, actor.username, actor.full_name)}\n"
        f"Чат 𝐈𝐃 {target_chat}\n"
        f"Время: {msk_time()} МСК",
        msg.chat.id if source_id else None,
        source_id,
    )


@dp.message(Command("unwarn"))
async def unwarn_cmd(msg: Message):
    actor = msg.from_user
    if not actor or not await check_permission(actor.id, 6):
        await msg.answer(
            "⛔ Снимать варны могут только главный администратор и создатель (ранг 6+)."
        )
        return
    payload = command_payload(msg)
    token = payload.split()[0] if payload else None

    # Цель определяем одинаково для reply и /unwarn @username/ID.
    # Наличие варнов проверяется отдельно через users.warns + warn_logs.
    target_id, username, full_name = await resolve_user(
        msg, None if msg.reply_to_message else token
    )

    if target_id is None:
        await msg.answer(
            "⚠️ Не удалось найти пользователя. Используйте @username или Telegram ID, известный боту, либо ответьте на его сообщение."
        )
        return
    if target_id == require_bot().id:
        await msg.answer("⚠️ Нельзя снять ограничения с самого бота.")
        return
    allowed, permission_error, mod_level, target_level = await can_punish(
        actor.id, target_id
    )
    if not allowed:
        await log_forbidden_attempt(
            "снять варны",
            actor,
            target_id,
            username,
            mod_level,
            target_level,
            permission_error,
        )
        await msg.answer(permission_error)
        return
    if await get_user_warns(target_id) == 0:
        await msg.answer("⚠️ У пользователя нет активных варнов.")
        return
    target_chat = await moderation_chat_id(msg.chat.id)
    try:
        if not await is_banned(target_id):
            await clear_restrictions(target_chat, target_id)
    except Exception as exc:
        LOGGER.exception("Не удалось снять ограничения Telegram")
        await msg.answer(f"❌ Не удалось снять ограничения Telegram: {esc(exc)}")
        return
    pool = require_db()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE users SET warns=0 WHERE user_id=$1", target_id)
            await conn.execute(
                "UPDATE warn_logs SET is_active=FALSE WHERE user_id=$1 AND is_active=TRUE",
                target_id,
            )
            number = format_number(await next_number(conn, "unwarn_counter"))
            await conn.execute(
                """
                INSERT INTO unwarn_logs
                    (user_id, unwarn_number, moderator_id, chat_id, message_id, created_at)
                VALUES ($1, $2, $3, $4, NULL, $5)
                """,
                target_id,
                number,
                actor.id,
                target_chat,
                now_ts(),
            )
    mention = user_mention(target_id, username, full_name)
    await msg.reply(build_unwarn_msg(mention, number))
    await send_admin_log(
        "◆<b>СНЯТЫ ВСЕ ВАРНЫ 💚</b>◆\n"
        f"{SEPARATOR}\n"
        f"𝐈𝐃: {esc(number)}\n"
        f"Пользователь: {mention}\n"
        f"𝐈𝐃: {target_id}\n"
        f"Кем сняты: {user_mention(actor.id, actor.username, actor.full_name)}\n"
        f"Чат 𝐈𝐃 {target_chat}\n"
        f"Время: {msk_time()} МСК"
    )


@dp.message(Command("unban"))
async def unban_cmd(msg: Message):
    actor = msg.from_user
    if not actor or not await check_permission(actor.id, 6):
        await msg.answer(
            "⛔ Разбанивать могут только главный администратор и создатель (ранг 6+)."
        )
        return
    payload = command_payload(msg)
    token = payload.split()[0] if payload else None
    target_id, username, full_name = await resolve_user(msg, token)
    if target_id is None:
        await msg.answer(
            "⚠️ Ответьте на сообщение пользователя либо укажите известный боту @username или ID."
        )
        return
    if target_id == actor.id:
        await msg.answer("❌ Нельзя разбанить самого себя.")
        return
    allowed, permission_error, mod_level, target_level = await can_punish(
        actor.id, target_id
    )
    if not allowed:
        await log_forbidden_attempt(
            "снять бан",
            actor,
            target_id,
            username,
            mod_level,
            target_level,
            permission_error,
        )
        await msg.answer(permission_error)
        return
    target_chat = await moderation_chat_id(msg.chat.id)
    try:
        success, number = await apply_unban(target_chat, target_id, actor.id)
    except Exception as exc:
        LOGGER.exception("Ошибка при разбане")
        await msg.answer(f"❌ Telegram не снял бан: {esc(exc)}")
        return
    if not success:
        await msg.answer("⚠️ Пользователь не отмечен как забаненный.")
        return
    mention = user_mention(target_id, username, full_name)
    await msg.reply(build_unban_msg(mention, number))
    await send_admin_log(
        "◆<b>СНЯТ БАН 💚</b>◆\n"
        f"{SEPARATOR}\n"
        f"𝐈𝐃: {esc(number)}\n"
        f"Пользователь: {mention}\n"
        f"𝐈𝐃: {target_id}\n"
        f"Кем снят: {user_mention(actor.id, actor.username, actor.full_name)}\n"
        f"Чат 𝐈𝐃 {target_chat}\n"
        f"Время: {msk_time()} МСК"
    )


# ========================== РЕПОРТЫ И СТАТИСТИКА ==========================
@dp.message(Command("report"))
async def report_cmd(msg: Message):
    if (
        not msg.from_user
        or not msg.reply_to_message
        or not msg.reply_to_message.from_user
    ):
        await msg.answer("⚠️ Используйте команду ответом на сообщение нарушителя.")
        return
    reason = command_payload(msg)
    error = validate_reason(reason)
    if error:
        await msg.answer(error)
        return
    reporter = msg.from_user
    violator = msg.reply_to_message.from_user
    if reporter.id == violator.id:
        await msg.answer("❌ Нельзя отправить репорт на самого себя.")
        return
    hubsup = await get_config("hubsup_id")
    if not hubsup:
        await msg.reply("⚠️ Бот не связан с административным чатом.")
        return
    pool = require_db()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                number = format_number(await next_number(conn, "report_counter"))
                await conn.execute(
                    """
                    INSERT INTO reports
                        (report_number, reporter_id, violator_id, chat_id, message_id, reason, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    number,
                    reporter.id,
                    violator.id,
                    msg.chat.id,
                    msg.reply_to_message.message_id,
                    reason,
                    now_ts(),
                )
    except asyncpg.UniqueViolationError:
        await msg.reply("⚠️ На это сообщение уже отправлен репорт.")
        return

    text = (
        f"◆<b>ПОЛУЧЕН РЕПОРТ ⚠️</b>◆\n"
        f"{SEPARATOR}\n"
        f"Причина: {esc(reason)}\n"
        f"𝐈𝐃: {esc(number)}\n"
        f"Пользователь: {user_mention(violator.id, violator.username, violator.full_name)}\n"
        f"𝐈𝐃: {violator.id}\n"
        f"Отправил: {user_mention(reporter.id, reporter.username, reporter.full_name)}\n"
        f"Чат 𝐈𝐃 {msg.chat.id}\n"
        f"Время: {msk_time()} МСК\n"
        f"{SEPARATOR}"
    )
    source_url = message_url(msg.chat.id, msg.reply_to_message.message_id)
    keyboard_rows = []
    if source_url:
        keyboard_rows.append(
            [InlineKeyboardButton(text="🔗 Перейти к сообщению", url=source_url)]
        )
    keyboard_rows.append(
        [InlineKeyboardButton(text="👀 Рассмотреть", callback_data=f"report_take_{number}")]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    try:
        await require_bot().send_message(
            int(hubsup),
            text,
            message_thread_id=TOPICS["reports"],
            reply_markup=keyboard,
        )
    except Exception:
        await pool.execute("DELETE FROM reports WHERE report_number=$1", number)
        LOGGER.exception("Не удалось переслать репорт")
        await msg.reply(
            "❌ Не удалось доставить репорт администрации. Попробуйте позже."
        )
        return
    await msg.reply("✅ Репорт отправлен администрации.")


@dp.callback_query(F.data.startswith("report_"))
async def report_cb(cb: CallbackQuery):
    if not cb.from_user or not await check_permission(cb.from_user.id, 1):
        await cb.answer("⛔ Недостаточно прав.", show_alert=True)
        return

    data = cb.data or ""
    match = re.fullmatch(r"report_(take|finish)_(#-\d{5})", data)
    if not match:
        await cb.answer("Некорректная кнопка репорта.", show_alert=True)
        return
    action, number = match.groups()
    pool = require_db()

    if action == "take":
        row = await pool.fetchrow(
            """
            UPDATE reports
            SET status='reviewing', reviewed_by=$2
            WHERE report_number=$1 AND status='pending'
            RETURNING report_number, chat_id, message_id, reviewed_by
            """,
            number,
            cb.from_user.id,
        )
        if not row:
            current = await pool.fetchrow(
                "SELECT status, reviewed_by, chat_id, message_id FROM reports WHERE report_number=$1",
                number,
            )
            if current and current["status"] == "reviewing":
                reviewer_id = int(current["reviewed_by"]) if current["reviewed_by"] else 0
                await cb.answer(
                    f"Этот репорт уже рассматривает администратор с ID {reviewer_id}.",
                    show_alert=True,
                )
            elif current and current["status"] == "completed":
                await cb.answer("Этот репорт уже завершён.", show_alert=True)
            else:
                await cb.answer("Репорт не найден.", show_alert=True)
            return

        if cb.message:
            source_url = message_url(int(row["chat_id"]), int(row["message_id"]))
            rows = []
            if source_url:
                rows.append([InlineKeyboardButton(text="🔗 Перейти к сообщению", url=source_url)])
            rows.append([InlineKeyboardButton(text="✅ Завершить рассмотрение", callback_data=f"report_finish_{number}")])
            await cb.message.edit_text(
                f"{cb.message.html_text}\n\n👀 <b>Рассматривает:</b> "
                f"{user_mention(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        await cb.answer("Репорт закреплён за вами.")
        return

    row = await pool.fetchrow(
        """
        UPDATE reports
        SET status='completed'
        WHERE report_number=$1 AND status='reviewing' AND reviewed_by=$2
        RETURNING report_number, chat_id, message_id, reviewed_by
        """,
        number,
        cb.from_user.id,
    )
    if not row:
        current = await pool.fetchrow(
            "SELECT status, reviewed_by FROM reports WHERE report_number=$1",
            number,
        )
        if current and current["status"] == "reviewing":
            reviewer_id = int(current["reviewed_by"]) if current["reviewed_by"] else 0
            await cb.answer(
                f"Завершить рассмотрение может только текущий проверяющий (ID {reviewer_id}).",
                show_alert=True,
            )
        elif current and current["status"] == "completed":
            await cb.answer("Репорт уже завершён.", show_alert=True)
        else:
            await cb.answer("Репорт ещё не взят на рассмотрение.", show_alert=True)
        return

    if cb.message:
        source_url = message_url(int(row["chat_id"]), int(row["message_id"]))
        rows = []
        if source_url:
            rows.append([InlineKeyboardButton(text="🔗 Перейти к сообщению", url=source_url)])
        await cb.message.edit_text(
            f"{cb.message.html_text}\n\n"
            f"✅ <b>Рассмотрение завершено.</b>\n"
            f"Рассматривал: {user_mention(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
        )
    await cb.answer("Рассмотрение репорта завершено.")


@dp.message(Command("stats"))
async def stats_cmd(msg: Message):
    if not msg.from_user or not await check_permission(msg.from_user.id, 5):
        await msg.answer("⛔ Недостаточно прав: требуется уровень 5+.")
        return
    pool = require_db()
    (
        warns,
        bans,
        unbans,
        unwarns,
        pending_reports,
        pending_appeals,
    ) = await asyncio.gather(
        pool.fetchval("SELECT COUNT(*) FROM warn_logs WHERE is_active=TRUE"),
        pool.fetchval("SELECT COUNT(*) FROM ban_logs"),
        pool.fetchval("SELECT COUNT(*) FROM unban_logs"),
        pool.fetchval("SELECT COUNT(*) FROM unwarn_logs"),
        pool.fetchval("SELECT COUNT(*) FROM reports WHERE status='pending'"),
        pool.fetchval("SELECT COUNT(*) FROM appeals WHERE status='pending'"),
    )
    await msg.answer(
        "📊 <b>Статистика</b>\n"
        f"Активных варнов: {warns}\nВсего банов: {bans}\n"
        f"Всего разбанов: {unbans}\nВсего снятий варнов: {unwarns}\n"
        f"Ожидают репорты: {pending_reports}\nОжидают апелляции: {pending_appeals}"
    )


# ========================== АПЕЛЛЯЦИИ ==========================
async def get_available_appeals(user_id: int):
    """Возвращает наказания, по которым пользователь ещё может подать апелляцию.

    Срок — 24 часа с момента выдачи. Варн должен быть активным, бан — текущим.
    """
    cutoff = now_ts() - 24 * 60 * 60
    pool = require_db()
    rows = await pool.fetch(
        """
        SELECT warn_number AS violation_number, 'warn' AS violation_type,
               reason, created_at
        FROM warn_logs
        WHERE user_id=$1 AND is_active=TRUE AND created_at >= $2
          AND NOT EXISTS (SELECT 1 FROM users WHERE user_id=$1 AND banned=TRUE)

        UNION ALL

        SELECT b.ban_number AS violation_number, 'ban' AS violation_type,
               b.reason, b.created_at
        FROM ban_logs b
        JOIN users u ON u.user_id=b.user_id
        WHERE b.user_id=$1 AND u.banned=TRUE AND b.created_at >= $2

        ORDER BY created_at DESC
        LIMIT 20
        """,
        user_id,
        cutoff,
    )
    return rows


def available_appeals_keyboard(rows) -> InlineKeyboardMarkup | None:
    buttons = []
    for row in rows:
        kind = str(row["violation_type"])
        label = "🔨 Бан" if kind == "ban" else "⚠️ Варн"
        buttons.append([
            InlineKeyboardButton(
                text=f"📝 {label} {row['violation_number']}",
                url=f"https://t.me/{BOT_USERNAME}?start=appeal_{kind}_{str(row['violation_number']).replace('#', '')}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


async def get_appeal_target(user_id: int, violation_number: str, violation_type: str):
    cutoff = now_ts() - 24 * 60 * 60
    pool = require_db()
    if violation_type == "ban":
        return await pool.fetchrow(
            """
            SELECT ban_number AS violation_number, reason, created_at
            FROM ban_logs
            WHERE ban_number=$1 AND user_id=$2 AND created_at >= $3
              AND EXISTS (SELECT 1 FROM users WHERE user_id=$2 AND banned=TRUE)
            LIMIT 1
            """,
            violation_number, user_id, cutoff,
        )
    return await pool.fetchrow(
        """
        SELECT warn_number AS violation_number, reason, created_at
        FROM warn_logs
        WHERE warn_number=$1 AND user_id=$2 AND is_active=TRUE AND created_at >= $3
        LIMIT 1
        """,
        violation_number, user_id, cutoff,
    )


async def delete_user_message_safely(msg: Message) -> None:
    try:
        await msg.delete()
    except Exception:
        LOGGER.debug("Не удалось удалить сообщение пользователя", exc_info=True)


@dp.message(Command("appeal"))
async def appeal_start(
    msg: Message,
    state: FSMContext,
    expected_violation: str | None = None,
    expected_type: str | None = None,
):
    if msg.chat.type != "private" or not msg.from_user:
        await msg.answer("📝 Используйте /appeal в личных сообщениях бота.")
        return

    user_id = msg.from_user.id
    pool = require_db()
    current_time = now_ts()

    block = await pool.fetchrow(
        "SELECT block_until FROM appeal_blocks WHERE user_id=$1", user_id
    )
    if block and int(block["block_until"]) > current_time:
        until = datetime.fromtimestamp(int(block["block_until"]), MSK).strftime(
            "%d.%m.%Y %H:%M:%S"
        )
        await msg.answer(
            "⛔ <b>Подача апелляций временно заблокирована.</b>\n\n"
            f"Повторить можно после <b>{until} МСК</b>."
        )
        return
    if block:
        await pool.execute("DELETE FROM appeal_blocks WHERE user_id=$1", user_id)

    pending = await pool.fetchval(
        "SELECT COUNT(*) FROM appeals WHERE user_id=$1 AND status='pending'",
        user_id,
    )
    if pending and not expected_violation:
        await msg.answer(
            "⏳ <b>У вас уже есть активная апелляция.</b>\n\n"
            "Дождитесь решения администрации."
        )
        return

    if expected_violation:
        target = await get_appeal_target(user_id, expected_violation, expected_type or "warn")
        if not target:
            await msg.answer(
                "⏰ <b>Срок подачи этой апелляции истёк</b> или наказание уже не является активным.\n\n"
                "Апелляцию можно подать только в течение 24 часов после выдачи наказания."
            )
            return
        await state.update_data(
            appeal_violation=expected_violation,
            appeal_type=expected_type or "warn",
        )
        kind = "бан" if (expected_type or "warn") == "ban" else "варн"
        await msg.answer(
            "📝 <b>Подача апелляции</b>\n\n"
            f"{('🔨' if (expected_type or 'warn') == 'ban' else '⚠️')} Наказание: <b>{kind}</b>\n"
            f"🆔 Номер: <code>{esc(expected_violation)}</code>\n"
            f"📌 Причина: «{esc(target['reason'])}»\n\n"
            "✍️ <b>Как заполнить:</b>\n"
            "Одним сообщением напишите, почему наказание следует отменить.\n"
            "Username указывать не нужно — бот автоматически проверит, что апелляцию подаёт именно владелец наказания.\n\n"
            "⏳ Срок подачи — 24 часа с момента наказания.\n"
            "❤️ Пожалуйста, изложите ситуацию спокойно и по существу."
        )
    else:
        rows = await get_available_appeals(user_id)
        if not rows:
            await state.clear()
            await msg.answer(
                "📭 <b>Доступных апелляций нет.</b>\n\n"
                "Апелляция доступна только на активное наказание, выданное не более 24 часов назад."
            )
            return
        await msg.answer(
            "📝 <b>Ваши доступные апелляции</b>\n\n"
            "Выберите наказание ниже. Апелляцию можно подать только на своё наказание и только в течение 24 часов с момента его выдачи.",
            reply_markup=available_appeals_keyboard(rows),
        )
        await state.clear()
        return

    await state.set_state(AppealState.waiting_text)


@dp.message(AppealState.waiting_text, F.text)
async def appeal_text(msg: Message, state: FSMContext):
    if not msg.from_user:
        await state.clear()
        return

    data = await state.get_data()
    expected_violation = data.get("appeal_violation")
    expected_type = data.get("appeal_type")
    pool = require_db()
    user_id = msg.from_user.id

    if not expected_violation:
        await state.clear()
        await msg.answer(
            "⚠️ Сначала выберите наказание для апелляции через кнопку 📝 или команду /appeal."
        )
        return

    lines = [line.strip() for line in (msg.text or "").splitlines() if line.strip()]
    appeal_body = "\n".join(lines).strip()
    if not appeal_body:
        await msg.answer("✍️ Напишите текст апелляции одним сообщением.")
        return
    if len(appeal_body) > 2000:
        await msg.answer("⚠️ Текст апелляции слишком длинный: максимум 2000 символов.")
        return

    # Повторно проверяем владельца и 24-часовой срок прямо перед созданием записи.
    target = await get_appeal_target(user_id, expected_violation, expected_type or "warn")
    if not target:
        await state.clear()
        await msg.answer(
            "⏰ <b>Апелляцию отправить нельзя.</b>\n\n"
            "Срок 24 часа истёк либо наказание уже не активно."
        )
        return

    # Две попытки подачи за час = текущая заявка не создаётся, сообщение удаляется,
    # после чего включается часовой cooldown.
    one_hour_ago = now_ts() - 3600
    recent_count = await pool.fetchval(
        "SELECT COUNT(*) FROM appeals WHERE user_id=$1 AND created_at>$2",
        user_id,
        one_hour_ago,
    )
    if recent_count >= 1:
        block_until = now_ts() + 3600
        await pool.execute(
            """
            INSERT INTO appeal_blocks (user_id, block_until) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET block_until=EXCLUDED.block_until
            """,
            user_id,
            block_until,
        )
        await delete_user_message_safely(msg)
        await state.clear()
        await msg.answer(
            "🚫 <b>Слишком много попыток подачи апелляции.</b>\n\n"
            "Вторая заявка за час автоматически отменена.\n"
            "⏳ Следующую апелляцию можно подать через 1 час."
        )
        return

    pending = await pool.fetchval(
        "SELECT COUNT(*) FROM appeals WHERE user_id=$1 AND status='pending'",
        user_id,
    )
    if pending:
        await delete_user_message_safely(msg)
        await state.clear()
        await msg.answer(
            "⏳ <b>У вас уже есть активная апелляция.</b>\n\n"
            "Повторная заявка отменена. Дождитесь решения администрации."
        )
        return

    username = f"@{msg.from_user.username}" if msg.from_user.username else None
    async with pool.acquire() as conn:
        async with conn.transaction():
            number = format_number(await next_number(conn, "appeal_counter"))
            await conn.execute(
                """
                INSERT INTO appeals
                    (appeal_number, user_id, username, violation_number, violation_type, appeal_text, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                number,
                user_id,
                username,
                expected_violation,
                expected_type or "warn",
                appeal_body,
                now_ts(),
            )

    await state.clear()
    hubsup = await get_config("hubsup_id")
    if not hubsup:
        await pool.execute("DELETE FROM appeals WHERE appeal_number=$1", number)
        await msg.answer("❌ Административный чат не подключён. Попробуйте позже.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять", callback_data=f"appeal_approve_{number}"
                ),
                InlineKeyboardButton(
                    text="❌ Отказать", callback_data=f"appeal_reject_{number}"
                ),
            ]
        ]
    )
    kind = "бан" if expected_type == "ban" else "варн"
    report = (
        f"📝 <b>Апелляция {esc(number)}</b>\n"
        "— • — • — • — • — • — • —\n"
        f"{('🔨' if expected_type == 'ban' else '⚠️')} Наказание: <b>{kind}</b>\n"
        f"🆔 Номер наказания: <code>{esc(expected_violation)}</code>\n"
        f"👤 Пользователь: {user_mention(user_id, msg.from_user.username, msg.from_user.full_name)}\n"
        f"🆔 Telegram ID: <code>{user_id}</code>\n\n"
        f"💬 {esc(appeal_body)}\n"
        "— • — • — • — • — • — • —"
    )
    try:
        await require_bot().send_message(
            int(hubsup),
            report,
            message_thread_id=TOPICS["appeals"],
            reply_markup=keyboard,
        )
    except Exception:
        await pool.execute("DELETE FROM appeals WHERE appeal_number=$1", number)
        LOGGER.exception("Не удалось доставить апелляцию")
        await msg.answer("❌ Не удалось доставить апелляцию. Попробуйте позже.")
        return
    await msg.answer(
        f"💚 <b>Апелляция {esc(number)} отправлена.</b>\n\n"
        "Ожидайте решения администрации."
    )


async def approve_appeal_punishment(
    user_id: int,
    violation_number: str,
    violation_type: str,
    moderator_id: int,
) -> str:
    """Применяет результат одобренной апелляции к наказанию пользователя."""
    pool = require_db()

    # Старая кнопка апелляции могла не содержать тип наказания.
    if violation_type not in ("warn", "ban"):
        ban_row = await pool.fetchrow(
            "SELECT 1 FROM ban_logs WHERE ban_number=$1 AND user_id=$2 LIMIT 1",
            violation_number,
            user_id,
        )
        warn_row = await pool.fetchrow(
            "SELECT 1 FROM warn_logs WHERE warn_number=$1 AND user_id=$2 LIMIT 1",
            violation_number,
            user_id,
        )
        if ban_row:
            violation_type = "ban"
        elif warn_row:
            violation_type = "warn"
        else:
            raise RuntimeError("наказание для апелляции не найдено")

    if violation_type == "ban":
        rows = await pool.fetch(
            "SELECT DISTINCT chat_id FROM ban_logs WHERE user_id=$1",
            user_id,
        )
        errors = []
        for row in rows:
            chat_id = int(row["chat_id"])
            try:
                await require_bot().unban_chat_member(
                    chat_id, user_id, only_if_banned=True
                )
            except Exception as exc:
                errors.append(f"{chat_id}: {exc}")
                LOGGER.exception(
                    "Не удалось снять бан при принятии апелляции: user=%s chat=%s",
                    user_id,
                    chat_id,
                )

        if errors:
            raise RuntimeError(
                "не удалось снять бан во всех чатах: " + "; ".join(errors)
            )

        await remove_all_warns(user_id)
        await pool.execute(
            """
            INSERT INTO users (user_id, warns, banned, ban_until)
            VALUES ($1, 0, FALSE, NULL)
            ON CONFLICT (user_id) DO UPDATE
            SET banned=FALSE, ban_until=NULL
            """,
            user_id,
        )
        chat_id = int(rows[0]["chat_id"]) if rows else await moderation_chat_id(TOPICS["chat"])
        result = await add_warn(
            user_id,
            "Апелляция по бану одобрена",
            moderator_id,
            chat_id,
            None,
        )
        if result is None:
            raise RuntimeError("не удалось выдать защитный 1-й варн после апелляции")
        return "бан снят, все варны сняты, выдан 1 варн для подстраховки"

    warn_chats = await pool.fetch(
        "SELECT DISTINCT chat_id FROM warn_logs WHERE user_id=$1",
        user_id,
    )
    await remove_all_warns(user_id)

    restriction_errors = []
    for row in warn_chats:
        chat_id = int(row["chat_id"])
        try:
            await clear_restrictions(chat_id, user_id)
        except Exception as exc:
            restriction_errors.append(f"{chat_id}: {exc}")
            LOGGER.exception(
                "Не удалось снять ограничение при принятии апелляции на варн: user=%s chat=%s",
                user_id,
                chat_id,
            )

    if restriction_errors:
        return "все варны сняты, но часть Telegram-ограничений не удалось снять: " + "; ".join(
            restriction_errors
        )
    return "все варны сняты"


@dp.callback_query(F.data.startswith("appeal_"))
async def appeal_cb(cb: CallbackQuery):
    if not cb.from_user or not await check_permission(cb.from_user.id, 1):
        await cb.answer("⛔ Недостаточно прав.", show_alert=True)
        return
    match = re.fullmatch(r"appeal_(approve|reject)_(#-\d{5})", cb.data or "")
    if not match:
        await cb.answer("Некорректная кнопка.", show_alert=True)
        return
    action, number = match.groups()
    status = "approved" if action == "approve" else "rejected"
    approved = status == "approved"
    if approved:
        # Сначала атомарно забираем апелляцию в обработку, чтобы два админа
        # одновременно не выдали два защитных варна/дважды не сняли наказание.
        row = await require_db().fetchrow(
            """
            UPDATE appeals SET status='processing'
            WHERE appeal_number=$1 AND status='pending'
            RETURNING user_id, violation_number, violation_type
            """,
            number,
        )
        if not row:
            await cb.answer("Эта апелляция уже рассматривается или рассмотрена.", show_alert=True)
            return
    else:
        row = await require_db().fetchrow(
            """
            UPDATE appeals SET status='rejected'
            WHERE appeal_number=$1 AND status='pending'
            RETURNING user_id, violation_number, violation_type
            """,
            number,
        )
        if not row:
            await cb.answer("Эта апелляция уже рассматривается или рассмотрена.", show_alert=True)
            return

    action_result = None
    action_error = None
    if approved:
        try:
            action_result = await approve_appeal_punishment(
                int(row["user_id"]),
                str(row["violation_number"]),
                str(row["violation_type"] or "unknown"),
                cb.from_user.id,
            )
            await require_db().execute(
                "UPDATE appeals SET status='approved' WHERE appeal_number=$1 AND status='processing'",
                number,
            )
        except Exception as exc:
            action_error = str(exc)
            LOGGER.exception("Не удалось применить одобренную апелляцию")
            await require_db().execute(
                "UPDATE appeals SET status='pending' WHERE appeal_number=$1 AND status='processing'",
                number,
            )

    try:
        if approved and action_error:
            user_text = (
                "⚠️ Ваша апелляция одобрена, но применить решение полностью не удалось. "
                f"Администратор исправит это вручную. Ошибка: {action_error}"
            )
        elif approved:
            if str(row["violation_type"] or "warn") == "ban":
                user_text = (
                    "💖 <b>Ваша апелляция принята!</b>\n\n"
                    "🔓 Ваш вечный бан снят, а все предыдущие варны аннулированы.\n\n"
                    "⚠️ <b>На вас наложен защитный варн (1/4).</b>\n"
                    "Он выдан автоматически для подстраховки после принятия апелляции.\n\n"
                    "Пожалуйста, соблюдайте правила чата — повторные нарушения снова учитываются.\n"
                    "— • — • — • — • — • — • —"
                )
            else:
                user_text = (
                    "💖 <b>Ваша апелляция принята!</b>\n\n"
                    "✅ Все ваши варны сняты.\n"
                    "📊 Текущее количество варнов: <b>0/4</b>.\n\n"
                    "Спасибо за обращение. Пожалуйста, соблюдайте правила чата.\n"
                    "— • — • — • — • — • — • —"
                )
        else:
            user_text = (
                "❌ <b>Ваша апелляция отклонена.</b>\n\n"
                "Решение администрации остаётся в силе.\n"
                "Если срок апелляции по другому доступному наказанию ещё не истёк, "
                "вы сможете подать отдельную апелляцию.\n"
                "— • — • — • — • — • — • —"
            )
        await require_bot().send_message(int(row["user_id"]), user_text)
    except Exception:
        LOGGER.exception("Не удалось уведомить автора апелляции")
    if cb.message:
        decision = "💖 Одобрено" if approved else "❌ Отказано"
        extra = ""
        if approved and action_result:
            extra = f"\nДействие: {esc(action_result)}"
        if approved and action_error:
            extra = f"\n⚠️ Ошибка применения: {esc(action_error)}"
        await cb.message.edit_text(
            f"{cb.message.html_text}\n\n{decision}: "
            f"{user_mention(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)}"
            f"{extra}"
        )
    await cb.answer("Готово.")


# ========================== АВТОМОДЕРАЦИЯ ==========================
@dp.message(F.new_chat_members)
async def welcome(msg: Message):
    hublox = await get_config("hublox_id")
    if not hublox or msg.chat.id != int(hublox):
        return
    template = (
        await get_template("welcome_template") or "{user}\nДобро пожаловать в HuBBlox!"
    )
    for member in msg.new_chat_members or []:
        if member.id == require_bot().id:
            continue
        await remember_user(member)
        mention = user_mention(member.id, member.username, member.full_name)
        text = (
            template.replace("{user}", mention)
            if "{user}" in template
            else f"{mention}\n{esc(template)}"
        )
        if "{user}" in template:
            before, _, after = template.partition("{user}")
            text = f"{esc(before)}{mention}{esc(after)}"
        await require_bot().send_message(
            msg.chat.id,
            text,
            message_thread_id=TOPICS["welcome"],
        )


@dp.message(lambda message: bool(message.text) and message.text.casefold() == "бот")
async def bot_mention(msg: Message):
    await msg.reply("На месте ✅")


@dp.message(F.text)
async def handle_links(msg: Message):
    if not msg.from_user or msg.message_thread_id in IGNORED_TOPICS:
        return
    hublox = await get_config("hublox_id")
    if not hublox or msg.chat.id != int(hublox):
        return
    if (
        msg.from_user.id == CREATOR_ID
        or await get_moderator_level(msg.from_user.id) > 0
    ):
        return
    if not re.search(r"(?i)\b(?:https?://|www\.)\S+", msg.text or ""):
        if await is_banned(msg.from_user.id):
            try:
                await msg.delete()
            except Exception:
                LOGGER.exception(
                    "Не удалось удалить сообщение забаненного пользователя"
                )
        return

    issued, count, number, action_error, ban_number = await issue_warning(
        msg.chat.id,
        msg.from_user.id,
        "Ссылка",
        require_bot().id,
        msg.message_id,
    )
    if not issued:
        try:
            await msg.delete()
        except Exception:
            LOGGER.exception("Не удалось удалить запрещённую ссылку")
        return
    mention = user_mention(
        msg.from_user.id, msg.from_user.username, msg.from_user.full_name
    )
    try:
        await msg.delete()
    except Exception:
        LOGGER.exception("Не удалось удалить сообщение со ссылкой")
    await require_bot().send_message(
        msg.chat.id,
        build_warn_msg(mention, count, "Ссылка", number),
        message_thread_id=msg.message_thread_id,
        reply_markup=None if ban_number else appeal_keyboard(number, "warn"),
    )
    if ban_number:
        auto_ban_reason = "Достигнут лимит варнов (4/4)"
        await require_bot().send_message(
            msg.chat.id,
            build_ban_msg(mention, auto_ban_reason, ban_number),
            message_thread_id=msg.message_thread_id,
            reply_markup=appeal_keyboard(ban_number, "ban"),
        )
        await notify_ban_in_dm(msg.from_user.id, auto_ban_reason, ban_number)
        await send_admin_log(
            "◆<b>ВЫДАН БАН ⚠️</b>◆\n"
            f"{SEPARATOR}\n"
            f"Причина: {esc(auto_ban_reason)}\n"
            f"𝐈𝐃: {esc(ban_number)}\n"
            f"Пользователь: {mention}\n"
            f"𝐈𝐃: {msg.from_user.id}\n"
            "Кем выдан: DuoSup\n"
            f"Чат 𝐈𝐃 {msg.chat.id}\n"
            f"Время: {msk_time()} МСК",
            msg.chat.id,
            msg.message_id,
        )
    if action_error:
        await send_admin_log(
            f"⚠️ Варн {esc(number)} записан, но наказание Telegram не применилось: {esc(action_error)}"
        )
    await send_admin_log(
        "◆<b>ВЫДАН ВАРН АВТОМАТИЧЕСКИ ⚠️</b>◆\n"
        f"{SEPARATOR}\n"
        "Причина: Ссылка\n"
        f"𝐈𝐃: {esc(number)}\n"
        f"Пользователь: {mention}\n"
        f"𝐈𝐃: {msg.from_user.id}\n"
        f"Кем выдан: DuoSup\n"
        f"Чат 𝐈𝐃 {msg.chat.id}\n"
        f"Время: {msk_time()} МСК",
        msg.chat.id,
        msg.message_id,
    )


# ========================== ЗАПУСК ==========================
def validate_environment() -> None:
    missing = [
        name
        for name, value in (("BOT_TOKEN", BOT_TOKEN), ("DATABASE_URL", DATABASE_URL))
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Не заданы обязательные Railway Variables: " + ", ".join(missing)
        )
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", BOT_TOKEN):
        raise RuntimeError("BOT_TOKEN имеет неверный формат")
    if not DATABASE_URL.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL должна быть строкой подключения PostgreSQL")


async def main() -> None:
    global bot, BOT_USERNAME
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    validate_environment()
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await init_db()
        me = await bot.get_me()
        BOT_USERNAME = me.username or BOT_USERNAME
        try:
            await update_admin_list()
        except Exception:
            LOGGER.exception("Стартовое обновление списка администраторов не удалось")
        await bot.delete_webhook(drop_pending_updates=False)
        LOGGER.info("Duosup @%s запущен", BOT_USERNAME)
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            tasks_concurrency_limit=100,
            close_bot_session=False,
        )
    finally:
        if db is not None:
            await db.close()
        if bot is not None:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
