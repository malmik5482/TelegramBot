import asyncio
from datetime import datetime, timedelta, time as dtime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import (Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler, ConversationHandler)
from config import BOT_TOKEN, TEACHER_CODE, TZ
from db import (init_db, connect, upsert_user, get_user, get_or_create_group, set_user_group,
                create_assignment, list_student_assignments, create_submission, get_pending_submission, set_grade,
                add_lesson, list_upcoming_lessons_for_student, list_future_lessons, list_groups, now_iso)

tz = pytz.timezone(TZ)

(AWAIT_TEACHER_CODE, T_NEW_TARGET, T_NEW_GROUP, T_NEW_STUDENT, T_NEW_TITLE, T_NEW_DESC, T_NEW_DUE, T_NEW_CONFIRM,
 T_ADD_GROUP_NAME, T_SCHEDULE_GROUP, T_SCHEDULE_DATETIME, T_SCHEDULE_LOCATION, T_SCHEDULE_CONFIRM,
 S_SUBMIT_WAIT) = range(14)

def is_teacher(user): return user and user.get("role")=="teacher"
def kb(rows): return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for (t,d) in row] for row in rows])
def home_keyboard_for(user):
    if is_teacher(user):
        return kb([[("📚 Задания","t:tasks"),("📝 Проверка","t:review")],[("👥 Группы","t:groups"),("🗓️ Расписание","t:schedule")],[("🏠 Домой","home")]])
    else:
        return kb([[("🧩 Мои задания","s:tasks:1")],[("📤 Сдать работу","s:submit")],[("🗓️ Расписание","s:schedule")],[("❓ Помощь","s:help")]])

def ensure_username(u): return u.username or f"id{u.id}"
def format_assignment_card(a):
    due_local = datetime.fromisoformat(a["due_at"]).astimezone(tz).strftime("%Y-%m-%d %H:%M")
    return f"#{a['id']} — *{a['title']}*\n{a['description']}\n🗓️ Срок: {due_local}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con=connect(); tg=update.effective_user
    u=upsert_user(con,tg.id,ensure_username(tg),tg.full_name)
    if is_teacher(u):
        await update.message.reply_text("Главное меню учителя:", reply_markup=home_keyboard_for(u), parse_mode="Markdown")
    else:
        await update.message.reply_text("Привет! Кто вы?", reply_markup=kb([[("Я учитель","role:teacher"),("Я ученик","role:student")]]))

async def handle_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con=connect(); u=get_user(con, update.effective_user.id)
    txt="Главное меню учителя:" if is_teacher(u) else "Главное меню ученика:"
    dest = update.callback_query.message.edit_text if update.callback_query else update.message.reply_text
    await dest(txt, reply_markup=home_keyboard_for(u), parse_mode="Markdown")

async def pick_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    if cq.data=="role:teacher":
        # IMPORTANT: ForceReply must be sent as a NEW message, not via edit
        await cq.message.reply_text("Введите секретный код учителя:", reply_markup=ForceReply(selective=True))
        return AWAIT_TEACHER_CODE
    else:
        con=connect(); gs=list_groups(con)
        if gs:
            rows = [[(g['name'], f"s:join:{g['id']}")] for g in gs[:10]]
            rows.append([("➕ Другая группа…","s:join:other")])
            await cq.message.edit_text("Выберите группу:", reply_markup=kb(rows))
        else:
            await cq.message.edit_text("Пока нет групп. Попросите учителя создать группу.")
        return ConversationHandler.END

async def teacher_code_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con=connect(); code=update.message.text.strip()
    if code!=TEACHER_CODE:
        await update.message.reply_text("Код неверный. Попробуйте ещё раз или /start."); return ConversationHandler.END
    upsert_user(con, update.effective_user.id, ensure_username(update.effective_user), update.effective_user.full_name, role="teacher")
    await update.message.reply_text("Готово! Вы — учитель.", reply_markup=home_keyboard_for({"role":"teacher"}))
    return ConversationHandler.END

