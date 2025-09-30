#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы с базой данных
"""

import sqlite3
import aiosqlite
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path="bot_database.db"):
        self.db_path = db_path

    async def init(self):
        """Инициализация базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    role TEXT DEFAULT 'student',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица групп
            await db.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица участников групп
            await db.execute("""
                CREATE TABLE IF NOT EXISTS group_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    user_id INTEGER,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES groups (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            # Таблица домашних заданий
            await db.execute("""
                CREATE TABLE IF NOT EXISTS homework (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    group_id INTEGER,
                    user_id INTEGER,
                    due_date TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES groups (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            # Таблица сданных работ
            await db.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    homework_id INTEGER,
                    user_id INTEGER,
                    file_path TEXT,
                    text_content TEXT,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    grade INTEGER,
                    feedback TEXT,
                    FOREIGN KEY (homework_id) REFERENCES homework (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            # Таблица расписания
            await db.execute("""
                CREATE TABLE IF NOT EXISTS schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    group_id INTEGER,
                    day_of_week INTEGER,
                    time TEXT,
                    duration INTEGER DEFAULT 60,
                    subject TEXT DEFAULT 'Английский язык',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (group_id) REFERENCES groups (id)
                )
            """)

            await db.commit()
            logger.info("База данных инициализирована")

    async def add_user(self, user_id, username, first_name, last_name):
        """Добавить пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, first_name, last_name))
            await db.commit()

    async def get_user(self, user_id):
        """Получить пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT * FROM users WHERE user_id = ?
            """, (user_id,))
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0], "user_id": row[1], "username": row[2],
                    "first_name": row[3], "last_name": row[4], "role": row[5]
                }
            return None

    async def set_user_role(self, user_id, role):
        """Установить роль пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users SET role = ? WHERE user_id = ?
            """, (role, user_id))
            await db.commit()

    async def create_group(self, name, description=""):
        """Создать группу"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO groups (name, description) VALUES (?, ?)
            """, (name, description))
            await db.commit()
            return cursor.lastrowid

    async def get_all_groups(self):
        """Получить все группы"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT g.*, COUNT(gm.user_id) as member_count
                FROM groups g
                LEFT JOIN group_members gm ON g.id = gm.group_id
                GROUP BY g.id
                ORDER BY g.created_at DESC
            """)
            rows = await cursor.fetchall()
            return [{
                "id": row[0], "name": row[1], "description": row[2],
                "created_at": row[3], "member_count": row[4]
            } for row in rows]

    async def get_user_groups(self, user_id):
        """Получить группы пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT g.*, COUNT(gm2.user_id) as member_count
                FROM groups g
                JOIN group_members gm ON g.id = gm.group_id
                LEFT JOIN group_members gm2 ON g.id = gm2.group_id
                WHERE gm.user_id = ?
                GROUP BY g.id
            """, (user_id,))
            rows = await cursor.fetchall()
            return [{
                "id": row[0], "name": row[1], "description": row[2],
                "created_at": row[3], "member_count": row[4]
            } for row in rows]

    async def add_user_to_group(self, group_id, user_id):
        """Добавить пользователя в группу"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)
            """, (group_id, user_id))
            await db.commit()

    async def get_group_members(self, group_id):
        """Получить участников группы"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT u.user_id, u.first_name, u.last_name, u.username
                FROM users u
                JOIN group_members gm ON u.user_id = gm.user_id
                WHERE gm.group_id = ?
            """, (group_id,))
            rows = await cursor.fetchall()
            return [{
                "user_id": row[0], "first_name": row[1],
                "last_name": row[2], "username": row[3]
            } for row in rows]

    async def get_group_info(self, group_id):
        """Получить информацию о группе"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT * FROM groups WHERE id = ?
            """, (group_id,))
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0], "name": row[1], "description": row[2], "created_at": row[3]
                }
            return None

    async def create_homework(self, title, description, group_id=None, user_id=None, due_date=None):
        """Создать домашнее задание"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO homework (title, description, group_id, user_id, due_date)
                VALUES (?, ?, ?, ?, ?)
            """, (title, description, group_id, user_id, due_date))
            await db.commit()
            return cursor.lastrowid

    async def get_user_homework(self, user_id):
        """Получить домашние задания пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT h.*, s.grade, s.submitted_at,
                       CASE WHEN s.id IS NOT NULL THEN 'submitted' ELSE 'pending' END as status
                FROM homework h
                LEFT JOIN submissions s ON h.id = s.homework_id AND s.user_id = ?
                WHERE h.user_id = ? OR h.group_id IN (
                    SELECT group_id FROM group_members WHERE user_id = ?
                )
                ORDER BY h.due_date ASC
            """, (user_id, user_id, user_id))
            rows = await cursor.fetchall()
            return [{
                "id": row[0], "title": row[1], "description": row[2],
                "group_id": row[3], "user_id": row[4], "due_date": row[5],
                "created_at": row[6], "grade": row[7], "submitted_at": row[8], "status": row[9]
            } for row in rows]

    async def get_homework_details(self, homework_id):
        """Получить детали домашнего задания"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT h.*, s.grade, s.submitted_at,
                       CASE WHEN s.id IS NOT NULL THEN 'submitted' ELSE 'pending' END as status
                FROM homework h
                LEFT JOIN submissions s ON h.id = s.homework_id
                WHERE h.id = ?
            """, (homework_id,))
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0], "title": row[1], "description": row[2],
                    "group_id": row[3], "user_id": row[4], "due_date": row[5],
                    "created_at": row[6], "grade": row[7], "submitted_at": row[8], "status": row[9]
                }
            return None

    async def get_all_homework(self):
        """Получить все домашние задания"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT h.*, COUNT(s.id) as submission_count
                FROM homework h
                LEFT JOIN submissions s ON h.id = s.homework_id
                GROUP BY h.id
                ORDER BY h.created_at DESC
            """)
            rows = await cursor.fetchall()
            return [{
                "id": row[0], "title": row[1], "description": row[2],
                "group_id": row[3], "user_id": row[4], "due_date": row[5],
                "created_at": row[6], "submission_count": row[7]
            } for row in rows]

    async def submit_homework(self, homework_id, user_id, file_path=None, text_content=None):
        """Сдать домашнее задание"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO submissions (homework_id, user_id, file_path, text_content)
                VALUES (?, ?, ?, ?)
            """, (homework_id, user_id, file_path, text_content))
            await db.commit()

    async def set_grade(self, homework_id, user_id, grade, feedback=None):
        """Поставить оценку"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE submissions SET grade = ?, feedback = ?
                WHERE homework_id = ? AND user_id = ?
            """, (grade, feedback, homework_id, user_id))
            await db.commit()

    async def create_schedule_entry(self, user_id, group_id, day_of_week, time, duration=60):
        """Создать запись в расписании"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO schedule (user_id, group_id, day_of_week, time, duration)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, group_id, day_of_week, time, duration))
            await db.commit()
            return cursor.lastrowid

    async def get_user_schedule(self, user_id):
        """Получить расписание пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT s.*, g.name as group_name
                FROM schedule s
                LEFT JOIN groups g ON s.group_id = g.id
                WHERE s.user_id = ? OR s.group_id IN (
                    SELECT group_id FROM group_members WHERE user_id = ?
                )
                ORDER BY s.day_of_week, s.time
            """, (user_id, user_id))
            rows = await cursor.fetchall()
            return [{
                "id": row[0], "user_id": row[1], "group_id": row[2],
                "day_of_week": row[3], "time": row[4], "duration": row[5],
                "subject": row[6], "created_at": row[7], "group_name": row[8]
            } for row in rows]

    async def close(self):
        """Закрыть соединение с базой данных"""
        pass