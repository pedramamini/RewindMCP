# RewindDB

a python library for interfacing with the rewind.ai sqlite database.

## project overview

rewinddb is a python library that provides a convenient interface to the rewind.ai sqlite database. rewind.ai is a personal memory assistant that captures audio transcripts and screen ocr data in real-time. this project allows you to programmatically access and search through this data, making it possible to retrieve past conversations, find specific information mentioned in meetings, or analyze screen content from previous work sessions.

the project consists of three main components:
1. a core python library (`rewinddb`) for direct database access
2. command-line tools for transcript retrieval and keyword searching
3. an mcp server that exposes these capabilities to genai models

## installation

### prerequisites

- python 3.6+
- fastapi and uvicorn (for mcp server)

### install from source

```bash
# clone the repository
git clone https://github.com/yourusername/RewindMCP.git
cd RewindMCP

# install the package and dependencies
pip install .
```

### manual installation

```bash
# install required dependencies
pip install fastapi uvicorn

# install the package in development mode
pip install -e .
```

## configuration

rewinddb uses a `.env` file to store database connection parameters. this approach avoids hardcoding sensitive information like database paths and passwords in the source code.

### setting up the .env file

1. create a `.env` file in your project directory or in your home directory as `~/.rewinddb.env`
2. add the following configuration parameters:

```
DB_PATH=/path/to/your/rewind/database.sqlite3
DB_PASSWORD=your_database_password
```

for example:

```
DB_PATH=/Users/username/Library/Application Support/com.memoryvault.MemoryVault/db-enc.sqlite3
DB_PASSWORD=your_database_password_here
```

### custom .env file location

you can also specify a custom location for your `.env` file when using the library or cli tools:

```python
# in python code
db = rewinddb.RewindDB(env_file="/path/to/custom/.env")
```

```bash
# with cli tools
python transcript_cli.py --relative "1 hour" --env-file /path/to/custom/.env
python search_cli.py --keyword "meeting" --env-file /path/to/custom/.env
```

```bash
# with mcp server
python mcp_server.py --env-file /path/to/custom/.env
```

## library usage

### basic usage

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

### retrieving audio transcripts

```python
# get transcripts from a relative time period
transcripts = db.get_audio_transcripts_relative(hours=2, minutes=30)

# get transcripts from a specific time range
from datetime import datetime
start_time = datetime(2023, 5, 11, 13, 0, 0)  # 1:00 PM
end_time = datetime(2023, 5, 11, 17, 0, 0)    # 5:00 PM
transcripts = db.get_audio_transcripts_absolute(start_time, end_time)
```

### retrieving screen ocr data

```python
# get screen ocr from a relative time period
ocr_data = db.get_screen_ocr_relative(days=1)

# get screen ocr from a specific time range
ocr_data = db.get_screen_ocr_absolute(start_time, end_time)
```

### searching across data

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

## cli tools

### transcript_cli.py

retrieve audio transcripts from the rewind.ai database.

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

search for keywords across both audio transcripts and screen ocr data.

```bash
# search for a keyword with default time range (7 days)
python search_cli.py --keyword "meeting"

# search with a specific time range
python search_cli.py --keyword "project" --from "2023-05-11 13:00:00" --to "2023-05-11 17:00:00"

# search with a relative time period
python search_cli.py --keyword "presentation" --relative "1 day"

# adjust context size and enable debug output
python search_cli.py --keyword "python" --context 5 --debug

# use a custom .env file
python search_cli.py --keyword "meeting" --env-file /path/to/custom/.env
```

## mcp server

the model context protocol (mcp) server exposes rewinddb functionality to genai models through a rest api.

### starting the server

```bash
# start the server on default port (8000)
python mcp_server.py

# specify a different port
python mcp_server.py --port 8080

# enable debug logging
python mcp_server.py --debug

# use a custom .env file
python mcp_server.py --env-file /path/to/custom/.env
```

### available tools

the mcp server provides the following tools:

1. `get_transcripts_relative`: retrieve audio transcripts from a relative time period
2. `get_transcripts_absolute`: retrieve audio transcripts from a specific time range
3. `search`: search for keywords across both audio and screen data

