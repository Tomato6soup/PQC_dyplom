#!/bin/bash
set -uo pipefail

HOST="http://127.0.0.1:9944"
WS_HOST="ws://127.0.0.1:9944"
PROM_URL="http://localhost:9090/api/v1/query"
NODE_METRICS_URL="http://127.0.0.1:9615/metrics"
PROCESSES=6
SPAWN_RATE=20
WARMUP_EXTRA_S=12
LOCUST_MARGIN_S=5
read -ra ALGOS <<< "${M_ALGOS:-ecdsa dilithium2 sphincs}"
read -ra USERS <<< "${M_USERS:-1 10 100}"
read -ra RUNTIMES <<< "${M_RUNTIMES:-default raised}"
DURATION_S="${M_DURATION_S:-120}"
REPEATS="${M_REPEATS:-5}"
LOGDIR="${M_LOGDIR:-logs_final_v3}"
TAIL_S="${M_TAIL_S:-30}"
MAX_WAIT=120
POLL_INTERVAL=2
SETTLE_EXTRA=5
TPS_HEAD_START=3
RES_SAMPLE_INTERVAL=3
POOL_SAMPLE_INTERVAL=2
MIN_TMP_FREE_MB=8000

NODE_BIN_DEFAULT="${NODE_BIN_DEFAULT:-$HOME/node-default}"
NODE_BIN_RAISED="${NODE_BIN_RAISED:-$HOME/node-raised}"
RAISED_BLOCK_SIZE_LIMIT="${RAISED_BLOCK_SIZE_LIMIT-20971520}"
EXTRA_NODE_ARGS="${EXTRA_NODE_ARGS:---rpc-max-response-size 512 --pool-limit 100000 --pool-kbytes 2097152}"

PIDFILE="${LOGDIR}/.node.pid"
NODE_BASE="${NODE_BASE:-$HOME/node_base_v3}"
NODE_WAIT_MAX=30
CUR_TAG=""
POOL_OK=0
PENDING_BEFORE=""

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
    avail_mb=$(df --output=avail -m "$HOME" | tail -1 | tr -d ' ')
    if [[ "$avail_mb" -lt "$MIN_TMP_FREE_MB" ]]; then
        echo "!!!!! PRZERYWAM: dysk ma tylko ${avail_mb}MB wolnego (prog ${MIN_TMP_FREE_MB}MB) !!!!!"
        exit 1
    fi
}

bin_for() { if [[ "$1" == "raised" ]]; then echo "$NODE_BIN_RAISED"; else echo "$NODE_BIN_DEFAULT"; fi; }
expected_len_for() { if [[ "$1" == "raised" ]]; then echo 15728640; else echo 3932160; fi; }

read_block_len() {
    python3 -c "
from substrateinterface import SubstrateInterface as S
s = S(url='$WS_HOST')
v = s.get_constant('System','BlockLength')
v = getattr(v,'value',v)
print(v['max']['normal'])
" 2>/dev/null
}

