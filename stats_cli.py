#!/usr/bin/env python3
"""
stats_cli.py - command line tool to display statistics about rewind.ai data.

this script provides statistics about audio transcripts, screen ocr data,
application usage, and other metrics from the rewind.ai database.
"""

import argparse
import datetime
from datetime import timezone
import json
import logging
import re
import sys
import threading
import time
from tabulate import tabulate
import rewinddb


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

# configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def spinner(stop_event, message):
    """display a simple spinner with a message while a task is running.

    args:
        stop_event: threading event to signal when to stop the spinner
        message: message to display alongside the spinner
    """

    spinner_chars = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']
    i = 0

    while not stop_event.is_set():
        sys.stdout.write(f"\r{spinner_chars[i]} {message}")
        sys.stdout.flush()
        i = (i + 1) % len(spinner_chars)
        time.sleep(0.1)

    # clear the spinner line when done
    sys.stdout.write("\r" + " " * (len(message) + 2) + "\r")
    sys.stdout.flush()


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


def display_stats(stats, relative_time=None, use_utc=False):
    """display collected statistics in a formatted way.

    formats and prints the collected statistics to the console.

    args:
        stats: dictionary with comprehensive statistics
        relative_time: optional relative time string used for display
    """
    audio_stats = stats['audio']
    screen_stats = stats['screen']
    app_stats = stats['app_usage']
    db_stats = stats['database']

    print("\n" + "=" * 80)
    print(" REWIND.AI DATABASE STATISTICS ")
    print("=" * 80)

    # database overview
    if db_stats['db_size_mb'] > 0:
        print("\n📊 DATABASE OVERVIEW")
        print(f"Database Size: {db_stats['db_size_mb']} MB")
        print(f"Number of Tables: {db_stats['table_count']}")
    # Skip database overview section for relative time queries
    print("\nData Types Explanation:")
    print("- Audio: Voice recordings captured by Rewind")
    print("- Transcript Words: Individual words extracted from audio recordings")
    print("- Frames: Screenshots captured by Rewind at regular intervals")
    print("- Nodes: Text elements extracted from screen captures using OCR")
    print("- Segments: Application usage sessions (time periods in specific apps/windows)")

    # audio statistics
    print("\n🎙️ AUDIO TRANSCRIPT STATISTICS")
    earliest_date = audio_stats['earliest_date']
    if earliest_date:
        # convert to local time if not using UTC
        if not use_utc:
            earliest_date = convert_to_local_time(earliest_date)
        earliest_date_str = earliest_date.strftime("%Y-%m-%d %H:%M:%S")
    else:
        earliest_date_str = "No data"
    print(f"Earliest Record: {earliest_date_str}")
    print(f"Total Audio Recordings: {audio_stats['total_audio']}")
    print(f"Total Transcript Words: {audio_stats['total_words']}")

    # check if we're using relative time or standard time periods
    if 'relative_count' in audio_stats:
        audio_table = [
            [f"Past {relative_time}" if relative_time else "Custom Time Period", audio_stats['relative_count']]
        ]
        print("\nTranscript Words:")
    else:
        audio_table = [
            ["Past Hour", audio_stats['hour_count']],
            ["Past Day", audio_stats['day_count']],
            ["Past Week", audio_stats['week_count']],
            ["Past Month", audio_stats['month_count']]
        ]
        print("\nTranscript Words by Time Period:")
    print(tabulate(audio_table, headers=["Time Period", "Word Count"], tablefmt="simple"))

    # screen statistics
    print("\n👁️ SCREEN OCR STATISTICS")
    earliest_date = screen_stats['earliest_date']
    if earliest_date:
        # convert to local time if not using UTC
        if not use_utc:
            earliest_date = convert_to_local_time(earliest_date)
        earliest_date_str = earliest_date.strftime("%Y-%m-%d %H:%M:%S")
    else:
        earliest_date_str = "No data"
    print(f"Earliest Record: {earliest_date_str}")
    print(f"Total Frames: {screen_stats['total_frames']}")
    print(f"Total OCR Nodes: {screen_stats['total_nodes']}")

    # check if we're using relative time or standard time periods
    if 'relative_count' in screen_stats:
        screen_table = [
            [f"Past {relative_time}" if relative_time else "Custom Time Period", screen_stats['relative_count']]
        ]
        print("\nOCR Elements:")
    else:
        screen_table = [
            ["Past Hour", screen_stats['hour_count']],
            ["Past Day", screen_stats['day_count']],
            ["Past Week", screen_stats['week_count']],
            ["Past Month", screen_stats['month_count']]
        ]
        print("\nOCR Elements by Time Period:")
    print(tabulate(screen_table, headers=["Time Period", "Element Count"], tablefmt="simple"))

    # app usage statistics
    # adjust the header based on whether we're using relative time
    if relative_time:
        print(f"\n💻 APPLICATION USAGE STATISTICS (Past {relative_time})")
    else:
        print("\n💻 APPLICATION USAGE STATISTICS (Past Week)")
    print(f"Total Applications: {app_stats['total_apps']}")
    print(f"Total Usage Time: {app_stats['total_hours']} hours")
    print("Note: Internal components like 'ai.rewind.audiorecorder' are filtered out")

    app_table = []
    for app in app_stats['top_apps']:
        app_table.append([app['app'], app['hours'], f"{app['percentage']}%"])

    print("\nTop 10 Applications by Usage Time:")
    print(tabulate(app_table, headers=["Application", "Hours", "Percentage"], tablefmt="simple"))

    # table statistics
    if db_stats['table_stats']:
        print("\n📋 TABLE RECORD COUNTS")
        table_table = []
        for table in db_stats['table_stats'][:10]:  # show top 10 tables
            table_table.append([table['table'], table['records']])
        print(tabulate(table_table, headers=["Table", "Records"], tablefmt="simple"))
    # Skip table record counts for relative time queries
    # display calculation time if available
    if 'calculation_time' in stats:
        print(f"\n⏱️ calculation time: {stats['calculation_time']:.2f} seconds")

    print("\n" + "=" * 80)


