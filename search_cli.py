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


def search_with_relative_time(db, keyword, time_str, context=100, debug=False):
    """search for keywords with a relative time period.

    args:
        db: rewinddb instance
        keyword: search keyword
        time_str: relative time string (e.g., "1 hour", "5 hours")
        context: number of words to show before/after audio hits (default: 100)
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
        from_time_str: start time string in format "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM", "HH:MM:SS", or "HH:MM"
        to_time_str: end time string in format "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM", "HH:MM:SS", or "HH:MM"
        debug: whether to print debug information

    returns:
        dictionary with 'audio' and 'screen' keys containing search results
    """

    def normalize_time_string(time_str):
        """normalize time string to handle both HH:MM and HH:MM:SS formats."""
        # check if time_str is time-only format (HH:MM or HH:MM:SS)
        if len(time_str) <= 8 and ':' in time_str:
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            # if it's HH:MM format, add :00 for seconds
            if time_str.count(':') == 1:
                time_str = f"{time_str}:00"
            time_str = f"{today} {time_str}"
        # check if it's date with HH:MM format
        elif ' ' in time_str and time_str.split(' ')[1].count(':') == 1:
            time_str = f"{time_str}:00"

        return time_str

    try:
        # get local timezone for proper conversion
        local_tz = datetime.datetime.now().astimezone().tzinfo

        # normalize time strings to handle HH:MM format
        from_time_str = normalize_time_string(from_time_str)
        to_time_str = normalize_time_string(to_time_str)

        # parse as naive datetime first
        from_time_naive = datetime.datetime.strptime(from_time_str, "%Y-%m-%d %H:%M:%S")
        to_time_naive = datetime.datetime.strptime(to_time_str, "%Y-%m-%d %H:%M:%S")

        # add local timezone info and convert to UTC for database query
        from_time = from_time_naive.replace(tzinfo=local_tz).astimezone(timezone.utc)
        to_time = to_time_naive.replace(tzinfo=local_tz).astimezone(timezone.utc)

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
        print(f"error: invalid time format. use format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'HH:MM:SS', or 'HH:MM'.", file=sys.stderr)
        sys.exit(1)


def format_audio_results(results, context=100, use_utc=False):
    """format audio search results with context.

    args:
        results: list of audio transcript dictionaries
        context: number of words to show before/after the hit (default: 100)

    returns:
        formatted string representation of the results
    """

    if not results:
        return "no audio matches found."

    # group words by audio session first
    sessions = {}
    for item in results:
        audio_id = item['audio_id']
        if audio_id not in sessions:
            sessions[audio_id] = {
                'start_time': item['audio_start_time'],
                'words': []
            }
        sessions[audio_id]['words'].append(item)

    # format each session with context
    formatted_results = []
    for audio_id, session in sessions.items():
        # sort all words by time offset
        all_words = sorted(session['words'], key=lambda x: x['time_offset'])

        # find all match words
        match_indices = [i for i, word in enumerate(all_words) if word.get('is_match', False)]

        if not match_indices:
            continue  # skip sessions with no matches

        start_time = session['start_time'].strftime('%Y-%m-%d %H:%M:%S')
        formatted_results.append(f"[{start_time}] Audio Match:")

        # group consecutive matches together
        match_groups = []
        current_group = [match_indices[0]]

        for i in range(1, len(match_indices)):
            # if matches are close together (within 10 words), group them
            if match_indices[i] - match_indices[i-1] <= 10:
                current_group.append(match_indices[i])
            else:
                match_groups.append(current_group)
                current_group = [match_indices[i]]
        match_groups.append(current_group)

        # process each match group
        for group in match_groups:
            first_match = group[0]
            last_match = group[-1]

            # ensure we have at least 'context' words before and after
            start_idx = max(0, first_match - context)
            end_idx = min(len(all_words), last_match + context + 1)

            # get the context words
            context_words = all_words[start_idx:end_idx]

            # format the context
            word_texts = []
            for word in context_words:
                if word.get('is_match', False):
                    # highlight match words
                    word_texts.append(f"{word['word']}")
                else:
                    word_texts.append(word['word'])

            context_text = " ".join(word_texts)

            # only add ellipsis if we actually truncated content
            prefix = "..." if start_idx > 0 else ""
            suffix = "..." if end_idx < len(all_words) else ""

            # add the context to the results
            formatted_results.append(f"  {prefix}{context_text}{suffix}")

        formatted_results.append("")  # empty line between sessions

    return "\n".join(formatted_results)


