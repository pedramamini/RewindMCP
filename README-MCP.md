# RewindDB MCP Server

Model Context Protocol server for RewindDB that exposes the services provided by the CLI tools to GenAI models.

## Overview

The RewindDB MCP server provides a FastAPI-based implementation of the Model Context Protocol (MCP) that allows GenAI models to access RewindDB functionality. It exposes endpoints for retrieving audio transcripts and searching across both audio and screen data.

## Requirements

- Python 3.6+
- RewindDB library
- FastAPI
- Uvicorn
- Pydantic

## Installation

```bash
pip install fastapi uvicorn
```

The server is part of the RewindDB project and uses the RewindDB library.

## Usage

### Starting the Server

```bash
./mcp_server.py --port 8000
```

or

```bash
python mcp_server.py --port 8000
```

### Command Line Options

- `--host`: Host to bind to (default: 0.0.0.0)
- `--port`: Port to bind to (default: 8000)
- `--debug`: Enable debug logging

## API Endpoints

### MCP Protocol Endpoints

- `GET /mcp/tools`: List available tools
- `GET /mcp/resources`: List available resources
- `POST /mcp/tools/{tool_name}`: Execute a tool
- `GET /mcp/resources/{resource_uri}`: Access a resource

### Health Check

- `GET /health`: Check server health

## Available Tools

### get_transcripts_relative

Retrieve audio transcripts from a relative time period.

**Parameters:**
- `time_period`: Relative time period (e.g., '1hour', '30minutes', '1day')

**example request:**
```json
{
  "time_period": "1hour"
}
```

### get_transcripts_absolute

Retrieve audio transcripts from a specific time range.

**Parameters:**
- `from`: Start time in ISO format
- `to`: End time in ISO format

**example request:**
```json
{
  "from": "2023-05-11T13:00:00",
  "to": "2023-05-11T17:00:00"
}
```

### search

Search for keywords across both audio and screen data.

**Parameters:**
- `keyword`: Keyword to search for
- `relative`: (Optional) Relative time period (e.g., '1day', '7days')
- `from`: (Optional) Start time in ISO format
- `to`: (Optional) End time in ISO format

**example request with relative time:**
```json
{
  "keyword": "meeting",
  "relative": "1day"
}
```

**example request with absolute time range:**
```json
{
  "keyword": "project",
  "from": "2023-05-11T13:00:00",
  "to": "2023-05-11T17:00:00"
}
```

## API Documentation

When the server is running, you can access the auto-generated API documentation at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Example Usage with cURL

### Get Transcripts from the Last Hour

```bash
curl -X POST "http://localhost:8000/mcp/tools/get_transcripts_relative" \
  -H "Content-Type: application/json" \
  -d '{"time_period": "1hour"}'
```

### Get Transcripts from a Specific Time Range

```bash
curl -X POST "http://localhost:8000/mcp/tools/get_transcripts_absolute" \
  -H "Content-Type: application/json" \
  -d '{"from": "2023-05-11T13:00:00", "to": "2023-05-11T17:00:00"}'
```

### Search for Keywords

```bash
curl -X POST "http://localhost:8000/mcp/tools/search" \
  -H "Content-Type: application/json" \
  -d '{"keyword": "meeting", "relative": "1day"}'
```

## Integration with GenAI Models

The server implements the Model Context Protocol (MCP), which allows GenAI models to access external tools and resources. The MCP server can be connected to GenAI models that support the protocol, enabling them to retrieve and search through RewindDB data.