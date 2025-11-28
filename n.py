import argparse
import datetime as dt
import fnmatch
import os
import stat
import time
from collections import defaultdict
from pathlib import Path

EXCLUDE_EXTS = {
    ".bak", ".json", ".log", ".pyc", ".ttf", ".otf",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
    ".pdf", ".zip", ".rar", ".7z", ".tar", ".gz",
    ".sqlite", ".sqlite3", ".db",
    ".txt", ".sqlite3-wal", ".sqlite3-shm",
}

EXCLUDE_DIRS = {".git", "__pycache__", ".idea", ".vscode", ".venv", "venv", "node_modules"}

HIDE_CODE_FILES = set()

HIDE_CODE_GLOBS = []

MAX_SIZE = 10 * 1024 * 1024

TRY_ENCODINGS = ("utf-8", "cp1251", "utf-16", "latin-1")

DEFAULT_TOPICS = {
    "расписание": {
        "keywords_any": ["schedule", "расписан", "parse_schedule", "ScheduleService", "week_mon_sat_for_display"],
        "roles_any": ["Schedule/Calendar"],
        "paths_any": ["app/services/schedule_service.py", "app/handlers/schedule.py"],
    },
    "группы": {
        "keywords_any": ["groupresolver", "setmygroup", "group_code", "group_resolver"],
        "roles_any": [],
        "paths_any": ["app/services/group_service.py", "app/handlers/common.py"],
    },
    "пользователи": {
        "keywords_any": ["get_user", "ensure_user", "accept_tos", "tos_accepted", "user"],
        "roles_any": [],
        "paths_any": ["app/services/db.py", "app/handlers/start.py", "app/handlers/common.py"],
    },
    "бот": {
        "keywords_any": ["setup_bot", "Dispatcher", "aiogram", "Bot", "AppContext"],
        "roles_any": [],
        "paths_any": ["main.py", "app/core/bot.py", "app/core/context.py"],
    },
    "fsm": {
        "keywords_any": ["fsm", "SQLiteStorage", "StatesGroup", "MenuStates", "State"],
        "roles_any": [],
        "paths_any": [
            "app/core/fsm_storage.py",
            "app/core/states.py",
            "app/handlers/common.py",
            "app/handlers/schedule.py",
            "app/handlers/start.py",
        ],
    },
    "хранилище": {
        "keywords_any": ["Database", "aiosqlite", "db_path", "fsm_states", "fsm_data"],
        "roles_any": ["Storage/IO"],
        "paths_any": ["app/services/db.py", "app/core/fsm_storage.py"],
    },
}


def fmt_ts(ts: float) -> str:
    try:
        return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def fmt_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    s = float(n)
    i = 0
    while s >= 1024 and i < len(units) - 1:
        s /= 1024.0
        i += 1
    return f"{int(s)}{units[i]}" if i == 0 else f"{s:.1f}{units[i]}"


def read_text(path: Path) -> str:
    try:
        st = path.stat()
        if not stat.S_ISREG(st.st_mode):
            return "[Не обычный файл]\n"
        if st.st_size > MAX_SIZE:
            return "[Файл слишком большой, пропущен]\n"
    except Exception as e:
        return f"[Ошибка доступа к файлу: {e}]\n"
    for enc in TRY_ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return f"[Ошибка при чтении: {e}]\n"
    return "[Не удалось декодировать файл]\n"


def _is_hidden_code(project_root: Path, p: Path) -> bool:
    if p.name in HIDE_CODE_FILES:
        return True
    if HIDE_CODE_GLOBS:
        rel = str(p.relative_to(project_root)).replace("\\", "/")
        for g in HIDE_CODE_GLOBS:
            if fnmatch.fnmatch(rel, g):
                return True
    return False


def collect_files(base_dir: Path, script_path: Path):
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            p = Path(root) / fname
            if p.resolve() == script_path:
                continue
            if p.suffix.lower() in EXCLUDE_EXTS:
                continue
            yield p


