import sqlite3
from contextlib import closing
from datetime import datetime, timezone

DB_PATH = "bot.db"

def connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with closing(connect()) as con, con:
        con.executescript(
            '''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER UNIQUE,
                username TEXT,
                full_name TEXT,
                role TEXT CHECK(role IN ('teacher','student','parent')),
                group_id INTEGER,
                streak_days INTEGER DEFAULT 0,
                last_activity TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                due_at TEXT,
                group_id INTEGER,
                student_tg_id INTEGER,
                created_by_tg_id INTEGER,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER,
                student_tg_id INTEGER,
                text_content TEXT,
                file_id TEXT,
                file_type TEXT,
                submitted_at TEXT,
                grade TEXT,
                feedback TEXT,
                graded_by_tg_id INTEGER,
                graded_at TEXT
            );
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                starts_at TEXT,
                duration_min INTEGER,
                location TEXT,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS parents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_tg_id INTEGER,
                parent_tg_id INTEGER,
                UNIQUE(student_tg_id, parent_tg_id)
            );
            CREATE TABLE IF NOT EXISTS flashcards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                front TEXT,
                back TEXT,
                created_by_tg_id INTEGER,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS flash_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER,
                student_tg_id INTEGER,
                status TEXT, -- unknown/learning/known
                last_seen TEXT,
                UNIQUE(card_id, student_tg_id)
            );
            CREATE TABLE IF NOT EXISTS quizzes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                question TEXT,
                correct TEXT,
                wrong1 TEXT,
                wrong2 TEXT,
                wrong3 TEXT,
                created_by_tg_id INTEGER,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quiz_id INTEGER,
                student_tg_id INTEGER,
                is_correct INTEGER,
                answered_at TEXT
            );
            '''
        )

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_user(con, tg_id):
    row = con.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
    return dict(row) if row else None

def upsert_user(con, tg_id, username, full_name, role=None):
    u = get_user(con, tg_id)
    if u:
        if role and u['role'] != role:
            con.execute("UPDATE users SET role=? WHERE tg_id=?", (role, tg_id))
        return get_user(con, tg_id)
    con.execute(
        "INSERT INTO users (tg_id, username, full_name, role, created_at) VALUES (?,?,?,?,?)",
        (tg_id, username, full_name, role, now_iso()),
    )
    return get_user(con, tg_id)

def set_user_group(con, tg_id, group_id):
    con.execute("UPDATE users SET group_id=? WHERE tg_id=?", (group_id, tg_id))

def get_or_create_group(con, name):
    row = con.execute("SELECT * FROM groups WHERE name=?", (name,)).fetchone()
    if row:
        return dict(row)
    con.execute("INSERT INTO groups (name) VALUES (?)", (name,))
    row = con.execute("SELECT * FROM groups WHERE name=?", (name,)).fetchone()
    return dict(row)

def list_groups(con):
    return [dict(r) for r in con.execute("SELECT * FROM groups ORDER BY name")]

def create_assignment(con, title, description, due_at, group_id, student_tg_id, created_by_tg_id):
    con.execute(
        "INSERT INTO assignments (title, description, due_at, group_id, student_tg_id, created_by_tg_id, created_at) VALUES (?,?,?,?,?,?,?)",
        (title, description, due_at, group_id, student_tg_id, created_by_tg_id, now_iso())
    )
    aid = con.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return aid

def list_student_assignments(con, student_tg_id):
    u = get_user(con, student_tg_id)
    if not u:
        return []
    return [dict(r) for r in con.execute(
        "SELECT * FROM assignments WHERE (student_tg_id=? OR (group_id IS NOT NULL AND group_id=?)) ORDER BY id DESC",
        (student_tg_id, u["group_id"])
    )]

def create_submission(con, assignment_id, student_tg_id, text_content=None, file_id=None, file_type=None):
    con.execute(
        "INSERT INTO submissions (assignment_id, student_tg_id, text_content, file_id, file_type, submitted_at) VALUES (?,?,?,?,?,?)",
        (assignment_id, student_tg_id, text_content, file_id, file_type, now_iso())
    )
    sid = con.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return sid

def get_pending_submission(con):
    row = con.execute(
        "SELECT * FROM submissions WHERE grade IS NULL ORDER BY submitted_at ASC LIMIT 1").fetchone()
    return dict(row) if row else None

