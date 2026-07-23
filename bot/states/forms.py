"""
Finite State Machine (FSM) для многошаговых форм.
Регистрация, инциденты, handover и т.д.
"""
from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):
    """Состояния регистрации нового пользователя."""
    waiting_fio = State()        # Шаг 1: ввод ФИО
    waiting_role = State()       # Шаг 2: выбор должности
    waiting_confirm = State()    # Шаг 3: подтверждение
    waiting_admin_approval = State()  # Ожидание одобрения admin


class IncidentState(StatesGroup):
    """Состояния создания инцидента."""
    waiting_type = State()
    waiting_datetime = State()
    waiting_location = State()
    waiting_description = State()
    waiting_photos = State()
    waiting_witnesses = State()
    waiting_status = State()


class HandoverState(StatesGroup):
    """Состояния создания передачи смены."""
    waiting_message = State()
    waiting_photos = State()
    waiting_importance = State()
    waiting_tags = State()


class AdminBroadcastState(StatesGroup):
    """Рассылка от администратора."""
    waiting_type = State()      # Тип рассылки: text / promo / event
    waiting_text = State()      # Текст рассылки (для type=text)
    waiting_target = State()    # Целевая аудитория
    waiting_confirm = State()   # Подтверждение


class AdminEditRoleState(StatesGroup):
    """Смена роли пользователя."""
    waiting_new_role = State()


class AdminEditPositionState(StatesGroup):
    """Смена должности пользователя."""
    waiting_new_position = State()


class AdminCreateUserState(StatesGroup):
    """Создание нового пользователя (admin/owner)."""
    waiting_name = State()
    waiting_position = State()


class EventAddBookingState(StatesGroup):
    """FSM для добавления брони."""
    waiting_name = State()
    waiting_date = State()
    waiting_time = State()
    waiting_guests = State()
    waiting_phone = State()
    waiting_comment = State()


class EventAddAnnouncementState(StatesGroup):
    """FSM для добавления анонса."""
    waiting_title = State()
    waiting_date = State()
    waiting_description = State()


class PromoEditState(StatesGroup):
    """FSM для редактирования описания акции."""
    waiting_description = State()


class TaskCreateState(StatesGroup):
    """FSM создания задачи (manager/admin)."""
    waiting_title = State()
    waiting_description = State()
    waiting_dept = State()
    waiting_user = State()
    waiting_priority = State()
    waiting_deadline = State()
    waiting_photo = State()


class TaskCompleteState(StatesGroup):
    """FSM выполнения задачи (worker)."""
    waiting_comment = State()
    waiting_photo = State()


class TaskSelfLogState(StatesGroup):
    """FSM самофиксации выполненной задачи (worker)."""
    waiting_title = State()
    waiting_description = State()
    waiting_photo = State()


class TaskCommentState(StatesGroup):
    """FSM добавления комментария к задаче (manager)."""
    waiting_text = State()


class TaskReassignState(StatesGroup):
    """FSM переназначения задачи (manager) — ручной ввод даты дедлайна."""
    waiting_deadline_text = State()


class MenuPhotoUploadState(StatesGroup):
    """FSM загрузки фото для позиции меню (admin)."""
    waiting_photo = State()
