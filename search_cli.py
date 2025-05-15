#!/usr/bin/env python
"""
search_cli.py - command line interface for searching keywords in rewinddb.

call flow:
1. parse command line arguments using argparse
2. connect to rewinddb database
3. determine time range based on arguments:
   - if --relative is provided, calculate relative time range from now
   - if --from and --to are provided, use specific time range
   - if no time range is specified, use default (7 days)
4. search for keywords across both audio transcripts and screen ocr data
5. format and display results:
   - for audio hits, show timestamp and text context before/after the hit
   - for visual hits, show timestamp and application
6. close database connection

the cli supports three main query modes:
- simple keyword search with default time range (e.g., "python search_cli.py meeting")
- relative time queries (e.g., "python search_cli.py meeting --relative "1 day"" or "--relative "5h"")
- specific time range queries with --from and --to timestamps

examples:
  python search_cli.py "meeting"
  python search_cli.py "project" --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"
  python search_cli.py "presentation" --relative "1 day"
  python search_cli.py "meeting" --relative "5h"
  python search_cli.py "code" --relative "3m"
  python search_cli.py "project" --relative "10d"
  python search_cli.py "design" --relative "2w"
  python search_cli.py "python" --context 5 --debug
"""

import argparse
import datetime
import re
import sys

import rewinddb
import rewinddb.utils


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


def search_with_relative_time(db, keyword, time_str, context=3, debug=False):
    """search for keywords with a relative time period.

    args:
        db: rewinddb instance
        keyword: search keyword
        time_str: relative time string (e.g., "1 hour", "5 hours")
        context: number of words to show before/after audio hits
        debug: whether to print debug information

    returns:
        dictionary with 'audio' and 'screen' keys containing search results
    """

    try:
        time_components = parse_relative_time(time_str)
        if debug:
            print(f"debug: searching for '{keyword}' in the last {time_str}")
            print(f"debug: time components: {time_components}")

        # calculate days for the search method
        total_seconds = (
            time_components["days"] * 86400 +
            time_components["hours"] * 3600 +
            time_components["minutes"] * 60 +
            time_components["seconds"]
        )
        days = total_seconds / 86400  # convert to days for the search method

        if debug:
            print(f"debug: searching {days:.2f} days back")

        return db.search(keyword, days=days)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


def search_with_absolute_time(db, keyword, from_time_str, to_time_str, debug=False):
    """search for keywords within a specific time range.

    args:
        db: rewinddb instance
        keyword: search keyword
        from_time_str: start time string in format "YYYY-MM-DD HH:MM:SS" or "HH:MM:SS"
        to_time_str: end time string in format "YYYY-MM-DD HH:MM:SS" or "HH:MM:SS"
        debug: whether to print debug information

    returns:
        dictionary with 'audio' and 'screen' keys containing search results
    """

    try:
        # check if from_time_str is time-only format (HH:MM:SS)
        if len(from_time_str) <= 8 and from_time_str.count(':') == 2:
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            from_time_str = f"{today} {from_time_str}"

        # check if to_time_str is time-only format (HH:MM:SS)
        if len(to_time_str) <= 8 and to_time_str.count(':') == 2:
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            to_time_str = f"{today} {to_time_str}"

        from_time = datetime.datetime.strptime(from_time_str, "%Y-%m-%d %H:%M:%S")
        to_time = datetime.datetime.strptime(to_time_str, "%Y-%m-%d %H:%M:%S")

        if debug:
            print(f"debug: searching for '{keyword}' from {from_time} to {to_time}")

        # Use the search method with the absolute time range
        # Convert the absolute time range to days for the search method
        days = (to_time - from_time).total_seconds() / 86400

        if debug:
            print(f"debug: calculated {days:.2f} days between {from_time} and {to_time}")

        # Get search results using the search method
        results = db.search(keyword, days=days)

        # Filter results to only include those within the specified time range
        audio_results = []
        for item in results['audio']:
            if from_time <= item['absolute_time'] <= to_time:
                audio_results.append(item)

        screen_results = []
        for item in results['screen']:
            if from_time <= item['frame_time'] <= to_time:
                screen_results.append(item)

        return {
            'audio': audio_results,
            'screen': screen_results
        }
    except ValueError as e:
        print(f"error: invalid time format. use format 'YYYY-MM-DD HH:MM:SS' or 'HH:MM:SS'.", file=sys.stderr)
        sys.exit(1)


