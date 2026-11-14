import math

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import json
import os
import sys
import numpy as np
from collections import defaultdict
from datetime import datetime, time, timezone

from ingestion.anomaly import RollingDetector

try:  # local dev mode run the file without aspetting for docker
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------- configuration ----------
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
topics_string = os.getenv("MQTT_TOPICS", "factory/machines/#")
MQTT_TOPICS = [t.strip() for t in topics_string.split(",") if t.strip()]

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "my-token-i-won-t-share-with-you")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "factory")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "telemetry")

ANOMALY_WINDOW = int(os.getenv("ANOMALY_WINDOW", 30))      # number of past readings for z score
ANOMALY_THRESHOLD = float(os.getenv("ANOMALY_THRESHOLD", 3.5)) # standard deviations

def parse_timestamp(raw):
    # to resolve that f crash bug
    try:
        ts = datetime.fromisoformat(raw)
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def build_points(payload, detector):
    """Turn one MQTT payload into InfluxDB points to stock and test"""
    machine_id = str(payload.get("machine_id", "unknown"))
    ts = parse_timestamp(payload.get("timestamp"))
    injected = bool(payload.get("injected_anomaly", False))

    # influxdb point
    reading = Point("sensor_reading").tag("machine_id", machine_id).time(ts)
    anomalies = []
    n_fields = 0

    for sensor, raw in (payload.get("sensors") or {}).items():
        try:  # do some sanity check
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        reading.field(sensor, value)
        n_fields += 1

        hit = detector.check(machine_id, sensor, value)  # check if is anomaly
        if hit:
            anomalies.append(
                Point("anomaly_event")
                .tag("machine_id", machine_id)
                .tag("sensor", sensor)
                .field("value", value)
                .field("expected_mean", round(hit["mean"], 2))
                .field("expected_std", round(hit["std"], 3))
                .field("z_score", round(hit["z"], 2))
                .field("injected", injected)
                .time(ts)
            )

    return ([reading] + anomalies) if n_fields else []

def main():
    if not INFLUXDB_TOKEN:  # without token we can do nothing
        sys.exit("INFLUXDB_TOKEN is empty in .env")

    detector = RollingDetector(ANOMALY_WINDOW, ANOMALY_THRESHOLD)
    influx = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    write_api = influx.write_api(write_options=SYNCHRONOUS)

    # print that influxdb started and initialize stats
    print(f"InfluxDB {INFLUXDB_URL} reachable: {influx.ping()}", flush=True)
    stats = {"messages": 0, "anomalies": 0}

    # when client connect to broker
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"MQTT connect failed: {reason_code}", flush=True)
            return
        for topic in MQTT_TOPICS:  # re-subscribe on every (re)connect
            client.subscribe(topic)  # subscribe to topic
        print(f"Connected to MQTT {MQTT_BROKER}:{MQTT_PORT}, subscribed to {MQTT_TOPICS}", flush=True)

    # when receive a message from broker format and write to influx
    def on_message(client, userdata, msg):
        try:  # deserialize message and turn to  dict
            payload = json.loads(msg.payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            print(f"Invalid JSON on {msg.topic}", flush=True)
            return
        if not isinstance(payload, dict):
            print(f"Invalid payload format on {msg.topic}", flush=True)
            return

        points = build_points(payload, detector)
        if not points:
            return
        try:
            write_api.write(bucket=INFLUXDB_BUCKET, record=points)
        except Exception as exc:  # keep the bridge alive if Influx hiccups
            print(f"InfluxDB write failed: {exc}", file=sys.stderr, flush=True)
            return

        # we increase stats counter and print
        stats["messages"] += 1
        for p in points[1:]:
            stats["anomalies"] += 1
            print(f"ANOMALY {p._tags['machine_id']} {p._tags['sensor']} "
                    f"value={p._fields['value']} z={p._fields['z_score']}", flush=True)
        if stats["messages"] % 100 == 0:  # print every 100 messages to not anoy
            print(f"[{stats['messages']} messages, {stats['anomalies']} anomalies so far]", flush=True)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    while True:  # broker may still be starting
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            break
        except OSError as exc:
            print(f"Broker {MQTT_BROKER}:{MQTT_PORT} not reachable ({exc}); retrying in 2 s...", flush=True)
            time.sleep(2)

    try:
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        print("Stopping bridge.")
    finally:
        mqtt_client.disconnect()  # always disconnect finally
        influx.close()


if __name__ == "__main__":
    main()
