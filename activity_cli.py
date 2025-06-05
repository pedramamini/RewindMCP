#!/usr/bin/env python3
"""
activity_cli.py - command line tool to display activity tracking data from rewinddb.

this script provides information about computer usage activity, application usage,
and calendar meetings from the rewind.ai database.

call flow:
1. parse command line arguments using argparse
2. connect to rewinddb database
3. determine time range based on arguments:
   - if --relative is provided, calculate relative time range from now
   - if --from and --to are provided, use specific time range
4. query activity data for the specified time range
5. format and display results:
   - active hours - when the computer was being used
   - apps - list of applications used with time spent
   - meetings - calendar events during the specified time period
6. close database connection

the cli supports two main query modes:
- relative time queries (e.g., "1 hour", "5h", "30m", "2d", "1w")
- specific time range queries with --from and --to timestamps

examples:
  python activity_cli.py --relative "1 day"
  python activity_cli.py --relative "5h"
  python activity_cli.py --relative "3m"
  python activity_cli.py --relative "10d"
  python activity_cli.py --relative "2w"
  python activity_cli.py --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"
  python activity_cli.py --from "2023-05-11" --to "2023-05-12"  # uses 00:00:00 and 23:59:59
  python activity_cli.py --from "13:00:00" --to "17:00:00"  # uses today's date
  python activity_cli.py --relative "7 days" --debug
  python activity_cli.py --relative "1 hour" --env-file /path/to/.env
"""

import argparse
import datetime
import logging
import re
import sys
import time
from datetime import timezone

import rewinddb
from tabulate import tabulate


# configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def parse_relative_time(time_str):
    """parse a relative time string into timedelta components.

    args:
        time_str: string like "1 hour", "5 hours", "30 minutes" or short form "5h", "3m", "10d", "2w"

    returns:
        dict with keys for days, hours, minutes, seconds

    raises:
        ValueError: if the time string format is invalid
    """

    time_str = time_str.lower().strip()
    time_components = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}

    # short form pattern (e.g., "5h", "3m", "10d", "2w")
    short_patterns = {
        r"^(\d+)w$": lambda x: {"days": int(x) * 7},
        r"^(\d+)d$": lambda x: {"days": int(x)},
        r"^(\d+)h$": lambda x: {"hours": int(x)},
        r"^(\d+)m$": lambda x: {"minutes": int(x)},
        r"^(\d+)s$": lambda x: {"seconds": int(x)}
    }

    # check for short form patterns first
    for pattern, handler in short_patterns.items():
        match = re.search(pattern, time_str)
        if match:
            component_values = handler(match.group(1))
            for component, value in component_values.items():
                time_components[component] = value
            return time_components

    # long form patterns
    patterns = {
        r"(\d+)\s*(?:day|days)": "days",
        r"(\d+)\s*(?:hour|hours|hr|hrs)": "hours",
        r"(\d+)\s*(?:minute|minutes|min|mins)": "minutes",
        r"(\d+)\s*(?:second|seconds|sec|secs)": "seconds",
        r"(\d+)\s*(?:week|weeks)": "weeks"
    }

    # try to match each pattern
    found_match = False
    for pattern, component in patterns.items():
        match = re.search(pattern, time_str)
        if match:
            if component == "weeks":
                time_components["days"] += int(match.group(1)) * 7
            else:
                time_components[component] = int(match.group(1))
            found_match = True

    if not found_match:
        raise ValueError(f"invalid time format: {time_str}. use format like '1 hour', '5h', '30m', '2d', '1w'.")

    return time_components


def get_activity_relative(db, time_str, debug=False):
    """get activity data from a relative time period.

    args:
        db: rewinddb instance
        time_str: relative time string (e.g., "1 hour", "5 hours")
        debug: whether to print debug information

    returns:
        dictionary with active hours, app usage, and meetings data
    """

    try:
        time_components = parse_relative_time(time_str)

        if debug:
            logger.info(f"getting activity data for the past {time_str}")
            logger.info(f"time components: {time_components}")

        # get active hours data
        active_hours = db.get_active_hours(**time_components)

        # get app usage data
        app_usage = db.get_app_usage(**time_components)

        # get meetings data
        try:
            meetings = db.get_meetings(**time_components)
        except Exception as e:
            if debug:
                logger.error(f"error retrieving meetings data: {e}")
            meetings = None

        return {
            'active_hours': active_hours,
            'app_usage': app_usage,
            'meetings': meetings
        }
    except ValueError as e:
        logger.error(f"error: {e}")
        sys.exit(1)


