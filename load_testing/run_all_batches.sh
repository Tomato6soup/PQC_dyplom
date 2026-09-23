#!/bin/bash
set -e

source /home/martyna/blockchain-env/bin/activate

NODE_DIR=~/polkadot-sdk-solochain-template
NODE_BIN="$NODE_DIR/target/release/solochain-template-node"
TEST_DIR=~/PQC_dyplom/load_testing
RESULTS_DIR="$TEST_DIR/results"
LOG_DIR="$RESULTS_DIR/node_logs"
mkdir -p "$LOG_DIR"

start_node() {
    echo "=== Startuje wezel dla: $1 ==="
    pkill -f solochain-template-node 2>/dev/null || true
    sleep 3
    cd "$NODE_DIR"
    nohup "$NODE_BIN" --dev --rpc-external --rpc-cors=all \
        > "$LOG_DIR/node_${1}_$(date +%H%M%S).log" 2>&1 &
    echo "Czekam az RPC odpowie..."
    for i in $(seq 1 60); do
        if curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","id":1,"method":"chain_getHeader","params":[]}' \
            http://127.0.0.1:9944 | grep -q "200"; then
            echo "Wezel gotowy."
            return 0
        fi
        sleep 2
    done
    echo "BLAD: wezel nie odpowiedzial w 120s"
    exit 1
}

stop_node() {
    echo "=== Zatrzymuje wezel ==="
    pkill -f solochain-template-node 2>/dev/null || true
    sleep 3
}

nohup bash -c 'while true; do date "+%Y-%m-%d %H:%M:%S"; free -h; echo; sleep 30; done' \
    > "$RESULTS_DIR/ram_monitor.log" 2>&1 &
MONITOR_PID=$!

for algo in ecdsa dilithium2 sphincs; do
    echo ""
    echo "##### PARTIA: $algo #####"
    start_node "$algo"
    cd "$TEST_DIR"
    python3 collect_batch.py "$algo"
    stop_node
    echo "Partia $algo zakonczona, przerwa 10s przed kolejna..."
    sleep 10
done

kill $MONITOR_PID 2>/dev/null || true

echo ""
echo "##### FINALIZACJA: statystyki + wykresy #####"
cd "$TEST_DIR"
python3 finalize_results.py

echo "WSZYSTKO ZAKONCZONE."
