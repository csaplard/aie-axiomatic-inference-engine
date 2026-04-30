# D kísérlet — priority × adjacency 2D dizájn (confound-free)

**Dátum:** 2026-04-30 (pre-regisztráció — futás ELŐTT rögzítve)

## Háttér

A C kísérletben (priority_weight mechanizmus) a pre-regisztrált elsődleges hipotézis (H1: priority koncentrálja a TOPO-mélyülést) **cáfolódott**. A post-hoc analízis viszont egy erős mintázatra mutatott: **a priority-eloszlás drámaian befolyásolja az immunrendszer aktivitását** (RRR a `priority_thesis` 0.31-tól a `priority_inverted` 0.98-ig, p=6·10⁻⁹).

A C kísérlet diagnosztikája (lásd [EXPERIMENT_PRIORITY.md](EXPERIMENT_PRIORITY.md) függelék) **két komoly problémát** azonosított:

1. **Confound: `n_nodes` default = 64 vs. registry = 15.** A 49 padding csúcs alapértelmezett priority=0.5-tel **dominálta** a kvantilis-alapú TOPO partícionálást — a H1 verdict tehát nem azt mondja, hogy a priority nem koncentrál, hanem hogy ezen a setupon **nem mérhető**, koncentrál-e.

2. **Versengő magyarázat a post-hoc RRR-mintázatra:**
   - **Domain-coherence**: a priority a domain-szerkezethez illeszkedik vagy ellene megy
   - **Chain-adjacency**: a magas-priority csúcsok a kauzális gerincben **konszekutívak** (1, 2, 5, 6, 9, 10, 13, 14 a `priority_inverted`-ben), és a forbidden_edges/negation_pairs **közeli index-távolságokra** koncentráltak — együtt extrém immun-aktivitást okoznak.

A diagnosztika a chain-adjacency-t **részben** támogatja (`priority_inverted` immun-rejekt medián \|i-j\| = 3), de nem zárja ki a koherenciát. A két magyarázat statisztikailag **összefonódik** a C kísérletben, mert a forbidden/negation placement mindig "near" volt.

## Cél

A D kísérlet **két forrást szétválaszt**:
1. **Confound eltávolítása**: `n_nodes = registry_size` (15) — nincs padding, a partícionálás tisztán a 15 csúcs priority-eloszlását nézi.
2. **Chain-adjacency vs koherencia diszambiguálása**: kétfaktoros (2D) dizájn, ahol a priority pattern és a forbidden/negation placement **független változók**.

## Kísérleti dizájn — 5 kar (2×2 + uniform baseline)

| Kar | Priority pattern | Forbidden/negation placement | Cél |
|---|---|---|---|
| `D_coherent_near` | strukturált (LOGIC/NEWTON=high, QM/INFO=low) | near (distance 2-4) | A C kísérlet thesis-ének tisztított változata |
| `D_coherent_far` | ugyanaz | far (distance 7-14) | Ha priority hat: ratio ugyanannyi mint near; ha chain-adjacency hat: RRR sokkal alacsonyabb |
| `D_random_near` | random ∈ [0.1, 0.9] | near | A C kísérlet random-jának tisztított változata |
| `D_random_far` | random | far | Ha chain-adjacency hat: RRR alacsony |
| `D_uniform` | mind 0.5 | near | Priority-mentes baseline (egyetlen baseline elég, mert priority null) |

**Statikus paraméterek minden karon:**
- `n_nodes = 15` (= registry size, **NINCS PADDING**)
- 30 seed × 10000 lépés × strict-immune
- 10 forbidden + 10 negation (mint a C `dense_thesis`)
- Ugyanaz a kauzális gerinc (`0→1→2→...→14` + ágak `0→2, 3→5, 6→8, 9→11, 12→14`)

A `--n-nodes-override 15` mező a regiszterben kényszeríti az engine-t pontosan 15-csúcsos mátrixra (új feature, [axiom_kernel.py](axiom_kernel.py) tiszteletben tartja a regiszter `n_nodes_override` kulcsát).

