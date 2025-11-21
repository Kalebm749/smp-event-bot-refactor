#!/usr/bin/python3
"""
Database migration script to add event_tasks table and scoreboard_interval column
"""
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DATABASE_FILE = os.getenv("DATABASE_FILE", "event_database.db")
DATABASE_DIR = os.getenv("DATABASE_DIR", "./database/")
DATABASE_PATH = os.path.join(DATABASE_DIR, DATABASE_FILE)

def migrate_database():
    """Add new tables and columns for task-based execution"""
    
    # Create database directory if it doesn't exist
    os.makedirs(DATABASE_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # Check if event_tasks table exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='event_tasks'
    """)
    
    if not cursor.fetchone():
        print("Creating event_tasks table...")
        cursor.execute("""
        CREATE TABLE event_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            task_name TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            priority INTEGER NOT NULL,
            completed BOOLEAN NOT NULL DEFAULT 0,
            execution_length_ms INTEGER DEFAULT 0,
            completed_time TEXT NULL,
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
        )
        """)
        
        cursor.execute("""
        CREATE INDEX idx_event_tasks_schedule 
        ON event_tasks(completed, scheduled_time, priority)
        """)
        print("event_tasks table created successfully")
    
    # Check if scoreboard_interval column exists in events table
    cursor.execute("PRAGMA table_info(events)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'scoreboard_interval' not in columns:
        print("Adding scoreboard_interval column to events table...")
        cursor.execute("""
        ALTER TABLE events 
        ADD COLUMN scoreboard_interval INTEGER DEFAULT 600
        """)
        print("scoreboard_interval column added successfully")
    
    # Add triggers for event_tasks if they don't exist
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='trigger' AND name='enforce_tasks_times_insert'
    """)
    
    if not cursor.fetchone():
        print("Creating triggers for event_tasks...")
        cursor.execute("""
        CREATE TRIGGER enforce_tasks_times_insert
        BEFORE INSERT ON event_tasks
        FOR EACH ROW
        BEGIN
            SELECT CASE
                WHEN NEW.scheduled_time IS NOT NULL
                     AND NEW.scheduled_time NOT LIKE '____-__-__T__:__:__Z'
                THEN RAISE (ABORT, 'scheduled_time must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
            END;
        END
        """)
        
        cursor.execute("""
        CREATE TRIGGER enforce_tasks_times_update
        BEFORE UPDATE ON event_tasks
        FOR EACH ROW
        BEGIN
            SELECT CASE
                WHEN NEW.scheduled_time IS NOT NULL
                     AND NEW.scheduled_time NOT LIKE '____-__-__T__:__:__Z'
                THEN RAISE (ABORT, 'scheduled_time must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
            END;
            SELECT CASE
                WHEN NEW.completed_time IS NOT NULL
                     AND NEW.completed_time NOT LIKE '____-__-__T__:__:__Z'
                THEN RAISE (ABORT, 'completed_time must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
            END;
        END
        """)
        print("Triggers created successfully")
    
    conn.commit()
    conn.close()
    print("Database migration completed successfully!")
    
if __name__ == "__main__":
    try:
        migrate_database()
    except Exception as e:
        print(f"Migration failed: {e}")