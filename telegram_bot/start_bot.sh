#!/bin/bash

# Скрипт запуска телеграм-бота локально
# Автор: AI Assistant
# Дата: 30.09.2025

set -e

echo "=== Запуск телеграм-бота для преподавателя английского языка ==="

# Проверка Python
if ! command -v python3 &> /dev/null; then
  echo "Python3 не найден. Установите Python3 и повторите попытку."
  exit 1
fi

# Создание и активация виртуального окружения
if [ ! -d "venv" ]; then
  echo "Создаю виртуальное окружение..."
  python3 -m venv venv
fi
source venv/bin/activate

# Установка зависимостей
pip install --upgrade pip
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
fi

# Создание папки для загружаемых файлов
mkdir -p uploads

# Запуск бота
echo "Запускаю бота (Ctrl+C для остановки)..."
python3 bot.py