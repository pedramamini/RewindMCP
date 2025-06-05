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

import rewinddb
from rewinddb.config import load_config

# Logger will be configured in main() after parsing arguments
logger = logging.getLogger("mcp_stdio")

# Global database connection
db: Optional[rewinddb.RewindDB] = None


def parse_relative_time(time_str: str) -> Dict[str, int]:
    """Parse a relative time string into timedelta components."""
    time_str = time_str.lower().strip()
    time_components = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}

    patterns = {
        r"(\d+)(?:day|days)": "days",
        r"(\d+)(?:hour|hours|hr|hrs)": "hours",
        r"(\d+)(?:minute|minutes|min|mins)": "minutes",
        r"(\d+)(?:second|seconds|sec|secs)": "seconds"
    }

    found_match = False
    for pattern, component in patterns.items():
        match = re.search(pattern, time_str)
        if match:
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
                "description": "Get audio transcripts from a relative time period",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "time_period": {
                            "type": "string",
                            "description": "Time period like '1hour', '30minutes', '1day'",
                            "pattern": r"^\d+(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs)$"
                        }
                    },
                    "required": ["time_period"]
                }
            },
            "get_transcripts_absolute": {
                "description": "Get audio transcripts from a specific time window",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "from": {
                            "type": "string",
                            "description": "Start time in ISO format (e.g., '2024-01-15T14:00:00')"
                        },
                        "to": {
                            "type": "string",
                            "description": "End time in ISO format (e.g., '2024-01-15T15:00:00')"
                        }
                    },
                    "required": ["from", "to"]
                }
            },
            "search_transcripts": {
                "description": "Search through audio transcripts for keywords",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "Keyword to search for"
                        },
                        "relative": {
                            "type": "string",
                            "description": "Optional relative time period like '1hour', '1day'",
                            "pattern": r"^\d+(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs)$"
                        },
                        "from": {
                            "type": "string",
                            "description": "Optional start time in ISO format"
                        },
                        "to": {
                            "type": "string",
                            "description": "Optional end time in ISO format"
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
                            "description": "Time period like '1hour', '30minutes', '1day'",
                            "pattern": r"^\d+(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs)$"
                        }
                    },
                    "required": ["time_period"]
                }
            },
            "get_transcript_by_id": {
                "description": "Get a specific transcript by audio ID",
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
                "description": "Search through OCR screen content for keywords",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "Keyword to search for in screen OCR content"
                        },
                        "relative": {
                            "type": "string",
                            "description": "Optional relative time period like '1hour', '1day'",
                            "pattern": r"^\d+(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs)$"
                        },
                        "from": {
                            "type": "string",
                            "description": "Optional start time in ISO format"
                        },
                        "to": {
                            "type": "string",
                            "description": "Optional end time in ISO format"
                        },
                        "application": {
                            "type": "string",
                            "description": "Optional application name to filter results"
                        }
                    },
                    "required": ["keyword"]
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
            pattern = r"^(\d+)(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs)$"
            if not re.match(pattern, time_period):
                raise ValueError("time_period must be in format like '1hour', '30minutes', '1day'")

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
            from_time = arguments["from"]
            to_time = arguments["to"]

            # Convert string times to datetime
            try:
                from_time = datetime.datetime.fromisoformat(from_time)
                to_time = datetime.datetime.fromisoformat(to_time)
            except ValueError as e:
                raise ValueError(f"Invalid ISO format for time parameters: {e}")

            # Validate time range
            if from_time >= to_time:
                raise ValueError("'from' time must be before 'to' time")

            # Get transcripts for the absolute time range
            transcripts = db.get_audio_transcripts_absolute(from_time, to_time)
            formatted = format_transcripts(transcripts)

            result = f"Found {len(formatted['transcripts'])} transcript sessions from {from_time.isoformat()} to {to_time.isoformat()}:\n\n"
            for i, session in enumerate(formatted['transcripts'][:5]):  # Show first 5
                result += f"Session {i+1} (Audio ID: {session['audio_id']}):\n"
                result += f"Time: {session['start_time']}\n"
                result += f"Text: {session['text'][:200]}{'...' if len(session['text']) > 200 else ''}\n\n"

            if len(formatted['transcripts']) > 5:
                result += f"... and {len(formatted['transcripts']) - 5} more sessions\n"

            return result

        elif name == "search_transcripts":
            keyword = arguments["keyword"]
            relative = arguments.get("relative")
            from_time = arguments.get("from")
            to_time = arguments.get("to")

            # Convert string times to datetime if provided
            if from_time:
                from_time = datetime.datetime.fromisoformat(from_time)
            if to_time:
                to_time = datetime.datetime.fromisoformat(to_time)

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
            pattern = r"^(\d+)(hour|hours|hr|hrs|minute|minutes|min|mins|day|days|second|seconds|sec|secs)$"
            if not re.match(pattern, time_period):
                raise ValueError("time_period must be in format like '1hour', '30minutes', '1day'")

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
            from_time = arguments.get("from")
            to_time = arguments.get("to")
            application = arguments.get("application")

            # Convert string times to datetime if provided
            if from_time:
                from_time = datetime.datetime.fromisoformat(from_time)
            if to_time:
                to_time = datetime.datetime.fromisoformat(to_time)

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

    # Create and run server
    server = MCPServer(args.env_file)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())