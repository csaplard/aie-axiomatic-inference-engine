# C kísérlet — priority_weight mechanizmus tesztje

**Dátum:** 2026-04-29 (pre-regisztráció — futás ELŐTT rögzítve)

## Háttér — miért kell ez a kísérlet

Az A1+B+B' kísérletek megerősítették a kettő-mechanizmus képet:
- TOPO ← strukturáltság
- Q ← immunrendszer

A jelen kísérlet egy **harmadik szabályozó réteget** vezet be: **csúcs-szintű `priority_weight ∈ [0,1]`**. A daemon-mód súlyozott választással többet próbál abduktív élet a magas-prioritású csúcsok körül, kevesebbet az alacsony-prioritásúak körül.

A nyitott kérdés: ez a mechanizmus **koncentrálja**-e a topológiai mélyülést a magas-prioritású részekre, vagy a rendszer priority-agnosztikus marad?

## Kísérleti dizájn

### Schema bővítés (visszafelé-kompatibilis)

A `nodes` listában opcionális `priority_weight` mező (default 0.5 ha hiányzik). A causal_edges és forbidden_edges változatlan; **éleken nincs priority** (átfedne a `source_trust`-tal — egy mechanizmus egyszerre).

### Engine-változtatás

Három pontot érint a `think_step`-ben az uniform random sampling helyett **súlyozott** sampling:
1. `_think_step_random_pair`: a két axióma választása súlyozott (`node_priority`)
2. `_think_step_heuristic`: `high[]` és `low[]` indexek priority-súlyozottak
3. Abduktív hipotézis-él próbálkozás: ugyanezzel a súlyozással

### 4-karú design (30 seed × 10000 lépés × strict-immune)

| Kar | Priority eloszlás | Cél |
|---|---|---|
| `priority_thesis` | strukturált — pl. classical mechanics csúcsok = 0.8, ZFC = 0.2, kvantum = 0.5 | Tézis: a strukturált priority koncentrálja a TOPO-mélyülést |
| `priority_uniform` | mind 0.5 | Baseline: priority-mentes (= mostani `timeless_strict` viselkedés ≈) |
| `priority_random` | csúcsonként véletlen ∈ [0.1, 0.9] | Strukturáltság vs. randomság teszt |
| `priority_inverted` | `priority_thesis` súlyok invertálva (1 - p) | Direkció-teszt: priority-szenzitív vagy priority-agnosztikus? |

### Új metrika — kvantilis-alapú TOPO partícionálás

A globális TOPO nem méri a koncentrációt. Új metrika a `graph_metrics.py`-ban:

```python
def topological_depth_partition(A, node_priority, q_high=0.67, q_low=0.33):
    """
    high_set = csúcsok, ahol priority >= q_high kvantilis (felső 33%)
    low_set  = csúcsok, ahol priority <= q_low kvantilis (alsó 33%)
    
    TOPO_high: leghosszabb irányított út a high_set-en belül (csak high csúcsokon át)
    TOPO_low: ugyanaz a low_set-en belül
    Vissza: (topo_high, topo_low, ratio = topo_high / max(topo_low, 1))
    """
```

Kvantilis-alapú (nem fix threshold), mert minden karon konzisztensen 33%-33%-ot jelöl ki, függetlenül a priority-eloszlás abszolút értékétől.

A telemetria kiegészül: `TOPO_HIGH=...` `TOPO_LOW=...` mezőkkel (visszafelé-kompatibilis: a régi parser ezeket figyelmen kívül hagyja, az új parser opcionálisként kezeli).

## Pre-regisztrált predikciók

### H1 (elsődleges) — TOPO koncentráció

A `priority_thesis` karon a TOPO **közvetlen koncentrálódik** a magas-prioritású csúcsokon:
- **Predikció:** `TOPO_high / TOPO_low > 1.5` (medián 30 seedre)
- **Statisztika:** Mann-Whitney U a TOPO_high vs TOPO_low eloszlásra, **p < 0.0125** (Bonferroni 4 teszt)
- **Cáfolat:** ratio < 1.2 vagy p > 0.05 → priority nem koncentrál

