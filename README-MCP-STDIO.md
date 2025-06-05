# RewindDB MCP STDIO Server

This is a Model Context Protocol (MCP) compliant STDIO server for RewindDB. It provides access to RewindDB functionality through the standardized MCP protocol, making it compatible with MCP clients like Raycast, Claude, and other AI assistants.

## Features

The server implements the MCP specification with proper JSON-RPC 2.0 protocol over STDIO transport and provides:

### Tools
- `get_transcripts_relative`: Get audio transcripts from a relative time period (e.g., "1hour", "30minutes", "1day")
- `search_transcripts`: Search through audio transcripts for keywords with optional time filtering
- `search_screen_ocr`: Search through OCR screen content for keywords with optional time and application filtering
- `get_activity_stats`: Get activity statistics for a specified time period
- `get_transcript_by_id`: Get a specific transcript by audio ID

### Resources
- `rewinddb://transcripts`: Access to audio transcript data
- `rewinddb://activity`: Access to computer activity data

## Installation

1. Install the required dependencies:
```bash
pip install "mcp>=0.1.0" pysqlcipher3 python-dotenv
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

### Get Recent Transcripts
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

### Search Transcripts
```json
{
  "jsonrpc": "2.0",
  "id": 2,
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
  "id": 3,
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
  "id": 3,
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