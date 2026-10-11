#!/bin/bash
set -uo pipefail

HOST="http://127.0.0.1:9944"
PROCESSES=6
SPAWN_RATE=20
DURATION_S=60
DURATION="${DURATION_S}s"
TPS_DURATION=$((DURATION_S + 10))
ALGOS=("ecdsa" "dilithium2" "sphincs")
USERS=(10 50 100 200 300 400 500 600)
REPEATS=5
LOGDIR="logs"
MAX_WAIT=120
POLL_INTERVAL=2
SETTLE_EXTRA=5
TPS_HEAD_START=3

mkdir -p "$LOGDIR"

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
            echo "    [pool] UWAGA: nie opróżnił się po ${MAX_WAIT}s - jedziemy dalej"
            return 1
        fi
        sleep "$POLL_INTERVAL"
        waited=$((waited + POLL_INTERVAL))
    done
}

total=$(( ${#ALGOS[@]} * ${#USERS[@]} * REPEATS ))
count=0
start_ts=$(date +%s)

for algo in "${ALGOS[@]}"; do
    for u in "${USERS[@]}"; do
        for run in $(seq 1 "$REPEATS"); do
            count=$((count + 1))
            echo "=== [$count/$total] algo=$algo U=$u run=$run $(date '+%H:%M:%S') ==="

            wait_for_empty_pool

            tpslog="${LOGDIR}/tps_${algo}_u${u}_run${run}.log"
            locustlog="${LOGDIR}/sweep_${algo}_u${u}_run${run}.log"

            python3 tps_monitor.py --host "$HOST" --duration "$TPS_DURATION" --call-filter submit_pqc \
                > "$tpslog" 2>&1 &
            tps_pid=$!

            sleep "$TPS_HEAD_START"

            TEST_ALGO="$algo" BATCH_SIZE=1 locust -f locustfile_batch.py --headless \
                -u "$u" -r "$SPAWN_RATE" -t "$DURATION" --host="$HOST" --processes "$PROCESSES" \
                > "$locustlog" 2>&1

            wait "$tps_pid" 2>/dev/null

            echo "    locust: $(tail -n 4 "$locustlog" | grep Aggregated | tail -n1)"
            echo "    tps:    $(grep -E 'TPS \(nasze' "$tpslog")"
        done
    done
done

elapsed=$(( $(date +%s) - start_ts ))
echo ""
echo "Gotowe: $count przebiegów w ${LOGDIR}/, czas całkowity: $((elapsed/60)) min"
