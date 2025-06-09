#!/usr/bin/env python
"""
MCP-compliant STDIO server for RewindDB.

This server implements the Model Context Protocol (MCP) specification using
JSON-RPC 2.0 protocol over STDIO transport. It provides tools for accessing
RewindDB functionality.

The server exposes the following tools:
- get_transcripts_relative: Get audio transcripts from a relative time period
- get_transcripts_absolute: Get audio transcripts from a specific time window
- search_transcripts: Search through audio transcripts
- search_screen_ocr: Search through OCR screen content
- get_screen_ocr_relative: Get all OCR content from a relative time period
- get_screen_ocr_absolute: Get all OCR content from a specific time window
- get_ocr_applications_relative: Get all applications with OCR data from a relative time period
- get_ocr_applications_absolute: Get all applications with OCR data from a specific time window
- get_activity_stats: Get activity statistics
- get_transcript_by_id: Get specific transcript by ID
"""

import asyncio
import json
import sys
import logging
import argparse
import datetime
import re
from typing import Any, Dict, List, Optional, Union
try:
    from zoneinfo import ZoneInfo
    import time
except ImportError:
    # Fallback for Python < 3.9
    from datetime import timezone
    ZoneInfo = None
    import time

import rewinddb
from rewinddb.config import load_config

# Logger will be configured in main() after parsing arguments
logger = logging.getLogger("mcp_stdio")

# Global database connection
db: Optional[rewinddb.RewindDB] = None

# Global system timezone (detected at startup)
system_timezone: Optional[str] = None