async def student_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    con=connect(); _,_,gid=cq.data.split(":")
    if gid=="other":
        await cq.message.reply_text("Введите название группы:", reply_markup=ForceReply(selective=True))
        context.user_data["await_group_name_for_join"]=True; return ConversationHandler.END
    set_user_group(con, cq.from_user.id, int(gid))
    await cq.message.edit_text("Вы добавлены в группу! Вот ваше меню:", reply_markup=home_keyboard_for({"role":"student"}))

async def on_text_maybe_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("await_group_name_for_join"):
        con=connect(); name=update.message.text.strip(); g=get_or_create_group(con,name)
        set_user_group(con, update.effective_user.id, g["id"]); context.user_data["await_group_name_for_join"]=False
        await update.message.reply_text(f"Готово! Вы в группе «{g['name']}».", reply_markup=home_keyboard_for({"role":"student"}))

async def s_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    con=connect(); page=int(cq.data.split(":")[-1]); tasks=list_student_assignments(con, cq.from_user.id)
    if not tasks:
        await cq.message.edit_text("У вас пока нет заданий.", reply_markup=home_keyboard_for({"role":"student"})); return
    per=3; start=(page-1)*per; chunk=tasks[start:start+per]
    text="🧩 *Мои задания:*\n\n" + "\n\n".join(format_assignment_card(t) for t in chunk)
    rows=[[(f"📤 Сдать #{t['id']}", f"s:submit:{t['id']}")] for t in chunk]
    nav=[]
    if page>1: nav.append(("◀️", f"s:tasks:{page-1}"))
    if start+per < len(tasks): nav.append(("▶️", f"s:tasks:{page+1}"))
    if nav: rows.append(nav)
    rows.append([("🏠 Домой","home")])
    await cq.message.edit_text(text, parse_mode="Markdown", reply_markup=kb(rows))

async def s_submit_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    parts=cq.data.split(":")
    if len(parts)==2:
        await cq.message.edit_text("Откройте «Мои задания» и нажмите «Сдать» рядом с нужным заданием.", reply_markup=kb([[("🧩 Мои задания","s:tasks:1")],[("🏠 Домой","home")]])); return ConversationHandler.END
    aid=int(parts[-1]); context.user_data["awaiting_submission_for"]=aid
    await cq.message.edit_text(f"Отправьте следующим сообщением текст/файл/фото/голос для задания #{aid}.", reply_markup=kb([[("❌ Отмена","s:submit:cancel")]])); return S_SUBMIT_WAIT

async def s_submit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer(); context.user_data["awaiting_submission_for"]=None
    await cq.message.edit_text("Отправка отменена.", reply_markup=home_keyboard_for({"role":"student"})); return ConversationHandler.END

async def s_submit_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con=connect(); u=update.effective_user; aid=context.user_data.get("awaiting_submission_for")
    if not aid: return
    text_content=file_id=file_type=None
    if update.message.document: file_id=update.message.document.file_id; file_type="document"
    elif update.message.photo: file_id=update.message.photo[-1].file_id; file_type="photo"
    elif update.message.audio: file_id=update.message.audio.file_id; file_type="audio"
    elif update.message.voice: file_id=update.message.voice.file_id; file_type="voice"
    elif update.message.text: text_content=update.message.text
    else: await update.message.reply_text("Этот тип пока не поддерживается."); return
    sid=create_submission(con, aid, u.id, text_content, file_id, file_type); context.user_data["awaiting_submission_for"]=None
    await update.message.reply_text(f"Готово! Работа отправлена (submission #{sid}).", reply_markup=home_keyboard_for({"role":"student"})); return ConversationHandler.END

async def s_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    con=connect(); lessons=list_upcoming_lessons_for_student(con, cq.from_user.id, now_iso())
    if not lessons: await cq.message.edit_text("Ближайших занятий пока нет.", reply_markup=kb([[("🏠 Домой","home")]])); return
    lines=[f"• {datetime.fromisoformat(L['starts_at']).astimezone(tz).strftime('%Y-%m-%d %H:%M')} — {L['location']}" for L in lessons]
    await cq.message.edit_text("🗓️ *Ближайшие занятия:*\n" + "\n".join(lines), parse_mode="Markdown", reply_markup=kb([[("🏠 Домой","home")]]))

