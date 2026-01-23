Labhub supports logging of everything into an InfluxDB database. From there, it is possible to retrieve state of the system at a particular time or extract troubleshooting data. 
## How does it work
InfluxDB is a database independent on Labhub and must be installed and configured separately (retention time). When enabled, Labhub will save to InfluxDB:
- complete state, ie. values of all the properties at regular intervals
- value of a property whenever it is written to via labhub
- command calls + their arguments and results

## Installation
Install Influxdb 2.xx following this [tutorial](https://docs.influxdata.com/influxdb/v2/install/).
Once installed open http://localhost:8086 and:
1. Create username/password
2. Create an organization (e.g., `myorg`)
3. Create a bucket (e.g., `labhub`)
4. [Create](https://docs.influxdata.com/influxdb/v2/admin/tokens/create-token/) and copy the API token
## Configuration
Add this to your config.yaml file
```yaml
influx:
  enabled: true
  url: "http://localhost:8086"
  token: "your-api-token"
  org: "myorg"
  bucket: "labhub"
  exe_path: "C:/Program Files/InfluxData/influxdb2/influxd.exe"  # optional
  stop_on_exit: false     # only if InfluxDB was started by launcher
  snapshot_interval: 10.0 # in seconds
```
Whenever you start Labhub via [[Launcher]], it will check whether InfluxDB is already running. If not, it will start InfluxDB based on the provided exe_path. When launcher starts InfluxDB, it will also stop it if the `stop_on_exit` flag is set to `true`.  
## Data structure

|Measurement|When Written|Tags|Fields|
|---|---|---|---|
|`device_state`|Every 10s|`device_id`, `driver`|One per property + `_connected`|
|`property_set`|On API PATCH|`device_id`, `driver`, `property`, `source`|`{prop}_old`, `{prop}_new`|
|`command_exec`|On command|`device_id`, `driver`, `command`|`args`, `result`, `duration_ms`, `success`|

## Admin Status Endpoint

If something breaks try checking labhub admin status:

```bash
curl http://localhost:8212/api/v2/admin/influx/status
```