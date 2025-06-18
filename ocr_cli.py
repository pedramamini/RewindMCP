#!/usr/bin/env python
"""
ocr_cli.py - command line interface for retrieving screen OCR data from rewinddb.

call flow:
1. parse command line arguments using argparse
2. connect to rewinddb database
3. determine time range based on arguments:
   - if --relative is provided, calculate relative time range from now
   - if --from and --to are provided, use specific time range
4. query screen OCR data for the specified time range
5. optionally filter by application if --app is specified
6. deduplicate OCR data to remove entries with very similar text content
7. format and display results (with conditional app name display)
8. close database connection

the cli supports two main query modes:
- relative time queries (e.g., "1 hour", "5h", "30m", "2d", "1w")
- specific time range queries with --from and --to timestamps

additional features:
- list all applications that have OCR data with --list-apps
- filter OCR data by specific application with --app
- automatic deduplication of similar text content (keeps most recent entries)
- improved display format when filtering by app (hides redundant app names)

examples:
  python ocr_cli.py --relative "1 hour"
  python ocr_cli.py --relative "5 hours"
  python ocr_cli.py --relative "5h"
  python ocr_cli.py --relative "30m"
  python ocr_cli.py --relative "2d"
  python ocr_cli.py --relative "1w"
  python ocr_cli.py --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"
  python ocr_cli.py --list-apps
  python ocr_cli.py --relative "1 day" --app "com.apple.Safari"
"""

import argparse
import datetime
from datetime import timezone
import re
import sys
import hashlib
import time
# Removed SequenceMatcher import - now using fast fingerprint approach
# Removed defaultdict import - no longer needed with fingerprint approach

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


def get_ocr_data_relative(db, time_str):
    """get screen OCR data from a relative time period.

    args:
        db: rewinddb instance
        time_str: relative time string (e.g., "1 hour", "5 hours")

    returns:
        list of OCR data dictionaries
    """

    try:
        time_components = parse_relative_time(time_str)
        return db.get_screen_ocr_text_relative(**time_components)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


