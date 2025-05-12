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

## Main Tables

### Audio

Stores information about audio recording segments.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| startTime | integer/text | timestamp when recording started (ms since epoch or iso format) |
| duration | integer | duration in milliseconds |
| segmentId | integer | foreign key to segment table |

### Transcript_Word

Stores individual words from audio transcriptions.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| segmentId | integer | foreign key to segment table (links to audio) |
| word | text | the transcribed word |
| timeOffset | integer | offset in milliseconds from audio segment start |
| duration | integer | duration of the word in milliseconds |

### Frame

Stores information about screen capture frames.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| createdAt | integer/text | timestamp when frame was captured (ms since epoch or iso format) |
| segmentId | integer | foreign key to segment table |

### Node

Stores text elements extracted from screen captures.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| frameId | integer | foreign key to frame table |
| textOffset | integer | offset in the text content |
| textLength | integer | length of the text content |

### Segment

Stores information about application/window usage segments.

| column | type | description |
|--------|------|-------------|
| id | integer | primary key |
| bundleID | text | application bundle identifier |
| windowName | text | window title |
| startTime | integer/text | timestamp when segment started |
| endTime | integer/text | timestamp when segment ended |

## Relationships

```
Segment
  ↑
  | one-to-many
  |
Audio ← one-to-many → Transcript_Word

Segment
  ↑
  | one-to-many
  |
Frame ← one-to-many → Node
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
    c0 TEXT,
    c1 TEXT,
    c2 TEXT
);
```

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