restart_node() {
    local bin="$1" runtime="$2"
    local nodelog="${LOGDIR}/node_${CUR_TAG}.log"
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
    rm -rf /tmp/substrate* "$NODE_BASE" 2>/dev/null || true
    if [[ "$runtime" == "raised" ]]; then
        PQC_BLOCK_SIZE_LIMIT="$RAISED_BLOCK_SIZE_LIMIT" setsid nohup "$bin" --dev --base-path "$NODE_BASE" --rpc-external --rpc-port 9944 --rpc-cors=all --rpc-max-connections 1000 $EXTRA_NODE_ARGS \
            > "$nodelog" 2>&1 < /dev/null &
    else
        setsid nohup "$bin" --dev --base-path "$NODE_BASE" --rpc-external --rpc-port 9944 --rpc-cors=all --rpc-max-connections 1000 $EXTRA_NODE_ARGS \
            > "$nodelog" 2>&1 < /dev/null &
    fi
    echo $! > "$PIDFILE"
    disown
    for i in $(seq 1 "$NODE_WAIT_MAX"); do
        resp=$(curl -s -H "Content-Type: application/json" \
            -d '{"id":1,"jsonrpc":"2.0","method":"system_health","params":[]}' "$HOST" 2>/dev/null)
        if echo "$resp" | grep -q '"peers"'; then
            echo "    [node] restart OK ($runtime), gotowy po ${i}s"
            return 0
        fi
        sleep 1
    done
    echo "    [node] BLAD: node nie odpowiedzial po restarcie w ${NODE_WAIT_MAX}s"
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
    POOL_OK=0
    PENDING_BEFORE=""
    while true; do
        pending=$(curl -s -H "Content-Type: application/json" \
            -d '{"id":1,"jsonrpc":"2.0","method":"author_pendingExtrinsics","params":[]}' \
            "$HOST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('result', [])))" 2>/dev/null)
        if [[ -z "$PENDING_BEFORE" && -n "$pending" ]]; then
            PENDING_BEFORE="$pending"
        fi
        if [[ "$pending" == "0" ]]; then
            echo "    [pool] pusty po ${waited}s, czekam jeszcze ${SETTLE_EXTRA}s..."
            POOL_OK=1
            sleep "$SETTLE_EXTRA"
            return 0
        fi
        if [[ "$waited" -ge "$MAX_WAIT" ]]; then
            echo "    [pool] UWAGA: nie oprozniol sie po ${MAX_WAIT}s"
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

sample_pool() {
    local poollog="$1"
    local duration="$2"
    local end=$(( $(date +%s) + duration ))
    : > "$poollog"
    while [ "$(date +%s)" -lt "$end" ]; do
        ts=$(date +%s.%N)
        curl -s --max-time 2 "$NODE_METRICS_URL" | grep -E '^substrate_.*(txpool|transactions)' | sed "s/^/${ts} /" >> "$poollog"
        sleep "$POOL_SAMPLE_INTERVAL"
    done
}

SHA_DEFAULT=$(sha256sum "$NODE_BIN_DEFAULT" 2>/dev/null | cut -d' ' -f1)
SHA_RAISED=$(sha256sum "$NODE_BIN_RAISED" 2>/dev/null | cut -d' ' -f1)
echo "node default: $NODE_BIN_DEFAULT sha256=$SHA_DEFAULT"
echo "node raised:  $NODE_BIN_RAISED sha256=$SHA_RAISED"
echo "flagi wspolne: $EXTRA_NODE_ARGS"
echo "baza node'a:   $NODE_BASE"

total=$(( ${#ALGOS[@]} * ${#USERS[@]} * ${#RUNTIMES[@]} * REPEATS ))
count=0
start_ts=$(date +%s)

for rep in $(seq 1 "$REPEATS"); do
  for algo in "${ALGOS[@]}"; do
    for u in "${USERS[@]}"; do
      for runtime in "${RUNTIMES[@]}"; do
        count=$((count + 1))
        CUR_TAG="${runtime}_${algo}_u${u}_run${rep}"
        meta="${LOGDIR}/meta_${CUR_TAG}.json"
        if [[ -f "$meta" ]]; then
            echo "=== [$count/$total] $CUR_TAG - juz zrobione, pomijam ==="
            continue
        fi
        echo "=== [$count/$total] $CUR_TAG $(date '+%H:%M:%S') ==="

        bin=$(bin_for "$runtime")
        sha=$SHA_DEFAULT; [[ "$runtime" == "raised" ]] && sha=$SHA_RAISED
        WARMUP=$(python3 -c "print(round($u/$SPAWN_RATE + $WARMUP_EXTRA_S, 2))")
        LOCUST_T=$(python3 -c "import math; print(math.ceil($WARMUP + $DURATION_S) + $LOCUST_MARGIN_S)")
        MON_DUR=$(( TPS_HEAD_START + 15 + LOCUST_T + TAIL_S ))

        check_tmp_space
        restart_node "$bin" "$runtime" || exit 1
        sleep "$SETTLE_EXTRA"

        blen=$(read_block_len)
        exp=$(expected_len_for "$runtime")
        if [[ "$blen" != "$exp" ]]; then
            echo "!!!!! PRZERYWAM: BlockLength Normal=$blen, oczekiwano $exp dla $runtime !!!!!"
            exit 1
        fi
        echo "    [node] BlockLength Normal=$blen OK"

        fund_accounts || exit 1
        echo 0 > .account_counter
        wait_for_empty_pool || { echo "!!!!! PRZERYWAM: pool nie jest pusty przed startem ($CUR_TAG) !!!!!"; exit 1; }

        blocklog="${LOGDIR}/blocks_${CUR_TAG}.jsonl"
        monlog="${LOGDIR}/monitor_${CUR_TAG}.log"
        locustlog="${LOGDIR}/locust_${CUR_TAG}.log"
        reslog="${LOGDIR}/res_${CUR_TAG}.log"
        poollog="${LOGDIR}/pool_${CUR_TAG}.log"
        prefix="${LOGDIR}/submits_${CUR_TAG}"

        timeout $((MON_DUR + 60)) python3 tps_monitor_v3.py --host "$HOST" --duration "$MON_DUR" --out "$blocklog" > "$monlog" 2>&1 &
        mon_pid=$!
        sample_resources "$reslog" "$MON_DUR" &
        res_pid=$!
        sample_pool "$poollog" "$MON_DUR" &
        pool_pid=$!
        sleep "$TPS_HEAD_START"

        locust_start=$(date +%s.%N)
        TEST_ALGO="$algo" BATCH_SIZE=1 SUBMIT_LOG_PREFIX="$prefix" python3 -m locust -f locustfile_v3.py --headless \
            -u "$u" -r "$SPAWN_RATE" -t "${LOCUST_T}s" --host="$HOST" --processes "$PROCESSES" --stop-timeout 10 \
            > "$locustlog" 2>&1
        locust_end=$(date +%s.%N)

        wait "$mon_pid" 2>/dev/null
        wait "$res_pid" 2>/dev/null
        wait "$pool_pid" 2>/dev/null

        printf '{"tag":"%s","runtime":"%s","algo":"%s","users":%s,"run":%s,"duration_s":%s,"warmup_s":%s,"locust_total_s":%s,"spawn_rate":%s,"locust_start":%s,"locust_end":%s,"pool_ok":%s,"pending_before":%s,"block_len_normal":%s,"node_bin":"%s","node_sha256":"%s","extra_args":"%s","complete":true}\n' \
            "$CUR_TAG" "$runtime" "$algo" "$u" "$rep" "$DURATION_S" "$WARMUP" "$LOCUST_T" "$SPAWN_RATE" \
            "$locust_start" "$locust_end" "$POOL_OK" "${PENDING_BEFORE:-0}" "$blen" "$bin" "$sha" "$EXTRA_NODE_ARGS" > "$meta"

        echo "    locust: $(awk '/Response time percentiles/{exit} /Aggregated/{line=$0} END{print line}' "$locustlog")"
        echo "    bloki:  $(grep -c 'blok #' "$monlog"), pool max ready: $(grep ready_transactions "$poollog" | awk '{print $NF}' | sort -g | tail -1)"
      done
    done
  done
done

[[ -f "$PIDFILE" ]] && kill "$(cat "$PIDFILE")" 2>/dev/null || true
elapsed=$(( $(date +%s) - start_ts ))
echo ""
echo "Gotowe: $count pozycji w ${LOGDIR}/, czas calkowity: $((elapsed/60)) min"