def is_probably_local(mod_name: str) -> bool:
    return mod_name.startswith((".", "app"))


def extract_imports(text: str):
    local = set()
    external = set()
    for line in text.splitlines():
        ls = line.strip()
        if not ls or ls.startswith("#"):
            continue
        if ls.startswith("import "):
            body = ls[len("import "):]
            parts = [p.strip() for p in body.split(",")]
            for part in parts:
                name = part.split(" as ")[0].strip()
                if not name:
                    continue
                (local if is_probably_local(name) else external).add(name)
        elif ls.startswith("from "):
            try:
                mod = ls[len("from "):].split(" import ")[0].strip()
            except Exception:
                continue
            if not mod:
                continue
            (local if is_probably_local(mod) else external).add(mod)
    return local, external


def module_basename_from_path(project_root: Path, path: Path) -> str:
    rel = path.relative_to(project_root)
    parts = list(rel.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def file_role(path: Path, text: str) -> str:
    parts = {p.lower() for p in path.parts}
    name = path.name.lower()
    if name == "main.py":
        return "Entry point"
    if name == "__init__.py":
        return "Package init"
    if "handlers" in parts:
        return "Router • Text/UI"
    if "keyboards" in parts:
        return "UI helper"
    if "services" in parts and "schedule" in name:
        return "Schedule/Calendar"
    if "services" in parts:
        return "Service"
    if "core" in parts:
        return "Core"
    if "utils" in parts:
        return "Utility"
    if "storage" in parts:
        return "Storage/IO"
    if "config" in parts or "config_paths.py" == name:
        return "Config"
    low = (text or "").lower()
    if "beautifulsoup" in low or "requests" in low:
        return "Parser"
    if "from pil" in low or "imagefont" in low or "imagedraw" in low:
        return "Renderer/Banner"
    if "schedule" in name:
        return "Schedule/Calendar"
    if "broadcast" in name:
        return "Broadcast"
    if "features" in name:
        return "Feature flags"
    if "chatgpt" in name:
        return "ChatGPT stub"
    return "Module"


def build_tree_summary(files_meta):
    dirs = defaultdict(lambda: {"count": 0, "size": 0, "mtime": 0.0})
    for meta in files_meta:
        d = str(meta["rel_parent"])
        rec = dirs[d]
        rec["count"] += 1
        rec["size"] += meta["size"]
        rec["mtime"] = max(rec["mtime"], meta["mtime"])
    return dirs


def _match_globs(rel: Path, patterns: list[str]) -> bool:
    s = str(rel).replace("\\", "/")
    for g in patterns or []:
        if fnmatch.fnmatch(s, g):
            return True
    return False


def _match_keywords(name: str, text: str, kws: list[str]) -> bool:
    s1 = (name or "").lower()
    s2 = (text or "").lower()
    for k in kws or []:
        k = (k or "").lower()
        if not k:
            continue
        if k in s1 or k in s2:
            return True
    return False


def _match_roles(role: str, roles: list[str]) -> bool:
    role = role or ""
    return any(r.lower() in role.lower() for r in (roles or []))


def resolve_topics_to_seeds(topic_tokens: list[str], files_meta, project_root: Path):
    agg = {"keywords_any": [], "roles_any": [], "paths_any": []}
    for raw in topic_tokens:
        t = (raw or "").strip()
        if not t:
            continue
        if t.startswith("p:"):
            agg["paths_any"].append(t[2:].strip())
            continue
        if t.startswith("r:"):
            agg["roles_any"].append(t[2:].strip())
            continue
        if t.startswith("k:"):
            agg["keywords_any"].append(t[2:].strip())
            continue
        key = t.lower()
        if key in DEFAULT_TOPICS:
            cfg = DEFAULT_TOPICS[key]
            agg["keywords_any"] += cfg.get("keywords_any", [])
            agg["roles_any"] += cfg.get("roles_any", [])
            agg["paths_any"] += cfg.get("paths_any", [])
        else:
            agg["keywords_any"].append(t)
    seeds = set()
    for m in files_meta:
        match = (
            _match_globs(m["rel"], agg["paths_any"]) or
            _match_roles(m.get("role", ""), agg["roles_any"]) or
            _match_keywords(m["name"], m.get("text", ""), agg["keywords_any"])
        )
        if match:
            seeds.add(m["path"])
    return seeds


def expand_by_deps(seeds_paths: set[Path], module_by_path: dict, imported_by: dict, imports_local: dict, project_root: Path, mode: str = "both", depth: int = 2):
    if mode == "none" or depth <= 0:
        return set(seeds_paths)
    seeds_mods = set()
    path_by_mod = {}
    for p, mod in module_by_path.items():
        path_by_mod[mod] = p
    for p in seeds_paths:
        mod = module_by_path.get(p)
        if mod:
            seeds_mods.add(mod)
    visited = set(seeds_mods)
    frontier = list(seeds_mods)
    result_mods = set(seeds_mods)

    def outgoing(mod: str) -> set[str]:
        outs = set()
        for token in imports_local.get(mod, set()):
            base = token.lstrip(".").split(".")[-1]
            for mname, path in path_by_mod.items():
                if mname.split(".")[-1] == base:
                    outs.add(mname)
        return outs

    def incoming(mod: str) -> set[str]:
        return set(imported_by.get(mod, set()))

    for _ in range(depth):
        new_frontier = []
        for mod in frontier:
            nxt = set()
            if mode in ("out", "both"):
                nxt |= outgoing(mod)
            if mode == "both":
                nxt |= incoming(mod)
            for nm in nxt:
                if nm not in visited:
                    visited.add(nm)
                    result_mods.add(nm)
                    new_frontier.append(nm)
        frontier = new_frontier
        if not frontier:
            break
    out_paths = set()
    for mod in result_mods:
        p = path_by_mod.get(mod)
        if p:
            out_paths.add(p)
    for p in seeds_paths:
        out_paths.add(p)
    return out_paths


def generate_report(project_root: Path, report_path: Path, script_path: Path, mode: str = "full", topics: list[str] | None = None, deps_mode: str = "both", deps_depth: int = 2):
    files = sorted(collect_files(project_root, script_path))
    files_meta = []
    for p in files:
        try:
            st = p.stat()
            size = st.st_size
            mtime = st.st_mtime
        except Exception:
            size = 0
            mtime = 0
        rel = p.relative_to(project_root)
        text = ""
        if p.suffix.lower() == ".py":
            text = read_text(p)
        files_meta.append({
            "path": p,
            "rel": rel,
            "rel_parent": rel.parent,
            "name": p.name,
            "ext": p.suffix.lower(),
            "size": size,
            "mtime": mtime,
            "text": text if p.suffix.lower() == ".py" else "",
        })
    module_by_path = {}
    basename_to_modules = defaultdict(set)
    for m in files_meta:
        if m["ext"] == ".py":
            mod = module_basename_from_path(project_root, m["path"])
            module_by_path[m["path"]] = mod
            basename_to_modules[m["path"].stem].add(mod)
    imports_local = defaultdict(set)
    imported_by = defaultdict(set)
    for m in files_meta:
        if m["ext"] != ".py":
            continue
        me = module_by_path.get(m["path"])
        text = m["text"] or read_text(m["path"])
        loc, _ext = extract_imports(text)
        if me:
            imports_local[me].update(loc)
        for token in loc:
            base_token = token.lstrip(".").split(".")[-1]
            for target_mod in basename_to_modules.get(base_token, ()):
                if me and target_mod != me:
                    imported_by[target_mod].add(me)
    for m in files_meta:
        role = "Asset"
        if m["ext"] == ".py":
            role = file_role(m["path"], m["text"])
        elif m["ext"] in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
            role = "Image asset"
        elif m["ext"] in {".ttf", ".otf"}:
            role = "Font"
        elif m["ext"] in {".sqlite", ".sqlite3", ".db"}:
            role = "Database file"
        elif m["ext"] == ".txt":
            role = "Text asset"
        m["role"] = role
    selected_paths = None
    if mode == "partial":
        seeds = resolve_topics_to_seeds(topics or [], files_meta, project_root)
        selected_paths = expand_by_deps(
            seeds_paths=seeds,
            module_by_path=module_by_path,
            imported_by=imported_by,
            imports_local=imports_local,
            project_root=project_root,
            mode=deps_mode,
            depth=deps_depth
        )

    def _iter_selected(metas):
        if selected_paths is None:
            for m in metas:
                yield m
        else:
            for m in metas:
                if m["path"] in selected_paths:
                    yield m

    visible_meta = list(_iter_selected(files_meta))
    dirs = build_tree_summary(visible_meta)
    name_to_paths = defaultdict(list)
    for m in visible_meta:
        name_to_paths[m["name"]].append(m["rel"])
    duplicates = {k: v for k, v in name_to_paths.items() if len(v) > 1}
    sus_list = []
    for m in visible_meta:
        if m["ext"] != ".py":
            continue
        if m["name"] in ("__init__.py", "main.py"):
            continue
        mod = module_by_path.get(m["path"])
        if not imported_by.get(mod):
            sus_list.append(m)
    with report_path.open("w", encoding="utf-8", newline="") as rep:
        rep.write(f"База проекта: {project_root}\n")
        rep.write(f"Сформировано: {fmt_ts(time.time())}\n")
        if mode == "partial":
            rep.write("Режим: НЕПОЛНЫЙ\n")
            rep.write(f"Темы/паттерны: {', '.join(topics or [])}\n")
            rep.write(f"Зависимости: {deps_mode}, глубина={deps_depth}\n")
        else:
            rep.write("Режим: ПОЛНЫЙ\n")
        rep.write("\n")
        rep.write("=== Сводка по папкам ===\n")
        for d in sorted(dirs.keys()):
            rec = dirs[d]
            rep.write(f"{d or '.'} — файлов: {rec['count']}, размер: {fmt_size(rec['size'])}, последняя правка: {fmt_ts(rec['mtime']) if rec['mtime'] else '-'}\n")
        rep.write("\n")
        rep.write("=== Дубликаты по имени файла (в разных папках) ===\n")
        if duplicates:
            for name, paths in sorted(duplicates.items()):
                rep.write(f"{name}:\n")
                for p in paths:
                    rep.write(f"    {p}\n")
        else:
            rep.write("Нет дубликатов.\n")
        rep.write("\n")
        rep.write("=== Подозрительные .py (не импортируются другими) ===\n")
        if sus_list:
            for m in sorted(sus_list, key=lambda x: str(x["rel"])):
                rep.write(f"{m['rel']}  [{m['role']}]  size={fmt_size(m['size'])}  mtime={fmt_ts(m['mtime'])}\n")
        else:
            rep.write("Нет.\n")
        rep.write("\n")
        rep.write("=== Структура ===\n")
        for m in sorted(visible_meta, key=lambda x: (str(x["rel_parent"]), x["name"])):
            depth = len(m["rel"].parents) - 1
            indent = "    " * depth
            rep.write(f"{indent}{m['name']}  [{m['role']}]  ({fmt_size(m['size'])}, {fmt_ts(m['mtime'])})\n")
        rep.write("\n")
        rep.write("=== Файлы ===\n\n")
        for idx, m in enumerate(sorted(visible_meta, key=lambda x: str(x["rel"])), 1):
            rep.write(f"{idx}. {m['rel']}  ({fmt_size(m['size'])}, {fmt_ts(m['mtime'])})\n")
            rep.write(f"   Роль: {m['role']}\n")
            if m["ext"] == ".py":
                me = module_by_path.get(m["path"])
                loc = sorted(imports_local.get(me, [])) if me else []
                imp_by = sorted(imported_by.get(me, [])) if me else []
                if loc:
                    rep.write(f"   Импорты (локальные): {', '.join(loc)}\n")
                if imp_by:
                    rep.write(f"   Импортируется модулями: {', '.join(imp_by)}\n")
            if m["ext"] == ".py" and _is_hidden_code(project_root, m["path"]):
                rep.write("Код:\n[Скрыт по настройке]\n")
            else:
                rep.write("Код:\n")
                content = read_text(m["path"]) if m["ext"] != ".py" else (m["text"] or read_text(m["path"]))
                rep.write(content)
                if not content.endswith("\n"):
                    rep.write("\n")
            rep.write("\n")
    print(f"Отчёт сохранён: {report_path}")


def auto_detect_root(start: Path) -> Path:
    current = start
    for _ in range(5):
        app_dir = current / "app"
        main_py = current / "main.py"
        if app_dir.is_dir() and main_py.is_file():
            return current
        current = current.parent
    return start


def parse_args():
    parser = argparse.ArgumentParser(
        description="Собрать отчёт по проекту (структура, роли, импорты, содержимое). По умолчанию — полный отчёт."
    )
    parser.add_argument(
        "-r",
        "--root",
        default=None,
        help="Корень проекта (по умолчанию определяется автоматически по папке app/ и main.py).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Имя файла-отчёта. Если относительный путь — создаётся в корне проекта.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Полный отчёт по всем файлам проекта.",
    )
    mode_group.add_argument(
        "--partial",
        action="store_true",
        help="Отчёт только по выбранным темам (--topic).",
    )
    parser.add_argument(
        "-t",
        "--topic",
        action="append",
        default=None,
        help="Тема/паттерн. Можно указывать несколько раз. "
             "Примеры: расписание, группы, k:parse_schedule, p:app/services/*.py, r:Service",
    )
    parser.add_argument(
        "--deps",
        choices=["none", "out", "both"],
        default="both",
        help="Как добавлять зависимости по импортам в режиме partial (по умолчанию both).",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Глубина добавления зависимостей по импортам (по умолчанию 2).",
    )
    parser.add_argument(
        "--list-topics",
        action="store_true",
        help="Показать доступные встроенные темы и выйти.",
    )
    return parser.parse_args()


def print_topics():
    print("Доступные темы:")
    for k in DEFAULT_TOPICS.keys():
        print(" •", k)
    print("\nМожно также использовать:")
    print("  k:слово   — поиск по имени файла и коду")
    print("  r:Роль    — поиск по роли (Service, Schedule/Calendar, Router • Text/UI, ...)")
    print("  p:glob    — поиск по glob-пути (например, app/services/*.py)")


def main():
    args = parse_args()
    if args.list_topics:
        print_topics()
        return
    script_path = Path(__file__).resolve()
    if args.root:
        project_root = Path(args.root).resolve()
    else:
        project_root = auto_detect_root(script_path.parent)
    if args.full:
        mode = "full"
    elif args.partial or (args.topic is not None and len(args.topic) > 0):
        mode = "partial"
    else:
        mode = "full"
    topics = args.topic or []
    if mode == "partial" and not topics:
        print("Режим partial выбран, но темы не указаны. Задайте хотя бы одну через --topic или используйте --full.")
        print_topics()
        return
    if args.output:
        report_path = Path(args.output)
        if not report_path.is_absolute():
            report_path = project_root / report_path
    else:
        suffix = "partial" if mode == "partial" else "full"
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = project_root / f"report_{suffix}_{ts}.txt"
    generate_report(
        project_root=project_root,
        report_path=report_path,
        script_path=script_path,
        mode=mode,
        topics=topics,
        deps_mode=args.deps,
        deps_depth=args.depth,
    )


if __name__ == "__main__":
    main()
