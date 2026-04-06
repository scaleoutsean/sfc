
## InfluxDB

### SQL API

HEADER="Authorization: Bearer "`cat /influxdb_tokens/sfc.token`

curl --cacert --cacert=/s3_certs/ca.crt --get https://influxdb:8181/api/v3/query_sql  --header "${HEADER}" --data-urlencode "db=sfc" --data-urlencode "q=SELECT * FROM accounts LIMIT 2"

### CLI

TOKEN=`cat /influxdb_tokens/sfc.token`
/home/influx/.influxdb/influxdb3 query -H https://influxdb:8181 --token "$TOKEN" --database "sfc" "SHOW TABLES"
/home/influx/.influxdb/influxdb3 query -H https://influxdb:8181 --token "$TOKEN" --database "sfc" "SHOW COLUMNS IN schedules"
/home/influx/.influxdb/influxdb3 query -H https://influxdb:8181 --token "$TOKEN" --database "sfc" "SELECT * FROM accounts LIMIT 1"
/home/influx/.influxdb/influxdb3 query -H https://influxdb:8181 --token "$TOKEN" --database "sfc" "SELECT cluster, name, latency_usec, time FROM volume_performance LIMIT 3"




