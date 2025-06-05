# RewindDB

A Python library for interfacing with the Rewind.ai SQLite database.

## Project Overview

RewindDB is a Python library that provides a convenient interface to the Rewind.ai SQLite database. Rewind.ai is a personal memory assistant that captures audio transcripts and screen OCR data in real-time. This project allows you to programmatically access and search through this data, making it possible to retrieve past conversations, find specific information mentioned in meetings, or analyze screen content from previous work sessions.

The project consists of three main components:
1. A core Python library (`rewinddb`) for direct database access
2. Command-line tools for transcript retrieval and keyword searching
3. An MCP STDIO server that exposes these capabilities to GenAI models through the standardized Model Context Protocol

## Installation

### Prerequisites

- Python 3.6+

### Install from Source

```bash
# clone the repository
git clone https://github.com/yourusername/RewindMCP.git
cd RewindMCP

# install the package and dependencies
pip install .
```

### Manual Installation

```bash
# install the package in development mode
pip install -e .
```

## Configuration

RewindDB uses a `.env` file to store database connection parameters. This approach avoids hardcoding sensitive information like database paths and passwords in the source code.

### Setting Up the .env File

1. Create a `.env` file in your project directory or in your home directory as `~/.rewinddb.env`
2. Add the following configuration parameters:

```
DB_PATH=/path/to/your/rewind/database.sqlite3
DB_PASSWORD=your_database_password
```

For example:

```
DB_PATH=/Users/username/Library/Application Support/com.memoryvault.MemoryVault/db-enc.sqlite3
DB_PASSWORD=your_database_password_here
```

### Custom .env File Location

You can also specify a custom location for your `.env` file when using the library or CLI tools:

```python
# in python code
db = rewinddb.RewindDB(env_file="/path/to/custom/.env")
```

```bash
# with cli tools
python transcript_cli.py --relative "1 hour" --env-file /path/to/custom/.env
python search_cli.py "meeting" --env-file /path/to/custom/.env
```

```bash
# with mcp server
python mcp_stdio.py --env-file /path/to/custom/.env
```

## CLI Tools

### transcript_cli.py

Retrieve audio transcripts from the Rewind.ai database.

```bash
# get transcripts from the last hour
python transcript_cli.py --relative "1 hour"

# get transcripts from the last 5 hours
python transcript_cli.py --relative "5 hours"

# get transcripts from a specific time range
python transcript_cli.py --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"

# enable debug output
python transcript_cli.py --relative "7 days" --debug

# use a custom .env file
python transcript_cli.py --relative "1 hour" --env-file /path/to/custom/.env
```

### search_cli.py

Search for keywords across both audio transcripts and screen OCR data.

```bash
# search for a keyword with default time range (7 days)
python search_cli.py "meeting"

# search with a specific time range
python search_cli.py "project" --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"

# search with a relative time period
python search_cli.py "presentation" --relative "1 day"

# adjust context size and enable debug output
python search_cli.py "python" --context 5 --debug

# use a custom .env file
python search_cli.py "meeting" --env-file /path/to/custom/.env
```

## MCP STDIO Server

The Model Context Protocol (MCP) server exposes RewindDB functionality to GenAI models through the standardized MCP STDIO protocol. This implementation is fully MCP-compliant and works with MCP clients like Claude, Raycast, and other AI assistants.

### Quick Start

```bash
# start the STDIO MCP server
python mcp_stdio.py

# enable debug logging
python mcp_stdio.py --debug

# use a custom .env file
python mcp_stdio.py --env-file /path/to/custom/.env
```

### Available Tools

The MCP server provides the following tools:

1. `get_transcripts_relative`: Get audio transcripts from a relative time period (e.g., "1hour", "30minutes", "1day")
2. `search_transcripts`: Search through audio transcripts for keywords with optional time filtering
3. `search_screen_ocr`: Search through OCR screen content for keywords with optional time and application filtering
4. `get_activity_stats`: Get activity statistics for a specified time period
5. `get_transcript_by_id`: Get a specific transcript by audio ID

### MCP Client Integration

The server follows the MCP specification and can be used with any MCP-compatible client. Example configuration:

```json
{
  "mcpServers": {
    "rewinddb": {
      "command": "python",
      "args": ["/path/to/mcp_stdio.py"],
      "env": {
        "REWIND_DB_PATH": "/path/to/your/rewind.db",
        "REWIND_DB_PASSWORD": "your_password"
      }
    }
  }
}
```

For detailed STDIO MCP setup instructions, configuration examples, and troubleshooting, see [README-MCP-STDIO.md](README-MCP-STDIO.md).

## Library Usage

### Basic Usage

```python
import rewinddb

# initialize connection to the database (uses .env file)
db = rewinddb.RewindDB()

# or specify a custom .env file
# db = rewinddb.RewindDB(env_file="/path/to/custom/.env")

# get audio transcripts from the last hour
transcripts = db.get_audio_transcripts_relative(hours=1)

# get screen ocr data from the last 30 minutes
ocr_data = db.get_screen_ocr_relative(minutes=30)

# search for keywords across both audio and screen data
results = db.search("python programming")

# close the connection when done
db.close()

# or use as a context manager
with rewinddb.RewindDB() as db:
    transcripts = db.get_audio_transcripts_relative(hours=1)
```

### Retrieving Audio Transcripts

```python
# get transcripts from a relative time period
transcripts = db.get_audio_transcripts_relative(hours=2, minutes=30)

# get transcripts from a specific time range
from datetime import datetime
start_time = datetime(2023, 5, 11, 13, 0, 0)  # 1:00 PM
end_time = datetime(2023, 5, 11, 17, 0, 0)    # 5:00 PM
transcripts = db.get_audio_transcripts_absolute(start_time, end_time)
```

