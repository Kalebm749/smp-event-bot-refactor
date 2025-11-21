#!/usr/bin/python3.12
import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from database_manager import db_manager

load_dotenv()
DATABASE_FILE = os.getenv("DATABASE_FILE")
DATABASE_DIR = os.getenv("DATABASE_DIR")
DATABASE_SCHEMA = os.getenv("DATABASE_SCHEMA")

SCHEMA_PATH = f"{DATABASE_DIR}{DATABASE_SCHEMA}"
DATABASE_PATH = f"{DATABASE_DIR}{DATABASE_FILE}"

def insert_task(event_id, task_name, scheduled_time, priority):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    timestamp = scheduled_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    query = """
    INSERT INTO event_tasks (event_id, task_name, scheduled_time, priority)
    VALUES (?, ?, ?, ?);
    """
    return db.db_query_with_params(query, (event_id, task_name, timestamp, priority))

def get_next_pending_task_time():
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    SELECT scheduled_time 
    FROM event_tasks 
    WHERE completed = 0
    ORDER BY scheduled_time ASC
    LIMIT 1;
    """
    result = db.db_query(query)
    if result and result[0]:
        return datetime.fromisoformat(result[0][0].replace('Z', '+00:00'))
    return None

def get_tasks_to_execute(current_time, window_seconds):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    current_iso = current_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    window_time = (current_time + timedelta(seconds=window_seconds)).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    query = """
    SELECT t.*, e.unique_event_name, e.name, e.event_json
    FROM event_tasks t
    JOIN events e ON t.event_id = e.id
    WHERE t.completed = 0
    AND t.scheduled_time <= ?
    ORDER BY t.priority DESC, t.scheduled_time ASC;
    """
    results = db.db_query_with_params(query, (window_time,))
    
    tasks = []
    for row in results:
        tasks.append({
            'id': row[0],
            'event_id': row[1],
            'task_name': row[2],
            'scheduled_time': datetime.fromisoformat(row[3].replace('Z', '+00:00')),
            'priority': row[4],
            'unique_event_name': row[8],
            'event_name': row[9],
            'event_json': row[10]
        })
    return tasks

def mark_task_completed(task_id, execution_length_ms):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    completed_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    query = """
    UPDATE event_tasks
    SET completed = 1,
        execution_length_ms = ?,
        completed_time = ?
    WHERE id = ?;
    """
    try:
        db_conn = db.db_connect()
        cursor = db_conn.cursor()
        cursor.execute(query, (execution_length_ms, completed_time, task_id))
        db_conn.commit()
        cursor.close()
        db_conn.close()
        return True
    except Exception as e:
        log_message(f"Error marking task {task_id} completed: {e}", "ERROR")
        return False

def get_all_tasks():
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    SELECT t.*, e.unique_event_name
    FROM event_tasks t
    LEFT JOIN events e ON t.event_id = e.id
    ORDER BY t.scheduled_time ASC;
    """
    results = db.db_query(query)
    tasks = []
    for row in results:
        tasks.append({
            'id': row[0],
            'event_id': row[1],
            'task_name': row[2],
            'scheduled_time': row[3],
            'priority': row[4],
            'completed': bool(row[5]),
            'execution_length_ms': row[6],
            'completed_time': row[7],
            'unique_event_name': row[8] if len(row) > 8 else None
        })
    return tasks

def find_missing_24h_notif():
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    missing_24_query = """
    SELECT e.*
    FROM events e
    LEFT JOIN event_notifications n
        ON e.id = n.event_id
        AND n.notification_type = '24h'
    WHERE e.start_time > strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '+30 minutes')
    AND e.start_time <= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '+1 day')
    AND n.id IS NULL
    AND e.event_over = 0;
    """
    return db.db_query(missing_24_query)

def find_missing_30m_notif():
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    missing_30_query = """
    SELECT e.*
    FROM events e
    LEFT JOIN event_notifications n
        ON e.id = n.event_id
        AND n.notification_type = '30min'
    WHERE e.start_time > strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    AND e.start_time <= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '+30 minutes')
    AND e.event_over = 0
    AND n.id IS NULL;
    """
    return db.db_query(missing_30_query)

def find_missing_now_notif():
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    missing_start_now_notif_query = """
    SELECT e.*
    FROM events e
    LEFT JOIN event_notifications n
        ON e.id = n.event_id
        AND n.notification_type = 'start'
    WHERE e.start_time <= strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    AND e.event_started = 1
    AND e.event_over = 0
    AND n.id IS NULL;
    """
    return db.db_query(missing_start_now_notif_query)

def events_needing_started():
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    events_needing_started_query = """
    SELECT *
    FROM events
    WHERE start_time <= strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    AND event_started = 0
    AND event_over = 0;
    """
    return db.db_query(events_needing_started_query)

def events_needing_ending():
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    events_needing_ending_query = """
    SELECT *
    FROM events
    WHERE event_in_progress = 1
    AND end_time < strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    AND event_over = 0;
    """
    return db.db_query(events_needing_ending_query)

def events_needing_scoreboard_display():
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    events_need_display_query = """
    SELECT *
    FROM events
    WHERE event_in_progress = 1
    AND (last_scoreboard_time IS NULL 
         OR last_scoreboard_time <= strftime('%Y-%m-%dT%H:%M:%SZ', datetime('now', '-10 minutes')));
    """
    return db.db_query(events_need_display_query)

