"""
example usage of the rewinddb library.
"""

import datetime
import logging
import sys
import os
import rewinddb
import rewinddb.utils

# configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def main():
    """demonstrate basic usage of the rewinddb library."""

    # check if .env file exists
    if not os.path.exists(".env"):
        logger.warning("no .env file found in current directory")
        logger.info("checking for default configuration...")

    try:
        # connect to the database with explicit error handling
        logger.info("connecting to rewind database...")
        with rewinddb.RewindDB() as db:
            logger.info("successfully connected to rewind database")

            try:
                # get audio transcripts from the last day
                logger.info("fetching audio transcripts from the last day...")
                transcripts = db.get_audio_transcripts_relative(days=1)
                logger.info(f"found {len(transcripts)} transcript words")

                # format and display some transcript data
                if transcripts:
                    formatted = rewinddb.utils.format_transcript(transcripts[:100])
                    print("\nsample transcript:")
                    print(formatted)
                else:
                    logger.info("no transcript data found in the last day")

                # get screen ocr data from the last hour
                logger.info("fetching screen ocr data from the last hour...")
                ocr_data = db.get_screen_ocr_relative(hours=1)
                logger.info(f"found {len(ocr_data)} ocr text elements")

                # format and display some ocr data
                if ocr_data:
                    formatted = rewinddb.utils.format_ocr_data(ocr_data[:20])
                    print("\nsample ocr data:")
                    print(formatted)
                else:
                    logger.info("no ocr data found in the last hour")

                # search for a keyword
                logger.info("searching for 'python'...")
                search_results = db.search("python", days=7)
                logger.info(f"found {len(search_results['audio'])} audio matches and "
                          f"{len(search_results['screen'])} screen matches")

                # get application usage segments from yesterday
                yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
                yesterday_start = datetime.datetime(
                    yesterday.year, yesterday.month, yesterday.day, 0, 0, 0
                )
                yesterday_end = datetime.datetime(
                    yesterday.year, yesterday.month, yesterday.day, 23, 59, 59
                )

                logger.info(f"fetching application usage from {yesterday_start.date()}...")
                segments = db.get_segments(yesterday_start, yesterday_end)
                logger.info(f"found {len(segments)} application segments")

                # show top applications by usage time
                if segments:
                    app_usage = {}
                    for segment in segments:
                        app = segment['application']
                        duration = segment['duration_seconds']
                        if app in app_usage:
                            app_usage[app] += duration
                        else:
                            app_usage[app] = duration

                    print("\ntop applications by usage time:")
                    for app, duration in sorted(app_usage.items(),
                                              key=lambda x: x[1], reverse=True)[:5]:
                        hours = duration / 3600
                        print(f"  {app}: {hours:.2f} hours")
                else:
                    logger.info("no application segments found for yesterday")

            except Exception as e:
                logger.error(f"error while querying database: {e}")

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