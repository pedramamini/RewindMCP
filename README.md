# RewindDB

A Python library for interfacing with the Rewind.ai SQLite database.

## Changelog

### 2025-07-04 - Voice Export & Training Data Features
- **NEW**: `--export-own-voice` CLI option for exporting user's voice transcripts organized by day
- **NEW**: `--speech-source` filter to separate user voice (`me`) from other speakers (`others`)
- **NEW**: Multi-format export support: text, JSON, and audio file export
- **NEW**: `--export-format audio` with `--audio-export-dir` for exporting actual M4A audio files
- **NEW**: `my-words.sh` script for generating word clouds from your voice data
- **ENHANCED**: RewindDB core library now supports speech source filtering
- **USE CASE**: Perfect for collecting clean voice training data for LLM fine-tuning
- **FILTER**: Text exports contain only user's voice (no other speakers), audio exports contain full conversations

## Project Overview

RewindDB is a Python library that provides a convenient interface to the Rewind.ai SQLite database. Rewind.ai is a personal memory assistant that captures audio transcripts and screen OCR data in real-time. This project allows you to programmatically access and search through this data, making it possible to retrieve past conversations, find specific information mentioned in meetings, or analyze screen content from previous work sessions.

The project consists of three main components:
1. A core Python library (`rewinddb`) for direct database access
2. Command-line tools for transcript retrieval, keyword searching, screen OCR data retrieval, and activity tracking
3. An MCP STDIO server that exposes these capabilities to GenAI models through the standardized Model Context Protocol

The main purpose of this project, for me, was to connect Rewind to my Raycast:

![image](https://github.com/user-attachments/assets/0e6cc4a7-dc4d-45ea-b368-52adbf70462c)

![image](https://github.com/user-attachments/assets/04a3932c-7cb1-4afe-84b2-b96401ac1021)


## Installation

### Prerequisites

- Python 3.6+

### Install from Source

```bash
# clone the repository
git clone https://github.com/pedramamini/RewindMCP.git
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
python ocr_cli.py --relative "1 hour" --env-file /path/to/custom/.env
python activity_cli.py --relative "1 day" --env-file /path/to/custom/.env
```

```bash
# with mcp server
python mcp_stdio.py --env-file /path/to/custom/.env
```

## CLI Tools

### transcript_cli.py

Retrieve audio transcripts from the Rewind.ai database with advanced voice filtering and export capabilities.

#### Basic Transcript Retrieval

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

#### Voice Source Filtering

```bash
# filter for only your own voice
python transcript_cli.py --relative "1 hour" --speech-source me

# filter for other speakers only
python transcript_cli.py --relative "1 day" --speech-source others

# filter works with any time range
python transcript_cli.py --from "2025-07-01" --to "2025-07-02" --speech-source me
```

#### Voice Export for Training Data 🎙️

**Perfect for collecting clean voice training data for LLM fine-tuning**

```bash
# export your voice transcripts organized by day (text format)
python transcript_cli.py --export-own-voice "2025-01-01 to 2025-07-04"

# export as JSON with metadata
python transcript_cli.py --export-own-voice "2025-01-01 to 2025-07-04" --export-format json --save-to my_voice.json

# export actual audio files organized by day
python transcript_cli.py --export-own-voice "2025-01-01 to 2025-07-04" --export-format audio --audio-export-dir ./my_voice_audio

# generate word cloud from your voice data (requires wordcloud library)
pip install wordcloud matplotlib  # install dependencies
./my-words.sh  # automatically uses last 6 months of your voice data
```

**Key Features:**
- **Clean Training Data**: Text exports contain only YOUR voice, filtered out other speakers
- **Audio Export**: M4A files organized by day with transcript summaries
- **Multiple Formats**: Text (readable), JSON (structured), Audio (original files)
- **Day Organization**: Perfect for chronological training data or analysis
- **Word Cloud**: Quick visualization of your most-used words with `my-words.sh`

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

### ocr_cli.py

Retrieve screen OCR (Optical Character Recognition) data from the Rewind.ai database. This tool allows you to see what text was visible on your screen during specific time periods, providing complete OCR text content rather than just metadata about frames and nodes.

```bash
# get OCR data from the last hour
python ocr_cli.py --relative "1 hour"

# get OCR data from the last 5 hours (supports short form)
python ocr_cli.py --relative "5h"

# get OCR data from a specific time range
python ocr_cli.py --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"

# get OCR data for today only
python ocr_cli.py --from "2023-05-11" --to "2023-05-11"

# get OCR data for specific hours today
python ocr_cli.py --from "13:00" --to "17:00"

# list all applications that have OCR data
python ocr_cli.py --list-apps

# filter OCR data by specific application
python ocr_cli.py --relative "1 day" --app "com.apple.Safari"

# enable debug output and use custom .env file
python ocr_cli.py --relative "7 days" --debug --env-file /path/to/custom/.env

# display times in UTC instead of local time
python ocr_cli.py --relative "1 day" --utc
```

**Key Features:**
- **Time formats**: Supports relative time ("1 hour", "5h", "30m", "2d", "1w") and absolute time ranges
- **Application filtering**: Use `--list-apps` to see available applications, then `--app` to filter by specific app
- **Flexible time input**: Accepts various formats including date-only, time-only, and full datetime strings
- **Text extraction**: Shows actual text content that was visible on screen, organized by timestamp and application

### activity_cli.py

Display comprehensive activity tracking data from the Rewind.ai database, including computer usage patterns, application usage statistics, and calendar meetings.

```bash
# get activity data for the last day
python activity_cli.py --relative "1 day"

# get activity data for the last 5 hours (supports short form)
python activity_cli.py --relative "5h"

# get activity data from a specific time range
python activity_cli.py --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"

# get activity data for today only
python activity_cli.py --from "2023-05-11" --to "2023-05-11"

# get activity data for specific hours today
python activity_cli.py --from "13:00" --to "17:00"

# enable debug output and use custom .env file
python activity_cli.py --relative "1 week" --debug --env-file /path/to/custom/.env

# display times in UTC instead of local time
python activity_cli.py --relative "1 day" --utc
```

**Key Features:**
- **Active Hours**: Shows when your computer was actively being used, with hourly and daily breakdowns
- **Application Usage**: Displays top applications by usage time with visual charts
- **Calendar Meetings**: Shows meeting statistics, duration, and distribution by time of day
- **Visual Charts**: Includes simple ASCII bar charts for easy data visualization
- **Time Zone Support**: Displays times in local timezone by default, with UTC option available

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

1. **`get_transcripts_relative`**: Get audio transcripts from a relative time period (e.g., "1hour", "30minutes", "1day", "1week"). Returns transcript sessions with full text content suitable for analysis, summarization, or detailed review. Each session includes complete transcript text and word-by-word timing.

2. **`get_transcripts_absolute`**: **PRIMARY TOOL for meeting summaries** - Get complete audio transcripts from a specific time window (e.g., '3 PM meeting'). This is the FIRST tool to use when asked to summarize meetings, calls, or conversations from specific times. Returns full transcript sessions with complete text content ready for analysis and summarization.

3. **`search_transcripts`**: Search for specific keywords/phrases in transcripts. **NOT for meeting summaries** - use `get_transcripts_absolute` instead when asked to summarize meetings from specific times. This tool finds keyword matches with context snippets, useful for finding specific topics or names mentioned across multiple sessions.

4. **`search_screen_ocr`**: Search through OCR screen content for keywords. Finds text that appeared on screen during specific time periods. Use this to find what was displayed on screen, applications used, or visual content during meetings or work sessions. Complements audio transcripts by showing what was visible.

5. **`get_screen_ocr_relative`**: Get all screen OCR content from a relative time period (e.g., "2hours", "1day"). Returns complete OCR text content that was visible on screen, organized by application and timestamp. Use this to see everything that was displayed during a time period.
   - **Parameters**: `time_period` (required, e.g., '1hour', '30minutes', '1day', '1week'), `application` (optional, filter by app name)
   - **Use Case**: "Show me all screen content from the last 2 hours" or "Show me all Chrome content from the last day"

6. **`get_screen_ocr_absolute`**: Get all screen OCR content from a specific time window. Returns complete OCR text content from the specified time range, with optional application filtering. Essential for reviewing what was visible during meetings or work sessions.
   - **Parameters**: `from` (required, ISO format), `to` (required, ISO format), `timezone` (optional), `application` (optional, filter by app name)
   - **Use Case**: "Show me all screen content from my 3 PM meeting" or "Show me all Slack content from yesterday afternoon"

7. **`get_ocr_applications_relative`**: Discover all applications that have OCR data from a relative time period. Shows which applications were active and their activity levels. Use this to identify applications before filtering OCR content.
   - **Parameters**: `time_period` (required, e.g., '1hour', '30minutes', '1day', '1week')
   - **Use Case**: "What applications were active in the last 4 hours?" - helps users discover what apps to filter by
   - **Returns**: Frame count per application, OCR node count (activity level), number of unique windows, time range when application was active, sorted by activity level

8. **`get_ocr_applications_absolute`**: Discover all applications that have OCR data from a specific time window. Helps identify what applications were active during specific meetings or time periods.
   - **Parameters**: `from` (required, ISO format), `to` (required, ISO format), `timezone` (optional)
   - **Use Case**: "What applications were active during my meeting from 2-3 PM?" - helps users discover what apps to filter by
   - **Returns**: Frame count per application, OCR node count (activity level), number of unique windows, time range when application was active, sorted by activity level

9. **`get_activity_stats`**: Get activity statistics for a specified time period (e.g., "1hour", "30minutes", "1day", "1week"). Provides comprehensive statistics about audio recordings, screen captures, and application usage.

10. **`get_transcript_by_id`**: **FOLLOW-UP TOOL** - Get complete transcript content by audio ID. Use this AFTER `get_transcripts_absolute` to retrieve full transcript text for summarization. Essential second step when the first tool shows preview text that needs complete content for proper analysis.

### OCR Tools Workflow Integration

The OCR tools work together in a natural workflow for comprehensive screen content analysis:

1. **Discovery Phase**: Use `get_ocr_applications_*` to see what applications were active
   ```
   get_ocr_applications_relative: "2hours"
   → Returns: Chrome, Slack, VS Code, Zoom, etc.
   ```

2. **Focused Retrieval**: Use `get_screen_ocr_*` with application filter to get specific content
   ```
   get_screen_ocr_relative: time_period="2hours", application="Chrome"
   → Returns: All Chrome OCR content from last 2 hours
   ```

3. **Keyword Search**: Use existing `search_screen_ocr` for specific content within results
   ```
   search_screen_ocr: keyword="meeting notes", application="Slack"
   → Returns: Specific matches for "meeting notes" in Slack
   ```

**Key Features:**
- **Application Filtering**: Both OCR content tools support optional application filtering with case-insensitive matching (e.g., "chrome" matches "Google Chrome")
- **Rich Metadata**: Application discovery tools provide frame count, OCR node count (activity level), number of unique windows, and time ranges
- **Consistent Time Handling**: All tools use smart datetime parsing supporting both relative time periods and absolute time ranges with timezone handling
- **Complete Content Access**: OCR content tools return actual OCR text content grouped by frame, not just metadata
- **Meeting Analysis**: Perfect for reviewing what was displayed during meetings or work sessions

**Benefits and Use Cases:**
- **Complete OCR Access**: Users can now pull all screen content from any time window, not just search for specific keywords
- **Application Discovery**: Easy way to see what apps were active during specific periods before filtering content
- **Flexible Filtering**: Can focus on specific applications after discovery phase
- **Meeting Analysis**: Perfect for reviewing what was displayed during meetings or presentations
- **Work Session Review**: Analyze screen activity and content during specific work periods
- **Seamless Integration**: Works with existing search and transcript tools for comprehensive data analysis

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

# filter by speech source for voice training data
user_only = db.get_audio_transcripts_relative(hours=1, speech_source='me')
others_only = db.get_audio_transcripts_relative(hours=1, speech_source='others')

# get voice data organized by day for training
transcripts_by_day = db.get_own_voice_transcripts_by_day(start_time, end_time)
for date, transcripts in transcripts_by_day.items():
    print(f"{date}: {len(transcripts)} words")
    words = [t['word'] for t in transcripts]
    text = ' '.join(words)
    print(f"Sample: {text[:100]}...")
```

### Retrieving Screen OCR Data

```python
# get screen ocr from a relative time period
ocr_data = db.get_screen_ocr_relative(days=1)

# get screen ocr from a specific time range
ocr_data = db.get_screen_ocr_absolute(start_time, end_time)

# get complete OCR text content from relative time period
ocr_text = db.get_screen_ocr_text_relative(hours=2)

# get complete OCR text content from specific time range
ocr_text = db.get_screen_ocr_text_absolute(start_time, end_time)

# get OCR text content filtered by application
ocr_text = db.get_screen_ocr_text_relative(hours=1, application="Chrome")
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

**Key Fields:**
- `speechSource`: Identifies the speaker - `'me'` for user's voice, `'others'` for other speakers
- `word`: The transcribed word text
- `timeOffset`: Timing within the audio segment (milliseconds)
- `duration`: Length of the spoken word (milliseconds)

This speaker identification enables clean voice training data export by filtering to only the user's spoken words.

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

This table is crucial for searching through screen content and is used by the new OCR text retrieval methods (`get_screen_ocr_text_absolute()` and `get_screen_ocr_text_relative()`) to provide complete OCR text content rather than just metadata about frames and nodes.

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
git clone https://github.com/pedramamini/RewindMCP.git
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