### H2 (másodlagos) — globális TOPO változatlan

Az össz-TOPO nem változik szignifikánsan (mert csak az élek **eloszlása** módosul, nem a számuk):
- **Predikció:** `priority_thesis` össz-TOPO ≈ `priority_uniform` össz-TOPO, **p > 0.05**
- **Cáfolat:** szignifikáns globális TOPO-eltérés → priority nem csak koncentrál, hanem összesen is hat

### H3 (másodlagos) — Q változatlan

Az élsűrűség nem változik szignifikánsan (priority nem rejekt-el éleket, csak átrendezi):
- **Predikció:** `priority_thesis` Q ≈ `priority_uniform` Q, **p > 0.05**

### H4 (kontroll) — direkció-teszt

A `priority_inverted` kar **fordított** TOPO_high/TOPO_low arányt ad:
- **Predikció:** `priority_inverted` `TOPO_high / TOPO_low < 0.7` (azaz a "low partíció" mostantól mélyebb, mert ott vannak az invertált high-priority csúcsok)
- **Statisztika:** `priority_thesis` ratio vs `priority_inverted` ratio, **p < 0.0125** (Bonferroni)
- **Cáfolat:** ha az inverted kar UGYANAZT az arányt adja, mint a thesis → a hatás nem priority-érték-szenzitív, hanem valami mellékhatás

### H5 (kontroll) — randomság-teszt

A `priority_random` kar **nem** ad szisztematikus koncentrációt:
- **Predikció:** `priority_random` `TOPO_high / TOPO_low ≈ 1.0` (nincs koncentráció)
- **Cáfolat:** szignifikáns eltérés 1.0-tól → maga a priority **megléte** koncentrál (nem a strukturáltság)

## Falszifikációs döntésfa

| Eredmény | Verdict |
|---|---|
| H1 PASS ÉS H4 PASS ÉS H5 PASS | **TÉZIS MEGERŐSÍTVE**: priority koncentrálja a TOPO-mélyülést, irány-szenzitív, struktúra-függő |
| H1 PASS DE H4 FAIL | **VEGYES**: priority hat, de nem irány-szenzitívan — gyanús, mellékhatás |
| H1 PASS DE H5 FAIL | **VEGYES**: maga a priority-megléte koncentrál, nem a strukturáltsága |
| H1 FAIL | **TÉZIS CÁFOLT**: priority nem koncentrálja a TOPO-t — a `think_step` súlyozása nem hat a kimenetre |
| H2 vagy H3 FAIL | Mellék-felfedezés — az átfogalmazott tézis: priority nem csak koncentrál, hanem globálisan is hat |

## Mit nem fogunk csinálni a kísérlet után

- Nem fogunk új küszöböt fittelni a kapott adatokra.
- Nem fogunk hozzáadni egy 5. kart, ami épp a kapott eredményt magyarázza.
- A pre-regisztrált küszöbök (1.5, 0.7, 1.2, 0.0125) változatlanok maradnak.

## Bónusz — post-hoc explorációs analízis (NEM része a falszifikációnak)

A kísérlet után, **transzparensen post-hoc**-ként jelölve, megvizsgáljuk:

> **Vajon a priority közvetve csökkenti az immunrendszer aktivitását az alacsony-prioritású részeken?**

Ha a `priority_thesis` low-partíción jelentősen alacsonyabb az élsűrűség (kevesebb hipotézis-próba), akkor ott az immunrendszer is ritkábban triggerel. Ez egy **harmadik mechanizmusra** utalna: priority → indirect immune-gating.

A vizsgálat módja: a futás után a végső gráfon a high vs low partícióban az élek és a contradiction-rejekciók aránya. **Ez nem pre-regisztrált predikció**, csak a kísérlet melléktermékének átnézése.

## Idő-becslés

