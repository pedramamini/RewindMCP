# Rewind.ai Database Schema

This document provides an overview of the Rewind.ai SQLite database schema based on analysis of the RewindDB code. It's intended to help users who want to manually query the database.

## Database Overview

The Rewind.ai database is an encrypted SQLite database that stores various types of data captured by the Rewind.ai application, including:

- Audio recordings and their transcriptions
- Screen captures and extracted text (OCR)
- Application and window usage information
- Events and user activity

## Encryption

The database uses SQLCipher (v4 compatibility) for encryption. To connect:

```sql
pragma key = 'your_password_here';
pragma cipher_compatibility = 4;
```

## File Locations

### Database File
The main database file is located at:
```
~/Library/Application Support/com.memoryvault.MemoryVault/db-enc.sqlite3
```

### Audio Snippets
Audio recordings are stored as snippets at:
```
~/Library/Application Support/com.memoryvault.MemoryVault/snippets/YYYY-MM-DDThh:mm:ss/snippet.m4a
```

### Screen Recordings
Screen recordings are stored as chunks at:
```
~/Library/Application Support/com.memoryvault.MemoryVault/chunks/YYYYMM/DD/[chunk_id]
```
Where:
- YYYYMM is the year and month (e.g., 202505 for May 2025)
- DD is the day (e.g., 13 for the 13th)
- [chunk_id] is a unique identifier for the recording chunk

## Main Tables

### Audio

Stores information about audio recording segments.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| startTime | integer/text | timestamp when recording started (ms since epoch or iso format) |
| duration | integer | duration in milliseconds |
| segmentId | integer | foreign key to segment table |
| path | text | path to the audio file |

### Transcript_Word

Stores individual words from audio transcriptions.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| segmentId | integer | foreign key to segment table (links to audio) |
| word | text | the transcribed word |
| timeOffset | integer | offset in milliseconds from audio segment start |
| duration | integer | duration of the word in milliseconds |
| speechSource | text | source of the speech |
| fullTextOffset | integer | offset in the full text |

### Frame

Stores information about screen capture frames.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| createdAt | integer/text | timestamp when frame was captured (ms since epoch or iso format) |
| segmentId | integer | foreign key to segment table |
| imageFileName | text | name of the image file |
| videoId | integer | foreign key to video table |
| videoFrameIndex | integer | index of the frame in the video |
| isStarred | integer | whether the frame is starred (0 or 1) |
| encodingStatus | text | status of the encoding process |

### Node

Stores text elements extracted from screen captures.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| frameId | integer | foreign key to frame table |
| nodeOrder | integer | order of the node in the frame |
| textOffset | integer | offset in the text content |
| textLength | integer | length of the text content |
| leftX | real | left X coordinate of the text element |
| topY | real | top Y coordinate of the text element |
| width | real | width of the text element |
| height | real | height of the text element |
| windowIndex | integer | index of the window containing the text |

### Segment

Stores information about application/window usage segments.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| bundleID | text | application bundle identifier |
| windowName | text | window title |
| startDate | text | timestamp when segment started |
| endDate | text | timestamp when segment ended |
| browserUrl | text | URL if the segment is a browser |
| browserProfile | text | browser profile if applicable |
| type | integer | type of segment |

### SearchRanking_Content

Stores OCR text content for searching.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| c0 | text | main text content extracted from screen |
| c1 | text | timestamp information |
| c2 | text | window/application information |

## Relationships

```graphviz
digraph RewindDB {
    rankdir=LR;
    node [shape=box, style=filled, fillcolor=lightblue];

    Segment -> Audio [label="1:N"];
    Segment -> Frame [label="1:N"];
    Audio -> Transcript_Word [label="1:N"];
    Frame -> Node [label="1:N"];
    Frame -> SearchRanking_Content [label="1:1", style=dashed];
    Event -> Segment [label="N:1"];
    Video -> Frame [label="1:N"];

    subgraph cluster_audio {
        label="Audio Processing";
        style=filled;
        fillcolor=lightyellow;
        Audio;
        Transcript_Word;
    }

    subgraph cluster_screen {
        label="Screen Processing";
        style=filled;
        fillcolor=lightgreen;
        Frame;
        Node;
        SearchRanking_Content;
        Video;
    }
}
```

## Timestamp Formats

The database uses two different timestamp formats:

1. Milliseconds since epoch (integer)
2. ISO format string (text): "YYYY-MM-DDThh:mm:ss.sss"

Queries need to handle both formats for compatibility.

## Example Queries

### Get Recent Audio Transcripts