async def s_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    await cq.message.edit_text("Подсказка: «Мои задания» → «Сдать» рядом с карточкой. «Расписание» — ближайшие уроки.", reply_markup=kb([[("🏠 Домой","home")]]))

# --- Teacher menu & review with comment (ForceReply via NEW messages) ---
async def t_menu_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    await cq.message.edit_text("📚 Задания:", reply_markup=kb([[("➕ Новое задание","t:new:start")],[("◀️ Назад","home")]]))

async def t_new_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer(); context.user_data["newtask"]={}
    await cq.message.edit_text("Для кого это задание?", reply_markup=kb([[("Группе","t:new:target:group"),("Ученик","t:new:target:student")],[("❌ Отмена","home")]])); return T_NEW_TARGET

async def t_new_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    kind=cq.data.split(":")[-1]; nt=context.user_data.get("newtask",{}); nt["target_kind"]=kind; context.user_data["newtask"]=nt
    con=connect()
    if kind=="group":
        gs=list_groups(con)
        if not gs:
            await cq.message.edit_text("Групп пока нет. Создайте в «Группы».", reply_markup=kb([[("👥 Группы","t:groups")],[("◀️ Назад","home")]])); return ConversationHandler.END
        rows=[[(g['name'], f"t:new:group:{g['id']}")] for g in gs[:20]]; rows.append([("◀️ Назад","t:tasks")])
        await cq.message.edit_text("Выберите группу:", reply_markup=kb(rows)); return T_NEW_GROUP
    else:
        await cq.message.reply_text("Введите @username ученика:", reply_markup=ForceReply(selective=True)); return T_NEW_STUDENT

async def t_new_pick_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    gid=int(cq.data.split(":")[-1]); nt=context.user_data.get("newtask",{}); nt["group_id"]=gid; context.user_data["newtask"]=nt
    await cq.message.reply_text("Введите *заголовок* задания:", parse_mode="Markdown", reply_markup=ForceReply(selective=True)); return T_NEW_TITLE

async def t_new_student_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username=update.message.text.strip().lstrip("@"); nt=context.user_data.get("newtask",{}); nt["student_username"]=username; context.user_data["newtask"]=nt
    await update.message.reply_text("Введите *заголовок* задания:", parse_mode="Markdown", reply_markup=ForceReply(selective=True)); return T_NEW_TITLE

async def t_new_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nt=context.user_data.get("newtask",{}); nt["title"]=update.message.text.strip(); context.user_data["newtask"]=nt
    await update.message.reply_text("Теперь введите *описание* (кратко):", parse_mode="Markdown", reply_markup=ForceReply(selective=True)); return T_NEW_DESC

async def t_new_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nt=context.user_data.get("newtask",{}); nt["desc"]=update.message.text.strip(); context.user_data["newtask"]=nt
    now_local=datetime.now(tz)
    presets=[("Сегодня 19:00", now_local.replace(hour=19,minute=0).strftime("%Y-%m-%d %H:%M")),
             ("Завтра 18:00",(now_local+timedelta(days=1)).replace(hour=18,minute=0).strftime("%Y-%m-%d %H:%M")),
             ("Через 3 дня 12:00",(now_local+timedelta(days=3)).replace(hour=12,minute=0).strftime("%Y-%m-%d %H:%M"))]
    rows=[[(label, f"t:new:duepreset:{val}")] for (label,val) in presets]; rows.append([("Ввести вручную…","t:new:due:manual")]); rows.append([("❌ Отмена","home")])
    await update.message.reply_text("Выберите срок сдачи или введите вручную:", reply_markup=kb(rows)); return T_NEW_DUE

