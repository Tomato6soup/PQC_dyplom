#!/bin/bash
set -uo pipefail

HOST="http://127.0.0.1:9944"
PROM_URL="http://localhost:9090/api/v1/query"
PROCESSES=6
SPAWN_RATE=20
LOGDIR="logs_duration_sweep"
MAX_WAIT=120
POLL_INTERVAL=2
SETTLE_EXTRA=5
TPS_HEAD_START=3
RES_SAMPLE_INTERVAL=3
MIN_TMP_FREE_MB=1200
algo="sphincs"

# format: "U:dur_s:start_run:end_run"
CONFIGS=(
    "10:90:3:3"
    "100:30:1:3"
    "100:60:1:3"
    "100:90:1:3"
    "300:30:1:3"
    "300:60:1:3"
    "300:90:1:3"
)

mkdir -p "$LOGDIR"

query_prometheus() {
    local query="$1"
    curl -s --data-urlencode "query=$query" "$PROM_URL" \
        | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    r = d['data']['result']
    print(r[0]['value'][1] if r else '')
except Exception:
    print('')
" 2>/dev/null
}

check_tmp_space() {
    local avail_mb
    avail_mb=$(df --output=avail -m /tmp | tail -1 | tr -d ' ')
    if [[ "$avail_mb" -lt "$MIN_TMP_FREE_MB" ]]; then
        echo ""
        echo "!!!!! PRZERYWAM: /tmp ma tylko ${avail_mb}MB wolnego (prog ${MIN_TMP_FREE_MB}MB) !!!!!"
        exit 1
    fi
}

wait_for_empty_pool() {
    local waited=0
    local pending
    while true; do
        pending=$(curl -s -H "Content-Type: application/json" \
            -d '{"id":1,"jsonrpc":"2.0","method":"author_pendingExtrinsics","params":[]}' \
            "$HOST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('result', [])))" 2>/dev/null)
        if [[ "$pending" == "0" ]]; then
            echo "    [pool] pusty po ${waited}s, czekam jeszcze ${SETTLE_EXTRA}s..."
            sleep "$SETTLE_EXTRA"
            return 0
        fi
        if [[ "$waited" -ge "$MAX_WAIT" ]]; then
            echo "    [pool] UWAGA: nie oprozniol sie po ${MAX_WAIT}s - jedziemy dalej"
            return 1
        fi
        sleep "$POLL_INTERVAL"
        waited=$((waited + POLL_INTERVAL))
    done
}

sample_resources() {
    local reslog="$1"
    local duration="$2"
    local end=$(( $(date +%s) + duration ))
    echo "timestamp,cpu_pct,ram_mb" > "$reslog"
    while [ "$(date +%s)" -lt "$end" ]; do
        cpu=$(query_prometheus '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[30s])) * 100)')
        ram=$(query_prometheus '(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / (1024 * 1024)')
        echo "$(date +%s),${cpu},${ram}" >> "$reslog"
        sleep "$RES_SAMPLE_INTERVAL"
    done
}

total=0
for c in "${CONFIGS[@]}"; do
    IFS=":" read -r u dur sr er <<< "$c"
    total=$((total + (er - sr + 1)))
done
count=0
start_ts=$(date +%s)

for c in "${CONFIGS[@]}"; do
    IFS=":" read -r u dur_s start_run end_run <<< "$c"
    DURATION="${dur_s}s"
    TPS_DURATION=$((dur_s + 10))
    for run in $(seq "$start_run" "$end_run"); do
        count=$((count + 1))
        echo "=== [$count/$total] algo=$algo U=$u dur=${dur_s}s run=$run $(date '+%H:%M:%S') ==="

        check_tmp_space
        wait_for_empty_pool

        tpslog="${LOGDIR}/tps_${algo}_u${u}_d${dur_s}_run${run}.log"
        locustlog="${LOGDIR}/sweep_${algo}_u${u}_d${dur_s}_run${run}.log"
        reslog="${LOGDIR}/res_${algo}_u${u}_d${dur_s}_run${run}.log"

        python3 tps_monitor.py --host "$HOST" --duration "$TPS_DURATION" --call-filter submit_pqc \
            > "$tpslog" 2>&1 &
        tps_pid=$!

        sample_resources "$reslog" "$TPS_DURATION" &
        res_pid=$!

        sleep "$TPS_HEAD_START"

        TEST_ALGO="$algo" BATCH_SIZE=1 locust -f locustfile_batch.py --headless \
            -u "$u" -r "$SPAWN_RATE" -t "$DURATION" --host="$HOST" --processes "$PROCESSES" \
            > "$locustlog" 2>&1

        wait "$tps_pid" 2>/dev/null
        wait "$res_pid" 2>/dev/null

        tmp_free_now=$(df --output=avail -m /tmp | tail -1 | tr -d ' ')

        cpu_mean=$(python3 -c "
import csv
vals = []
with open('$reslog') as f:
    for row in csv.DictReader(f):
        try: vals.append(float(row['cpu_pct']))
        except Exception: pass
print(f'{sum(vals)/len(vals):.1f}' if vals else 'n/a')
" 2>/dev/null)
        ram_mean=$(python3 -c "
import csv
vals = []
with open('$reslog') as f:
    for row in csv.DictReader(f):
        try: vals.append(float(row['ram_mb']))
        except Exception: pass
print(f'{sum(vals)/len(vals):.0f}' if vals else 'n/a')
" 2>/dev/null)

        echo "    locust: $(tail -n 4 "$locustlog" | grep Aggregated | tail -n1)"
        echo "    tps:    $(grep -E 'TPS \(nasze' "$tpslog")"
        echo "    zasoby: CPU_mean=${cpu_mean}% RAM_mean=${ram_mean}MB /tmp_wolne=${tmp_free_now}MB"
    done
done

elapsed=$(( $(date +%s) - start_ts ))
echo "Gotowe: $count przebiegow, czas calkowity: $((elapsed/60)) min"
