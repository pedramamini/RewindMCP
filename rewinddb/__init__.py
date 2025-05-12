"""
rewinddb - a python library for interfacing with the rewind.ai sqlite database.

this module provides access to the rewind.ai database, allowing users to query
audio transcripts, screen ocr data, and search across both. the main entry point
is the rewinddb class, which handles connection to the encrypted database and
provides methods for data retrieval.

typical usage:
    import rewinddb

    # initialize connection to the database
    db = rewinddb.RewindDB()

    # query audio transcripts from the last hour
    transcripts = db.get_audio_transcripts_relative(hours=1)

    # search for keywords across all data
    results = db.search("python programming")
"""

from rewinddb.core import RewindDB
from rewinddb.config import load_config, get_db_path, get_db_password

__all__ = ["RewindDB", "load_config", "get_db_path", "get_db_password"]