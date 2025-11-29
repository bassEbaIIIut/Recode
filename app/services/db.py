import datetime as dt
from typing import Any

import aiosqlite


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    tos_accepted INTEGER NOT NULL DEFAULT 0,
                    group_code TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor = await db.execute("PRAGMA table_info(users)")
            rows = await cursor.fetchall()
            column_names = {row[1] for row in rows}
            if "is_blocked" not in column_names:
                await db.execute(
                    "ALTER TABLE users "
                    "ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0"
                )
            if "schedule_notify_enabled" not in column_names:
                await db.execute(
                    "ALTER TABLE users "
                    "ADD COLUMN schedule_notify_enabled INTEGER NOT NULL DEFAULT 1"
                )
            if "schedule_style" not in column_names:
                await db.execute(
                    "ALTER TABLE users "
                    "ADD COLUMN schedule_style TEXT"
                )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    password TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_login_limits (
                    tg_id INTEGER PRIMARY KEY,
                    attempts_left INTEGER NOT NULL,
                    blocked_until TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS banned_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER,
                    username TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS premium_users (
                    tg_id INTEGER PRIMARY KEY,
                    until TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS stewards (
                    tg_id INTEGER PRIMARY KEY,
                    group_code TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS homework_notifications (
                    tg_id INTEGER PRIMARY KEY,
                    minutes_before INTEGER NOT NULL
                )
                """
            )
            await db.commit()

    async def ensure_user(
        self,
        tg_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO users (
                    tg_id,
                    username,
                    first_name,
                    last_name,
                    tos_accepted,
                    group_code,
                    is_blocked,
                    created_at
                )
                VALUES (?, ?, ?, ?, 0, NULL, 0, ?)
                """,
                (
                    tg_id,
                    username,
                    first_name,
                    last_name,
                    dt.datetime.utcnow().isoformat(),
                ),
            )
            await db.execute(
                """
                UPDATE users
                SET username = ?, first_name = ?, last_name = ?
                WHERE tg_id = ?
                """,
                (
                    username,
                    first_name,
                    last_name,
                    tg_id,
                ),
            )
            await db.commit()

    async def accept_tos(
        self,
        tg_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO users (
                    tg_id,
                    username,
                    first_name,
                    last_name,
                    tos_accepted,
                    group_code,
                    is_blocked,
                    created_at
                )
                VALUES (?, ?, ?, ?, 1, NULL, 0, ?)
                """,
                (
                    tg_id,
                    username,
                    first_name,
                    last_name,
                    dt.datetime.utcnow().isoformat(),
                ),
            )
            await db.execute(
                """
                UPDATE users
                SET tos_accepted = 1,
                    username = ?,
                    first_name = ?,
                    last_name = ?
                WHERE tg_id = ?
                """,
                (
                    username,
                    first_name,
                    last_name,
                    tg_id,
                ),
            )
            await db.commit()

    async def get_user(self, tg_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    id,
                    tg_id,
                    username,
                    first_name,
                    last_name,
                    tos_accepted,
                    group_code,
                    is_blocked,
                    created_at
                FROM users
                WHERE tg_id = ?
                """,
                (tg_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

    async def set_user_group(self, tg_id: int, group_code: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO users (
                    tg_id,
                    username,
                    first_name,
                    last_name,
                    tos_accepted,
                    group_code,
                    is_blocked,
                    created_at
                )
                VALUES (?, NULL, NULL, NULL, 0, ?, 0, ?)
                """,
                (
                    tg_id,
                    group_code,
                    dt.datetime.utcnow().isoformat(),
                ),
            )
            await db.execute(
                "UPDATE users SET group_code = ? WHERE tg_id = ?",
                (group_code, tg_id),
            )
            await db.commit()

    async def set_user_blocked(self, tg_id: int, blocked: bool) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET is_blocked = ? WHERE tg_id = ?",
                (1 if blocked else 0, tg_id),
            )
            await db.commit()

    async def list_users_page(
        self,
        page: int,
        per_page: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT COUNT(*) AS c FROM users")
            row = await cursor.fetchone()
            total = row["c"] if row else 0
            if total == 0:
                return [], 0, 0
            pages = (total + per_page - 1) // per_page
            if page < 1:
                page = 1
            if page > pages:
                page = pages
            offset = (page - 1) * per_page
            cursor = await db.execute(
                """
                SELECT
                    u.id,
                    u.tg_id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    u.group_code,
                    u.is_blocked,
                    EXISTS(
                        SELECT 1
                        FROM admin_sessions s
                        WHERE s.tg_id = u.tg_id
                          AND s.active = 1
                    ) AS is_admin
                FROM users u
                ORDER BY u.id
                LIMIT ? OFFSET ?
                """,
                (per_page, offset),
            )
            rows = await cursor.fetchall()
            users = [dict(r) for r in rows]
            return users, total, pages

    async def get_users_stats(self) -> dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT COUNT(*) AS c FROM users")
            row = await cursor.fetchone()
            total = row["c"] if row else 0
            cursor = await db.execute(
                "SELECT COUNT(*) AS c FROM users WHERE is_blocked = 1"
            )
            row = await cursor.fetchone()
            blocked = row["c"] if row else 0
            cursor = await db.execute(
                "SELECT COUNT(*) AS c FROM users WHERE group_code IS NOT NULL"
            )
            row = await cursor.fetchone()
            with_group = row["c"] if row else 0
            cursor = await db.execute(
                "SELECT COUNT(*) AS c FROM admin_sessions WHERE active = 1"
            )
            row = await cursor.fetchone()
            active_admins = row["c"] if row else 0
            return {
                "total": total,
                "blocked": blocked,
                "with_group": with_group,
                "active_admins": active_admins,
            }

    async def search_users(self, query: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            if query.isdigit():
                cursor = await db.execute(
                    """
                    SELECT
                        u.id,
                        u.tg_id,
                        u.username,
                        u.first_name,
                        u.last_name,
                        u.group_code,
                        u.is_blocked,
                        EXISTS(
                            SELECT 1
                            FROM admin_sessions s
                            WHERE s.tg_id = u.tg_id
                              AND s.active = 1
                        ) AS is_admin
                    FROM users u
                    WHERE u.tg_id = ?
                    ORDER BY u.id
                    """,
                    (int(query),),
                )
            else:
                username = query.lstrip("@").lower()
                cursor = await db.execute(
                    """
                    SELECT
                        u.id,
                        u.tg_id,
                        u.username,
                        u.first_name,
                        u.last_name,
                        u.group_code,
                        u.is_blocked,
                        EXISTS(
                            SELECT 1
                            FROM admin_sessions s
                            WHERE s.tg_id = u.tg_id
                              AND s.active = 1
                        ) AS is_admin
                    FROM users u
                    WHERE LOWER(u.username) LIKE ?
                    ORDER BY u.id
                    """,
                    (username + "%",),
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_active_admin_session_for_user(
        self,
        tg_id: int,
    ) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, tg_id, level, password, active, created_at
                FROM admin_sessions
                WHERE tg_id = ? AND active = 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (tg_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

    async def get_active_admin_session_by_password(
        self,
        password: str,
    ) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, tg_id, level, password, active, created_at
                FROM admin_sessions
                WHERE password = ? AND active = 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (password,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

    async def create_admin_session(
        self,
        tg_id: int,
        level: int,
        password: str,
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            now = dt.datetime.utcnow().isoformat()
            cursor = await db.execute(
                """
                INSERT INTO admin_sessions (
                    tg_id,
                    level,
                    password,
                    active,
                    created_at
                )
                VALUES (?, ?, ?, 1, ?)
                """,
                (tg_id, level, password, now),
            )
            await db.commit()
            return cursor.lastrowid

    async def deactivate_admin_sessions_for_user(self, tg_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE admin_sessions SET active = 0 WHERE tg_id = ? AND active = 1",
                (tg_id,),
            )
            await db.commit()

    async def get_active_admin_sessions_with_users(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    s.id,
                    s.tg_id,
                    s.level,
                    s.password,
                    s.active,
                    s.created_at,
                    u.username,
                    u.first_name,
                    u.last_name
                FROM admin_sessions s
                LEFT JOIN users u ON u.tg_id = s.tg_id
                WHERE s.active = 1
                ORDER BY s.created_at DESC
                """
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_admin_session_by_id(
        self,
        session_id: int,
    ) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, tg_id, level, password, active, created_at
                FROM admin_sessions
                WHERE id = ?
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

    async def deactivate_admin_session_by_id(self, session_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE admin_sessions SET active = 0 WHERE id = ?",
                (session_id,),
            )
            await db.commit()

    async def get_admin_login_limits(
        self,
        tg_id: int,
    ) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT tg_id, attempts_left, blocked_until
                FROM admin_login_limits
                WHERE tg_id = ?
                """,
                (tg_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

    async def set_admin_login_limits(
        self,
        tg_id: int,
        attempts_left: int,
        blocked_until: str | None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO admin_login_limits (tg_id, attempts_left, blocked_until)
                VALUES (?, ?, ?)
                ON CONFLICT(tg_id) DO UPDATE SET
                    attempts_left = excluded.attempts_left,
                    blocked_until = excluded.blocked_until
                """,
                (tg_id, attempts_left, blocked_until),
            )
            await db.commit()

    async def clear_admin_login_limits(self, tg_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM admin_login_limits WHERE tg_id = ?",
                (tg_id,),
            )
            await db.commit()

    async def get_all_users_for_broadcast(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT tg_id, username, is_blocked
                FROM users
                ORDER BY id
                """
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def ban_user(
        self,
        tg_id: int | None,
        username: str | None,
        reason: str,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            username_norm = username.lower() if username else None
            if tg_id is not None:
                await db.execute(
                    "DELETE FROM banned_users WHERE tg_id = ?",
                    (tg_id,),
                )
            if username_norm:
                await db.execute(
                    "DELETE FROM banned_users WHERE LOWER(username) = ?",
                    (username_norm,),
                )
            now = dt.datetime.utcnow().isoformat()
            await db.execute(
                """
                INSERT INTO banned_users (tg_id, username, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (tg_id, username, reason, now),
            )
            await db.commit()

    async def unban_by_tg_id(self, tg_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "DELETE FROM banned_users WHERE tg_id = ?",
                (tg_id,),
            )
            await db.commit()
            return cursor.rowcount

    async def unban_by_username(self, username: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            username_norm = username.lower()
            cursor = await db.execute(
                "DELETE FROM banned_users WHERE LOWER(username) = ?",
                (username_norm,),
            )
            await db.commit()
            return cursor.rowcount

    async def get_banned_users(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, tg_id, username, reason, created_at
                FROM banned_users
                ORDER BY created_at DESC, id DESC
                """
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_ban_for_user(
        self,
        tg_id: int,
        username: str | None,
    ) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            username_norm = username.lower() if username else None
            if username_norm:
                cursor = await db.execute(
                    """
                    SELECT id, tg_id, username, reason, created_at
                    FROM banned_users
                    WHERE tg_id = ? OR LOWER(username) = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    (tg_id, username_norm),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT id, tg_id, username, reason, created_at
                    FROM banned_users
                    WHERE tg_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    (tg_id,),
                )
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

    async def is_user_banned(self, tg_id: int, username: str | None) -> bool:
        entry = await self.get_ban_for_user(tg_id, username)
        return entry is not None

    async def is_user_premium(self, tg_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT until FROM premium_users WHERE tg_id = ?",
                (tg_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return False
            try:
                until = dt.datetime.fromisoformat(row["until"])
            except Exception:
                return False
            return until > dt.datetime.utcnow()

    async def set_user_premium(self, tg_id: int, until: dt.datetime) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO premium_users (tg_id, until)
                VALUES (?, ?)
                ON CONFLICT(tg_id) DO UPDATE SET until = excluded.until
                """,
                (tg_id, until.isoformat()),
            )
            await db.commit()

    async def get_user_premium_until(self, tg_id: int) -> dt.datetime | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT until FROM premium_users WHERE tg_id = ?",
                (tg_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            try:
                until = dt.datetime.fromisoformat(row["until"])
            except Exception:
                return None
            if until <= dt.datetime.utcnow():
                return None
            return until

    async def get_schedule_notify_enabled(self, tg_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT schedule_notify_enabled FROM users WHERE tg_id = ?",
                (tg_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return True
            value = row["schedule_notify_enabled"]
            if value is None:
                return True
            return bool(value)

    async def set_schedule_notify_enabled(self, tg_id: int, enabled: bool) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET schedule_notify_enabled = ? WHERE tg_id = ?",
                (1 if enabled else 0, tg_id),
            )
            await db.commit()

    async def get_schedule_style(self, tg_id: int) -> str:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT schedule_style FROM users WHERE tg_id = ?",
                (tg_id,),
            )
            row = await cursor.fetchone()
            value = row["schedule_style"] if row else None
            if not value:
                return "Обычный"
            return str(value)

    async def set_schedule_style(self, tg_id: int, style: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET schedule_style = ? WHERE tg_id = ?",
                (style, tg_id),
            )
            await db.commit()

    async def get_users_for_schedule_notifications(self, group_code: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT tg_id, username, is_blocked, schedule_notify_enabled
                FROM users
                WHERE group_code = ?
                """,
                (group_code,),
            )
            rows = await cursor.fetchall()
            result: list[dict[str, Any]] = []
            for r in rows:
                item = dict(r)
                tg_id = item.get("tg_id")
                if not tg_id:
                    continue
                if item.get("is_blocked"):
                    continue
                value = item.get("schedule_notify_enabled")
                enabled = True if value is None else bool(value)
                if not enabled:
                    continue
                result.append(item)
            return result

    async def set_steward(self, tg_id: int, group_code: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO stewards (tg_id, group_code)
                VALUES (?, ?)
                ON CONFLICT(tg_id) DO UPDATE SET group_code = excluded.group_code
                """,
                (tg_id, group_code),
            )
            await db.commit()

    async def remove_steward(self, tg_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM stewards WHERE tg_id = ?",
                (tg_id,),
            )
            await db.commit()

    async def get_steward_group(self, tg_id: int) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT group_code FROM stewards WHERE tg_id = ?",
                (tg_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return row["group_code"]

    async def list_stewards(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    s.tg_id,
                    s.group_code,
                    u.username,
                    u.first_name,
                    u.last_name
                FROM stewards s
                LEFT JOIN users u ON u.tg_id = s.tg_id
                ORDER BY s.group_code, s.tg_id
                """
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_homework_notify_minutes(self, tg_id: int) -> int | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT minutes_before FROM homework_notifications WHERE tg_id = ?",
                (tg_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return int(row["minutes_before"])

    async def set_homework_notify_minutes(self, tg_id: int, minutes_before: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO homework_notifications (tg_id, minutes_before)
                VALUES (?, ?)
                ON CONFLICT(tg_id) DO UPDATE SET minutes_before = excluded.minutes_before
                """,
                (tg_id, minutes_before),
            )
            await db.commit()