# Modul D — meta-monitor (PFC-analóg) pre-regisztráció

**Dátum:** 2026-04-30 (pre-regisztráció — futás ELŐTT rögzítve)

## Háttér

A `PLAN_BRAIN_ARCHITECTURE.md` szerinti Modul D feladata: **stuck-detection + mód-váltó intervenció**. Az AIE érzékelje, ha a daemon ugyanazt a pár-régiót pörgeti, és intervenció (hipnagóg epizód) szakítsa meg a kört.

A C+D priority-kísérletek tanulsága szerint a stuck-detection **paraméter-érzékeny**: ha túl szigorú a küszöb, mindig tüzel; ha túl laza, soha. Ezért a formális pre-reg ELŐTT **calibration-scan** szakaszt futtattunk.

## Calibration scan eredménye (NEM pre-reg, exploratórikus)

Script: [`experiments/meta_calibration.py`](experiments/meta_calibration.py)

24 cella (W ∈ {50, 100, 200, 500} × M ∈ {3, 5, 10} × granularity ∈ {pair, domain}) × 3 seed × 2000 lépés × `n_nodes=80` × strict immune × baseline daemon.

**Egyetlen healthy zóna** (fire_rate medián ∈ [0.05, 0.30]):

| Paraméter | Érték |
|---|---|
| `window_size` (W) | **500** |
| `repetition_threshold` (M) | **3** |
| `granularity` | **pair** |
| baseline fire_rate medián | **0.144** |

A többi cella vagy silent (pair-szinten kis M-mel) vagy saturated (domain-szinten gyorsan telítődik a 4×4-es domain-tér).

**Ezt a paraméter-konfigurációt rögzítjük az alábbi pre-reg-hez.** A formál tesztek 30 seedjén az átlagos firing rate ezen a paraméteren prediktívan **0.07–0.21** közé esik (calibration ±50%).

## Architekturális döntések

### Mit detektál

A `StuckDetector` az utóbbi W=500 think_step pár-attempt-jét figyeli. Ha **bármely (i, j) pár M=3 vagy többször** előfordul ebben az ablakban, a detektor tüzel.

### Mit csinál az intervenció

`hypnagogic` mód: ha a detektor tüzel, a `start_hypnagogic_episode()` metódust hívja az engine-en. Ez 8+35+8=51 lépéses hipnagóg epizódot indít (entry → deep → exit), majd 200 lépés cooldown.

A meta-monitor saját cooldown-ja: 100 lépés (a hipnagóg epizód időzítését nem zavarjuk).

### Karok (3 kar)

| Kar | Konfiguráció |
|---|---|
| `meta_baseline` | daemon, NINCS detector, NINCS intervenció |
| `meta_log_only` | daemon + detector (log_only mód), NINCS intervenció — sanity check a detection-re |
| `meta_intervention` | daemon + detector + hipnagóg intervenció (cooldown=100) |

**Statikus paraméterek:** 30 seed × 3000 lépés × `n_nodes=80` × strict immune × `forbidden=5`, `negation=5`. A `meta_intervention` kar policy-ja `hypnagogic.enabled=True` (ezért a `start_hypnagogic_episode()` ténylegesen működik).

## Pre-regisztrált hipotézisek

### Validity preconditions (V1-V3, futás előtt rögzítve)

A `meta_baseline` kar 30 seed-medián értékeire:
- **V1**: n_edges_added ∈ [50, 5000] (egészséges növekedési zóna, nem stuck-by-design)
- **V2**: a `meta_log_only` kar mediánján a fire_rate ∈ [0.05, 0.30] (a calibration zóna reprodukálva 30 seedre)
- **V3**: a `meta_intervention` kar mediánján legalább 3 intervenció történt 3000 lépés alatt (ha 0, a teszt érdemtelen)

Ha bármelyik sérül, verdict: `INVALID_DUE_TO_PRECONDITION`, **újrafutás** más paraméterekkel.

### M-H1 (sanity) — detektor reprodukálja a calibrationt

