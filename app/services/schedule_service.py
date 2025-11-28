import asyncio
import datetime as dt
import json
import logging
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup


def week_bounds_mon_sun(d):
    monday = d - dt.timedelta(days=d.weekday())
    sunday = monday + dt.timedelta(days=6)
    return monday, sunday


def week_mon_sat_for_display(now_date):
    wd = now_date.weekday()
    if wd in (5, 6):
        shift = 7 - wd
        base = now_date + dt.timedelta(days=shift)
    else:
        base = now_date
    monday = base - dt.timedelta(days=base.weekday())
    saturday = monday + dt.timedelta(days=5)
    return monday, saturday


_DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})(?:\s+(.+))?")


def _clean_text(s):
    s = (s or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _mk_full_title(cell):
    subj_tag = cell.find("a", class_="z1")
    room_tag = cell.find("a", class_="z2")
    teacher_tag = cell.find(attrs={"class": lambda x: x and ("z3" in x)})
    subj_raw = subj_tag.get_text(strip=True) if subj_tag else cell.get_text(strip=True)
    subj = re.sub(r"\(\s*\)", "", subj_raw).strip()
    parts = [
        p
        for p in [
            subj,
            room_tag.get_text(strip=True) if room_tag else "",
            teacher_tag.get_text(strip=True) if teacher_tag else "",
        ]
        if p
    ]
    return " | ".join(parts)


def fetch_page(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/117.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return r.content


def parse_schedule(url):
    try:
        html = fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="output-table") or soup.find("table")
        if not table:
            return {}
        rows = table.find_all("tr")
        schedule = {}
        i = 0
        n = len(rows)
        while i < n:
            row = rows[i]
            date_cell = row.find("td", attrs={"rowspan": True})
            if not date_cell:
                i += 1
                continue
            date_text = date_cell.get_text(separator="\n").strip()
            m = _DATE_RE.search(date_text)
            if not m:
                i += 1
                continue
            date = m.group(1)
            dayname = (m.group(2) or "").strip()
            schedule.setdefault(date, {"day": dayname, "pairs": {}, "pairs_cols": {}, "merge": {}})
            day_rows = rows[i : i + 8]
            i += 8
            for dr in day_rows:
                tds = dr.find_all("td")
                pair_num = None
                pair_idx = -1
                for idx, td in enumerate(tds):
                    if "hd" in (td.get("class") or []):
                        text = _clean_text(td.get_text())
                        if text.isdigit():
                            pair_num = int(text)
                            pair_idx = idx
                            break
                if pair_num is None:
                    continue
                cells = tds[pair_idx + 1 :]
                groups = [None] * 5
                col = 0
                for cell in cells:
                    span = 1
                    if cell.has_attr("colspan"):
                        try:
                            span = int(cell["colspan"])
                        except Exception:
                            span = 1
                    content = None
                    if "ur" in (cell.get("class") or []):
                        content = _mk_full_title(cell)
                    for k in range(span):
                        if col + k < 5:
                            groups[col + k] = content
                    col += span
                first = groups[0]
                second = groups[1]
                common = None
                for j in range(2, 5):
                    if groups[j] is not None:
                        common = groups[j]
                        break
                if all(g is None for g in groups):
                    continue
                if common:
                    schedule[date]["merge"][pair_num] = common
                    schedule[date]["pairs"][pair_num] = [common]
                else:
                    if first and second:
                        if first == second:
                            schedule[date]["merge"][pair_num] = first
                            schedule[date]["pairs"][pair_num] = [first]
                        else:
                            schedule[date]["pairs_cols"][pair_num] = [first, second]
                            schedule[date]["pairs"][pair_num] = [first, second]
                    elif first:
                        schedule[date]["pairs_cols"][pair_num] = [first, ""]
                        schedule[date]["pairs"][pair_num] = [first]
                    elif second:
                        schedule[date]["pairs_cols"][pair_num] = ["", second]
                        schedule[date]["pairs"][pair_num] = [second]
        for d, info in schedule.items():
            lines = []
            for i_pair in range(1, 9):
                if i_pair in info.get("merge", {}):
                    lines.append(f"{i_pair} пара: {info['merge'][i_pair]}")
                    continue
                cols = info.get("pairs_cols", {}).get(i_pair, None)
                if not cols:
                    items = info.get("pairs", {}).get(i_pair, [])
                    if not items:
                        lines.append(f"{i_pair} пара: НЕТ")
                    elif len(items) == 1:
                        lines.append(f"{i_pair} пара: {items[0]}")
                    else:
                        lines.append(f"{i_pair} пара:")
                        lines.append(f"① {items[0]}")
                        lines.append(f"② {items[1]}")
                    continue
                c1 = cols[0] if len(cols) > 0 else ""
                c2 = cols[1] if len(cols) > 1 else ""
                if not c1 and not c2:
                    lines.append(f"{i_pair} пара: НЕТ")
                elif c1 and c2:
                    lines.append(f"{i_pair} пара:")
                    lines.append(f"① {c1}")
                    lines.append(f"② {c2}")
                elif c1:
                    lines.append(f"{i_pair} пара: ① {c1}")
                else:
                    lines.append(f"{i_pair} пара: ② {c2}")
            info["lessons"] = lines
        return schedule
    except Exception as e:
        logging.error("parse error: %s", e)
        return {}


def sort_dates_all(schedule):
    def _parse(s):
        try:
            return dt.datetime.strptime(s, "%d.%m.%Y")
        except Exception:
            return dt.datetime.max

    return sorted(schedule.keys(), key=lambda k: _parse(k))


def day_name_ru(weekday):
    return [
        "Понедельник",
        "Вторник",
        "Среда",
        "Четверг",
        "Пятница",
        "Суббота",
        "Воскресенье",
    ][weekday]


def normalize_day(dstr, info, max_pairs=8, subgroup=None, multiline=False):
    d = dt.datetime.strptime(dstr, "%d.%m.%Y").date()
    name = day_name_ru(d.weekday())
    return f"{name} • {dstr}", info.get("lessons", ["Пар нету🤗"])


def make_blocks(schedule, max_pairs=8, subgroup=None, multiline=False):
    blocks = []
    for d in sort_dates_all(schedule):
        header, lst = normalize_day(
            d, schedule.get(d, {}), max_pairs=max_pairs, subgroup=subgroup, multiline=multiline
        )
        blocks.append((header, lst))
    return blocks

class ScheduleService:
    def __init__(self, url_path: Path):
        url_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with url_path.open(encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            with url_path.open("w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            data = {}
        self.url_map: dict[str, str] = data if isinstance(data, dict) else {}
        self.schedule_dir = url_path.parent / "schedule"
        self.schedule_dir.mkdir(parents=True, exist_ok=True)

    def get_url_for_group(self, group_code: str) -> str | None:
        return self.url_map.get(group_code)

    def _schedule_filename(self, group_code: str, monday: dt.date, saturday: dt.date) -> Path:
        name = f"{group_code}_{monday.strftime('%d.%m.%y')}-{saturday.strftime('%d.%m.%y')}.json"
        return self.schedule_dir / name

    def _cleanup_old_files(self, current_date: dt.date) -> None:
        monday_current, saturday_current = week_mon_sat_for_display(current_date)
        for path in self.schedule_dir.glob("*.json"):
            stem = path.stem
            if "_" not in stem:
                continue
            try:
                _, range_part = stem.rsplit("_", 1)
                start_str, end_str = range_part.split("-", 1)
                start_date = dt.datetime.strptime(start_str, "%d.%m.%y").date()
                end_date = dt.datetime.strptime(end_str, "%d.%m.%y").date()
            except Exception:
                continue
            if end_date < monday_current:
                try:
                    path.unlink()
                except OSError as e:
                    logging.error("failed to delete old schedule file %s: %s", path, e)

    def _load_cached_schedule(self, group_code: str, target_date: dt.date) -> dict | None:
        for path in self.schedule_dir.glob(f"{group_code}_*.json"):
            stem = path.stem
            try:
                _, range_part = stem.rsplit("_", 1)
                start_str, end_str = range_part.split("-", 1)
                start_date = dt.datetime.strptime(start_str, "%d.%m.%y").date()
                end_date = dt.datetime.strptime(end_str, "%d.%m.%y").date()
            except Exception:
                continue
            if start_date <= target_date <= end_date:
                try:
                    with path.open(encoding="utf-8") as f:
                        data = json.load(f)
                    schedule = data.get("schedule")
                    if isinstance(schedule, dict):
                        return schedule
                except Exception as e:
                    logging.error("failed to load cached schedule %s: %s", path, e)
        return None

    def _save_schedule(self, group_code: str, base_date: dt.date, schedule: dict) -> None:
        monday, saturday = week_mon_sat_for_display(base_date)
        path = self._schedule_filename(group_code, monday, saturday)
        data = {
            "group": group_code,
            "monday": monday.strftime("%d.%m.%Y"),
            "saturday": saturday.strftime("%d.%m.%Y"),
            "schedule": schedule,
        }
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error("failed to save schedule %s: %s", path, e)

    async def _fetch_schedule_for_group(self, group_code: str, base_date: dt.date) -> dict:
        self._cleanup_old_files(base_date)
        cached = self._load_cached_schedule(group_code, base_date)
        if cached is not None:
            return cached
        url = self.get_url_for_group(group_code)
        if not url:
            return {}
        schedule = await asyncio.to_thread(parse_schedule, url)
        if schedule:
            self._save_schedule(group_code, base_date, schedule)
        return schedule

    async def get_day_schedule_text(self, group_code: str, date_obj: dt.date) -> str:
        schedule = await self._fetch_schedule_for_group(group_code, date_obj)
        if not schedule:
            return f"Не удалось получить расписание для группы <b>{group_code}</b>."
        date_str = date_obj.strftime("%d.%m.%Y")
        info = schedule.get(date_str, {})
        header, lessons = normalize_day(date_str, info)
        header_text = f"<b>{header}</b>\n"
        lessons_text = "\n".join(lessons)
        return header_text + f"<blockquote>{lessons_text}</blockquote>"

    async def get_week_schedule_text(self, group_code: str, base_date: dt.date) -> str:
        schedule = await self._fetch_schedule_for_group(group_code, base_date)
        if not schedule:
            return f"Не удалось получить расписание для группы <b>{group_code}</b>."
        monday, saturday = week_mon_sat_for_display(base_date)
        parts = []
        current = monday
        while current <= saturday:
            date_str = current.strftime("%d.%m.%Y")
            info = schedule.get(date_str, {})
            header, lessons = normalize_day(date_str, info)
            lessons_text = "\n".join(lessons)
            block_text = f"<b>{header}</b>\n<blockquote>{lessons_text}</blockquote>"
            parts.append(block_text)
            current += dt.timedelta(days=1)
        if not parts:
            return f"Для недели, начинающейся {monday.strftime('%d.%m.%Y')}, расписание не найдено."
        return "\n\n".join(parts)

    async def get_unique_subjects_for_week(self, group_code: str, base_date: dt.date) -> list[str]:
        schedule = await self._fetch_schedule_for_group(group_code, base_date)
        subjects = set()
        for info in schedule.values():
            pairs_dict = info.get("pairs", {})
            merge_dict = info.get("merge", {})
            for p_list in pairs_dict.values():
                for raw in p_list:
                    if raw:
                        parts = raw.split("|")
                        if parts:
                            subj = parts[0].strip()
                            if subj:
                                subjects.add(subj)
            for raw in merge_dict.values():
                if raw:
                    parts = raw.split("|")
                    if parts:
                        subj = parts[0].strip()
                        if subj:
                            subjects.add(subj)
        return sorted(list(subjects))
