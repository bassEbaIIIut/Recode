from contextlib import asynccontextmanager

from aiogram.fsm.context import FSMContext


@asynccontextmanager
async def preserve_state(state: FSMContext):
    """Remember the current FSM state and restore it after a command.

    The context manager is designed for short command handlers that should not
    change the conversation flow. If the handler leaves the FSM in another
    state, we return the user to the state that was active before the command
    was processed.
    """

    previous_state = await state.get_state()
    try:
        yield previous_state
    finally:
        if previous_state is None:
            return

        current_state = await state.get_state()
        if current_state != previous_state:
            await state.set_state(previous_state)
