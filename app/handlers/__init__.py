from app.handlers.start import router as start_router
from app.handlers.common import router as common_router
from app.handlers.schedule import router as schedule_router
from app.handlers.admin import router as admin_router
from app.handlers.homework import router as homework_router


def get_routers():
    return (
        start_router,
        common_router,
        schedule_router,
        admin_router,
        homework_router,
    )