def detect_system_timezone() -> str:
    """Detect the system's local timezone."""
    global system_timezone
    if system_timezone is not None:
        return system_timezone

    try:
        import os

        # Method 1: Check TZ environment variable
        if 'TZ' in os.environ:
            system_timezone = os.environ['TZ']
            logger.info(f"Detected timezone from TZ env var: {system_timezone}")
            return system_timezone

        # Method 2: Try to read /etc/timezone (Linux)
        try:
            with open('/etc/timezone', 'r') as f:
                system_timezone = f.read().strip()
                logger.info(f"Detected timezone from /etc/timezone: {system_timezone}")
                return system_timezone
        except (FileNotFoundError, PermissionError):
            pass

        # Method 3: Try to read /etc/localtime symlink (Linux/macOS)
        try:
            import os
            localtime_path = '/etc/localtime'
            if os.path.islink(localtime_path):
                link_target = os.readlink(localtime_path)
                # Extract timezone from path like /usr/share/zoneinfo/America/Chicago
                if 'zoneinfo/' in link_target:
                    system_timezone = link_target.split('zoneinfo/')[-1]
                    logger.info(f"Detected timezone from /etc/localtime symlink: {system_timezone}")
                    return system_timezone
        except Exception:
            pass

        # Method 4: macOS specific - use systemsetup command
        try:
            import subprocess
            result = subprocess.run(['systemsetup', '-gettimezone'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # Output format: "Time Zone: America/Chicago"
                output = result.stdout.strip()
                if 'Time Zone:' in output:
                    system_timezone = output.split('Time Zone:')[-1].strip()
                    logger.info(f"Detected timezone from macOS systemsetup: {system_timezone}")
                    return system_timezone
        except Exception:
            pass

        # Method 5: Use Python's time module to get UTC offset
        import time
        if time.daylight:
            offset_seconds = time.altzone
        else:
            offset_seconds = time.timezone

        offset_hours = -offset_seconds // 3600
        offset_minutes = (-offset_seconds % 3600) // 60

        if offset_minutes == 0:
            system_timezone = f"UTC{offset_hours:+d}"
        else:
            system_timezone = f"UTC{offset_hours:+d}:{offset_minutes:02d}"

        logger.info(f"Detected timezone from UTC offset: {system_timezone}")
        return system_timezone

    except Exception as e:
        logger.warning(f"Failed to detect system timezone: {e}, using UTC")
        system_timezone = "UTC"
        return system_timezone


def parse_datetime_with_timezone(time_str: str, timezone: Optional[str] = None) -> datetime.datetime:
    """Parse a datetime string and convert to UTC.

    Args:
        time_str: ISO format datetime string, optionally with timezone
        timezone: Optional timezone name (e.g., 'America/Chicago') if time_str has no timezone
                 If None, will use detected system timezone

    Returns:
        datetime object in UTC
    """
    try:
        # Try to parse as timezone-aware datetime first
        dt = datetime.datetime.fromisoformat(time_str)

        # If no timezone info, determine what timezone to use
        if dt.tzinfo is None:
            # Use provided timezone, or fall back to system timezone
            tz_to_use = timezone or detect_system_timezone()
            logger.debug(f"No timezone in '{time_str}', using timezone: {tz_to_use}")

            if ZoneInfo and tz_to_use != "UTC":
                try:
                    if tz_to_use.startswith("UTC"):
                        # Handle UTC+X or UTC-X format
                        if tz_to_use == "UTC":
                            local_tz = datetime.timezone.utc
                        else:
                            # Parse UTC offset (e.g., "UTC-6" or "UTC+5")
                            if ':' in tz_to_use:
                                # Handle UTC+5:30 format
                                offset_part = tz_to_use[3:]
                                sign = 1 if offset_part[0] == '+' else -1
                                hours, minutes = map(int, offset_part[1:].split(':'))
                                total_minutes = sign * (hours * 60 + minutes)
                                local_tz = datetime.timezone(datetime.timedelta(minutes=total_minutes))
                            else:
                                # Handle UTC+5 format
                                sign = 1 if tz_to_use[3] == '+' else -1
                                hours = int(tz_to_use[4:])
                                local_tz = datetime.timezone(datetime.timedelta(hours=sign * hours))
                    else:
                        # Try to use as IANA timezone name
                        local_tz = ZoneInfo(tz_to_use)
                    dt = dt.replace(tzinfo=local_tz)
                    logger.debug(f"Applied timezone '{tz_to_use}' to '{time_str}' -> {dt}")
                except Exception as e:
                    logger.warning(f"Failed to apply timezone '{tz_to_use}': {e}, using UTC")
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
            else:
                # Fallback: assume UTC
                logger.debug(f"No timezone support or UTC specified, treating '{time_str}' as UTC")
                dt = dt.replace(tzinfo=datetime.timezone.utc)

        # Convert to UTC
        utc_dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        logger.debug(f"Final UTC conversion: '{time_str}' -> {utc_dt}")
        return utc_dt

    except ValueError as e:
        raise ValueError(f"Invalid datetime format '{time_str}': {e}")


def parse_smart_datetime(time_str: str, timezone: Optional[str] = None) -> datetime.datetime:
    """Parse a datetime string with smart local date handling.

    This function handles cases where users provide times that should be
    interpreted as local time, even if they have timezone offsets.

    Args:
        time_str: Time string (e.g., "15:00:00", "2025-06-05T15:00:00", or "2025-06-05T15:00:00-06:00")
        timezone: Optional timezone to apply if not specified in time_str

    Returns:
        datetime object in UTC
    """
    original_time_str = time_str

    # If the time string is just a time (HH:MM or HH:MM:SS), add today's local date
    if ':' in time_str and 'T' not in time_str and '-' not in time_str:
        # Get current local date
        local_tz = detect_system_timezone()
        if ZoneInfo and local_tz != "UTC" and not local_tz.startswith("UTC"):
            try:
                tz = ZoneInfo(local_tz)
                now_local = datetime.datetime.now(tz)
                today_str = now_local.strftime('%Y-%m-%d')
                time_str = f"{today_str}T{time_str}"
                logger.debug(f"Added local date to time: {time_str}")
            except Exception:
                # Fallback to system local time
                now_local = datetime.datetime.now()
                today_str = now_local.strftime('%Y-%m-%d')
                time_str = f"{today_str}T{time_str}"
                logger.debug(f"Added system date to time: {time_str}")

    # Special handling: If user provides a timezone-aware timestamp,
    # treat the datetime part as local time instead of respecting the offset
    if ('+' in time_str or ('-' in time_str and time_str.count('-') > 2)):
        try:
            # Parse the full timestamp to extract the naive datetime part
            dt_with_tz = datetime.datetime.fromisoformat(time_str)
            naive_dt = dt_with_tz.replace(tzinfo=None)

            # Get current local date to check if user meant "today"
            local_tz_name = timezone or detect_system_timezone()
            if ZoneInfo and local_tz_name != "UTC" and not local_tz_name.startswith("UTC"):
                try:
                    local_tz = ZoneInfo(local_tz_name)
                    now_local = datetime.datetime.now(local_tz)
                    today_local = now_local.date()

                    # If they're asking for tomorrow's date but it's still today locally,
                    # adjust to today
                    if naive_dt.date() == today_local + datetime.timedelta(days=1):
                        time_part = naive_dt.time()
                        naive_dt = datetime.datetime.combine(today_local, time_part)
                        logger.info(f"Adjusted future date to local today: {naive_dt}")

                    # Apply local timezone to the naive datetime
                    local_dt = naive_dt.replace(tzinfo=local_tz)
                    utc_dt = local_dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)

                    logger.debug(f"Treated '{original_time_str}' as local time: {naive_dt} {local_tz_name} -> {utc_dt} UTC")
                    return utc_dt

                except Exception as e:
                    logger.warning(f"Failed to apply local timezone to '{time_str}': {e}")

        except ValueError:
            # If parsing fails, fall through to regular parsing
            pass

    # If no timezone specified in the string and user is asking for a future date,
    # check if they might mean "today" in local time
    if 'T' in time_str and '+' not in time_str and '-' not in time_str.split('T')[1]:
        # Parse the date part
        date_part = time_str.split('T')[0]
        try:
            requested_date = datetime.datetime.strptime(date_part, '%Y-%m-%d').date()

            # Get current local date
            local_tz = detect_system_timezone()
            if ZoneInfo and local_tz != "UTC" and not local_tz.startswith("UTC"):
                try:
                    tz = ZoneInfo(local_tz)
                    now_local = datetime.datetime.now(tz)
                    today_local = now_local.date()

                    # If they're asking for tomorrow's date but it's still today locally,
                    # they probably mean today
                    if requested_date == today_local + datetime.timedelta(days=1):
                        time_part = time_str.split('T')[1]
                        time_str = f"{today_local.strftime('%Y-%m-%d')}T{time_part}"
                        logger.info(f"Adjusted future date to local today: {time_str}")
                except Exception:
                    pass
        except ValueError:
            pass

    # Fall back to regular parsing
    return parse_datetime_with_timezone(time_str, timezone)


def parse_relative_time(time_str: str) -> Dict[str, int]:
    """Parse a relative time string into timedelta components."""
    time_str = time_str.lower().strip()
    time_components = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}

    # Short form pattern (e.g., "5h", "3m", "10d", "2w")
    short_patterns = {
        r"^(\d+)w$": lambda x: {"days": int(x) * 7},
        r"^(\d+)d$": lambda x: {"days": int(x)},
        r"^(\d+)h$": lambda x: {"hours": int(x)},
        r"^(\d+)m$": lambda x: {"minutes": int(x)},
        r"^(\d+)s$": lambda x: {"seconds": int(x)}
    }

    # Check for short form patterns first
    for pattern, handler in short_patterns.items():
        match = re.search(pattern, time_str)
        if match:
            component_values = handler(match.group(1))
            for component, value in component_values.items():
                time_components[component] = value
            return time_components

    # Long form patterns
    patterns = {
        r"(\d+)(?:day|days)": "days",
        r"(\d+)(?:hour|hours|hr|hrs)": "hours",
        r"(\d+)(?:minute|minutes|min|mins)": "minutes",
        r"(\d+)(?:second|seconds|sec|secs)": "seconds",
        r"(\d+)(?:week|weeks)": "weeks"
    }

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
        raise ValueError(f"Invalid time format: {time_str}")

    return time_components


def ensure_db_connection(env_file: Optional[str] = None) -> rewinddb.RewindDB:
    """Ensure database connection is established."""
    global db
    if db is None:
        try:
            db = rewinddb.RewindDB(env_file)
            logger.info("Connected to RewindDB")
        except Exception as e:
            logger.error(f"Failed to connect to RewindDB: {e}")
            raise Exception(f"Database connection error: {str(e)}")
    return db


