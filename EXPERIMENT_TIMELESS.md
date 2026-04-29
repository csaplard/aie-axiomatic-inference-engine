# Az „idő” anatómiája és az „Időtlen univerzum” kísérlet

Ez a szöveg **nem** a kód matematikai bizonyítása, hanem a motor **értelmezhető modellje**: hogyan jelenik meg az „idő” és az entrópia-jellegű mennyiség egy **gráf-alapú, policy-vezérelt** AIE-ben.

## 1. Nincs beépített óra

A `sleep_s` és az adaptív policy-alvás **csak a CPU / ütemezés** miatt van: nem fizikai időmodell, nem lépésszámláló „világidő”.

## 2. Hol van akkor az „idő”?

Ebben az architektúrában az idő **nem** egy skalár `t` változó a motor központi állapotában, hanem **topológiai / gráf-fogalmak** csomagolása:

| Fogalom | Megfeleltetés a kódban |
|--------|------------------------|
| **Kauzális irány** | Irányított élek: `knowledge_matrix[i,j] > 0` ⇒ `i → j` |
| **Lánc / „mélység”** | `shortest_path`, `verify_logic` (tranzitív `i→k` és `k→j`), ill. a BFS távolság a domainek között |
| **„Idő nyila” (metafora)** | Hosszú, **egyirányú** követhető láncok a gráfban — nem külön `time_arrow` csúcs kell hozzá, hanem a **DAG-szerű** lefutás a mátrixon |

Az entrópia-jellegű mennyiségek proxyi:

- **Q**: összefüggés-sűrűség (irányított élek aránya).
- **H₀**: bemeneti entrópia-proxi (`input_entropy_*`, `filter_input`).

Tiszta, magas entrópiájú bemenet → több csúcs / több hipotézis-próba → a gráf **kitapogatása** a `think_step` + discovery hipotézis ágon.

## 3. Immunrendszer és paradoxon

- **`forbidden_edges`**: explicit tiltott irány.
- **`logical_negation_pairs` + `_would_contradict_edge`**: egy él felvétele ellentmondást okozna (pl. A és ¬A elérhető ugyanabból a körből).

A motor **nem** „időt számol”, hanem **él-felvételeket** enged vagy tilt. Ha a gráf túl sok **kétirányú / szimmetrikus** próbát tesz, az immunrendszer **contradiction** / **forbidden** jelzéssel visszautasít — ezt a `reject=` mező a `format_last_think_ascii()` kimeneten követi.

## 4. Kísérlet: „Időtlen univerzum” (izoláció)

**Cél:** induljunk **minimális, explicit időnyíl / II. főtétel nélküli** axiómahalmazon, majd **információt injektáljunk** (pl. kvantum readout), és figyeljük a Q-t, a hipotézis-éleket és a `reject` okokat.

### 4.1 Kezdőállapot (szimmetria / reverzibilis bázis)

Fájl: **`axioms_registry_timeless.json`**

- A teljes `axioms_registry.json`-ból **kivágva** a következő csúcsok:  
  `entropy_2nd`, `boltzmann_entropy`, `time_arrow`
- A hozzájuk tartozó **causal_edges** / **forbidden_edges** szűrve (csak megmaradt id-k maradnak).
- A többi axióma (logika, Newton, Maxwell, QM, Born-út, readout kulcsszavak stb.) megmarad.

Így a gráf **nem** indul explicit termodinamikai „időnyíl” láncról.

### 4.2 Információ-injektálás

A **`quantum_ingestor.py`** a readout chunkokat dolgozza fel; összeköthető az **`AxiomaticInferenceEngine`** `derive_statement` / bemeneti útvonalával (részletek a modul docstringjében és a `README.md`-ben).

### 4.3 Daemon + hipotézis

Policy: **`discovery.enabled: true`** (lásd `agi_policy_daemon.example.yaml`).

- `verify_logic` nélkül is próbálhat **hipotézis élt**, ha az immunrendszer engedi (`hyp_edge`, `reject=`).

### 4.4 Mit nézzünk?

- **Q** emelkedik-e a hipotézis-élek miatt.
- **`reject=exists|contradiction|forbidden`** aránya — **contradiction** gyakorisága jelzi, hogy a gráf **szűk** maradt-e.
- **Makro–mikro távolság** (`telemetry.log`, `get_tension_report_ascii`) — a Hamilton-gyűrű daemon policy mellett ki van kapcsolva, így indulhat **inf** távolság, és csak valódi / hipotézis élek közelítenek.

## 5. Futtatás (példa)

```bash
python run_daemon_test.py --policy agi_policy_daemon.example.yaml --registry axioms_registry_timeless.json --status-every 5
```

Vagy Pythonból:

```python
from axiom_kernel import AxiomaticInferenceEngine

engine = AxiomaticInferenceEngine(
    policy_enabled=True,
    policy_path="agi_policy_daemon.example.yaml",
    registry_path="axioms_registry_timeless.json",
)
```

## 6. Mit **nem** garantál a kísérlet?

A kód **nem** bizonyítja**, hogy a fizikai idő „kicsapódik”** egy kritikus ponton: ez egy **heurisztikus gráf-szimuláció** policyvel és immunrendszerrel. A fenti narratíva **értelmezési keret** a megfigyelhető mennyiségekhez (Q, él-szám, reject okok, topológiai mélység).

---

## Időtlen regiszter újragenerálása

Ha a fő `axioms_registry.json` változik, futtasd a projekt gyökeréből:

```bash
python tools/build_timeless_registry.py
```

Opcionális: `--source` és `--output` (lásd `python tools/build_timeless_registry.py --help`).  
Szűrés: kiesnek a `entropy_2nd`, `boltzmann_entropy`, `time_arrow` csúcsok és az érintett élek.
