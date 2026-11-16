import os

os.environ.setdefault("INFLUXDB_TOKEN", "test-token")  # bridge reads env at import time

from ingestion.anomaly import RollingDetector
from ingestion.bridge import build_points, parse_timestamp


def payload(temp=70.0, **extra):
    return {"machine_id": "M1", "timestamp": "2026-11-15T14:23:01.432+00:00",
            "sensors": {"temperature_c": temp, "vibration_mm_s": 1.2, "current_a": 10.5},
            "injected_anomaly": False, **extra}


def test_one_telemetry_point_with_three_fields_and_machine_tag():
    points = build_points(payload(), RollingDetector(10, 3.0))
    assert len(points) == 1
    line = points[0].to_line_protocol()
    assert line.startswith("sensor_reading,machine_id=M1 ")
    for field in ("temperature_c=70", "vibration_mm_s=1.2", "current_a=10.5"):
        assert field in line


def test_anomaly_event_is_added_for_a_spike():
    det = RollingDetector(10, 3.0)
    for i in range(10):
        build_points(payload(70 + (i % 3) * 0.5), det)
    points = build_points(payload(120.0, injected_anomaly=True), det)
    assert [p._name for p in points] == ["sensor_reading", "anomaly_event"]
    assert points[1]._tags["sensor"] == "temperature_c"
    assert points[1]._fields["injected"] is True


def test_garbage_values_are_skipped_not_crashing():
    bad = {"machine_id": "M1", "sensors": {"temperature_c": "n/a", "current_a": float("nan")}}
    assert build_points(bad, RollingDetector(10, 3.0)) == []


def test_bad_timestamp_falls_back_to_now_and_does_not_raise():
    assert parse_timestamp("not-a-date").tzinfo is not None
    assert parse_timestamp(None).tzinfo is not None
