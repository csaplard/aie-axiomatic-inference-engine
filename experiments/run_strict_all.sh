#!/usr/bin/env bash
# B (sűrű) + A1 (timeless) ÚJRAFUTÁS strict immunon — az immunrendszer
# ténylegesen aktív (ignore_forbidden_edges=false, ignore_negation_contradictions=false).
# A daemon példa-policy alapból lazítja az immunt, ezt felülírjuk.
set -e
cd "$(dirname "$0")/.."

run_arm() {
    local name=$1
    local reg=$2
    echo "=== [$(date +%H:%M:%S)] strict-immune start: $name (registry=$reg) ==="
    python -m experiments.run_experiment \
        --name "$name" \
        --registry "$reg" \
        --n-seeds 30 \
        --max-steps 10000 \
        --telemetry-every 100 \
        --workers 4 \
        --strict-immune
    echo "=== [$(date +%H:%M:%S)] done: $name ==="
}

# B kísérlet (kicsi, sűrű)
echo ""
echo "############################################################"
echo "# B KÍSÉRLET — sűrű regiszter, strict immune"
echo "############################################################"
run_arm dense_thesis_strict        experiments/registries/dense_thesis.json
run_arm dense_random_strict        experiments/registries/dense_random.json
run_arm dense_no_immune_strict     experiments/registries/dense_no_immune.json
run_arm dense_random_immune_strict experiments/registries/dense_random_immune.json

# A1 kísérlet (48-csúcsos timeless, az eredeti)
echo ""
echo "############################################################"
echo "# A1 KÍSÉRLET — 48-csúcsos timeless, strict immune"
echo "############################################################"
run_arm timeless_strict        axioms_registry_timeless.json
run_arm random_strict          experiments/registries/random_48.json
run_arm no_immune_strict       experiments/registries/timeless_no_immune.json
run_arm random_immune_strict   experiments/registries/timeless_random_immune.json

echo ""
echo "=== ALL STRICT-IMMUNE RUNS COMPLETE ==="
