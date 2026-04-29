#!/usr/bin/env bash
# 4-karú design: timeless (tézis) + 3 kontroll (struktúra/immun-faktorok elválasztva).
# 30 seed × 10000 lépés mind a 4 karon.
set -e
cd "$(dirname "$0")/.."

ARMS=(timeless random no_immune random_immune)
REGISTRIES=(
    axioms_registry_timeless.json
    experiments/registries/random_48.json
    experiments/registries/timeless_no_immune.json
    experiments/registries/timeless_random_immune.json
)

for i in "${!ARMS[@]}"; do
    name="${ARMS[$i]}"
    reg="${REGISTRIES[$i]}"
    echo "=== [$(date +%H:%M:%S)] start arm: $name (registry=$reg) ==="
    python -m experiments.run_experiment \
        --name "$name" \
        --registry "$reg" \
        --n-seeds 30 \
        --max-steps 10000 \
        --telemetry-every 100 \
        --workers 4
    echo "=== [$(date +%H:%M:%S)] done arm: $name ==="
done
echo "=== ALL ARMS COMPLETE ==="