- Schema + engine + új metrika: ~1 óra
- Unit tesztek: ~30 perc
- 4 priority generátor: ~30 perc
- Batch + elemzés: ~1 óra
- **Összesen: ~3 óra**

---

*Pre-regisztráció lezárva.*

---

# UTÓRÉSZ — eredmények és verdict

**Dátum:** 2026-04-30 (futás után, őszinte adatközpontú értékelés)

## A 4 kar nyers számai (medián, 30 seed × 10000 lépés × strict-immune)

| Kar | TOPO | TOPO_high | TOPO_low | ratio | Q | RRR |
|---|---:|---:|---:|---:|---:|---:|
| priority_thesis | 19.00 | 4.00 | 5.00 | **0.817** | 0.1951 | 0.000 |
| priority_uniform | 16.00 | 16.00* | 16.00* | 1.000* | 0.1952 | 0.000 |
| priority_random | 20.00 | — | — | 0.545 | — | 0.900 |
| priority_inverted | 20.50 | — | — | 1.000 | — | 0.988 |

\* `priority_uniform`-on minden priority = 0.5, ezért a kvantilis-küszöbök egybeesnek; a partíció gyakorlatilag az egész gráf — ez **nem** torzítja a többi kar értelmezését (a thesis/random/inverted partíciói valódiak).

## Pre-regisztrált predikciók verdictje

| Hipotézis | Predikció | Eredmény | Verdict |
|---|---|---|---|
| **H1** — priority_thesis koncentrál a high-partícióba | ratio > 1.5 ÉS p<0.0125 | **ratio = 0.817 (LOW > HIGH!)** Mann-Whitney p=0.97 | ❌ **CÁFOLT — pont fordítva** |
| **H2** — globális TOPO változatlan | p > 0.05 | thesis=19 vs uniform=16, **p = 2.2·10⁻⁵** | ❌ **CÁFOLT — priority HAT a globális TOPO-ra** |
| **H3** — Q változatlan | p > 0.05 | thesis Q=0.1951 vs uniform Q=0.1952, p=0.44 | ✅ **PASS** |
| **H4** — inverted ratio < 0.7 (irány-szenzitív) | inverted ratio < 0.7 | inverted ratio = **1.000** | ❌ **CÁFOLT** |
| **H5** — random ratio ≈ 1.0 | |ratio - 1.0| < 0.2 | random ratio = **0.545** | ❌ **CÁFOLT** |

**Pre-regisztrált döntésfa szerint: TÉZIS CÁFOLT** — a priority NEM koncentrálja a TOPO-mélyülést a magas-prioritású csúcsokra. Sőt, fordítva: a `priority_thesis`-en az alacsony-priority partíció **mélyebb**, mint a magas.

## Mit mond ez a kísérlet a priority mechanizmusról?

A pre-regisztrált verdict önmagában nem teljes. Az adat egy **gazdagabb képet** rajzol:

### Megfigyelés 1: A priority globálisan HAT a TOPO-ra (H2 cáfolata)

`priority_thesis` össz-TOPO = 19 vs `priority_uniform` = 16. **3 csúccsal mélyebb láncot** épít, p<10⁻⁴. A priority **nem semleges** átrendezés — a heurisztika egyébként nem építette volna ezt a mélységet.

### Megfigyelés 2: A koncentráció iránya FORDÍTOTT a vártnak (H1 cáfolata)

A `priority_thesis`-en a **low-partíció** (QM+INFO csúcsok) **mélyebb** lánc-szerkezetet kap, mint a high-partíció (LOGIC+NEWTON). Lehetséges magyarázat: a heurisztika a high-priority csúcsokat összefogja **rövid ágakra** (sok redundáns él), mialatt a low-partícióban a kauzális gerinc (`0→1→...→14` lánc természetes szakaszai a QM+INFO indexeknél) **háborítatlanabbul** mélyülhet a `verify_logic` tranzitív zárás által.

Ez egy **mechanikai felfedezés**: a súlyozott abduktív sampling **nem azonos** a topológiai mélyítéssel. Több próba ≠ mélyebb topológia, sőt, fordítva is hat.

