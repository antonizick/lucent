# Voice Box Activity Logging

## Overview
The Voice Box now maintains a complete activity log of all speech output, with automatic monthly compression and archival.

## Features

### Activity Logging
- Every message sent to the Voice Box via `/speak` endpoint is logged to a daily activity file
- Logs are stored in `ui/logs/activity_YYYY-MM-DD.log`
- Each entry includes: timestamp (ISO 8601), source, and message text
- Format: `[2026-05-09T10:30:45.123456] [voice_box] Message text here`

### Directory Structure
```
ui/logs/
├── activity_2026-05-09.log    # Today's activity log
├── activity_2026-05-08.log    # Previous days
├── archives/
│   ├── activity_2026-04.tar.gz    # Compressed monthly archives
│   ├── activity_2026-03.tar.gz
│   └── ...
```

### Automatic Monthly Compression
- Runs at server startup and whenever `/logs/compress-monthly` is called
- Compresses all logs from the previous month into a `.tar.gz` file
- Removes original log files after successful compression
- Archive name format: `activity_YYYY-MM.tar.gz`
- Example: All April logs are compressed into `activity_2026-04.tar.gz`

## API Endpoints

### Get Today's Activity Log
```bash
GET /activity-log
```
Returns: JSON with date, content, and entry count
```json
{
  "date": "2026-05-09",
  "content": "[2026-05-09T10:30:45...] [voice_box] Message\n...",
  "entries": 42
}
```

### List All Archives
```bash
GET /logs/archives
```
Returns: List of all compressed archives with size and modification date
```json
{
  "archives": [
    {
      "name": "activity_2026-04.tar.gz",
      "size_bytes": 1024,
      "size_mb": 0.001,
      "modified": "2026-05-09T02:01:10.706127"
    }
  ],
  "total": 1
}
```

### Download Archive
```bash
GET /logs/archives/{archive_name}
```
Example: `curl http://localhost:8001/logs/archives/activity_2026-04.tar.gz -o archive.tar.gz`

### Trigger Monthly Compression
```bash
POST /logs/compress-monthly
```
Returns: Compression result with statistics
```json
{
  "status": "success",
  "month": "2026-04",
  "archive": "activity_2026-04.tar.gz",
  "logs_compressed": 42
}
```

## Voice Box Speaking
The existing `/speak` endpoint now automatically logs activity:
```bash
POST /speak
Content-Type: application/json

{"text": "Your message here"}
```
This message will be:
1. Queued for TTS
2. Logged to today's activity file with timestamp
3. Available via `/activity-log` endpoint

## Implementation Details
- Written to `ui/server.py`
- Imports: `tarfile`, `shutil` for compression
- `init_logs_dirs()`: Ensures `logs/` and `logs/archives/` directories exist
- `log_activity()`: Writes timestamped entries to daily logs
- `compress_monthly_logs()`: Archives previous month's logs
- Startup event checks and compresses logs when server starts

## Usage Examples

### Check today's activity
```bash
curl http://localhost:8001/activity-log | jq
```

### See all archives
```bash
curl http://localhost:8001/logs/archives | jq
```

### Download April archive
```bash
curl http://localhost:8001/logs/archives/activity_2026-04.tar.gz -o april.tar.gz
tar -xzf april.tar.gz
```

### Force compression (useful for testing)
```bash
curl -X POST http://localhost:8001/logs/compress-monthly | jq
```