def format_audio_results(results, context=3):
    """format audio search results with context.

    args:
        results: list of audio transcript dictionaries
        context: number of words to show before/after the hit

    returns:
        formatted string representation of the results
    """

    if not results:
        return "no audio matches found."

    # group words by audio session and match time
    sessions = {}
    for item in results:
        audio_id = item['audio_id']
        if audio_id not in sessions:
            sessions[audio_id] = {
                'start_time': item['audio_start_time'],
                'matches': {}
            }

        # if this is a match word, create a new match group
        if item.get('is_match', False):
            # use absolute_time as key to group matches
            match_time = item['absolute_time']
            time_key = match_time.strftime('%Y-%m-%d %H:%M:%S.%f')

            if time_key not in sessions[audio_id]['matches']:
                sessions[audio_id]['matches'][time_key] = {
                    'match_time': match_time,
                    'words': []
                }

        # add word to appropriate match group or closest one
        if item.get('is_match', False):
            match_time = item['absolute_time']
            time_key = match_time.strftime('%Y-%m-%d %H:%M:%S.%f')
            sessions[audio_id]['matches'][time_key]['words'].append(item)
        else:
            # find closest match time to add context word to
            word_time = item['absolute_time']
            closest_match = None
            min_diff = float('inf')

            for match_time_key, match_data in sessions[audio_id]['matches'].items():
                diff = abs((word_time - match_data['match_time']).total_seconds())
                if diff < min_diff:
                    min_diff = diff
                    closest_match = match_time_key

            if closest_match:
                sessions[audio_id]['matches'][closest_match]['words'].append(item)

    # format each session with context
    formatted_results = []
    for audio_id, session in sessions.items():
        start_time = session['start_time'].strftime('%Y-%m-%d %H:%M:%S')
        formatted_results.append(f"[{start_time}] Audio Match:")

        # process each match in this session
        for match_time_key, match_data in session['matches'].items():
            # sort words by time offset
            words = sorted(match_data['words'], key=lambda x: x['time_offset'])

            # format the context
            word_texts = []
            for word in words:
                if word.get('is_match', False):
                    # highlight match words
                    word_texts.append(f"{word['word']}")
                else:
                    word_texts.append(word['word'])

            context_text = " ".join(word_texts)

            # add the context to the results
            formatted_results.append(f"  ...{context_text}...")

        formatted_results.append("")  # empty line between sessions

    return "\n".join(formatted_results)


