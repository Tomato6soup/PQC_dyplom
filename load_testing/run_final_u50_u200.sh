#!/bin/bash
set -uo pipefail

HOST="http://127.0.0.1:9944"
PROM_URL="http://localhost:9090/api/v1/query"
PROCESSES=6
SPAWN_RATE=20
ALGOS=("ecdsa" "dilithium2" "sphincs")
USERS=(50 200)
DURATIONS_S=(120)
REPEATS=5
LOGDIR="logs_final_u50_u200"
MAX_WAIT=120
POLL_INTERVAL=2
SETTLE_EXTRA=5
TPS_HEAD_START=3
RES_SAMPLE_INTERVAL=3
MIN_TMP_FREE_MB=1200

NODE_DIR="${NODE_DIR:-$HOME/polkadot-sdk-solochain-template}"
NODE_BIN="${NODE_BIN:-$NODE_DIR/target/release/solochain-template-node}"
PIDFILE="${LOGDIR}/.node.pid"
NODE_WAIT_MAX=30

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

restart_node() {
    if [[ -f "$PIDFILE" ]]; then
        oldpid=$(cat "$PIDFILE")
        kill "$oldpid" 2>/dev/null || true
        for i in $(seq 1 10); do
            kill -0 "$oldpid" 2>/dev/null || break
            sleep 1
        done
        kill -9 "$oldpid" 2>/dev/null || true
    fi
    sleep 2
    fuser -k 9944/tcp 2>/dev/null || true
    sleep 1
    rm -rf /tmp/substrate* 2>/dev/null || true
    cd "$NODE_DIR"
    setsid nohup "$NODE_BIN" --dev --tmp --rpc-external --rpc-port 9944 --rpc-cors=all --rpc-max-connections 1000 \
        > "${OLDPWD}/${LOGDIR}/node_$(date +%s).log" 2>&1 < /dev/null &
    echo $! > "${OLDPWD}/${PIDFILE}"
    disown
    cd "$OLDPWD"
    for i in $(seq 1 "$NODE_WAIT_MAX"); do
        resp=$(curl -s -H "Content-Type: application/json" \
            -d '{"id":1,"jsonrpc":"2.0","method":"system_health","params":[]}' "$HOST" 2>/dev/null)
        if echo "$resp" | grep -q '"peers"'; then
            echo "    [node] restart OK, gotowy po ${i}s"
            return 0
        fi
        sleep 1
    done
    echo "    [node] BLAD: nie odpowiedzial poprawnym system_health po restarcie w ${NODE_WAIT_MAX}s (ostatnia odp.: $resp)"
    return 1
}

fund_accounts() {
    python3 "$(dirname "$0")/fund_accounts.py" --host "$HOST" || {
        echo "    [fund] BLAD: dofinansowanie kont nie powiodlo sie"
        return 1
    }
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

total=$(( ${#ALGOS[@]} * ${#USERS[@]} * ${#DURATIONS_S[@]} * REPEATS ))
count=0
start_ts=$(date +%s)

for algo in "${ALGOS[@]}"; do
    for u in "${USERS[@]}"; do
        for dur_s in "${DURATIONS_S[@]}"; do
            DURATION="${dur_s}s"
            TPS_DURATION=$((dur_s + 10))
            WARMUP=$(python3 -c "print(round($u/$SPAWN_RATE, 1))")

            echo "### RESTART noda przed configiem algo=$algo U=$u dur=${dur_s}s ###"
            check_tmp_space
            restart_node || exit 1
            sleep "$SETTLE_EXTRA"
            fund_accounts || exit 1

            for run in $(seq 1 "$REPEATS"); do
                count=$((count + 1))
                echo "=== [$count/$total] algo=$algo U=$u dur=${dur_s}s run=$run $(date '+%H:%M:%S') ==="

                wait_for_empty_pool

                tpslog="${LOGDIR}/tps_${algo}_u${u}_d${dur_s}_run${run}.log"
                locustlog="${LOGDIR}/sweep_${algo}_u${u}_d${dur_s}_run${run}.log"
                reslog="${LOGDIR}/res_${algo}_u${u}_d${dur_s}_run${run}.log"

                python3 tps_monitor.py --host "$HOST" --duration "$TPS_DURATION" --call-filter submit_pqc \
                    --warmup-s "$WARMUP" > "$tpslog" 2>&1 &
                tps_pid=$!

                sample_resources "$reslog" "$TPS_DURATION" &
                res_pid=$!

                sleep "$TPS_HEAD_START"

                TEST_ALGO="$algo" BATCH_SIZE=1 python3 -m locust -f locustfile_batch.py --headless \
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

                echo "    locust: $(awk '/Response time percentiles/{exit} /Aggregated/{line=$0} END{print line}' "$locustlog")"
                echo "    tps:    $(grep -E 'TPS \(nasze' "$tpslog")"
                echo "    zasoby: CPU_mean=${cpu_mean}% RAM_mean=${ram_mean}MB /tmp_wolne=${tmp_free_now}MB"
            done
        done
    done
done

elapsed=$(( $(date +%s) - start_ts ))
echo ""
echo "Gotowe: $count przebiegow w ${LOGDIR}/, czas calkowity: $((elapsed/60)) min"