def set_grade(con, submission_id, grade, feedback, teacher_tg_id):
    con.execute(
        "UPDATE submissions SET grade=?, feedback=?, graded_by_tg_id=?, graded_at=? WHERE id=?",
        (grade, feedback, teacher_tg_id, now_iso(), submission_id)
    )

def bump_streak(con, student_tg_id, today_str):
    u = get_user(con, student_tg_id)
    last = u["last_activity"]
    new_streak = 1
    if last:
        if last[:10] == today_str[:10]:
            new_streak = u["streak_days"] or 1
        else:
            # простая логика: если вчера — +1, иначе 1
            from datetime import datetime
            d_prev = datetime.fromisoformat(last).date()
            d_today = datetime.fromisoformat(today_str).date()
            if (d_today - d_prev).days == 1:
                new_streak = (u["streak_days"] or 0) + 1
            else:
                new_streak = 1
    con.execute("UPDATE users SET last_activity=?, streak_days=? WHERE tg_id=?", (today_str, new_streak, student_tg_id))
    return new_streak

def add_lesson(con, group_id, starts_at_iso, duration_min, location, notes):
    con.execute(
        "INSERT INTO lessons (group_id, starts_at, duration_min, location, notes) VALUES (?,?,?,?,?)",
        (group_id, starts_at_iso, duration_min, location, notes)
    )
    lid = con.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return lid

def list_upcoming_lessons_for_student(con, student_tg_id, now_iso_str):
    u = get_user(con, student_tg_id)
    if not u or not u["group_id"]:
        return []
    return [dict(r) for r in con.execute(
        "SELECT * FROM lessons WHERE group_id=? AND starts_at>=? ORDER BY starts_at ASC LIMIT 10",
        (u["group_id"], now_iso_str)
    )]

def list_future_lessons(con, now_iso_str):
    return [dict(r) for r in con.execute(
        "SELECT * FROM lessons WHERE starts_at>=? ORDER BY starts_at ASC",
        (now_iso_str, )
    )]

def list_future_assignments(con, now_iso_str):
    return [dict(r) for r in con.execute(
        "SELECT * FROM assignments WHERE due_at>=? ORDER BY due_at ASC",
        (now_iso_str, )
    )]

def link_parent(con, student_tg_id, parent_tg_id):
    con.execute("INSERT OR IGNORE INTO parents (student_tg_id, parent_tg_id) VALUES (?,?)", (student_tg_id, parent_tg_id))

def get_parents(con, student_tg_id):
    return [r["parent_tg_id"] for r in con.execute("SELECT parent_tg_id FROM parents WHERE student_tg_id=?", (student_tg_id,)).fetchall()]

def add_flashcard(con, group_id, front, back, created_by_tg_id):
    con.execute("INSERT INTO flashcards (group_id, front, back, created_by_tg_id, created_at) VALUES (?,?,?,?,?)",
                (group_id, front, back, created_by_tg_id, now_iso()))

def get_random_card_for_student(con, student_tg_id):
    u = get_user(con, student_tg_id)
    if not u or not u["group_id"]:
        return None
    # простая выборка случайной карточки группы
    return con.execute("SELECT * FROM flashcards WHERE group_id=? ORDER BY RANDOM() LIMIT 1", (u["group_id"],)).fetchone()

def set_card_progress(con, card_id, student_tg_id, status):
    con.execute("INSERT OR REPLACE INTO flash_progress (card_id, student_tg_id, status, last_seen) VALUES (?,?,?,?)",
                (card_id, student_tg_id, status, now_iso()))

def add_quiz(con, group_id, question, correct, wrong1, wrong2, wrong3, created_by_tg_id):
    con.execute("INSERT INTO quizzes (group_id, question, correct, wrong1, wrong2, wrong3, created_by_tg_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (group_id, question, correct, wrong1, wrong2, wrong3, created_by_tg_id, now_iso()))

def get_random_quiz_for_student(con, student_tg_id):
    u = get_user(con, student_tg_id)
    if not u or not u["group_id"]:
        return None
    return con.execute("SELECT * FROM quizzes WHERE group_id=? ORDER BY RANDOM() LIMIT 1", (u["group_id"],)).fetchone()

def save_quiz_result(con, quiz_id, student_tg_id, is_correct):
    con.execute("INSERT INTO quiz_results (quiz_id, student_tg_id, is_correct, answered_at) VALUES (?,?,?,?)",
                (quiz_id, student_tg_id, 1 if is_correct else 0, now_iso()))