def start_event_by_id(event_id):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    start_event_query = """
    UPDATE events
    SET event_in_progress = 1,
        event_started = 1
    WHERE id = ?;
    """
    try:
        db_conn = db.db_connect()
        cursor = db_conn.cursor()
        cursor.execute(start_event_query, (event_id,))
        db_conn.commit()
        affected_rows = cursor.rowcount
        cursor.close()
        db_conn.close()
        log_message(f"Event {event_id} marked as started (affected {affected_rows} rows)")
        return affected_rows > 0
    except Exception as e:
        log_message(f"Error starting event {event_id}: {e}", "ERROR")
        return False

def end_event_by_id(event_id):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    end_event_query = """
    UPDATE events
    SET event_in_progress = 0,
        event_over = 1
    WHERE id = ?;
    """
    try:
        db_conn = db.db_connect()
        cursor = db_conn.cursor()
        cursor.execute(end_event_query, (event_id,))
        db_conn.commit()
        affected_rows = cursor.rowcount
        cursor.close()
        db_conn.close()
        log_message(f"Event {event_id} marked as ended (affected {affected_rows} rows)")
        return affected_rows > 0
    except Exception as e:
        log_message(f"Error ending event {event_id}: {e}", "ERROR")
        return False

def update_scoreboard_display_time(event_id):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    current_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    update_query = """
    UPDATE events
    SET last_scoreboard_time = ?
    WHERE id = ?;
    """
    try:
        db_conn = db.db_connect()
        cursor = db_conn.cursor()
        cursor.execute(update_query, (current_time, event_id))
        db_conn.commit()
        affected_rows = cursor.rowcount
        cursor.close()
        db_conn.close()
        return affected_rows > 0
    except Exception as e:
        log_message(f"Error updating scoreboard time for event {event_id}: {e}", "ERROR")
        return False

def send_24h_notification(event_id):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    INSERT INTO event_notifications (event_id, notification_type)
    VALUES (?, '24h');
    """
    return db.db_query_with_params(query, (event_id,))

def send_30min_notification(event_id):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    INSERT INTO event_notifications (event_id, notification_type)
    VALUES (?, '30min');
    """
    return db.db_query_with_params(query, (event_id,))

def send_start_notification(event_id):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    INSERT INTO event_notifications (event_id, notification_type)
    VALUES (?, 'start');
    """
    return db.db_query_with_params(query, (event_id,))

def send_end_notification(event_id):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    INSERT INTO event_notifications (event_id, notification_type)
    VALUES (?, 'end');
    """
    return db.db_query_with_params(query, (event_id,))

def get_event_by_id(event_id):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    SELECT * FROM events WHERE id = ?;
    """
    result = db.db_query_with_params(query, (event_id,))
    return result[0] if result else None

def insert_event(unique_name, name, event_json, description, start_time, end_time, scoreboard_interval=600):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    INSERT INTO events (unique_event_name, name, event_json, description, start_time, end_time, scoreboard_interval)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    return db.db_query_with_params(query, (unique_name, name, event_json, description, start_time, end_time, scoreboard_interval))

def log_message(message, level="INFO"):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    query = """
    INSERT INTO logs (timestamp, message, log_level)
    VALUES (?, ?, ?);
    """
    return db.db_query_with_params(query, (timestamp, message, level))

def log_message_with_timestamp(message, level="INFO", timestamp=None):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    if not timestamp:
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    query = """
    INSERT INTO logs (timestamp, message, log_level)
    VALUES (?, ?, ?);
    """
    return db.db_query_with_params(query, (timestamp, message, level))

def update_scoreboard_time(event_id, timestamp):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    UPDATE events
    SET last_scoreboard_time = ?
    WHERE id = ?;
    """
    try:
        db_conn = db.db_connect()
        cursor = db_conn.cursor()
        cursor.execute(query, (timestamp, event_id))
        db_conn.commit()
        affected_rows = cursor.rowcount
        cursor.close()
        db_conn.close()
        return affected_rows > 0
    except Exception as e:
        log_message(f"Error updating scoreboard time: {e}", "ERROR")
        return False

def get_event_id_by_unique_name(unique_name):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    SELECT id FROM events WHERE unique_event_name = ?;
    """
    result = db.db_query_with_params(query, (unique_name,))
    return result[0][0] if result else None

def insert_winner(event_id, player_name, final_score, was_online):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    query = """
    INSERT INTO event_winners (event_id, player_name, final_score, was_online, rewarded_at)
    VALUES (?, ?, ?, ?, ?);
    """
    return db.db_query_with_params(query, (event_id, player_name, final_score, 1 if was_online else 0, timestamp))

def get_event_winners(event_id):
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = """
    SELECT * FROM event_winners WHERE event_id = ?;
    """
    return db.db_query_with_params(query, (event_id,))

def get_last_event_id():
    db = db_manager(DATABASE_PATH, SCHEMA_PATH)
    query = "SELECT id FROM events ORDER BY id DESC LIMIT 1;"
    result = db.db_query(query)
    return result[0][0] if result else None