def get_activity_absolute(db, from_time_str, to_time_str, debug=False):
    """get activity data from a specific time range.

    args:
        db: rewinddb instance
        from_time_str: start time string in format "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD", or "HH:MM:SS"
        to_time_str: end time string in format "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD", or "HH:MM:SS"
        debug: whether to print debug information

    returns:
        dictionary with active hours, app usage, and meetings data
    """

    try:
        # get local timezone for proper conversion
        local_tz = datetime.datetime.now().astimezone().tzinfo

        # check if from_time_str is time-only format (HH:MM:SS)
        if len(from_time_str) <= 8 and from_time_str.count(':') == 2:
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            from_time_str = f"{today} {from_time_str}"
        # check if from_time_str is date-only format (YYYY-MM-DD)
        elif len(from_time_str) == 10 and from_time_str.count('-') == 2:
            from_time_str = f"{from_time_str} 00:00:00"

        # check if to_time_str is time-only format (HH:MM:SS)
        if len(to_time_str) <= 8 and to_time_str.count(':') == 2:
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            to_time_str = f"{today} {to_time_str}"
        # check if to_time_str is date-only format (YYYY-MM-DD)
        elif len(to_time_str) == 10 and to_time_str.count('-') == 2:
            to_time_str = f"{to_time_str} 23:59:59"

        # parse as naive datetime first
        from_time_naive = datetime.datetime.strptime(from_time_str, "%Y-%m-%d %H:%M:%S")
        to_time_naive = datetime.datetime.strptime(to_time_str, "%Y-%m-%d %H:%M:%S")

        # add local timezone info and convert to UTC for database query
        from_time = from_time_naive.replace(tzinfo=local_tz).astimezone(timezone.utc)
        to_time = to_time_naive.replace(tzinfo=local_tz).astimezone(timezone.utc)

        if debug:
            logger.info(f"getting activity data from {from_time} to {to_time}")

        # get active hours data
        active_hours = db.get_active_hours(start_time=from_time, end_time=to_time)

        # get app usage data
        app_usage = db.get_app_usage(start_time=from_time, end_time=to_time)

        # get meetings data
        try:
            meetings = db.get_meetings(start_time=from_time, end_time=to_time)
        except Exception as e:
            if debug:
                logger.error(f"error retrieving meetings data: {e}")
            meetings = None

        return {
            'active_hours': active_hours,
            'app_usage': app_usage,
            'meetings': meetings
        }
    except ValueError as e:
        logger.error(f"error: invalid time format. use format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD', or 'HH:MM:SS'.")
        sys.exit(1)


def convert_to_local_time(dt):
    """convert a utc datetime to local time.

    args:
        dt: datetime object in utc

    returns:
        datetime object in local time
    """

    if dt is None:
        return None

    # if datetime has no timezone info, assume it's utc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    # convert to local time
    return dt.astimezone()


def display_active_hours(active_hours, use_utc=False):
    """display active hours data in a formatted way.

    args:
        active_hours: dictionary with active hours data from get_active_hours()
        use_utc: whether to display times in utc (default: false, use local time)
    """

    print("\n" + "=" * 80)
    print(" ACTIVE HOURS ")
    print("=" * 80)

    print(f"\nTotal Active Time: {active_hours['total_active_hours']} hours")
    print(f"Number of Active Sessions: {active_hours['session_count']}")
    print(f"Average Session Length: {active_hours['avg_session_minutes']} minutes")

    # display hourly activity
    print("\nHourly Activity:")
    hourly_data = []
    for hour_data in active_hours['hourly_activity']:
        hour = hour_data['hour']
        hours_active = hour_data['hours']
        # create a simple bar chart
        bar = "█" * int(hours_active * 4) if hours_active > 0 else ""
        hour_str = f"{hour:02d}:00"
        hourly_data.append([hour_str, f"{hours_active:.2f}", bar])

    print(tabulate(hourly_data, headers=["Hour", "Hours Active", "Activity"], tablefmt="simple"))

    # display daily activity if available
    if active_hours['daily_activity']:
        print("\nDaily Activity:")
        daily_data = []
        for day_data in active_hours['daily_activity']:
            date_str = day_data['date']
            hours_active = day_data['hours']

            # convert date string to local time if needed
            if not use_utc and '-' in date_str:
                try:
                    # parse the date string
                    date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    # convert to local time
                    local_date = convert_to_local_time(date_obj)
                    # format as date string
                    date_str = local_date.strftime("%Y-%m-%d")
                except ValueError:
                    # if parsing fails, keep original string
                    pass

            # create a simple bar chart
            bar = "█" * int(hours_active) if hours_active > 0 else ""
            daily_data.append([date_str, f"{hours_active:.2f}", bar])

        print(tabulate(daily_data, headers=["Date", "Hours Active", "Activity"], tablefmt="simple"))