### Retrieving Screen OCR Data

```python
# get screen ocr from a relative time period
ocr_data = db.get_screen_ocr_relative(days=1)

# get screen ocr from a specific time range
ocr_data = db.get_screen_ocr_absolute(start_time, end_time)
```

### Searching Across Data

```python
# search for keywords in the last 7 days (default)
results = db.search("meeting notes")

# search for keywords in a specific time period
results = db.search("project deadline", days=30)

# access search results
for audio_hit in results['audio']:
    print(f"Audio match at {audio_hit['absolute_time']}: {audio_hit['word']}")

for screen_hit in results['screen']:
    print(f"Screen match at {screen_hit['frame_time']} in {screen_hit['application']}: {screen_hit['text']}")
```

## Database Schema

The Rewind.ai database contains several key tables:

- `audio`: Stores audio recording segments with timestamps
- `transcript_word`: Contains individual transcribed words linked to audio segments
- `frame`: Stores screen capture frames with timestamps
- `node`: Contains text elements extracted from screen captures (OCR)
- `segment`: Tracks application and window usage sessions
- `event`: Stores calendar events and meetings
- `searchRanking_content`: Stores OCR text content for searching

### Data Types Explained

#### Audio Recordings
Audio recordings are captured by Rewind.ai when you speak or when there's audio playing on your computer. Each recording is stored as a segment in the `audio` table with metadata like start time and duration. These recordings are then processed to extract transcribed words.

Audio snippets are stored on disk at:
```
~/Library/Application Support/com.memoryvault.MemoryVault/snippets/YYYY-MM-DDThh:mm:ss/snippet.m4a
```

#### Transcript Words
Individual words extracted from audio recordings through speech recognition. Each word in the `transcript_word` table includes information about when it occurred within the audio recording (timeOffset), its position in the full text (fullTextOffset), and its duration. Transcript words are linked to their source audio recording.

#### Frames
Screenshots captured by Rewind.ai at regular intervals as you use your computer. Each frame in the `frame` table includes a timestamp (createdAt) and is linked to the application segment it belongs to. Frames are the visual equivalent of audio recordings, capturing what was on your screen at specific moments.

Screen recordings are stored on disk as chunks at:
```
~/Library/Application Support/com.memoryvault.MemoryVault/chunks/YYYYMM/DD/[chunk_id]
```
Where:
- YYYYMM is the year and month (e.g., 202505 for May 2025)
- DD is the day (e.g., 13 for the 13th)
- [chunk_id] is a unique identifier for the recording chunk

#### Nodes
Text elements extracted from screen captures using Optical Character Recognition (OCR). Each node in the `node` table represents a piece of text visible on your screen, including its position (leftX, topY, width, height) and other metadata. Nodes are linked to the frame they were extracted from. They are the visual equivalent of transcript words.

#### SearchRanking_Content
This table stores the actual OCR text content extracted from screen captures. It contains three columns:
- `id`: A unique identifier that can be used to locate the corresponding recording chunk
- `c0`: The main text content extracted from the screen
- `c1`: Timestamp information
- `c2`: Window/application information

This table is crucial for searching through screen content.

#### Segments
Application usage sessions that track when you were using specific applications and windows. Each segment in the `segment` table includes the application bundle ID, window name, start time, and end time. Segments help organize frames and audio recordings by the application context they occurred in.

#### Events
Calendar events and meetings that were scheduled during your computer usage. The `event` table stores information about these events, including title, start time, end time, and other metadata. Events provide additional context about what you were doing during specific time periods.

Key relationships:
- Audio segments are linked to transcript words
- Frames are linked to nodes (text elements)
- Frames and audio segments are associated with application segments
- Events may be associated with specific segments
- SearchRanking_content entries are linked to frames and contain the actual OCR text

## Development

### Setup for Development

```bash
# clone the repository
git clone https://github.com/yourusername/RewindMCP.git
cd RewindMCP

# install in development mode
pip install -e .

# install development dependencies
pip install pytest black isort
```

### Running Tests

```bash
# run all tests
pytest

# run a specific test
pytest test_mcp_stdio.py
```

## Troubleshooting

### Database Connection Issues

If you encounter database connection errors:

1. Verify that the Rewind.ai application is installed and has created the database
2. Check that your `.env` file contains the correct database path and password
3. Ensure the RewindDB module is properly installed

### No Transcripts Found

If no transcripts are returned:

1. Verify that the time range contains data (try expanding the time range)
2. Check that Rewind.ai was actively recording during the requested time period
3. Use the `--debug` flag with CLI tools to see more information

### MCP Server Issues

If the MCP server fails to start or respond:

1. Check that all MCP dependencies are installed: `pip install "mcp>=0.1.0"`
2. Verify your database configuration in the `.env` file
3. Check the server logs in `/tmp/mcp_stdio.log` for specific error messages

## Stats CLI

The `stats_cli.py` tool provides comprehensive statistics about your Rewind.ai data:

```bash
# get statistics about your rewind.ai data
python stats_cli.py

# use a custom .env file
python stats_cli.py --env /path/to/custom/.env
```

The Stats CLI provides information about:
- Database overview (size, tables, record counts)
- Audio transcript statistics (counts by time period, earliest records)
- Screen OCR statistics (counts by time period, earliest records)
- Application usage statistics (most used applications, usage time)
- Table record counts

This tool is useful for understanding the scope and content of your Rewind.ai data, and for diagnosing potential issues with data collection or storage.

## License

MIT