A `meta_log_only` kar fire_rate mediánja a calibration ±50% közelében:
- **Pre-reg**: median(`meta_log_only` fire_rate) ∈ [0.07, 0.21]
- **Cáfolat**: kívül esik → a calibration nem reprodukálható nagyobb seed-számra → a detektor paraméter-érzékeny módon viselkedik

### M-H2 (elsődleges engineering) — intervenció CSÖKKENTI az ismétlés-sűrűséget

A `meta_intervention` kar **legmagasabb pár-előfordulása** alacsonyabb, mint a `meta_baseline` kar legmagasabb pár-előfordulása.

Konkrét metrika: minden kar minden seed-jére, a futás végén összeszámoljuk a (i, j) pár-attempt-eket az utolsó W=500 lépésen, és a maximális számot vesszük. Ezt nevezzük `max_repetition_density`-nek.

- **Pre-reg**: Mann-Whitney U, egyoldali, `meta_baseline > meta_intervention`, **p < 0.01**
- **Effektus-méret**: `median(meta_baseline) - median(meta_intervention) ≥ 1` (legalább 1-szeri csökkenés a max repetícióban)
- **Cáfolat**: p > 0.05 vagy effektus < 1 → a hipnagóg intervenció **nem szakítja meg** a stuck-loopot

### M-H3 (másodlagos) — intervenció új területre vezet

A `meta_intervention` kar `far_domain_edge_ratio`-ja eltér a `meta_baseline`-tól (akár fel, akár le, kétoldali teszt):

- **Pre-reg**: Mann-Whitney U, kétoldali, **p < 0.05**
- **Cáfolat**: nincs eltérés → az intervenció ugyanabba a domain-térbe vezet vissza, csak más úton

### M-H4 (sanity) — intervenció NEM rontja az engine-t

A `meta_intervention` final Q ne csökkenjen drámaian:

- **Pre-reg**: median(`meta_intervention` final Q) ≥ 0.5 × median(`meta_baseline` final Q)
- **Cáfolat**: meredek Q-csökkenés → a hipnagóg intervenciók túl gyakran szakítják meg a növekedést, az engine effektíven megáll

## Falszifikációs döntésfa

| V1-V3 | M-H1 | M-H2 | M-H3 | M-H4 | Verdict |
|---|---|---|---|---|---|
| PASS | PASS | PASS | bármi | PASS | **MODUL D MEGERŐSÍTVE** — stuck-detection működik, intervenció hatásos, engine intakt |
| PASS | PASS | FAIL | bármi | bármi | **Stuck-detection mechanikus, de az intervenció hatástalan** — más intervención (pl. domain-skip) próbálkozni |
| PASS | FAIL | bármi | bármi | bármi | **Calibration drift** — paraméter-érzékenyebb mint vártuk, calibration ismétlés szükséges |
| PASS | bármi | bármi | bármi | FAIL | **Az intervenció kárt okoz** — a hipnagóg epizódok túl gyakoriak, csökkenteni a cooldown-t |
| bármelyik V FAIL | — | — | — | — | **INVALID_DUE_TO_PRECONDITION** — re-run más paraméterekkel |

## Mit nem csinálunk a verdict alapján

- **Nem fittelünk új W vagy M küszöböt** — a calibration-szken egyszer megvolt, a pre-reg ezzel megy
- **Nem cseréljük le az intervenció-módot futás közben**. Ha M-H2 FAIL, új kísérlet új pre-reg-gel
- **Nem ülteti át** a `verify_chain_depth` és a meglepetés-detektort a Modul D-be — azok már Modul C-be vannak rendelve

## Idő-becslés

- Implementáció: **kész**
- Calibration scan: **kész** (24 cella × 3 seed × 2000 lépés ≈ 4 perc)
- Pre-reg írás: **kész**
- Formal batch (3 kar × 30 seed × 3000 lépés): **~5 perc compute**
- Elemzés + verdict: **~15 perc**
- **Hátralévő összesen: ~30 perc**

---

*Pre-regisztráció lezárva.*

---

# UTÓRÉSZ — eredmények és verdict

**Dátum:** 2026-04-30 (futás után)

