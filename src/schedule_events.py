#!/usr/bin/python3.12
import json
import os
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
import sql_calendar

load_dotenv()
EVENTS_JSON_PATH = os.getenv("EVENTS_JSON_PATH")

def schedule_tasks_for_event(event_id, start_time, end_time, scoreboard_interval=600):
    tasks_scheduled = []
    now = datetime.now(pytz.UTC)
    
    # Discord 24-hour notification
    notify_24h = start_time - timedelta(hours=24)
    if notify_24h > now:
        sql_calendar.insert_task(event_id, 'discord_twenty_four_hr_notif', notify_24h, 1)
        tasks_scheduled.append('discord_twenty_four_hr_notif')
    
    # Discord 30-minute notification
    notify_30m = start_time - timedelta(minutes=30)
    if notify_30m > now:
        sql_calendar.insert_task(event_id, 'discord_thirty_m_notif', notify_30m, 2)
        tasks_scheduled.append('discord_thirty_m_notif')
    
    # Server start event (exactly at start_time)
    sql_calendar.insert_task(event_id, 'server_start_event', start_time, 5)
    tasks_scheduled.append('server_start_event')
    
    # Discord now notification (at start_time)
    sql_calendar.insert_task(event_id, 'discord_now_notif', start_time, 4)
    tasks_scheduled.append('discord_now_notif')
    
    # Scoreboard displays (if interval > 0)
    if scoreboard_interval > 0:
        scoreboard_time = start_time + timedelta(seconds=60)
        end_minus_one = end_time - timedelta(seconds=60)
        
        while scoreboard_time < end_minus_one:
            sql_calendar.insert_task(event_id, 'server_display_scoreboard', scoreboard_time, 3)
            tasks_scheduled.append('server_display_scoreboard')
            scoreboard_time += timedelta(seconds=scoreboard_interval)
    
    # Server end event (exactly at end_time)
    sql_calendar.insert_task(event_id, 'server_end_event', end_time, 5)
    tasks_scheduled.append('server_end_event')
    
    # Discord results notification (5 minutes after end)
    notify_results = end_time + timedelta(minutes=5)
    sql_calendar.insert_task(event_id, 'discord_results_notify', notify_results, 3)
    tasks_scheduled.append('discord_results_notify')
    
    sql_calendar.log_message(f"Scheduled {len(tasks_scheduled)} tasks for event {event_id}")
    return tasks_scheduled

def create_event_with_tasks(unique_name, name, event_json, description, start_time_str, end_time_str, scoreboard_interval=600):
    try:
        # Parse datetime strings
        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
        
        # Insert event
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