def format_screen_results(results):
    """format screen ocr search results.

    args:
        results: list of screen ocr dictionaries

    returns:
        formatted string representation of the results
    """

    if not results:
        return "no screen matches found."

    # format each result
    formatted_results = []

    for item in results:
        # handle results from searchRanking_content
        if 'text' in item and item['text']:
            # try to get a timestamp
            timestamp = None
            if 'frame_time' in item and item['frame_time']:
                timestamp = item['frame_time']
            elif 'timestamp_info' in item and item['timestamp_info']:
                # try to extract timestamp from timestamp_info
                timestamp_str = str(item['timestamp_info'])
                if "UTC:" in timestamp_str:
                    timestamp_str = timestamp_str.split("UTC:")[0].strip()
                    try:
                        timestamp = datetime.datetime.strptime(timestamp_str, "%a %b %d %I:%M:%S %p")
                        # add current year since it's missing
                        current_year = datetime.datetime.now().year
                        timestamp = timestamp.replace(year=current_year)
                    except:
                        pass

            # format the timestamp
            time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else "Unknown time"

            # get application and window info
            app_str = ""
            if 'application' in item and item['application'] and 'window' in item and item['window']:
                app_str = f"{item['application']} - {item['window']}"
            elif 'window_info' in item and item['window_info']:
                app_str = str(item['window_info'])
            else:
                app_str = "Unknown application"

            # add the formatted result
            formatted_results.append(f"[{time_str}] Screen Match in {app_str}")

            # add the text content with more context
            text_content = item['text']
            formatted_results.append(f"  Text: {text_content}")

            # construct recording path based on content ID
            if 'content_id' in item and item['content_id']:
                content_id = item['content_id']

                # Query the database to get the frame.createdAt for this content_id
                try:
                    # First, check if we have a direct connection to the database
                    if hasattr(db, 'cursor') and db.cursor:
                        # Use the existing database connection
                        cursor = db.cursor
                    else:
                        # Create a new connection
                        from rewinddb.config import get_db_path, get_db_password
                        import pysqlcipher3.dbapi2 as sqlite3

                        db_path = get_db_path()
                        db_password = get_db_password()

                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()

                        # Configure the connection for the encrypted database
                        cursor.execute(f"PRAGMA key = '{db_password}'")
                        cursor.execute("PRAGMA cipher_compatibility = 4")

                    # Query the frame table to get the createdAt timestamp for this content_id
                    cursor.execute("""
                        SELECT
                            createdAt
                        FROM
                            frame
                        WHERE
                            id = ?
                    """, (content_id,))

                    result = cursor.fetchone()
                    if result:
                        created_at = result[0]

                        # Parse the timestamp
                        if isinstance(created_at, int):
                            # Convert milliseconds to datetime
                            frame_time = datetime.datetime.fromtimestamp(created_at / 1000)
                        else:
                            # Parse ISO format
                            try:
                                frame_time = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%f")
                            except ValueError:
                                frame_time = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S")

                        # Construct recording path
                        year_month = frame_time.strftime("%Y%m")
                        day = frame_time.strftime("%d")
                        recording_path = f"~/Library/Application Support/com.memoryvault.MemoryVault/chunks/{year_month}/{day}"

                        formatted_results.append(f"  Recording path: {recording_path}")
                        formatted_results.append(f"  Timestamp: {frame_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    else:
                        # If no timestamp found, use the content_id to provide a hint
                        formatted_results.append(f"  Content ID: {content_id}")
                        formatted_results.append("  Note: This content ID could not be linked to a frame timestamp")
                except Exception as e:
                    # Fallback if there's an error
                    formatted_results.append(f"  Content ID: {content_id}")
                    formatted_results.append(f"  Note: Error retrieving frame timestamp: {e}")

            formatted_results.append("")  # empty line between results

        # handle results from traditional search
        elif 'frame_id' in item and 'frame_time' in item:
            if item['frame_time']:
                time_str = item['frame_time'].strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = "Unknown time"

            app_str = "Unknown application"
            if 'application' in item and item['application'] and 'window' in item and item['window']:
                app_str = f"{item['application']} - {item['window']}"

            formatted_results.append(f"[{time_str}] Screen Match in {app_str}")

            # construct recording path based on frame ID
            if 'frame_id' in item and item['frame_time']:
                frame_id = item['frame_id']
                timestamp = item['frame_time']

                # Construct recording path
                year_month = timestamp.strftime("%Y%m")
                day = timestamp.strftime("%d")
                recording_path = f"~/Library/Application Support/com.memoryvault.MemoryVault/chunks/{year_month}/{day}"

                formatted_results.append(f"  Recording path: {recording_path}")
                formatted_results.append(f"  Timestamp: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            elif 'frame_id' in item:
                # Fallback if timestamp is not available
                formatted_results.append(f"  Frame ID: {item['frame_id']}")
                formatted_results.append("  Note: No timestamp available for this frame")

            formatted_results.append("")  # empty line between results

    return "\n".join(formatted_results)


def parse_arguments():
    """parse command line arguments.

    returns:
        parsed argument namespace
    """

    parser = argparse.ArgumentParser(
        description="search for keywords across audio transcripts and screen ocr data in rewinddb",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s "meeting"
  %(prog)s "project" --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"
  %(prog)s "project" --from "13:00:00" --to "17:00:00"  # uses today's date
  %(prog)s "presentation" --relative "1 day"
  %(prog)s "meeting" --relative "5h"
  %(prog)s "code" --relative "3m"
  %(prog)s "project" --relative "10d"
  %(prog)s "design" --relative "2w"
  %(prog)s "python" --context 5 --debug
  %(prog)s "meeting" --env-file /path/to/.env
"""
    )

    parser.add_argument("keyword", help="keyword to search for")

    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument("-r", "--relative", metavar="TIME", help="relative time period (e.g., '1 hour', '5h', '3m', '10d', '2w')")
    time_group.add_argument("--from", dest="from_time", metavar="DATETIME",
                           help="start time in format 'YYYY-MM-DD HH:MM:SS' or 'HH:MM:SS' (uses today's date)")

    parser.add_argument("--to", dest="to_time", metavar="DATETIME",
                       help="end time in format 'YYYY-MM-DD HH:MM:SS' or 'HH:MM:SS' (uses today's date)")
    parser.add_argument("--context", type=int, default=3,
                       help="number of words to show before/after audio hits (default: 3)")
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    parser.add_argument("--env-file", metavar="FILE", help="path to .env file with database configuration")

    args = parser.parse_args()

    # validate that if --from is provided, --to is also provided
    if args.from_time and not args.to_time:
        parser.error("--to is required when --from is provided")

    return args


# No replacement needed - removing the DirectSqliteAccess class


def main():
    """main function for the search cli tool."""

    args = parse_arguments()

    try:
        # connect to the database using rewinddb library
        print("connecting to rewind database...")
        with rewinddb.RewindDB(args.env_file) as db:
            # search based on the specified time range
            if args.relative:
                print(f"searching for '{args.keyword}' in the last {args.relative}...")
                results = search_with_relative_time(db, args.keyword, args.relative,
                                                  args.context, args.debug)
            elif args.from_time:
                print(f"searching for '{args.keyword}' from {args.from_time} to {args.to_time}...")
                results = search_with_absolute_time(db, args.keyword, args.from_time,
                                                  args.to_time, args.debug)
            else:
                # default to 120 days if no time range specified
                print(f"searching for '{args.keyword}' in the last 120 days...")
                results = db.search(args.keyword, days=120)

            # format and display results
            audio_results = results['audio']
            screen_results = results['screen']

            print(f"found {len(audio_results)} audio matches and {len(screen_results)} screen matches.")

            if args.debug:
                print(f"\ndebug: first few audio matches:")
                for i, match in enumerate(audio_results[:3]):
                    print(f"debug: match {i+1}: {match}")

                print(f"\ndebug: first few screen matches:")
                for i, match in enumerate(screen_results[:3]):
                    print(f"debug: match {i+1}: {match}")

            # display audio results
            print("\naudio matches:")
            formatted_audio = format_audio_results(audio_results, args.context)
            print(formatted_audio)

            # display screen results
            print("\nscreen matches:")
            formatted_screen = format_screen_results(screen_results)
            print(formatted_screen)

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