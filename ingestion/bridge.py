import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import json
import os
import numpy as np
from collections import defaultdict
from datetime import datetime

# ---------- configuration ----------
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = "factory/machines/#"

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "my-token-i-won-t-share-with-you")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "factory")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "telemetry")

ANOMALY_WINDOW = 10      # number of past readings for z‑score
ANOMALY_THRESHOLD = 2.5  # standard deviations

# ---------- we set a rolling buffer for anomaly detection ----------
buffer = defaultdict(list)  # key: "machine_id:sensor", value is deque of floats

def detect_anomaly(machine, sensor, value):
    key = f"{machine}:{sensor}"
    history = buffer[key]
    history.append(value)
    if len(history) > ANOMALY_WINDOW:
        history.pop(0)

    if len(history) < ANOMALY_WINDOW:
        return False, 0, 0

    mean = np.mean(history)
    std = np.std(history)
    if std == 0:
        return False, mean, std

    z = abs(value - mean) / std

    return z > ANOMALY_THRESHOLD, mean, std

# ---------- influxDB client ----------
client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

# ---------- MQTT callbacks ----------
def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connected to MQTT broker, subscribing to {MQTT_TOPIC}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print(f"Invalid JSON on topic {msg.topic}")
        return

    machine_id = payload.get("machine_id", "unknown")
    timestamp = payload.get("timestamp")
    sensors = payload.get("sensors", {})
    injected = payload.get("injected_anomaly", False)

    # then we convert ISO timestamp to datetime
    try:
        ts = datetime.fromisoformat(timestamp)
    except Exception:
        ts = datetime.now(datetime.timezone.utc)

    for sensor, value in sensors.items():
        # normal telemetry point
        point = (
            Point("sensor_reading")
            .tag("machine_id", machine_id)
            .field(sensor, float(value))
            .time(ts)
        )
        write_api.write(bucket=INFLUXDB_BUCKET, record=point)

        # it detect anomaly
        is_anomaly, mean, std = detect_anomaly(machine_id, sensor, float(value))
        if is_anomaly:
            anomaly_point = (
                Point("anomaly_event")
                .tag("machine_id", machine_id)
                .tag("sensor", sensor)
                .field("value", float(value))
                .field("expected_mean", round(mean, 2))
                .field("expected_std", round(std, 2))
                .field("z_score", round(abs(float(value) - mean) / std, 2))
                .field("injected", injected)
                .time(ts)
            )
            write_api.write(bucket=INFLUXDB_BUCKET, record=anomaly_point)
            print(f"ANOMALY: {machine_id} {sensor} = {value:.2f} (mean {mean:.2f}, std {std:.2f})")

    print(f"Processed: {machine_id} - {sensors}")

def main():
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    print("Bridge started. Forwarding MQTT → InfluxDB...")
    mqtt_client.loop_forever()

if __name__ == "__main__":
    main()