async def t_new_duepreset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer(); val=cq.data.split(":")[-1]
    nt=context.user_data.get("newtask",{}); nt["due_str"]=val; context.user_data["newtask"]=nt
    await cq.message.edit_text(f"Срок: {val}\n\nПодтвердить создание задания?", reply_markup=kb([[("✅ Создать","t:new:confirm")],[("◀️ Назад","t:tasks")]])); return T_NEW_CONFIRM

async def t_new_due_manual_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    await cq.message.reply_text("Введите срок в формате YYYY-MM-DD HH:MM:", reply_markup=ForceReply(selective=True)); return T_NEW_DUE

async def t_new_due_manual_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nt=context.user_data.get("newtask",{}); nt["due_str"]=update.message.text.strip(); context.user_data["newtask"]=nt
    await update.message.reply_text(f"Срок: {nt['due_str']}\n\nПодтвердить создание задания?", reply_markup=kb([[("✅ Создать","t:new:confirm")],[("❌ Отмена","home")]])); return T_NEW_CONFIRM

async def t_new_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer(); con=connect(); nt=context.user_data.get("newtask",{})
    try: due_local=tz.localize(datetime.strptime(nt["due_str"], "%Y-%m-%d %H:%M"))
    except Exception:
        await cq.message.edit_text("Неверный формат даты. Попробуйте снова.", reply_markup=kb([[("◀️ Назад","t:tasks")]])); return ConversationHandler.END
    due_iso=due_local.astimezone(pytz.UTC).isoformat()
    group_id=student_tg_id=None
    if nt.get("target_kind")=="group":
        group_id=nt.get("group_id")
    else:
        row=connect().execute("SELECT tg_id FROM users WHERE username=?", (nt.get("student_username"),)).fetchone()
        if not row:
            await cq.message.edit_text("Ученик не найден. Попросите его написать боту /start.", reply_markup=kb([[("◀️ Назад","t:tasks")]])); return ConversationHandler.END
        student_tg_id=row["tg_id"]
    aid=create_assignment(con, nt["title"], nt["desc"], due_iso, group_id, student_tg_id, cq.from_user.id)
    await cq.message.edit_text(f"Задание создано: #{aid} — {nt['title']}", reply_markup=kb([[("📚 К заданиям","t:tasks")],[("🏠 Домой","home")]])); context.user_data["newtask"]={}; return ConversationHandler.END

async def t_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer(); con=connect(); sub=get_pending_submission(con)
    if not sub: await cq.message.edit_text("Непроверенных работ нет 🎉", reply_markup=kb([[("🏠 Домой","home")]])); return
    text=f"Submission #{sub['id']} по заданию #{sub['assignment_id']}\nСтудент tg_id: {sub['student_tg_id']}"
    rows=[[("5",f"t:grade:{sub['id']}:5"),("4",f"t:grade:{sub['id']}:4"),("3",f"t:grade:{sub['id']}:3"),("2",f"t:grade:{sub['id']}:2")],[("Следующая ▶️","t:review")],[("🏠 Домой","home")]]
    await cq.message.edit_text(text, reply_markup=kb(rows))

async def t_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    _,_,sid,grade=cq.data.split(":"); sid=int(sid); con=connect()
    # запросим комментарий отдельным сообщением
    context.user_data["grade_sid"]=sid; context.user_data["grade_val"]=grade
    await cq.message.reply_text("Введите комментарий к оценке (или '-' для пропуска):", reply_markup=ForceReply(selective=True))
    return T_NEW_CONFIRM  # переиспользуем состояние для ожидания одного сообщения

async def t_grade_comment_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con=connect(); sid=context.user_data.get("grade_sid"); grade=context.user_data.get("grade_val")
    feedback=update.message.text.strip(); 
    if feedback=="-": feedback=""
    set_grade(con, sid, grade, feedback, update.effective_user.id)
    await update.message.reply_text(f"Оценка сохранена: {grade}. Комментарий: {feedback or '—'}", reply_markup=home_keyboard_for({"role":"teacher"}))
    context.user_data["grade_sid"]=None; context.user_data["grade_val"]=None
    return ConversationHandler.END

