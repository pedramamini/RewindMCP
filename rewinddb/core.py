"""
core module containing the main rewinddb class for interfacing with the rewind.ai database.

this module provides the rewinddb class which handles connection to the encrypted
sqlite database and implements methods for querying audio transcripts, screen ocr data,
and searching across both data types.
"""

import os
import time
import datetime
import typing
import logging
import pysqlcipher3.dbapi2 as sqlite3
from rewinddb.config import get_db_path, get_db_password

# configure logging
log_level = logging.INFO if os.environ.get('DEBUG') == '1' else logging.CRITICAL
logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RewindDB:
    """main class for interfacing with the rewind.ai sqlite database.

    this class handles connection to the encrypted sqlite database and provides
    methods to query audio transcripts, screen ocr data, and search functionality.
    the database path and password are hardcoded based on standard locations.
    """

    def __init__(self, env_file: typing.Optional[str] = None) -> None:
        """initialize the rewinddb connection.

        connects to the encrypted sqlite database using configuration from .env file.
        raises an exception if the database cannot be accessed.

        args:
            env_file: optional path to a .env file to load configuration from
        """

        # load database configuration
        self.db_path = get_db_path(env_file)
        self.db_password = get_db_password(env_file)

        # verify the database file exists
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"rewind database not found at {self.db_path}")

        # connect to the database
        self._connect()

    def _connect(self) -> None:
        """establish connection to the encrypted sqlite database.

        uses the pysqlcipher3 library to connect to the encrypted database.
        sets up the connection and cursor objects for use by other methods.
        """
        logger.info(f"connecting to database at {self.db_path}")

        try:
            # connect to the database using pysqlcipher3
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()

            # configure the connection for the encrypted database
            # note: sqlcipher requires the key to be set before any other operations
            self.cursor.execute(f"PRAGMA key = '{self.db_password}'")
            self.cursor.execute("PRAGMA cipher_compatibility = 4")  # ensure sqlcipher v4 compatibility

            # test the connection
            try:
                logger.debug("testing database connection")
                self.cursor.execute("SELECT count(*) FROM sqlite_master")
                result = self.cursor.fetchone()
                logger.info(f"database connection successful, found {result[0]} tables")
            except sqlite3.DatabaseError as e:
                logger.error(f"failed to query database: {e}")
                self.close()  # ensure connection is closed on error
                raise ConnectionError(f"failed to connect to rewind database (invalid password?): {e}")

        except Exception as e:
            logger.error(f"unexpected error connecting to database: {e}")
            raise ConnectionError(f"failed to connect to rewind database: {e}")

    def close(self) -> None:
        """close the database connection.

        properly closes the connection to the database.
        should be called when done using the database.
        """

        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    def get_audio_transcripts_absolute(self, start_time: datetime.datetime,
                                      end_time: datetime.datetime) -> typing.List[dict]:
        """retrieve audio transcripts within an absolute time range.

        queries the audio and transcript_word tables to get transcribed words
        within the specified absolute time range.

        args:
            start_time: the start datetime to query from
            end_time: the end datetime to query to

        returns:
            a list of dictionaries containing transcript data
        """

        # Try both timestamp formats
        try:
            # First try with millisecond timestamps
            start_timestamp = int(start_time.timestamp() * 1000)  # convert to milliseconds
            end_timestamp = int(end_time.timestamp() * 1000)  # convert to milliseconds

            query = """
            SELECT
                a.id as audio_id,
                a.startTime as start_time,
                a.duration,
                tw.id as word_id,
                tw.word,
                tw.timeOffset as time_offset,
                tw.duration
            FROM
                audio a
            JOIN
                transcript_word tw ON a.segmentId = tw.segmentId
            WHERE
                a.startTime + tw.timeOffset BETWEEN ? AND ?
            ORDER BY
                a.startTime, tw.timeOffset
            """

            self.cursor.execute(query, (start_timestamp, end_timestamp))
            rows = self.cursor.fetchall()

            # If no results, try with string-formatted timestamps
            if not rows:
                # Format timestamps as strings
                start_timestamp = start_time.strftime("%Y-%m-%dT%H:%M:%S.000")
                end_timestamp = end_time.strftime("%Y-%m-%dT%H:%M:%S.999")

                query = """
                SELECT
                    a.id as audio_id,
                    a.startTime as start_time,
                    a.duration,
                    tw.id as word_id,
                    tw.word,
                    tw.timeOffset as time_offset,
                    tw.duration
                FROM
                    audio a
                JOIN
                    transcript_word tw ON a.segmentId = tw.segmentId
                WHERE
                    a.startTime BETWEEN ? AND ?
                ORDER BY
                    a.startTime, tw.timeOffset
                """

                self.cursor.execute(query, (start_timestamp, end_timestamp))
                rows = self.cursor.fetchall()

            results = []
            for row in rows:
                # Check if the timestamp is a string or an integer
                if isinstance(row[1], str):
                    # Parse the timestamp from the text format
                    try:
                        start_time_dt = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        # Try without microseconds
                        start_time_dt = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S")

                    absolute_time = start_time_dt + datetime.timedelta(milliseconds=row[5])
                else:
                    # Use the existing _ms_to_datetime method
                    start_time_dt = self._ms_to_datetime(row[1])
                    absolute_time = self._ms_to_datetime(row[1] + row[5])

                results.append({
                    'audio_id': row[0],
                    'audio_start_time': start_time_dt,
                    'audio_duration': row[2],
                    'word_id': row[3],
                    'word': row[4],
                    'time_offset': row[5],
                    'duration': row[6],  # using duration instead of confidence
                    'absolute_time': absolute_time
                })

            return results

        except Exception as e:
            logger.error(f"Error in get_audio_transcripts_absolute: {e}")
            return []

    def get_audio_transcripts_relative(self, days: int = 0, hours: int = 0,
                                      minutes: int = 0, seconds: int = 0) -> typing.List[dict]:
        """retrieve audio transcripts from a relative time period.

        queries audio transcripts from a time period relative to now.

        args:
            days: number of days to look back
            hours: number of hours to look back
            minutes: number of minutes to look back
            seconds: number of seconds to look back

        returns:
            a list of dictionaries containing transcript data
        """

        # Use UTC timezone to be consistent with get_statistics
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = datetime.timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        start_time = now - delta

        return self.get_audio_transcripts_absolute(start_time, now)

    def get_screen_ocr_absolute(self, start_time: datetime.datetime,
                               end_time: datetime.datetime) -> typing.List[dict]:
        """retrieve screen ocr data within an absolute time range.

        queries the frame and node tables to get text elements extracted from
        screen captures within the specified absolute time range.

        args:
            start_time: the start datetime to query from
            end_time: the end datetime to query to

        returns:
            a list of dictionaries containing ocr data
        """

        # Try both timestamp formats
        try:
            # First try with millisecond timestamps
            start_timestamp = int(start_time.timestamp() * 1000)  # convert to milliseconds
            end_timestamp = int(end_time.timestamp() * 1000)  # convert to milliseconds

            query = """
            SELECT
                f.id as frame_id,
                f.createdAt as created_at,
                f.segmentId as segment_id,
                n.id as node_id,
                n.textOffset,
                n.textLength,
                s.bundleID as app_name,
                s.windowName as window_name
            FROM
                frame f
            JOIN
                node n ON f.id = n.frameId
            JOIN
                segment s ON f.segmentId = s.id
            WHERE
                f.createdAt BETWEEN ? AND ?
            ORDER BY
                f.createdAt
            """

            self.cursor.execute(query, (start_timestamp, end_timestamp))
            rows = self.cursor.fetchall()

            # If no results, try with string-formatted timestamps
            if not rows:
                # Format timestamps as strings
                start_timestamp = start_time.strftime("%Y-%m-%dT%H:%M:%S.000")
                end_timestamp = end_time.strftime("%Y-%m-%dT%H:%M:%S.999")

                query = """
                SELECT
                    f.id as frame_id,
                    f.createdAt as created_at,
                    f.segmentId as segment_id,
                    n.id as node_id,
                    n.textOffset,
                    n.textLength,
                    s.bundleID as app_name,
                    s.windowName as window_name
                FROM
                    frame f
                JOIN
                    node n ON f.id = n.frameId
                JOIN
                    segment s ON f.segmentId = s.id
                WHERE
                    f.createdAt BETWEEN ? AND ?
                ORDER BY
                    f.createdAt
                """

                self.cursor.execute(query, (start_timestamp, end_timestamp))
                rows = self.cursor.fetchall()

            results = []
            for row in rows:
                # Check if the timestamp is a string or an integer
                if isinstance(row[1], str):
                    # Parse the timestamp from the text format
                    try:
                        frame_time = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        # Try without microseconds
                        frame_time = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S")
                else:
                    # Use the existing _ms_to_datetime method
                    frame_time = self._ms_to_datetime(row[1])

                results.append({
                    'frame_id': row[0],
                    'frame_time': frame_time,
                    'segment_id': row[2],
                    'node_id': row[3],
                    'text_offset': row[4],
                    'text_length': row[5],
                    'application': row[6],
                    'window': row[7]
                })

            return results

        except Exception as e:
            logger.error(f"Error in get_screen_ocr_absolute: {e}")
            return []

    def get_screen_ocr_relative(self, days: int = 0, hours: int = 0,
                               minutes: int = 0, seconds: int = 0) -> typing.List[dict]:
        """retrieve screen ocr data from a relative time period.

        queries screen ocr data from a time period relative to now.

        args:
            days: number of days to look back
            hours: number of hours to look back
            minutes: number of minutes to look back
            seconds: number of seconds to look back

        returns:
            a list of dictionaries containing ocr data
        """

        # Use UTC timezone to be consistent with get_statistics
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = datetime.timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        start_time = now - delta

        return self.get_screen_ocr_absolute(start_time, now)

    def search(self, query: str, days: int = 7) -> typing.Dict[str, typing.List[dict]]:
        """search for keywords across both audio and screen data.

        performs a search for the given query string across both audio transcripts
        and screen ocr data from the specified number of days back.

        args:
            query: the search string to look for
            days: number of days to look back (default: 7)

        returns:
            a dictionary with 'audio' and 'screen' keys containing matching results
        """

        # Use UTC timezone to be consistent with get_statistics
        now = datetime.datetime.now(datetime.timezone.utc)
        start_time = now - datetime.timedelta(days=days)

        # search in audio transcripts
        # Try both timestamp formats (milliseconds and ISO string)
        start_timestamp_ms = int(start_time.timestamp() * 1000)
        end_timestamp_ms = int(now.timestamp() * 1000)
        start_timestamp_str = start_time.strftime("%Y-%m-%dT%H:%M:%S.000")
        end_timestamp_str = now.strftime("%Y-%m-%dT%H:%M:%S.999")
        search_term = query.lower()

        # first find all matching words
        # first try with millisecond timestamps
        audio_query = """
        SELECT
            a.id as audio_id,
            a.startTime as start_time,
            a.duration,
            a.segmentId as segment_id,
            tw.id as word_id,
            tw.word,
            tw.timeOffset as time_offset,
            tw.duration
        FROM
            audio a
        JOIN
            transcript_word tw ON a.segmentId = tw.segmentId
        WHERE
            (CAST(a.startTime AS INTEGER) BETWEEN ? AND ?)
            AND INSTR(LOWER(tw.word), ?) > 0
        ORDER BY
            a.startTime, tw.timeOffset
        """

        self.cursor.execute(audio_query, (start_timestamp_ms, end_timestamp_ms, search_term))
        audio_matches = self.cursor.fetchall()

        # if no results with millisecond timestamps, try with string timestamps
        if not audio_matches:
            audio_query = """
            SELECT
                a.id as audio_id,
                a.startTime as start_time,
                a.duration,
                a.segmentId as segment_id,
                tw.id as word_id,
                tw.word,
                tw.timeOffset as time_offset,
                tw.duration
            FROM
                audio a
            JOIN
                transcript_word tw ON a.segmentId = tw.segmentId
            WHERE
                (a.startTime BETWEEN ? AND ?)
                AND INSTR(LOWER(tw.word), ?) > 0
            ORDER BY
                a.startTime, tw.timeOffset
            """

            self.cursor.execute(audio_query, (start_timestamp_str, end_timestamp_str, search_term))
            audio_matches = self.cursor.fetchall()

        audio_results = []

        # for each match, get surrounding context words
        for match in audio_matches:
            audio_id = match[0]
            start_time_val = match[1]
            segment_id = match[3]
            match_word_id = match[4]
            match_word = match[5]
            match_time_offset = match[6]

            # get context words (words before and after the match)
            context_query = """
            SELECT
                tw.id as word_id,
                tw.word,
                tw.timeOffset as time_offset,
                tw.duration
            FROM
                transcript_word tw
            WHERE
                tw.segmentId = ?
                AND tw.timeOffset BETWEEN ? AND ?
            ORDER BY
                tw.timeOffset
            """

            # get words within 5 seconds before and after the match
            context_before = match_time_offset - 5000  # 5 seconds before
            context_after = match_time_offset + 5000   # 5 seconds after

            self.cursor.execute(context_query, (segment_id, context_before, context_after))
            context_words = self.cursor.fetchall()

            # parse the start time
            if isinstance(start_time_val, str):
                try:
                    start_time_dt = datetime.datetime.strptime(start_time_val, "%Y-%m-%dT%H:%M:%S.%f")
                except ValueError:
                    try:
                        start_time_dt = datetime.datetime.strptime(start_time_val, "%Y-%m-%dT%H:%M:%S")
                    except ValueError:
                        start_time_dt = self._ms_to_datetime(int(start_time_val))
            else:
                start_time_dt = self._ms_to_datetime(start_time_val)

            # add all context words to results
            for context_word in context_words:
                word_id = context_word[0]
                word = context_word[1]
                time_offset = context_word[2]
                duration = context_word[3]

                # calculate absolute time for this word
                if isinstance(start_time_val, str):
                    if isinstance(time_offset, int):
                        absolute_time = start_time_dt + datetime.timedelta(milliseconds=time_offset)
                    else:
                        absolute_time = start_time_dt
                else:
                    absolute_time = self._ms_to_datetime(start_time_val + time_offset)

                # mark if this is the actual match
                is_match = (word_id == match_word_id)

                audio_results.append({
                    'audio_id': audio_id,
                    'audio_start_time': start_time_dt,
                    'audio_duration': match[2],
                    'word_id': word_id,
                    'word': word,
                    'time_offset': time_offset,
                    'duration': duration,
                    'absolute_time': absolute_time,
                    'is_match': is_match
                })

        # Search in screen OCR data
        try:
            # First, try to use the searchRanking_content table which contains OCR text content
            logger.info(f"Searching for '{search_term}' in searchRanking_content table")
            screen_query = """
            SELECT
                src.id as content_id,
                src.c0 as text_content,
                src.c1 as timestamp_info,
                src.c2 as window_info,
                f.id as frame_id,
                f.createdAt as created_at,
                f.segmentId as segment_id,
                s.bundleID as app_name,
                s.windowName as window_name,
                f.imageFileName
            FROM
                searchRanking_content src
            LEFT JOIN
                frame f ON src.id = f.id
            LEFT JOIN
                segment s ON f.segmentId = s.id
            WHERE
                LOWER(src.c0) LIKE ?
            ORDER BY
                src.id DESC
            LIMIT 100  -- Limit results to avoid performance issues
            """

            # add wildcards for LIKE query
            like_term = f"%{search_term}%"
            self.cursor.execute(screen_query, (like_term,))
            screen_rows = self.cursor.fetchall()

            if not screen_rows:
                logger.info(f"No results found in searchRanking_content table, trying search_content table")
                # Try to use the search_content table for full-text search
                screen_query = """
                SELECT
                    f.id as frame_id,
                    f.createdAt as created_at,
                    f.segmentId as segment_id,
                    n.id as node_id,
                    n.textOffset,
                    n.textLength,
                    s.bundleID as app_name,
                    s.windowName as window_name,
                    f.imageFileName
                FROM
                    frame f
                JOIN
                    node n ON f.id = n.frameId
                JOIN
                    segment s ON f.segmentId = s.id
                JOIN
                    search_content sc ON f.id = sc.docid
                WHERE
                    f.createdAt BETWEEN ? AND ?
                    AND (LOWER(sc.c0text) LIKE ? OR LOWER(sc.c1otherText) LIKE ?)
                ORDER BY
                    f.createdAt
                """

                self.cursor.execute(screen_query, (start_timestamp, end_timestamp, like_term, like_term))
                screen_rows = self.cursor.fetchall()

            # If still no results, try searching in window names and bundle IDs
            if not screen_rows:
                logger.info(f"No results found in search_content table, trying window names and bundle IDs")
                screen_query = """
                SELECT
                    f.id as frame_id,
                    f.createdAt as created_at,
                    f.segmentId as segment_id,
                    n.id as node_id,
                    n.textOffset,
                    n.textLength,
                    s.bundleID as app_name,
                    s.windowName as window_name,
                    f.imageFileName
                FROM
                    frame f
                JOIN
                    node n ON f.id = n.frameId
                JOIN
                    segment s ON f.segmentId = s.id
                WHERE
                    f.createdAt BETWEEN ? AND ?
                    AND (LOWER(s.windowName) LIKE ? OR LOWER(s.bundleID) LIKE ?)
                ORDER BY
                    f.createdAt
                LIMIT 100  -- Limit results to avoid performance issues
                """

                self.cursor.execute(screen_query, (start_timestamp, end_timestamp, like_term, like_term))
                screen_rows = self.cursor.fetchall()

            screen_results = []
            for row in screen_rows:
                result = {}

                # Handle results from searchRanking_content query
                if len(row) >= 4 and row[0] is not None and row[1] is not None:
                    result = {
                        'content_id': row[0],
                        'text': row[1][:100] + "..." if row[1] and len(row[1]) > 100 else row[1],
                        'timestamp_info': row[2],
                        'window_info': row[3],
                        'frame_id': row[4] if len(row) > 4 else None,
                        'frame_time': self._ms_to_datetime(row[5]) if len(row) > 5 and row[5] else None,
                        'segment_id': row[6] if len(row) > 6 else None,
                        'application': row[7] if len(row) > 7 else None,
                        'window': row[8] if len(row) > 8 else None,
                        'image_file': row[9] if len(row) > 9 else None
                    }
                # Handle results from other queries
                else:
                    result = {
                        'frame_id': row[0],
                        'frame_time': self._ms_to_datetime(row[1]) if row[1] else None,
                        'segment_id': row[2] if len(row) > 2 else None,
                        'node_id': row[3] if len(row) > 3 else None,
                        'text_offset': row[4] if len(row) > 4 else None,
                        'text_length': row[5] if len(row) > 5 else None,
                        'application': row[6] if len(row) > 6 else None,
                        'window': row[7] if len(row) > 7 else None,
                        'image_file': row[8] if len(row) > 8 else None,
                        'text': f"Screen match in {row[6]} - {row[7]}" if len(row) > 7 else "Screen match"
                    }

                screen_results.append(result)
        except Exception as e:
            logger.error(f"Error in screen OCR search: {e}")
            screen_results = []

        return {
            'audio': audio_results,
            'screen': screen_results
        }

    def get_segments(self, start_time: datetime.datetime,
                    end_time: datetime.datetime) -> typing.List[dict]:
        """retrieve application/window usage segments within a time range.

        queries the segment table to get application usage sessions within
        the specified time range.

        args:
            start_time: the start datetime to query from
            end_time: the end datetime to query to

        returns:
            a list of dictionaries containing segment data
        """

        # Try both timestamp formats
        try:
            # First try with millisecond timestamps
            start_timestamp = int(start_time.timestamp() * 1000)
            end_timestamp = int(end_time.timestamp() * 1000)

            query = """
            SELECT
                id,
                startDate,
                endDate,
                bundleID,
                windowName,
                browserUrl
            FROM
                segment
            WHERE
                (startDate BETWEEN ? AND ?) OR
                (endDate BETWEEN ? AND ?) OR
                (startDate <= ? AND endDate >= ?)
            ORDER BY
                startDate
            """

            self.cursor.execute(query, (
                start_timestamp, end_timestamp,
                start_timestamp, end_timestamp,
                start_timestamp, end_timestamp
            ))
            rows = self.cursor.fetchall()

            # If no results, try with string-formatted timestamps
            if not rows:
                # Format timestamps as strings
                start_timestamp = start_time.strftime("%Y-%m-%dT%H:%M:%S.000")
                end_timestamp = end_time.strftime("%Y-%m-%dT%H:%M:%S.999")

                query = """
                SELECT
                    id,
                    startDate,
                    endDate,
                    bundleID,
                    windowName,
                    browserUrl
                FROM
                    segment
                WHERE
                    (startDate BETWEEN ? AND ?) OR
                    (endDate BETWEEN ? AND ?) OR
                    (startDate <= ? AND endDate >= ?)
                ORDER BY
                    startDate
                """

                self.cursor.execute(query, (
                    start_timestamp, end_timestamp,
                    start_timestamp, end_timestamp,
                    start_timestamp, end_timestamp
                ))
                rows = self.cursor.fetchall()

            results = []
            for row in rows:
                # Check if the timestamps are strings or integers
                if isinstance(row[1], str) and isinstance(row[2], str):
                    # Parse the timestamps from the text format
                    try:
                        start_time_dt = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S.%f")
                        end_time_dt = datetime.datetime.strptime(row[2], "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        # Try without microseconds
                        start_time_dt = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S")
                        end_time_dt = datetime.datetime.strptime(row[2], "%Y-%m-%dT%H:%M:%S")

                    # Calculate duration in seconds
                    duration_seconds = (end_time_dt - start_time_dt).total_seconds()
                else:
                    # Use the existing _ms_to_datetime method
                    start_time_dt = self._ms_to_datetime(row[1])
                    end_time_dt = self._ms_to_datetime(row[2])
                    duration_seconds = (row[2] - row[1]) / 1000

                results.append({
                    'id': row[0],
                    'start_time': start_time_dt,
                    'end_time': end_time_dt,
                    'application': row[3],
                    'window': row[4],
                    'browser_url': row[5],
                    'duration_seconds': duration_seconds
                })

            return results

        except Exception as e:
            logger.error(f"Error in get_segments: {e}")
            return []

    def get_events(self, start_time: datetime.datetime,
                  end_time: datetime.datetime) -> typing.List[dict]:
        """retrieve events (meetings) within a time range.

        queries the event table to get meeting or event records within
        the specified time range.

        args:
            start_time: the start datetime to query from
            end_time: the end datetime to query to

        returns:
            a list of dictionaries containing event data
        """

        start_timestamp = int(start_time.timestamp() * 1000)
        end_timestamp = int(end_time.timestamp() * 1000)

        query = """
        SELECT
            id,
            title,
            startDate,
            endDate,
            location,
            notes,
            calendarName
        FROM
            event
        WHERE
            (startDate BETWEEN ? AND ?) OR
            (endDate BETWEEN ? AND ?) OR
            (startDate <= ? AND endDate >= ?)
        ORDER BY
            startDate
        """

        self.cursor.execute(query, (
            start_timestamp, end_timestamp,
            start_timestamp, end_timestamp,
            start_timestamp, end_timestamp
        ))
        rows = self.cursor.fetchall()

        results = []
        for row in rows:
            results.append({
                'id': row[0],
                'title': row[1],
                'start_time': self._ms_to_datetime(row[2]),
                'end_time': self._ms_to_datetime(row[3]),
                'location': row[4],
                'notes': row[5],
                'calendar': row[6],
                'duration_seconds': (row[3] - row[2]) / 1000
            })

        return results

    def _ms_to_datetime(self, ms: int) -> datetime.datetime:
        """convert milliseconds since epoch to datetime object.

        utility function to convert millisecond timestamps to datetime objects.

        args:
            ms: milliseconds since epoch

        returns:
            datetime object representing the timestamp in UTC
        """

        # Convert to UTC datetime to match the now() call in get_statistics
        return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc)

    def get_statistics(self, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> dict:
        """collect comprehensive statistics about the rewind database.

        gathers statistics about audio transcripts, screen ocr data,
        application usage, and general database metrics.

        args:
            days: number of days to look back (default: 0)
            hours: number of hours to look back (default: 0)
            minutes: number of minutes to look back (default: 0)
            seconds: number of seconds to look back (default: 0)

        returns:
            dict: dictionary with comprehensive statistics
        """
        # Get date ranges for time-based statistics
        now = datetime.datetime.now(datetime.timezone.utc)

        # check if relative time parameters are provided
        is_relative = any([days, hours, minutes, seconds])

        if is_relative:
            # calculate the relative time range
            delta = datetime.timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
            start_time = now - delta

            # for relative time queries, we only need one time range
            hour_ago = start_time
            day_ago = start_time
            week_ago = start_time
            month_ago = start_time
        else:
            # use default time ranges for standard statistics
            hour_ago = now - datetime.timedelta(hours=1)
            day_ago = now - datetime.timedelta(days=1)
            week_ago = now - datetime.timedelta(days=7)
            month_ago = now - datetime.timedelta(days=30)

        # Audio statistics
        audio_stats = self._get_audio_stats(now, hour_ago, day_ago, week_ago, month_ago, is_relative)

        # Screen statistics
        screen_stats = self._get_screen_stats(now, hour_ago, day_ago, week_ago, month_ago, is_relative)

        # App usage statistics
        app_stats = self._get_app_usage_stats(now, week_ago, is_relative)

        # Database statistics
        # Note: This is the most time-consuming part, so we skip it for relative time queries
        if is_relative:
            # For relative time, use a simplified version with just the essential info
            db_stats = {
                'table_stats': [],  # Empty list to avoid scanning all tables
                'db_size_mb': 0,    # Skip file size calculation
                'table_count': 0    # Skip table count calculation
            }
        else:
            # For standard statistics, get full database stats
            db_stats = self._get_database_stats()

        return {
            'audio': audio_stats,
            'screen': screen_stats,
            'app_usage': app_stats,
            'database': db_stats
        }

    def _get_audio_stats(self, now, hour_ago, day_ago, week_ago, month_ago, is_relative=False) -> dict:
        """collect statistics about audio transcripts.

        internal method to gather metrics about audio transcripts.

        returns:
            dict: dictionary with audio statistics
        """
        # Convert dates to timestamps (milliseconds)
        now_ts = int(now.timestamp() * 1000)
        hour_ago_ts = int(hour_ago.timestamp() * 1000)
        day_ago_ts = int(day_ago.timestamp() * 1000)
        week_ago_ts = int(week_ago.timestamp() * 1000)
        month_ago_ts = int(month_ago.timestamp() * 1000)

        # Log the timestamps for debugging
        logger.info(f"now: {now}, now_ts: {now_ts}")
        logger.info(f"hour_ago: {hour_ago}, hour_ago_ts: {hour_ago_ts}")

        # Also log the actual datetime objects for comparison
        logger.info(f"now timezone: {now.tzinfo}")
        logger.info(f"hour_ago timezone: {hour_ago.tzinfo}")

        # Initialize count variables
        hour_count = day_count = week_count = month_count = 0

        # Get transcript counts
        try:
            if is_relative:
                # For relative time, only execute one query
                # Log the SQL query for debugging
                query = """
                    SELECT COUNT(*) FROM transcript_word tw
                    JOIN audio a ON tw.segmentId = a.segmentId
                    WHERE a.startTime + tw.timeOffset BETWEEN ? AND ?
                """
                logger.info(f"Executing query: {query} with params: ({hour_ago_ts}, {now_ts})")

                self.cursor.execute(query, (hour_ago_ts, now_ts))
                result = self.cursor.fetchone()
                hour_count = result[0] if result else 0

                logger.info(f"Query result: {result}")

                # Try a simpler query to see if there's any data in the audio table
                self.cursor.execute("SELECT COUNT(*) FROM audio")
                total_audio_count = self.cursor.fetchone()[0]
                logger.info(f"Total audio records: {total_audio_count}")

                # Try a query with a wider time range
                one_year_ago_ts = int((now - datetime.timedelta(days=365)).timestamp() * 1000)
                self.cursor.execute("""
                    SELECT COUNT(*) FROM audio
                    WHERE startTime BETWEEN ? AND ?
                """, (one_year_ago_ts, now_ts))
                year_audio_count = self.cursor.fetchone()[0]
                logger.info(f"Audio records in the past year: {year_audio_count}")

                # Try to get the earliest and latest audio record
                self.cursor.execute("SELECT MIN(startTime), MAX(startTime) FROM audio")
                min_max = self.cursor.fetchone()
                if min_max and min_max[0] and min_max[1]:
                    min_time = self._ms_to_datetime(min_max[0]) if isinstance(min_max[0], int) else min_max[0]
                    max_time = self._ms_to_datetime(min_max[1]) if isinstance(min_max[1], int) else min_max[1]
                    logger.info(f"Earliest audio record: {min_time}, Latest audio record: {max_time}")
            else:
                # For standard statistics, execute all queries
                # Hour count
                self.cursor.execute("""
                    SELECT COUNT(*) FROM transcript_word tw
                    JOIN audio a ON tw.segmentId = a.segmentId
                    WHERE a.startTime + tw.timeOffset BETWEEN ? AND ?
                """, (hour_ago_ts, now_ts))
                hour_count = self.cursor.fetchone()[0]

                # Day count
                self.cursor.execute("""
                    SELECT COUNT(*) FROM transcript_word tw
                    JOIN audio a ON tw.segmentId = a.segmentId
                    WHERE a.startTime + tw.timeOffset BETWEEN ? AND ?
                """, (day_ago_ts, now_ts))
                day_count = self.cursor.fetchone()[0]

                # Week count
                self.cursor.execute("""
                    SELECT COUNT(*) FROM transcript_word tw
                    JOIN audio a ON tw.segmentId = a.segmentId
                    WHERE a.startTime + tw.timeOffset BETWEEN ? AND ?
                """, (week_ago_ts, now_ts))
                week_count = self.cursor.fetchone()[0]

                # Month count
                self.cursor.execute("""
                    SELECT COUNT(*) FROM transcript_word tw
                    JOIN audio a ON tw.segmentId = a.segmentId
                    WHERE a.startTime + tw.timeOffset BETWEEN ? AND ?
                """, (month_ago_ts, now_ts))
                month_count = self.cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"error getting transcript counts: {e}")
            hour_count = day_count = week_count = month_count = 0

        # Get earliest audio record and total counts
        if is_relative:
            # For relative time, only consider records within the time period
            try:
                self.cursor.execute("""
                    SELECT MIN(startTime) FROM audio
                    WHERE startTime BETWEEN ? AND ?
                """, (hour_ago_ts, now_ts))
                earliest_timestamp = self.cursor.fetchone()[0]

                # If no records in the time period, use None
                if earliest_timestamp is None:
                    earliest_date = None
                elif isinstance(earliest_timestamp, int):
                    earliest_date = self._ms_to_datetime(earliest_timestamp)
                elif isinstance(earliest_timestamp, str):
                    try:
                        earliest_date = datetime.datetime.strptime(earliest_timestamp, "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        earliest_date = datetime.datetime.strptime(earliest_timestamp, "%Y-%m-%dT%H:%M:%S")
                else:
                    earliest_date = None
            except Exception as e:
                logger.error(f"error getting earliest audio record: {e}")
                earliest_date = None

            # Get total audio records within the time period
            try:
                self.cursor.execute("""
                    SELECT COUNT(*) FROM audio
                    WHERE startTime BETWEEN ? AND ?
                """, (hour_ago_ts, now_ts))
                total_audio = self.cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"error getting total audio count: {e}")
                total_audio = 0

            # Get total transcript words within the time period
            try:
                self.cursor.execute("""
                    SELECT COUNT(*) FROM transcript_word tw
                    JOIN audio a ON tw.segmentId = a.segmentId
                    WHERE a.startTime + tw.timeOffset BETWEEN ? AND ?
                """, (hour_ago_ts, now_ts))
                total_words = self.cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"error getting total word count: {e}")
                total_words = 0
        else:
            # For standard statistics, get global counts
            try:
                self.cursor.execute("SELECT MIN(startTime) FROM audio")
                earliest_timestamp = self.cursor.fetchone()[0]
                if isinstance(earliest_timestamp, int):
                    earliest_date = self._ms_to_datetime(earliest_timestamp)
                elif isinstance(earliest_timestamp, str):
                    try:
                        earliest_date = datetime.datetime.strptime(earliest_timestamp, "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        earliest_date = datetime.datetime.strptime(earliest_timestamp, "%Y-%m-%dT%H:%M:%S")
                else:
                    earliest_date = None
            except Exception as e:
                logger.error(f"error getting earliest audio record: {e}")
                earliest_date = None

            # Get total audio records
            try:
                self.cursor.execute("SELECT COUNT(*) FROM audio")
                total_audio = self.cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"error getting total audio count: {e}")
                total_audio = 0

            # Get total transcript words
            try:
                self.cursor.execute("SELECT COUNT(*) FROM transcript_word")
                total_words = self.cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"error getting total word count: {e}")
                total_words = 0

        result = {
            'earliest_date': earliest_date,
            'total_audio': total_audio,
            'total_words': total_words
        }

        if is_relative:
            # for relative time queries, we only need one count
            result['relative_count'] = hour_count
        else:
            # for standard statistics, include all time periods
            result['hour_count'] = hour_count
            result['day_count'] = day_count
            result['week_count'] = week_count
            result['month_count'] = month_count

        return result

    def _get_screen_stats(self, now, hour_ago, day_ago, week_ago, month_ago, is_relative=False) -> dict:
        """collect statistics about screen ocr data.

        internal method to gather metrics about screen ocr data.

        returns:
            dict: dictionary with screen statistics
        """
        # Convert dates to timestamps (milliseconds)
        now_ts = int(now.timestamp() * 1000)
        hour_ago_ts = int(hour_ago.timestamp() * 1000)
        day_ago_ts = int(day_ago.timestamp() * 1000)
        week_ago_ts = int(week_ago.timestamp() * 1000)
        month_ago_ts = int(month_ago.timestamp() * 1000)

        # Initialize count variables
        hour_count = day_count = week_count = month_count = 0

        # Get ocr counts
        try:
            if is_relative:
                # For relative time, only execute one query
                self.cursor.execute("""
                    SELECT COUNT(*) FROM node n
                    JOIN frame f ON n.frameId = f.id
                    WHERE f.createdAt BETWEEN ? AND ?
                """, (hour_ago_ts, now_ts))
                hour_count = self.cursor.fetchone()[0]
            else:
                # For standard statistics, execute all queries
                # Hour count
                self.cursor.execute("""
                    SELECT COUNT(*) FROM node n
                    JOIN frame f ON n.frameId = f.id
                    WHERE f.createdAt BETWEEN ? AND ?
                """, (hour_ago_ts, now_ts))
                hour_count = self.cursor.fetchone()[0]

                # Day count
                self.cursor.execute("""
                    SELECT COUNT(*) FROM node n
                    JOIN frame f ON n.frameId = f.id
                    WHERE f.createdAt BETWEEN ? AND ?
                """, (day_ago_ts, now_ts))
                day_count = self.cursor.fetchone()[0]

                # Week count
                self.cursor.execute("""
                    SELECT COUNT(*) FROM node n
                    JOIN frame f ON n.frameId = f.id
                    WHERE f.createdAt BETWEEN ? AND ?
                """, (week_ago_ts, now_ts))
                week_count = self.cursor.fetchone()[0]

                # Month count
                self.cursor.execute("""
                    SELECT COUNT(*) FROM node n
                    JOIN frame f ON n.frameId = f.id
                    WHERE f.createdAt BETWEEN ? AND ?
                """, (month_ago_ts, now_ts))
                month_count = self.cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"error getting ocr counts: {e}")
            hour_count = day_count = week_count = month_count = 0

        # Get earliest frame record and total counts
        if is_relative:
            # For relative time, only consider records within the time period
            try:
                self.cursor.execute("""
                    SELECT MIN(createdAt) FROM frame
                    WHERE createdAt BETWEEN ? AND ?
                """, (hour_ago_ts, now_ts))
                earliest_timestamp = self.cursor.fetchone()[0]

                # If no records in the time period, use None
                if earliest_timestamp is None:
                    earliest_date = None
                elif isinstance(earliest_timestamp, int):
                    earliest_date = self._ms_to_datetime(earliest_timestamp)
                elif isinstance(earliest_timestamp, str):
                    try:
                        earliest_date = datetime.datetime.strptime(earliest_timestamp, "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        earliest_date = datetime.datetime.strptime(earliest_timestamp, "%Y-%m-%dT%H:%M:%S")
                else:
                    earliest_date = None
            except Exception as e:
                logger.error(f"error getting earliest frame record: {e}")
                earliest_date = None

            # Get total frame records within the time period
            try:
                self.cursor.execute("""
                    SELECT COUNT(*) FROM frame
                    WHERE createdAt BETWEEN ? AND ?
                """, (hour_ago_ts, now_ts))
                total_frames = self.cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"error getting total frame count: {e}")
                total_frames = 0

            # Get total node records within the time period
            try:
                self.cursor.execute("""
                    SELECT COUNT(*) FROM node n
                    JOIN frame f ON n.frameId = f.id
                    WHERE f.createdAt BETWEEN ? AND ?
                """, (hour_ago_ts, now_ts))
                total_nodes = self.cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"error getting total node count: {e}")
                total_nodes = 0
        else:
            # For standard statistics, get global counts
            try:
                self.cursor.execute("SELECT MIN(createdAt) FROM frame")
                earliest_timestamp = self.cursor.fetchone()[0]
                if isinstance(earliest_timestamp, int):
                    earliest_date = self._ms_to_datetime(earliest_timestamp)
                elif isinstance(earliest_timestamp, str):
                    try:
                        earliest_date = datetime.datetime.strptime(earliest_timestamp, "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        earliest_date = datetime.datetime.strptime(earliest_timestamp, "%Y-%m-%dT%H:%M:%S")
                else:
                    earliest_date = None
            except Exception as e:
                logger.error(f"error getting earliest frame record: {e}")
                earliest_date = None

            # Get total frame records
            try:
                self.cursor.execute("SELECT COUNT(*) FROM frame")
                total_frames = self.cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"error getting total frame count: {e}")
                total_frames = 0

            # Get total node records
            try:
                self.cursor.execute("SELECT COUNT(*) FROM node")
                total_nodes = self.cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"error getting total node count: {e}")
                total_nodes = 0

        result = {
            'earliest_date': earliest_date,
            'total_frames': total_frames,
            'total_nodes': total_nodes
        }

        if is_relative:
            # for relative time queries, we only need one count
            result['relative_count'] = hour_count
        else:
            # for standard statistics, include all time periods
            result['hour_count'] = hour_count
            result['day_count'] = day_count
            result['week_count'] = week_count
            result['month_count'] = month_count

        return result

    def _get_app_usage_stats(self, now, week_ago, is_relative=False) -> dict:
        """collect statistics about application usage.

        internal method to gather metrics about application usage.

        returns:
            dict: dictionary with application usage statistics
        """
        # Convert dates to timestamps (milliseconds)
        now_ts = int(now.timestamp() * 1000)
        week_ago_ts = int(week_ago.timestamp() * 1000)

        # Directly query segments from the database
        try:
            query = """
            SELECT
                id,
                startDate,
                endDate,
                bundleID,
                windowName,
                browserUrl
            FROM
                segment
            WHERE
                (startDate BETWEEN ? AND ?) OR
                (endDate BETWEEN ? AND ?) OR
                (startDate <= ? AND endDate >= ?)
            ORDER BY
                startDate
            """

            self.cursor.execute(query, (
                week_ago_ts, now_ts,
                week_ago_ts, now_ts,
                week_ago_ts, now_ts
            ))
            rows = self.cursor.fetchall()

            # Calculate app usage time
            app_usage = {}
            for row in rows:
                app = row[3]  # bundleID
                if app is None:
                    app = "Unknown"

                # Calculate duration in seconds
                if isinstance(row[1], int) and isinstance(row[2], int):
                    duration = (row[2] - row[1]) / 1000  # (endDate - startDate) / 1000
                else:
                    # Handle string timestamps
                    try:
                        start_time = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        start_time = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S")

                    try:
                        end_time = datetime.datetime.strptime(row[2], "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        end_time = datetime.datetime.strptime(row[2], "%Y-%m-%dT%H:%M:%S")

                    duration = (end_time - start_time).total_seconds()

                if app in app_usage:
                    app_usage[app] += duration
                else:
                    app_usage[app] = duration
        except Exception as e:
            logger.error(f"error getting segment data: {e}")
            app_usage = {}

        # Sort apps by usage time
        sorted_apps = sorted(app_usage.items(), key=lambda x: x[1], reverse=True)

        # Get top 10 apps
        top_apps = []
        total_duration = sum(app_usage.values()) if app_usage else 1  # Avoid division by zero

        for app, duration in sorted_apps[:10]:
            hours = duration / 3600
            top_apps.append({
                'app': app,
                'hours': round(hours, 2),
                'percentage': round((duration / total_duration) * 100, 2)
            })

        # Get total segments
        try:
            if is_relative:
                # For relative time, only count segments within the time period
                self.cursor.execute("""
                    SELECT COUNT(*) FROM segment
                    WHERE (startDate BETWEEN ? AND ?) OR
                          (endDate BETWEEN ? AND ?) OR
                          (startDate <= ? AND endDate >= ?)
                """, (
                    week_ago_ts, now_ts,
                    week_ago_ts, now_ts,
                    week_ago_ts, now_ts
                ))
            else:
                # For standard statistics, count all segments
                self.cursor.execute("SELECT COUNT(*) FROM segment")

            total_segments = self.cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"error getting total segment count: {e}")
            total_segments = 0

        return {
            'top_apps': top_apps,
            'total_apps': len(app_usage),
            'total_segments': total_segments,
            'total_hours': round(sum(app_usage.values()) / 3600, 2)
        }

    def _get_database_stats(self) -> dict:
        """collect general statistics about the database.

        internal method to gather general metrics about the database.

        returns:
            dict: dictionary with database statistics
        """
        # Get table counts
        table_stats = []
        try:
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = self.cursor.fetchall()

            for table in tables:
                table_name = table[0]
                try:
                    # Handle tokenizer table specially
                    if table_name == 'tokenizer':
                        self.cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tokenizer'")
                        count = self.cursor.fetchone()[0]
                    else:
                        self.cursor.execute(f"SELECT COUNT(*) FROM '{table_name}'")
                        count = self.cursor.fetchone()[0]
                    table_stats.append({
                        'table': table_name,
                        'records': count
                    })
                except Exception as e:
                    logger.warning(f"could not get count for table {table_name}: {e}")
                    table_stats.append({
                        'table': table_name,
                        'records': 0
                    })

            # Add sqlite_sequence table separately
            try:
                self.cursor.execute("SELECT COUNT(*) FROM sqlite_sequence")
                count = self.cursor.fetchone()[0]
                table_stats.append({
                    'table': 'sqlite_sequence',
                    'records': count
                })
            except Exception:
                pass

            # Sort by record count
            table_stats = sorted(table_stats, key=lambda x: x['records'], reverse=True)
        except Exception as e:
            logger.error(f"error getting table statistics: {e}")

        # Get database file size
        try:
            import os
            db_size = os.path.getsize(self.db_path)
            db_size_mb = round(db_size / (1024 * 1024), 2)
        except Exception as e:
            logger.error(f"error getting database file size: {e}")
            db_size_mb = 0

        return {
            'table_stats': table_stats,
            'db_size_mb': db_size_mb,
            'table_count': len(table_stats)
        }

    def __enter__(self):
        """context manager entry.

        allows using the rewinddb class with a 'with' statement.

        returns:
            self: the rewinddb instance
        """

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """context manager exit.

        ensures the database connection is closed when exiting a 'with' block.

        args:
            exc_type: exception type if an exception was raised
            exc_val: exception value if an exception was raised
            exc_tb: exception traceback if an exception was raised
        """

        self.close()

    def get_screenshot_by_id(self, frame_id: int) -> typing.Optional[dict]:
        """retrieve a screenshot by frame id.

        queries the frame table to get a specific screenshot by its id.

        args:
            frame_id: the id of the frame to retrieve

        returns:
            a dictionary containing screenshot data or none if not found
        """

        try:
            # query the frame table for the specified id
            query = """
            SELECT
                f.id as frame_id,
                f.createdAt as created_at,
                f.segmentId as segment_id,
                f.imageFileName as image_file,
                s.bundleID as app_name,
                s.windowName as window_name
            FROM
                frame f
            LEFT JOIN
                segment s ON f.segmentId = s.id
            WHERE
                f.id = ?
            """

            self.cursor.execute(query, (frame_id,))
            row = self.cursor.fetchone()

            if not row:
                return None

            # parse the timestamp
            if isinstance(row[1], str):
                try:
                    frame_time = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S.%f")
                except ValueError:
                    # try without microseconds
                    frame_time = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S")
            else:
                # use the existing _ms_to_datetime method
                frame_time = self._ms_to_datetime(row[1])

            # construct the result
            result = {
                'frame_id': row[0],
                'frame_time': frame_time,
                'segment_id': row[2],
                'image_file': row[3],
                'application': row[4],
                'window': row[5]
            }

            return result

        except Exception as e:
            logger.error(f"error in get_screenshot_by_id: {e}")
            return None

    def get_screenshots_absolute(self, start_time: datetime.datetime,
                               end_time: datetime.datetime,
                               limit: int = 100) -> typing.List[dict]:
        """retrieve screenshots within an absolute time range.

        queries the frame table to get screenshots within the specified absolute time range.

        args:
            start_time: the start datetime to query from
            end_time: the end datetime to query to
            limit: maximum number of screenshots to return (default: 100)

        returns:
            a list of dictionaries containing screenshot data
        """

        # try both timestamp formats
        try:
            # first try with millisecond timestamps
            start_timestamp = int(start_time.timestamp() * 1000)  # convert to milliseconds
            end_timestamp = int(end_time.timestamp() * 1000)  # convert to milliseconds

            query = """
            SELECT
                f.id as frame_id,
                f.createdAt as created_at,
                f.segmentId as segment_id,
                f.imageFileName as image_file,
                s.bundleID as app_name,
                s.windowName as window_name
            FROM
                frame f
            LEFT JOIN
                segment s ON f.segmentId = s.id
            WHERE
                f.createdAt BETWEEN ? AND ?
            ORDER BY
                f.createdAt DESC
            LIMIT ?
            """

            self.cursor.execute(query, (start_timestamp, end_timestamp, limit))
            rows = self.cursor.fetchall()

            # if no results, try with string-formatted timestamps
            if not rows:
                # format timestamps as strings
                start_timestamp = start_time.strftime("%Y-%m-%dT%H:%M:%S.000")
                end_timestamp = end_time.strftime("%Y-%m-%dT%H:%M:%S.999")

                query = """
                SELECT
                    f.id as frame_id,
                    f.createdAt as created_at,
                    f.segmentId as segment_id,
                    f.imageFileName as image_file,
                    s.bundleID as app_name,
                    s.windowName as window_name
                FROM
                    frame f
                LEFT JOIN
                    segment s ON f.segmentId = s.id
                WHERE
                    f.createdAt BETWEEN ? AND ?
                ORDER BY
                    f.createdAt DESC
                LIMIT ?
                """

                self.cursor.execute(query, (start_timestamp, end_timestamp, limit))
                rows = self.cursor.fetchall()

            results = []
            for row in rows:
                # check if the timestamp is a string or an integer
                if isinstance(row[1], str):
                    # parse the timestamp from the text format
                    try:
                        frame_time = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        # try without microseconds
                        frame_time = datetime.datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S")
                else:
                    # use the existing _ms_to_datetime method
                    frame_time = self._ms_to_datetime(row[1])

                results.append({
                    'frame_id': row[0],
                    'frame_time': frame_time,
                    'segment_id': row[2],
                    'image_file': row[3],
                    'application': row[4],
                    'window': row[5]
                })

            return results

        except Exception as e:
            logger.error(f"error in get_screenshots_absolute: {e}")
            return []

    def get_screenshots_relative(self, days: int = 0, hours: int = 0,
                               minutes: int = 0, seconds: int = 0,
                               limit: int = 100) -> typing.List[dict]:
        """retrieve screenshots from a relative time period.

        queries screenshots from a time period relative to now.

        args:
            days: number of days to look back
            hours: number of hours to look back
            minutes: number of minutes to look back
            seconds: number of seconds to look back
            limit: maximum number of screenshots to return (default: 100)

        returns:
            a list of dictionaries containing screenshot data
        """

        # use utc timezone to be consistent with get_statistics
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = datetime.timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        start_time = now - delta

        return self.get_screenshots_absolute(start_time, now, limit)