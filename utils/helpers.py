#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Вспомогательные функции
"""

from datetime import datetime, timedelta
from config import TEACHER_CODE
from database import Database

db = Database()

async def is_teacher(user_id):
    """Проверить, является ли пользователь преподавателем"""
    user = await db.get_user(user_id)
    return user and user['role'] == 'teacher'

def format_homework_list(homework_list, is_teacher=False):
    """Форматировать список домашних заданий"""
    if not homework_list:
        return "📝 <b>Домашних заданий пока нет</b>"

    text = "📝 <b>Домашние задания:</b>\n\n"

    for hw in homework_list:
        status_emoji = "✅" if hw['status'] == 'submitted' else "📝"
        if is_teacher:
            status_emoji = "✅" if hw.get('submission_count', 0) > 0 else "📝"

        text += f"{status_emoji} <b>{hw['title']}</b>\n"
        text += f"📅 Срок: {hw['due_date'] or 'Не указан'}\n"

        if hw.get('grade'):
            text += f"⭐ Оценка: {hw['grade']}/5\n"
        elif hw['status'] == 'submitted':
            text += "⏳ Ожидает проверки\n"

        text += "\n"

    return text

def format_schedule(schedule):
    """Форматировать расписание"""
    if not schedule:
        return "📅 <b>Расписание пустое</b>"

    days = ["", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    text = "📅 <b>Ваше расписание:</b>\n\n"

    current_day = None
    for entry in schedule:
        if entry['day_of_week'] != current_day:
            current_day = entry['day_of_week']
            text += f"📅 <b>{days[current_day]}</b>\n"

        text += f"⏰ {entry['time']} - {entry['subject']}"
        if entry['group_name']:
            text += f" (группа: {entry['group_name']})"
        text += f" ({entry['duration']} мин)\n"

    return text

def get_current_week_dates():
    """Получить даты текущей недели"""
    today = datetime.now()
    days = []

    # Найти понедельник текущей недели
    monday = today - timedelta(days=today.weekday())

    for i in range(7):
        day = monday + timedelta(days=i)
        days.append(day.strftime("%d.%m.%Y"))

    return days

def validate_time_format(time_str):
    """Проверить формат времени"""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False

def get_file_extension(filename):
    """Получить расширение файла"""
    return filename.split('.')[-1].lower() if '.' in filename else ''

def is_valid_file_type(filename):
    """Проверить, допустимый ли тип файла"""
    allowed_extensions = ['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png', 'zip']
    return get_file_extension(filename) in allowed_extensions

def format_file_size(size_bytes):
    """Форматировать размер файла"""
    if size_bytes < 1024:
        return f"{size_bytes} байт"
    elif size_bytes < 1024**2:
        return f"{size_bytes/1024:.1f} КБ"
    else:
        return f"{size_bytes/(1024**2):.1f} МБ"