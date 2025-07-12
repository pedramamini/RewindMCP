# RewindDB MCP STDIO Server

This is a Model Context Protocol (MCP) compliant STDIO server for RewindDB. It provides access to RewindDB functionality through the standardized MCP protocol, making it compatible with MCP clients like Raycast, Claude, and other AI assistants.

## Features

The server implements the MCP specification with proper JSON-RPC 2.0 protocol over STDIO transport and provides:

### Tools

- **`get_transcripts_relative`**: Get audio transcripts from a relative time period (e.g., "1hour", "30minutes", "1day", "1week"). Returns transcript sessions with full text content suitable for analysis, summarization, or detailed review. Each session includes complete transcript text and word-by-word timing.

- **`get_transcripts_absolute`**: **PRIMARY TOOL for meeting summaries** - Get complete audio transcripts from a specific time window (e.g., '3 PM meeting'). This is the FIRST tool to use when asked to summarize meetings, calls, or conversations from specific times. Returns full transcript sessions with complete text content ready for analysis and summarization.

- **`search_transcripts`**: Search for specific keywords/phrases in transcripts. **NOT for meeting summaries** - use `get_transcripts_absolute` instead when asked to summarize meetings from specific times. This tool finds keyword matches with context snippets, useful for finding specific topics or names mentioned across multiple sessions.

- **`search_screen_ocr`**: Search through OCR screen content for keywords. Finds text that appeared on screen during specific time periods. Use this to find what was displayed on screen, applications used, or visual content during meetings or work sessions. Complements audio transcripts by showing what was visible.

- **`get_activity_stats`**: Get activity statistics for a specified time period (e.g., "1hour", "30minutes", "1day", "1week"). Provides comprehensive statistics about audio recordings, screen captures, and application usage.

- **`get_transcript_by_id`**: **FOLLOW-UP TOOL** - Get complete transcript content by audio ID. Use this AFTER `get_transcripts_absolute` to retrieve full transcript text for summarization. Essential second step when the first tool shows preview text that needs complete content for proper analysis.

### Resources
- `rewinddb://transcripts`: Access to audio transcript data
- `rewinddb://activity`: Access to computer activity data

## Installation

1. Install the required dependencies:
```bash
pip install "mcp>=0.1.0" sqlcipher3 python-dotenv tabulate
```

2. Set up your RewindDB configuration in a `.env` file:
```bash
REWIND_DB_PATH=/path/to/your/rewind.db
REWIND_DB_PASSWORD=your_database_password
```

## Usage

### Running the Server

```bash
python mcp_stdio.py [--debug] [--env-file .env]
```

Options:
- `--debug`: Enable debug logging
- `--env-file FILE`: Path to .env file with database configuration (default: .env)

### MCP Client Integration

The server follows the MCP specification and can be used with any MCP-compatible client. Here's an example configuration for common clients:

#### MCP Configuration
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

## Protocol Compliance

This implementation follows the MCP specification:

- **Protocol Version**: 2024-11-05
- **Transport**: STDIO with JSON-RPC 2.0
- **Message Format**: Proper JSON-RPC 2.0 with `{"jsonrpc": "2.0", "method": "...", "params": {...}, "id": 1}`
- **Initialization**: Proper MCP handshake with capability negotiation
- **Error Handling**: JSON-RPC 2.0 compliant error responses

## Example Tool Calls

### Get Recent Transcripts (Relative Time)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_transcripts_relative",
    "arguments": {
      "time_period": "1hour"
    }
  }
}
```

### Get Transcripts from Specific Time Window (Primary for Meeting Summaries)
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get_transcripts_absolute",
    "arguments": {
      "from": "2025-06-05T14:00:00",
      "to": "2025-06-05T15:00:00",
      "timezone": "America/Chicago"
    }
  }
}
```

### Get Complete Transcript by ID (Follow-up Tool)
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_transcript_by_id",
    "arguments": {
      "audio_id": 12345
    }
  }
}
```

### Search Transcripts for Keywords
```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "search_transcripts",
    "arguments": {
      "keyword": "meeting",
      "relative": "1day"
    }
  }
}
```

### Search Screen OCR Content
```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "search_screen_ocr",
    "arguments": {
      "keyword": "password",
      "relative": "2hours",
      "application": "Chrome"
    }
  }
}
```

### Get Activity Statistics
```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "tools/call",
  "params": {
    "name": "get_activity_stats",
    "arguments": {
      "time_period": "1day"
    }
  }
}
```

## Testing

Run the test script to verify the server works correctly:

```bash
python test_mcp_stdio.py
```

This will test:
- MCP initialization handshake
- Tools listing
- Resources listing
- Basic protocol compliance

## Differences from Previous Implementation

The new implementation is fully MCP-compliant and differs from the previous version in several key ways:

1. **Proper JSON-RPC 2.0**: Uses standard JSON-RPC 2.0 message format
2. **MCP Initialization**: Implements proper MCP handshake with capability negotiation
3. **Standard Message Framing**: Uses proper STDIO transport instead of line-based reading
4. **Tool Schema**: Uses JSON Schema for tool input validation
5. **Error Handling**: Proper JSON-RPC 2.0 error responses
6. **Resource Support**: Implements MCP resource access pattern

## Troubleshooting

### Database Connection Issues
- Ensure your `.env` file has the correct `REWIND_DB_PATH` and `REWIND_DB_PASSWORD`
- Check that the RewindDB file exists and is accessible
- Verify the database password is correct

### MCP Client Issues
- Check that the client supports MCP protocol version 2024-11-05
- Ensure the server path and arguments are correct in client configuration
- Check server logs in `/tmp/mcp_stdio.log` for debugging information

### Performance
- The server connects to the database on first use and maintains the connection
- Large time ranges may take longer to process
- Use specific time periods for better performance

## Logging

The server logs to `/tmp/mcp_stdio.log`. Enable debug logging with the `--debug` flag for more detailed information.