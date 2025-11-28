from aiogram.fsm.state import StatesGroup, State


class MenuStates(StatesGroup):
    MAIN = State()
    SCHEDULE = State()


class HomeworkStates(StatesGroup):
    MENU = State()
    PERSONAL_MENU = State()
    PERSONAL_EDITOR_MENU = State()
    PERSONAL_ADD_SELECT_PAIR = State()
    PERSONAL_ADD_WAIT_CONTENT = State()
    PERSONAL_EDIT_SELECT_SUBJECT = State()
    PERSONAL_EDIT_SELECT_ACTION = State()
    PERSONAL_EDIT_WAIT_TEXT = State()
    PERSONAL_NOTIFICATIONS_MENU = State()
    PUBLIC_MENU = State()
    PUBLIC_SUGGEST_WAIT_PAIR = State()
    PUBLIC_SUGGEST_WAIT_CONTENT = State()


class PersonalCabinetStates(StatesGroup):
    MENU = State()
    SETTINGS = State()
    SETTINGS_WAIT_GROUP = State()


class AdminAuthStates(StatesGroup):
    waiting_for_password = State()


class AdminStates(StatesGroup):
    MAIN = State()
    USER_SYSTEM_MENU = State()
    USER_SEARCH = State()
    SCHEDULE_MENU = State()
    LOGS_MENU = State()
    BROADCAST_WAIT_MESSAGE = State()
    BAN_MENU = State()
    BAN_WAIT_USER = State()
    UNBAN_WAIT_USER = State()
    CATEGORIES_SELECT = State()
    CATEGORIES_CATEGORY_MENU = State()
    CATEGORY_EDIT_TEXT = State()
    MAILING_MENU = State()
    MAILING_BLOCK_WAIT_USER = State()
    MAILING_UNBLOCK_WAIT_USER = State()
    LOGS_WAIT_LINES = State()
    LOGS_WAIT_USER_ERRORS_LINES = State()
    HOMEWORK_MENU = State()
    HOMEWORK_PENDING_MENU = State()
    HOMEWORK_AI_MENU = State()
    HOMEWORK_AI_EDIT_PROMPT = State()
    HOMEWORK_STEWARDS_MENU = State()
    HOMEWORK_STEWARDS_ADD = State()
    HOMEWORK_STEWARDS_REMOVE = State()