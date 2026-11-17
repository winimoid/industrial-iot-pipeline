# Industrial IoT Data Pipeline

> Collects telemetry from 5 simulated machines over MQTT, stores it in InfluxDB, flags anomalies in real time and
> visualises everything in Grafana. the whole stack starts with one `docker compose up`.

i have to write a better readme after

python -m pytest -v

tests/test_bridge_logic.py::test_anomaly_event_is_added_for_a_spike PASSED                                        [ 50%]
tests/test_bridge_logic.py::test_garbage_values_are_skipped_not_crashing PASSED                                   [ 75%]
tests/test_bridge_logic.py::test_bad_timestamp_falls_back_to_now_and_does_not_raise PASSED 



Data model: measurement `sensor_reading` (tag `machine_id`; fields `temperature_c`, `vibration_mm_s`, `current_a`)
and measurement `anomaly_event` (tags `machine_id`, `sensor`; fields `value`, `expected_mean`, `expected_std`, `z_score`, `injected`).

## 1. Stat - current temperature per machine (one tile per machine)
Visualization **Stat**. Title: `Temperature`. Unit: Celsius.
```flux
from(bucket: "telemetry")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "sensor_reading" and r._field == "temperature_c")
  |> group(columns: ["machine_id"])
  |> last()
```
- Standard options -> Unit: `Temperature / Celsius`; Display name: `${__field.labels.machine_id}`
- Thresholds: Base green, **80** amber, **90** red. Color mode: Background.

## 2. Time series - temperature, all machines
```flux
from(bucket: "telemetry")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "sensor_reading" and r._field == "temperature_c")
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
```
Set the time range to *Last 30 minutes*. Display name `${__field.labels.machine_id}`.
Make a **second panel** for `vibration_mm_s` (same query, change the field): temperature (~70) and vibration (~1.5)
share a chart badly because of the scale difference. If you insist on one chart, give vibration its own right-hand axis
(Overrides -> Axis placement -> Right).

## 3. Gauge - current draw per machine
```flux
from(bucket: "telemetry")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "sensor_reading" and r._field == "current_a")
  |> group(columns: ["machine_id"])
  |> last()
```
Visualization **Gauge**, Unit: Ampere, Min 0, Max 20, thresholds green / amber 14 / red 17.

## 4. Table - last 20 anomaly events
```flux
from(bucket: "telemetry")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "anomaly_event")
  |> pivot(rowKey: ["_time", "machine_id", "sensor"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "machine_id", "sensor", "value", "expected_mean", "expected_std", "z_score", "injected"])
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 20)
```

## 5. Alert - temperature > 90 C for more than 1 minute
1. Create a webhook at https://webhook.site and copy the URL.
2. **Alerting -> Contact points -> Add** -> type *Webhook*, paste the URL.
3. **Alerting -> Alert rules -> New alert rule**
   - Query **A** (data source InfluxDB):
     ```flux
     from(bucket: "telemetry")
       |> range(start: -5m)
       |> filter(fn: (r) => r._measurement == "sensor_reading" and r._field == "temperature_c")
       |> aggregateWindow(every: 10s, fn: mean, createEmpty: false)
     ```
   - Expression **B**: Reduce, input A, function *Last*. Expression **C**: Threshold, input B, *IS ABOVE* `90`.
   - Evaluate every `10s`, **Pending period `1m`**. Notification -> the webhook contact point.
4. Random spikes last one 2-second reading, so they never trip a 1-minute alert. That is why the simulator has a
   *sustained fault* mode: in `docker-compose.yml`, M3 overheats to ~100 C for 150 s every 10 minutes. Within ~12 min of
   starting the stack the rule should go Pending -> Firing and webhook.site shows the POST.

## 6. Export for the repo
Dashboard -> **Export -> Export as JSON** (leave "Export for sharing externally" **OFF**, so the fixed datasource uid
is kept) -> save as `grafana/dashboards/factory-overview.json`. On the next `docker compose up` it loads by itself.


in docker-compose.yml # command: ["python", "-u", "sensor_sim.py", "--fault-machine", "M3"]
    # we specify the faulty machine if we want to trigger grafana temp>90 celcius alert

l'erreur se trouve dans factory-overview.json, chaque panneau pointe encore vers l'ancien identifiant aléatoire "uid": "cg4gju3ybgnwgc", alors que la nouvelle source de données créée par le provisioning utilise l'identifiant fixe "uid": "influxdb-telemetry".