## Nyers számok (medián, 30 seed × 3000 lépés × n_nodes=80, kalibrált W=500/M=3/pair)

| Kar | final_Q | n_edges | far_domain | max_rep_W | det_fires | interventions |
|---|---:|---:|---:|---:|---:|---:|
| meta_baseline | 0.1579 | 893 | 0.7524 | **6** | 0 | 0 |
| meta_log_only | 0.1579 | 893 | 0.7524 | 6 | 506 | 0 |
| meta_intervention | 0.1677 | 955 | 0.7586 | **5** | 493 | **12** |

A `meta_baseline` és `meta_log_only` **identikus** a Q/edges/far metrikákon (a detektor csak figyel, nem hat), ami sanity-megerősítés.

## V-feltételek

| | Érték | Verdict |
|---|---|---|
| V1 — n_edges in [50, 5000] | 893 | ✅ PASS |
| V2 — log_only fire_rate in [0.05, 0.30] | 0.169 | ✅ PASS |
| V3 — intervention count ≥ 3 | medián 12 | ✅ PASS |

## H-tesztek

### M-H1 (sanity) — calibration reprodukció

| | Érték |
|---|---|
| Calibration prediction (3 seed × 2000 step) | 0.144 |
| Formal (30 seed × 3000 step) | **0.169** |
| Pre-reg sáv | [0.07, 0.21] |

✅ **PASS** — a 30 seedes batch reprodukálja a calibration-t, a paraméter-érzékenység **kontroll alatt**.

### M-H2 (elsődleges engineering) — intervenció csökkenti az ismétlés-sűrűséget

| | Érték |
|---|---|
| baseline max_rep medián | 6 |
| intervention max_rep medián | **5** |
| Mann-Whitney p (egyoldali) | **7.6·10⁻³** (< 0.01) |
| effektus-méret | **1.0** (≥ 1.0 küszöb) |

✅ **PASS** — a hipnagóg intervenció szignifikánsan csökkenti az utolsó 500 lépés legmagasabb pár-ismétlődését. **A stuck-loop ténylegesen megszakad.**

### M-H3 (másodlagos substantive) — intervenció új területet érint

| | Érték |
|---|---|
| baseline far_domain | 0.7524 |
| intervention far_domain | 0.7586 |
| Mann-Whitney p (kétoldali) | **4.1·10⁻⁴** (< 0.05) |

✅ **PASS** — szignifikáns eltérés, a marginális mérete (+0.6pp) jelzi, hogy az intervenció **átirányít** a domain-térben.

### M-H4 (sanity) — intervenció nem rontja a Q-t

| | Érték |
|---|---|
| baseline final Q | 0.1579 |
| intervention final Q | **0.1677** |
| ratio | 1.062 (≥ 0.5 küszöb) |

✅ **PASS** — sőt, az intervención áteső kar **kissé jobb Q-t** ér el. A meta-monitor és a hipnagóg intervenció együtt **nem rontja** az engine-t.

## Pre-regisztrált döntésfa szerint a verdict

| V1-V3 | M-H1 | M-H2 | M-H3 | M-H4 | Verdict |
|---|---|---|---|---|---|
| **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **MODUL D MEGERŐSÍTVE** |

✅ **MODUL D — TELJES MEGERŐSÍTÉS**

## Mit jelent ez

A meta-monitor (PFC-analóg) **stuck-detection + hipnagóg intervenció** rendszere:

1. **Mechanikailag működik**: a stuck-detector W=500/M=3/pair paraméterekkel a baseline-on 16.9% firing rate-et ad — a calibration-ben prediktált zónában.
2. **Az intervenció hatásos**: a hipnagóg epizódok ténylegesen megszakítják a stuck-loopot, csökkentik az ismétlés-sűrűséget (max_rep 6 → 5, p<0.01).
3. **Új területet érint**: a far_domain_ratio szignifikánsan eltér (+0.6pp), tehát az intervenció **átirányít** a keresési térben — nem csak megszakít, hanem új útra terel.
4. **Nem ront**: az engine final Q-ja **javul** az intervenció hatására, nem csökken. A meta-monitor terhelése elhanyagolható.

