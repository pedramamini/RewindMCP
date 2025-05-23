#!/usr/bin/env python
"""
mcp_server.py - model context protocol server for rewinddb.

call flow:
1. initialize fastapi application and mcp server
2. connect to rewinddb database
3. register mcp tools and resources:
   - get_transcripts_relative: retrieve audio transcripts from a relative time period
   - get_transcripts_absolute: retrieve audio transcripts from a specific time range
   - search: search for keywords across both audio and screen data
4. start the server with uvicorn
5. handle incoming requests:
   - parse request parameters
   - validate input
   - query rewinddb for requested data
   - format and return results
6. handle errors and provide appropriate responses
7. close database connection when server shuts down

the server exposes the following endpoints:
- /mcp/tools: list available tools
- /mcp/resources: list available resources
- /mcp/tools/{tool_name}: execute a tool
- /mcp/resources/{resource_uri}: access a resource

example tool calls:
- get_transcripts_relative with parameters: {"time_period": "1hour"}
- get_transcripts_absolute with parameters: {"from": "2023-05-11T13:00:00", "to": "2023-05-11T17:00:00"}
- search with parameters: {"keyword": "meeting", "relative": "1day"}

the server is designed to be used with the model context protocol (mcp),
which allows genai models to access external tools and resources.
"""

import os
import re
import sys
import json
import time
import base64
import typing
import logging
import datetime
import argparse
from pathlib import Path

import fastapi
import uvicorn
import pydantic
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

import rewinddb
import rewinddb.utils
from rewinddb.config import load_config


# configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("mcp_server")


class RelativeTimeParams(BaseModel):
    """parameters for relative time transcript retrieval."""

    time_period: str = Field(..., description="relative time period (e.g., '1hour', '30minutes', '1day')")

    @field_validator("time_period")
    def validate_time_period(cls, v):
        """validate the time period format."""

        pattern = r"^(\d+)(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs)$"
        if not re.match(pattern, v):
            raise ValueError("time_period must be in format like '1hour', '30minutes', '1day'")
        return v


class AbsoluteTimeParams(BaseModel):
    """parameters for absolute time transcript retrieval."""

    from_time: datetime.datetime = Field(..., alias="from", description="start time in ISO format")
    to_time: datetime.datetime = Field(..., alias="to", description="end time in ISO format")

    class Config:
        populate_by_name = True


class SearchParams(BaseModel):
    """parameters for keyword search."""

    keyword: str = Field(..., description="keyword to search for")
    relative: typing.Optional[str] = Field(None, description="relative time period (e.g., '1day', '7days')")
    from_time: typing.Optional[datetime.datetime] = Field(None, alias="from", description="start time in ISO format")
    to_time: typing.Optional[datetime.datetime] = Field(None, alias="to", description="end time in ISO format")

    @field_validator("relative")
    def validate_relative(cls, v):
        """validate the relative time format."""

        if v is not None:
            pattern = r"^(\d+)(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs)$"
            if not re.match(pattern, v):
                raise ValueError("relative must be in format like '1hour', '30minutes', '1day'")
        return v

    @field_validator("to_time")
    def validate_time_range(cls, v, values):
        """validate that if from_time is provided, to_time is also provided."""

        if values.get("from_time") is not None and v is None:
            raise ValueError("to_time is required when from_time is provided")
        return v

    class Config:
        populate_by_name = True


class ScreenshotByIdParams(BaseModel):
    """parameters for retrieving a screenshot by id."""

    frame_id: int = Field(..., description="id of the screenshot frame to retrieve")


