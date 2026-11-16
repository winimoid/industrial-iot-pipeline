# Industrial IoT Data Pipeline

> Collects telemetry from 5 simulated machines over MQTT, stores it in InfluxDB, flags anomalies in real time and
> visualises everything in Grafana. the whole stack starts with one `docker compose up`.

i have to write a better readme after

python -m pytest -v

tests/test_bridge_logic.py::test_anomaly_event_is_added_for_a_spike PASSED                                        [ 50%]
tests/test_bridge_logic.py::test_garbage_values_are_skipped_not_crashing PASSED                                   [ 75%]
tests/test_bridge_logic.py::test_bad_timestamp_falls_back_to_now_and_does_not_raise PASSED 