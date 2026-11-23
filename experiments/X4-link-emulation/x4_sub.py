"""Broker-side receiver (root namespace): logs every telemetry delivery with exact receive time."""
import json, sys, time
import paho.mqtt.client as mqtt
out = open(sys.argv[1], "a")
def on_msg(c, u, m):
    t = int(time.time() * 1000)
    try:
        p = json.loads(m.payload); out.write(f"{p['device_id']},{p['seq']},{p['ts_sent']},{t}\n"); out.flush()
    except Exception: pass
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="x4-sub")
c.on_connect = lambda c, *x: c.subscribe("cybershield/iot/+/telemetry", qos=1)
c.on_message = on_msg
c.connect("127.0.0.1", 1883, 60); c.loop_forever()