def format_transcripts(transcripts: List[Dict]) -> Dict[str, Any]:
    """Format transcript data for MCP response."""
    if not transcripts:
        return {"transcripts": []}

    # Group words by audio session
    sessions = {}
    for item in transcripts:
        audio_id = item['audio_id']
        if audio_id not in sessions:
            sessions[audio_id] = {
                'start_time': item['audio_start_time'],
                'words': []
            }
        sessions[audio_id]['words'].append(item)

    # Format each session
    formatted_sessions = []
    for audio_id, session in sessions.items():
        # Sort words by time offset
        words = sorted(session['words'], key=lambda x: x['time_offset'])

        # Extract text and timestamps
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


def format_search_results(results: Dict[str, List[Dict]]) -> Dict[str, Any]:
    """Format search results for MCP response."""
    formatted_results = {
        'audio': [],
        'screen': []
    }

    # Format audio results
    if results.get('audio'):
        # Group words by audio session
        sessions = {}
        for item in results['audio']:
            audio_id = item['audio_id']
            if audio_id not in sessions:
                sessions[audio_id] = {
                    'start_time': item['audio_start_time'],
                    'words': [item],
                    'hit_indices': [0]
                }
            else:
                sessions[audio_id]['words'].append(item)
                sessions[audio_id]['hit_indices'].append(len(sessions[audio_id]['words']) - 1)

        # Format each session
        for audio_id, session in sessions.items():
            # Sort words by time offset
            words = sorted(session['words'], key=lambda x: x['time_offset'])

            # Get text and context
            word_texts = [word['word'] for word in words]

            # For each hit in this session, show context
            for hit_idx in session['hit_indices']:
                context_start = max(0, hit_idx - 3)  # 3 words before
                context_end = min(len(word_texts), hit_idx + 4)  # 3 words after

                # Format the context
                context_words = word_texts[context_start:context_end]
                context_text = " ".join(context_words)

                # Add the hit to the results
                formatted_results['audio'].append({
                    'time': session['start_time'].isoformat(),
                    'text': context_text,
                    'audio_id': audio_id
                })

    # Format screen results
    if results.get('screen'):
        # Group by frame
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

        # Format each frame
        for frame_id, frame in frames.items():
            # Ensure frame time is not None before calling isoformat()
            frame_time = frame['time'].isoformat() if frame['time'] else None

            formatted_results['screen'].append({
                'time': frame_time,
                'application': frame['application'],
                'window': frame['window'],
                'text': '\n'.join(frame['texts']),
                'frame_id': frame_id
            })

    return formatted_results