async def t_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer(); con=connect(); gs=list_groups(con)
    rows=[[(g['name'], "noop")] for g in gs[:20]]; rows.append([("➕ Добавить группу","t:group:add")]); rows.append([("◀️ Назад","home")])
    await cq.message.edit_text("Группы:", reply_markup=kb(rows))

async def t_group_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    await cq.message.reply_text("Название новой группы:", reply_markup=ForceReply(selective=True)); return T_ADD_GROUP_NAME

async def t_group_add_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con=connect(); name=update.message.text.strip(); g=get_or_create_group(con,name)
    await update.message.reply_text(f"Группа создана: {g['name']}", reply_markup=home_keyboard_for({"role":"teacher"})); return ConversationHandler.END

async def t_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer()
    await cq.message.edit_text("Расписание:", reply_markup=kb([[("➕ Добавить занятие","t:sch:add")],[("◀️ Назад","home")]]))

async def t_schedule_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer(); con=connect(); gs=list_groups(con)
    rows=[[(g['name'], f"t:sch:g:{g['id']}")] for g in gs[:20]]; rows.append([("❌ Отмена","home")])
    await cq.message.edit_text("Выберите группу:", reply_markup=kb(rows)); return T_SCHEDULE_GROUP

async def t_schedule_group_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer(); gid=int(cq.data.split(":")[-1])
    context.user_data["sch"]={"gid":gid}
    await cq.message.reply_text("Введите дату и время (YYYY-MM-DD HH:MM):", reply_markup=ForceReply(selective=True)); return T_SCHEDULE_DATETIME

async def t_schedule_datetime_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sch"]["dt"]=update.message.text.strip()
    await update.message.reply_text("Место/ссылка (Zoom, адрес и т.п.):", reply_markup=ForceReply(selective=True)); return T_SCHEDULE_LOCATION

async def t_schedule_location_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sch=context.user_data["sch"]; sch["loc"]=update.message.text.strip()
    await update.message.reply_text(f"Добавить занятие?\nГруппа: {sch['gid']}\nКогда: {sch['dt']}\nГде: {sch['loc']}", reply_markup=kb([[("✅ Добавить","t:sch:confirm")],[("❌ Отмена","home")]])); return T_SCHEDULE_CONFIRM

async def send_lesson_reminder(context: ContextTypes.DEFAULT_TYPE):
    con=connect(); data=context.job.data; group_id=data["group_id"]; time_str=data["time_str"]; location=data["location"]
    rows=con.execute("SELECT tg_id FROM users WHERE group_id=?", (group_id,)).fetchall()
    for r in rows:
        try: await context.bot.send_message(r["tg_id"], f"🔔 Напоминание: занятие через 1 час, в {time_str}. Место/ссылка: {location}")
        except: pass

async def t_schedule_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query; await cq.answer(); con=connect(); sch=context.user_data.get("sch",{})
    try: dt_local=tz.localize(datetime.strptime(sch["dt"], "%Y-%m-%d %H:%M"))
    except Exception:
        await cq.message.edit_text("Неверная дата. Попробуйте снова.", reply_markup=kb([[("◀️ Назад","home")]])); return ConversationHandler.END
    dt_utc=dt_local.astimezone(pytz.UTC)
    add_lesson(con, sch["gid"], dt_utc.isoformat(), 60, sch["loc"], "")
    remind_at=dt_utc - timedelta(minutes=60)
    context.job_queue.run_once(send_lesson_reminder, when=remind_at, data={"group_id": sch["gid"], "time_str": dt_local.strftime("%Y-%m-%d %H:%M"), "location": sch["loc"]})
    await cq.message.edit_text("Занятие добавлено и напоминание запланировано ✅", reply_markup=kb([[("🏠 Домой","home")]]))
    context.user_data["sch"]={}; return ConversationHandler.END

