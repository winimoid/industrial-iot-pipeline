import paho.mqtt.client as mqtt
import time
import json
import random
import argparse
from datetime import datetime, timezone

# ---------- configuration ----------
MACHINES = ['M1', 'M2', 'M3', 'M4', 'M5']
SENSOR_KEYS = ['temperature_c', 'vibration_mm_s', 'current_a']
INTERVAL = 2  # seconds between messages
ANOMALY_CHANCE = 0.05  # 5% chance per sensor per reading
ANOMALY_MULTIPLIER = (1.5, 3.0)  # spike range

# slightly different baseline values for each machine to mimic variation
baselines = {
    'M1': {'temperature_c': 68, 'vibration_mm_s': 1.2, 'current_a': 10.5},
    'M2': {'temperature_c': 72, 'vibration_mm_s': 1.5, 'current_a': 11.2},
    'M3': {'temperature_c': 75, 'vibration_mm_s': 1.3, 'current_a': 12.0},
    'M4': {'temperature_c': 70, 'vibration_mm_s': 1.8, 'current_a': 10.8},
    'M5': {'temperature_c': 69, 'vibration_mm_s': 1.4, 'current_a': 11.5},
}

noise_std = {
    'temperature_c': 1.5,
    'vibration_mm_s': 0.2,
    'current_a': 0.5,
}

def generate_reading(machine_id):
    payload = {
        'machine_id': machine_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'sensors': {},
        'injected_anomaly': False,
    }

    for key in SENSOR_KEYS:
        base = baselines[machine_id][key]
        noise = random.gauss(0, noise_std[key])
        value = base + noise

        # inject anomaly?
        if random.random() < ANOMALY_CHANCE:
            factor = random.uniform(*ANOMALY_MULTIPLIER)
            value *= factor
            payload['injected_anomaly'] = True

        payload['sensors'][key] = round(value, 2)

    return payload

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--broker', default='localhost', help='MQTT broker address')
    parser.add_argument('--port', type=int, default=1883, help='MQTT broker port')
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(args.broker, args.port, 60)

    print(f"Simulator started. Publishing to {args.broker}:{args.port}...")
    while True:
        for machine in MACHINES:
            data = generate_reading(machine)
            topic = f"factory/machines/{machine}/telemetry"
            client.publish(topic, json.dumps(data))
            print(f"Published: {topic} -> {data['sensors']} (anomaly: {data['injected_anomaly']})")
        time.sleep(INTERVAL)

if __name__ == '__main__':
    main()
