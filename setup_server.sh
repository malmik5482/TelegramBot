#!/bin/bash

# Скрипт настройки VPS сервера для телеграм-бота
# Автор: AI Assistant
# Дата: 30.09.2025

set -e

echo "=== Настройка VPS сервера для телеграм-бота ==="

# 1. Обновление системы
sudo apt update && sudo apt upgrade -y

# 2. Установка необходимых пакетов
sudo apt install -y python3 python3-pip python3-venv git wget curl sqlite3 htop nano screen

# 3. Создание пользователя для бота (по желанию)
if ! id "botuser" &>/dev/null; then
  echo "Создаём системного пользователя botuser"
  sudo useradd -m -s /bin/bash botuser
  sudo usermod -aG sudo botuser
fi

# 4. Копирование проекта (предполагается, что репозиторий уже склонирован)
PROJECT_DIR="/home/botuser/telegram_bot"

sudo mkdir -p "$PROJECT_DIR"
sudo chown -R botuser:botuser "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 5. Создание виртуального окружения
sudo -u botuser python3 -m venv venv
source venv/bin/activate

# 6. Установка зависимостей
pip install --upgrade pip
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
fi

# 7. Создание директорий
mkdir -p uploads utils

# 8. Создание systemd сервиса
SERVICE_FILE="/etc/systemd/system/telegram-bot.service"

echo "Создаём systemd unit файл $SERVICE_FILE"

sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Telegram Bot for English Teacher
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin
ExecStart=$PROJECT_DIR/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 9. Перезапуск systemd и запуск сервиса
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot.service

echo "=== Настройка завершена ==="
echo "Запустить бота: sudo systemctl start telegram-bot.service"
echo "Проверить статус: sudo systemctl status telegram-bot.service"
echo "Логи: sudo journalctl -u telegram-bot.service -f"
