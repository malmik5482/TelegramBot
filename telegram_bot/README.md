# 🤖 Телеграм-бот для преподавателя английского языка

Этот репозиторий содержит полнофункциональный телеграм-бот для **Саликовой Ольги Александровны** (преподаватель английского). Бот помогает управлять группами учеников, домашними заданиями, расписанием и оценками.

## Состав проекта

```
telegram_bot/
├── bot.py              # Основной код бота
├── config.py           # Конфигурация (токен бота, код преподавателя)
├── database.py         # Работа с SQLite базой данных
├── requirements.txt    # Python-зависимости
├── start_bot.sh        # Локальный запуск бота
├── setup_server.sh     # Автoнастройка VPS и systemd-сервиса
├── utils/
│   ├── __init__.py    # Пустой файл-пакет
│   ├── helpers.py     # Вспомогательные функции
│   └── keyboards.py   # Inline-клавиатуры
└── uploads/            # Папка для загружаемых файлов (создаётся автоматически)
```

## Быстрый старт (локально)
```bash
cd telegram_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./start_bot.sh
```

## Развёртывание на VPS
```bash
scp -r telegram_bot/ user@server:/home/user/
ssh user@server
cd /home/user/telegram_bot
chmod +x setup_server.sh && sudo ./setup_server.sh
```

После установки сервис запускается командами:
```bash
sudo systemctl start telegram-bot.service      # запустить
sudo systemctl status telegram-bot.service     # статус
sudo journalctl -u telegram-bot.service -f     # логи
```

## Данные доступа
* **Токен бота:** хранится в `config.py`
* **Код преподавателя:** `0306`

## Возможности бота
* Просмотр и управление группами учеников
* Домашние задания с прикреплением файлов и оценками
* Персональное расписание занятий
* Статистика успеваемости
* Полностью кнопочный интерфейс (без команд)

---
© 2025 • AI Assistant