"""
utility functions for the rewinddb library.

this module provides helper functions for time conversions, data formatting,
and other utility operations used by the rewinddb library.
"""

import datetime
import typing


def timestamp_to_datetime(timestamp_ms: int) -> datetime.datetime:
    """convert millisecond timestamp to datetime object.

    args:
        timestamp_ms: milliseconds since epoch

    returns:
        datetime object representing the timestamp
    """

    # Always return timezone-aware UTC datetimes to be consistent with other
    # helpers like ``_ms_to_datetime`` in ``RewindDB``.
    return datetime.datetime.fromtimestamp(
        timestamp_ms / 1000, tz=datetime.timezone.utc
    )


def datetime_to_timestamp(dt: datetime.datetime) -> int:
    """convert datetime object to millisecond timestamp.

    args:
        dt: datetime object to convert

    returns:
        milliseconds since epoch
    """

    # Assume UTC when naive datetime objects are provided to avoid implicit
    # conversion using the local timezone.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


def format_transcript(transcript_data: typing.List[dict]) -> str:
    """format transcript data into readable text.

    converts a list of transcript word dictionaries into a formatted string
    with timestamps and spoken text.

    args:
        transcript_data: list of transcript word dictionaries

    returns:
        formatted string representation of the transcript
    """

    if not transcript_data:
        return "no transcript data available."

    # group words by audio session
    sessions = {}
    for item in transcript_data:
        audio_id = item['audio_id']
        if audio_id not in sessions:
            sessions[audio_id] = {
                'start_time': item['audio_start_time'],
                'words': []
            }
        sessions[audio_id]['words'].append(item)

    # format each session
    result = []
    for audio_id, session in sessions.items():
        start_time = session['start_time'].strftime('%Y-%m-%d %H:%M:%S')
        result.append(f"transcript from {start_time}:")

        # sort words by time offset
        words = sorted(session['words'], key=lambda x: x['time_offset'])

        # combine words into text
        text = ' '.join(word['word'] for word in words)
        result.append(text)
        result.append("")  # empty line between sessions

    return "\n".join(result)


def format_ocr_data(ocr_data: typing.List[dict]) -> str:
    """format ocr data into readable text.

    converts a list of ocr data dictionaries into a formatted string
    with timestamps, applications, and extracted text.

    args:
        ocr_data: list of ocr data dictionaries

    returns:
        formatted string representation of the ocr data
    """

    if not ocr_data:
        return "no ocr data available."

    # group by frame
    frames = {}
    for item in ocr_data:
        frame_id = item['frame_id']
        if frame_id not in frames:
            frames[frame_id] = {
                'time': item['frame_time'],
                'application': item['application'],
                'window': item['window'],
                'nodes': []
            }
        frames[frame_id]['nodes'].append({
            'text_offset': item['text_offset'],
            'text_length': item['text_length']
        })

    # format each frame
    result = []
    for frame_id, frame in frames.items():
        time_str = frame['time'].strftime('%Y-%m-%d %H:%M:%S')
        app_str = f"{frame['application']} - {frame['window']}"
        result.append(f"[{time_str}] {app_str}")

        # show node information
        for node in frame['nodes']:
            result.append(f"  Text offset: {node['text_offset']}, length: {node['text_length']}")

        result.append("")  # empty line between frames

    return "\n".join(result)


def group_results_by_time(results: typing.List[dict],
                         interval_seconds: int = 60) -> typing.List[typing.List[dict]]:
    """group results into time intervals.

    groups a list of result dictionaries (audio or ocr) into time intervals.

    args:
        results: list of result dictionaries with timestamp fields
        interval_seconds: size of time interval in seconds

    returns:
        list of lists, where each inner list contains results from the same time interval
    """

    if not results:
        return []

    # determine which timestamp field to use
    time_field = None
    if 'absolute_time' in results[0]:
        time_field = 'absolute_time'
    elif 'frame_time' in results[0]:
        time_field = 'frame_time'
    else:
        raise ValueError("results must contain either 'absolute_time' or 'frame_time' field")

    # sort by timestamp
    sorted_results = sorted(results, key=lambda x: x[time_field])

    # group by interval
    groups = []
    current_group = []
    current_interval_start = None

    for item in sorted_results:
        item_time = item[time_field]

        if current_interval_start is None:
            # first item
            current_interval_start = item_time
            current_group = [item]
        elif (item_time - current_interval_start).total_seconds() <= interval_seconds:
            # within current interval
            current_group.append(item)
        else:
            # new interval
            groups.append(current_group)
            current_interval_start = item_time
            current_group = [item]

    # add the last group if not empty
    if current_group:
        groups.append(current_group)

    return groups