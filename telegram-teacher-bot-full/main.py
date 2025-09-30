
import asyncio
import random
from datetime import datetime, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler, ConversationHandler
)
from config import BOT_TOKEN, TEACHER_CODE, TZ
from db import (
    init_db, connect, upsert_user, get_user, get_or_create_group, set_user_group,
    create_assignment, list_student_assignments, create_submission, get_pending_submission, set_grade,
    add_lesson, list_upcoming_lessons_for_student, list_future_lessons, list_groups, now_iso,
    bump_streak, list_future_assignments, link_parent, get_parents,
    add_flashcard, get_random_card_for_student, set_card_progress,
    add_quiz, get_random_quiz_for_student, save_quiz_result
)

tz = pytz.timezone(TZ)

# --- States ---
(
    AWAIT_TEACHER_CODE,
    # New task wizard
    T_NEW_TARGET, T_NEW_GROUP, T_NEW_STUDENT, T_NEW_TITLE, T_NEW_DESC, T_NEW_DUE, T_NEW_CONFIRM,
    # Groups
    T_ADD_GROUP_NAME,
    # Schedule
    T_SCHEDULE_GROUP, T_SCHEDULE_DATETIME, T_SCHEDULE_LOCATION, T_SCHEDULE_CONFIRM,
    # Student submit
    S_SUBMIT_WAIT,
    # Grade comment
    T_GRADE_COMMENT,
    # Parent link
    P_CHILD_USERNAME,
    # Flashcards add
    F_ADD_GROUP_PICK, F_ADD_TEXT,
    # Quiz add
    Q_ADD_GROUP_PICK, Q_ADD_TEXT
) = range(20)

def is_teacher(user):
    return user and user.get("role") == "teacher"

def is_parent(user):
    return user and user.get("role") == "parent"

def kb(rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=data) for (text, data) in row] for row in rows])

def home_keyboard_for(u):
    if is_teacher(u):
        return kb([
            [("📚 Задания", "t:tasks"), ("📝 Проверка", "t:review")],
            [("👥 Группы", "t:groups"), ("🗓️ Расписание", "t:schedule")],
            [("👪 Родители", "t:parents"), ("🎴 Карточки", "t:flash"), ("❓ Викторины", "t:quiz")],
            [("🏠 Домой", "home")]
        ])
    elif is_parent(u):
        return kb([
            [("👪 Привязать ребёнка", "p:link")],
            [("🏠 Домой", "home")]
        ])
    else:
        return kb([
            [("🧩 Мои задания", "s:tasks:1")],
            [("📤 Сдать работу", "s:submit")],
            [("🗓️ Расписание", "s:schedule")],
            [("🎴 Карточки", "s:flash"), ("❓ Викторина", "s:quiz")],
            [("🏆 Мой прогресс", "s:progress"), ("❓ Помощь", "s:help")]
        ])

def ensure_username(u):
    return u.username or f"id{u.id}"

def fmtdt(dt_iso):
    return datetime.fromisoformat(dt_iso).astimezone(tz).strftime("%Y-%m-%d %H:%M")

def format_assignment_card(a):
    return f"#{a['id']} — *{a['title']}*\n{a['description']}\n🗓️ Срок: {fmtdt(a['due_at'])}"

# --- Start / Role ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    tg = update.effective_user
    u = upsert_user(con, tg.id, ensure_username(tg), tg.full_name)
    await update.message.reply_text(
        "Привет! Кто вы?",
        reply_markup=kb([[("Я учитель", "role:teacher"), ("Я ученик", "role:student"), ("Я родитель", "role:parent")]])
    )

async def handle_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    u = get_user(con, update.effective_user.id)
    text = "Главное меню учителя:" if is_teacher(u) else ("Главное меню родителя:" if is_parent(u) else "Главное меню ученика:")
    await (update.callback_query.message.edit_text if update.callback_query else update.message.reply_text)(
        text, reply_markup=home_keyboard_for(u), parse_mode="Markdown"
    )

async def pick_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    data = cq.data
    if data == "role:teacher":
        await cq.message.edit_text("Введите секретный код учителя:", reply_markup=ForceReply(selective=True))
        return AWAIT_TEACHER_CODE
    elif data == "role:parent":
        upsert_user(con, cq.from_user.id, ensure_username(cq.from_user), cq.from_user.full_name, role="parent")
        await cq.message.edit_text("Введите @username ребёнка, чтобы получать отчёты:", reply_markup=ForceReply(selective=True))
        return P_CHILD_USERNAME
    else:
        gs = list_groups(con)
        if gs:
            rows = [[(g['name'], f"s:join:{g['id']}")] for g in gs[:10]]
            rows.append([("➕ Другая группа…", "s:join:other")])
            await cq.message.edit_text("Выберите группу:", reply_markup=kb(rows))
        else:
            await cq.message.edit_text("Пока нет групп. Попросите учителя создать группу.")
        return ConversationHandler.END

