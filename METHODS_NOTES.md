# Módszertani jegyzet — confound-térkép és metrika-revízió

**Dátum:** 2026-04-30 (a C+D kísérletek után, az E pre-regisztráció előtt)

Ez a dokumentum a C és D kísérletek módszertani tanulságait rögzíti, és előkészíti az E pre-regisztrációt. **Nem hipotézis-teszt, hanem mérési-feltétel-feltérképezés.**

## 1. Confound-térkép — exploratórikus 2D scan

### Cél

A C és D kísérletek mind a paramétertér **két végpontján** confound-régiókat találtak (padding-domination és RRR-saturáció). A térkép célja: feltérképezni, **hol** mérhető tisztán a priority-mechanizmus.

### Setup

Script: [`experiments/confound_map.py`](experiments/confound_map.py)

- 16 cella (4 × 4): `n_nodes ∈ {15, 25, 40, 60}` × `N_immune ∈ {3, 6, 10, 15}`
- Minden cella: `dense_synthetic_registry` + uniform priority + Hamilton-ring kikapcsolva
- 5 seed × {200, 500, 3000} lépés × strict-immune
- Cella-cimkézés: `RRR_saturated`, `TOPO_saturated`, `RRR_silent`, `healthy`

### Eredmények

**Adjacency = uniform, 200 lépés (legrövidebb):**
```
 n \ N |   3       6      10      15
   15 | RRR_s   RRR_s   RRR_s   RRR_s
   25 | RRR_s   RRR_s   RRR_s   RRR_s
   40 | TOPO_s  RRR_s   RRR_s   RRR_s
   60 | TOPO_s  TOPO_s  TOPO_s  RRR_s
```

**Adjacency = uniform, 200 lépés, nagyobb n + kisebb N:**
```
 n \ N |   1       2       3       5
   40 | TOPO_s  TOPO_s  TOPO_s  TOPO_s
   60 | TOPO_s  TOPO_s  TOPO_s  TOPO_s
   80 | TOPO_s  TOPO_s  TOPO_s  TOPO_s
  100 | TOPO_s  TOPO_s  TOPO_s  TOPO_s
```

**Egyetlen "healthy" cella sem található** a tesztelt paramétertérben.

### Konklúzió: két alapvető saturáció

#### (A) Globális TOPO saturáció — a `dense_synthetic_registry` természetes következménye

A `dense_synthetic_registry` **kezdeti causal_edges-e már tartalmaz egy lineáris láncot** `0→1→2→...→(n-1)`. Ez a kezdeti gráf TOPO-ja **= n** mielőtt egyetlen `think_step` is futna. Ezért minden cellán `TOPO/n = 1.0`.

**Ez nem think_step által okozott saturáció**, hanem a regiszter design következménye. Az incremental TOPO-növekedés **már a 0. lépésnél telített**.

#### (B) RRR saturáció — sűrű immun-rendszer kis gráfon

`n_nodes = 15`, `N_immune = 3` esetén már `RRR ≈ 1.0` mind az 5 seedre. Ez **mechanikus**: ha 6 negation-csúcs van 15 csúcsban, és a gráf után néhány think_step már feltöltött, gyakorlatilag **minden** reverse-próba (i, j ∈ negation_set) találkozik kontradikciós úttal `i→...→neg(j)`.

A RRR saturáció a kis gráf + sűrű immun kombinációjában megszűnik (n=80, N=1: RRR=0.10), de ott a globális TOPO továbbra is saturált.

### Mit jelent ez az E kísérletre

- **A `dense_synthetic_registry` nem alkalmas TOPO-növekedés mérésére** (a kezdeti lánc már saturál). Egy alkalmasabb regiszter: izolált csúcsok (causal_edges = []), hagyva, hogy a `think_step` építse fel a gráfot. A növekedés iránya és tempója ekkor priority-függő lehet.
- **A globális TOPO mint metrika nem informatív** a jelenlegi setupon. A partícionált TOPO viszont igen — de újdonságot kell hozzáadni hozzá (lásd 2. pont).
- **Az RRR mérhető tartomány** szűk: nagy n (≥80) és kevés immun-pár (≤5). Ez fontos kritérium az E setupra.

