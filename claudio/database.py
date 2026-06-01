import logging
import sqlite3
from config import DATABASE

logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            original_format TEXT NOT NULL,
            target_format TEXT NOT NULL,
            output_filename TEXT,
            file_size INTEGER,
            engine TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            filename TEXT,
            detail TEXT,
            job_id TEXT,
            sharepoint_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL DEFAULT 'bug',
            message TEXT NOT NULL,
            page_url TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            admin_note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            admin_reply TEXT,
            replied_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            replied_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (replied_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price INTEGER NOT NULL DEFAULT 0,
            order_date TEXT NOT NULL,
            delivery_date TEXT,
            status TEXT NOT NULL DEFAULT '下書き',
            notes TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS chat_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '新しい会話',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL DEFAULT 'info',
            title TEXT NOT NULL,
            message TEXT,
            link TEXT,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            color TEXT DEFAULT '#fff',
            is_pinned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

    # Insert default settings if not present
    defaults = {
        "site_name": "Claudio",
        "default_role": "user",
        "max_upload_mb": "16",
        "allow_registration": "true",
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()

    # Migrate: add sharepoint_status column to conversions if missing
    try:
        conn.execute("ALTER TABLE conversions ADD COLUMN sharepoint_status TEXT DEFAULT NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migrate: add ms_email column to users if missing
    try:
        conn.execute("ALTER TABLE users ADD COLUMN ms_email TEXT DEFAULT NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migrate: add MS OAuth2 columns to users if missing
    for col_sql in [
        "ALTER TABLE users ADD COLUMN ms_oid TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN ms_access_token TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN ms_refresh_token TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN ms_token_expires_at TIMESTAMP DEFAULT NULL",
    ]:
        try:
            conn.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Migrate: add avatar_filename column to users if missing
    try:
        conn.execute("ALTER TABLE users ADD COLUMN avatar_filename TEXT DEFAULT NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migrate: add source and bot_reply columns to escalations if missing
    for col_sql in [
        "ALTER TABLE escalations ADD COLUMN source TEXT DEFAULT 'manual'",
        "ALTER TABLE escalations ADD COLUMN bot_reply TEXT DEFAULT NULL",
    ]:
        try:
            conn.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass

    logger.info("Database initialized successfully")

    # Clean up stale "running" tasks from previous server crashes
    conn.execute(
        "UPDATE conversions SET status='failed', error_message='サーバー再起動により中断されました' WHERE status='running'"
    )
    conn.commit()
    conn.close()


def create_notification(user_id: int, title: str, message: str = "",
                       notification_type: str = "info", link: str = ""):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO notifications (user_id, type, title, message, link) VALUES (?, ?, ?, ?, ?)",
            (user_id, notification_type, title, message, link),
        )
        conn.commit()
    finally:
        conn.close()


def log_activity(user_id: int, action_type: str, filename: str = None,
                 detail: str = None, job_id: str = None, sharepoint_path: str = None):
    """Record an activity to activity_log."""
    conn = get_db()
    conn.execute(
        """INSERT INTO activity_log (user_id, action_type, filename, detail, job_id, sharepoint_path)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, action_type, filename, detail, job_id, sharepoint_path),
    )
    conn.commit()
    conn.close()
