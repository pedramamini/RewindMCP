# RewindDB MCP Server

model context protocol server for rewinddb that exposes the services provided by the cli tools to genai models.

## overview

the rewinddb mcp server provides a fastapi-based implementation of the model context protocol (mcp) that allows genai models to access rewinddb functionality. it exposes endpoints for retrieving audio transcripts and searching across both audio and screen data.

## requirements

- python 3.6+
- rewinddb library
- fastapi
- uvicorn
- pydantic

## installation

```bash
pip install fastapi uvicorn
```

the server is part of the rewinddb project and uses the rewinddb library.

## usage

### starting the server

```bash
./mcp_server.py --port 8000
```

or

```bash
python mcp_server.py --port 8000
```

### command line options

- `--host`: host to bind to (default: 0.0.0.0)
- `--port`: port to bind to (default: 8000)
- `--debug`: enable debug logging

## api endpoints

### mcp protocol endpoints

- `GET /mcp/tools`: list available tools
- `GET /mcp/resources`: list available resources
- `POST /mcp/tools/{tool_name}`: execute a tool
- `GET /mcp/resources/{resource_uri}`: access a resource

### health check

- `GET /health`: check server health

## available tools

### get_transcripts_relative

retrieve audio transcripts from a relative time period.

**parameters:**
- `time_period`: relative time period (e.g., '1hour', '30minutes', '1day')

**example request:**
```json
{
  "time_period": "1hour"
}
```

### get_transcripts_absolute

retrieve audio transcripts from a specific time range.

**parameters:**
- `from`: start time in iso format
- `to`: end time in iso format

**example request:**
```json
{
  "from": "2023-05-11T13:00:00",
  "to": "2023-05-11T17:00:00"
}
```

### search

search for keywords across both audio and screen data.

**parameters:**
- `keyword`: keyword to search for
- `relative`: (optional) relative time period (e.g., '1day', '7days')
- `from`: (optional) start time in iso format
- `to`: (optional) end time in iso format

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

## api documentation

when the server is running, you can access the auto-generated api documentation at:

- swagger ui: `http://localhost:8000/docs`
- redoc: `http://localhost:8000/redoc`

## example usage with curl

### get transcripts from the last hour

```bash
curl -X POST "http://localhost:8000/mcp/tools/get_transcripts_relative" \
  -H "Content-Type: application/json" \
  -d '{"time_period": "1hour"}'
```

### get transcripts from a specific time range

```bash
curl -X POST "http://localhost:8000/mcp/tools/get_transcripts_absolute" \
  -H "Content-Type: application/json" \
  -d '{"from": "2023-05-11T13:00:00", "to": "2023-05-11T17:00:00"}'
```

### search for keywords

```bash
curl -X POST "http://localhost:8000/mcp/tools/search" \
  -H "Content-Type: application/json" \
  -d '{"keyword": "meeting", "relative": "1day"}'
```

## integration with genai models

the server implements the model context protocol (mcp), which allows genai models to access external tools and resources. the mcp server can be connected to genai models that support the protocol, enabling them to retrieve and search through rewinddb data.