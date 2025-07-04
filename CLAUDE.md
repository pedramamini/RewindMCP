# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RewindMCP is a Python library that interfaces with the Rewind.ai SQLite database to access audio transcripts and screen OCR data. The project has three main components:

1. **Core Library** (`rewinddb/`): Python library for direct database access
2. **CLI Tools**: Command-line interfaces for data retrieval and search
3. **MCP Server**: Model Context Protocol server exposing functionality to AI models

## Development Commands

### Installation
```bash
# Install in development mode
pip install -e .

# Install dependencies
pip install pysqlcipher3 pydantic requests python-dotenv "mcp>=0.1.0"
```

### Testing
```bash
# Run specific test files
python test_ocr_tools.py
python test_deduplication.py
python test_fuzzy_deduplication.py
python test_fast_deduplication.py

# Test MCP server functionality
python scratch/test_mcp_stdio.py
```

### Running Tools
```bash
# CLI tools (require .env configuration)
python transcript_cli.py --relative "1 hour"
python search_cli.py "keyword" --relative "1 day"
python ocr_cli.py --relative "2 hours"
python activity_cli.py --relative "1 day"
python stats_cli.py

# MCP server
python mcp_stdio.py --debug
```

## Architecture

### Core Components

- **`rewinddb/core.py`**: Main `RewindDB` class with database connection and query methods
- **`rewinddb/config.py`**: Configuration management for database path/password from .env files
- **`rewinddb/utils.py`**: Utility functions for time parsing and data processing
- **`mcp_stdio.py`**: MCP server implementing the Model Context Protocol for AI integration

### Database Schema

The Rewind.ai database contains:
- `audio`: Audio recording segments with timestamps
- `transcript_word`: Individual transcribed words with timing
- `frame`: Screen capture frames
- `node`: OCR text elements from frames
- `searchRanking_content`: Complete OCR text content for searching
- `segment`: Application usage sessions
- `event`: Calendar events/meetings

### Data Flow

1. **Audio Path**: `audio` → `transcript_word` (speech-to-text with timing)
2. **Screen Path**: `frame` → `node` (OCR with positioning) + `searchRanking_content` (full text)
3. **Context**: Both linked to `segment` (application sessions) and `event` (meetings)

## Configuration

### Environment Setup
The project requires a `.env` file (or `~/.rewinddb.env`) with:
```
DB_PATH=/Users/username/Library/Application Support/com.memoryvault.MemoryVault/db-enc.sqlite3
DB_PASSWORD=your_database_password
```

### MCP Integration
For AI assistants, configure MCP server in client:
```json
{
  "mcpServers": {
    "rewinddb": {
      "command": "python",
      "args": ["/path/to/mcp_stdio.py"],
      "env": {
        "REWIND_DB_PATH": "/path/to/db-enc.sqlite3",
        "REWIND_DB_PASSWORD": "password"
      }
    }
  }
}
```

## Key Patterns

### Time Handling
All tools support flexible time parsing:
- Relative: "1 hour", "30 minutes", "2 days", "1 week" (also short forms: "1h", "30m", "2d", "1w")
- Absolute: ISO format timestamps with timezone support
- Smart parsing in `rewinddb/utils.py`

### Database Access
- Always use context manager pattern: `with RewindDB() as db:`
- Connection uses pysqlcipher3 for encrypted database access
- Error handling for database connection and query failures

### MCP Tools Structure
MCP server exposes 10+ tools for:
- Transcript retrieval (relative/absolute time ranges)
- OCR content access (with application filtering)  
- Keyword searching across both data types
- Application discovery and activity statistics

## Development Notes

- **Scratch Directory**: Contains experimental scripts and database exploration tools
- **Performance Focus**: Several deduplication and speed optimization scripts
- **Error Handling**: Comprehensive logging and debug modes throughout
- **Security**: Database password handling through environment variables only

## Development Best Practices

- All temporary and data exploration tools should go under scratch/ and you should look there for existing testing/validation tools before writing new ones.

## Investigation Notes

- Exported audio clips investigation
  - Confirmed both sides of conversation are present in exported clips
  - Uncertain if .TXT transcripts are exclusively user's voice