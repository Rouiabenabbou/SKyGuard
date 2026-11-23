#!/bin/bash
# start broker + two emulated links (sat primary 10.9.0.x, g5 backup 10.8.0.x)
cd /tmp/claude-0/exp/x
pkill -f linkemu; pkill mosquitto; sleep 1
ip netns del devns 2>/dev/null; sleep 0.5
echo '{"delay_ms":0,"jitter_ms":0,"loss":0,"down":false}' > sat.json
echo '{"delay_ms":0,"jitter_ms":0,"loss":0,"down":false}' > g5.json
nohup ../venv/bin/python linkemu2.py --ns devns --name sat --host-ip 10.9.0.1 --dev-ip 10.9.0.2 --ctl sat.json > sat.log 2>&1 &
sleep 2
nohup ../venv/bin/python linkemu2.py --ns devns --name g5 --host-ip 10.8.0.1 --dev-ip 10.8.0.2 --ctl g5.json > g5.log 2>&1 &
sleep 2
nohup mosquitto -c ../mosq.conf > mosq.log 2>&1 &
sleep 1
cat sat.log g5.log
