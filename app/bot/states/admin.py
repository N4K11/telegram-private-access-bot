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
    waiting_for_new_badge = State()
    waiting_for_new_channel = State()


class AdminUserForm(StatesGroup):
    waiting_for_direct_message = State()


class AdminBroadcastForm(StatesGroup):
    waiting_for_content = State()
    waiting_for_template_name = State()


class AdminSupportForm(StatesGroup):
    waiting_for_reply = State()


class AdminAuditForm(StatesGroup):
    waiting_for_target_user = State()
    waiting_for_actor_user = State()
    waiting_for_action = State()


class AdminRoleForm(StatesGroup):
    waiting_for_user_reference = State()