def get_ocr_data_absolute(db, from_time_str, to_time_str):
    """get screen OCR data from a specific time range.

    args:
        db: rewinddb instance
        from_time_str: start time string in format "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM", "YYYY-MM-DD", "HH:MM:SS", or "HH:MM"
        to_time_str: end time string in format "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM", "YYYY-MM-DD", "HH:MM:SS", or "HH:MM"

    returns:
        list of OCR data dictionaries
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

        return db.get_screen_ocr_text_absolute(from_time, to_time)
    except ValueError as e:
        print(f"error: invalid time format. use format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD', 'HH:MM:SS', or 'HH:MM'.", file=sys.stderr)
        sys.exit(1)


def get_applications_with_ocr_data(db, time_str=None, from_time_str=None, to_time_str=None):
    """get list of applications that have OCR data.

    args:
        db: rewinddb instance
        time_str: optional relative time string (e.g., "1 week")
        from_time_str: optional start time string
        to_time_str: optional end time string

    returns:
        sorted list of unique application names
    """

    # get OCR data for the specified time range
    if time_str:
        ocr_data = get_ocr_data_relative(db, time_str)
    elif from_time_str and to_time_str:
        ocr_data = get_ocr_data_absolute(db, from_time_str, to_time_str)
    else:
        # default to last week if no time range specified
        ocr_data = get_ocr_data_relative(db, "1 week")

    # extract unique application names
    applications = set()
    for item in ocr_data:
        app = item.get('application')
        if app:
            applications.add(app)

    return sorted(list(applications))


def filter_ocr_data_by_app(ocr_data, app_name):
    """filter OCR data to only include entries from a specific application.

    args:
        ocr_data: list of OCR data dictionaries
        app_name: application name to filter by

    returns:
        filtered list of OCR data dictionaries
    """

    return [item for item in ocr_data if item.get('application') == app_name]


def normalize_text_for_similarity(text):
    """normalize text for similarity comparison.

    args:
        text: input text string

    returns:
        normalized text string suitable for similarity matching
    """
    if not text:
        return ""

    # convert to lowercase, remove extra whitespace, strip
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    # remove common punctuation that doesn't affect meaning but keep structure
    normalized = re.sub(r'[.,;:!?"\'\-_(){}[\]]+', '', normalized)
    return normalized


# Removed calculate_text_similarity - now using fast fingerprint approach


# Removed old fuzzy matching functions - now using fast fingerprint approach


def deduplicate_ocr_data_fuzzy(ocr_data, similarity_threshold=None, debug=False):
    """fast, lossy deduplication using improved text fingerprinting for maximum speed.

    uses multi-part text fingerprinting instead of similarity calculations:
    - creates fingerprints using first 30 chars + words 3-5 + last 20 chars + length
    - uses dictionary lookups for O(1) duplicate detection
    - catches variations in middle of text (like "CONANT H V S" vs "CONANT H V")
    - prioritizes speed over perfect accuracy
    - target: process 1000+ entries in under 1 second

    keeps the most recent entry when duplicates are found.

    args:
        ocr_data: list of OCR data dictionaries
        similarity_threshold: ignored (kept for compatibility)
        debug: whether to show timing and debug information

    returns:
        tuple of (deduplicated_ocr_data, num_duplicates_removed)
    """
    if not ocr_data:
        return ocr_data, 0

    start_time = time.time()

    if debug:
        print(f"starting fast fingerprint deduplication with {len(ocr_data)} entries...")

    # sort by frame_time to process chronologically (keep most recent)
    sorted_data = sorted(ocr_data, key=lambda x: x.get('frame_time', datetime.datetime.min))

    # dictionary to track fingerprints: fingerprint -> (index, item)
    fingerprint_to_item = {}
    deduplicated = []
    duplicates_removed = 0

    for current_item in sorted_data:
        current_text = current_item.get('text', '')
        current_app = current_item.get('application', '')

        # skip items with no meaningful text
        if not current_text.strip():
            deduplicated.append(current_item)
            continue

        # create improved fingerprint using multiple text parts
        normalized_text = normalize_text_for_similarity(current_text)
        text_len = len(normalized_text)

        # create fingerprint components
        first_part = normalized_text[:30] if len(normalized_text) > 30 else normalized_text
        last_part = normalized_text[-20:] if len(normalized_text) > 20 else ""

        # get middle words (words 3-5) to catch variations like "V S" vs "V" vs "U2"
        words = normalized_text.split()
        middle_words = ""
        if len(words) >= 5:
            middle_words = " ".join(words[2:5])  # words 3-5 (0-indexed)
        elif len(words) >= 3:
            middle_words = " ".join(words[2:])   # remaining words after first 2

        # combine into fingerprint: app:length:first30:middle_words:last20
        fingerprint = f"{current_app}:{text_len}:{first_part}:{middle_words}:{last_part}"

        if fingerprint in fingerprint_to_item:
            # this is a duplicate - replace the existing item with the more recent one
            existing_index, existing_item = fingerprint_to_item[fingerprint]
            deduplicated[existing_index] = current_item
            fingerprint_to_item[fingerprint] = (existing_index, current_item)
            duplicates_removed += 1
        else:
            # this is a new unique item
            new_index = len(deduplicated)
            deduplicated.append(current_item)
            fingerprint_to_item[fingerprint] = (new_index, current_item)

    elapsed = time.time() - start_time

    if debug:
        print(f"fast fingerprint deduplication completed in {elapsed:.3f} seconds")
        print(f"processed {len(ocr_data)} entries, removed {duplicates_removed} duplicates")
        print(f"processing rate: {len(ocr_data)/elapsed:.0f} entries/second")

    return deduplicated, duplicates_removed


def deduplicate_ocr_data_fast(ocr_data, debug=False):
    """legacy fast hash-based deduplication (kept for compatibility).

    this is the old exact-match approach. use deduplicate_ocr_data_fuzzy for better results.

    args:
        ocr_data: list of OCR data dictionaries
        debug: whether to show timing information

    returns:
        tuple of (deduplicated_ocr_data, num_duplicates_removed)
    """
    if not ocr_data:
        return ocr_data, 0

    start_time = time.time() if debug else None

    # sort by frame_time to process chronologically
    sorted_data = sorted(ocr_data, key=lambda x: x.get('frame_time', datetime.datetime.min))

    # use dictionary to track unique text hashes
    hash_to_item = {}
    deduplicated = []
    duplicates_removed = 0

    for current_item in sorted_data:
        current_text = current_item.get('text', '')
        current_app = current_item.get('application', '')

        # skip items with no meaningful text
        if not current_text.strip():
            deduplicated.append(current_item)
            continue

        # create hash for this text + app combination
        normalized_text = normalize_text_for_similarity(current_text)
        hash_input = f"{current_app}:{normalized_text}"
        text_hash = hashlib.md5(hash_input.encode('utf-8')).hexdigest()

        if text_hash in hash_to_item:
            # this is a duplicate - replace the existing item with the more recent one
            existing_index, existing_item = hash_to_item[text_hash]
            deduplicated[existing_index] = current_item
            hash_to_item[text_hash] = (existing_index, current_item)
            duplicates_removed += 1
        else:
            # this is a new unique item
            new_index = len(deduplicated)
            deduplicated.append(current_item)
            hash_to_item[text_hash] = (new_index, current_item)

    if debug and start_time:
        elapsed = time.time() - start_time
        print(f"hash-based deduplication completed in {elapsed:.3f} seconds")

    return deduplicated, duplicates_removed


def deduplicate_ocr_data(ocr_data, similarity_threshold=None, debug=False):
    """deduplicate OCR data using fast fingerprint-based matching.

    uses fast text fingerprinting instead of similarity calculations for maximum speed.
    can catch similar entries like:
    - "CONANT H V S + home DMs Activity Later..."
    - "CONANT H V + home DMs Activity Later..."
    - "CONANT H U2 + home DMs Activity Later..."

    keeps the most recent entry when duplicates are found.

    args:
        ocr_data: list of OCR data dictionaries
        similarity_threshold: ignored (kept for compatibility)
        debug: whether to show timing and debug information

    returns:
        tuple of (deduplicated_ocr_data, num_duplicates_removed)
    """
    return deduplicate_ocr_data_fuzzy(ocr_data, similarity_threshold, debug=debug)


# Compatibility functions for existing test files
def normalize_text_for_deduplication(text):
    """legacy function name - redirects to normalize_text_for_similarity for compatibility."""
    return normalize_text_for_similarity(text)


def create_text_hash(text, app_name=""):
    """legacy function for creating text hash - kept for compatibility with test files."""
    normalized_text = normalize_text_for_similarity(text)
    hash_input = f"{app_name}:{normalized_text}"
    return hashlib.md5(hash_input.encode('utf-8')).hexdigest()


def format_ocr_data_with_text(ocr_data, show_app_name=True):
    """format OCR data into readable text with actual text content.

    converts a list of OCR data dictionaries into a formatted string
    with timestamps, applications, and extracted text content.

    args:
        ocr_data: list of OCR data dictionaries
        show_app_name: whether to show application name in the output

    returns:
        formatted string representation of the OCR data
    """

    if not ocr_data:
        return "no OCR data available."

    # group by frame time and application for better readability
    frames = {}
    for item in ocr_data:
        frame_time = item['frame_time']
        application = item.get('application', 'Unknown')
        window = item.get('window', 'Unknown')
        text = item.get('text', '')

        # create a key for grouping
        time_str = frame_time.strftime('%Y-%m-%d %H:%M:%S')
        key = f"{time_str}_{application}_{window}"

        if key not in frames:
            frames[key] = {
                'time': frame_time,
                'application': application,
                'window': window,
                'texts': []
            }

        if text.strip():  # only add non-empty text
            frames[key]['texts'].append(text.strip())

    # sort frames by time
    sorted_frames = sorted(frames.items(), key=lambda x: x[1]['time'])

    # format each frame
    result = []
    for key, frame in sorted_frames:
        time_str = frame['time'].strftime('%Y-%m-%d %H:%M:%S')

        if show_app_name:
            app_str = f"{frame['application']}"
            if frame['window'] and frame['window'] != 'Unknown':
                app_str += f" - {frame['window']}"
            result.append(f"[{time_str}] {app_str}")
        else:
            # when not showing app name, still show window if available
            if frame['window'] and frame['window'] != 'Unknown':
                result.append(f"[{time_str}] {frame['window']}")
            else:
                result.append(f"[{time_str}]")

        # show text content
        if frame['texts']:
            for text in frame['texts']:
                # show full text content without truncation
                result.append(f"  {text}")
        else:
            result.append("  (no text content)")

        result.append("")  # empty line between frames

    return "\n".join(result)


def parse_arguments():
    """parse command line arguments.

    returns:
        parsed argument namespace
    """

    parser = argparse.ArgumentParser(
        description="retrieve screen OCR data from rewinddb",
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
  %(prog)s --list-apps  # list all applications with OCR data
  %(prog)s --relative "1 day" --app "com.apple.Safari"  # filter by application
"""
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-r", "--relative", metavar="TIME", help="relative time period (e.g., '1 hour', '5h', '3m', '10d', '2w')")
    group.add_argument("--from", dest="from_time", metavar="DATETIME",
                       help="start time in format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD' (uses 00:00:00), 'HH:MM:SS', or 'HH:MM' (uses today's date)")
    group.add_argument("--list-apps", action="store_true", help="list all applications that have OCR data")

    parser.add_argument("--to", dest="to_time", metavar="DATETIME",
                       help="end time in format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD' (uses 23:59:59), 'HH:MM:SS', or 'HH:MM' (uses today's date)")
    parser.add_argument("--app", metavar="APPLICATION", help="filter OCR data by specific application name")
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    parser.add_argument("--env-file", metavar="FILE", help="path to .env file with database configuration")
    parser.add_argument("--utc", action="store_true", help="display times in UTC instead of local time")

    args = parser.parse_args()

    # validate that if --from is provided, --to is also provided
    if args.from_time and not args.to_time:
        parser.error("--to is required when --from is provided")

    # validate that --app can only be used with time range queries
    if args.app and args.list_apps:
        parser.error("--app cannot be used with --list-apps")

    return args