def estimate_timestamp_from_content_id(content_id, reference_date=None):
    """estimate a timestamp based on content id.

    args:
        content_id: the content id to estimate timestamp from
        reference_date: reference date to use (defaults to current date)

    returns:
        estimated datetime object or none if estimation fails
    """

    if not reference_date:
        reference_date = datetime.datetime.now()

    try:
        # convert content_id to int if it's not already
        content_id = int(content_id)

        # use a reference point for estimation
        # these values would need to be calibrated based on your system
        # assuming content ids are sequential and higher numbers are more recent

        # get current hour of day to make estimation more accurate
        current_hour = reference_date.hour

        # estimate based on content id ranges
        # adjust these ranges based on your system's content id patterns
        if content_id > 6000000:  # very recent (last few hours)
            hours_ago = min(5, current_hour)  # don't go before today
            return reference_date - datetime.timedelta(hours=hours_ago)
        elif content_id > 5000000:  # recent (today)
            hours_ago = min(12, current_hour)  # don't go before today
            return reference_date - datetime.timedelta(hours=hours_ago)
        elif content_id > 4000000:  # last few days
            return reference_date - datetime.timedelta(days=1)
        elif content_id > 3000000:  # last week
            return reference_date - datetime.timedelta(days=3)
        elif content_id > 2000000:  # last month
            return reference_date - datetime.timedelta(days=14)
        else:  # older
            return reference_date - datetime.timedelta(days=30)
    except:
        return None