## Pre-regisztrált hipotézisek

### Faktor A — Priority pattern hatása (4-arm marginális, az `D_uniform` referenciaként)

#### A-H1 — TOPO koncentráció a priority partícióban

A `D_coherent_*` karon a magas-priority csúcsok körüli TOPO mélyebb-e:
- **Predikció:** `D_coherent_near` ratio = TOPO_high / TOPO_low > **1.3** (medián 30 seedre)
- **Statisztika:** Mann-Whitney U `topo_high` vs `topo_low` (paired-szerű, ugyanaz a 30 seed), egyoldali, **p < 0.0125** (Bonferroni 4 teszt)
- **Cáfolat:** ratio ≤ 1.0 vagy p > 0.05 → priority NEM koncentrál (még confound nélkül sem)
- **Megjegyzés:** A C-ben 1.5-ös küszöböt írtunk; itt **1.3-ra puhítjuk**, mert a 15-csúcsos kis méreten az effektus nehezebben válhat dominánssá

#### A-H2 — Globális TOPO változás

`D_coherent_near` össz-TOPO vs `D_uniform` össz-TOPO:
- **Predikció:** szignifikáns eltérés (priority hat a globális TOPO-ra is, ahogy a C-ben láttuk; itt confound nélkül)
- **Tájékoztató, nem döntő** — ha p < 0.05, priority valamit csinál; ha p > 0.05, semmit
- Két-oldali Mann-Whitney

### Faktor B — Adjacency placement hatása az immun-aktivitásra

#### B-H1 — Chain-adjacency teszt (CSAK a near-far összehasonlítás)

A `D_random_near` vs `D_random_far` karok: ugyanaz a (random) priority, csak az adjacency placement különbözik. **Ez a legtisztább chain-adjacency teszt.**

- **Predikció:** `D_random_near` RRR > `D_random_far` RRR, **p < 0.0125** (Bonferroni 4 teszt)
- **Cáfolat:** p > 0.05 vagy fordított irány → chain-adjacency NEM magyarázza a C post-hoc RRR-jét

#### B-H2 — Coherent + adjacency interakció

A `D_coherent_near` vs `D_coherent_far`: ha priority strukturáltsága dominál, RRR nem változik adjacency-vel; ha chain-adjacency, csökken.

- **Predikció:** `D_coherent_near` RRR > `D_coherent_far` RRR, **p < 0.0125**
- **Cáfolat:** p > 0.05 → adjacency-nek nincs marginal hatása ezen a priority-pattern-en (priority dominál)

### Faktor C — Priority pattern hatása az immun-aktivitásra (csak adjacency=near rögzítve)

#### C-H1 — Coherence teszt

A `D_coherent_near` vs `D_random_near`: ugyanaz az adjacency placement (near), csak a priority pattern különbözik.

- **Predikció:** `D_random_near` RRR > `D_coherent_near` RRR, **p < 0.0125**
- **Cáfolat:** p > 0.05 → priority strukturáltsága NEM hat az RRR-re (csak az adjacency)

## Falszifikációs döntésfa (a 4 marginális teszt eredményei alapján)

| B-H1 (random near>far) | C-H1 (random near > coherent near) | Verdict |
|:---:|:---:|---|
| ✅ PASS | ✅ PASS | **Mindkét mechanizmus aktív**: chain-adjacency ÉS priority-coherence külön-külön mérhető |
| ✅ PASS | ❌ FAIL | **Csak chain-adjacency** — priority-strukturáltság nem számít |
| ❌ FAIL | ✅ PASS | **Csak priority-coherence** — adjacency placement nem számít |
| ❌ FAIL | ❌ FAIL | **A C post-hoc RRR-mintázat artefaktum** — sem coherence, sem chain-adjacency nem reprodukálódik confound nélkül |

A B-H2 teszt (coherent near vs far) **interakciós jel**: ha B-H1 PASS de B-H2 FAIL, az azt jelzi, hogy a coherent priority *elnyeli* az adjacency-hatást.