class MCPServer:
    """MCP Server implementation using JSON-RPC 2.0 over STDIO."""

    def __init__(self, env_file: Optional[str] = None):
        self.env_file = env_file
        self.tools = {
            "get_transcripts_relative": {
                "description": "Get audio transcripts from a relative time period. Returns transcript sessions with full text content suitable for analysis, summarization, or detailed review. Each session includes complete transcript text and word-by-word timing.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "time_period": {
                            "type": "string",
                            "description": "Time period like '1hour', '30minutes', '1day', '1week'",
                            "pattern": r"^\d+(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs|week|weeks)$"
                        }
                    },
                    "required": ["time_period"]
                }
            },
            "get_transcripts_absolute": {
                "description": "**PRIMARY TOOL for meeting summaries**: Get complete audio transcripts from a specific time window (e.g., '3 PM meeting'). This is the FIRST tool to use when asked to summarize meetings, calls, or conversations from specific times. Returns full transcript sessions with complete text content ready for analysis and summarization.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "from": {
                            "type": "string",
                            "description": "Start time in ISO format. Can include timezone (e.g., '2024-01-15T14:00:00-06:00') or use timezone parameter"
                        },
                        "to": {
                            "type": "string",
                            "description": "End time in ISO format. Can include timezone (e.g., '2024-01-15T15:00:00-06:00') or use timezone parameter"
                        },
                        "timezone": {
                            "type": "string",
                            "description": "Optional timezone name (e.g., 'America/Chicago') if from/to times don't include timezone info"
                        }
                    },
                    "required": ["from", "to"]
                }
            },
            "search_transcripts": {
                "description": "Search for specific keywords/phrases in transcripts. **NOT for meeting summaries** - use get_transcripts_absolute instead when asked to summarize meetings from specific times. This tool finds keyword matches with context snippets, useful for finding specific topics or names mentioned across multiple sessions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "Keyword to search for"
                        },
                        "relative": {
                            "type": "string",
                            "description": "Optional relative time period like '1hour', '1day', '1week'",
                            "pattern": r"^\d+(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs|week|weeks)$"
                        },
                        "from": {
                            "type": "string",
                            "description": "Optional start time in ISO format. Can include timezone or use timezone parameter"
                        },
                        "to": {
                            "type": "string",
                            "description": "Optional end time in ISO format. Can include timezone or use timezone parameter"
                        },
                        "timezone": {
                            "type": "string",
                            "description": "Optional timezone name (e.g., 'America/Chicago') if from/to times don't include timezone info"
                        }
                    },
                    "required": ["keyword"]
                }
            },
            "get_activity_stats": {
                "description": "Get activity statistics for a time period",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "time_period": {
                            "type": "string",
                            "description": "Time period like '1hour', '30minutes', '1day', '1week'",
                            "pattern": r"^\d+(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs|week|weeks)$"
                        }
                    },
                    "required": ["time_period"]
                }
            },
            "get_transcript_by_id": {
                "description": "**FOLLOW-UP TOOL**: Get complete transcript content by audio ID. Use this AFTER get_transcripts_absolute to retrieve full transcript text for summarization. Essential second step when the first tool shows preview text that needs complete content for proper analysis.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "audio_id": {
                            "type": "integer",
                            "description": "The audio ID to retrieve"
                        }
                    },
                    "required": ["audio_id"]
                }
            },
            "search_screen_ocr": {
                "description": "Search through OCR screen content for keywords. Finds text that appeared on screen during specific time periods. Use this to find what was displayed on screen, applications used, or visual content during meetings or work sessions. Complements audio transcripts by showing what was visible.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "Keyword to search for in screen OCR content"
                        },
                        "relative": {
                            "type": "string",
                            "description": "Optional relative time period like '1hour', '1day', '1week'",
                            "pattern": r"^\d+(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs|week|weeks)$"
                        },
                        "from": {
                            "type": "string",
                            "description": "Optional start time in ISO format. Can include timezone or use timezone parameter"
                        },
                        "to": {
                            "type": "string",
                            "description": "Optional end time in ISO format. Can include timezone or use timezone parameter"
                        },
                        "timezone": {
                            "type": "string",
                            "description": "Optional timezone name (e.g., 'America/Chicago') if from/to times don't include timezone info"
                        },
                        "application": {
                            "type": "string",
                            "description": "Optional application name to filter results"
                        }
                    },
                    "required": ["keyword"]
                }
            },
            "get_screen_ocr_relative": {
                "description": "Get all screen OCR content from a relative time period. Returns complete OCR text that appeared on screen during the specified time window, useful for reviewing what was displayed without needing to search for specific keywords.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "time_period": {
                            "type": "string",
                            "description": "Time period like '1hour', '30minutes', '1day', '1week'",
                            "pattern": r"^\d+(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs|week|weeks)$"
                        },
                        "application": {
                            "type": "string",
                            "description": "Optional application name to filter results"
                        }
                    },
                    "required": ["time_period"]
                }
            },
            "get_screen_ocr_absolute": {
                "description": "Get all screen OCR content from a specific time window. Returns complete OCR text that appeared on screen during the specified absolute time range, useful for reviewing what was displayed during meetings, work sessions, or specific time periods.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "from": {
                            "type": "string",
                            "description": "Start time in ISO format. Can include timezone (e.g., '2024-01-15T14:00:00-06:00') or use timezone parameter"
                        },
                        "to": {
                            "type": "string",
                            "description": "End time in ISO format. Can include timezone (e.g., '2024-01-15T15:00:00-06:00') or use timezone parameter"
                        },
                        "timezone": {
                            "type": "string",
                            "description": "Optional timezone name (e.g., 'America/Chicago') if from/to times don't include timezone info"
                        },
                        "application": {
                            "type": "string",
                            "description": "Optional application name to filter results"
                        }
                    },
                    "required": ["from", "to"]
                }
            },
            "get_ocr_applications_relative": {
                "description": "Get all application names that have OCR data from a relative time period. Returns a list of applications that were active and had screen content captured during the specified time window, useful for discovering what apps were used.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "time_period": {
                            "type": "string",
                            "description": "Time period like '1hour', '30minutes', '1day', '1week'",
                            "pattern": r"^\d+(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs|week|weeks)$"
                        }
                    },
                    "required": ["time_period"]
                }
            },
            "get_ocr_applications_absolute": {
                "description": "Get all application names that have OCR data from a specific time window. Returns a list of applications that were active and had screen content captured during the specified absolute time range, useful for discovering what apps were used during meetings or work sessions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "from": {
                            "type": "string",
                            "description": "Start time in ISO format. Can include timezone (e.g., '2024-01-15T14:00:00-06:00') or use timezone parameter"
                        },
                        "to": {
                            "type": "string",
                            "description": "End time in ISO format. Can include timezone (e.g., '2024-01-15T15:00:00-06:00') or use timezone parameter"
                        },
                        "timezone": {
                            "type": "string",
                            "description": "Optional timezone name (e.g., 'America/Chicago') if from/to times don't include timezone info"
                        }
                    },
                    "required": ["from", "to"]
                }
            }
        }

        self.resources = {
            "rewinddb://transcripts": {
                "name": "Audio Transcripts",
                "description": "Access to audio transcript data",
                "mimeType": "application/json"
            },
            "rewinddb://activity": {
                "name": "Activity Data",
                "description": "Access to computer activity data",
                "mimeType": "application/json"
            }
        }

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming JSON-RPC 2.0 request."""
        try:
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")

            logger.info(f"Handling request: {method}")

            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {},
                            "resources": {}
                        },
                        "serverInfo": {
                            "name": "rewinddb-mcp",
                            "version": "1.0.0"
                        }
                    }
                }

            elif method == "notifications/initialized":
                # No response needed for notification
                return None

            elif method == "tools/list":
                tools_list = []
                for name, tool_def in self.tools.items():
                    tools_list.append({
                        "name": name,
                        "description": tool_def["description"],
                        "inputSchema": tool_def["inputSchema"]
                    })

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": tools_list
                    }
                }

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                result = await self.call_tool(tool_name, arguments)

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": result
                            }
                        ]
                    }
                }

            elif method == "resources/list":
                resources_list = []
                for uri, resource_def in self.resources.items():
                    resources_list.append({
                        "uri": uri,
                        "name": resource_def["name"],
                        "description": resource_def["description"],
                        "mimeType": resource_def["mimeType"]
                    })

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "resources": resources_list
                    }
                }

            elif method == "resources/read":
                uri = params.get("uri")
                result = await self.get_resource(uri)

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "text/plain",
                                "text": result
                            }
                        ]
                    }
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Handle tool calls."""
        db = ensure_db_connection(self.env_file)

        if name == "get_transcripts_relative":
            time_period = arguments["time_period"]

            # Validate time period format
            pattern = r"^(\d+)(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs|week|weeks)$"
            if not re.match(pattern, time_period):
                raise ValueError("time_period must be in format like '1hour', '30minutes', '1day', '1week'")

            # Parse relative time
            time_components = parse_relative_time(time_period)

            # Get transcripts
            transcripts = db.get_audio_transcripts_relative(**time_components)
            formatted = format_transcripts(transcripts)

            result = f"Found {len(formatted['transcripts'])} transcript sessions in the last {time_period}:\n\n"
            for i, session in enumerate(formatted['transcripts'][:5]):  # Show first 5
                result += f"Session {i+1} (Audio ID: {session['audio_id']}):\n"
                result += f"Time: {session['start_time']}\n"
                result += f"Text: {session['text'][:200]}{'...' if len(session['text']) > 200 else ''}\n\n"

            return result

        elif name == "get_transcripts_absolute":
            from_time_str = arguments["from"]
            to_time_str = arguments["to"]
            timezone = arguments.get("timezone")

            # Convert string times to UTC datetime using smart parsing
            from_time = parse_smart_datetime(from_time_str, timezone)
            to_time = parse_smart_datetime(to_time_str, timezone)

            # Validate time range
            if from_time >= to_time:
                raise ValueError("'from' time must be before 'to' time")

            # Get transcripts for the absolute time range
            transcripts = db.get_audio_transcripts_absolute(from_time, to_time)
            formatted = format_transcripts(transcripts)

            result = f"Found {len(formatted['transcripts'])} transcript sessions from {from_time_str} to {to_time_str}"
            if timezone:
                result += f" (timezone: {timezone})"
            result += ":\n\n"

            if len(formatted['transcripts']) == 0:
                result += "No transcript sessions found for this time period.\n"
                result += "Try:\n"
                result += "- Expanding the time range\n"
                result += "- Checking if the date/time is correct\n"
                result += "- Using search_transcripts to find content by keywords\n"
                return result

            for i, session in enumerate(formatted['transcripts'][:5]):  # Show first 5
                result += f"Session {i+1} (Audio ID: {session['audio_id']}):\n"
                result += f"Time: {session['start_time']}\n"
                result += f"Text: {session['text'][:200]}{'...' if len(session['text']) > 200 else ''}\n\n"

            if len(formatted['transcripts']) > 5:
                result += f"... and {len(formatted['transcripts']) - 5} more sessions\n"

            # Add guidance for AI tools
            if len(formatted['transcripts']) > 0:
                result += "\n--- AI Tool Guidance ---\n"
                result += "This tool provides transcript previews. For complete analysis:\n"
                result += f"• Use get_transcript_by_id with audio IDs: {', '.join(str(s['audio_id']) for s in formatted['transcripts'][:3])}\n"
                result += "• Each session contains full transcript text suitable for summarization\n"
                result += "• Word-by-word timing is available for detailed analysis\n"

            return result

        elif name == "search_transcripts":
            keyword = arguments["keyword"]
            relative = arguments.get("relative")
            from_time_str = arguments.get("from")
            to_time_str = arguments.get("to")
            timezone = arguments.get("timezone")

            # Convert string times to UTC datetime if provided using smart parsing
            from_time = None
            to_time = None
            if from_time_str:
                from_time = parse_smart_datetime(from_time_str, timezone)
            if to_time_str:
                to_time = parse_smart_datetime(to_time_str, timezone)

            # Perform search based on parameters
            if relative:
                # Search with relative time
                time_components = parse_relative_time(relative)
                days = (
                    time_components["days"] +
                    time_components["hours"] / 24 +
                    time_components["minutes"] / (24 * 60) +
                    time_components["seconds"] / (24 * 60 * 60)
                )
                results = db.search(keyword, days=days)
            elif from_time and to_time:
                # Search with absolute time range
                audio_transcripts = db.get_audio_transcripts_absolute(from_time, to_time)
                screen_ocr = db.get_screen_ocr_absolute(from_time, to_time)

                # Filter results for the keyword
                audio_results = [
                    item for item in audio_transcripts
                    if keyword.lower() in item['word'].lower()
                ]

                screen_results = [
                    item for item in screen_ocr
                    if keyword.lower() in item.get('text', '').lower()
                ]

                results = {
                    'audio': audio_results,
                    'screen': screen_results
                }
            else:
                # Default to 7 days if no time range specified
                results = db.search(keyword)

            formatted = format_search_results(results)

            audio_count = len(formatted['audio'])
            screen_count = len(formatted['screen'])

            response_text = f"Search results for '{keyword}':\n"
            response_text += f"Found {audio_count} audio matches and {screen_count} screen matches\n\n"

            if formatted['audio']:
                response_text += "Audio matches:\n"
                for i, match in enumerate(formatted['audio'][:3]):  # Show first 3
                    response_text += f"{i+1}. {match['time']}: {match['text']}\n"
                if audio_count > 3:
                    response_text += f"... and {audio_count - 3} more audio matches\n"
                response_text += "\n"

            if formatted['screen']:
                response_text += "Screen matches:\n"
                for i, match in enumerate(formatted['screen'][:3]):  # Show first 3
                    response_text += f"{i+1}. {match['time']} ({match['application']}): {match['text'][:100]}...\n"
                if screen_count > 3:
                    response_text += f"... and {screen_count - 3} more screen matches\n"

            return response_text

        elif name == "get_activity_stats":
            time_period = arguments["time_period"]

            # Validate time period format
            pattern = r"^(\d+)(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs|week|weeks)$"
            if not re.match(pattern, time_period):
                raise ValueError("time_period must be in format like '1hour', '30minutes', '1day', '1week'")

            # Parse relative time
            time_components = parse_relative_time(time_period)

            # Get statistics
            stats = db.get_statistics(**time_components)

            response_text = f"Activity statistics for the last {time_period}:\n\n"
            response_text += f"Audio:\n"
            response_text += f"- Total audio records: {stats['audio']['total_audio']}\n"
            response_text += f"- Total words: {stats['audio']['total_words']}\n"
            if 'relative_count' in stats['audio']:
                response_text += f"- Words in period: {stats['audio']['relative_count']}\n"
            response_text += f"\nScreen:\n"
            response_text += f"- Total frames: {stats['screen']['total_frames']}\n"
            response_text += f"- Total nodes: {stats['screen']['total_nodes']}\n"
            if 'relative_count' in stats['screen']:
                response_text += f"- Nodes in period: {stats['screen']['relative_count']}\n"
            response_text += f"\nApp Usage:\n"
            response_text += f"- Total apps: {stats['app_usage']['total_apps']}\n"
            response_text += f"- Total hours: {stats['app_usage']['total_hours']}\n"

            if stats['app_usage']['top_apps']:
                response_text += f"\nTop apps:\n"
                for app in stats['app_usage']['top_apps'][:5]:
                    response_text += f"- {app['app']}: {app['hours']} hours ({app['percentage']}%)\n"

            return response_text

        elif name == "get_transcript_by_id":
            audio_id = arguments["audio_id"]

            # Get transcripts for this specific audio ID
            # We'll search for transcripts and filter by audio_id
            transcripts = db.get_audio_transcripts_relative(days=30)  # Look back 30 days

            # Filter by audio_id
            matching_transcripts = [t for t in transcripts if t['audio_id'] == audio_id]

            if not matching_transcripts:
                return f"No transcript found for audio ID {audio_id}"

            formatted = format_transcripts(matching_transcripts)

            if formatted['transcripts']:
                session = formatted['transcripts'][0]
                response_text = f"Transcript for Audio ID {audio_id}:\n\n"
                response_text += f"Time: {session['start_time']}\n"
                response_text += f"Text: {session['text']}\n\n"
                response_text += f"Word-by-word breakdown:\n"
                for word in session['words'][:20]:  # Show first 20 words
                    response_text += f"- {word['word']} ({word['time']})\n"
                if len(session['words']) > 20:
                    response_text += f"... and {len(session['words']) - 20} more words\n"
            else:
                response_text = f"No transcript data found for audio ID {audio_id}"

            return response_text

        elif name == "search_screen_ocr":
            keyword = arguments["keyword"]
            relative = arguments.get("relative")
            from_time_str = arguments.get("from")
            to_time_str = arguments.get("to")
            timezone = arguments.get("timezone")
            application = arguments.get("application")

            # Convert string times to UTC datetime if provided using smart parsing
            from_time = None
            to_time = None
            if from_time_str:
                from_time = parse_smart_datetime(from_time_str, timezone)
            if to_time_str:
                to_time = parse_smart_datetime(to_time_str, timezone)

            # Perform search based on parameters
            if relative:
                # Search with relative time
                time_components = parse_relative_time(relative)
                days = (
                    time_components["days"] +
                    time_components["hours"] / 24 +
                    time_components["minutes"] / (24 * 60) +
                    time_components["seconds"] / (24 * 60 * 60)
                )
                results = db.search(keyword, days=days)
            elif from_time and to_time:
                # Search with absolute time range
                screen_ocr = db.get_screen_ocr_absolute(from_time, to_time)

                # Filter results for the keyword
                screen_results = [
                    item for item in screen_ocr
                    if keyword.lower() in item.get('text', '').lower()
                ]

                results = {
                    'audio': [],
                    'screen': screen_results
                }
            else:
                # Default to 7 days if no time range specified
                results = db.search(keyword)

            # Filter by application if specified
            if application and results.get('screen'):
                results['screen'] = [
                    item for item in results['screen']
                    if application.lower() in item.get('application', '').lower()
                ]

            # Only keep screen results for this tool
            screen_only_results = {
                'audio': [],
                'screen': results.get('screen', [])
            }

            formatted = format_search_results(screen_only_results)
            screen_count = len(formatted['screen'])

            response_text = f"Screen OCR search results for '{keyword}':\n"
            response_text += f"Found {screen_count} screen matches\n\n"

            if formatted['screen']:
                response_text += "Screen matches:\n"
                for i, match in enumerate(formatted['screen'][:10]):  # Show first 10
                    app_info = f" ({match['application']})" if match['application'] else ""
                    window_info = f" - {match['window']}" if match['window'] else ""
                    response_text += f"{i+1}. {match['time']}{app_info}{window_info}:\n"
                    response_text += f"   {match['text'][:200]}{'...' if len(match['text']) > 200 else ''}\n\n"
                if screen_count > 10:
                    response_text += f"... and {screen_count - 10} more screen matches\n"
            else:
                response_text += "No screen OCR matches found.\n"

            return response_text

        elif name == "get_screen_ocr_relative":
            time_period = arguments["time_period"]
            application = arguments.get("application")

            # Validate time period format
            pattern = r"^(\d+)(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs|week|weeks)$"
            if not re.match(pattern, time_period):
                raise ValueError("time_period must be in format like '1hour', '30minutes', '1day', '1week'")

            # Parse relative time
            time_components = parse_relative_time(time_period)

            # Get OCR text content
            ocr_data = db.get_screen_ocr_text_relative(**time_components)

            # Filter by application if specified
            if application:
                ocr_data = [
                    item for item in ocr_data
                    if application.lower() in item.get('application', '').lower()
                ]

            # Format the response
            response_text = f"Found {len(ocr_data)} OCR records in the last {time_period}"
            if application:
                response_text += f" for application '{application}'"
            response_text += ":\n\n"

            if not ocr_data:
                response_text += "No OCR data found for this time period.\n"
                response_text += "Try:\n"
                response_text += "- Expanding the time range\n"
                response_text += "- Removing application filter\n"
                response_text += "- Using search_screen_ocr to find specific content\n"
                return response_text

            # Show OCR text content grouped by frame
            frame_count = 0
            frames_shown = set()

            for item in sorted(ocr_data, key=lambda x: x['frame_time'], reverse=True):
                frame_id = item['frame_id']

                # Skip if we've already shown this frame or reached limit
                if frame_id in frames_shown or frame_count >= 10:
                    continue

                frames_shown.add(frame_id)
                frame_count += 1

                time_str = item['frame_time'].isoformat() if item['frame_time'] else 'Unknown'
                app_info = f" ({item['application']})" if item['application'] else ""
                window_info = f" - {item['window']}" if item['window'] else ""

                response_text += f"Frame {frame_count} (ID: {frame_id}):\n"
                response_text += f"Time: {time_str}{app_info}{window_info}\n"
                response_text += f"OCR Text:\n{item['text']}\n\n"

            unique_frames = len(set(item['frame_id'] for item in ocr_data))
            if unique_frames > 10:
                response_text += f"... and {unique_frames - 10} more frames\n"

            response_text += f"\nTotal frames: {unique_frames}, Total OCR records: {len(ocr_data)}\n"

            return response_text

        elif name == "get_screen_ocr_absolute":
            from_time_str = arguments["from"]
            to_time_str = arguments["to"]
            timezone = arguments.get("timezone")
            application = arguments.get("application")

            # Convert string times to UTC datetime using smart parsing
            from_time = parse_smart_datetime(from_time_str, timezone)
            to_time = parse_smart_datetime(to_time_str, timezone)

            # Validate time range
            if from_time >= to_time:
                raise ValueError("'from' time must be before 'to' time")

            # Get OCR text content for the absolute time range
            ocr_data = db.get_screen_ocr_text_absolute(from_time, to_time)

            # Filter by application if specified
            if application:
                ocr_data = [
                    item for item in ocr_data
                    if application.lower() in item.get('application', '').lower()
                ]

            # Format the response
            response_text = f"Found {len(ocr_data)} OCR records from {from_time_str} to {to_time_str}"
            if timezone:
                response_text += f" (timezone: {timezone})"
            if application:
                response_text += f" for application '{application}'"
            response_text += ":\n\n"

            if not ocr_data:
                response_text += "No OCR data found for this time period.\n"
                response_text += "Try:\n"
                response_text += "- Expanding the time range\n"
                response_text += "- Checking if the date/time is correct\n"
                response_text += "- Removing application filter\n"
                response_text += "- Using search_screen_ocr to find specific content\n"
                return response_text

            # Show OCR text content grouped by frame
            frame_count = 0
            frames_shown = set()

            for item in sorted(ocr_data, key=lambda x: x['frame_time'], reverse=True):
                frame_id = item['frame_id']

                # Skip if we've already shown this frame or reached limit
                if frame_id in frames_shown or frame_count >= 10:
                    continue

                frames_shown.add(frame_id)
                frame_count += 1

                time_str = item['frame_time'].isoformat() if item['frame_time'] else 'Unknown'
                app_info = f" ({item['application']})" if item['application'] else ""
                window_info = f" - {item['window']}" if item['window'] else ""

                response_text += f"Frame {frame_count} (ID: {frame_id}):\n"
                response_text += f"Time: {time_str}{app_info}{window_info}\n"
                response_text += f"OCR Text:\n{item['text']}\n\n"

            unique_frames = len(set(item['frame_id'] for item in ocr_data))
            if unique_frames > 10:
                response_text += f"... and {unique_frames - 10} more frames\n"

            response_text += f"\nTotal frames: {unique_frames}, Total OCR records: {len(ocr_data)}\n"

            return response_text

        elif name == "get_ocr_applications_relative":
            time_period = arguments["time_period"]

            # Validate time period format
            pattern = r"^(\d+)(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs|week|weeks)$"
            if not re.match(pattern, time_period):
                raise ValueError("time_period must be in format like '1hour', '30minutes', '1day', '1week'")

            # Parse relative time
            time_components = parse_relative_time(time_period)

            # Get OCR text content
            ocr_data = db.get_screen_ocr_text_relative(**time_components)

            # Extract unique applications with their usage stats
            app_stats = {}
            frame_app_map = {}

            for item in ocr_data:
                app = item.get('application', 'Unknown')
                frame_id = item['frame_id']

                if app not in app_stats:
                    app_stats[app] = {
                        'frame_count': 0,
                        'text_records': 0,
                        'first_seen': item['frame_time'],
                        'last_seen': item['frame_time'],
                        'windows': set(),
                        'total_text_length': 0
                    }

                app_stats[app]['text_records'] += 1
                app_stats[app]['total_text_length'] += len(item.get('text', ''))

                if item['window']:
                    app_stats[app]['windows'].add(item['window'])

                # Update time range
                if item['frame_time']:
                    if item['frame_time'] < app_stats[app]['first_seen']:
                        app_stats[app]['first_seen'] = item['frame_time']
                    if item['frame_time'] > app_stats[app]['last_seen']:
                        app_stats[app]['last_seen'] = item['frame_time']

                # Count unique frames per app
                if frame_id not in frame_app_map:
                    frame_app_map[frame_id] = app
                    app_stats[app]['frame_count'] += 1

            # Format response
            response_text = f"Found {len(app_stats)} applications with OCR data in the last {time_period}:\n\n"

            if not app_stats:
                response_text += "No applications found with OCR data for this time period.\n"
                return response_text

            # Sort by text records (activity level)
            sorted_apps = sorted(app_stats.items(), key=lambda x: x[1]['text_records'], reverse=True)

            for i, (app, stats) in enumerate(sorted_apps, 1):
                first_seen = stats['first_seen'].isoformat() if stats['first_seen'] else 'Unknown'
                last_seen = stats['last_seen'].isoformat() if stats['last_seen'] else 'Unknown'
                window_count = len(stats['windows'])
                avg_text_length = stats['total_text_length'] // stats['text_records'] if stats['text_records'] > 0 else 0

                response_text += f"{i}. {app}\n"
                response_text += f"   Frames: {stats['frame_count']}, Text Records: {stats['text_records']}\n"
                response_text += f"   Windows: {window_count}, Avg Text Length: {avg_text_length} chars\n"
                response_text += f"   Active: {first_seen} to {last_seen}\n\n"

            response_text += f"Total OCR records: {len(ocr_data)}\n"
            return response_text

        elif name == "get_ocr_applications_absolute":
            from_time_str = arguments["from"]
            to_time_str = arguments["to"]
            timezone = arguments.get("timezone")

            # Convert string times to UTC datetime using smart parsing
            from_time = parse_smart_datetime(from_time_str, timezone)
            to_time = parse_smart_datetime(to_time_str, timezone)

            # Validate time range
            if from_time >= to_time:
                raise ValueError("'from' time must be before 'to' time")

            # Get OCR text content for the absolute time range
            ocr_data = db.get_screen_ocr_text_absolute(from_time, to_time)

            # Extract unique applications with their usage stats
            app_stats = {}
            frame_app_map = {}

            for item in ocr_data:
                app = item.get('application', 'Unknown')
                frame_id = item['frame_id']

                if app not in app_stats:
                    app_stats[app] = {
                        'frame_count': 0,
                        'text_records': 0,
                        'first_seen': item['frame_time'],
                        'last_seen': item['frame_time'],
                        'windows': set(),
                        'total_text_length': 0
                    }

                app_stats[app]['text_records'] += 1
                app_stats[app]['total_text_length'] += len(item.get('text', ''))

                if item['window']:
                    app_stats[app]['windows'].add(item['window'])

                # Update time range
                if item['frame_time']:
                    if item['frame_time'] < app_stats[app]['first_seen']:
                        app_stats[app]['first_seen'] = item['frame_time']
                    if item['frame_time'] > app_stats[app]['last_seen']:
                        app_stats[app]['last_seen'] = item['frame_time']

                # Count unique frames per app
                if frame_id not in frame_app_map:
                    frame_app_map[frame_id] = app
                    app_stats[app]['frame_count'] += 1

            # Format response
            response_text = f"Found {len(app_stats)} applications with OCR data from {from_time_str} to {to_time_str}"
            if timezone:
                response_text += f" (timezone: {timezone})"
            response_text += ":\n\n"

            if not app_stats:
                response_text += "No applications found with OCR data for this time period.\n"
                response_text += "Try:\n"
                response_text += "- Expanding the time range\n"
                response_text += "- Checking if the date/time is correct\n"
                return response_text

            # Sort by text records (activity level)
            sorted_apps = sorted(app_stats.items(), key=lambda x: x[1]['text_records'], reverse=True)

            for i, (app, stats) in enumerate(sorted_apps, 1):
                first_seen = stats['first_seen'].isoformat() if stats['first_seen'] else 'Unknown'
                last_seen = stats['last_seen'].isoformat() if stats['last_seen'] else 'Unknown'
                window_count = len(stats['windows'])
                avg_text_length = stats['total_text_length'] // stats['text_records'] if stats['text_records'] > 0 else 0

                response_text += f"{i}. {app}\n"
                response_text += f"   Frames: {stats['frame_count']}, Text Records: {stats['text_records']}\n"
                response_text += f"   Windows: {window_count}, Avg Text Length: {avg_text_length} chars\n"
                response_text += f"   Active: {first_seen} to {last_seen}\n\n"

            response_text += f"Total OCR records: {len(ocr_data)}\n"
            return response_text

        else:
            raise ValueError(f"Unknown tool: {name}")

    async def get_resource(self, uri: str) -> str:
        """Get a resource by URI."""
        db = ensure_db_connection(self.env_file)

        if uri == "rewinddb://transcripts":
            # Get recent transcripts (last hour)
            transcripts = db.get_audio_transcripts_relative(hours=1)
            formatted = format_transcripts(transcripts)

            return f"Recent transcripts (last hour): {len(formatted['transcripts'])} sessions found"

        elif uri == "rewinddb://activity":
            # Get recent activity stats
            stats = db.get_statistics(hours=1)

            return f"Activity stats: {stats['audio']['total_audio']} audio records, {stats['screen']['total_frames']} screen frames"

        else:
            raise ValueError(f"Unknown resource URI: {uri}")

    async def run(self):
        """Run the MCP server."""
        logger.info("Starting MCP STDIO server")

        # Initialize database connection
        ensure_db_connection(self.env_file)

        try:
            while True:
                # Read JSON-RPC message from stdin
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                    logger.debug(f"Received request: {request}")

                    response = await self.handle_request(request)

                    if response is not None:
                        response_json = json.dumps(response)
                        print(response_json)
                        sys.stdout.flush()
                        logger.debug(f"Sent response: {response_json}")

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32700,
                            "message": "Parse error"
                        }
                    }
                    print(json.dumps(error_response))
                    sys.stdout.flush()

        except KeyboardInterrupt:
            logger.info("Server interrupted")
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
        finally:
            if db:
                db.close()
            logger.info("MCP STDIO server stopped")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MCP STDIO server for RewindDB",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--log", metavar="FILE", default="/tmp/mcp_stdio.log",
                       help="Path to log file for debug outputs")
    parser.add_argument("--env-file", metavar="FILE", default=".env",
                       help="Path to .env file with database configuration")

    args = parser.parse_args()

    # Configure logging with the specified log file
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(args.log)],
        force=True  # Override any existing configuration
    )

    # Set log level for our logger
    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Detect system timezone at startup
    detected_tz = detect_system_timezone()
    logger.info(f"MCP server starting with system timezone: {detected_tz}")

    # Log current date/time in both local and UTC
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_local = datetime.datetime.now()

    logger.info(f"Current UTC time: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"Current local time: {now_local.strftime('%Y-%m-%d %H:%M:%S')} (assumed {detected_tz})")

    # Also try to show local time with detected timezone if possible
    if ZoneInfo and detected_tz != "UTC" and not detected_tz.startswith("UTC"):
        try:
            local_tz = ZoneInfo(detected_tz)
            now_with_tz = datetime.datetime.now(local_tz)
            utc_offset = now_with_tz.utcoffset()
            offset_hours = utc_offset.total_seconds() / 3600

            logger.info(f"Current time with detected timezone: {now_with_tz.strftime('%Y-%m-%d %H:%M:%S %Z')} (offset: {now_with_tz.strftime('%z')})")
            logger.info(f"UTC offset calculation: {offset_hours:+.1f} hours ({utc_offset})")

            # Test timezone conversion with a sample time
            test_time = "2025-06-05T15:00:00"
            test_dt = datetime.datetime.fromisoformat(test_time).replace(tzinfo=local_tz)
            test_utc = test_dt.astimezone(datetime.timezone.utc)
            logger.info(f"Test conversion: {test_time} in {detected_tz} -> {test_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")

            # Test what happens if we treat a -06:00 timestamp as local time
            test_input = "2025-06-05T15:00:00-06:00"
            test_parsed = datetime.datetime.fromisoformat(test_input)
            # Extract just the naive datetime part
            naive_dt = test_parsed.replace(tzinfo=None)
            # Apply local timezone
            local_dt = naive_dt.replace(tzinfo=local_tz)
            local_utc = local_dt.astimezone(datetime.timezone.utc)
            logger.info(f"If we treat '{test_input}' as local time: {naive_dt} {detected_tz} -> {local_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        except Exception as e:
            logger.debug(f"Could not create timezone-aware datetime: {e}")

    # Create and run server
    server = MCPServer(args.env_file)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())