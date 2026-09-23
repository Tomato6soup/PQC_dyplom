#!/bin/bash
set -e

source /home/martyna/blockchain-env/bin/activate

NODE_DIR=~/polkadot-sdk-solochain-template
NODE_BIN="$NODE_DIR/target/release/solochain-template-node"
TEST_DIR=~/PQC_dyplom/load_testing
RESULTS_DIR="$TEST_DIR/results"

echo "=== 1. Startuje wezel ==="
pkill -f solochain-template-node 2>/dev/null || true
sleep 3
cd "$NODE_DIR"
nohup "$NODE_BIN" --dev --rpc-external --rpc-cors=all > "$RESULTS_DIR/diag_node.log" 2>&1 &
for i in $(seq 1 60); do
    if curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","id":1,"method":"chain_getHeader","params":[]}' \
        http://127.0.0.1:9944 | grep -q "200"; then
        echo "Wezel gotowy."
        break
    fi
    sleep 2
done

echo ""
echo "=== 2. Sprawdzam target Prometheusa ==="
curl -s "http://localhost:9090/api/v1/targets" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for t in data['data']['activeTargets']:
    print(t['labels'].get('job','?'), '->', t['health'], '| last scrape:', t.get('lastScrape','?'))
"

echo ""
echo "=== 3. Czekam 30s zeby zebrac baseline metryk CPU (przed obciazeniem) ==="
sleep 30
BASELINE_CPU=$(curl -s "http://localhost:9090/api/v1/query" --data-urlencode 'query=100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[30s])) * 100)' | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['result'][0]['value'][1] if d['data']['result'] else 'BRAK DANYCH')")
echo "CPU baseline (bezczynnosc): $BASELINE_CPU %"

echo ""
echo "=== 4. Odpalam KROTKI test obciazeniowy: dilithium2, u=50, t=20s ==="
cd "$TEST_DIR"
TEST_ALGO=dilithium2 locust -f locustfile.py --headless -u 50 -r 10 -t 20s --host http://127.0.0.1:9944 \
    --csv="$RESULTS_DIR/diag_test"

echo ""
echo "=== 5. Metryki CPU TUZ PO tescie (rozne okna czasowe) ==="
for window in 10s 20s 30s 60s; do
    val=$(curl -s "http://localhost:9090/api/v1/query" --data-urlencode "query=100 - (avg(rate(node_cpu_seconds_total{mode=\"idle\"}[$window])) * 100)" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['result'][0]['value'][1] if d['data']['result'] else 'BRAK DANYCH')")
    echo "  CPU (okno $window): $val %"
done

echo ""
echo "=== 6. Surowe dane z Locusta (P95/P99 wprost z pliku) ==="
cat "$RESULTS_DIR/diag_test_stats.csv"

echo ""
echo "=== 7. RAM tuz po tescie ==="
free -h

echo ""
echo "=== Zatrzymuje wezel ==="
pkill -f solochain-template-node 2>/dev/null || true

echo ""
echo "DIAGNOSTYKA ZAKONCZONA."