def display_app_usage(app_usage):
    """display application usage data in a formatted way.

    args:
        app_usage: dictionary with app usage data from get_app_usage()
    """

    print("\n" + "=" * 80)
    print(" APPLICATION USAGE ")
    print("=" * 80)

    # filter out rewind's own app
    filtered_apps = [app for app in app_usage['top_apps'] if app['name'] != "ai.rewind.audiorecorder"]

    # recalculate total hours for filtered apps
    filtered_total_hours = sum(app['hours'] for app in filtered_apps)

    # recalculate percentages based on filtered total
    if filtered_total_hours > 0:
        for app in filtered_apps:
            app['percentage'] = (app['hours'] / filtered_total_hours) * 100

    # adjust total apps count (subtract 1 if we filtered out rewind)
    total_apps = app_usage['total_apps']
    if len(filtered_apps) < len(app_usage['top_apps']):
        total_apps -= 1

    print(f"\nTotal Apps Used: {total_apps}")
    print(f"Total Usage Time: {filtered_total_hours:.2f} hours")

    # display top apps
    print("\nTop Applications by Usage Time:")
    app_data = []
    for app in filtered_apps:
        name = app['name']
        hours = app['hours']
        percentage = app['percentage']
        # create a simple bar chart
        bar = "█" * int(percentage / 5) if percentage > 0 else ""
        app_data.append([name, f"{hours:.2f}", f"{percentage:.1f}%", bar])

    print(tabulate(app_data, headers=["Application", "Hours", "Percentage", "Usage"], tablefmt="simple"))


def display_meetings(meetings, use_utc=False):
    """display meetings data in a formatted way.

    args:
        meetings: dictionary with meetings data from get_meetings()
        use_utc: whether to display times in utc (default: false, use local time)
    """

    print("\n" + "=" * 80)
    print(" CALENDAR MEETINGS ")
    print("=" * 80)

    if meetings is None:
        print("\nMeetings data could not be retrieved. This may be due to a database schema mismatch.")
        return

    if meetings['total_events'] == 0:
        print("\nNo calendar events found for the specified time period.")
        return

    print(f"\nTotal Meetings: {meetings['total_events']}")
    print(f"Total Meeting Time: {meetings['total_hours']} hours")
    print(f"Average Meeting Length: {meetings['avg_meeting_minutes']} minutes")

    # display calendar stats
    if meetings['calendar_stats']:
        print("\nMeetings by Calendar:")
        calendar_data = []
        for cal in meetings['calendar_stats']:
            name = cal['calendar']
            hours = cal['hours']
            count = cal['event_count']
            percentage = cal['percentage']
            calendar_data.append([name, count, f"{hours:.2f}", f"{percentage:.1f}%"])

        print(tabulate(calendar_data, headers=["Calendar", "Count", "Hours", "Percentage"], tablefmt="simple"))

    # display daily meeting hours
    if meetings['daily_meeting_hours']:
        print("\nMeeting Hours by Day:")
        daily_data = []
        for day_data in meetings['daily_meeting_hours']:
            date_str = day_data['date']
            hours = day_data['hours']

            # convert date string to local time if needed
            if not use_utc and '-' in date_str:
                try:
                    # parse the date string
                    date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    # convert to local time
                    local_date = convert_to_local_time(date_obj)
                    # format as date string
                    date_str = local_date.strftime("%Y-%m-%d")
                except ValueError:
                    # if parsing fails, keep original string
                    pass

            # create a simple bar chart
            bar = "█" * int(hours * 2) if hours > 0 else ""
            daily_data.append([date_str, f"{hours:.2f}", bar])

        print(tabulate(daily_data, headers=["Date", "Hours", "Meetings"], tablefmt="simple"))

    # display hourly distribution
    print("\nMeeting Hours by Time of Day:")
    hourly_data = []
    for hour_data in meetings['hourly_distribution']:
        hour = hour_data['hour']
        hours = hour_data['hours']
        # create a simple bar chart
        bar = "█" * int(hours * 4) if hours > 0 else ""
        hour_str = f"{hour:02d}:00"
        hourly_data.append([hour_str, f"{hours:.2f}", bar])

    print(tabulate(hourly_data, headers=["Hour", "Hours", "Meetings"], tablefmt="simple"))


