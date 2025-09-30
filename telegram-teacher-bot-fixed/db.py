# (same DB as ранее, укорочено для фикса UI)
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
DB_PATH="bot.db"
def connect():
    con=sqlite3.connect(DB_PATH,check_same_thread=False); con.row_factory=sqlite3.Row; return con
def init_db():
    with closing(connect()) as con, con:
        con.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY,tg_id INTEGER UNIQUE,username TEXT,full_name TEXT,role TEXT,group_id INTEGER,created_at TEXT);
        CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY,name TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS assignments (id INTEGER PRIMARY KEY,title TEXT,description TEXT,due_at TEXT,group_id INTEGER,student_tg_id INTEGER,created_by_tg_id INTEGER,created_at TEXT);
        CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY,assignment_id INTEGER,student_tg_id INTEGER,text_content TEXT,file_id TEXT,file_type TEXT,submitted_at TEXT,grade TEXT,feedback TEXT,graded_by_tg_id INTEGER,graded_at TEXT);
        CREATE TABLE IF NOT EXISTS lessons (id INTEGER PRIMARY KEY,group_id INTEGER,starts_at TEXT,duration_min INTEGER,location TEXT,notes TEXT);
        ''')
def now_iso(): from datetime import datetime,timezone; return datetime.now(timezone.utc).isoformat()
def get_user(con,tg_id): r=con.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone(); return dict(r) if r else None
def upsert_user(con,tg_id,username,full_name,role=None):
    u=get_user(con,tg_id)
    if u:
        if role and u.get("role")!=role: con.execute("UPDATE users SET role=? WHERE tg_id=?", (role,tg_id))
        return get_user(con,tg_id)
    con.execute("INSERT INTO users (tg_id,username,full_name,role,created_at) VALUES (?,?,?,?,?)",(tg_id,username,full_name,role,now_iso())); return get_user(con,tg_id)
def set_user_group(con,tg_id,group_id): con.execute("UPDATE users SET group_id=? WHERE tg_id=?", (group_id,tg_id))
def get_or_create_group(con,name):
    r=con.execute("SELECT * FROM groups WHERE name=?", (name,)).fetchone()
    if r: return dict(r)
    con.execute("INSERT INTO groups (name) VALUES (?)",(name,)); r=con.execute("SELECT * FROM groups WHERE name=?", (name,)).fetchone(); return dict(r)
def list_groups(con): return [dict(r) for r in con.execute("SELECT * FROM groups ORDER BY name")]
def create_assignment(con,title,description,due_at,group_id,student_tg_id,created_by_tg_id):
    con.execute("INSERT INTO assignments (title,description,due_at,group_id,student_tg_id,created_by_tg_id,created_at) VALUES (?,?,?,?,?,?,?)",(title,description,due_at,group_id,student_tg_id,created_by_tg_id,now_iso())); return con.execute("SELECT last_insert_rowid()").fetchone()[0]
def list_student_assignments(con,student_tg_id):
    u=get_user(con,student_tg_id)
    return [] if not u else [dict(r) for r in con.execute("SELECT * FROM assignments WHERE (student_tg_id=? OR (group_id IS NOT NULL AND group_id=?)) ORDER BY id DESC",(student_tg_id,u.get("group_id")))]
def create_submission(con,assignment_id,student_tg_id,text_content=None,file_id=None,file_type=None):
    con.execute("INSERT INTO submissions (assignment_id,student_tg_id,text_content,file_id,file_type,submitted_at) VALUES (?,?,?,?,?,?)",(assignment_id,student_tg_id,text_content,file_id,file_type,now_iso())); return con.execute("SELECT last_insert_rowid()").fetchone()[0]
def get_pending_submission(con): r=con.execute("SELECT * FROM submissions WHERE grade IS NULL ORDER BY submitted_at ASC LIMIT 1").fetchone(); return dict(r) if r else None
def set_grade(con,submission_id,grade,feedback,teacher_tg_id): con.execute("UPDATE submissions SET grade=?,feedback=?,graded_by_tg_id=?,graded_at=? WHERE id=?",(grade,feedback,teacher_tg_id,now_iso(),submission_id))
def add_lesson(con,group_id,starts_at_iso,duration_min,location,notes): con.execute("INSERT INTO lessons (group_id,starts_at,duration_min,location,notes) VALUES (?,?,?,?,?)",(group_id,starts_at_iso,duration_min,location,notes)); return con.execute("SELECT last_insert_rowid()").fetchone()[0]
def list_upcoming_lessons_for_student(con,student_tg_id,now_iso_str):
    u=get_user(con,student_tg_id)
    return [] if not u or not u.get("group_id") else [dict(r) for r in con.execute("SELECT * FROM lessons WHERE group_id=? AND starts_at>=? ORDER BY starts_at ASC LIMIT 10",(u["group_id"],now_iso_str))]
def list_future_lessons(con,now_iso_str): return [dict(r) for r in con.execute("SELECT * FROM lessons WHERE starts_at>=? ORDER BY starts_at ASC",(now_iso_str,))]