### Megfigyelés 3 (post-hoc, transzparensen jelölve): priority → immun-gating

A 4 kar között **óriási** RRR-variancia:

| Összevetés | medián RRR_a vs RRR_b | p (kétoldali) |
|---|---|---|
| thesis vs uniform | 0.00 vs 0.00 | 0.55 (nincs eltérés) |
| thesis vs random | 0.00 vs 0.90 | **0.0025** |
| thesis vs inverted | 0.00 vs 0.99 | **6·10⁻⁹** |
| random vs inverted | 0.90 vs 0.99 | **8·10⁻⁷** |

A priority eloszlása szignifikánsan **átrendezi**, hogy mely él-próbák kerülnek a heurisztikába → **közvetve** aktiválja vagy elnémítja az immunrendszert. A `priority_inverted` karon az RRR átlag **0.98**, gyakorlatilag minden visszafelé-próba contradicción rejekcióba ütközik. A `priority_thesis`-en RRR átlag **0.31**.

Ez **bemenett** abba, amit a kísérlet előtti pre-feedback explicit megsejtett: *"a priority közvetve csökkenti az immun-rendszer aktivitását azokon a területeken, ahol kevés a fókusz"*. A **direkció** azonban nem csak csökkenés — a hatás **kétirányú**: thesis-szerű konfigurációk **csendesítik**, az inverted-szerű konfigurációk **felerősítik** az immunrendszert.

A korábbi A1+B+B' kísérletekben azt találtuk: az immun **a Q-t szabályozza**, **a TOPO-t nem**. A C kísérlet hozzáteszi: **a priority közvetve a Q-szabályozó immun-rendszer aktivitását is állítja**. Ez egy **negyedik mechanizmus** a képbe.

## Mit nem csinálunk a verdict alapján

- **Nem fittelünk új küszöböt** a priority-hatás megmentésére. Az 1.5-ös arány-küszöb a pre-regisztráció része volt; nem mozdítjuk.
- **Nem dobjuk el a priority koncepciót** — az adat azt mutatja, hogy a mechanizmus **valós**, csak nem azt csinálja, amit a tézis feltételezett. A priority **nem** koncentrációs eszköz; **átirányít a heurisztika-keresési térben**, és ennek mellékhatása az immun-aktivitás drasztikus változása.

## Mi a következő, jól-formált kérdés?

A C kísérlet egy **negatív elsődleges eredménnyel** + **erős mellék-felfedezéssel** zárul. A logikus folytatás:

> **D kísérlet — pre-regisztráció:** *Ha a priority a heurisztika átirányításán keresztül szabályozza az immun-aktivitást, akkor egy második priority-konfigurációval (pl. priority_random_2 másik seeddel) szignifikánsan reprodukálható a 0.5–0.8 közti köztes RRR. És az immun-aktivitás kar-ról-kar-ra deterministikusan kiszámítható kell hogy legyen a priority-eloszlásból + heurisztika ismeretéből.*

Ez egy **új tézis** — pre-regisztrálva, mint nyitott kérdés. **Nem most futtatjuk**, mert ez nem volt a C kísérlet része.

## A négy mechanizmus jelenlegi képe