def main():
    """main function for the OCR cli tool."""

    args = parse_arguments()

    try:
        # connect to the database using rewinddb library
        print("connecting to rewind database...")
        with rewinddb.RewindDB(args.env_file) as db:

            if args.list_apps:
                # list all applications with OCR data
                print("retrieving applications with OCR data...")
                applications = get_applications_with_ocr_data(db)

                if not applications:
                    print("no applications found with OCR data.")
                    return

                print(f"found {len(applications)} applications with OCR data:")
                for app in applications:
                    print(f"  {app}")
                return

            # get OCR data based on the specified time range
            if args.relative:
                print(f"retrieving OCR data from the last {args.relative}...")
                ocr_data = get_ocr_data_relative(db, args.relative)
            else:
                print(f"retrieving OCR data from {args.from_time} to {args.to_time}...")
                ocr_data = get_ocr_data_absolute(db, args.from_time, args.to_time)

            # filter by application if specified
            if args.app:
                print(f"filtering OCR data for application: {args.app}")
                original_count = len(ocr_data)
                ocr_data = filter_ocr_data_by_app(ocr_data, args.app)
                filtered_count = len(ocr_data)
                print(f"filtered from {original_count} to {filtered_count} OCR entries.")

            # deduplicate OCR data
            if ocr_data:
                if args.debug:
                    print("deduplicating OCR data using fast fingerprint matching...")
                else:
                    print("deduplicating OCR data...")
                ocr_data, duplicates_removed = deduplicate_ocr_data(ocr_data, debug=args.debug)
                if duplicates_removed > 0:
                    print(f"removed {duplicates_removed} duplicate entries.")
                else:
                    print("no duplicates found.")

            # format and display results
            if not ocr_data:
                if args.app:
                    print(f"no OCR data found for application '{args.app}' in the specified time range.")
                else:
                    print("no OCR data found for the specified time range.")
                return

            print(f"found {len(ocr_data)} OCR entries after deduplication.")

            # convert timestamps to local time if not using UTC
            if not args.utc:
                for item in ocr_data:
                    if 'frame_time' in item:
                        item['frame_time'] = convert_to_local_time(item['frame_time'])

            # format with conditional app name display
            show_app_name = not bool(args.app)  # hide app name when filtering by specific app
            formatted = format_ocr_data_with_text(ocr_data, show_app_name=show_app_name)
            print("\nOCR data:")
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