#!/usr/bin/env python3
"""
stats_cli.py - command line tool to display statistics about rewind.ai data.

this script provides statistics about audio transcripts, screen ocr data,
application usage, and other metrics from the rewind.ai database.
"""

import argparse
import json
import logging
import sys
import time
from tabulate import tabulate
import rewinddb

# configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def display_stats(stats):
    """display collected statistics in a formatted way.

    formats and prints the collected statistics to the console.

    args:
        stats: dictionary with comprehensive statistics
    """
    audio_stats = stats['audio']
    screen_stats = stats['screen']
    app_stats = stats['app_usage']
    db_stats = stats['database']

    print("\n" + "=" * 80)
    print(" REWIND.AI DATABASE STATISTICS ")
    print("=" * 80)

    # database overview
    print("\n📊 DATABASE OVERVIEW")
    print(f"Database Size: {db_stats['db_size_mb']} MB")
    print(f"Number of Tables: {db_stats['table_count']}")
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
        earliest_date_str = earliest_date.strftime("%Y-%m-%d %H:%M:%S")
    else:
        earliest_date_str = "No data"
    print(f"Earliest Record: {earliest_date_str}")
    print(f"Total Audio Recordings: {audio_stats['total_audio']}")
    print(f"Total Transcript Words: {audio_stats['total_words']}")

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
        earliest_date_str = earliest_date.strftime("%Y-%m-%d %H:%M:%S")
    else:
        earliest_date_str = "No data"
    print(f"Earliest Record: {earliest_date_str}")
    print(f"Total Frames: {screen_stats['total_frames']}")
    print(f"Total OCR Nodes: {screen_stats['total_nodes']}")

    screen_table = [
        ["Past Hour", screen_stats['hour_count']],
        ["Past Day", screen_stats['day_count']],
        ["Past Week", screen_stats['week_count']],
        ["Past Month", screen_stats['month_count']]
    ]
    print("\nOCR Elements by Time Period:")
    print(tabulate(screen_table, headers=["Time Period", "Element Count"], tablefmt="simple"))

    # app usage statistics
    print("\n💻 APPLICATION USAGE STATISTICS (Past Week)")
    print(f"Total Applications: {app_stats['total_apps']}")
    print(f"Total Usage Time: {app_stats['total_hours']} hours")

    app_table = []
    for app in app_stats['top_apps']:
        app_table.append([app['app'], app['hours'], f"{app['percentage']}%"])

    print("\nTop 10 Applications by Usage Time:")
    print(tabulate(app_table, headers=["Application", "Hours", "Percentage"], tablefmt="simple"))

    # table statistics
    print("\n📋 TABLE RECORD COUNTS")
    table_table = []
    for table in db_stats['table_stats'][:10]:  # show top 10 tables
        table_table.append([table['table'], table['records']])

    print(tabulate(table_table, headers=["Table", "Records"], tablefmt="simple"))
    print("\n" + "=" * 80)


def main():
    """main function to run the stats cli."""
    parser = argparse.ArgumentParser(description="display statistics about rewind.ai data")
    parser.add_argument("--env", help="path to .env file with database configuration")
    parser.add_argument("--json", action="store_true", help="output statistics as JSON")
    args = parser.parse_args()

    try:
        # connect to the database
        logger.info("connecting to rewind database...")
        start_time = time.time()

        db = rewinddb.RewindDB(args.env)

        # collect statistics using the rewinddb module
        logger.info("collecting statistics...")
        stats = db.get_statistics()

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
            display_stats(stats)

        # close the database connection
        db.close()

        elapsed_time = time.time() - start_time
        logger.info(f"statistics collection completed in {elapsed_time:.2f} seconds")

    except FileNotFoundError as e:
        logger.error(f"database file not found: {e}")
        logger.info("check your DB_PATH setting in .env file")
        sys.exit(1)
    except ConnectionError as e:
        logger.error(f"database connection error: {e}")
        logger.info("check your DB_PASSWORD setting in .env file")
        sys.exit(1)
    except Exception as e:
        logger.error(f"unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()