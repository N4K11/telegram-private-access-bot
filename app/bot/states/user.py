from aiogram.fsm.state import State, StatesGroup


class UserSupportForm(StatesGroup):
    waiting_for_message = State()
