import datetime as dt
import json
import re
import uuid
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any, TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from app.services.schedule_service import ScheduleService


class HomeworkService:
    def __init__(
        self,
        db,
        schedule_service: "ScheduleService",
        times_path: Path,
        models_path: Path,
        homeworks_dir: Path,
        freeimage_api_key: str | None,
        telegraph_token: str | None,
    ):
        self.db = db
        self.schedule_service = schedule_service
        self.times_path = times_path
        self.models_path = models_path
        self.homeworks_dir = homeworks_dir
        self.freeimage_api_key = freeimage_api_key
        self.telegraph_token = telegraph_token
        self.homeworks_dir.mkdir(parents=True, exist_ok=True)
        self.personal_dir = self.homeworks_dir / "personal"
        self.public_dir = self.homeworks_dir / "public"
        self.personal_dir.mkdir(parents=True, exist_ok=True)
        self.public_dir.mkdir(parents=True, exist_ok=True)
        self._legacy_personal_path = self.homeworks_dir / "personal.json"
        self._legacy_public_path = self.homeworks_dir / "public.json"
        self.pending_path = self.homeworks_dir / "pending.json"
        self.ai_logs_path = self.homeworks_dir / "ai_logs.jsonl"
        self.ai_config_path = self.homeworks_dir / "ai_config.json"
        self._times_cache: dict | None = None
        self._ensure_files()

    def _ensure_files(self) -> None:
        if self._legacy_personal_path.exists():
            items = self._load_json_list(self._legacy_personal_path)
            for item in items:
                uid = item.get("user_id")
                if uid is None:
                    continue
                current = self._load_json_list(self._personal_file(uid))
                current.append(item)
                self._save_json_list(self._personal_file(uid), current)
            try:
                self._legacy_personal_path.unlink()
            except OSError:
                pass
        if self._legacy_public_path.exists():
            items = self._load_json_list(self._legacy_public_path)
            grouped: dict[str, list[dict]] = {}
            for item in items:
                gc = (item.get("group_code") or "").strip()
                if not gc:
                    continue
                grouped.setdefault(gc, []).append(item)
            for gc, lst in grouped.items():
                self._save_json_list(self._public_file(gc), lst)
            try:
                self._legacy_public_path.unlink()
            except OSError:
                pass
        if not self.pending_path.exists():
            self.pending_path.write_text("[]", encoding="utf-8")
        if not self.ai_logs_path.exists():
            self.ai_logs_path.write_text("", encoding="utf-8")
        if not self.ai_config_path.exists():
            data = {
                "model": "pollinations/llama-3.1-70b-instruct",
                "temperature": 0.2,
                "system_prompt": "Ты проверяешь домашнее задание студентов. Отвечай только в JSON с полем decision: 'да' или 'нет', и полем reason с коротким объяснением.",
                "auto_accept": False,
            }
            self.ai_config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if not self.models_path.exists():
            self.models_path.write_text(json.dumps({"models": [], "updated_at": None}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_json_list(self, path: Path) -> list[dict]:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw or "[]")
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

    def _save_json_list(self, path: Path, items: list[dict]) -> None:
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def _personal_file(self, user_id: int) -> Path:
        return self.personal_dir / f"{user_id}.json"

    def _public_file(self, group_code: str) -> Path:
        safe_code = re.sub(r"[\s-]+", "", group_code).upper() or "UNKNOWN"
        return self.public_dir / f"{safe_code}.json"

    def _load_personal_hw(self, user_id: int) -> list[dict]:
        return self._load_json_list(self._personal_file(user_id))

    def _save_personal_hw(self, user_id: int, items: list[dict]) -> None:
        self._save_json_list(self._personal_file(user_id), items)

    def _load_public_hw(self, group_code: str) -> list[dict]:
        return self._load_json_list(self._public_file(group_code))

    def _save_public_hw(self, group_code: str, items: list[dict]) -> None:
        self._save_json_list(self._public_file(group_code), items)

    def _now_iso(self) -> str:
        return dt.datetime.utcnow().isoformat()

    def _format_datetime(self, value: str | dt.datetime | None) -> str:
        if value is None:
            return ""
        dt_obj: dt.datetime | None
        if isinstance(value, dt.datetime):
            dt_obj = value
        else:
            try:
                dt_obj = dt.datetime.fromisoformat(value)
            except Exception:
                dt_obj = None
        if not dt_obj:
            return ""
        return dt_obj.strftime("%d.%m.%Y %H:%M")

    async def is_premium(self, user_id: int) -> bool:
        return await self.db.is_user_premium(user_id)

    def _compact_ai_raw(self, raw: Any) -> str | None:
        if raw is None:
            return None
        content = None
        if isinstance(raw, dict):
            choices = raw.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content")
        if content is None and isinstance(raw, str):
            try:
                data = json.loads(raw)
            except Exception:
                content = raw
            else:
                if isinstance(data, dict):
                    choices = data.get("choices")
                    if isinstance(choices, list) and choices:
                        msg = choices[0].get("message") or {}
                        content = msg.get("content")
                if content is None:
                    content = raw
        if content is None:
            content = str(raw)
        if len(content) > 2000:
            content = content[:2000]
        return content
        
    def _normalize_ai_result(self, result: Any) -> dict:
        if not isinstance(result, dict):
            return {
                "decision": None,
                "reason": None,
                "raw": self._compact_ai_raw(result),
                "meta": result,
            }
        decision = result.get("decision")
        reason = result.get("reason")
        raw = result.get("raw", result)
        compact_raw = self._compact_ai_raw(raw)
        return {
            "decision": decision,
            "reason": reason,
            "raw": compact_raw,
            "meta": raw,
        }

    def _normalize_text(self, s: str) -> str:
        s = (s or "").lower().replace("ё", "е")
        return re.sub(r"[\s\-]", "", s)

    def _load_times(self) -> dict:
        if self._times_cache is None:
            try:
                raw = self.times_path.read_text(encoding="utf-8")
                self._times_cache = json.loads(raw or "{}")
            except Exception:
                self._times_cache = {}
        return self._times_cache or {}

    def _find_times_template(self, group_code: str) -> str | None:
        data = self._load_times()
        groups_map = data.get("groups_map", {})
        target = self._normalize_text(group_code)
        for key, info in groups_map.items():
            matches = info.get("match") if isinstance(info, dict) else None
            if not matches:
                continue
            for m in matches:
                if self._normalize_text(m) == target:
                    return key
        return None

    def _weekday_key(self, date_obj: dt.date) -> str:
        return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][date_obj.weekday()]

    def _filter_lessons(self, lessons: list[str]) -> list[str]:
        filtered = []
        for item in lessons:
            low = item.lower()
            if "внеуроч" in low or "обед" in low:
                continue
            filtered.append(item)
        return filtered

    def _parse_end_time(self, item: str) -> dt.time | None:
        m = re.search(r"(\d{2}:\d{2})\s*[\u2013-]\s*(\d{2}:\d{2})", item)
        if not m:
            return None
        try:
            end = dt.datetime.strptime(m.group(2), "%H:%M").time()
            return end
        except Exception:
            return None

    def _pair_end_datetime(self, template_key: str, date_obj: dt.date, pair_number: int) -> dt.datetime | None:
        data = self._load_times()
        template = data.get("templates", {}).get(template_key, {})
        if not template:
            return None
        day_key = self._weekday_key(date_obj)
        lessons = template.get(day_key)
        if not isinstance(lessons, list):
            return None
        filtered = self._filter_lessons(lessons)
        first_lesson_idx = (pair_number - 1) * 2
        if first_lesson_idx < 0 or first_lesson_idx >= len(filtered):
            return None
        end_time = self._parse_end_time(filtered[first_lesson_idx])
        if not end_time:
            return None
        return dt.datetime.combine(date_obj, end_time)

    async def _find_pair_for_subject(self, group_code: str, subject: str) -> tuple[dt.date, int] | None:
        normalized_target = self._normalize_text(subject)
        if not normalized_target:
            return None
        candidates: list[tuple[dt.date, int]] = []
        for shift in (0, 7):
            base_date = dt.date.today() + dt.timedelta(days=shift)
            schedule = await self.schedule_service.get_week_schedule(group_code, base_date)
            if not schedule:
                continue
            for date_str, info in schedule.items():
                try:
                    date_obj = dt.datetime.strptime(date_str, "%d.%m.%Y").date()
                except Exception:
                    continue
                pairs = info.get("pairs", {}) if isinstance(info, dict) else {}
                for pair_num_raw, entries in pairs.items():
                    try:
                        pair_num = int(pair_num_raw)
                    except Exception:
                        continue
                    if not isinstance(entries, list):
                        continue
                    for raw in entries:
                        subj = str(raw or "").split("|")[0].strip()
                        if self._normalize_text(subj) == normalized_target:
                            candidates.append((date_obj, pair_num))
                            break
        if not candidates:
            return None
        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates[0]

    async def calculate_delete_time(self, group_code: str, subject: str) -> dt.datetime | None:
        template_key = self._find_times_template(group_code)
        if not template_key:
            return None
        pair_info = await self._find_pair_for_subject(group_code, subject)
        if pair_info:
            date_obj, pair_num = pair_info
        else:
            m = re.search(r"(\d+)", subject)
            if not m:
                return None
            pair_num = int(m.group(1))
            date_obj = dt.date.today()
        if pair_num <= 0:
            return None
        return self._pair_end_datetime(template_key, date_obj, pair_num)

    def add_personal_homework(
        self,
        user_id: int,
        subject: str,
        text: str,
        telegraph_url: str | None,
        delete_at: dt.datetime | None,
    ) -> None:
        items = self._load_personal_hw(user_id)
        new_item = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "subject": subject,
            "text": text,
            "telegraph_url": telegraph_url,
            "created_at": self._now_iso(),
            "delete_at": delete_at.isoformat() if delete_at else None,
        }
        items.append(new_item)
        self._save_personal_hw(user_id, items)

    async def delete_personal_homework(self, user_id: int, subject: str) -> bool:
        items = self._load_personal_hw(user_id)
        before = len(items)
        items = [i for i in items if not (i.get("user_id") == user_id and i.get("subject") == subject)]
        self._save_personal_hw(user_id, items)
        return len(items) < before

    async def edit_personal_homework_text(self, user_id: int, hw_id: str, new_text: str) -> bool:
        items = self._load_personal_hw(user_id)
        changed = False
        for i in items:
            if i.get("user_id") == user_id and i.get("id") == hw_id:
                i["text"] = new_text
                changed = True
                break
        if changed:
            self._save_personal_hw(user_id, items)
        return changed

    async def format_personal_view(self, user_id: int) -> str:
        items = self._load_personal_hw(user_id)
        if not items:
            return "У вас пока нет личных домашних заданий."
        lines: list[str] = ["<b>Ваши личные домашние задания</b>", ""]
        items_sorted = sorted(items, key=lambda x: x.get("created_at") or "")
        for item in items_sorted:
            subject = escape(item.get("subject") or "Без названия")
            text = escape(item.get("text") or "")
            telegraph_url = item.get("telegraph_url")
            delete_at = self._format_datetime(item.get("delete_at"))
            lines.append(f"📌 <b>{subject}</b>")
            if text:
                lines.append(text)
            if telegraph_url:
                lines.append(f"Фото: <a href=\"{escape(telegraph_url)}\">открыть</a>")
            if delete_at:
                lines.append(f"Удалится: <code>{escape(delete_at)}</code>")
            lines.append("")
        return "\n".join(lines)

    def add_public_homework(
        self,
        group_code: str,
        subject: str,
        text: str,
        telegraph_url: str | None,
        delete_at: dt.datetime | None,
    ) -> None:
        items = self._load_public_hw(group_code)
        new_item = {
            "id": str(uuid.uuid4()),
            "group_code": group_code,
            "subject": subject,
            "text": text,
            "telegraph_url": telegraph_url,
            "created_at": self._now_iso(),
            "delete_at": delete_at.isoformat() if delete_at else None,
        }
        items.append(new_item)
        self._save_public_hw(group_code, items)

    async def format_public_view(self, group_code: str) -> str:
        items = self._load_public_hw(group_code)
        if not items:
            return (
                f"Для группы <b>{escape(group_code)}</b> ещё нет сохранённых общих домашних заданий.\n"
                "Вы можете предложить задание через кнопку «📝 Предложить общее дз»."
            )
        lines: list[str] = [f"<b>Общая домашка для группы {escape(group_code)}</b>", ""]
        items_sorted = sorted(items, key=lambda x: x.get("created_at") or "")
        for item in items_sorted:
            subject = escape(item.get("subject") or "Без названия")
            text = escape(item.get("text") or "")
            telegraph_url = item.get("telegraph_url")
            created_at = item.get("created_at")
            delete_at = self._format_datetime(item.get("delete_at"))
            dt_text = ""
            if created_at:
                try:
                    dt_obj = dt.datetime.fromisoformat(created_at)
                    dt_text = dt_obj.strftime("%d.%m.%Y %H:%M")
                except Exception:
                    dt_text = created_at
            lines.append(f"📌 <b>{subject}</b>")
            if dt_text:
                lines.append(f"Добавлено: <code>{escape(dt_text)}</code>")
            if text:
                lines.append(text)
            if telegraph_url:
                lines.append(f"Фото: <a href=\"{escape(telegraph_url)}\">открыть</a>")
            if delete_at:
                lines.append(f"Удалится: <code>{escape(delete_at)}</code>")
            lines.append("")
        return "\n".join(lines)

    def add_public_pending(
        self,
        user_id: int,
        username: str | None,
        full_name: str | None,
        group_code: str,
        subject: str,
        text: str,
        telegraph_url: str | None,
        ai_result: dict | None,
    ) -> None:
        normalized_ai = self._normalize_ai_result(ai_result)
        items = self._load_json_list(self.pending_path)
        new_item = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "group_code": group_code,
            "subject": subject,
            "text": text,
            "telegraph_url": telegraph_url,
            "ai_result": normalized_ai,
            "created_at": self._now_iso(),
        }
        items.append(new_item)
        self._save_json_list(self.pending_path, items)

    def load_public_pending_page(self, page: int, per_page: int = 10) -> tuple[list[dict], int, int]:
        items = self._load_json_list(self.pending_path)
        total = len(items)
        if total == 0:
            return [], 0, 0
        items_sorted = sorted(items, key=lambda x: x.get("created_at") or "", reverse=True)
        pages = (total + per_page - 1) // per_page
        if page < 1:
            page = 1
        if page > pages:
            page = pages
        start = (page - 1) * per_page
        end = start + per_page
        return items_sorted[start:end], total, pages

    def get_pending_request(self, req_id: str) -> dict | None:
        items = self._load_json_list(self.pending_path)
        for it in items:
            if it.get("id") == req_id:
                return it
        return None

    def remove_pending_request(self, req_id: str) -> None:
        items = self._load_json_list(self.pending_path)
        items = [i for i in items if i.get("id") != req_id]
        self._save_json_list(self.pending_path, items)

    def append_ai_log(
        self,
        user_id: int,
        username: str | None,
        full_name: str | None,
        subject: str,
        text: str,
        telegraph_url: str | None,
        result: dict | None,
    ) -> None:
        normalized_ai = self._normalize_ai_result(result)
        entry = {
            "timestamp": self._now_iso(),
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "subject": subject,
            "text": text,
            "telegraph_url": telegraph_url,
            "ai_result": normalized_ai,
        }
        with self.ai_logs_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_ai_logs_page(self, page: int, per_page: int = 10) -> tuple[list[dict], int, int]:
        entries: list[dict] = []
        if self.ai_logs_path.exists():
            with self.ai_logs_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(data, dict):
                        entries.append(data)
        entries_sorted = sorted(entries, key=lambda x: x.get("timestamp") or "", reverse=True)
        total = len(entries_sorted)
        if total == 0:
            return [], 0, 0
        pages = (total + per_page - 1) // per_page
        if page < 1:
            page = 1
        if page > pages:
            page = pages
        start = (page - 1) * per_page
        end = start + per_page
        return entries_sorted[start:end], total, pages

    def load_ai_config(self) -> dict:
        try:
            raw = self.ai_config_path.read_text(encoding="utf-8")
            data = json.loads(raw or "{}")
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            return {}

    def save_ai_config(self, data: dict) -> None:
        self.ai_config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_models(self) -> list[str]:
        try:
            raw = self.models_path.read_text(encoding="utf-8")
            data = json.loads(raw or "{}")
            if not isinstance(data, dict):
                return []
            models = data.get("models")
            if isinstance(models, list):
                return [str(m) for m in models]
            return []
        except Exception:
            return []

    async def pollinations_refresh_models(self) -> list[str]:
        url = "https://text.pollinations.ai/openai/models"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                try:
                    payload = await resp.json()
                except Exception:
                    payload = []
        models: list[str] = []
        if isinstance(payload, list):
            for m in payload:
                if isinstance(m, dict):
                    name = m.get("id") or m.get("name")
                    if name:
                        models.append(str(name))
        data = {
            "models": models,
            "updated_at": self._now_iso(),
        }
        self.models_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return models

    async def pollinations_check_homework(self, text: str) -> dict:
        config = self.load_ai_config()
        model = config.get("model") or "pollinations/llama-3.1-70b-instruct"
        temperature = float(config.get("temperature", 0.2))
        system_prompt = config.get("system_prompt") or "Отвечай только JSON с decision и reason."
        url = "https://text.pollinations.ai/openai/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=payload, timeout=60) as resp:
                    raw = await resp.text()
            except Exception as e:
                return {"decision": "нет", "reason": f"Ошибка при обращении к API: {e}", "raw": None}
        parsed: dict[str, Any] | None = None
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                choices = data.get("choices")
                if isinstance(choices, list) and choices:
                    msg = choices[0].get("message") or {}
                    content = msg.get("content") or ""
                    parsed = json.loads(content)
        except Exception:
            parsed = None
        if not isinstance(parsed, dict):
            return {"decision": "нет", "reason": "Не удалось разобрать ответ модели", "raw": raw}
        decision = str(parsed.get("decision") or "").strip().lower()
        if decision not in {"да", "нет"}:
            decision = "нет"
        return {"decision": decision, "reason": parsed.get("reason"), "raw": parsed}

    async def upload_images_and_make_telegraph(self, message) -> str | None:
        if not self.telegraph_token:
            return None
        if not message.photo:
            return None
        photos = message.photo
        file_ids = [p.file_id for p in photos]
        bot = message.bot
        file_bytes_list: list[bytes] = []
        for fid in file_ids:
            f = await bot.get_file(fid)
            buf = BytesIO()
            await bot.download_file(f.file_path, buf)
            file_bytes_list.append(buf.getvalue())
        telegraph_files: list[dict] = []
        async with aiohttp.ClientSession() as session:
            for idx, data in enumerate(file_bytes_list):
                form = aiohttp.FormData()
                form.add_field(
                    "file",
                    data,
                    filename=f"image_{idx}.jpg",
                    content_type="image/jpeg",
                )
                async with session.post("https://telegra.ph/upload", data=form) as resp:
                    uploaded = await resp.json()
                    if isinstance(uploaded, list) and uploaded and isinstance(uploaded[0], dict):
                        src = uploaded[0].get("src")
                        if src:
                            telegraph_files.append({"src": src})
        if not telegraph_files:
            return None
        content_nodes = []
        for f in telegraph_files:
            src = f["src"]
            if src.startswith("/"):
                url = "https://telegra.ph" + src
            else:
                url = src
            content_nodes.append({"tag": "img", "attrs": {"src": url}})
        page_url = await self._create_telegraph_page_with_images(message, content_nodes)
        return page_url

    async def _create_telegraph_page_with_images(self, message, nodes: list[dict]) -> str | None:
        if not self.telegraph_token:
            return None
        author_name = message.from_user.full_name or message.from_user.username or "Студент"
        title = "Домашка"
        url = "https://api.telegra.ph/createPage"
        payload = {
            "access_token": self.telegraph_token,
            "title": title,
            "author_name": author_name,
            "content": json.dumps(nodes, ensure_ascii=False),
            "return_content": False,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload) as resp:
                data = await resp.json()
        if not isinstance(data, dict):
            return None
        if not data.get("ok"):
            return None
        result = data.get("result") or {}
        return result.get("url")