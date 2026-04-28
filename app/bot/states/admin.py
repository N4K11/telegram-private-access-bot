from aiogram.fsm.state import State, StatesGroup


class AdminTextEditor(StatesGroup):
    waiting_for_key = State()
    waiting_for_value = State()


class AdminChannelForm(StatesGroup):
    waiting_for_reference = State()
    waiting_for_title = State()


class AdminTariffForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_days = State()
    waiting_for_channel = State()
    waiting_for_new_name = State()
    waiting_for_new_price = State()
    waiting_for_new_days = State()
    waiting_for_new_sort = State()
    waiting_for_new_channel = State()


class AdminUserForm(StatesGroup):
    waiting_for_direct_message = State()


class AdminBroadcastForm(StatesGroup):
    waiting_for_content = State()