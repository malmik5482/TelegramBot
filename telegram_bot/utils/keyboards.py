#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль клавиатур для телеграм-бота
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu():
    """Главное меню выбора роли"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩‍🎓 Я ученик", callback_data="role_student")],
        [InlineKeyboardButton(text="👩‍🏫 Я преподаватель", callback_data="role_teacher")]
    ])
    return keyboard

def get_student_menu():
    """Меню ученика"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Мои группы", callback_data="my_groups")],
        [InlineKeyboardButton(text="📝 Домашние задания", callback_data="my_homework")],
        [InlineKeyboardButton(text="📅 Расписание", callback_data="my_schedule")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    return keyboard

def get_teacher_menu():
    """Меню преподавателя"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление группами", callback_data="manage_groups")],
        [InlineKeyboardButton(text="📝 Домашние задания", callback_data="manage_homework")],
        [InlineKeyboardButton(text="📅 Расписание", callback_data="manage_schedule")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="view_statistics")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    return keyboard

def get_groups_keyboard(groups, is_teacher=False, show_members=False):
    """Клавиатура для работы с группами"""
    keyboard = []
    
    if is_teacher:
        keyboard.append([InlineKeyboardButton(text="➕ Создать группу", callback_data="create_group")])
        
        for group in groups:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📚 {group['name']} ({group['member_count']} чел.)",
                    callback_data=f"manage_group_{group['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_teacher")])
    else:
        for group in groups:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📚 {group['name']}",
                    callback_data=f"group_{group['id']}"
                )
            ])
        
        if show_members:
            keyboard.append([InlineKeyboardButton(text="💬 Написать сообщение", callback_data="send_group_message")])
        
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_student")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_homework_keyboard(homework_list, is_teacher=False, detailed=False):
    """Клавиатура для работы с домашними заданиями"""
    keyboard = []
    
    if is_teacher:
        keyboard.append([InlineKeyboardButton(text="➕ Создать задание", callback_data="create_homework")])
        
        for hw in homework_list[:5]:  # Показываем первые 5
            status_emoji = "✅" if hw.get('submission_count', 0) > 0 else "📝"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_emoji} {hw['title'][:30]}{'...' if len(hw['title']) > 30 else ''}",
                    callback_data=f"hw_manage_{hw['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_teacher")])
    else:
        for hw in homework_list[:5]:  # Показываем первые 5
            status_emoji = "✅" if hw['status'] == 'submitted' else "📝"
            grade_text = f" ({hw['grade']}/5)" if hw['grade'] else ""
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_emoji} {hw['title'][:25]}{'...' if len(hw['title']) > 25 else ''}{grade_text}",
                    callback_data=f"homework_{hw['id']}"
                )
            ])
        
        if detailed:
            keyboard.append([InlineKeyboardButton(text="📎 Сдать работу", callback_data="submit_homework")])
        
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_student")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_schedule_keyboard():
    """Клавиатура для расписания"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 На эту неделю", callback_data="schedule_week")],
        [InlineKeyboardButton(text="📆 На следующую неделю", callback_data="schedule_next_week")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_student")]
    ])
    return keyboard

def get_back_keyboard(callback_data="back_to_main"):
    """Простая клавиатура с кнопкой назад"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]
    ])
    return keyboard

def get_grade_keyboard(homework_id, user_id):
    """Клавиатура для выставления оценок"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data=f"grade_{homework_id}_{user_id}_1"),
            InlineKeyboardButton(text="2", callback_data=f"grade_{homework_id}_{user_id}_2"),
            InlineKeyboardButton(text="3", callback_data=f"grade_{homework_id}_{user_id}_3"),
            InlineKeyboardButton(text="4", callback_data=f"grade_{homework_id}_{user_id}_4"),
            InlineKeyboardButton(text="5", callback_data=f"grade_{homework_id}_{user_id}_5")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_homework")]
    ])
    return keyboard

def get_days_keyboard():
    """Клавиатура выбора дней недели"""
    days = [
        ("Понедельник", 1), ("Вторник", 2), ("Среда", 3),
        ("Четверг", 4), ("Пятница", 5), ("Суббота", 6), ("Воскресенье", 7)
    ]
    keyboard = []
    for day_name, day_num in days:
        keyboard.append([InlineKeyboardButton(text=day_name, callback_data=f"day_{day_num}")])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_teacher")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)