## Kapcsolódás a többi modulhoz

- **Modul A (hipnagóg)**: a Modul D **közvetlenül használja** a Modul A-ban implementált `start_hypnagogic_episode()` API-t. A hipnagóg mód E1+E2-ben **részlegesen megerősítve** volt (H2 PASS, kreatív felfedezés cáfolt). **Modul D-ben mást használ a hipnagóg mód**: nem kreatív felfedezésre, hanem **stuck-loop megtörésére**. Ez **új funkció**, és a Modul D adatai alapján **ez a funkció működik**.
- **Modul B (memória)**: a Modul D engine-állapota a meglévő `engine.save_state()`-tel perzisztálható. A stuck-detector belső deque-je **nincs** mentve (transient real-time state, AWAKE-szerű), de az `_intervention_manager.intervention_count` rekordja a session-en belül elvész — későbbi finomítás.
- **Modul C** (jövőbeli): a stuck-detection eseményeit a Modul C konfliktus-érzékelő használhatja (a stuck-történet egy típus a "konfliktus-történet"-ben).

## Mit nem csinálunk a verdict alapján

- **Nem fittelünk új W vagy M paramétert** a kapott adatokra. A calibration-zóna egyszer megvolt.
- **Nem mondjuk azt, hogy "a hipnagóg mód megerősítve általánosságban"** — csak a **stuck-megtörő** funkciójában. A kreatív-felfedezés rész a Modul A E2-ben cáfolt maradt.
- **Nem keverjük a Modul D-t a Modul C-vel** — ezek külön mechanizmusok, külön pre-reg-ekkel.

## Statisztikai erősség összevetés a többi modul-eredménnyel

| Modul | Verdict | Erősség (legfontosabb p) |
|---|---|---|
| C — priority TOPO koncentráció | Cáfolat | p = 0.97 (vártnak ellentétes) |
| D — chain-adjacency setup | Cáfolat | mind cella saturated/silent |
| E1+E2 — hipnagóg kreativitás | Részleges (H2 PASS) | H2 p=10⁻⁸, H1+H4 cáfolt |
| **B** — epizodikus memória | **Megerősítve** | p = 1.4·10⁻¹¹ |
| **D** — meta-monitor (most) | **Megerősítve** | M-H2 p = 7.6·10⁻³ |

A két "MEGERŐSÍTVE" modul (B és D) az engineering-pillérek, amelyek a többi (kísérletileg cáfolt vagy részleges) modul köré kerültek. A vízió **egyharmada empirikusan megerősített**, a többi tisztán dokumentált negatív eredmény.

## Mit ad ez a paper-narratívához

- **Két engineering pillér** (Modul B + Modul D) együtt definiálja az AIE **session-folytonosság + stuck-detection** infrastruktúráját
- A Modul D **újrahasznosítja a Modul A hipnagóg mechanizmust** — egy másik kontextusban (stuck-megtörés vs kreatív felfedezés). Ez interesting tanulság: a hipnagóg mód **operatív értéke** nem ott van, ahol az eredeti vízió feltételezte
- A pre-reg + calibration + V-feltétel diszciplína **harmadszor is megmenti a tudományt** — itt nem ad cáfolatot, hanem a **paraméter-érzékenység előzetes kalibrálását** biztosítja, ami az érdemi mérés feltétele

## Következő lépés

A `PLAN_BRAIN_ARCHITECTURE.md` szerint:
- **Modul C — ACC-analóg konfliktus-érzékelő** (3 nap, mert átkerült 2 feature)
  - confidence_score(edge) — episztemikus címkézés
  - verify_chain_depth (Modul A-ból átkerülve)
  - meglepetés-detektor (Modul A-ból átkerülve)
- **Modul E — hierarchikus axióma-rétegzés** (nagyobb, csak ha A-B-C-D együtt szilárd)

A te ajánlásod szerint Modul C érlelési-tervezési munkával ELŐTTE — `confidence_score` definíció finomítása. A Modul D visszajelzése: a stuck-detection eseményei mint "konfliktus-jelzés" természetesen integrálódnak a Modul C-be.