def parse_arguments():
    """parse command line arguments.

    returns:
        parsed argument namespace
    """

    parser = argparse.ArgumentParser(
        description="display activity tracking data from rewinddb",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s --relative "1 day"
  %(prog)s --relative "5h"
  %(prog)s --relative "3m"
  %(prog)s --relative "10d"
  %(prog)s --relative "2w"
  %(prog)s --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"
  %(prog)s --from "2023-05-11" --to "2023-05-12"  # uses 00:00:00 and 23:59:59
  %(prog)s --from "13:00:00" --to "17:00:00"  # uses today's date
  %(prog)s --relative "7 days" --debug
  %(prog)s --relative "1 hour" --env-file /path/to/.env
  %(prog)s --relative "1 day" --utc  # display times in UTC instead of local time
"""
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-r", "--relative", metavar="TIME", help="relative time period (e.g., '1 hour', '5h', '3m', '10d', '2w')")
    group.add_argument("--from", dest="from_time", metavar="DATETIME",
                       help="start time in format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD' (uses 00:00:00), or 'HH:MM:SS' (uses today's date)")

    parser.add_argument("--to", dest="to_time", metavar="DATETIME",
                       help="end time in format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD' (uses 23:59:59), or 'HH:MM:SS' (uses today's date)")
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    parser.add_argument("--env-file", metavar="FILE", help="path to .env file with database configuration")
    parser.add_argument("--utc", action="store_true", help="display times in UTC instead of local time")

    args = parser.parse_args()

    # validate that if --from is provided, --to is also provided
    if args.from_time and not args.to_time:
        parser.error("--to is required when --from is provided")

    return args


def main():
    """main function for the activity cli tool."""

    args = parse_arguments()

    # set debug level if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("debug mode enabled")

    start_time = time.time()

    try:
        # connect to the database using rewinddb library
        logger.info("connecting to rewind database...")
        with rewinddb.RewindDB(args.env_file) as db:
            # get activity data based on the specified time range
            if args.relative:
                logger.info(f"retrieving activity data for the past {args.relative}...")
                activity_data = get_activity_relative(db, args.relative, args.debug)
            else:
                logger.info(f"retrieving activity data from {args.from_time} to {args.to_time}...")
                activity_data = get_activity_absolute(db, args.from_time, args.to_time, args.debug)

            # display the results
            display_active_hours(activity_data['active_hours'], args.utc)
            display_app_usage(activity_data['app_usage'])

            # display meetings if available
            if activity_data['meetings'] is not None:
                display_meetings(activity_data['meetings'], args.utc)
            else:
                print("\n" + "=" * 80)
                print(" CALENDAR MEETINGS ")
                print("=" * 80)
                print("\nMeetings data could not be retrieved. This may be due to a database schema mismatch.")

            elapsed_time = time.time() - start_time
            logger.info(f"activity data retrieved and displayed in {elapsed_time:.2f} seconds")

    except FileNotFoundError as e:
        logger.error(f"error: {e}")
        logger.error("check your DB_PATH setting in .env file")
        sys.exit(1)
    except ConnectionError as e:
        logger.error(f"error: {e}")
        logger.error("check your DB_PASSWORD setting in .env file")
        sys.exit(1)
    except Exception as e:
        logger.error(f"unexpected error: {e}")
        logger.error(f"error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()