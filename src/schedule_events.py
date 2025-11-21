# /path/to/schedule_events.py

#!/usr/bin/python3.12
import json
import os
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
import sql_calendar

load_dotenv()
EVENTS_JSON_PATH = os.getenv("EVENTS_JSON_PATH")

# --- NEW IMPLEMENTATION ---
# Load the scoreboard interval from .env, defaulting to 600 if not set.
try:
    DEFAULT_SCOREBOARD_INTERVAL = int(os.getenv("SCOREBOARD_INTERVAL_SECONDS", 600))
except ValueError:
    # Handle case where environment variable is not a valid integer
    DEFAULT_SCOREBOARD_INTERVAL = 600
    sql_calendar.log_message("SCOREBOARD_INTERVAL_SECONDS in .env is not an integer. Using default of 600.", "WARN")
# --------------------------

def schedule_tasks_for_event(event_id, start_time, end_time, scoreboard_interval=DEFAULT_SCOREBOARD_INTERVAL):
    tasks_scheduled = []
    # Ensure 'now' is a timezone-aware UTC datetime for comparison
    now = datetime.now(pytz.UTC)
    
    # -------------------------------------------------------------------
    # DISCORD NOTIFICATION TASKS - Using consistent naming
    # -------------------------------------------------------------------

    # 24-Hour Notification - Priority 2
    notify_24h_time = start_time - timedelta(hours=24)
    if notify_24h_time > now:
        sql_calendar.insert_task(event_id, 'discord_twentyfour_notify', notify_24h_time, 2)
        tasks_scheduled.append('discord_twentyfour_notify')

    # 30-Minute Notification - Priority 2
    notify_30min_time = start_time - timedelta(minutes=30)
    if notify_30min_time > now:
        sql_calendar.insert_task(event_id, 'discord_thirty_notify', notify_30min_time, 2)
        tasks_scheduled.append('discord_thirty_notify')

    # Start Notification - Priority 4 (before server starts at priority 5)
    if start_time > now:
        sql_calendar.insert_task(event_id, 'discord_now_notify', start_time, 4)
        tasks_scheduled.append('discord_now_notify')

    # Server start event (exactly at start_time) - Priority 5
    if start_time > now:
        sql_calendar.insert_task(event_id, 'server_start_event', start_time, 5)
        tasks_scheduled.append('server_start_event')
    
    # Server end event (exactly at end_time) - Priority 5
    sql_calendar.insert_task(event_id, 'server_end_event', end_time, 5)
    tasks_scheduled.append('server_end_event')
    
    # -------------------------------------------------------------------
    # Scoreboard Display Tasks - Using consistent naming
    # -------------------------------------------------------------------
    
    # The first display task should happen at start_time + scoreboard_interval
    next_display_time = start_time + timedelta(seconds=scoreboard_interval)
    
    # Loop while the next scheduled time is before the event ends
    while next_display_time < end_time:
        
        # Only schedule tasks that have NOT passed yet.
        if next_display_time > now:
            # FIXED: Using consistent task name
            sql_calendar.insert_task(event_id, 'server_display_scoreboard', next_display_time, 4)
            tasks_scheduled.append('server_display_scoreboard')

        # Increment the time by the interval
        next_display_time += timedelta(seconds=scoreboard_interval)

    # -------------------------------------------------------------------
    
    # Results Notification - Priority 3
    notify_results = end_time + timedelta(minutes=5)
    sql_calendar.insert_task(event_id, 'discord_over_notify', notify_results, 3)
    tasks_scheduled.append('discord_over_notify')
    
    sql_calendar.log_message(f"Scheduled {len(tasks_scheduled)} tasks for event {event_id}")
    return tasks_scheduled


def create_event_with_tasks(unique_name, name, event_json, description, start_time_str, end_time_str, scoreboard_interval=DEFAULT_SCOREBOARD_INTERVAL):
    try:
        # Parse datetime strings
        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
        
        # Insert event
        # This will use the value passed by the caller, or the DEFAULT_SCOREBOARD_INTERVAL if the caller doesn't provide it.
        sql_calendar.insert_event(unique_name, name, event_json, description, start_time_str, end_time_str, scoreboard_interval)
        
        # Get the event ID
        event_id = sql_calendar.get_last_event_id()
        
        if event_id:
            # Schedule tasks for the event
            tasks = schedule_tasks_for_event(event_id, start_time, end_time, scoreboard_interval)
            sql_calendar.log_message(f"Created event '{name}' with {len(tasks)} scheduled tasks")
            return event_id
        else:
            sql_calendar.log_message(f"Failed to get event ID for '{name}'", "ERROR")
            return None
            
    except Exception as e:
        sql_calendar.log_message(f"Error creating event with tasks: {e}", "ERROR")
        return None
