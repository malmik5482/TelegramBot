#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Телеграм-бот для преподавателя английского языка Саликовой Ольги Александровны
Автор: AI Assistant
Дата: 30.09.2025
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, Document, PhotoSize
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

# Импорты модулей проекта
try:
    from config import BOT_TOKEN, TEACHER_CODE
    from database import Database
    from utils.keyboards import (
        get_main_menu, get_teacher_menu, get_student_menu,
        get_groups_keyboard, get_homework_keyboard, get_schedule_keyboard,
        get_back_keyboard, get_grade_keyboard, get_days_keyboard
    )
    from utils.helpers import (
        is_teacher, format_homework_list, format_schedule,
        validate_time_format, is_valid_file_type, format_file_size
    )
except ImportError as e:
    print(f"Ошибка импорта модулей: {e}")
    print("Убедитесь, что все файлы проекта находятся в одной директории")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Состояния FSM
class TeacherStates(StatesGroup):
    waiting_for_teacher_code = State()
    creating_group = State()
    adding_student_to_group = State()
    adding_homework = State()
    adding_homework_description = State()
    adding_homework_due_date = State()
    setting_grade = State()
    creating_schedule = State()
    setting_schedule_time = State()

class StudentStates(StatesGroup):
    submitting_homework = State()
    messaging_classmate = State()

# Инициализация базы данных
db = Database()

# Создание директории для файлов
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    
    # Регистрируем пользователя в базе данных
    await db.add_user(user_id, username, first_name, last_name)
    
    welcome_text = f"""
🌟 <b>Добро пожаловать в образовательный бот!</b> 🌟

👩‍🏫 <b>Саликова Ольга Александровна</b>
🇬🇧 Преподаватель английского языка

<i>Этот бот поможет сделать обучение более организованным и эффективным!</i>

✨ <b>Возможности для учеников:</b>
📚 Просмотр групп и общение с одноклассниками
📝 Получение и сдача домашних заданий
📅 Персональное расписание занятий
⭐ Отслеживание оценок и прогресса

✨ <b>Возможности для преподавателя:</b>
👥 Управление группами учеников
📋 Создание и проверка домашних заданий
📊 Выставление оценок и обратная связь
🗺️ Планирование расписания занятий

Выберите свою роль для начала работы:
"""
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu()
    )

@router.callback_query(F.data == "role_student")
async def select_student_role(callback: CallbackQuery):
    """Выбор роли ученика"""
    await callback.message.edit_text(
        "🎓 <b>Добро пожаловать, ученик!</b>\n\n"
        "Здесь вы можете:\n"
        "• 👥 Просматривать свои группы\n"
        "• 📝 Выполнять домашние задания\n"
        "• 📅 Следить за расписанием\n"
        "• 💬 Общаться с одноклассниками\n\n"
        "Выберите действие:",
        reply_markup=get_student_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "role_teacher")
async def select_teacher_role(callback: CallbackQuery, state: FSMContext):
    """Выбор роли преподавателя"""
    await state.set_state(TeacherStates.waiting_for_teacher_code)
    await callback.message.edit_text(
        "👩‍🏫 <b>Вход для преподавателя</b>\n\n"
        "🔐 Для доступа к функциям преподавателя\n"
        "введите специальный код:",
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@router.message(TeacherStates.waiting_for_teacher_code)
async def check_teacher_code(message: Message, state: FSMContext):
    """Проверка кода преподавателя"""
    if message.text == TEACHER_CODE:
        user_id = message.from_user.id
        await db.set_user_role(user_id, 'teacher')
        await state.clear()
        
        await message.answer(
            "✅ <b>Добро пожаловать, Ольга Александровна!</b>\n\n"
            "🎯 Панель управления преподавателя активирована.\n"
            "Теперь вам доступны все функции управления:\n\n"
            "👥 Управление группами учеников\n"
            "📚 Создание домашних заданий\n"
            "⭐ Проверка работ и выставление оценок\n"
            "📅 Планирование расписания\n\n"
            "Выберите действие:",
            reply_markup=get_teacher_menu()
        )
    else:
        await message.answer(
            "❌ <b>Неверный код доступа!</b>\n\n"
            "🔑 Код доступа предназначен только для преподавателя.\n"
            "Если вы забыли код, обратитесь к администратору.\n\n"
            "Попробуйте еще раз:",
            reply_markup=get_back_keyboard()
        )

# Обработчики для учеников
@router.callback_query(F.data == "my_groups")
async def show_my_groups(callback: CallbackQuery):
    """Показать мои группы"""
    user_id = callback.from_user.id
    groups = await db.get_user_groups(user_id)
    
    if groups:
        text = "👥 <b>Ваши группы:</b>\n\n"
        for group in groups:
            text += f"📚 <b>{group['name']}</b>\n"
            text += f"👤 Участников: {group['member_count']}\n"
            text += f"📅 Создана: {group['created_at'][:10]}\n\n"
        
        text += "💡 <i>Выберите группу для просмотра участников</i>"
        keyboard = get_groups_keyboard(groups)
    else:
        text = (
            "😔 <b>Вы пока не состоите в группах</b>\n\n"
            "👩‍🏫 Обратитесь к Ольге Александровне для\n"
            "добавления в группу или записи на\n"
            "индивидуальные занятия.\n\n"
            "📞 Свяжитесь с преподавателем через\n"
            "этот бот или другими способами."
        )
        keyboard = get_back_keyboard("back_to_student")
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("group_"))
async def show_group_details(callback: CallbackQuery):
    """Показать детали группы"""
    group_id = int(callback.data.split("_")[1])
    group_info = await db.get_group_info(group_id)
    members = await db.get_group_members(group_id)
    
    if not group_info:
        await callback.answer("❌ Группа не найдена")
        return
    
    text = f"📚 <b>{group_info['name']}</b>\n\n"
    text += "👥 <b>Участники группы:</b>\n"
    
    for i, member in enumerate(members, 1):
        name = f"{member['first_name']} {member['last_name']}".strip()
        if not name:
            name = f"@{member['username']}" if member['username'] else f"Пользователь {member['user_id']}"
        text += f"{i}. {name}\n"
    
    text += f"\n📊 Всего участников: <b>{len(members)}</b>\n"
    text += f"📅 Дата создания: {group_info['created_at'][:10]}"
    
    keyboard = get_groups_keyboard([group_info], show_members=True)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()