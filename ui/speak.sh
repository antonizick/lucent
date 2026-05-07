#!/bin/bash
# Quick Voice Box test command
# Usage: speak "Your message here"

TEXT="${1:-Test message}"

curl -s -X POST http://localhost:8001/speak \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"$TEXT\"}"
