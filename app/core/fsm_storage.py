import datetime as dt
import json
from collections.abc import Mapping
from typing import Any

import aiosqlite
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType
from aiogram.fsm.state import State


class SQLiteStorage(BaseStorage):
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS fsm_states (
                    bot_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    destiny TEXT NOT NULL,
                    state TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (bot_id, chat_id, user_id, destiny)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS fsm_data (
                    bot_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    destiny TEXT NOT NULL,
                    data TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (bot_id, chat_id, user_id, destiny)
                )
                """
            )
            await db.commit()

    async def close(self) -> None:
        return

    async def get_state(self, key: StorageKey) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT state FROM fsm_states WHERE bot_id = ? AND chat_id = ? AND user_id = ? AND destiny = ?",
                (key.bot_id, key.chat_id, key.user_id, key.destiny),
            )
            row = await cursor.fetchone()
            return row["state"] if row else None

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        if isinstance(state, State):
            value = state.state
        else:
            value = state
        async with aiosqlite.connect(self.path) as db:
            if value is None:
                await db.execute(
                    "DELETE FROM fsm_states WHERE bot_id = ? AND chat_id = ? AND user_id = ? AND destiny = ?",
                    (key.bot_id, key.chat_id, key.user_id, key.destiny),
                )
                await db.commit()
                return
            now = dt.datetime.utcnow().isoformat()
            await db.execute(
                """
                INSERT INTO fsm_states (bot_id, chat_id, user_id, destiny, state, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(bot_id, chat_id, user_id, destiny)
                DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at
                """,
                (key.bot_id, key.chat_id, key.user_id, key.destiny, value, now),
            )
            await db.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT data FROM fsm_data WHERE bot_id = ? AND chat_id = ? AND user_id = ? AND destiny = ?",
                (key.bot_id, key.chat_id, key.user_id, key.destiny),
            )
            row = await cursor.fetchone()
            if not row or row["data"] is None:
                return {}
            try:
                return json.loads(row["data"])
            except Exception:
                return {}

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        async with aiosqlite.connect(self.path) as db:
            if not data:
                await db.execute(
                    "DELETE FROM fsm_data WHERE bot_id = ? AND chat_id = ? AND user_id = ? AND destiny = ?",
                    (key.bot_id, key.chat_id, key.user_id, key.destiny),
                )
                await db.commit()
                return
            now = dt.datetime.utcnow().isoformat()
            payload = json.dumps(dict(data), ensure_ascii=False)
            await db.execute(
                """
                INSERT INTO fsm_data (bot_id, chat_id, user_id, destiny, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(bot_id, chat_id, user_id, destiny)
                DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
                """,
                (key.bot_id, key.chat_id, key.user_id, key.destiny, payload, now),
            )
            await db.commit()
