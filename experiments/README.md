# Kísérleti keret — kontrollok + falszifikáció

Cél: az AIE-tézist (THEORY.md) **cáfolható** állítássá tenni — több seedes
futások + random/szimmetrikus kontrollok + explicit küszöbkritérium.

## Munkafolyamat

### 1. Kontroll-regiszterek generálása

```bash
# Véletlen irányított gráf, 40 csúcs, ~4% éldensitás:
python -m experiments.registry_generators random \
    --n-nodes 40 --edge-density 0.04 --seed 42 \
    --out experiments/registries/random_40.json

# Szimmetrikus immunrendszer az időtlen regiszterből:
python -m experiments.registry_generators symmetric \
    --source axioms_registry_timeless.json \
    --out experiments/registries/timeless_sym.json
```

### 2. Batch-futás (3 kar)

A `--n-seeds 30` 30 független seedet ad. Ne állítsd túl magasra a `--workers`
értéket — minden worker egy NumPy-engine-t indít.

```bash
# Timeless (a tézis kara):
python -m experiments.run_experiment \
    --name timeless --registry axioms_registry_timeless.json \
    --n-seeds 30 --max-steps 10000 --workers 4

# Random kontroll:
python -m experiments.run_experiment \
    --name random --registry experiments/registries/random_40.json \
    --n-seeds 30 --max-steps 10000 --workers 4

# Szimmetrikus immunrendszer kontroll:
python -m experiments.run_experiment \
    --name symmetric --registry experiments/registries/timeless_sym.json \
    --n-seeds 30 --max-steps 10000 --workers 4
```

Minden futás kimenete: `experiments/runs/<name>/seed_NNNN.telemetry.log`
(eredeti telemetria-formátum, PID + TICK + Q/TOPO/ASYM/RRR), plusz egy
`manifest.json`.

### 3. Aggregálás (mean ± 95% CI)

```bash
python -m experiments.aggregate --manifest experiments/runs/timeless/manifest.json
python -m experiments.aggregate --manifest experiments/runs/random/manifest.json
python -m experiments.aggregate --manifest experiments/runs/symmetric/manifest.json
```

Kimenet: `aggregate.csv` és `aggregate.json` minden manifest mellett. Ezekből
közvetlenül plotolható Q(t), ASYM(t), TOPO(t) görbe seed-átlaggal és CI-vel.

### 4. Falszifikációs döntés

```bash
python -m experiments.falsification \
    --timeless-manifest experiments/runs/timeless/manifest.json \
    --random-manifest experiments/runs/random/manifest.json \
    --symmetric-manifest experiments/runs/symmetric/manifest.json
```

**Alapértelmezett kritériumok** (`falsification.DEFAULT_CRITERIA`):

| Kar | Tick | Feltétel |
|-----|------|----------|
| timeless | ≥10000 | ASYM medián ≥ 0.7 ÉS TOPO medián ≥ 5 |
| random | ≥10000 | ASYM medián ≤ 0.5 |
| symmetric | ≥10000 | ASYM medián ≤ 0.5 |

Felülírható `--criteria my_thresholds.yaml` paraméterrel:

```yaml
timeless:
  at_tick: 20000
  asym_min: 0.75
  topo_min: 8
random:
  at_tick: 20000
  asym_max: 0.4
```

**Kimenetek:**
- `PASS / FAIL` minden karra.
- Végeredmény: `tézis NEM cáfolt`, `ARTEFAKTUM (CÁFOLT)`, vagy
  `NEM bizonyított`.

## Mit ad ez hozzá a projekthez

1. **Reprodukálhatóság**: `random_seed` policy-ben + telemetriában — bármelyik
   futás újrajátszható.
2. **Statisztika**: 30 seed → 95% CI a Q/ASYM/TOPO görbéken — nem egy
   szerencsés futás.
3. **Kontrollok**: random gráf + szimmetrikus immunrendszer baseline — a
   tézis tudományossá válik (Popper-feltétel).
4. **Explicit falszifikáció**: numerikus küszöb pass/fail, nem narratíva.

## Mit *nem* ad ez hozzá

- Nem bizonyítja, hogy a fizikai időnyíl így keletkezik (a tézis eleve
  metafora — lásd [../THEORY.md](../THEORY.md)).
- A `random_registry` egy **egyszerű** kontroll (uniform él-valószínűség).
  Ha a timeless kar nyer, érdemes lehet **finomabb** kontrollokat is futtatni
  (pl. azonos él-szám, de véletlen permutált irányítás).

## Költségbecslés

Egy seed × 10000 lépés ≈ 1-3 perc (n_nodes ~ 40, dense NumPy). 30 seed × 3 kar
≈ 1.5–5 óra 4 worker mellett. Több kart párhuzamosan futtathatsz külön shellben.
