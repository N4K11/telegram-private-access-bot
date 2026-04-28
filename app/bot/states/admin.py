from aiogram.fsm.state import State, StatesGroup


class AdminTextEditor(StatesGroup):
    waiting_for_key = State()
    waiting_for_value = State()
