import asyncio
import datetime as dt
import json
import logging
import re
from pathlib import Path
from typing import Any

from aiogram import Bot

from app.core.context import get_context
from app.services.schedule_service import week_bounds_mon_sun, parse_schedule, normalize_day, day_name_ru

_HEADER_RE = re.compile(r"^\s*(\d+)\s*пара\s*:\s*(.*)$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*[①②•\-]\s*")
_NO_RE = re.compile(r"^(нет|нет пар|—|-)$", re.IGNORECASE)

BASE_DIR = Path(__file__).resolve().parents[2]
TMP_DIR = BASE_DIR / "config"
TMP_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = TMP_DIR / "watchdog_state.json"
SCHEDULE_CACHE_DIR = TMP_DIR / "watchdog_schedule"
OVERLAY_PATH = TMP_DIR / "schedule_overlay.json"
SCHEDULE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _normalize_day_lines(dstr: str, info: Any) -> list[str]:
    _, lines = normalize_day(dstr, info, max_pairs=8, subgroup=None, multiline=False)
    return lines or []


def _parse_slots(lines: list[str] | None) -> dict[int, list[str]]:
    slots: dict[int, list[str]] = {}
    j = 0
    n = len(lines or [])
    while j < n:
        raw = lines[j] if lines[j] is not None else ""
        line = _clean(str(raw))
        m = _HEADER_RE.match(line)
        if not m:
            j += 1
            continue
        num = int(m.group(1))
        tail = _clean(m.group(2))
        items: list[str] = []
        if tail and not _NO_RE.fullmatch(tail):
            items.append(_BULLET_RE.sub("", tail))
        k = j + 1
        while k < n:
            raw_next = lines[k] if lines[k] is not None else ""
            nxt = _clean(str(raw_next))
            if _HEADER_RE.match(nxt):
                break
            if nxt and not _NO_RE.fullmatch(nxt):
                items.append(_BULLET_RE.sub("", nxt))
            k += 1
        slots[num] = [x for x in items if x]
        j = k
    return slots


def _norm_join(arr: list[str] | None) -> str:
    return _clean(" | ".join([_clean(x) for x in (arr or []) if _clean(x)]))


def _build_changes(
    old_slots: dict[int, list[str]],
    new_slots: dict[int, list[str]],
) -> tuple[list[tuple[int, str]], list[tuple[int, str]], list[tuple[int, str, str]]]:
    all_keys = set(old_slots.keys()) | set(new_slots.keys())
    removed: list[tuple[int, str]] = []
    added: list[tuple[int, str]] = []
    changed: list[tuple[int, str, str]] = []
    for k in sorted(all_keys):
        o = old_slots.get(k) or []
        n = new_slots.get(k) or []
        o_s = _norm_join(o)
        n_s = _norm_join(n)
        if not o_s and not n_s:
            continue
        if o_s and not n_s:
            removed.append((k, o_s))
        elif not o_s and n_s:
            added.append((k, n_s))
        elif o_s != n_s:
            changed.append((k, o_s, n_s))
    return removed, added, changed


def _format_message(
    group: str,
    now_dt: dt.datetime,
    ddate: dt.date,
    dstr: str,
    removed: list[tuple[int, str]],
    added: list[tuple[int, str]],
    changed: list[tuple[int, str, str]],
) -> str:
    head: list[str] = []
    head.append("Группа: " + str(group))
    head.append("")
    head.append("🗓️ Обновление расписания")
    head.append("⏰ " + now_dt.strftime("%d.%m.%Y %H:%M"))
    head.append("")
    head.append(day_name_ru(ddate.weekday()) + " • " + dstr)
    body: list[str] = []
    for k, o in removed:
        body.append(f"• {k} пара: отменена «{o}»")
    for k, n in added:
        body.append(f"• {k} пара: добавлена «{n}»")
    for k, o, n in changed:
        body.append(f"• {k} пара: изменена «{o}» → «{n}»")
    if not body:
        body.append("• Изменений нет")
    return "\n".join(head + body)


def _load_state() -> dict[str, str]:
    if not STATE_PATH.exists():
        return {}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            out: dict[str, str] = {}
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, str):
                    out[k] = v
            return out
        return {}
    except Exception:
        return {}