A kísérletek (A1+B+B'+C) együtt:

1. **TOPO ← strukturáltság** (megerősítve, p=10⁻¹¹)
2. **Q ← immunrendszer** (megerősítve, p=10⁻¹¹ A1-en)
3. **TOPO ⊥ immun** (megerősítve, p>0.3 mindenhol)
4. **Immun-aktivitás ← priority** (post-hoc, p=10⁻⁸ thesis vs inverted) — **új, megerősítendő**

A C kísérlet a 4. mechanizmust **gyanús erős mintázatként** dokumentálja, de mint **post-hoc megfigyelést**, nem mint pre-regisztrált bizonyítékot. A formális megerősítéshez új kísérlet kell.

---

## Függelék: post-hoc index-távolság diagnosztika (D kísérlet tervezéséhez)

A post-hoc RRR-mintázatra két versengő magyarázat élt:
- **(a) Domain-coherence**: priority-eloszlás illeszkedése/inkongruenciája a domain-szerkezethez
- **(b) Chain-adjacency**: a magas-priority csúcsok közelsége a kauzális gerincben + a forbidden_edges/negation_pairs közeli-távolság placement-je

A mechanizmus szétválasztásához egy gyors diagnosztikai re-run, seed=0, 2000 lépés a 4 priority karra. Lépésenként rögzítve a (i, j, reject_reason) hármas a `_last_think_snapshot`-ból.

### Eredmény (script: [`experiments/pair_distance_diagnostic.py`](experiments/pair_distance_diagnostic.py))

| Kar | mean \|i-j\| összes próba | mean \|i-j\| immun-rejekt | n immun-rejekt |
|---|---:|---:|---:|
| priority_thesis | 22.38 | 19.30 | 312 |
| priority_uniform | 24.06 | 28.99 (medián 46) | 266 |
| priority_random | 22.39 | 27.37 | 251 |
| priority_inverted | 23.25 | **13.40 (medián 3)** | 124 |

Mann-Whitney U (kétoldali p, immun-rejekt eloszlások):
- thesis vs inverted: **p = 2.6·10⁻¹⁰**
- random vs inverted: **p = 6.9·10⁻¹⁷**

### Confound felfedezés — `n_nodes` default = 64

A diagnosztika közben kiderült, hogy a motor `n_nodes` alapértelmezése **64**, és a 15-csúcsos dense regiszterre `max(64, 15) = 64`-es mátrixban dolgozik. Indexen 15-63 **49 padding csúcs** áll, mind alapértelmezett `priority = 0.5`.

Ez azt jelenti, hogy a C kísérlet **kvantilis-alapú TOPO partícionálása** valójában a padding-domináns priority-eloszlást nézte:
- q67 = 0.5, q33 = 0.5 (mert 49/64 érték pontosan 0.5)
- high_mask ≈ 56 csúcs, low_mask ≈ 57 csúcs, **óriási átfedéssel**

A pre-regisztrált H1 teszt **valójában nem mérte azt, amit szerettünk volna mérni** — a partícióban a registry-csúcsok elenyésző kisebbség. Ez nem cáfolja az eredményt (a verdict továbbra is "H1 cáfolt"), de **a cáfolat oka most más**: nem azt mondja, hogy a priority nem koncentrál, hanem azt, hogy a confound miatt nem **mérhető** tisztán, hogy koncentrál-e.

### Két egymást nem kizáró megállapítás

1. **Chain-adjacency részben magyarázza** a `priority_inverted` extrém RRR-jét — a heurisztika konszekutív párokra (medián|i-j|=3!) koncentrálja a próbákat, és a forbidden_edges/negation_pairs registry-indextér 0-14 közeli párokra esik.

2. **A `priority_uniform` immun-rejekt mean|i-j|=29 nem chain-adjacency** — uniform-on nincs adjacency-bias, hanem a padding-confound mutatja meg az "immun-rejekt csúcsok kiugrása" mintázatát.

### Ajánlás a D kísérlet dizájnjához

**2D dizájn szükséges:** priority-koherencia × adjacency-konfiguráció.

Két kötelező változtatás a C-hez képest:
1. **`n_nodes = registry size`** — ha 15-csúcsos regiszter, akkor `--n-nodes 15` az engine-nek (a runner-be új flag), eltünteti a padding-domináns partíciót.
2. **Külön kontroll a chain-adjacency-re** — kar, ahol a `forbidden_edges` és `negation_pairs` placement véletlen, nem a "j-i ≥ 2" kényszerrel.

Várható mátrix: ~6-8 kar (3 priority-szint × 2-3 adjacency-konfiguráció), ~10 perc compute 30 seeddel. A pre-regisztráció ezzel az információval most informáltabb lesz — **érlelve** állítsuk össze, nem siettetve.