## Pre-regisztrált operacionalizációk

### Coherence definíció

A `D_coherent_*` karon a priority a **domain index modulo 4**-tel összekapcsolva (ugyanaz mint a C kísérlet `priority_thesis`):
- index%4 == 0 (LOGIC): priority = 0.85
- index%4 == 1 (QM): priority = 0.30
- index%4 == 2 (INFO): priority = 0.20
- index%4 == 3 (NEWTON): priority = 0.75

### Random priority definíció

`random.Random(seed=42)`-vel csúcsonként uniform [0.1, 0.9]. Ugyanaz a generátor mint a C `priority_random`-on.

### Adjacency-mode operacionalizáció

A `dense_synthetic_registry` kapott egy `adjacency_mode` paramétert:
- **`near`**: forbidden + negation `(j-i)` távolság ∈ [2, 4]
- **`far`**: forbidden + negation `(j-i)` távolság ∈ [7, 14]
- **`uniform`**: minden 2-14 közti távolság egyformán esélyes (kontroll, nem használjuk D-ben)

A két mód **diszjunkt** távolság-tartományt használ → tisztán szétválasztható.

## Mit nem fogunk csinálni

- Nem fogunk új küszöböt fittelni a kapott adatokra.
- Nem fogunk hozzáadni egy 6. kart, ami épp a kapott eredményt magyarázza.
- A pre-regisztrált küszöbök (1.3 ratio, 0.0125 Bonferroni-α) változatlanok maradnak.

## Idő-becslés

- Engine + generator + tests: már megvan
- 5 regiszter generálás + 5 kar futás × 30 seed × 10000 lépés × n=15: **~5-7 perc compute**
- Elemzés: ~10 perc
- **Összesen ~30-40 perc** (a pre-regisztrációs munka külön számolva)

---

*Pre-regisztráció lezárva.*

---

# UTÓRÉSZ — eredmények és verdict

**Dátum:** 2026-04-30 (futás után)

## Nyers számok (medián, 30 seed × 10000 lépés × strict-immune × n_nodes=15)

| Kar | TOPO | TOPO_high | TOPO_low | ratio | Q | RRR |
|---|---:|---:|---:|---:|---:|---:|
| D_coherent_near | 15.0 | 3.0 | 2.0 | 1.500 | 0.1000 | 0.9999 |
| D_coherent_far | 15.0 | 3.0 | 2.0 | 1.500 | 0.0952 | 1.0000 |
| D_random_near | 15.0 | 3.0 | 2.0 | 1.500 | 0.1000 | 0.9997 |
| D_random_far | 15.0 | 3.0 | 2.0 | 1.500 | 0.0952 | 1.0000 |
| D_uniform | 15.0 | 15.0\* | 15.0\* | 1.000\* | 0.1000 | 0.9999 |

\* `D_uniform`-on minden priority = 0.5, kvantilis-küszöbök egybeesnek; partíció = teljes gráf.

## Pre-regisztrált verdictek

| Hipotézis | Predikció | Eredmény | Verdict |
|---|---|---|---|
| **A-H1** (TOPO koncentráció) | ratio > 1.3 medián, p < 0.0125 | ratio = 1.500, p = 5.4·10⁻¹¹ | ✅ Technikailag PASS |
| **B-H1** (chain-adjacency tisztán) | random_near RRR > random_far RRR | 0.9997 vs 1.0000 | ❌ FAIL |
| **B-H2** (priority + adjacency interakció) | coherent_near RRR > coherent_far RRR | 0.9999 vs 1.0000 | ❌ FAIL |
| **C-H1** (priority-coherence tisztán) | random_near RRR > coherent_near RRR | 0.9997 vs 0.9999 | ❌ FAIL |

A pre-regisztrált döntésfa szerint: **B-H1 FAIL ÉS C-H1 FAIL → "C post-hoc RRR-mintázat artefaktum"**.

