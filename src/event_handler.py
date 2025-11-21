#!/usr/bin/python3.12
import json
import os
import subprocess
import time
import sql_calendar
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

load_dotenv()
RESULTS_PATH = os.getenv("LOGS_PATH")

BOT_PY_PATH = "./src/bot.py"
RCON_FRAMEWORK_PATH = "./src/rcon_event_framework.py"

TASK_CAPTURE_WINDOW = 30
MIN_SLEEP_INTERVAL = 1
MAX_SLEEP_INTERVAL = 120
SLEEP_THRESHOLD = 240

def send_discord_notification(action, unique_name, winners=None, score=None):
    cmd = ["python3", BOT_PY_PATH, action, unique_name]
    if action == "over":
        if winners is None:
            winners = ['no_Participants']
        if score is None:
            score = 0
        cmd.append(",".join(winners))
        cmd.append(str(score))
    
    sql_calendar.log_message(f"Sending Discord notification: {' '.join(cmd)}")
    subprocess.run(cmd)

def call_rcon_framework(action, json_file, unique_name=None):
    cmd = ["python3", RCON_FRAMEWORK_PATH, action, json_file]
    if unique_name:
        cmd.append(unique_name)
    sql_calendar.log_message(f"Calling RCON framework: {' '.join(cmd)}")
    subprocess.run(cmd)

def get_event_results(unique_event_name):
    winners = []
    score = None
    
    try:
        event_id = sql_calendar.get_event_id_by_unique_name(unique_event_name)
        if not event_id:
            sql_calendar.log_message(f"Could not find event ID for: {unique_event_name}", "ERROR")
            return ['no_Participants'], 0
        
        winners_data = sql_calendar.get_event_winners(event_id)
        
        if winners_data:
            winners = [winner[2] for winner in winners_data]
            score = winners_data[0][3] if winners_data[0][3] is not None else 0
            sql_calendar.log_message(f"Found winners in database: {winners} with score {score}")
        else:
            sql_calendar.log_message("No winners found in database")
            winners = ['no_Participants']
            score = 0
            
    except Exception as e:
        sql_calendar.log_message(f"Error getting event results from database: {e}", "ERROR")
        winners = ['no_Participants']
        score = 0
    
    return winners, score

def execute_task(task):
    t_start = time.time()
    task_name = task['task_name']
    event_id = task['event_id']
    unique_name = task['unique_event_name']
    event_json = task['event_json']
    
    sql_calendar.log_message(f"Executing task: {task_name} for event {event_id} ({unique_name})")
    
    try:
        if task_name == 'discord_twenty_four_hr_notif':
            send_discord_notification("twenty_four", unique_name)
            sql_calendar.send_24h_notification(event_id)
            
        elif task_name == 'discord_thirty_m_notif':
            send_discord_notification("thirty", unique_name)
            sql_calendar.send_30min_notification(event_id)
            
        elif task_name == 'discord_now_notif':
            send_discord_notification("now", unique_name)
            sql_calendar.send_start_notification(event_id)
            
        elif task_name == 'discord_results_notify':
            winners, score = get_event_results(unique_name)
            send_discord_notification("over", unique_name, winners=winners, score=score)
            sql_calendar.send_end_notification(event_id)
            
        elif task_name == 'server_start_event':
            call_rcon_framework("start", event_json)
            sql_calendar.start_event_by_id(event_id)
            
        elif task_name == 'server_end_event':
            call_rcon_framework("clean", event_json, unique_name)
            time.sleep(3)
            sql_calendar.end_event_by_id(event_id)
            
        elif task_name == 'server_display_scoreboard':
            call_rcon_framework("display", event_json, unique_name)
            sql_calendar.update_scoreboard_display_time(event_id)
            
        else:
            sql_calendar.log_message(f"Unknown task name: {task_name}", "ERROR")
            
    except Exception as e:
        sql_calendar.log_message(f"Error executing task {task_name}: {e}", "ERROR")
    
    t_end = time.time()
    execution_length_ms = int((t_end - t_start) * 1000)
    sql_calendar.mark_task_completed(task['id'], execution_length_ms)
    sql_calendar.log_message(f"Task {task_name} completed in {execution_length_ms}ms")

def task_execution_loop():
    sql_calendar.log_message("Task execution loop starting")
    
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            
            tasks = sql_calendar.get_tasks_to_execute(current_time, TASK_CAPTURE_WINDOW)
            
            for task in tasks:
                if task['scheduled_time'] <= current_time:
                    execute_task(task)
            
            next_task_time = sql_calendar.get_next_pending_task_time()
            
            if next_task_time:
                time_until_next = (next_task_time - datetime.now(timezone.utc)).total_seconds()
                
                if time_until_next <= SLEEP_THRESHOLD:
                    sleep_duration = MIN_SLEEP_INTERVAL
                else:
                    sleep_duration = min(MAX_SLEEP_INTERVAL, max(MIN_SLEEP_INTERVAL, time_until_next / 2))
                
                sql_calendar.log_message(f"Next task in {time_until_next:.0f}s, sleeping for {sleep_duration}s")
            else:
                sleep_duration = MAX_SLEEP_INTERVAL
                sql_calendar.log_message(f"No pending tasks, sleeping for {sleep_duration}s")
            
            time.sleep(sleep_duration)
            
        except Exception as e:
            error_msg = f"Error in task execution loop: {e}"
            sql_calendar.log_message(error_msg, "ERROR")
            time.sleep(MIN_SLEEP_INTERVAL)

def main():
    sql_calendar.log_message("Event handler (task-based) starting up")
    task_execution_loop()

if __name__ == "__main__":
    main()