import paho.mqtt.client as mqtt
import os
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
FAULT_DELTA_C = 25.0  # this is sustained overheating (when we want to simulate a fault oursef)

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

def generate_reading(machine_id, fault_active=False, rng=random):
    # add some noise to each reading
    values = {k: baselines[machine_id][k] + rng.gauss(0, noise_std[k]) for k in SENSOR_KEYS}

    injected_sensor = None

    if fault_active:
        # if we simulate a fault ourself we add overheating to temperature
        values['temperature_c'] += FAULT_DELTA_C
        injected_sensor = 'temperature_c'
    elif rng.random() < ANOMALY_CHANCE:
        # otherwise we randomly inject an anomaly into any sensor
        injected_sensor = rng.choice(SENSOR_KEYS)

        # values[injected_sensor] *= rng.uniform(ANOMALY_MULTIPLIER[0], ANOMALY_MULTIPLIER[1])
        values[injected_sensor] *= rng.uniform(*ANOMALY_MULTIPLIER)

    payload = {
        'machine_id': machine_id,
        'timestamp': datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        'sensors': {k: round(v, 2) for k, v in values.items()},
        # 'injected_anomaly': injected_sensor != None,
        'injected_anomaly': injected_sensor is not None,
        'injected_sensor': injected_sensor
    }

    return payload

def fault_is_active(now_s, period_s, duration_s):
    # fault is active at the end of the period
    # for the fault to trigger,where we are now in the period must be greater 
    # # than the durage where everything is ok
    return period_s > 0 and (now_s % period_s) >= (period_s - duration_s)

# custom connect with rety function every 2s
def connect_with_retry(client, host, port):
    while True:
        try:
            client.connect(host, port, keepalive=60)
            return
        except OSError as exception:
            print(f"Broker {host}:{port} is not available ({exception}). retying after 2s...", flush=True)
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--broker', default=os.getenv("MQTT_BROKER", "localhost"), help='MQTT broker address')
    parser.add_argument('--port', type=int, default=int(os.getenv("MQTT_PORT", 1883)), help='MQTT broker port')
    parser.add_argument('--interval', type=float, default=float(os.getenv("SIM_INTERVAL", 2)), 
                        help='Interval between messages in seconds')
    parser.add_argument("--fault-machine", choices=MACHINES, default=os.getenv("SIM_FAULT_MACHINE") or None, 
                        help="Machine ID to simulate an overheating fault sustained")
    parser.add_argument("--fault-period", type=int, default=600,
                        help="Period of the fault cycles in seconds")
    parser.add_argument("--fault-duration", type=int, default=150, 
                        help="How many seconds the fault lasts")
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    connect_with_retry(client, args.broker, args.port)  # retry to connect ro broker
    client.loop_start() # keep connection between broker and client alive

    print(f"Simulator started. Publishing to {args.broker}:{args.port} every {args.interval}s"
          + (f", fault on {args.fault_machine}" if args.fault_machine else ""), flush=True)

    # t_start = next_tick = time.time()
    t_start = next_tick = time.monotonic()

    try:
        while True:
            elapsed = time.monotonic() - t_start

            for machine in MACHINES:

                fault = machine == args.fault_machine and fault_is_active(elapsed, args.fault_period, 
                                                                        args.fault_duration)
                data = generate_reading(machine, fault_active=fault)
                topic = f"factory/machines/{machine}/telemetry"
                client.publish(topic, json.dumps(data))

                # if an anomaly was injected print it
                if data['injected_anomaly']:
                    print(f"[anomaly] {machine} {data['injected_sensor']} -> {data['sensors']}", flush=True)

            next_tick += args.interval # fixed the time drift
            time.sleep(max(0.0, next_tick - time.monotonic()))  # avoid negative time
    except KeyboardInterrupt:
        print("keyboard interrupt, stopping simulator...")
    finally:
        # we stop the keep alive and disconect finally
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    main()
