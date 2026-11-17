# the flux queries i used to build the dashboard

Data source **InfluxDB** is provisioned automatically (Flux, uid `influxdb-telemetry`).
Open http://localhost:3001 (admin / admin) -> **Dashboards -> New -> New dashboard -> Add visualization**.

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
we set the time range to *Last 30 minutes*. Display name `${__field.labels.machine_id}`.
and make a **second panel** for `vibration_mm_s` (same query, change of the field): temperature (~70) and vibration (~1.5)
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
1. We have to create a webhook at https://webhook.site and copy the URL.
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
4. Random spikes last one 2 second reading so they never trip a 1-minute alert. That is why the simulator has a
   *sustained fault* mode: in `docker-compose.yml`, M3 overheats to ~100 C for 150 s every 10 minutes. Within ~12 min of
   starting the stack the rule should go Pending -> Firing and webhook.site shows the POST.

## 6. Export for the repo
Dashboard -> **Export -> Export as JSON** "Export for sharing externally" must be **OFF** so the fixed datasource uid is kept then -> save as `grafana/dashboards/factory-overview.json`. On the next `docker compose up` it loads by itself.