```sql
SELECT
    a.id AS audio_id,
    a.startTime AS start_time,
    tw.word,
    tw.timeOffset AS time_offset
FROM
    audio a
JOIN
    transcript_word tw ON a.segmentId = tw.segmentId
WHERE
    a.startTime > (strftime('%s', 'now') - 3600) * 1000  -- last hour
ORDER BY
    a.startTime, tw.timeOffset;
```

### Search for Text in Transcripts

```sql
SELECT
    a.id AS audio_id,
    a.startTime AS start_time,
    tw.word,
    tw.timeOffset AS time_offset
FROM
    audio a
JOIN
    transcript_word tw ON a.segmentId = tw.segmentId
WHERE
    LOWER(tw.word) LIKE '%search_term%'
ORDER BY
    a.startTime, tw.timeOffset;
```

### Get Screen Text from Specific Application

```sql
SELECT
    f.id AS frame_id,
    f.createdAt AS created_at,
    n.textOffset,
    n.textLength,
    s.bundleID AS app_name,
    s.windowName AS window_name
FROM
    frame f
JOIN
    node n ON f.id = n.frameId
JOIN
    segment s ON f.segmentId = s.id
WHERE
    s.bundleID = 'com.example.app'
ORDER BY
    f.createdAt;
```

### Get Application Usage Statistics

```sql
SELECT
    s.bundleID AS app_name,
    COUNT(*) AS segment_count,
    SUM((julianday(s.endTime) - julianday(s.startTime)) * 86400) AS total_seconds
FROM
    segment s
WHERE
    s.startTime > datetime('now', '-7 days')
GROUP BY
    s.bundleID
ORDER BY
    total_seconds DESC;
```

## Notes on Querying

1. Always handle both timestamp formats (integer milliseconds and ISO string)
2. Use appropriate date/time functions based on the format
3. For text searches, use case-insensitive matching with `LOWER()` and `INSTR()` or `LIKE`
4. Join through the segment table to correlate audio and screen data

## Additional Tables

The database contains approximately 55 tables in total. The ones documented here are the main tables used for transcript and screen data queries. Other tables may exist for additional functionality.

## Complete Schema Reference

Below is a comprehensive reference of all tables in the Rewind.ai database.

### Audio
```sql
CREATE TABLE audio (
    id INTEGER PRIMARY KEY,
    segmentId INTEGER NOT NULL,
    path TEXT NOT NULL,
    startTime TEXT NOT NULL,
    duration REAL NOT NULL
);
```

### Frame
```sql
CREATE TABLE frame (
    id INTEGER PRIMARY KEY,
    createdAt TEXT NOT NULL,
    imageFileName TEXT NOT NULL,
    segmentId INTEGER,
    videoId INTEGER,
    videoFrameIndex INTEGER,
    isStarred INTEGER NOT NULL DEFAULT 0,
    encodingStatus TEXT
);
```

### Node
```sql
CREATE TABLE node (
    id INTEGER PRIMARY KEY,
    frameId INTEGER NOT NULL,
    nodeOrder INTEGER NOT NULL,
    textOffset INTEGER NOT NULL,
    textLength INTEGER NOT NULL,
    leftX REAL NOT NULL,
    topY REAL NOT NULL,
    width REAL NOT NULL,
    height REAL NOT NULL,
    windowIndex INTEGER
);
```

### Segment
```sql
CREATE TABLE segment (
    id INTEGER PRIMARY KEY,
    bundleID TEXT,
    startDate TEXT NOT NULL,
    endDate TEXT NOT NULL,
    windowName TEXT,
    browserUrl TEXT,
    browserProfile TEXT,
    type INTEGER NOT NULL DEFAULT 0
);
```

### Transcript_Word
```sql
CREATE TABLE transcript_word (
    id INTEGER PRIMARY KEY,
    segmentId INTEGER NOT NULL,
    speechSource TEXT NOT NULL,
    word TEXT NOT NULL,
    timeOffset INTEGER NOT NULL,
    fullTextOffset INTEGER,
    duration INTEGER NOT NULL
);
```

### Video
```sql
CREATE TABLE video (
    id INTEGER PRIMARY KEY,
    height INTEGER NOT NULL,
    width INTEGER NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    fileSize INTEGER,
    frameRate REAL NOT NULL DEFAULT 0.0,
    uploadedAt TEXT,
    xid TEXT,
    processingState INTEGER NOT NULL DEFAULT 0
);
```

### Doc_Segment
```sql
CREATE TABLE doc_segment (
    docid INTEGER NOT NULL,
    segmentId INTEGER NOT NULL,
    frameId INTEGER
);
```

