import random
from datetime import datetime

from simulator.sensor_sim import MACHINES, SENSOR_KEYS, fault_is_active, generate_reading


def test_payload_schema():
    msg = generate_reading("M1", rng=random.Random(0))
    assert set(msg) == {"machine_id", "timestamp", "sensors", "injected_anomaly", "injected_sensor"}
    assert set(msg["sensors"]) == set(SENSOR_KEYS)
    datetime.fromisoformat(msg["timestamp"])  # must parse


def test_no_injection_when_chance_is_zero():
    for m in MACHINES:
        msg = generate_reading(m, anomaly_chance=0.0, rng=random.Random(1))
        assert msg["injected_anomaly"] is False and msg["injected_sensor"] is None


def test_injection_always_flags_exactly_one_sensor():
    msg = generate_reading("M1", anomaly_chance=1.0, rng=random.Random(2))
    assert msg["injected_anomaly"] is True and msg["injected_sensor"] in SENSOR_KEYS


def test_fault_pushes_temperature_over_alert_threshold():
    msg = generate_reading("M3", fault_active=True, rng=random.Random(3))
    assert msg["sensors"]["temperature_c"] > 90  # the Grafana alert threshold


def test_fault_window_is_at_end_of_period():
    assert not fault_is_active(10, 600, 150)
    assert fault_is_active(500, 600, 150)
    assert not fault_is_active(10, 0, 150)  # period 0 disables faults
