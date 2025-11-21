import subprocess
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, Response, flash
from dotenv import load_dotenv
import os
import json
from datetime import datetime, timezone
from functools import wraps
import pytz
import platform
import sys
import socket
import re
from mcrcon import MCRcon

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
import sql_calendar
import schedule_events
from database_manager import db_manager

load_dotenv()
PASSWORD = os.getenv("ADMIN_PASSWORD")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

DATABASE_FILE = os.getenv("DATABASE_FILE", "event_database.db")
DATABASE_DIR = os.getenv("DATABASE_DIR", "./database/")
DATABASE_SCHEMA = os.getenv("DATABASE_SCHEMA", "schema.sql")
DATABASE_PATH = os.path.join(DATABASE_DIR, DATABASE_FILE)
SCHEMA_PATH = os.path.join(DATABASE_DIR, DATABASE_SCHEMA)

EVENTS_JSON_PATH = os.path.join(".", "events", "events_json")
LOGS_PATH = os.path.join(".", "logs")

def get_db():
    return db_manager(DATABASE_PATH, SCHEMA_PATH)

def start_event_handler():
    try:
        if not is_event_handler_running():
            if platform.system() == "Windows":
                subprocess.Popen(["python", "./src/event_handler.py"], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(["python3", "./src/event_handler.py"])
            return True
        return False
    except Exception as e:
        print("Error starting event handler:", e)
        return False

def stop_event_handler():
    try:
        if is_event_handler_running():
            if platform.system() == "Windows":
                subprocess.run(["taskkill", "/F", "/IM", "python.exe"])
            else:
                subprocess.run(["pkill", "-f", "event_handler.py"])
            return True
        return False
    except Exception as e:
        print("Error stopping event handler:", e)
        return False

def is_event_handler_running():
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["tasklist"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            return "event_handler.py" in result.stdout
        else:
            result = subprocess.run(
                ["pgrep", "-f", "event_handler.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            return result.returncode == 0
    except Exception as e:
        print("Error checking event handler:", e)
        return False

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def load_events_from_db():
    try:
        db = get_db()
        query = """
        SELECT id, unique_event_name, name, event_json, description, 
               start_time, end_time, event_in_progress, event_started, 
               event_over, last_scoreboard_time
        FROM events 
        ORDER BY start_time DESC
        """
        results = db.db_query(query)
        
        events = []
        for row in results:
            event = {
                "id": row[0],
                "unique_event_name": row[1],
                "name": row[2],
                "event_json": row[3],
                "description": row[4],
                "start": row[5],
                "end": row[6],
                "event_in_progress": bool(row[7]),
                "event_started": bool(row[8]),
                "event_over": bool(row[9]),
                "last_scoreboard_time": row[10]
            }
            events.append(event)
        
        return events
    except Exception as e:
        print(f"Error loading events from database: {e}")
        return []

def load_event_files():
    if os.path.exists(EVENTS_JSON_PATH):
        return [f for f in os.listdir(EVENTS_JSON_PATH) if f.endswith(".json")]
    return []

def load_logs_from_db():
    try:
        db = get_db()
        query = """
        SELECT timestamp, message, log_level 
        FROM logs 
        ORDER BY timestamp DESC 
        LIMIT 100
        """
        results = db.db_query(query)
        
        logs = []
        for row in results:
            logs.append({
                "timestamp": row[0],
                "message": row[1],
                "log_level": row[2]
            })
        
        return logs
    except Exception as e:
        print(f"Error loading logs from database: {e}")
        return []

def get_event_status(event):
    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(event["start"].replace('Z', '+00:00'))
    end = datetime.fromisoformat(event["end"].replace('Z', '+00:00'))
    
    if event.get("event_over"):
        return "completed"
    elif event.get("event_in_progress"):
        return "ongoing"
    elif start > now:
        return "future"
    elif start <= now <= end:
        return "should_be_ongoing"
    else:
        return "past"

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/tasks")
@login_required
def tasks():
    return render_template("tasks.html")

@app.route("/winners")
@login_required
def winners():
    return render_template("winners.html")

@app.route("/api/tasks")
@login_required
def api_tasks():
    tasks = sql_calendar.get_all_tasks()
    return jsonify(tasks)

@app.route("/api/tasks/delete", methods=["POST"])
@login_required
def api_delete_task():
    try:
        task_id = request.json.get("task_id")
        if not task_id:
            return jsonify({"success": False, "error": "No task ID provided"})
        
        db = get_db()
        
        # Check if task exists and is not completed
        check_query = "SELECT completed FROM event_tasks WHERE id = ?"
        result = db.db_query_with_params(check_query, (task_id,))
        
        if not result:
            return jsonify({"success": False, "error": "Task not found"})
        
        if result[0][0]:  # Task is completed
            return jsonify({"success": False, "error": "Cannot delete completed tasks"})
        
        # Delete the task
        delete_query = "DELETE FROM event_tasks WHERE id = ?"
        db.db_query_with_params(delete_query, (task_id,))
        
        sql_calendar.log_message(f"Admin deleted task {task_id} via web interface", "ADMIN")
        
        return jsonify({
            "success": True,
            "message": f"Task {task_id} deleted successfully"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            flash("Invalid password")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

@app.route("/api/calendar")
@login_required
def api_calendar():
    events = load_events_from_db()
    for e in events:
        e["status"] = get_event_status(e)
    return jsonify(events)

@app.route("/event_monitor")
@login_required
def event_monitor():
    return render_template("event_monitor.html")

@app.route("/database_viewer")
@login_required
def database_viewer():
    return render_template("database_viewer.html")

@app.route("/api/health/minecraft")
@login_required
def api_minecraft_health():
    try:
        rcon_host = os.getenv("RCON_HOST")
        if not rcon_host:
            return jsonify({
                "healthy": False,
                "status": "error",
                "error": "RCON_HOST not configured in .env",
                "server_ip": "Not configured"
            })
        
        minecraft_port = 25565
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        
        result = sock.connect_ex((rcon_host, minecraft_port))
        sock.close()
        
        if result == 0:
            return jsonify({
                "healthy": True,
                "status": "online",
                "message": f"Server at {rcon_host}:{minecraft_port} is reachable",
                "server_ip": rcon_host
            })
        else:
            return jsonify({
                "healthy": False,
                "status": "offline",
                "error": f"Cannot connect to {rcon_host}:{minecraft_port}",
                "server_ip": rcon_host
            })
            
    except Exception as e:
        return jsonify({
            "healthy": False,
            "status": "error",
            "error": str(e),
            "server_ip": rcon_host if 'rcon_host' in locals() else "Unknown"
        })

@app.route("/api/health/rcon")
@login_required 
def api_rcon_health():
    try:
        import subprocess
        
        script_path = os.path.join("src", "rcon_health_check.py")
        
        result = subprocess.run(
            [sys.executable, script_path], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        if result.returncode == 0:
            import json
            health_data = json.loads(result.stdout.strip())
            
            player_count = 0
            if health_data.get("result"):
                import re
                match = re.search(r'There are (\d+)', health_data["result"])
                if match:
                    player_count = int(match.group(1))
            
            health_data["player_count"] = player_count
            return jsonify(health_data)
        else:
            try:
                error_data = json.loads(result.stdout.strip())
                error_data["player_count"] = 0
                return jsonify(error_data)
            except:
                return jsonify({
                    "healthy": False,
                    "status": "error",
                    "error": f"RCON health check script failed: {result.stderr or 'Unknown error'}",
                    "player_count": 0
                })
                
    except subprocess.TimeoutExpired:
        return jsonify({
            "healthy": False,
            "status": "error",
            "error": "RCON health check timed out",
            "player_count": 0
        })
    except Exception as e:
        return jsonify({
            "healthy": False,
            "status": "error",
            "error": f"Failed to run RCON health check: {str(e)}",
            "player_count": 0
        })
    
@app.route("/api/health/overall")
@login_required
def api_overall_health():
    try:
        minecraft_response = api_minecraft_health()
        rcon_response = api_rcon_health()
        
        minecraft_data = minecraft_response.get_json()
        rcon_data = rcon_response.get_json()
        
        minecraft_healthy = minecraft_data.get("healthy", False)
        rcon_healthy = rcon_data.get("healthy", False)
        
        overall_healthy = minecraft_healthy and rcon_healthy
        
        issues = []
        if not minecraft_healthy:
            issues.append("Minecraft Server")
        if not rcon_healthy:
            issues.append("RCON Connection")
        
        return jsonify({
            "healthy": overall_healthy,
            "minecraft": minecraft_data,
            "rcon": rcon_data,
            "issues": issues,
            "status": "All systems operational" if overall_healthy else f"Issues: {', '.join(issues)}"
        })
        
    except Exception as e:
        return jsonify({
            "healthy": False,
            "status": "error",
            "error": str(e)
        })

@app.route("/api/database/info")
@login_required
def api_database_info():
    try:
        db = get_db()
        info = db.db_info()
        
        if os.path.exists(DATABASE_PATH):
            file_size = os.path.getsize(DATABASE_PATH)
            info["size_bytes"] = file_size
            info["size_mb"] = round(file_size / 1024 / 1024, 2)
        
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/database/table/<table_name>")
@login_required
def api_table_data(table_name):
    allowed_tables = ["events", "event_notifications", "logs", "event_winners", "event_tasks"]
    if table_name not in allowed_tables:
        return jsonify({"error": "Table not allowed"}), 400
    
    try:
        db = get_db()
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        
        count_query = f"SELECT COUNT(*) FROM {table_name}"
        count_result = db.db_query(count_query)
        total = count_result[0][0] if count_result else 0
        
        query = f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT {limit} OFFSET {offset}"
        results = db.db_query(query)
        
        column_query = f"PRAGMA table_info({table_name})"
        column_info = db.db_query(column_query)
        columns = [col[1] for col in column_info]
        
        rows = []
        for row in results:
            row_dict = {}
            for i, col_name in enumerate(columns):
                row_dict[col_name] = row[i]
            rows.append(row_dict)
        
        return jsonify({
            "table": table_name,
            "columns": columns,
            "rows": rows,
            "total": total,
            "limit": limit,
            "offset": offset
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/database/enhanced-table/<table_name>")
@login_required
def api_enhanced_table_data(table_name):
    allowed_tables = ["event_notifications", "event_winners", "event_tasks"]
    if table_name not in allowed_tables:
        return jsonify({"error": "Table not allowed"}), 400
    
    try:
        db = get_db()
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        
        if table_name == "event_notifications":
            query = f"""
            SELECT n.id, n.event_id, e.unique_event_name, e.name as event_name, 
                   n.notification_type, n.sent_at
            FROM event_notifications n
            JOIN events e ON n.event_id = e.id
            ORDER BY n.id DESC 
            LIMIT {limit} OFFSET {offset}
            """
            columns = ["id", "event_id", "unique_event_name", "event_name", "notification_type", "sent_at"]
            count_query = "SELECT COUNT(*) FROM event_notifications"
            
        elif table_name == "event_winners":
            query = f"""
            SELECT w.id, w.event_id, e.unique_event_name, e.name as event_name,
                   w.player_name, w.final_score, w.was_online, w.rewarded_at
            FROM event_winners w
            JOIN events e ON w.event_id = e.id
            ORDER BY w.id DESC 
            LIMIT {limit} OFFSET {offset}
            """
            columns = ["id", "event_id", "unique_event_name", "event_name", "player_name", "final_score", "was_online", "rewarded_at"]
            count_query = "SELECT COUNT(*) FROM event_winners"
            
        elif table_name == "event_tasks":
            query = f"""
            SELECT t.id, t.event_id, e.unique_event_name, e.name as event_name,
                   t.task_name, t.scheduled_time, t.priority, t.completed,
                   t.execution_length_ms, t.completed_time
            FROM event_tasks t
            JOIN events e ON t.event_id = e.id
            ORDER BY t.scheduled_time ASC 
            LIMIT {limit} OFFSET {offset}
            """
            columns = ["id", "event_id", "unique_event_name", "event_name", "task_name", 
                      "scheduled_time", "priority", "completed", "execution_length_ms", "completed_time"]
            count_query = "SELECT COUNT(*) FROM event_tasks"
        
        count_result = db.db_query(count_query)
        total = count_result[0][0] if count_result else 0
        
        results = db.db_query(query)
        
        rows = []
        for row in results:
            row_dict = {}
            for i, col_name in enumerate(columns):
                row_dict[col_name] = row[i]
            rows.append(row_dict)
        
        return jsonify({
            "table": table_name,
            "columns": columns,
            "rows": rows,
            "total": total,
            "limit": limit,
            "offset": offset
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/database/admin-unlock", methods=["POST"])
@login_required
def api_admin_unlock():
    try:
        password = request.json.get("password")
        master_password = os.getenv("DATABASE_MASTER")
        
        if not master_password:
            return jsonify({"success": False, "error": "DATABASE_MASTER not configured"})
        
        if password == master_password:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Invalid password"})
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/database/admin-clear-logs", methods=["POST"])
@login_required
def api_admin_clear_logs():
    try:
        db = get_db()
        
        count_query = "SELECT COUNT(*) FROM logs"
        count_result = db.db_query(count_query)
        deleted_count = count_result[0][0] if count_result else 0
        
        delete_query = "DELETE FROM logs"
        db.db_query_with_params(delete_query, ())
        
        sql_calendar.log_message(f"Admin cleared {deleted_count} log entries via web interface", "ADMIN")
        
        return jsonify({
            "success": True,
            "deleted_count": deleted_count
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/database/admin-events-list")
@login_required
def api_admin_events_list():
    try:
        db = get_db()
        
        query = """
        SELECT id, unique_event_name, name, start_time, end_time, event_over
        FROM events 
        ORDER BY start_time DESC
        """
        
        results = db.db_query(query)
        
        events = []
        for row in results:
            events.append({
                "id": row[0],
                "unique_event_name": row[1],
                "name": row[2],
                "start_time": row[3],
                "end_time": row[4],
                "event_over": bool(row[5])
            })
        
        return jsonify({"events": events})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/winners")
@login_required
def api_winners():
    try:
        db = get_db()
        query = """
        SELECT w.id, w.event_id, e.unique_event_name, e.name as event_name,
               w.player_name, w.final_score, w.was_online, w.rewarded_at, e.event_json
        FROM event_winners w
        JOIN events e ON w.event_id = e.id
        ORDER BY w.rewarded_at DESC
        """
        results = db.db_query(query)
        
        winners = []
        for row in results:
            # Parse event JSON to get reward command
            reward_cmd = None
            event_json_filename = row[8]  # e.event_json
            if event_json_filename:
                try:
                    events_json_path = os.path.join(".", "events", "events_json")
                    json_path = os.path.join(events_json_path, event_json_filename)
                    if os.path.exists(json_path):
                        with open(json_path, 'r') as f:
                            event_data = json.load(f)
                            reward_cmd = event_data.get('reward_cmd')
                except Exception as e:
                    sql_calendar.log_message(f"Error loading event JSON {event_json_filename}: {e}", "WARN")
            
            winners.append({
                "id": row[0],
                "event_id": row[1],
                "unique_event_name": row[2],
                "event_name": row[3],
                "player_name": row[4],
                "final_score": row[5],
                "was_online": bool(row[6]),
                "rewarded_at": row[7],
                "reward_cmd": reward_cmd
            })
        
        return jsonify(winners)
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/api/database/admin-json-files")
@login_required
def api_admin_json_files():
    try:
        if not os.path.exists(EVENTS_JSON_PATH):
            return jsonify({"files": []})
        
        files = []
        for filename in os.listdir(EVENTS_JSON_PATH):
            if filename.endswith('.json'):
                filepath = os.path.join(EVENTS_JSON_PATH, filename)
                stat = os.stat(filepath)
                
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    event_name = data.get('name', 'Unknown')
                    description = data.get('description', 'No description')
                except:
                    event_name = filename.replace('.json', '')
                    description = 'Could not read file'
                
                files.append({
                    "filename": filename,
                    "event_name": event_name,
                    "description": description,
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
        
        files.sort(key=lambda x: x['filename'])
        
        return jsonify({"files": files})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/options")
@login_required
def options():
    return render_template("options.html")

@app.route("/api/settings/get")
@login_required
def api_get_settings():
    try:
        # Get scoreboard interval from database
        db = get_db()
        # NOTE: This query looks for the interval in the 'events' table, 
        # which might not be the most reliable source if no events exist.
        # It should probably check a dedicated 'settings' table or fallback to a constant.
        query = "SELECT scoreboard_interval FROM events ORDER BY id DESC LIMIT 1"
        result = db.db_query(query)
        default_interval = result[0][0] if result else 600
        
        settings = {
            "rcon_host": os.getenv("RCON_HOST", ""),
            "rcon_port": os.getenv("RCON_PORT", "25575"),
            "discord_token": os.getenv("DISCORD_TOKEN", ""),
            "event_channel_id": os.getenv("EVENT_CHANNEL_ID", ""),
            # FIX: Ensure we are using SCOREBOARD_INTERVAL here
            "scoreboard_interval": os.getenv("SCOREBOARD_INTERVAL", str(default_interval))
        }
        return jsonify(settings)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/settings/update", methods=["POST"])
@login_required
def api_update_settings():
    try:
        data = request.json
        
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        
        if not os.path.exists(env_path):
            return jsonify({"success": False, "error": ".env file not found"}), 404
        
        with open(env_path, 'r') as f:
            lines = f.readlines()
        
        updated_lines = []
        settings_to_update = {
            'RCON_HOST': data.get('rcon_host'),
            'RCON_PORT': data.get('rcon_port'),
            'DISCORD_TOKEN': data.get('discord_token'),
            'EVENT_CHANNEL_ID': data.get('event_channel_id'),
            # FIX: Change the environment variable name from SCOREBOARD_INTERVAL_SECONDS to SCOREBOARD_INTERVAL
            'SCOREBOARD_INTERVAL': data.get('scoreboard_interval') 
        }
        
        found_settings = set()
        
        for line in lines:
            updated = False
            for key, value in settings_to_update.items():
                if value is not None and line.startswith(f"{key}="):
                    updated_lines.append(f"{key}={value}\n")
                    found_settings.add(key)
                    updated = True
                    break
            
            if not updated:
                updated_lines.append(line)
        
        for key, value in settings_to_update.items():
            if key not in found_settings and value is not None:
                updated_lines.append(f"{key}={value}\n")
        
        with open(env_path, 'w') as f:
            f.writelines(updated_lines)
        
        load_dotenv(override=True)
        
        sql_calendar.log_message("Settings updated via web interface", "ADMIN")
        
        return jsonify({
            "success": True,
            "message": "Settings updated successfully. Changes will take effect on next restart."
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/settings/test-connection", methods=["POST"])
@login_required
def api_test_connection():
    try:
        data = request.json
        host = data.get('rcon_host')
        port = int(data.get('rcon_port', 25575))
        password = os.getenv('RCON_PASS')
        
        if not host:
            return jsonify({"success": False, "error": "Host is required"})
        
        with MCRcon(host, password, port=port, timeout=5) as mcr:
            result = mcr.command("list")
        
        return jsonify({
            "success": True,
            "message": "Connection successful!",
            "result": result
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Connection failed: {str(e)}"
        })
    
@app.route("/api/database/admin-delete-json", methods=["POST"])
@login_required
def api_admin_delete_json():
    try:
        filename = request.json.get("filename")
        if not filename:
            return jsonify({"success": False, "error": "No filename provided"})
        
        if not filename.endswith('.json') or '/' in filename or '\\' in filename:
            return jsonify({"success": False, "error": "Invalid filename"})
        
        filepath = os.path.join(EVENTS_JSON_PATH, filename)
        
        if not os.path.exists(filepath):
            return jsonify({"success": False, "error": "File not found"})
        
        os.remove(filepath)
        
        sql_calendar.log_message(f"Admin deleted event JSON file: {filename}", "ADMIN")
        
        return jsonify({
            "success": True,
            "message": f"Event JSON file '{filename}' deleted successfully"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/database/admin-delete-event", methods=["POST"])
@login_required
def api_admin_delete_event():
    try:
        event_id = request.json.get("event_id")
        if not event_id:
            return jsonify({"success": False, "error": "No event ID provided"})
        
        db = get_db()
        
        event_query = "SELECT unique_event_name, name FROM events WHERE id = ?"
        event_result = db.db_query_with_params(event_query, (event_id,))
        
        if not event_result:
            return jsonify({"success": False, "error": "Event not found"})
        
        unique_name, event_name = event_result[0]
        
        db.db_query_with_params("DELETE FROM event_winners WHERE event_id = ?", (event_id,))
        db.db_query_with_params("DELETE FROM event_notifications WHERE event_id = ?", (event_id,))
        db.db_query_with_params("DELETE FROM event_tasks WHERE event_id = ?", (event_id,))
        db.db_query_with_params("DELETE FROM events WHERE id = ?", (event_id,))
        
        sql_calendar.log_message(f"Admin deleted event '{event_name}' ({unique_name}) and all related data via web interface", "ADMIN")
        
        return jsonify({
            "success": True,
            "message": f"Event '{event_name}' and all related data deleted successfully"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/database/query", methods=["POST"])
@login_required
def api_database_query():
    try:
        query = request.json.get("query", "").strip()
        
        if not query.upper().startswith("SELECT"):
            return jsonify({"error": "Only SELECT queries are allowed"}), 400
        
        db = get_db()
        results = db.db_query(query)
        
        return jsonify({
            "results": results,
            "count": len(results) if results else 0
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/create_event", methods=["GET", "POST"])
@login_required
def create_event():
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        event_json = request.form.get("event_json")
        timezone_str = request.form.get("timezone")

        start_str = request.form.get("start")
        end_str = request.form.get("end")

        if not timezone_str or timezone_str not in pytz.all_timezones:
            flash("Invalid timezone selected")
            return redirect(url_for("create_event"))

        tz = pytz.timezone(timezone_str)

        try:
            start_local = datetime.strptime(start_str, "%Y-%m-%d %I:%M %p")
            end_local = datetime.strptime(end_str, "%Y-%m-%d %I:%M %p")
        except ValueError:
            flash("Invalid date/time format. Use YYYY-MM-DD HH:MM AM/PM")
            return redirect(url_for("create_event"))

        start_dt = tz.localize(start_local).astimezone(pytz.UTC)
        end_dt = tz.localize(end_local).astimezone(pytz.UTC)

        start_utc = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_utc = end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        unique_event_name = f"{name.replace(' ','-')}-{start_dt.strftime('%m-%d-%Y-%H%M')}"

        # Get scoreboard interval from settings or use default
        scoreboard_interval = int(os.getenv("SCOREBOARD_INTERVAL", "600"))

        try:
            event_id = schedule_events.create_event_with_tasks(
                unique_event_name, name, event_json, description, start_utc, end_utc, scoreboard_interval
            )
            
            if event_id:
                sql_calendar.log_message_with_timestamp(f"Event created via web interface: {name}")
                flash(f"Event '{name}' created successfully with scheduled tasks!")
            else:
                flash("Error creating event with tasks")
            
            return redirect(url_for("index"))
            
        except Exception as e:
            flash(f"Error creating event: {e}")
            return redirect(url_for("create_event"))

    event_files = load_event_files()
    return render_template("create_event.html", event_files=event_files)

@app.route("/create_json_event", methods=["GET", "POST"])
@login_required
def create_json_event():
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        is_aggregate = request.form.get("is_aggregate") == "true"
        score_text = request.form.get("score_text")
        aggregate_objective = request.form.get("aggregate_objective")

        sidebar = {
            "displayName": request.form.get("sidebar_display"),
            "color": request.form.get("sidebar_color"),
            "bold": request.form.get("sidebar_bold") == "true",
            "duration": int(request.form.get("sidebar_duration") or 15),
        }

        reward_cmd = request.form.get("reward_cmd")
        reward_name = request.form.get("reward_name")

        setup_commands = []
        aggregate_list = []

        if is_aggregate:
            obj_names = request.form.getlist("setup_obj_name[]")
            actions = request.form.getlist("setup_action[]")
            items = request.form.getlist("setup_item[]")

            for obj_name, action, item in zip(obj_names, actions, items):
                if action == "custom":
                    cmd = f"scoreboard objectives add {obj_name} {item}"
                else:
                    cmd = f"scoreboard objectives add {obj_name} minecraft.{action}:minecraft.{item}"
                setup_commands.append(cmd)
                aggregate_list.append(obj_name)

            setup_commands.append(f"scoreboard objectives add {aggregate_objective} dummy \"{aggregate_objective}\"")
        else:
            obj_names = request.form.getlist("setup_obj_name[]")
            actions = request.form.getlist("setup_action[]")
            items = request.form.getlist("setup_item[]")

            if obj_names and actions and items:
                obj_name = obj_names[0]
                action = actions[0]
                item = items[0]
                if action == "custom":
                    cmd = f"scoreboard objectives add {obj_name} {item}"
                else:
                    cmd = f"scoreboard objectives add {obj_name} minecraft.{action}:minecraft.{item}"
                setup_commands.append(cmd)

        cleanup_commands = []
        if is_aggregate:
            cleanup_commands.extend(aggregate_list)
            cleanup_commands.append(aggregate_objective)
        else:
            cleanup_commands.append(aggregate_objective)

        event_json = {
            "unique_event_name": f"{name.replace(' ', '_')}",
            "name": name,
            "description": description,
            "is_aggregate": is_aggregate,
            "score_text": score_text,
            "aggregate_objective": aggregate_objective,
            "commands": {
                "setup": setup_commands,
                "aggregate": aggregate_list if is_aggregate else [],
                "cleanup": cleanup_commands,
            },
            "sidebar": sidebar,
            "reward_cmd": reward_cmd,
            "reward_name": reward_name,
        }

        os.makedirs(EVENTS_JSON_PATH, exist_ok=True)

        filename = "".join(word.capitalize() for word in name.split()) + ".json"
        filepath = os.path.join(EVENTS_JSON_PATH, filename)

        with open(filepath, "w") as f:
            json.dump(event_json, f, indent=2)

        flash(f"Event JSON '{name}' saved to {filepath}")
        return redirect(url_for("index"))

    return render_template("create_json_event.html")

@app.route("/api/event_handler/start", methods=["POST"])
@login_required
def api_start_event_handler():
    success = start_event_handler()
    return jsonify({"success": success, "status": "Running" if is_event_handler_running() else "Not Running"})

@app.route("/api/event_handler_status")
@login_required
def api_event_handler_status():
    running = is_event_handler_running()
    return jsonify({"status": "Running" if running else "Not Running"})

@app.route("/api/event_handler/stop", methods=["POST"])
@login_required
def api_stop_event_handler():
    success = stop_event_handler()
    return jsonify({"success": success, "status": "Running" if is_event_handler_running() else "Not Running"})

@app.route("/api/event_files")
@login_required
def api_event_files():
    files = load_event_files()
    return jsonify(files)

@app.route("/api/logs")
@login_required
def api_logs():
    logs = load_logs_from_db()
    return jsonify(logs)

@app.route("/api/event_json_content/<filename>")
@login_required
def api_event_json_content(filename):
    path = os.path.join(EVENTS_JSON_PATH, filename)
    if os.path.exists(path):
        with open(path, "r") as f:
            data = json.load(f)
            return json.dumps(data, indent=2)
    return "", 404

@app.route("/api/log_content/<filename>")
@login_required
def api_log_content(filename):
    if filename == "handler_logs.txt":
        logs = load_logs_from_db()
        log_text = "\n".join([f"{log['timestamp']}: [{log['log_level']}] {log['message']}" for log in logs])
        return log_text
    
    path = os.path.join(LOGS_PATH, filename)
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    return "", 404

if __name__ == "__main__":
    try:
        db = get_db()
        
        if not os.path.exists(DATABASE_PATH):
            print("Database file doesn't exist, creating new database...")
            db.initialize_db()
            print("Database initialized successfully")
        else:
            info = db.db_info()
            if not info or not info.get('tables'):
                print("Database exists but has no tables, initializing...")
                db.initialize_db()
                print("Database initialized successfully")
            else:
                print(f"Database already exists with {len(info['tables'])} tables")
                
    except Exception as e:
        print(f"Error with database: {e}")
    
    app.run(host="0.0.0.0", port=8080, debug=True)