async def teacher_code_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    code = update.message.text.strip()
    if code != TEACHER_CODE:
        await update.message.reply_text("Код неверный. Попробуйте ещё раз или /start.")
        return ConversationHandler.END
    upsert_user(con, update.effective_user.id, ensure_username(update.effective_user), update.effective_user.full_name, role="teacher")
    await update.message.reply_text("Готово! Вы — учитель.", reply_markup=home_keyboard_for({"role":"teacher"}))
    return ConversationHandler.END

async def parent_link_child(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    child_username = update.message.text.strip().lstrip("@")
    row = con.execute("SELECT tg_id FROM users WHERE username=?", (child_username,)).fetchone()
    if not row:
        await update.message.reply_text("Ученик не найден. Попросите его написать боту /start.")
    else:
        link_parent(con, row["tg_id"], update.effective_user.id)
        await update.message.reply_text("Готово! Вы будете получать недельные отчёты по ребёнку.", reply_markup=home_keyboard_for({"role":"parent"}))
    return ConversationHandler.END

# --- Student: join ---
async def student_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    _, _, gid = cq.data.split(":")
    if gid == "other":
        await cq.message.edit_text("Введите название группы:", reply_markup=ForceReply(selective=True))
        context.user_data["await_group_name_for_join"] = True
        return ConversationHandler.END
    set_user_group(con, cq.from_user.id, int(gid))
    await cq.message.edit_text("Вы добавлены в группу! Вот ваше меню:", reply_markup=home_keyboard_for({"role":"student"}))

async def on_text_maybe_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("await_group_name_for_join"):
        con = connect()
        name = update.message.text.strip()
        g = get_or_create_group(con, name)
        set_user_group(con, update.effective_user.id, g["id"])
        context.user_data["await_group_name_for_join"] = False
        await update.message.reply_text(f"Готово! Вы в группе «{g['name']}».", reply_markup=home_keyboard_for({"role":"student"}))

# --- Student: tasks & submit ---
async def s_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    page = int(cq.data.split(":")[-1])
    tasks = list_student_assignments(con, cq.from_user.id)
    if not tasks:
        await cq.message.edit_text("У вас пока нет заданий.", reply_markup=home_keyboard_for({"role":"student"})); return
    per = 3; start = (page-1)*per; chunk = tasks[start:start+per]
    text = "🧩 *Мои задания:*\n\n" + "\n\n".join(format_assignment_card(t) for t in chunk)
    rows = []
    for t in chunk:
        rows.append([(f"📤 Сдать #{t['id']}", f"s:submit:{t['id']}")])
    nav = []
    if page>1: nav.append(("◀️", f"s:tasks:{page-1}"))
    if start+per < len(tasks): nav.append(("▶️", f"s:tasks:{page+1}"))
    if nav: rows.append(nav)
    rows.append([("🏠 Домой", "home")])
    await cq.message.edit_text(text, parse_mode="Markdown", reply_markup=kb(rows))

async def s_submit_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    parts = cq.data.split(":")
    if len(parts)==2:
        await cq.message.edit_text("Откройте «Мои задания» и нажмите «Сдать» рядом с нужным заданием.",
                                   reply_markup=kb([[("🧩 Мои задания", "s:tasks:1")],[("🏠 Домой","home")]]))
        return ConversationHandler.END
    aid = int(parts[-1])
    context.user_data["awaiting_submission_for"] = aid
    await cq.message.edit_text(f"Отправьте одним следующим сообщением текст/файл/фото/голос для задания #{aid}.",
                               reply_markup=kb([[("❌ Отмена", "s:submit:cancel")]]))
    return S_SUBMIT_WAIT

async def s_submit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    context.user_data["awaiting_submission_for"] = None
    await cq.message.edit_text("Отправка отменена.", reply_markup=home_keyboard_for({"role":"student"}))
    return ConversationHandler.END

async def s_submit_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    u = update.effective_user
    aid = context.user_data.get("awaiting_submission_for")
    if not aid: return
    text_content, file_id, file_type = None, None, None
    if update.message.document: file_id = update.message.document.file_id; file_type = "document"
    elif update.message.photo: file_id = update.message.photo[-1].file_id; file_type = "photo"
    elif update.message.audio: file_id = update.message.audio.file_id; file_type = "audio"
    elif update.message.voice: file_id = update.message.voice.file_id; file_type = "voice"
    elif update.message.text: text_content = update.message.text
    else:
        await update.message.reply_text("Этот тип сообщения пока не поддерживается. Пришлите текст/файл/фото/голос."); return
    sid = create_submission(con, aid, u.id, text_content, file_id, file_type)
    # streaks
    ns = bump_streak(con, u.id, now_iso())
    if ns in (3,7,30):
        await update.message.reply_text(f"🏆 Поздравляю! Серия активности {ns} дней!")
    context.user_data["awaiting_submission_for"] = None
    await update.message.reply_text(f"Готово! Работа отправлена (submission #{sid}).", reply_markup=home_keyboard_for({"role":"student"}))
    return ConversationHandler.END

async def s_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    lessons = list_upcoming_lessons_for_student(con, cq.from_user.id, now_iso())
    if not lessons:
        await cq.message.edit_text("Ближайших занятий пока нет.", reply_markup=kb([[("🏠 Домой","home")]])); return
    lines = []
    for L in lessons:
        local = datetime.fromisoformat(L["starts_at"]).astimezone(tz).strftime("%Y-%m-%d %H:%M")
        lines.append(f"• {local} — {L['location']}")
    await cq.message.edit_text("🗓️ *Ближайшие занятия:*\n" + "\\n".join(lines), parse_mode="Markdown",
                               reply_markup=kb([[("🏠 Домой","home")]]))

async def s_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    u = get_user(con, cq.from_user.id)
    streak = u.get("streak_days") or 0
    await cq.message.edit_text(f"🏆 Ваша текущая серия активности: {streak} дн.",
                               reply_markup=kb([[("🏠 Домой","home")]]))

async def s_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    await cq.message.edit_text("Помощь:\n— «Мои задания» → карточка → «Сдать»\n— «Расписание» → список ближайших уроков\n— Карточки/Викторина — тренировки\nЕсли что-то не работает — напишите учителю 🙂",
                               reply_markup=kb([[("🏠 Домой","home")]]))

# --- Teacher: tasks ---
async def t_menu_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    await cq.message.edit_text("📚 Задания:", reply_markup=kb([[("➕ Новое задание", "t:new:start")],[("◀️ Назад", "home")]]))

# New task wizard
async def t_new_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    context.user_data["newtask"] = {}
    await cq.message.edit_text("Для кого это задание?", reply_markup=kb([[("Группе", "t:new:target:group"), ("Ученик", "t:new:target:student")],[("❌ Отмена", "home")]]))
    return T_NEW_TARGET

async def t_new_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    kind = cq.data.split(":")[-1]
    nt = context.user_data.get("newtask", {}); nt["target_kind"] = kind; context.user_data["newtask"] = nt
    con = connect()
    if kind == "group":
        gs = list_groups(con)
        if not gs:
            await cq.message.edit_text("Групп пока нет. Создайте в разделе «Группы».", reply_markup=kb([[("👥 Группы","t:groups")],[("◀️ Назад","home")]]))
            return ConversationHandler.END
        rows = [[(g['name'], f"t:new:group:{g['id']}")] for g in gs[:20]]
        rows.append([("◀️ Назад", "t:tasks")])
        await cq.message.edit_text("Выберите группу:", reply_markup=kb(rows))
        return T_NEW_GROUP
    else:
        await cq.message.edit_text("Введите @username ученика:", reply_markup=ForceReply(selective=True))
        return T_NEW_STUDENT

async def t_new_pick_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    gid = int(cq.data.split(":")[-1])
    nt = context.user_data.get("newtask", {}); nt["group_id"] = gid; context.user_data["newtask"] = nt
    await cq.message.edit_text("Введите *заголовок* задания:", parse_mode="Markdown", reply_markup=ForceReply(selective=True))
    return T_NEW_TITLE

async def t_new_student_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().lstrip("@")
    nt = context.user_data.get("newtask", {}); nt["student_username"] = username; context.user_data["newtask"] = nt
    await update.message.reply_text("Введите *заголовок* задания:", parse_mode="Markdown", reply_markup=ForceReply(selective=True))
    return T_NEW_TITLE

async def t_new_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nt = context.user_data.get("newtask", {}); nt["title"] = update.message.text.strip(); context.user_data["newtask"] = nt
    await update.message.reply_text("Теперь введите *описание* (кратко):", parse_mode="Markdown", reply_markup=ForceReply(selective=True))
    return T_NEW_DESC

async def t_new_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nt = context.user_data.get("newtask", {}); nt["desc"] = update.message.text.strip(); context.user_data["newtask"] = nt
    now_local = datetime.now(tz)
    presets = [
        ("Сегодня 19:00", (now_local.replace(hour=19, minute=0) if now_local.hour<19 else now_local.replace(hour=19, minute=0)).strftime("%Y-%m-%d %H:%M")),
        ("Завтра 18:00", (now_local+timedelta(days=1)).replace(hour=18, minute=0).strftime("%Y-%m-%d %H:%M")),
        ("Через 3 дня 12:00", (now_local+timedelta(days=3)).replace(hour=12, minute=0).strftime("%Y-%m-%d %H:%M")),
    ]
    rows = [[(label, f"t:new:duepreset:{val}")] for (label,val) in presets]
    rows.append([("Ввести вручную…","t:new:due:manual")])
    rows.append([("❌ Отмена","home")])
    await update.message.reply_text("Выберите срок сдачи или введите вручную:", reply_markup=kb(rows))
    return T_NEW_DUE

async def t_new_duepreset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    val = cq.data.split(":")[-1]
    nt = context.user_data.get("newtask", {}); nt["due_str"] = val; context.user_data["newtask"] = nt
    await cq.message.edit_text(f"Срок: {val}\n\nПодтвердить создание задания?", reply_markup=kb([[("✅ Создать","t:new:confirm")],[("◀️ Назад","t:tasks")]]))
    return T_NEW_CONFIRM

async def t_new_due_manual_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    await cq.message.edit_text("Введите срок в формате YYYY-MM-DD HH:MM:", reply_markup=ForceReply(selective=True))
    return T_NEW_DUE

async def t_new_due_manual_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nt = context.user_data.get("newtask", {}); nt["due_str"] = update.message.text.strip(); context.user_data["newtask"] = nt
    await update.message.reply_text(f"Срок: {nt['due_str']}\n\nПодтвердить создание задания?",
                                    reply_markup=kb([[("✅ Создать","t:new:confirm")],[("❌ Отмена","home")]]))
    return T_NEW_CONFIRM

async def schedule_assignment_reminders(context: ContextTypes.DEFAULT_TYPE, assignment):
    # plan -24h and -2h reminders to student(s)
    con = connect()
    due_dt = datetime.fromisoformat(assignment["due_at"])
    targets = []
    if assignment["student_tg_id"]:
        targets = [assignment["student_tg_id"]]
    elif assignment["group_id"]:
        rows = con.execute("SELECT tg_id FROM users WHERE group_id=?", (assignment["group_id"],)).fetchall()
        targets = [r["tg_id"] for r in rows]
    for delta in (24*60, 2*60):
        when = due_dt - timedelta(minutes=delta)
        if when > datetime.utcnow():
            for tg_id in targets:
                context.job_queue.run_once(send_deadline_reminder, when=when, data={"tg_id": tg_id, "aid": assignment["id"], "title": assignment["title"], "due": assignment["due_at"]})

async def t_new_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    nt = context.user_data.get("newtask", {})
    try:
        due_local = tz.localize(datetime.strptime(nt["due_str"], "%Y-%m-%d %H:%M"))
    except Exception:
        await cq.message.edit_text("Неверный формат даты. Попробуйте снова.", reply_markup=kb([[("◀️ Назад","t:tasks")]]))
        return ConversationHandler.END
    due_iso = due_local.astimezone(pytz.UTC).isoformat()
    group_id, student_tg_id = None, None
    if nt.get("target_kind") == "group":
        group_id = nt.get("group_id")
    else:
        row = connect().execute("SELECT tg_id FROM users WHERE username=?", (nt.get("student_username"),)).fetchone()
        if not row:
            await cq.message.edit_text("Ученик не найден. Попросите его написать боту /start.", reply_markup=kb([[("◀️ Назад","t:tasks")]]))
            return ConversationHandler.END
        student_tg_id = row["tg_id"]
    aid = create_assignment(con, nt["title"], nt["desc"], due_iso, group_id, student_tg_id, cq.from_user.id)
    assignment = {"id": aid, "title": nt["title"], "due_at": due_iso, "group_id": group_id, "student_tg_id": student_tg_id}
    await schedule_assignment_reminders(context, assignment)
    await cq.message.edit_text(f"Задание создано: #{aid} — {nt['title']}", reply_markup=kb([[("📚 К заданиям","t:tasks")],[("🏠 Домой","home")]]))
    context.user_data["newtask"] = {}
    return ConversationHandler.END

# --- Teacher: Review with comment ---
async def t_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    sub = get_pending_submission(con)
    if not sub:
        await cq.message.edit_text("Непроверенных работ нет 🎉", reply_markup=kb([[("🏠 Домой","home")]])); return
    text = f"Submission #{sub['id']} по заданию #{sub['assignment_id']}\nСтудент tg_id: {sub['student_tg_id']}"
    rows = [[("5","t:grade:{}:5".format(sub['id'])),("4","t:grade:{}:4".format(sub['id'])),("3","t:grade:{}:3".format(sub['id'])),("2","t:grade:{}:2".format(sub['id']))],
            [("💬 Комментарий","t:gradec:{}" .format(sub['id']))],
            [("Следующая ▶️","t:review")],
            [("🏠 Домой","home")]]
    await cq.message.edit_text(text, reply_markup=kb(rows))

async def t_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    _, _, sid, grade = cq.data.split(":")
    context.user_data["grade_for_sid"] = (int(sid), grade)
    await cq.message.reply_text("Введите короткий комментарий к оценке (или пришлите «-», если без комментария):",
                                reply_markup=ForceReply(selective=True))
    return T_GRADE_COMMENT

async def t_grade_comment_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    sid, grade = context.user_data.get("grade_for_sid", (None, None))
    if not sid:
        await update.message.reply_text("Что-то пошло не так. Попробуйте ещё раз /start."); return ConversationHandler.END
    feedback = update.message.text.strip()
    if feedback == "-": feedback = ""
    set_grade(con, sid, grade, feedback, update.effective_user.id)
    await update.message.reply_text(f"Оценка {grade} сохранена. Комментарий: {feedback or '—'}",
                                    reply_markup=kb([[("Проверить ещё ▶️","t:review")],[("🏠 Домой","home")]]))
    context.user_data["grade_for_sid"] = None
    return ConversationHandler.END

async def t_grade_comment_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    sid = int(cq.data.split(":")[-1])
    context.user_data["grade_for_sid"] = (sid, None)  # только комментарий
    await cq.message.reply_text("Введите комментарий к работе:", reply_markup=ForceReply(selective=True))
    return T_GRADE_COMMENT

# --- Teacher: Groups ---
async def t_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    gs = list_groups(con)
    rows = [[(g['name'], f"noop")] for g in gs[:20]]
    rows.append([("➕ Добавить группу","t:group:add")])
    rows.append([("◀️ Назад","home")])
    await cq.message.edit_text("Группы:", reply_markup=kb(rows))

async def t_group_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    await cq.message.edit_text("Название новой группы:", reply_markup=ForceReply(selective=True))
    return T_ADD_GROUP_NAME

async def t_group_add_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    name = update.message.text.strip()
    g = get_or_create_group(con, name)
    await update.message.reply_text(f"Группа создана: {g['name']}", reply_markup=home_keyboard_for({"role":"teacher"}))
    return ConversationHandler.END

# --- Teacher: Schedule ---
async def t_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    await cq.message.edit_text("Расписание:", reply_markup=kb([[("➕ Добавить занятие","t:sch:add")],[("◀️ Назад","home")]]))

async def t_schedule_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    gs = list_groups(con)
    rows = [[(g['name'], f"t:sch:g:{g['id']}")] for g in gs[:20]]
    rows.append([("❌ Отмена","home")])
    await cq.message.edit_text("Выберите группу:", reply_markup=kb(rows))
    return T_SCHEDULE_GROUP

async def t_schedule_group_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    gid = int(cq.data.split(":")[-1])
    context.user_data["sch"] = {"gid": gid}
    await cq.message.edit_text("Введите дату и время (YYYY-MM-DD HH:MM):", reply_markup=ForceReply(selective=True))
    return T_SCHEDULE_DATETIME

async def t_schedule_datetime_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sch"]["dt"] = update.message.text.strip()
    await update.message.reply_text("Место/ссылка (Zoom, адрес и т.п.):", reply_markup=ForceReply(selective=True))
    return T_SCHEDULE_LOCATION

async def t_schedule_location_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sch = context.user_data["sch"]
    sch["loc"] = update.message.text.strip()
    await update.message.reply_text(f"Добавить занятие?\nГруппа: {sch['gid']}\nКогда: {sch['dt']}\nГде: {sch['loc']}",
                                    reply_markup=kb([[("✅ Добавить","t:sch:confirm")],[("❌ Отмена","home")]]))
    return T_SCHEDULE_CONFIRM

async def send_lesson_reminder(context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    data = context.job.data
    group_id = data["group_id"]
    time_str = data["time_str"]
    location = data["location"]
    rows = con.execute("SELECT tg_id FROM users WHERE group_id=?", (group_id,)).fetchall()
    for r in rows:
        try:
            await context.bot.send_message(r["tg_id"], f"🔔 Напоминание: занятие через 1 час, в {time_str}. Место/ссылка: {location}")
        except Exception:
            pass

async def send_deadline_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    try:
        local_due = datetime.fromisoformat(data["due"]).astimezone(tz).strftime("%Y-%m-%d %H:%M")
        await context.bot.send_message(data["tg_id"], f"⏰ Напоминание: дедлайн по заданию #{data['aid']} «{data['title']}» в {local_due}.")
    except Exception:
        pass

async def t_schedule_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    sch = context.user_data.get("sch", {})
    try:
        dt_local = tz.localize(datetime.strptime(sch["dt"], "%Y-%m-%d %H:%M"))
    except Exception:
        await cq.message.edit_text("Неверная дата. Попробуйте снова.", reply_markup=kb([[("◀️ Назад","home")]]))
        return ConversationHandler.END
    dt_utc = dt_local.astimezone(pytz.UTC)
    add_lesson(con, sch["gid"], dt_utc.isoformat(), 60, sch["loc"], "")
    remind_at = dt_utc - timedelta(minutes=60)
    context.job_queue.run_once(send_lesson_reminder, when=remind_at, data={"group_id": sch["gid"], "time_str": dt_local.strftime("%Y-%m-%d %H:%M"), "location": sch["loc"]})
    await cq.message.edit_text("Занятие добавлено и напоминание запланировано ✅", reply_markup=kb([[("🏠 Домой","home")]]))
    context.user_data["sch"] = {}
    return ConversationHandler.END

# --- Parents menu for teacher ---
async def t_parents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    await cq.message.edit_text("Родители: попросите родителя нажать «Я родитель» и ввести @username ребёнка.\nЕженедельные отчёты будут приходить автоматически.",
                               reply_markup=kb([[("🏠 Домой","home")]]))

# --- Flashcards ---
async def t_flash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    await cq.message.edit_text("Карточки слов (для учителя):", reply_markup=kb([[("➕ Добавить карточку","f:add")],[("◀️ Назад","home")]]))

async def f_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    gs = list_groups(con)
    rows = [[(g['name'], f"f:add:g:{g['id']}")] for g in gs[:20]]
    rows.append([("❌ Отмена","home")])
    await cq.message.edit_text("Выберите группу:", reply_markup=kb(rows))
    return F_ADD_GROUP_PICK

async def f_add_group_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    gid = int(cq.data.split(":")[-1])
    context.user_data["f_gid"] = gid
    await cq.message.edit_text("Введите карточку в формате: `слово | перевод`", parse_mode="Markdown", reply_markup=ForceReply(selective=True))
    return F_ADD_TEXT

async def f_add_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    gid = context.user_data.get("f_gid")
    parts = [p.strip() for p in update.message.text.split("|")]
    if len(parts) < 2:
        await update.message.reply_text("Неверный формат. Пример: *apple | яблоко*", parse_mode="Markdown"); return ConversationHandler.END
    add_flashcard(con, gid, parts[0], parts[1], update.effective_user.id)
    await update.message.reply_text("Карточка добавлена ✅", reply_markup=home_keyboard_for({"role":"teacher"}))
    context.user_data["f_gid"] = None
    return ConversationHandler.END

async def s_flash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    row = get_random_card_for_student(con, cq.from_user.id)
    if not row:
        await cq.message.edit_text("Пока нет карточек для вашей группы.", reply_markup=kb([[("🏠 Домой","home")]])); return
    card = dict(row)
    context.user_data["flash_card_id"] = card["id"]
    await cq.message.edit_text(f"🎴 *{card['front']}*", parse_mode="Markdown",
                               reply_markup=kb([[("Показать ответ","f:show")],[("🏠 Домой","home")]]))

async def f_show_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    card_id = context.user_data.get("flash_card_id")
    row = con.execute("SELECT * FROM flashcards WHERE id=?", (card_id,)).fetchone()
    if not row:
        await cq.message.edit_text("Карточка не найдена.", reply_markup=kb([[("🏠 Домой","home")]])); return
    card = dict(row)
    await cq.message.edit_text(f"🎴 *{card['front']}* → **{card['back']}**", parse_mode="Markdown",
                               reply_markup=kb([[("Знаю","f:know"),("Не знаю","f:unk")],[("Ещё карточка ▶️","s:flash")]]))

async def f_mark_known(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    card_id = context.user_data.get("flash_card_id")
    set_card_progress(con, card_id, cq.from_user.id, "known" if "f:know" in cq.data else "learning")
    await cq.message.edit_text("Запомнил! Двигаемся дальше ▶️", reply_markup=kb([[("Ещё ▶️","s:flash")],[("🏠 Домой","home")]]))

# --- Quizzes ---
async def t_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    await cq.message.edit_text("Викторины (для учителя):", reply_markup=kb([[("➕ Добавить вопрос","q:add")],[("◀️ Назад","home")]]))

async def q_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    gs = list_groups(con)
    rows = [[(g['name'], f"q:add:g:{g['id']}")] for g in gs[:20]]
    rows.append([("❌ Отмена","home")])
    await cq.message.edit_text("Выберите группу:", reply_markup=kb(rows))
    return Q_ADD_GROUP_PICK

async def q_add_group_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    gid = int(cq.data.split(":")[-1])
    context.user_data["q_gid"] = gid
    await cq.message.edit_text("Формат: `Вопрос | Правильный | Неверный1 | Неверный2 | Неверный3`",
                               parse_mode="Markdown", reply_markup=ForceReply(selective=True))
    return Q_ADD_TEXT

async def q_add_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    gid = context.user_data.get("q_gid")
    parts = [p.strip() for p in update.message.text.split("|")]
    if len(parts) < 5:
        await update.message.reply_text("Неверный формат. Пример: *What is 'apple'? | яблоко | груша | апельсин | банан*", parse_mode="Markdown"); return ConversationHandler.END
    add_quiz(con, gid, parts[0], parts[1], parts[2], parts[3], parts[4], update.effective_user.id)
    await update.message.reply_text("Вопрос добавлен ✅", reply_markup=home_keyboard_for({"role":"teacher"}))
    context.user_data["q_gid"] = None
    return ConversationHandler.END

async def s_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    con = connect()
    row = get_random_quiz_for_student(con, cq.from_user.id)
    if not row:
        await cq.message.edit_text("Пока нет вопросов для вашей группы.", reply_markup=kb([[("🏠 Домой","home")]])); return
    q = dict(row)
    options = [q["correct"], q["wrong1"], q["wrong2"], q["wrong3"]]
    random.shuffle(options)
    rows = [[(opt, f"q:ans:{q['id']}:{1 if opt==q['correct'] else 0}") ] for opt in options]
    rows.append([("Другое вопрос ▶️","s:quiz")])
    await cq.message.edit_text(f"❓ {q['question']}", reply_markup=kb(rows))

async def q_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query; await cq.answer()
    _, _, qid, is_cor = cq.data.split(":")
    con = connect()
    save_quiz_result(con, int(qid), cq.from_user.id, bool(int(is_cor)))
    await cq.message.edit_text("✅ Верно!" if is_cor == "1" else "❌ Неверно.", reply_markup=kb([[("Ещё вопрос ▶️","s:quiz")],[("🏠 Домой","home")]]))

# --- Weekly reports to parents ---
async def weekly_reports(context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    # Короткий отчёт по активности/оценкам за последние 7 дней
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()
    # По каждому родителю найдём его ребёнка(детей)
    parents = con.execute("SELECT DISTINCT parent_tg_id FROM parents").fetchall()
    for pr in parents:
        parent_id = pr["parent_tg_id"]
        # найдём детей
        kids = con.execute("SELECT DISTINCT student_tg_id FROM parents WHERE parent_tg_id=?", (parent_id,)).fetchall()
        lines = []
        for kid in kids:
            kid_id = kid["student_tg_id"]
            u = get_user(con, kid_id)
            # кол-во проверенных оценок
            row = con.execute("SELECT COUNT(*) AS c FROM submissions WHERE student_tg_id=? AND graded_at>=?", (kid_id, since)).fetchone()
            graded = row["c"]
            streak = u.get("streak_days") or 0
            lines.append(f"👤 {u.get('full_name') or u.get('username')}: оценок за неделю — {graded}, текущая серия — {streak}.")
        if lines:
            try:
                await context.bot.send_message(parent_id, "Недельный отчёт:\n" + "\n".join(lines))
            except Exception:
                pass

# --- Startup helpers ---
async def reschedule_all(app: Application):
    con = connect()
    # Lessons
    now_s = datetime.utcnow().isoformat()
    for L in list_future_lessons(con, now_s):
        starts_at = datetime.fromisoformat(L["starts_at"])
        remind_at = starts_at - timedelta(minutes=60)
        if remind_at > datetime.utcnow():
            local = starts_at.astimezone(tz).strftime("%Y-%m-%d %H:%M")
            app.job_queue.run_once(send_lesson_reminder, when=remind_at, data={"group_id": L["group_id"], "time_str": local, "location": L["location"]})
    # Assignments deadlines
    for A in list_future_assignments(con, now_s):
        await schedule_assignment_reminders(app, A)
    # Weekly parent reports: каждый понедельник 09:00 TZ
    # Вычислим ближайший понедельник 09:00
    now_local = datetime.now(tz)
    days_ahead = (7 - now_local.weekday()) % 7  # 0=понедельник
    next_mon = (now_local + timedelta(days=days_ahead)).replace(hour=9, minute=0, second=0, microsecond=0)
    app.job_queue.run_repeating(weekly_reports, interval=7*24*3600, first=next_mon.astimezone(pytz.UTC))

async def on_startup(app: Application):
    await reschedule_all(app)

def build_app():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))

    # Common
    app.add_handler(CallbackQueryHandler(handle_home, pattern=r"^home$"))
    app.add_handler(CallbackQueryHandler(pick_role, pattern=r"^role:(teacher|student|parent)$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(pick_role, pattern=r"^role:teacher$")],
        states={ AWAIT_TEACHER_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, teacher_code_message)] },
        fallbacks=[CommandHandler("start", start)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(pick_role, pattern=r"^role:parent$")],
        states={ P_CHILD_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, parent_link_child)] },
        fallbacks=[CommandHandler("start", start)]
    ))

    # Student
    app.add_handler(CallbackQueryHandler(student_join, pattern=r"^s:join:(\\d+|other)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_maybe_join))
    app.add_handler(CallbackQueryHandler(s_tasks, pattern=r"^s:tasks:\\d+$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(s_submit_pick, pattern=r"^s:submit(:\\d+)?$")],
        states={ S_SUBMIT_WAIT: [MessageHandler(~filters.COMMAND, s_submit_receive)] },
        fallbacks=[CallbackQueryHandler(s_submit_cancel, pattern=r"^s:submit:cancel$")]
    ))
    app.add_handler(CallbackQueryHandler(s_schedule, pattern=r"^s:schedule$"))
    app.add_handler(CallbackQueryHandler(s_progress, pattern=r"^s:progress$"))
    app.add_handler(CallbackQueryHandler(s_help, pattern=r"^s:help$"))

    # Teacher: tasks
    app.add_handler(CallbackQueryHandler(t_menu_tasks, pattern=r"^t:tasks$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(t_new_start, pattern=r"^t:new:start$")],
        states={
            T_NEW_TARGET: [CallbackQueryHandler(t_new_target, pattern=r"^t:new:target:(group|student)$")],
            T_NEW_GROUP: [CallbackQueryHandler(t_new_pick_group, pattern=r"^t:new:group:\\d+$")],
            T_NEW_STUDENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, t_new_student_username)],
            T_NEW_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, t_new_title)],
            T_NEW_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, t_new_desc)],
            T_NEW_DUE: [
                CallbackQueryHandler(t_new_duepreset, pattern=r"^t:new:duepreset:.+"),
                CallbackQueryHandler(t_new_due_manual_request, pattern=r"^t:new:due:manual$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, t_new_due_manual_receive)
            ],
            T_NEW_CONFIRM: [CallbackQueryHandler(t_new_confirm, pattern=r"^t:new:confirm$")]
        },
        fallbacks=[CallbackQueryHandler(handle_home, pattern=r"^home$")]
    ))
    app.add_handler(CallbackQueryHandler(t_review, pattern=r"^t:review$"))
    app.add_handler(CallbackQueryHandler(t_grade, pattern=r"^t:grade:\\d+:\\d$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(t_grade_comment_button, pattern=r"^t:gradec:\\d+$")],
        states={ T_GRADE_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, t_grade_comment_receive)] },
        fallbacks=[CallbackQueryHandler(handle_home, pattern=r"^home$")]
    ))

    # Teacher: groups/schedule
    app.add_handler(CallbackQueryHandler(t_groups, pattern=r"^t:groups$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(t_group_add, pattern=r"^t:group:add$")],
        states={ T_ADD_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, t_group_add_receive)] },
        fallbacks=[CallbackQueryHandler(handle_home, pattern=r"^home$")]
    ))
    app.add_handler(CallbackQueryHandler(t_schedule, pattern=r"^t:schedule$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(t_schedule_add, pattern=r"^t:sch:add$")],
        states={
            T_SCHEDULE_GROUP: [CallbackQueryHandler(t_schedule_group_pick, pattern=r"^t:sch:g:\\d+$")],
            T_SCHEDULE_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, t_schedule_datetime_receive)],
            T_SCHEDULE_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, t_schedule_location_receive)],
            T_SCHEDULE_CONFIRM: [CallbackQueryHandler(t_schedule_confirm, pattern=r"^t:sch:confirm$")]
        },
        fallbacks=[CallbackQueryHandler(handle_home, pattern=r"^home$")]
    ))

    # Teacher: parents
    app.add_handler(CallbackQueryHandler(t_parents, pattern=r"^t:parents$"))

    # Teacher/Student: flashcards & quiz
    app.add_handler(CallbackQueryHandler(t_flash, pattern=r"^t:flash$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(f_add_start, pattern=r"^f:add$")],
        states={
            F_ADD_GROUP_PICK: [CallbackQueryHandler(f_add_group_pick, pattern=r"^f:add:g:\\d+$")],
            F_ADD_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, f_add_text_receive)]
        },
        fallbacks=[CallbackQueryHandler(handle_home, pattern=r"^home$")]
    ))
    app.add_handler(CallbackQueryHandler(s_flash, pattern=r"^s:flash$"))
    app.add_handler(CallbackQueryHandler(f_show_answer, pattern=r"^f:show$"))
    app.add_handler(CallbackQueryHandler(f_mark_known, pattern=r"^f:(know|unk)$"))

    app.add_handler(CallbackQueryHandler(t_quiz, pattern=r"^t:quiz$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(q_add_start, pattern=r"^q:add$")],
        states={
            Q_ADD_GROUP_PICK: [CallbackQueryHandler(q_add_group_pick, pattern=r"^q:add:g:\\d+$")],
            Q_ADD_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_add_text_receive)]
        },
        fallbacks=[CallbackQueryHandler(handle_home, pattern=r"^home$")]
    ))
    app.add_handler(CallbackQueryHandler(s_quiz, pattern=r"^s:quiz$"))
    app.add_handler(CallbackQueryHandler(q_answer, pattern=r"^q:ans:\\d+:(0|1)$"))

    app.post_init = on_startup
    return app

async def main():
    app = build_app()
    if not BOT_TOKEN or BOT_TOKEN.startswith("123456"):
        print("⚠️  Укажите реальный BOT_TOKEN в .env")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