### Event
```sql
CREATE TABLE event (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT,
    participants TEXT,
    detailsJSON TEXT,
    calendarID TEXT,
    calendarEventID TEXT,
    calendarSeriesID TEXT,
    segmentID INTEGER NOT NULL DEFAULT 0
);
```

### Summary
```sql
CREATE TABLE summary (
    id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    text TEXT,
    eventId INTEGER NOT NULL
);
```

### Frame_Processing
```sql
CREATE TABLE frame_processing (
    id INTEGER NOT NULL,
    processingType TEXT NOT NULL,
    createdAt TEXT NOT NULL DEFAULT '2023-04-17T14:12:30.029'
);
```

### VideoFileState
```sql
CREATE TABLE videoFileState (
    id TEXT PRIMARY KEY,
    downloadedAt TEXT
);
```

### SearchRanking
```sql
CREATE TABLE searchRanking (
    text TEXT,
    otherText TEXT,
    title TEXT
);
```

### SearchRanking_Config
```sql
CREATE TABLE searchRanking_config (
    k TEXT PRIMARY KEY,
    v TEXT
);
```

### SearchRanking_Content
```sql
CREATE TABLE searchRanking_content (
    id INTEGER PRIMARY KEY,
    c0 TEXT,  -- Main text content extracted from screen
    c1 TEXT,  -- Timestamp information
    c2 TEXT   -- Window/application information
);
```

This table is crucial for screen content search functionality. It stores the actual OCR text content extracted from screen captures, along with metadata about when and where the content was captured. The `id` field can be used to locate the corresponding recording chunk in the filesystem.

### SearchRanking_Data
```sql
CREATE TABLE searchRanking_data (
    id INTEGER PRIMARY KEY,
    block BLOB
);
```

### SearchRanking_Docsize
```sql
CREATE TABLE searchRanking_docsize (
    id INTEGER PRIMARY KEY,
    sz BLOB
);
```

### SearchRanking_Idx
```sql
CREATE TABLE searchRanking_idx (
    segid INTEGER NOT NULL,
    term TEXT NOT NULL,
    pgno INTEGER,
    PRIMARY KEY (segid, term)
);
```

### Search
```sql
CREATE TABLE search (
    text TEXT,
    otherText TEXT
);
```

### Search_Content
```sql
CREATE TABLE search_content (
    docid INTEGER PRIMARY KEY,
    c0text TEXT,
    c1otherText TEXT
);
```

### Search_Docsize
```sql
CREATE TABLE search_docsize (
    docid INTEGER PRIMARY KEY,
    size BLOB
);
```

### Search_Segdir
```sql
CREATE TABLE search_segdir (
    level INTEGER,
    idx INTEGER,
    start_block INTEGER,
    leaves_end_block INTEGER,
    end_block INTEGER,
    root BLOB,
    PRIMARY KEY (level, idx)
);
```

### Search_Segments
```sql
CREATE TABLE search_segments (
    blockid INTEGER PRIMARY KEY,
    block BLOB
);
```

### Search_Stat
```sql
CREATE TABLE search_stat (
    id INTEGER PRIMARY KEY,
    value BLOB
);
```

### SearchOffsets
```sql
CREATE TABLE searchOffsets (
    text TEXT,
    otherText TEXT
);
```

### SearchOffsets_Content
```sql
CREATE TABLE searchOffsets_content (
    docid INTEGER PRIMARY KEY,
    c0text TEXT,
    c1otherText TEXT
);
```

### SearchOffsets_Docsize
```sql
CREATE TABLE searchOffsets_docsize (
    docid INTEGER PRIMARY KEY,
    size BLOB
);
```

### SearchOffsets_Segdir
```sql
CREATE TABLE searchOffsets_segdir (
    level INTEGER,
    idx INTEGER,
    start_block INTEGER,
    leaves_end_block INTEGER,
    end_block INTEGER,
    root BLOB,
    PRIMARY KEY (level, idx)
);
```

### SearchOffsets_Segments
```sql
CREATE TABLE searchOffsets_segments (
    blockid INTEGER PRIMARY KEY,
    block BLOB
);
```

### SearchOffsets_Stat
```sql
CREATE TABLE searchOffsets_stat (
    id INTEGER PRIMARY KEY,
    value BLOB
);
```

### Tokenizer
```sql
CREATE TABLE tokenizer (
    input TEXT,
    token TEXT,
    start INTEGER,
    end INTEGER,
    position INTEGER
);
```

### Purge
```sql
CREATE TABLE purge (
    path TEXT NOT NULL,
    fileType TEXT NOT NULL
);
```

### Sqlite_Sequence
```sql
CREATE TABLE sqlite_sequence (
    name TEXT,
    seq INTEGER
);
```