class ScreenshotsRelativeParams(BaseModel):
    """parameters for relative time screenshot retrieval."""

    time_period: str = Field(..., description="relative time period (e.g., '1hour', '30minutes', '1day')")
    limit: typing.Optional[int] = Field(100, description="maximum number of screenshots to return")

    @field_validator("time_period")
    def validate_time_period(cls, v):
        """validate the time period format."""

        pattern = r"^(\d+)(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs)$"
        if not re.match(pattern, v):
            raise ValueError("time_period must be in format like '1hour', '30minutes', '1day'")
        return v

    @field_validator("limit")
    def validate_limit(cls, v):
        """validate the limit value."""

        if v is not None and (v < 1 or v > 1000):
            raise ValueError("limit must be between 1 and 1000")
        return v


class ScreenshotsAbsoluteParams(BaseModel):
    """parameters for absolute time screenshot retrieval."""

    from_time: datetime.datetime = Field(..., alias="from", description="start time in ISO format")
    to_time: datetime.datetime = Field(..., alias="to", description="end time in ISO format")
    limit: typing.Optional[int] = Field(100, description="maximum number of screenshots to return")

    @field_validator("limit")
    def validate_limit(cls, v):
        """validate the limit value."""

        if v is not None and (v < 1 or v > 1000):
            raise ValueError("limit must be between 1 and 1000")
        return v

    class Config:
        populate_by_name = True


def parse_relative_time(time_str):
    """parse a relative time string into timedelta components.

    args:
        time_str: string like "1hour", "5hours", "30minutes"

    returns:
        dict with keys for days, hours, minutes, seconds
    """

    time_str = time_str.lower().strip()
    time_components = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}

    # regex patterns for different time units
    patterns = {
        r"(\d+)(?:day|days)": "days",
        r"(\d+)(?:hour|hours|hr|hrs)": "hours",
        r"(\d+)(?:minute|minutes|min|mins)": "minutes",
        r"(\d+)(?:second|seconds|sec|secs)": "seconds"
    }

    # try to match each pattern
    found_match = False
    for pattern, component in patterns.items():
        match = re.search(pattern, time_str)
        if match:
            time_components[component] = int(match.group(1))
            found_match = True

    if not found_match:
        raise ValueError(f"invalid time format: {time_str}")

    return time_components


