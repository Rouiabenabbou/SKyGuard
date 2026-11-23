#!/bin/bash
until grep -q "^done" /tmp/claude-0/exp/x1/x1_run.log && grep -q "geo-burst done" /tmp/claude-0/exp/x3/x3_run.log; do sleep 20; done
sleep 20
pkill -f "uvicorn app.main:app --port 800"; pkill -f x1_devices.py; pkill -f x4_sub.py; sleep 3
cd /tmp/claude-0/exp/x5 && /tmp/claude-0/exp/venv/bin/python x5_run.py > x5_run.log 2>&1
echo chain-done; date
