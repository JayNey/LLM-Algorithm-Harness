#!/bin/bash
# Celery worker 启动脚本

export PYTHONPATH="${PYTHONPATH}:$(pwd)"

celery -A src.celery_app worker \
    --loglevel=info \
    --concurrency=4 \
    --max-tasks-per-child=50 \
    --queues=evaluations,default \
    --hostname=worker@%h
