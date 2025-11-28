from typing import Optional


class AppContext:
    def __init__(self, db, group_resolver, schedule_service, admin_service=None, storage=None, homework_service=None):
        self.db = db
        self.group_resolver = group_resolver
        self.schedule_service = schedule_service
        self.admin_service = admin_service
        self.storage = storage
        self.homework_service = homework_service


_context: Optional[AppContext] = None


def set_context(ctx: AppContext) -> None:
    global _context
    _context = ctx


def get_context() -> AppContext:
    if _context is None:
        raise RuntimeError("App context is not initialized")
    return _context
