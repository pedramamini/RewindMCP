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
import os
import shutil
from pathlib import Path

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


def get_transcripts_relative(db, time_str, speech_source=None):
    """get audio transcripts from a relative time period.

    args:
        db: rewinddb instance
        time_str: relative time string (e.g., "1 hour", "5 hours")
        speech_source: optional filter for speech source ('me' for user voice, 'others' for other speakers)

    returns:
        list of transcript dictionaries
    """

    try:
        time_components = parse_relative_time(time_str)
        return db.get_audio_transcripts_relative(speech_source=speech_source, **time_components)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


def get_transcripts_absolute(db, from_time_str, to_time_str, speech_source=None):
    """get audio transcripts from a specific time range.

    args:
        db: rewinddb instance
        from_time_str: start time string in format "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM", "YYYY-MM-DD", "HH:MM:SS", or "HH:MM"
        to_time_str: end time string in format "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM", "YYYY-MM-DD", "HH:MM:SS", or "HH:MM"
        speech_source: optional filter for speech source ('me' for user voice, 'others' for other speakers)

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

        return db.get_audio_transcripts_absolute(from_time, to_time, speech_source)
    except ValueError as e:
        print(f"error: invalid time format. use format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD', 'HH:MM:SS', or 'HH:MM'.", file=sys.stderr)
        sys.exit(1)


def export_own_voice_by_day(db, from_time_str, to_time_str, format_type='text'):
    """export user's own voice transcripts organized by day.

    args:
        db: rewinddb instance
        from_time_str: start time string
        to_time_str: end time string
        format_type: 'text' for text output, 'audio' for audio file export (future)

    returns:
        dictionary with dates as keys and formatted output as values
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

        # get own voice transcripts organized by day
        transcripts_by_day = db.get_own_voice_transcripts_by_day(from_time, to_time)
        
        return transcripts_by_day
    except ValueError as e:
        print(f"error: invalid time format. use format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD', 'HH:MM:SS', or 'HH:MM'.", file=sys.stderr)
        sys.exit(1)


def format_own_voice_export(transcripts_by_day, format_type='text'):
    """format own voice transcripts for export.

    args:
        transcripts_by_day: dictionary with dates as keys and transcript lists as values
        format_type: 'text' for text output, 'json' for JSON output

    returns:
        formatted string for export
    """
    if format_type == 'json':
        import json
        export_data = {}
        for date, transcripts in sorted(transcripts_by_day.items()):
            words = [t['word'] for t in transcripts]
            export_data[date] = {
                'word_count': len(words),
                'text': ' '.join(words),
                'words': words
            }
        return json.dumps(export_data, indent=2, default=str)
    
    else:  # text format
        output_lines = []
        total_words = 0
        
        for date in sorted(transcripts_by_day.keys()):
            transcripts = transcripts_by_day[date]
            words = [t['word'] for t in transcripts]
            word_count = len(words)
            total_words += word_count
            
            output_lines.append(f"\n=== {date} ===")
            output_lines.append(f"Word count: {word_count}")
            output_lines.append("")
            
            # join words into readable text
            text = ' '.join(words)
            output_lines.append(text)
            output_lines.append("")
        
        output_lines.insert(0, f"Own Voice Export - Total words: {total_words}")
        output_lines.insert(1, f"Date range: {min(transcripts_by_day.keys())} to {max(transcripts_by_day.keys())}")
        output_lines.insert(2, "=" * 50)
        
        return '\n'.join(output_lines)


