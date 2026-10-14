#!/bin/bash
set -uo pipefail

HOST="http://127.0.0.1:9944"
PROM_URL="http://localhost:9090/api/v1/query"
PROCESSES=6
SPAWN_RATE=20
DURATION_S=60
DURATION="${DURATION_S}s"
TPS_DURATION=$((DURATION_S + 10))
LOGDIR="logs_batch_full"
MIN_TMP_FREE_MB=1200
u=10

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
            echo "    [pool] pusty po ${waited}s, czekam jeszcze 5s..."
            sleep 5
            return 0
        fi
        if [[ "$waited" -ge 120 ]]; then
            echo "    [pool] UWAGA: nie oprozniol sie po 120s - jedziemy dalej"
            return 1
        fi
        sleep 2
        waited=$((waited + 2))
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
        sleep 3
    done
}

# TYLKO brakujące: sphincs/bs=25/run=5, sphincs/bs=50/run=1..5
JOBS=(
  "sphincs 25 5"
  "sphincs 50 1"
  "sphincs 50 2"
  "sphincs 50 3"
  "sphincs 50 4"
  "sphincs 50 5"
)

total=${#JOBS[@]}
count=0
start_ts=$(date +%s)

for job in "${JOBS[@]}"; do
    read -r algo bs run <<< "$job"
    count=$((count + 1))
    echo "=== [$count/$total] algo=$algo U=$u BATCH_SIZE=$bs run=$run $(date '+%H:%M:%S') ==="

    check_tmp_space
    wait_for_empty_pool

    tpslog="${LOGDIR}/tps_${algo}_u${u}_bs${bs}_run${run}.log"
    locustlog="${LOGDIR}/sweep_${algo}_u${u}_bs${bs}_run${run}.log"
    reslog="${LOGDIR}/res_${algo}_u${u}_bs${bs}_run${run}.log"

    python3 tps_monitor.py --host "$HOST" --duration "$TPS_DURATION" --call-filter submit_pqc \
        > "$tpslog" 2>&1 &
    tps_pid=$!

    sample_resources "$reslog" "$TPS_DURATION" &
    res_pid=$!

    sleep 3

    TEST_ALGO="$algo" BATCH_SIZE="$bs" locust -f locustfile_batch.py --headless \
        -u "$u" -r "$SPAWN_RATE" -t "$DURATION" --host="$HOST" --processes "$PROCESSES" \
        > "$locustlog" 2>&1

    wait "$tps_pid" 2>/dev/null
    wait "$res_pid" 2>/dev/null

    tmp_free_now=$(df --output=avail -m /tmp | tail -1 | tr -d ' ')
    echo "    locust: $(tail -n 4 "$locustlog" | grep Aggregated | tail -n1)"
    echo "    tps:    $(grep -E 'TPS \(nasze' "$tpslog")"
    echo "    /tmp_wolne=${tmp_free_now}MB"
done

elapsed=$(( $(date +%s) - start_ts ))
echo "Gotowe: $count przebiegow (dopelnienie) w ${LOGDIR}/, czas calkowity: $((elapsed/60)) min"