def main():
    """main function to run the stats cli."""
    parser = argparse.ArgumentParser(
        description="display statistics about rewind.ai data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s
  %(prog)s --json
  %(prog)s --relative "1 day"
  %(prog)s --relative "5h"
  %(prog)s --relative "3m"
  %(prog)s --relative "10d"
  %(prog)s --relative "2w"
  %(prog)s --env /path/to/.env
  %(prog)s --relative "1 day" --utc  # display times in UTC instead of local time
"""
    )
    parser.add_argument("--env", help="path to .env file with database configuration")
    parser.add_argument("--json", action="store_true", help="output statistics as JSON")
    parser.add_argument("-r", "--relative", metavar="TIME",
                        help="relative time period (e.g., '1 hour', '5h', '3m', '10d', '2w')")
    parser.add_argument("--utc", action="store_true", help="display times in UTC instead of local time")
    args = parser.parse_args()

    # initialize spinner control variables
    stop_spinner = threading.Event()
    spinner_thread = None

    try:
        # connect to the database
        print("initializing rewind database connection...")
        start_time = time.time()

        # start spinner for database connection
        stop_spinner = threading.Event()
        spinner_thread = threading.Thread(
            target=spinner,
            args=(stop_spinner, "connecting to database (this may take a moment)...")
        )
        spinner_thread.daemon = True
        spinner_thread.start()

        db = rewinddb.RewindDB(args.env)

        # stop connection spinner and show progress
        stop_spinner.set()
        spinner_thread.join()
        print("✓ database connection established")

        # start spinner for statistics collection
        if args.relative:
            # print(f"gathering statistics for the past {args.relative}...")
            spinner_message = f"analyzing database tables and records for the past {args.relative} (this may take a while)..."
        else:
            # print("gathering statistics from database...")
            spinner_message = "analyzing database tables and records (this may take a while)..."

        stop_spinner = threading.Event()
        spinner_thread = threading.Thread(
            target=spinner,
            args=(stop_spinner, spinner_message)
        )
        spinner_thread.daemon = True
        spinner_thread.start()

        # collect statistics using the rewinddb module and measure execution time
        stats_start_time = time.time()

        if args.relative:
            try:
                time_components = parse_relative_time(args.relative)
                stats = db.get_statistics(**time_components)
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # default behavior - get all statistics
            stats = db.get_statistics()

        # calculate stats execution time
        stats_elapsed_time = time.time() - stats_start_time

        # add calculation time to stats dictionary
        stats['calculation_time'] = stats_elapsed_time

        # stop statistics spinner
        stop_spinner.set()
        spinner_thread.join()
        print("✓ statistics collection complete")
        print(f"⏱️ stats calculated in {stats_elapsed_time:.2f} seconds")

        # output statistics
        if args.json:
            # Convert datetime objects to strings for JSON serialization
            json_stats = stats.copy()

            # Handle audio stats
            if json_stats['audio']['earliest_date']:
                json_stats['audio']['earliest_date'] = json_stats['audio']['earliest_date'].strftime("%Y-%m-%d %H:%M:%S")

            # Handle screen stats
            if json_stats['screen']['earliest_date']:
                json_stats['screen']['earliest_date'] = json_stats['screen']['earliest_date'].strftime("%Y-%m-%d %H:%M:%S")

            # Output as JSON
            print(json.dumps(json_stats, indent=2))
        else:
            # Display formatted statistics
            display_stats(stats, args.relative, args.utc)

        # close the database connection
        db.close()

        elapsed_time = time.time() - start_time
        logger.info(f"statistics collection completed in {elapsed_time:.2f} seconds")

    except FileNotFoundError as e:
        # ensure spinner is stopped if running
        if spinner_thread and spinner_thread.is_alive():
            stop_spinner.set()
            spinner_thread.join()
        print("✗ error: database file not found")
        logger.error(f"database file not found: {e}")
        logger.info("check your DB_PATH setting in .env file")
        sys.exit(1)
    except ConnectionError as e:
        # ensure spinner is stopped if running
        if spinner_thread and spinner_thread.is_alive():
            stop_spinner.set()
            spinner_thread.join()
        print("✗ error: database connection failed")
        logger.error(f"database connection error: {e}")
        logger.info("check your DB_PASSWORD setting in .env file")
        sys.exit(1)
    except KeyboardInterrupt:
        # ensure spinner is stopped if running
        if spinner_thread and spinner_thread.is_alive():
            stop_spinner.set()
            spinner_thread.join()
        print("\n✗ operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        # ensure spinner is stopped if running
        if spinner_thread and spinner_thread.is_alive():
            stop_spinner.set()
            spinner_thread.join()
        print(f"✗ error: operation failed - {str(e)}")
        logger.error(f"unexpected error: {e}")
        import traceback
        logger.error(f"traceback: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()