class MCPServer:
    """model context protocol server for rewinddb.

    this class implements an mcp server that exposes rewinddb functionality
    to genai models through the model context protocol.
    """

    def __init__(self, env_file=None):
        """initialize the mcp server.

        args:
            env_file: optional path to a .env file to load configuration from
        """

        self.app = FastAPI(
            title="RewindDB MCP Server",
            description="Model Context Protocol server for RewindDB",
            version="0.1.0",
        )

        # add cors middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # store env_file path
        self.env_file = env_file

        # initialize database connection
        self.db = None

        # register routes
        self.register_routes()

    def register_routes(self):
        """register api routes."""

        # mcp protocol routes
        @self.app.get("/mcp/tools")
        async def list_tools():
            """list available tools."""

            return {
                "tools": [
                    {
                        "name": "get_transcripts_relative",
                        "description": "Get audio transcripts from a relative time period",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "time_period": {
                                    "type": "string",
                                    "description": "Relative time period (e.g., '1hour', '30minutes', '1day')"
                                }
                            },
                            "required": ["time_period"]
                        }
                    },
                    {
                        "name": "get_transcripts_absolute",
                        "description": "Get audio transcripts from a specific time range",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "from": {
                                    "type": "string",
                                    "format": "date-time",
                                    "description": "Start time in ISO format"
                                },
                                "to": {
                                    "type": "string",
                                    "format": "date-time",
                                    "description": "End time in ISO format"
                                }
                            },
                            "required": ["from", "to"]
                        }
                    },
                    {
                        "name": "get_screenshot",
                        "description": "Get a single screenshot by frame ID",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "frame_id": {
                                    "type": "integer",
                                    "description": "ID of the screenshot frame to retrieve"
                                }
                            },
                            "required": ["frame_id"]
                        }
                    },
                    {
                        "name": "get_screenshots_relative",
                        "description": "Get screenshots from a relative time period",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "time_period": {
                                    "type": "string",
                                    "description": "Relative time period (e.g., '1hour', '30minutes', '1day')"
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of screenshots to return",
                                    "default": 100
                                }
                            },
                            "required": ["time_period"]
                        }
                    },
                    {
                        "name": "get_screenshots_absolute",
                        "description": "Get screenshots from a specific time range",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "from": {
                                    "type": "string",
                                    "format": "date-time",
                                    "description": "Start time in ISO format"
                                },
                                "to": {
                                    "type": "string",
                                    "format": "date-time",
                                    "description": "End time in ISO format"
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of screenshots to return",
                                    "default": 100
                                }
                            },
                            "required": ["from", "to"]
                        }
                    },
                    {
                        "name": "search",
                        "description": "Search for keywords across both audio and screen data",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "keyword": {
                                    "type": "string",
                                    "description": "Keyword to search for"
                                },
                                "relative": {
                                    "type": "string",
                                    "description": "Relative time period (e.g., '1day', '7days')"
                                },
                                "from": {
                                    "type": "string",
                                    "format": "date-time",
                                    "description": "Start time in ISO format"
                                },
                                "to": {
                                    "type": "string",
                                    "format": "date-time",
                                    "description": "End time in ISO format"
                                }
                            },
                            "required": ["keyword"]
                        }
                    }
                ]
            }

        @self.app.get("/mcp/resources")
        async def list_resources():
            """list available resources."""

            return {
                "resources": []  # no resources for now, just tools
            }

        @self.app.post("/mcp/tools/{tool_name}")
        async def execute_tool(tool_name: str, request: Request):
            """execute a tool with the given parameters."""

            # ensure database connection
            await self.ensure_db_connection()

            # parse request body
            try:
                body = await request.json()
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"invalid json: {str(e)}")

            # execute the requested tool
            if tool_name == "get_transcripts_relative":
                # validate parameters
                try:
                    params = RelativeTimeParams(**body)
                except pydantic.ValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))

                # parse relative time
                try:
                    time_components = parse_relative_time(params.time_period)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

                # get transcripts
                try:
                    transcripts = self.db.get_audio_transcripts_relative(**time_components)
                    return self.format_transcripts(transcripts)
                except HTTPException:
                    # Re-raise HTTP exceptions without wrapping them
                    raise
                except Exception as e:
                    logger.error(f"error getting transcripts: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"error getting transcripts: {str(e)}")

            elif tool_name == "get_transcripts_absolute":
                # validate parameters
                try:
                    params = AbsoluteTimeParams(**body)
                except pydantic.ValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))

                # get transcripts
                try:
                    transcripts = self.db.get_audio_transcripts_absolute(
                        params.from_time, params.to_time
                    )
                    return self.format_transcripts(transcripts)
                except HTTPException:
                    # Re-raise HTTP exceptions without wrapping them
                    raise
                except Exception as e:
                    logger.error(f"error getting transcripts: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"error getting transcripts: {str(e)}")

            elif tool_name == "search":
                # validate parameters
                try:
                    params = SearchParams(**body)
                except pydantic.ValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))

                # perform search based on parameters
                try:
                    if params.relative:
                        # search with relative time
                        time_components = parse_relative_time(params.relative)
                        days = (
                            time_components["days"] +
                            time_components["hours"] / 24 +
                            time_components["minutes"] / (24 * 60) +
                            time_components["seconds"] / (24 * 60 * 60)
                        )
                        results = self.db.search(params.keyword, days=days)
                    elif params.from_time and params.to_time:
                        # search with absolute time range
                        # get audio transcripts for the time range
                        audio_transcripts = self.db.get_audio_transcripts_absolute(
                            params.from_time, params.to_time
                        )

                        # get screen ocr for the time range
                        screen_ocr = self.db.get_screen_ocr_absolute(
                            params.from_time, params.to_time
                        )

                        # filter results for the keyword
                        audio_results = [
                            item for item in audio_transcripts
                            if params.keyword.lower() in item['word'].lower()
                        ]

                        screen_results = [
                            item for item in screen_ocr
                            if params.keyword.lower() in item['text'].lower()
                        ]

                        results = {
                            'audio': audio_results,
                            'screen': screen_results
                        }
                    else:
                        # default to 7 days if no time range specified
                        results = self.db.search(params.keyword)

                    return self.format_search_results(results)
                except HTTPException:
                    # Re-raise HTTP exceptions without wrapping them
                    raise
                except Exception as e:
                    logger.error(f"error searching: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"error searching: {str(e)}")

            elif tool_name == "get_screenshot":
                # validate parameters
                try:
                    params = ScreenshotByIdParams(**body)
                except pydantic.ValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))

                # get screenshot
                try:
                    screenshot = self.db.get_screenshot_by_id(params.frame_id)
                    if not screenshot:
                        logger.warning(f"screenshot with id {params.frame_id} not found")
                        raise HTTPException(status_code=404, detail=f"screenshot with id {params.frame_id} not found")

                    return self.format_screenshot(screenshot)
                except HTTPException:
                    # Re-raise HTTP exceptions (like 404) without wrapping them
                    raise
                except Exception as e:
                    logger.error(f"error getting screenshot: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"error getting screenshot: {str(e)}")

            elif tool_name == "get_screenshots_relative":
                # validate parameters
                try:
                    params = ScreenshotsRelativeParams(**body)
                except pydantic.ValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))

                # parse relative time
                try:
                    time_components = parse_relative_time(params.time_period)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

                # get screenshots
                try:
                    screenshots = self.db.get_screenshots_relative(**time_components, limit=params.limit)
                    return self.format_screenshots(screenshots)
                except HTTPException:
                    # Re-raise HTTP exceptions without wrapping them
                    raise
                except Exception as e:
                    logger.error(f"error getting screenshots: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"error getting screenshots: {str(e)}")

            elif tool_name == "get_screenshots_absolute":
                # validate parameters
                try:
                    params = ScreenshotsAbsoluteParams(**body)
                except pydantic.ValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))

                # get screenshots
                try:
                    screenshots = self.db.get_screenshots_absolute(
                        params.from_time, params.to_time, limit=params.limit
                    )
                    return self.format_screenshots(screenshots)
                except HTTPException:
                    # Re-raise HTTP exceptions without wrapping them
                    raise
                except Exception as e:
                    logger.error(f"error getting screenshots: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"error getting screenshots: {str(e)}")

            else:
                raise HTTPException(status_code=404, detail=f"tool '{tool_name}' not found")

        @self.app.get("/mcp/resources/{resource_uri:path}")
        async def access_resource(resource_uri: str):
            """access a resource by uri."""

            # no resources implemented yet
            raise HTTPException(status_code=404, detail=f"resource '{resource_uri}' not found")

        # health check endpoint
        @self.app.get("/health")
        async def health_check():
            """check server health."""

            return {"status": "ok"}

    async def ensure_db_connection(self):
        """ensure database connection is established."""

        if self.db is None:
            try:
                self.db = rewinddb.RewindDB(self.env_file)
                logger.info("connected to rewinddb")
            except Exception as e:
                logger.error(f"failed to connect to rewinddb: {e}")
                raise HTTPException(status_code=500, detail=f"database connection error: {str(e)}")

    def format_transcripts(self, transcripts):
        """format transcript data for api response.

        args:
            transcripts: list of transcript dictionaries from rewinddb

        returns:
            formatted transcript data suitable for genai models
        """

        if not transcripts:
            return {"transcripts": []}

        # group words by audio session
        sessions = {}
        for item in transcripts:
            audio_id = item['audio_id']
            if audio_id not in sessions:
                sessions[audio_id] = {
                    'start_time': item['audio_start_time'],
                    'words': []
                }
            sessions[audio_id]['words'].append(item)

        # format each session
        formatted_sessions = []
        for audio_id, session in sessions.items():
            # sort words by time offset
            words = sorted(session['words'], key=lambda x: x['time_offset'])

            # extract text and timestamps
            formatted_session = {
                'start_time': session['start_time'].isoformat(),
                'audio_id': audio_id,
                'text': ' '.join(word['word'] for word in words),
                'words': [
                    {
                        'word': word['word'],
                        'time': (session['start_time'] + datetime.timedelta(milliseconds=word['time_offset'])).isoformat(),
                        'duration': word.get('duration', 0)
                    }
                    for word in words
                ]
            }

            formatted_sessions.append(formatted_session)

        return {"transcripts": formatted_sessions}

    def format_search_results(self, results):
        """format search results for api response.

        args:
            results: search results dictionary from rewinddb

        returns:
            formatted search results suitable for genai models
        """

        formatted_results = {
            'audio': [],
            'screen': []
        }

        # format audio results
        if results['audio']:
            # group words by audio session
            sessions = {}
            for item in results['audio']:
                audio_id = item['audio_id']
                if audio_id not in sessions:
                    sessions[audio_id] = {
                        'start_time': item['audio_start_time'],
                        'words': [item],
                        'hit_indices': [0]  # index of the hit word in this session's words list
                    }
                else:
                    sessions[audio_id]['words'].append(item)
                    sessions[audio_id]['hit_indices'].append(len(sessions[audio_id]['words']) - 1)

            # format each session
            for audio_id, session in sessions.items():
                # sort words by time offset
                words = sorted(session['words'], key=lambda x: x['time_offset'])

                # get text and context
                word_texts = [word['word'] for word in words]

                # for each hit in this session, show context
                for hit_idx in session['hit_indices']:
                    context_start = max(0, hit_idx - 3)  # 3 words before
                    context_end = min(len(word_texts), hit_idx + 4)  # 3 words after

                    # format the context
                    context_words = word_texts[context_start:context_end]
                    context_text = " ".join(context_words)

                    # add the hit to the results
                    formatted_results['audio'].append({
                        'time': session['start_time'].isoformat(),
                        'text': context_text,
                        'audio_id': audio_id
                    })

        # format screen results
        if results['screen']:
            # group by frame
            frames = {}
            for item in results['screen']:
                frame_id = item['frame_id']
                if frame_id not in frames:
                    frames[frame_id] = {
                        'time': item['frame_time'],
                        'application': item['application'],
                        'window': item['window'],
                        'texts': [item['text']]
                    }
                else:
                    frames[frame_id]['texts'].append(item['text'])

            # format each frame
            for frame_id, frame in frames.items():
                # ensure frame time is not None before calling isoformat()
                frame_time = frame['time'].isoformat() if frame['time'] else None

                formatted_results['screen'].append({
                    'time': frame_time,
                    'application': frame['application'],
                    'window': frame['window'],
                    'text': '\n'.join(frame['texts']),
                    'frame_id': frame_id
                })

        return formatted_results

    def get_image_path(self, image_file: str) -> typing.Optional[str]:
        """get the full path to an image file.

        args:
            image_file: the image file name from the database

        returns:
            the full path to the image file or none if not found
        """

        # check if the image file is a valid path
        if not image_file:
            return None

        # get the rewind data directory from the database path
        db_path = self.db.db_path
        data_dir = os.path.dirname(os.path.dirname(db_path))

        # construct the path to the image file
        # image files are stored in chunks directory with a specific structure
        # the exact path depends on the image_file format

        # try different possible locations
        possible_paths = [
            # direct path if image_file is a full path
            image_file,
            # path relative to data directory
            os.path.join(data_dir, image_file),
            # path in chunks directory
            os.path.join(data_dir, "chunks", image_file)
        ]

        # check if any of the paths exist
        for path in possible_paths:
            if os.path.exists(path):
                return path

        # if no path exists, log a warning and return none
        logger.warning(f"image file not found: {image_file}")
        return None

    def encode_image_base64(self, image_path: str) -> typing.Optional[str]:
        """encode an image file as base64.

        args:
            image_path: path to the image file

        returns:
            base64 encoded image or none if file not found
        """

        if not image_path or not os.path.exists(image_path):
            return None

        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

            # determine the mime type based on file extension
            file_ext = os.path.splitext(image_path)[1].lower()
            mime_type = "image/jpeg"  # default

            if file_ext == ".png":
                mime_type = "image/png"
            elif file_ext in [".jpg", ".jpeg"]:
                mime_type = "image/jpeg"
            elif file_ext == ".gif":
                mime_type = "image/gif"
            elif file_ext == ".webp":
                mime_type = "image/webp"

            # return data url format
            return f"data:{mime_type};base64,{encoded_string}"
        except Exception as e:
            logger.error(f"error encoding image: {e}")
            return None

    def format_screenshot(self, screenshot: dict) -> dict:
        """format a single screenshot for api response.

        args:
            screenshot: screenshot dictionary from rewinddb

        returns:
            formatted screenshot data suitable for genai models
        """

        if not screenshot:
            return {"screenshot": None}

        # get the image path
        image_path = self.get_image_path(screenshot.get('image_file'))

        # encode the image as base64
        image_data = self.encode_image_base64(image_path) if image_path else None

        # format the result
        result = {
            "screenshot": {
                "frame_id": screenshot.get('frame_id'),
                "time": screenshot.get('frame_time').isoformat(),
                "application": screenshot.get('application'),
                "window": screenshot.get('window'),
                "image_data": image_data
            }
        }

        return result

    def format_screenshots(self, screenshots: typing.List[dict]) -> dict:
        """format multiple screenshots for api response.

        args:
            screenshots: list of screenshot dictionaries from rewinddb

        returns:
            formatted screenshots data suitable for genai models
        """

        if not screenshots:
            return {"screenshots": []}

        formatted_screenshots = []

        for screenshot in screenshots:
            # get the image path
            image_path = self.get_image_path(screenshot.get('image_file'))

            # encode the image as base64
            image_data = self.encode_image_base64(image_path) if image_path else None

            # format the screenshot
            formatted_screenshot = {
                "frame_id": screenshot.get('frame_id'),
                "time": screenshot.get('frame_time').isoformat(),
                "application": screenshot.get('application'),
                "window": screenshot.get('window'),
                "image_data": image_data
            }

            formatted_screenshots.append(formatted_screenshot)

        return {"screenshots": formatted_screenshots}

    def start(self, host="0.0.0.0", port=8000):
        """start the server.

        args:
            host: host to bind to
            port: port to bind to
        """

        uvicorn.run(self.app, host=host, port=port)

    def cleanup(self):
        """clean up resources."""

        if self.db:
            self.db.close()
            logger.info("closed database connection")


def parse_arguments():
    """parse command line arguments.

    returns:
        parsed argument namespace
    """

    parser = argparse.ArgumentParser(
        description="model context protocol server for rewinddb",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("--host", default="0.0.0.0", help="host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="port to bind to")
    parser.add_argument("--debug", action="store_true", help="enable debug logging")
    parser.add_argument("--env-file", metavar="FILE", help="path to .env file with database configuration")

    return parser.parse_args()


def main():
    """main entry point."""

    args = parse_arguments()

    # set log level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # create and start server
    server = MCPServer(args.env_file)

    try:
        logger.info(f"starting mcp server on {args.host}:{args.port}")
        server.start(host=args.host, port=args.port)
    except KeyboardInterrupt:
        logger.info("shutting down server")
    finally:
        server.cleanup()


if __name__ == "__main__":
    main()