def build_app():
    init_db(); app=Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_home, pattern=r"^home$"))
    app.add_handler(CallbackQueryHandler(pick_role, pattern=r"^role:(teacher|student)$"))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(pick_role, pattern=r"^role:teacher$")],
                                       states={ AWAIT_TEACHER_CODE:[MessageHandler(filters.TEXT & ~filters.COMMAND, teacher_code_message)]},
                                       fallbacks=[CommandHandler("start", start)]))
    # Student
    app.add_handler(CallbackQueryHandler(student_join, pattern=r"^s:join:(\d+|other)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_maybe_join))
    app.add_handler(CallbackQueryHandler(s_tasks, pattern=r"^s:tasks:\d+$"))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(s_submit_pick, pattern=r"^s:submit(:\d+)?$")],
                                       states={ S_SUBMIT_WAIT:[MessageHandler(~filters.COMMAND, s_submit_receive)]},
                                       fallbacks=[CallbackQueryHandler(s_submit_cancel, pattern=r"^s:submit:cancel$")]))
    app.add_handler(CallbackQueryHandler(s_schedule, pattern=r"^s:schedule$"))
    app.add_handler(CallbackQueryHandler(s_help, pattern=r"^s:help$"))
    # Teacher
    app.add_handler(CallbackQueryHandler(t_menu_tasks, pattern=r"^t:tasks$"))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(t_new_start, pattern=r"^t:new:start$")],
        states={ T_NEW_TARGET:[CallbackQueryHandler(t_new_target, pattern=r"^t:new:target:(group|student)$")],
                 T_NEW_GROUP:[CallbackQueryHandler(t_new_pick_group, pattern=r"^t:new:group:\d+$")],
                 T_NEW_STUDENT:[MessageHandler(filters.TEXT & ~filters.COMMAND, t_new_student_username)],
                 T_NEW_TITLE:[MessageHandler(filters.TEXT & ~filters.COMMAND, t_new_title)],
                 T_NEW_DESC:[MessageHandler(filters.TEXT & ~filters.COMMAND, t_new_desc)],
                 T_NEW_DUE:[CallbackQueryHandler(t_new_duepreset, pattern=r"^t:new:duepreset:.+"),
                            CallbackQueryHandler(t_new_due_manual_request, pattern=r"^t:new:due:manual$"),
                            MessageHandler(filters.TEXT & ~filters.COMMAND, t_new_due_manual_receive)],
                 T_NEW_CONFIRM:[CallbackQueryHandler(t_new_confirm, pattern=r"^t:new:confirm$")]},
        fallbacks=[CommandHandler("start", start)]))
    app.add_handler(CallbackQueryHandler(t_review, pattern=r"^t:review$"))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(t_grade, pattern=r"^t:grade:\d+:\d$")],
                                       states={ T_NEW_CONFIRM:[MessageHandler(filters.TEXT & ~filters.COMMAND, t_grade_comment_receive)]},
                                       fallbacks=[CommandHandler("start", start)]))
    app.add_handler(CallbackQueryHandler(t_groups, pattern=r"^t:groups$"))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(t_group_add, pattern=r"^t:group:add$")],
                                       states={ T_ADD_GROUP_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, t_group_add_receive)]},
                                       fallbacks=[CommandHandler("start", start)]))
    app.add_handler(CallbackQueryHandler(t_schedule, pattern=r"^t:schedule$"))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(t_schedule_add, pattern=r"^t:sch:add$")],
                                       states={ T_SCHEDULE_GROUP:[CallbackQueryHandler(t_schedule_group_pick, pattern=r"^t:sch:g:\d+$")],
                                                T_SCHEDULE_DATETIME:[MessageHandler(filters.TEXT & ~filters.COMMAND, t_schedule_datetime_receive)],
                                                T_SCHEDULE_LOCATION:[MessageHandler(filters.TEXT & ~filters.COMMAND, t_schedule_location_receive)],
                                                T_SCHEDULE_CONFIRM:[CallbackQueryHandler(t_schedule_confirm, pattern=r"^t:sch:confirm$")]},
                                       fallbacks=[CommandHandler("start", start)]))
    return app

async def main(): app=build_app(); await app.run_polling()
if __name__=="__main__": asyncio.run(main())