def export_own_voice_audio(transcripts_by_day, output_dir):
    """export audio files for own voice transcripts.

    args:
        transcripts_by_day: dictionary with dates as keys and transcript lists as values
        output_dir: directory to save audio files

    returns:
        summary of exported files
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    exported_files = []
    skipped_files = []
    total_copied = 0
    
    # group transcripts by audio file to avoid duplicates
    audio_files_by_day = {}
    
    for date, transcripts in transcripts_by_day.items():
        audio_files_by_day[date] = {}
        for transcript in transcripts:
            audio_path = transcript.get('audio_path')
            if audio_path and os.path.exists(audio_path):
                audio_id = transcript['audio_id']
                if audio_id not in audio_files_by_day[date]:
                    audio_files_by_day[date][audio_id] = {
                        'path': audio_path,
                        'audio_start_time': transcript['audio_start_time'],
                        'duration': transcript['audio_duration'],
                        'words': []
                    }
                audio_files_by_day[date][audio_id]['words'].append(transcript['word'])
    
    # export files organized by day
    for date, audio_files in audio_files_by_day.items():
        day_dir = output_path / date
        day_dir.mkdir(exist_ok=True)
        
        # create summary file for the day
        day_summary = []
        day_summary.append(f"Voice Export Summary for {date}")
        day_summary.append("=" * 40)
        day_summary.append("")
        
        for audio_id, info in audio_files.items():
            src_path = info['path']
            if not os.path.exists(src_path):
                skipped_files.append(f"{date}/{audio_id} - file not found")
                continue
            
            # create descriptive filename
            time_str = info['audio_start_time'].strftime("%H%M%S")
            word_count = len(info['words'])
            filename = f"{time_str}_audio{audio_id}_{word_count}words.m4a"
            dest_path = day_dir / filename
            
            try:
                shutil.copy2(src_path, dest_path)
                file_size = os.path.getsize(dest_path) / 1024 / 1024  # MB
                
                exported_files.append(str(dest_path))
                total_copied += 1
                
                # add to summary
                transcript_text = ' '.join(info['words'][:20])  # first 20 words
                if len(info['words']) > 20:
                    transcript_text += "..."
                
                day_summary.append(f"File: {filename}")
                day_summary.append(f"  Size: {file_size:.1f} MB")
                day_summary.append(f"  Duration: {info['duration']/1000:.1f} seconds")
                day_summary.append(f"  Words: {word_count}")
                day_summary.append(f"  Preview: {transcript_text}")
                day_summary.append("")
                
            except Exception as e:
                skipped_files.append(f"{date}/{audio_id} - copy error: {e}")
        
        # save day summary
        summary_file = day_dir / "transcript_summary.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(day_summary))
    
    # create overall summary
    overall_summary = []
    overall_summary.append("Own Voice Audio Export Summary")
    overall_summary.append("=" * 50)
    overall_summary.append(f"Total files exported: {total_copied}")
    overall_summary.append(f"Total files skipped: {len(skipped_files)}")
    overall_summary.append(f"Export directory: {output_path.absolute()}")
    overall_summary.append("")
    
    if skipped_files:
        overall_summary.append("Skipped files:")
        for skipped in skipped_files:
            overall_summary.append(f"  - {skipped}")
        overall_summary.append("")
    
    overall_summary.append("Exported files by day:")
    for date in sorted(audio_files_by_day.keys()):
        count = len([f for f in exported_files if f"/{date}/" in f])
        overall_summary.append(f"  {date}: {count} files")
    
    return {
        'exported_files': exported_files,
        'skipped_files': skipped_files,
        'total_copied': total_copied,
        'summary': '\n'.join(overall_summary)
    }


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
  %(prog)s --relative "1 hour" --speech-source me  # filter for own voice only
  %(prog)s --relative "1 day" --speech-source others  # filter for other speakers
  %(prog)s --export-own-voice "2025-01-01 to 2025-01-31"  # export own voice by day
  %(prog)s --export-own-voice "2025-01-01 to 2025-01-31" --export-format json --save-to my_voice.json
  %(prog)s --export-own-voice "2025-01-01 to 2025-01-31" --export-format audio --audio-export-dir ./my_voice_audio
"""
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-r", "--relative", metavar="TIME", help="relative time period (e.g., '1 hour', '5h', '3m', '10d', '2w')")
    group.add_argument("--from", dest="from_time", metavar="DATETIME",
                       help="start time in format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD' (uses 00:00:00), 'HH:MM:SS', or 'HH:MM' (uses today's date)")
    group.add_argument("--export-own-voice", dest="export_own_voice", metavar="DATERANGE",
                       help="export own voice transcripts by day in format 'YYYY-MM-DD to YYYY-MM-DD' (e.g., '2025-01-01 to 2025-01-31')")

    parser.add_argument("--to", dest="to_time", metavar="DATETIME",
                       help="end time in format 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD' (uses 23:59:59), 'HH:MM:SS', or 'HH:MM' (uses today's date)")
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    parser.add_argument("--env-file", metavar="FILE", help="path to .env file with database configuration")
    parser.add_argument("--utc", action="store_true", help="display times in UTC instead of local time")
    parser.add_argument("--speech-source", choices=['me', 'others'], help="filter by speech source ('me' for own voice, 'others' for other speakers)")
    parser.add_argument("--export-format", choices=['text', 'json', 'audio'], default='text', help="export format for own voice (default: text)")
    parser.add_argument("--save-to", metavar="FILE", help="save export output to file instead of displaying")
    parser.add_argument("--audio-export-dir", metavar="DIR", help="directory to export audio files (required when --export-format audio)")

    args = parser.parse_args()

    # validate that if --from is provided, --to is also provided
    if args.from_time and not args.to_time:
        parser.error("--to is required when --from is provided")
    
    # validate export-own-voice format
    if args.export_own_voice:
        if " to " not in args.export_own_voice:
            parser.error("--export-own-voice must be in format 'YYYY-MM-DD to YYYY-MM-DD'")
        try:
            parts = args.export_own_voice.split(" to ")
            if len(parts) != 2:
                raise ValueError()
            # validate date format
            for part in parts:
                datetime.datetime.strptime(part.strip(), "%Y-%m-%d")
        except ValueError:
            parser.error("--export-own-voice dates must be in format 'YYYY-MM-DD to YYYY-MM-DD'")
    
    # validate audio export requirements
    if args.export_format == 'audio':
        if not args.export_own_voice:
            parser.error("--export-format audio can only be used with --export-own-voice")
        if not args.audio_export_dir:
            parser.error("--audio-export-dir is required when --export-format is audio")

    return args


