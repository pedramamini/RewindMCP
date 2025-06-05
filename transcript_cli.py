#!/usr/bin/env python
"""
transcript_cli.py - command line interface for retrieving audio transcripts from rewinddb.

call flow:
1. parse command line arguments using argparse
2. connect to rewinddb database
3. determine time range based on arguments:
   - if --relative is provided, calculate relative time range from now
   - if --from and --to are provided, use specific time range
4. query audio transcripts for the specified time range
5. format and display results
6. close database connection

the cli supports two main query modes:
- relative time queries (e.g., "1 hour", "5h", "30m", "2d", "1w")
- specific time range queries with --from and --to timestamps

examples:
  python transcript_cli.py --relative "1 hour"
  python transcript_cli.py --relative "5 hours"
  python transcript_cli.py --relative "5h"
  python transcript_cli.py --relative "30m"
  python transcript_cli.py --relative "2d"
  python transcript_cli.py --relative "1w"
  python transcript_cli.py --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"
"""

import argparse
import datetime
from datetime import timezone
import re
import sys

import rewinddb
import rewinddb.utils


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


def get_transcripts_relative(db, time_str):
    """get audio transcripts from a relative time period.

    args:
        db: rewinddb instance
        time_str: relative time string (e.g., "1 hour", "5 hours")

    returns:
        list of transcript dictionaries
    """

    try:
        time_components = parse_relative_time(time_str)
        return db.get_audio_transcripts_relative(**time_components)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


def get_transcripts_absolute(db, from_time_str, to_time_str):
    """get audio transcripts from a specific time range.

    args:
        db: rewinddb instance
        from_time_str: start time string in format "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM", "YYYY-MM-DD", "HH:MM:SS", or "HH:MM"
        to_time_str: end time string in format "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM", "YYYY-MM-DD", "HH:MM:SS", or "HH:MM"

    returns:
        list of transcript dictionaries
    """

    def normalize_time_string(time_str, is_end_time=False):
        """normalize time string to handle various formats."""
        # check if time_str is time-only format (HH:MM or HH:MM:SS)
        if len(time_str) <= 8 and ':' in time_str:
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            # if it's HH:MM format, add :00 for seconds
            if time_str.count(':') == 1:
                time_str = f"{time_str}:00"
            time_str = f"{today} {time_str}"
        # check if it's date-only format (YYYY-MM-DD)
        elif len(time_str) == 10 and time_str.count('-') == 2:
            if is_end_time:
                time_str = f"{time_str} 23:59:59"
            else:
                time_str = f"{time_str} 00:00:00"
        # check if it's date with HH:MM format
        elif ' ' in time_str and time_str.split(' ')[1].count(':') == 1:
            time_str = f"{time_str}:00"

        return time_str

    try:
        # get local timezone for proper conversion
        local_tz = datetime.datetime.now().astimezone().tzinfo

        # normalize time strings to handle various formats
        from_time_str = normalize_time_string(from_time_str, is_end_time=False)
        to_time_str = normalize_time_string(to_time_str, is_end_time=True)

        # parse as naive datetime first
        from_time_naive = datetime.datetime.strptime(from_time_str, "%Y-%m-%d %H:%M:%S")
        to_time_naive = datetime.datetime.strptime(to_time_str, "%Y-%m-%d %H:%M:%S")

        # add local timezone info and convert to UTC for database query
        from_time = from_time_naive.replace(tzinfo=local_tz).astimezone(timezone.utc)
        to_time = to_time_naive.replace(tzinfo=local_tz).astimezone(timezone.utc)

        return db.get_audio_transcripts_absolute(from_time, to_time)
    except ValueError as e:
        print(f"error: invalid time format. use format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD', 'HH:MM:SS', or 'HH:MM'.", file=sys.stderr)
        sys.exit(1)


def parse_arguments():
    """parse command line arguments.

    returns:
        parsed argument namespace
    """

    parser = argparse.ArgumentParser(
        description="retrieve audio transcripts from rewinddb",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s --relative "1 hour"
  %(prog)s --relative "5 hours"
  %(prog)s --relative "5h"
  %(prog)s --relative "30m"
  %(prog)s --relative "2d"
  %(prog)s --relative "1w"
  %(prog)s --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"
  %(prog)s --from "2023-05-11" --to "2023-05-12"  # uses 00:00:00 and 23:59:59
  %(prog)s --from "13:00:00" --to "17:00:00"  # uses today's date
  %(prog)s --from "13:00" --to "17:00"  # uses today's date, HH:MM format
  %(prog)s --relative "7 days" --debug
  %(prog)s --relative "1 hour" --env-file /path/to/.env
  %(prog)s --relative "1 day" --utc  # display times in UTC instead of local time
"""
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-r", "--relative", metavar="TIME", help="relative time period (e.g., '1 hour', '5h', '3m', '10d', '2w')")
    group.add_argument("--from", dest="from_time", metavar="DATETIME",
                       help="start time in format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD' (uses 00:00:00), 'HH:MM:SS', or 'HH:MM' (uses today's date)")

    parser.add_argument("--to", dest="to_time", metavar="DATETIME",
                       help="end time in format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD' (uses 23:59:59), 'HH:MM:SS', or 'HH:MM' (uses today's date)")
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    parser.add_argument("--env-file", metavar="FILE", help="path to .env file with database configuration")
    parser.add_argument("--utc", action="store_true", help="display times in UTC instead of local time")

    args = parser.parse_args()

    # validate that if --from is provided, --to is also provided
    if args.from_time and not args.to_time:
        parser.error("--to is required when --from is provided")

    return args


# No replacement needed - removing the DirectSqliteAccess class


def main():
    """main function for the transcript cli tool."""

    args = parse_arguments()

    try:
        # connect to the database using rewinddb library
        print("connecting to rewind database...")
        with rewinddb.RewindDB(args.env_file) as db:
            # get transcripts based on the specified time range
            if args.relative:
                print(f"retrieving transcripts from the last {args.relative}...")
                transcripts = get_transcripts_relative(db, args.relative)
            else:
                print(f"retrieving transcripts from {args.from_time} to {args.to_time}...")
                transcripts = get_transcripts_absolute(db, args.from_time, args.to_time)

            # format and display results
            if not transcripts:
                print("no transcripts found for the specified time range.")
                return

            print(f"found {len(transcripts)} transcript words.")

            # convert timestamps to local time if not using UTC
            if not args.utc:
                for transcript in transcripts:
                    if 'absolute_time' in transcript:
                        transcript['absolute_time'] = convert_to_local_time(transcript['absolute_time'])
                    if 'audio_start_time' in transcript:
                        transcript['audio_start_time'] = convert_to_local_time(transcript['audio_start_time'])

            formatted = rewinddb.utils.format_transcript(transcripts)
            print("\ntranscripts:")
            print(formatted)

    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        print("check your DB_PATH setting in .env file", file=sys.stderr)
        sys.exit(1)
    except ConnectionError as e:
        print(f"error: {e}", file=sys.stderr)
        print("check your DB_PASSWORD setting in .env file", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"unexpected error: {e}", file=sys.stderr)
        print(f"error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()