### api documentation

when the server is running, you can access the auto-generated api documentation at:
- swagger ui: `http://localhost:8000/docs`
- redoc: `http://localhost:8000/redoc`

### example usage with curl

```bash
# get transcripts from the last hour
curl -X POST "http://localhost:8000/mcp/tools/get_transcripts_relative" \
  -H "Content-Type: application/json" \
  -d '{"time_period": "1hour"}'

# search for keywords
curl -X POST "http://localhost:8000/mcp/tools/search" \
  -H "Content-Type: application/json" \
  -d '{"keyword": "meeting", "relative": "1day"}'
```

## database schema

the rewind.ai database contains several key tables:

- `audio`: stores audio recording segments with timestamps
- `transcript_word`: contains individual transcribed words linked to audio segments
- `frame`: stores screen capture frames with timestamps
- `node`: contains text elements extracted from screen captures (ocr)
- `segment`: tracks application and window usage sessions
- `event`: stores calendar events and meetings

### data types explained

#### audio recordings
audio recordings are captured by rewind.ai when you speak or when there's audio playing on your computer. each recording is stored as a segment in the `audio` table with metadata like start time and duration. these recordings are then processed to extract transcribed words.

#### transcript words
individual words extracted from audio recordings through speech recognition. each word in the `transcript_word` table includes information about when it occurred within the audio recording (timeOffset), its position in the full text (fullTextOffset), and its duration. transcript words are linked to their source audio recording.

#### frames
screenshots captured by rewind.ai at regular intervals as you use your computer. each frame in the `frame` table includes a timestamp (createdAt) and is linked to the application segment it belongs to. frames are the visual equivalent of audio recordings, capturing what was on your screen at specific moments.

#### nodes
text elements extracted from screen captures using optical character recognition (ocr). each node in the `node` table represents a piece of text visible on your screen, including its position (leftX, topY, width, height) and other metadata. nodes are linked to the frame they were extracted from. they are the visual equivalent of transcript words.

#### segments
application usage sessions that track when you were using specific applications and windows. each segment in the `segment` table includes the application bundle id, window name, start time, and end time. segments help organize frames and audio recordings by the application context they occurred in.

#### events
calendar events and meetings that were scheduled during your computer usage. the `event` table stores information about these events, including title, start time, end time, and other metadata. events provide additional context about what you were doing during specific time periods.

key relationships:
- audio segments are linked to transcript words
- frames are linked to nodes (text elements)
- frames and audio segments are associated with application segments
- events may be associated with specific segments

## development

### setup for development

```bash
# clone the repository
git clone https://github.com/yourusername/RewindMCP.git
cd RewindMCP

# install in development mode
pip install -e .

# install development dependencies
pip install pytest black isort
```

### running tests

```bash
# run all tests
pytest

# run a specific test
pytest test_mcp_server.py
```

## troubleshooting

### database connection issues

if you encounter database connection errors:

1. verify that the rewind.ai application is installed and has created the database
2. check that your `.env` file contains the correct database path and password
3. ensure the rewinddb module is properly installed

### no transcripts found

if no transcripts are returned:

1. verify that the time range contains data (try expanding the time range)
2. check that rewind.ai was actively recording during the requested time period
3. use the `--debug` flag with cli tools to see more information

### mcp server issues

if the mcp server fails to start or respond:

1. check that all dependencies are installed: `pip install fastapi uvicorn`
2. verify that the port is not in use by another application
3. check the server logs for specific error messages

## stats cli

the `stats_cli.py` tool provides comprehensive statistics about your rewind.ai data:

```bash
# get statistics about your rewind.ai data
python stats_cli.py

# use a custom .env file
python stats_cli.py --env /path/to/custom/.env
```

the stats cli provides information about:
- database overview (size, tables, record counts)
- audio transcript statistics (counts by time period, earliest records)
- screen ocr statistics (counts by time period, earliest records)
- application usage statistics (most used applications, usage time)
- table record counts

this tool is useful for understanding the scope and content of your rewind.ai data, and for diagnosing potential issues with data collection or storage.

## license

mit