## 2. Metrika-revízió — normalizált TOPO_partition

### Cél

A `topological_depth_partition` (kvantilis-alapú TOPO_high / TOPO_low) **érzékeny a méret-artefaktokra**: ha a gráf saturált, vagy a partíció-méret kicsi, az arány konstans-szerű mintázatot ad **független a priority-eloszlástól**.

### Megoldás — random-permutáció baseline

A `graph_metrics.topological_depth_partition_normalized` (új) **kontrollál** a gráf-struktúra-eredetű artefaktokra:

1. Kiszámolja a tényleges (TOPO_high, TOPO_low, ratio) értékeket a megadott priority-eloszlásra.
2. `n_permutations` (default 50) random permutációval újraszámolja ugyanezeket — a permutációk a "null priority" baseline-t adják.
3. Visszaadja:
   - `z_score_high` = (actual_topo_high − mean(perm_topo_high)) / std(perm)
   - `z_score_low` = ugyanaz a low partícióra
   - `normalized_ratio` = actual_ratio / median(perm_ratios)

### Mit ad ez

- A gráf-struktúra-eredetű "alap-arány" (pl. 1.5 ratio a chain-domináns gráfon) most a **baseline középértéke**, nem a tézis "PASS"-a.
- Csak a **tényleges priority-jel** ad nem-nulla z-score-t.
- A teszt akkor is működik, ha a globális TOPO saturált, mert a baseline ugyanott van saturálva.

### Tesztek

A `tests/test_priority.py` 2 új teszttel egészült ki:
- `test_uniform_priority_gives_z_near_zero`: uniform priority esetén minden permutáció ugyanazt adja → std=0 → z=0 (per def).
- `test_perfect_priority_alignment_gives_high_z`: ha a priority strukturálisan mély részt jelöl, z_high > 0.5.

50/50 unit teszt zöld.

## 3. Mit jelent ez az E pre-regisztrációnak

Az E kísérlet **érlelődik** a következő körültekintéssel:

1. **Új regiszter-típusú dizájn:** ne `dense_synthetic_registry` legyen az alap, hanem egy **growing-graph** kísérleti regiszter, ahol az initial causal_edges **kevés** (pl. csak néhány branch), és a TOPO **nem saturált a kiindulásban**.
2. **Új metrika:** a `topological_depth_partition_normalized` használata az E hipotézis tesztjére. A küszöb: `z_score_high > 1.5` (1.5 szórásnyira a baseline fölött).
3. **Healthy paraméter-régió:** `n_nodes ∈ [80, 120]`, `N_immune ∈ [3, 5]`, `n_steps ∈ [500, 1500]` — ahol a confound-térkép szerint az RRR még variábilis.
4. **Pre-registráció minimum:**
   - H1: a `coherent` priority kar `z_score_high` > 1.5 → priority koncentrál (új metrikával, új setupon)
   - H2: az `inverted` priority kar `z_score_high` ≈ 0 vagy negatív → direkció-szenzitív
   - Mindkét kar `n_steps`-en növekedési fázisban (`TOPO < 0.7 × n_nodes`)

Ez **nem 1-2 nap munka** — ez **legalább 1 hét** módszertani érlelés. A jelen módszertani jegyzet rögzíti, hogy honnan indulunk.

---

*A jegyzet nem hipotézis-teszt eredményét rögzíti. A confound-térkép adata: [`experiments/runs/_confound_map_*/confound_map_*.csv`](experiments/runs/). A normalizált metrika: [`graph_metrics.py`](graph_metrics.py) `topological_depth_partition_normalized`.*