def _save_state(state: dict[str, str]) -> None:
    try:
        with STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def _safe_parse(url: str) -> dict[str, Any]:
    try:
        data = parse_schedule(url)
        if isinstance(data, dict):
            return data
        return {}
    except Exception as e:
        logging.error("watchdog: parse failed: %s", e)
        return {}


def _should_skip_false_cancel(old_slots: dict[int, list[str]], new_slots: dict[int, list[str]]) -> bool:
    o_cnt = sum(1 for v in old_slots.values() if _norm_join(v))
    n_cnt = sum(1 for v in new_slots.values() if _norm_join(v))
    return o_cnt > 0 and n_cnt == 0


def _week_path(group: str, monday: dt.date, sunday: dt.date) -> Path:
    return SCHEDULE_CACHE_DIR / f"{group}_{monday.strftime('%Y%m%d')}_{sunday.strftime('%Y%m%d')}.json"


def _load_week(group: str, monday: dt.date, sunday: dt.date) -> dict[str, Any]:
    path = _week_path(group, monday, sunday)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def _save_week(group: str, monday: dt.date, sunday: dt.date, data: dict[str, Any]) -> None:
    path = _week_path(group, monday, sunday)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _load_overlay() -> dict[str, Any]:
    if not OVERLAY_PATH.exists():
        return {}
    try:
        with OVERLAY_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


async def schedule_watchdog_loop(bot: Bot, tz: dt.tzinfo) -> None:
    state = _load_state()
    while True:
        try:
            ctx = get_context()
        except Exception:
            await asyncio.sleep(2)
            continue
        try:
            schedule_service = ctx.schedule_service
            url_map = getattr(schedule_service, "url_map", {}) or {}
            overlay_all = _load_overlay()
            now = dt.datetime.now(tz)
            targets = [now.date(), now.date() + dt.timedelta(days=1)]
            for g, url in list(url_map.items()):
                if not url:
                    continue
                for tgt in targets:
                    cmonday, csunday = week_bounds_mon_sun(tgt)
                    old_week = _load_week(g, cmonday, csunday) or {}
                    fresh = await asyncio.to_thread(_safe_parse, url)
                    overlay = overlay_all.get(g, {}) or {}
                    for dstr, info in list(overlay.items()):
                        try:
                            d = dt.datetime.strptime(dstr, "%d.%m.%Y").date()
                        except Exception:
                            continue
                        if cmonday <= d <= csunday:
                            fresh[dstr] = info
                    dstr = tgt.strftime("%d.%m.%Y")
                    new_info = fresh.get(dstr)
                    if new_info is None:
                        continue
                    old_info = old_week.get(dstr, {"day": "", "lessons": []})
                    old_lines = _normalize_day_lines(dstr, old_info)
                    new_lines = _normalize_day_lines(dstr, new_info)
                    old_slots = _parse_slots(old_lines)
                    new_slots = _parse_slots(new_lines)
                    removed, added, changed = _build_changes(old_slots, new_slots)
                    if not removed and not added and not changed:
                        continue
                    if _should_skip_false_cancel(old_slots, new_slots):
                        continue
                    fingerprint = json.dumps(
                        {"rem": removed, "add": added, "chg": changed},
                        ensure_ascii=False,
                    )
                    key = f"{g}:{dstr}"
                    if state.get(key) == fingerprint:
                        continue
                    msg = _format_message(g, now, tgt, dstr, removed, added, changed)
                    users = await ctx.db.get_users_for_schedule_notifications(g)
                    for u in users:
                        tg_id = u.get("tg_id")
                        if not tg_id:
                            continue
                        username = u.get("username")
                        banned = await ctx.db.is_user_banned(tg_id, username)
                        if banned:
                            continue
                        try:
                            await bot.send_message(tg_id, msg, disable_web_page_preview=True)
                        except TypeError:
                            await bot.send_message(tg_id, msg)
                        except Exception:
                            await ctx.db.set_user_blocked(tg_id, True)
                    _save_week(g, cmonday, csunday, fresh)
                    state[key] = fingerprint
                    _save_state(state)
        except Exception as e:
            logging.error("watchdog loop: %s", e)
        await asyncio.sleep(30)