def format_screen_results(results, use_utc=False):
    """format screen ocr search results.

    args:
        results: list of screen ocr dictionaries
        use_utc: whether to display times in UTC (default: False for local time)

    returns:
        formatted string representation of the results
    """

    if not results:
        return "no screen matches found."

    # format each result
    formatted_results = []
    seen_display_hashes = set()  # Track seen display combinations to avoid duplicates

    # create a database connection for looking up timestamps
    try:
        from rewinddb.config import get_db_path, get_db_password
        import pysqlcipher3.dbapi2 as sqlite3

        db_path = get_db_path()
        db_password = get_db_password()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # configure the connection for the encrypted database
        cursor.execute(f"PRAGMA key = '{db_password}'")
        cursor.execute("PRAGMA cipher_compatibility = 4")

        db_connection_available = True
    except Exception as e:
        db_connection_available = False

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
            # try to estimate timestamp from content_id if not available
            if not timestamp and 'content_id' in item and item['content_id']:
                estimated_timestamp = estimate_timestamp_from_content_id(item['content_id'])
                if estimated_timestamp:
                    timestamp = estimated_timestamp
                    item['frame_time'] = timestamp

            time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else "Unknown time"

            # get application and window info
            app_str = ""
            if 'application' in item and item['application'] and 'window' in item and item['window']:
                app_str = f"{item['application']} - {item['window']}"
            elif 'window_info' in item and item['window_info']:
                app_str = str(item['window_info'])
            else:
                app_str = "Unknown application"

            # create a display hash to avoid duplicate display lines
            # round timestamp to nearest minute for better deduplication
            if timestamp:
                rounded_time = timestamp.replace(second=0, microsecond=0)
                rounded_time_str = rounded_time.strftime('%Y-%m-%d %H:%M')
            else:
                rounded_time_str = "Unknown time"

            display_hash = f"{rounded_time_str}_{app_str}"

            # skip if we've already shown this exact timestamp/app combination
            if display_hash in seen_display_hashes:
                continue
            seen_display_hashes.add(display_hash)

            # add the formatted result
            formatted_results.append(f"[{time_str}] Screen Match in {app_str}")

            # add the text content with more context
            text_content = item['text']
            formatted_results.append(f"  Text: {text_content}")

            # construct recording path based on content ID
            if 'content_id' in item and item['content_id']:
                content_id = item['content_id']

                # Query the database to get the frame.createdAt for this content_id
                if db_connection_available:
                    try:
                        # Try to determine the date from the content ID itself
                        # Most recent content IDs are likely to be from the current date
                        current_date = datetime.datetime.now()
                        year_month = current_date.strftime("%Y%m")
                        day = current_date.strftime("%d")

                        # extract timestamp from content_id
                        # content ids are typically sequential and can be used to estimate time
                        # newer content ids are higher numbers
                        estimated_timestamp = None

                        # first try to query the frame table
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

                            # parse the timestamp
                            if isinstance(created_at, int):
                                # convert milliseconds to datetime
                                frame_time = datetime.datetime.fromtimestamp(created_at / 1000)
                                # update the item's timestamp
                                item['frame_time'] = frame_time
                                # update the time_str that will be displayed
                                time_str = frame_time.strftime('%Y-%m-%d %H:%M:%S')
                            else:
                                # parse iso format
                                try:
                                    frame_time = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%f")
                                except ValueError:
                                    frame_time = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S")
                                # update the item's timestamp
                                item['frame_time'] = frame_time
                                # update the time_str that will be displayed
                                time_str = frame_time.strftime('%Y-%m-%d %H:%M:%S')

                            # construct recording path
                            year_month = frame_time.strftime("%Y%m")
                            day = frame_time.strftime("%d")
                            recording_path = f"~/Library/Application Support/com.memoryvault.MemoryVault/chunks/{year_month}/{day}"

                            formatted_results.append(f"  Recording path: {recording_path}")
                            formatted_results.append(f"  Timestamp: {frame_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        else:
                            # if no direct match in frame table, try to use the content id to estimate the date
                            # check if the content id is in searchranking_content
                            cursor.execute("""
                                SELECT
                                    c1
                                FROM
                                    searchRanking_content
                                WHERE
                                    id = ?
                            """, (content_id,))

                            result = cursor.fetchone()
                            if result and result[0]:
                                # try to extract date from c1
                                timestamp_str = str(result[0])
                                if "UTC:" in timestamp_str:
                                    timestamp_parts = timestamp_str.split("UTC:")
                                    if len(timestamp_parts) > 0:
                                        date_part = timestamp_parts[0].strip()
                                        try:
                                            date_obj = datetime.datetime.strptime(date_part, "%a %b %d %I:%M:%S %p")
                                            # add current year
                                            date_obj = date_obj.replace(year=current_date.year)

                                            # update the item's timestamp
                                            item['frame_time'] = date_obj
                                            # update the time_str that will be displayed
                                            time_str = date_obj.strftime('%Y-%m-%d %H:%M:%S')

                                            # construct recording path
                                            year_month = date_obj.strftime("%Y%m")
                                            day = date_obj.strftime("%d")
                                            recording_path = f"~/Library/Application Support/com.memoryvault.MemoryVault/chunks/{year_month}/{day}"

                                            formatted_results.append(f"  Recording path: {recording_path}")
                                            formatted_results.append(f"  Timestamp (estimated): {date_obj.strftime('%Y-%m-%d %H:%M:%S')}")
                                        except Exception as e:
                                            # use current date as fallback
                                            # estimate timestamp from content id
                                            estimated_timestamp = estimate_timestamp_from_content_id(content_id, current_date)
                                            if estimated_timestamp:
                                                item['frame_time'] = estimated_timestamp
                                                time_str = estimated_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                                                year_month = estimated_timestamp.strftime("%Y%m")
                                                day = estimated_timestamp.strftime("%d")
                                            else:
                                                year_month = current_date.strftime("%Y%m")
                                                day = current_date.strftime("%d")

                                            recording_path = f"~/Library/Application Support/com.memoryvault.MemoryVault/chunks/{year_month}/{day}"
                                            formatted_results.append(f"  Recording path (estimated): {recording_path}")
                                            formatted_results.append(f"  Content ID: {content_id}")
                                    else:
                                        # estimate timestamp from content id
                                        estimated_timestamp = estimate_timestamp_from_content_id(content_id, current_date)
                                        if estimated_timestamp:
                                            item['frame_time'] = estimated_timestamp
                                            time_str = estimated_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                                            year_month = estimated_timestamp.strftime("%Y%m")
                                            day = estimated_timestamp.strftime("%d")
                                        else:
                                            year_month = current_date.strftime("%Y%m")
                                            day = current_date.strftime("%d")

                                        recording_path = f"~/Library/Application Support/com.memoryvault.MemoryVault/chunks/{year_month}/{day}"
                                        formatted_results.append(f"  Recording path (estimated): {recording_path}")
                                        formatted_results.append(f"  Content ID: {content_id}")
                                else:
                                    # estimate timestamp from content id
                                    estimated_timestamp = estimate_timestamp_from_content_id(content_id, current_date)
                                    if estimated_timestamp:
                                        item['frame_time'] = estimated_timestamp
                                        time_str = estimated_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                                        year_month = estimated_timestamp.strftime("%Y%m")
                                        day = estimated_timestamp.strftime("%d")
                                    else:
                                        year_month = current_date.strftime("%Y%m")
                                        day = current_date.strftime("%d")

                                    recording_path = f"~/Library/Application Support/com.memoryvault.MemoryVault/chunks/{year_month}/{day}"
                                    formatted_results.append(f"  Recording path (estimated): {recording_path}")
                                    formatted_results.append(f"  Content ID: {content_id}")
                            else:
                                # estimate timestamp from content id
                                estimated_timestamp = estimate_timestamp_from_content_id(content_id, current_date)
                                if estimated_timestamp:
                                    item['frame_time'] = estimated_timestamp
                                    time_str = estimated_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                                    year_month = estimated_timestamp.strftime("%Y%m")
                                    day = estimated_timestamp.strftime("%d")
                                else:
                                    year_month = current_date.strftime("%Y%m")
                                    day = current_date.strftime("%d")

                                recording_path = f"~/Library/Application Support/com.memoryvault.MemoryVault/chunks/{year_month}/{day}"
                                formatted_results.append(f"  Recording path (estimated): {recording_path}")
                                formatted_results.append(f"  Content ID: {content_id}")
                    except Exception as e:
                        # fallback if there's an error
                        # estimate timestamp from content id
                        estimated_timestamp = estimate_timestamp_from_content_id(content_id, current_date)
                        if estimated_timestamp:
                            item['frame_time'] = estimated_timestamp
                            time_str = estimated_timestamp.strftime('%Y-%m-%d %H:%M:%S')

                        formatted_results.append(f"  Content ID: {content_id}")
                        formatted_results.append(f"  Note: error retrieving frame timestamp: {str(e)}")
                else:
                    # If database connection is not available
                    formatted_results.append(f"  Content ID: {content_id}")
                    formatted_results.append("  Note: Database connection not available for timestamp lookup")

            formatted_results.append("")  # empty line between results

        # handle results from traditional search
        elif 'frame_id' in item:
            # try to get timestamp from frame_time
            if 'frame_time' in item and item['frame_time']:
                time_str = item['frame_time'].strftime('%Y-%m-%d %H:%M:%S')
            else:
                # try to estimate timestamp from frame_id
                estimated_timestamp = estimate_timestamp_from_content_id(item['frame_id'])
                if estimated_timestamp:
                    item['frame_time'] = estimated_timestamp
                    time_str = estimated_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    time_str = "Unknown time"

            app_str = "Unknown application"
            if 'application' in item and item['application'] and 'window' in item and item['window']:
                app_str = f"{item['application']} - {item['window']}"

            # create a display hash to avoid duplicate display lines
            # round timestamp to nearest minute for better deduplication
            if 'frame_time' in item and item['frame_time']:
                rounded_time = item['frame_time'].replace(second=0, microsecond=0)
                rounded_time_str = rounded_time.strftime('%Y-%m-%d %H:%M')
            else:
                rounded_time_str = "Unknown time"

            display_hash = f"{rounded_time_str}_{app_str}"

            # skip if we've already shown this exact timestamp/app combination
            if display_hash in seen_display_hashes:
                continue
            seen_display_hashes.add(display_hash)

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

    # Close the database connection if it was opened
    if db_connection_available:
        conn.close()

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
  %(prog)s "project" --from "13:00" --to "17:00"  # uses today's date, HH:MM format
  %(prog)s "presentation" --relative "1 day"
  %(prog)s "meeting" --relative "5h"
  %(prog)s "code" --relative "3m"
  %(prog)s "project" --relative "10d"
  %(prog)s "design" --relative "2w"
  %(prog)s "python" --context 5 --debug
  %(prog)s "meeting" --env-file /path/to/.env
  %(prog)s "meeting" --utc  # display times in UTC instead of local time
  %(prog)s "code" --audio  # search only in audio transcripts
  %(prog)s "menu" --visual  # search only in screen OCR data
"""
    )

    parser.add_argument("keyword", help="keyword to search for")

    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument("-r", "--relative", metavar="TIME", help="relative time period (e.g., '1 hour', '5h', '3m', '10d', '2w')")
    time_group.add_argument("--from", dest="from_time", metavar="DATETIME",
                           help="start time in format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'HH:MM:SS', or 'HH:MM' (uses today's date)")

    parser.add_argument("--to", dest="to_time", metavar="DATETIME",
                       help="end time in format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'HH:MM:SS', or 'HH:MM' (uses today's date)")
    parser.add_argument("--context", type=int, default=100,
                       help="number of words to show before/after audio hits (default: 100)")
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    parser.add_argument("--env-file", metavar="FILE", help="path to .env file with database configuration")
    parser.add_argument("--utc", action="store_true", help="display times in UTC instead of local time")

    # Add source filter options
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--audio", action="store_true", help="search only in audio transcripts")
    source_group.add_argument("--visual", action="store_true", help="search only in screen OCR data")

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

            # Filter results based on source options
            if args.audio:
                screen_results = []  # Only show audio results
            elif args.visual:
                audio_results = []  # Only show visual results

            # Convert timestamps to local time if not using UTC
            if not args.utc:
                # Convert audio timestamps
                for item in audio_results:
                    if 'absolute_time' in item:
                        item['absolute_time'] = convert_to_local_time(item['absolute_time'])
                    if 'audio_start_time' in item:
                        item['audio_start_time'] = convert_to_local_time(item['audio_start_time'])

                # Convert screen timestamps
                for item in screen_results:
                    if 'frame_time' in item:
                        item['frame_time'] = convert_to_local_time(item['frame_time'])

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
            formatted_audio = format_audio_results(audio_results, args.context, args.utc)
            print(formatted_audio)

            # display screen results
            print("\nscreen matches:")
            formatted_screen = format_screen_results(screen_results, args.utc)
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