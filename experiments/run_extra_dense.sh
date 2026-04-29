#!/usr/bin/env bash
# Függelék B: extra-sűrű (15 csúcs, 15 forbidden, 15 negation) megerősítő futás.
set -e
cd "$(dirname "$0")/.."

ARMS=(extra_thesis extra_no_immune extra_random_immune)
REGISTRIES=(
    experiments/registries/extra_thesis.json
    experiments/registries/extra_no_immune.json
    experiments/registries/extra_random_immune.json
)

for i in "${!ARMS[@]}"; do
    name="${ARMS[$i]}"
    reg="${REGISTRIES[$i]}"
    echo "=== [$(date +%H:%M:%S)] start arm: $name ==="
    python -m experiments.run_experiment \
        --name "$name" \
        --registry "$reg" \
        --n-seeds 30 \
        --max-steps 10000 \
        --telemetry-every 100 \
        --workers 4 \
        --strict-immune
    echo "=== [$(date +%H:%M:%S)] done: $name ==="
done
echo "=== ALL EXTRA-DENSE ARMS COMPLETE ==="