# No replacement needed - removing the DirectSqliteAccess class


def main():
    """main function for the transcript cli tool."""

    args = parse_arguments()

    try:
        # connect to the database using rewinddb library
        print("connecting to rewind database...")
        with rewinddb.RewindDB(args.env_file) as db:
            # handle export own voice mode
            if args.export_own_voice:
                parts = args.export_own_voice.split(" to ")
                from_date = parts[0].strip()
                to_date = parts[1].strip()
                
                print(f"exporting own voice transcripts from {from_date} to {to_date}...")
                transcripts_by_day = export_own_voice_by_day(db, from_date, to_date)
                
                if not transcripts_by_day:
                    print("no own voice transcripts found for the specified date range.")
                    return
                
                # handle different export formats
                if args.export_format == 'audio':
                    # export audio files
                    print("exporting audio files...")
                    export_result = export_own_voice_audio(transcripts_by_day, args.audio_export_dir)
                    
                    print(export_result['summary'])
                    
                    # also save text summary if requested
                    if args.save_to:
                        formatted_output = format_own_voice_export(transcripts_by_day, 'text')
                        with open(args.save_to, 'w', encoding='utf-8') as f:
                            f.write(formatted_output)
                        print(f"\ntext summary also saved to {args.save_to}")
                else:
                    # format text/json output
                    formatted_output = format_own_voice_export(transcripts_by_day, args.export_format)
                    
                    # save to file or display
                    if args.save_to:
                        with open(args.save_to, 'w', encoding='utf-8') as f:
                            f.write(formatted_output)
                        print(f"own voice transcripts exported to {args.save_to}")
                        
                        # show summary
                        total_days = len(transcripts_by_day)
                        total_words = sum(len(transcripts) for transcripts in transcripts_by_day.values())
                        print(f"exported {total_words} words across {total_days} days")
                    else:
                        print(formatted_output)
                
                return
            
            # handle regular transcript retrieval
            speech_source = args.speech_source
            
            # get transcripts based on the specified time range
            if args.relative:
                source_msg = f" (speech source: {speech_source})" if speech_source else ""
                print(f"retrieving transcripts from the last {args.relative}{source_msg}...")
                transcripts = get_transcripts_relative(db, args.relative, speech_source)
            else:
                source_msg = f" (speech source: {speech_source})" if speech_source else ""
                print(f"retrieving transcripts from {args.from_time} to {args.to_time}{source_msg}...")
                transcripts = get_transcripts_absolute(db, args.from_time, args.to_time, speech_source)

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

