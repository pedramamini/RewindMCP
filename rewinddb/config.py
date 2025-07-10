"""
configuration module for the rewinddb library.

this module provides functions to load and access configuration settings
from environment variables or .env files. it handles database connection
parameters and other configuration options.
"""

import os
import typing
from pathlib import Path
from dotenv import load_dotenv


def load_config(env_file: typing.Optional[str] = None) -> dict:
    """load configuration from environment variables or .env file.

    args:
        env_file: optional path to a .env file to load

    returns:
        dictionary containing configuration values
    """

    # if env_file is provided, load it
    if env_file:
        if not os.path.exists(env_file):
            raise FileNotFoundError(f"env file not found: {env_file}")
        load_dotenv(env_file)
    else:
        # try to load from default locations
        # first check current directory
        if os.path.exists(".env"):
            load_dotenv(".env")
        # then check user's home directory
        elif os.path.exists(os.path.expanduser("~/.rewinddb.env")):
            load_dotenv(os.path.expanduser("~/.rewinddb.env"))

    # get database configuration
    db_path = os.getenv("DB_PATH")
    db_password = os.getenv("DB_PASSWORD")

    # ensure required configuration is provided
    if not db_path:
        raise ValueError("DB_PATH environment variable must be set in .env file")

    if not db_password:
        raise ValueError("DB_PASSWORD environment variable must be set in .env file")

    return {
        "db_path": db_path,
        "db_password": db_password
    }


def get_db_path(env_file: typing.Optional[str] = None) -> str:
    """get the database path from configuration.

    args:
        env_file: optional path to a .env file to load

    returns:
        database path string
    """

    config = load_config(env_file)
    return config["db_path"]


def get_db_password(env_file: typing.Optional[str] = None) -> str:
    """get the database password from configuration.

    args:
        env_file: optional path to a .env file to load

    returns:
        database password string
    """

    config = load_config(env_file)
    return config["db_password"]