## Honestseti értelmezés — új confound, nem cáfolat

A pre-regisztrált verdict mechanikusan azt mondaná, hogy a C post-hoc RRR-mintázat artefaktum volt. **De ez az értelmezés nem tisztességes**, mert a D kísérlet egy MÁS típusú confoundba ütközött:

### **RRR saturáció a 15-csúcsos gráfon**

Mind az 5 karon RRR ≈ 1.0 — a 10 forbidden + 10 negation pair × 15 csúcs olyan sűrű immunrendszert ad, hogy **minden** reverse-próba contradiction-ben végződik. **Nincs varianciánk** a karok közti összehasonlításhoz az RRR mentén.

A `D_uniform` is RRR=0.9999-et kapott. Ez nem koherencia/adjacency hatás — ez **a setup mérési plafonja**.

### Az A-H1 "PASS" sem priority-specifikus

A coherent_near, coherent_far, random_near, random_far **mindegyik** ratio-medianja 1.500. Ez a **kvantilis-partícionálás 5+5 csúcsos szubgráfjainak természetes ratio-ja a 15-csúcsos teljes lánchoz képest** — nem a priority struktúra hatása. Az A-H1 statisztikai szignifikanciája (p = 5·10⁻¹¹) onnan jön, hogy a 30 seed mindegyikén ugyanaz a determinisztikus partíció-érték (3 vs 2). **Stiszikailag erős, információ-tartalmilag nulla.**

## Két confound, egy nyitott kérdés

| Kísérlet | Setup | Confound | Mit veszít |
|---|---|---|---|
| **C** | n_nodes=64, registry=15 | Padding-domination | A partícionálást a 49 padding csúcs uralja |
| **D** | n_nodes=15, registry=15 | Immun-saturáció | RRR ≈ 1.0 minden karon, nincs variancia |

A priority mechanizmus **tényleges hatása nem mérhető** egyik végponton sem. Egy közbülső régió kellene:

- **n_nodes ≈ 30–40**, hogy a partíció legalább 10-15 csúcsot tartalmazzon mindkét oldalon (TOPO mérésre legyen elég strukturális hely)
- **Csökkentett immunrendszer-sűrűség** (pl. 3-5 forbidden + 3-5 negation), hogy az RRR ne saturáljon

## Mit nem csinálunk most

- **Nem fittelünk új küszöböt** a kapott adatokra a "PASS" megmentésére. Az A-H1 statisztikai PASS, de információs FAIL — ezt nem álcázzuk sikernek.
- **Nem mondjuk azt, hogy "a C post-hoc RRR-mintázat artefaktum volt"**, mert a D kísérlet az értékelést **nem tudta lefolytatni** — nem cáfolta, csak nem érintette.
- **Nem indítunk azonnal új kísérletet** a közbülső paraméter-tartományon. Az E kísérlet **érlelést igényel** — még legalább egy környi át nem gondolt tervezés, ahol a confound-tér rendszeresen leírható.

## A négy mechanizmus jelenlegi képe — D után

| # | Mechanizmus | Bizonyíték | Státusz |
|---|---|---|---|
| 1 | TOPO ← strukturáltság | A1: p=10⁻¹¹ | Megerősítve |
| 2 | Q ← immunrendszer | A1+B+B': p<10⁻³ mindenhol | Megerősítve |
| 3 | TOPO ⊥ immunrendszer | A1+B+B': p>0.3 | Megerősítve (negatív) |
| 4 | Immun-aktivitás ← priority | C post-hoc: p=10⁻⁸; **D nem tudta értékelni** | Nyitott (nem cáfolt, nem megerősített) |

A D kísérlet **nem dönti el** a 4. mechanizmus sorsát. A confound-tér feltérképezése azonban értékes melléktermék: tudjuk, hogy a méretarány **mátrixhatás** — mind a két szélen artefaktumok torzítanak. Az E kísérlet (ha lesz) középső paraméter-tartományba kell hogy célozzon.
