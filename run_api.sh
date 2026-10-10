#!/bin/bash

# Start the LLM Algorithm Harness API server
# Usage: ./run_api.sh [--host 0.0.0.0] [--port 8000] [--reload]

set -e

# Default values
HOST="localhost"
PORT=8000
RELOAD=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --reload)
            RELOAD="--reload"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--host HOST] [--port PORT] [--reload]"
            exit 1
            ;;
    esac
done

echo "Starting LLM Algorithm Harness API..."
echo "Host: $HOST"
echo "Port: $PORT"
echo "API Documentation: http://$HOST:$PORT/docs"

# Run uvicorn
python3 -m uvicorn api.main:app --host "$HOST" --port "$PORT" $RELOAD
