import sqlite3
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from app.db.session import build_engine


def test_upgrade_preserves_legacy_records(tmp_path):
    path = tmp_path / 'legacy.db'
    config = Config('alembic.ini')
    config.set_main_option('sqlalchemy.url', f'sqlite:///{path}')
    command.upgrade(config, '0001_legacy')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO students VALUES (42, 'Synthetic', '{}', '2026-01-01')")
        db.execute("INSERT INTO questionnaires VALUES ('synthetic', 'Synthetic', 1)")
        db.execute("INSERT INTO assessment_questions VALUES (1,'synthetic','key','Prompt','text',1,1,'[]')")
        db.execute("INSERT INTO student_answers VALUES (1,42,1,'\"Synthetic answer\"')")
        db.execute("INSERT INTO conversations VALUES (1,42,'synthetic','2026-01-01')")
        db.execute("INSERT INTO conversation_messages VALUES (1,1,'user','Synthetic message','completed',NULL,'2026-01-01')")
        tables = ['students', 'questionnaires', 'assessment_questions', 'student_answers', 'conversations', 'conversation_messages']
        before = {table: db.execute(f'SELECT * FROM {table}').fetchall() for table in tables}
        # Simulate the pre-Alembic installation.
        db.execute('DROP TABLE alembic_version')
    command.upgrade(config, 'head')
    command.upgrade(config, 'head')  # idempotent
    with sqlite3.connect(path) as db:
        assert before == {table: db.execute(f'SELECT * FROM {table}').fetchall() for table in tables}
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    engine = build_engine(f'sqlite:///{path}')
    assert 'auth_sessions' in inspect(engine).get_table_names()
    engine.dispose()


def test_email_migration_preserves_accounts_but_does_not_verify_them(tmp_path):
    path = tmp_path / 'accounts.db'
    config = Config('alembic.ini')
    config.set_main_option('sqlalchemy.url', f'sqlite:///{path}')
    command.upgrade(config, '0002_auth')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO students VALUES (42, 'Synthetic existing student', '{}', '2026-01-01')")
        db.execute("INSERT INTO users VALUES (7, 'synthetic@example.org', 'preserved-hash', 'student', '2026-01-01', 1, 42)")
        db.execute("INSERT INTO auth_sessions VALUES ('synthetic-session-hash',7,'synthetic-csrf-hash','2026-01-01','2099-01-01',NULL)")
        student = db.execute('SELECT * FROM students').fetchall()
        account = db.execute('SELECT * FROM users').fetchone()
    command.upgrade(config, 'head')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM students').fetchall() == student
        migrated = db.execute('SELECT * FROM users').fetchone()
        assert migrated[:-1] == account
        assert migrated[-1] is None
        assert db.execute('SELECT revoked_at FROM auth_sessions').fetchone()[0] is not None
        assert db.execute('SELECT COUNT(*) FROM email_challenges').fetchone()[0] == 0
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
