#!/usr/bin/env bash
set -euo pipefail

# === Настройки ===
APP_DIR="/opt/telegram-teacher-bot"
REPO_URL_DEFAULT="https://github.com/malmik5482/TelegramBot.git"

echo "==> Обновление пакетов и установка зависимостей"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

echo "==> Создание директории приложения: $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo chown -R "$USER":"$USER" "$APP_DIR"

if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> Клонирование репозитория (если нужно)"
  read -r -p "URL репозитория (Enter для по умолчанию): " REPO_URL
  REPO_URL="${REPO_URL:-$REPO_URL_DEFAULT}"
  git clone "$REPO_URL" "$APP_DIR" || true
else
  echo "==> Репозиторий уже существует, выполняем pull"
  git -C "$APP_DIR" pull || true
fi

# Если вы загружаете архив вручную, просто распакуйте его в $APP_DIR и пропустите git.
# Копию .env поместите в $APP_DIR/.env

echo "==> Настройка виртуального окружения"
python3 -m venv "$APP_DIR/.venv"
source "$APP_DIR/.venv/bin/activate"
pip install --upgrade pip
if [ -f "$APP_DIR/requirements.txt" ]; then
  pip install -r "$APP_DIR/requirements.txt"
fi

# Создаём systemd unit
SERVICE_FILE="$HOME/telegram-teacher-bot.service"
cat > "$SERVICE_FILE" << 'UNIT'
[Unit]
Description=Telegram Teacher Bot (polling)
After=network-online.target

[Service]
Type=simple
User=%i
WorkingDirectory=/opt/telegram-teacher-bot
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/telegram-teacher-bot/.venv/bin/python /opt/telegram-teacher-bot/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

echo "==> Установка systemd-сервиса от имени текущего пользователя"
# Имя сервиса будет USER@telegram-teacher-bot.service
sudo mv "$SERVICE_FILE" "/etc/systemd/system/$(whoami)@telegram-teacher-bot.service"
sudo systemctl daemon-reload
sudo systemctl enable "$(whoami)@telegram-teacher-bot.service"
sudo systemctl restart "$(whoami)@telegram-teacher-bot.service"

echo "==> Готово! Проверить статус:"
echo "sudo systemctl status $(whoami)@telegram-teacher-bot.service"
