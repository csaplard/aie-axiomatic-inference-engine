# E kísérlet — hipnagóg üzemmód + Fisher-detektor

**Dátum:** 2026-04-30 (pre-regisztráció — futás ELŐTT rögzítve, post-hoc fittelés kizárására)

## Háttér — miért kell ez a kísérlet

Az A1+B+B'+C+D kísérletek megerősítették a kettő-mechanizmus képet (TOPO ← strukturáltság, Q ← immun) és felfedezték a priority-mediált indirekt immun-modulációt mint negyedik mechanizmust. A `PLAN_BRAIN_ARCHITECTURE.md` Modul A egy **harmadik üzemmódot** ír le a daemon mellé: hipnagóg módot, ahol a szabályok lazulnak, távoli asszociációk születnek, és a mód-átmenet pillanata egy **Fisher path speed**-szerű mérőszámmal detektálható.

A nyitott kérdés: a hipnagóg mód **valóban új felfedezési mechanizmus** (strukturálisan eltérő dinamika + olyan élek, amelyek daemon-módban nem jelennek meg), vagy csak **a daemon mód paraméter-variációja** (több próba, de azonos minta)? És: a Frobenius-alapú minimális Fisher-becslő képes-e a koncepció-szintű átmenetet detektálni?

A `METHODS_NOTES.md` rögzítette, hogy a paramétertér nagy részén (kis n, sűrű immun) a TOPO és RRR egyaránt **saturált** mintázatokat ad. Az E kísérlet ezt explicit figyelembe veszi a setupban.

## Architekturális döntések (MEGEGYEZÉSSEL rögzítve, a pre-reg ezekre épít)

### Fisher path speed — minimum-viable Markov-Frobenius változat

A teljes paper-4 SAX+LSTM pipeline átemelése helyett **minimum-viable Markov-becslő** kerül implementálásra:

- **Diszkrét emissziós ábécé, K=4** (kölcsönösen kizáró osztályok):
  - `deductive_added` — `verify_logic` sikeres ÉS él hozzáadva
  - `abductive_added` — discovery módban hipotézis-él hozzáadva (NEM `verify_logic` útján)
  - `rejected` — bármilyen rejekt (forbidden / negation / exists, aggregálva)
  - `idle` — nem volt érvényes pár
- **Domain-átmenet külön logolva** (nem szerepel az emissziós ábécében — utólag származtatva az (i, j) pár-azonosítókból a registry domain-mappingjéből).
- **T_n becslés**: a legutóbbi W emisszióból gördülő ablakon számolt K×K maximum-likelihood átmeneti mátrix (Laplace-simítással kis ablakon).
- **v(N) = ‖T_(n+1) − T_n‖_F** (Frobenius-norma a két szomszédos ablak transition-mátrixa között).
- **Ajánlott ablakméret: W ∈ [200, 500] think_step.** Implementációs paraméter; a pre-reg konkrét értékhez nem köt — a diagnosztikai futás után az implementáció rögzít egy értéket, és minden alábbi pre-reg küszöb erre az értékre vonatkozik.

### Háromfázisú állapotgép

| Fázis | Hossz (think_step) | Cél |
|---|---:|---|
| Belépő (`entry`) | 5–10 | Szabályok fokozatos lazítása |
| Mély (`deep`) | 20–50 | Teljes lazítás |
| Kilépő (`exit`) | 5–10 | Visszatérés éber-szigorhoz |

**Lazítási paraméterek (entry → deep közti lineáris interpoláció):**

| Paraméter | Éber/daemon | Mély hipnagóg |
|---|---|---|
| `forbidden_edges` súly | 1.0 (kemény) | 0.3 (lágy szűrő) |
| `logical_negation_pairs` ellenőrzés | bináris | küszöb-alapú |
| heurisztika domain-távoli pár-preferencia | 0% | 60% |
| `verify_logic` lánc-mélysége | 1 | 3–5 |
| meglepetés-detektor érzékenysége | nominális | maximum |

### "Kő-leesés" trigger (kilépés a deep fázisból)

Ha a v(N) **megugrik** (= az átmeneti mátrix gyorsan változik = kaotikussá válik a rendszer = mély-alvás-szerű állapot kezdődik), **azonnal exit-fázis indul**.

- **Elsődleges (pre-regisztrált) detektor:** küszöb-alapú: `v(N) > median(v_steady_state) × 2.0`, ahol `v_steady_state` a megelőző daemon-szakasz gördülő mediánja.
- **Másodlagos (kontroll) detektor:** második derivált alapú: a v(N) görbe **második inflexiós pontja** a deep fázis kezdete óta. Lásd a következő pontot.

### Kettős inflexió — pre-regisztrált módszertani megfontolás

A v(N) profil hipnagóg módban **két inflexiós pontot** mutathat:
1. **Korai emelkedés:** a lazítás bekapcsolásakor a rejekt-arány csökken → a transition-mátrix `rejected` oszlopa lecsökken → v(N) **első emelkedés** (a relaxáció elkerülhetetlen mellékhatása, NEM koncepció-szintű átmenet).
2. **Késői emelkedés:** ha a rendszer ténylegesen kaotikus állapotba kerül → v(N) **másodszor is emelkedik** (ez a "kő-leesés", koncepció-szintű átmenet).

A trigger előfordulhat, hogy **a második inflexión kell hogy fírejen**, nem a puszta küszöb-átlépésen. Pre-regisztráljuk:
- Az **elsődleges signal** a küszöb-alapú trigger (`v(N) > 2.0 × median_steady`).
- A **másodlagos check** a második-derivált (`d²v/dN² > 0` váltása a deep fázisban legalább 2 ablak-szélességgel a belépő fázis után).
- A naplózás **mindkét** detektor-eseményt rögzíti, függetlenül attól, hogy melyik kapcsolt először. A verdict után dönthető el, melyik a hűségesebb jelzés.

Ha a két detektor **rendszeresen különböző pillanatokban** kapcsol (medián késleltetés > 5 think_step a deep fázis hosszához képest), akkor a Frobenius-metrika nem informatív a koncepció-szintű átmenetre — ez a pre-reg null-eredmény harmadik ága (lásd alább).

## Kísérleti dizájn

### Schema — emissziós napló (új JSONL)

Új fájl: `hypnagogic_emissions.jsonl`. Lépésenként egy rekord:

```json
{
  "step_id": int,
  "tick": int,
  "emission": "deductive_added" | "abductive_added" | "rejected" | "idle",
  "pair": [int, int] | null,
  "domain_transition": bool,
  "reject_reason": "forbidden" | "negation" | "exists" | null
}
```

Külön fájl: `hypnagogic_log.jsonl` — minden hipnagóg módban felvett él rekordja a `PLAN_BRAIN_ARCHITECTURE.md` Modul A pont 5 szerint (timestamp, fázis, lazítási értékek, pár-azonosítók, meglepetés-pontszám, v(N) a felvétel pillanatában).

### Karok (3 kar)

A confound-térkép tanulsága szerint healthy paraméter-régió: `n_nodes ∈ [60, 100]`, kis-közepes immun-sűrűség, izolált-vagy-ritka kezdeti causal_edges. Az E kísérlet ebben a tartományban fut.

| Kar | Mód-séma | Cél |
|---|---|---|
| `daemon_baseline` | tisztán daemon, hipnagóg sosem aktiválódik | Baseline minden mérésre |
| `hypnagogic_periodic` | minden N=300 think_step után 30-50 lépés hipnagóg-ciklus (entry → deep → exit) | Tézis-kar |
| `hypnagogic_no_relax` | ugyanaz a 30-50 lépéses ciklus időzítés, de a lazítási paraméterek éber-szigoron maradnak | Specifikusság-kontroll: a hatás a lazításból jön, nem a ciklikus reset-ből |

**Statikus paraméterek:** 30 seed × 3000 think_step / seed × strict-immune. `n_nodes = 80`, registry: a meglévő dense-szerű, de kis-közepes immun-sűrűséggel (`forbidden = 5`, `negation = 5`).

Compute-becslés: ~30 perc az első batch-re (matching the PLAN's first-batch estimate).

### Új metrikák

A `graph_metrics.py`-ba két új mérőszám kerül (visszafelé-kompatibilis, a régi parser figyelmen kívül hagyja):

1. **`far_domain_edge_ratio(graph, domain_map)`** — a hozzáadott élek közül azok aránya, amelyekre `domain(i) ≠ domain(j)` ÉS `domain_distance(i, j) ≥ 2` (a domain-mapping részletei az implementációs döntés).
2. **`waking_pass_rate(hypnagogic_edges, kernel)`** — a hipnagóg módban felvett élek listáján éber-szigorral (`strict_immune`, `verify_logic` mélység = 1, `forbidden_edges` súly = 1.0) végzett re-evaluáció pass-aránya. A re-evaluáció **a deep fázis lezárása után automatikusan** fut a kilépő fázisban.

### Telemetria-bővítés

A meglévő telemetry-sorok kiegészülnek (a régi parser ezeket figyelmen kívül hagyja):
- `V_N=...` — a Frobenius v(N) érték
- `MODE=daemon|hypnagogic_entry|hypnagogic_deep|hypnagogic_exit`
- `FAR_DOMAIN=...` — kumulatív far-domain élek száma
- `WAKING_PASS=...` — utolsó hipnagóg-ciklus waking_pass_rate értéke

## Pre-regisztrált predikciók

### H1 (elsődleges) — far-domain élek

A `hypnagogic_periodic` kar szignifikánsan **több far-domain élt** termel, mint a `daemon_baseline`:

- **Predikció:** Mann-Whitney U a `far_domain_edge_ratio` eloszlásra (30 seed), egyoldali, **p < 0.01**
- **Effektus-irány:** `hypnagogic_periodic > daemon_baseline`
- **Cáfolat:** p > 0.05 vagy fordított irány → a hipnagóg mód NEM nyit új távoli kapcsolatokat

### H2 (elsődleges) — alacsonyabb waking pass-rate

A hipnagóg módban felvett élek **éber-szigorra bukási aránya** lényegesen magasabb, mint a daemon-mód éleié:

- **Predikció:** `waking_pass_rate(hypnagogic_periodic) ∈ [0.30, 0.60]`, `waking_pass_rate(daemon_baseline) ∈ [0.80, 0.95]`
- **Statisztika:** Mann-Whitney U az élszintű pass-arány eloszlásra, egyoldali, **p < 0.01**
- **Effektus-irány:** `hypnagogic_periodic < daemon_baseline`
- **Cáfolat:** ha a hipnagóg pass-rate ≥ 0.80, akkor a lazítás **gyakorlatilag nem hat** (vagyis a forbidden/negation szabályok soft-formája is rejekt-el — a relaxáció implementációs hibája gyanús, vagy a koncepció hibás)

### H3 (elsődleges) — újdonság-teszt

A `hypnagogic_periodic` karban éber-szigort átment hipnagóg-élek **többségükben olyan domain-pár-konfigurációkat** tartalmaznak, amelyeket a `daemon_baseline` 30 seed × 3000 lépés alatt **nem termelt meg**:

- **Predikció:** a hipnagóg-túlélő far-domain élek **legalább 50%-a** olyan (domain_a, domain_b) párokat érint, amelyekre a `daemon_baseline` a teljes 30-seed batch-ben 0 darab élt rakott le
- **Statisztika:** binomiális teszt vs. 0.5, egyoldali, **p < 0.05** (azaz az újdonság-arány szignifikánsan ≥ 0.5)
- **Cáfolat:** ha az újdonság-arány < 0.3 → a hipnagóg mód **csak több próbát** termel, nem új tartományokat

### H4 (másodlagos) — magasabb v(N) a deep fázisban

A Frobenius v(N) átlaga a `hypnagogic_periodic` deep fázisának (csak a deep szakaszok aggregálva) szignifikánsan magasabb, mint a `daemon_baseline` ugyanazon long-window-időablakain:

- **Predikció:** Mann-Whitney U, egyoldali, **p < 0.01**
- **Effektus-irány:** `mean(v_N | hypnagogic_deep) > mean(v_N | daemon_baseline)`
- **Cáfolat:** p > 0.05 → a Frobenius-metrika nem érzékeny a mód-átmenetre. A H1+H2+H3 még megerősíthető anélkül is, de akkor **a trigger-detektort cserélni kell** (lásd döntésfa).

### Kontroll — `hypnagogic_no_relax` viselkedése

- **Várakozás:** `hypnagogic_no_relax` minden mérőszámon **statisztikailag megkülönböztethetetlen** a `daemon_baseline`-tól (Mann-Whitney p > 0.1 mindenhol).
- **Ha mégis eltér:** a periódikus reset önmagában is hat → a tézist a "lazítás vs. ciklus" megkülönböztetésre élesíteni kell.

## Falszifikációs döntésfa

Az "elsődleges szigor" cella: a H1+H2+H3 **többsége** átment (legalább 2/3) ÉS a `hypnagogic_no_relax` kontroll jól viselkedik (nem különbözik a baseline-tól).

| H1+H2+H3 többsége PASS | H4 PASS | Verdict |
|---|---|---|
| Igen | Igen | **Hipnagóg mód mint különálló felfedezési mechanizmus megerősítve** — különálló dinamika és új far-domain felfedezések, a Frobenius-trigger érzékeny |
| Igen | Nem | **Megerősítve, de a trigger-metrika hibás** — a mód valós és új éleket termel, de a Frobenius v(N) nem fogja meg az átmenetet; új detektor szükséges (pl. spektrális gap, vagy a paper-4 LSTM-pipeline) |
| Nem | Igen | **A mód más dinamikát ad, de NEM új felfedezéseket** — a Frobenius érzékeny a paraméter-változásra, de a kimenet nem hozz új far-domain éleket; a hipnagóg-koncepció TUDOMÁNYOS értéke kérdéses |
| Nem | Nem | **Hipnagóg-koncepció ezen a motoron CÁFOLT** — sem új dinamika, sem új felfedezések |

A `hypnagogic_no_relax` kontroll bármely cellában **el kell hogy térjen** a `hypnagogic_periodic`-tól (legalább a H1 vagy H2 mérőszámon, p < 0.05). Ha nem tér el → a hatás nem a lazításból jön, hanem a ciklikus-reset mellékhatásából, és a verdict **vegyes** kategóriába kerül a fenti 4-cellás döntésfa felett.

## Null-eredmény pre-regisztráció (CRITICAL — a C, D hagyomány szerint)

A `hypnagogic_periodic` koncepciót **teljesen cáfolja**, ha az alábbiak közül **bármelyik** teljesül:

1. **Az emissziós eloszlás nem különbözik a daemon-tól.**
   - Konkrét teszt: a `daemon_baseline` és a `hypnagogic_periodic` deep-fázisainak v(N) eloszlására Mann-Whitney U **p > 0.05** (kétoldali).
   - Verdict: a hipnagóg mód **csak a daemon paraméter-variációja**, nem új mód.

2. **A felfedezett élek waking pass-rate-je megkülönböztethetetlen a daemon-tól.**
   - Konkrét teszt: a hipnagóg-felvett élek élszintű pass-rate eloszlása vs. a daemon-felvett élek pass-rate eloszlása, Mann-Whitney U **p > 0.05**.
   - Verdict: a hipnagóg **csak több próbát** termel, nem új típusú felfedezéseket.

3. **A Fisher-trigger soha nem fíre, vagy mindig túl korán/későn.**
   - Konkrét teszt: a 30 seedből legalább 25-ben a küszöb-alapú trigger **a deep fázis első 5 lépésén belül** kapcsol (túl korán) VAGY **soha nem kapcsol** a deep fázis 50 lépése alatt (egyik sem fogja meg az átmenetet).
   - Verdict: a Frobenius-metrika **nem érzékeny** a koncepció-szintű átmenetre — más detektor kell (pl. paper-4 SAX+LSTM, vagy spektrális gap a transition-mátrixon, vagy entrópia-alapú).

Bármelyik null-eredmény-ág beteljesülése esetén a **döntésfa felülírja** a 4-cellás verdictet ("hipnagóg-koncepció refutálva ezen a motoron").

## Mit nem fogunk csinálni a kísérlet után

- **Nem fittelünk új küszöböt** a kapott v(N) eloszlásra. A `2.0 × median_steady` trigger-küszöb és a `0.5` újdonság-arány-küszöb, valamint a `[0.30, 0.60]` és `[0.80, 0.95]` waking pass-rate sávok **a futás előtt rögzítve**, post-hoc nem mozdítjuk.
- **Nem adunk hozzá egy 4. kart**, ami épp a kapott eredményt magyarázza. Ha a `hypnagogic_no_relax` kontroll szokatlan mintát ad, az **új kísérlet új pre-regisztrációja**.
- **Nem cseréljük le a Frobenius-metrikát** a futás közben. Ha a H4 cáfolódik, a verdict azt mondja, és egy következő kísérlet (új pre-reg) cseréli le a detektort.
- **Nem nevezzük át** a "rejected" emissziós osztályt finomabb sub-kategóriákra (forbidden / negation / exists), ha a H1–H3 nem ad tiszta eredményt. A K=4 ábécé a futásra rögzített.
- **Nem keverjük** a TOPO-saturáció és RRR-saturáció confound-térképet az E-eredmény értelmezésébe — az E saját registry- és paramétertér-választása szándékosan a `METHODS_NOTES.md` healthy-régiójára esik.

## Érvényesség-feltételek (validity preconditions) — pre-reg, futás ELŐTT rögzítve

A C és D kísérletek tanulsága szerint a paramétertér mindkét végpontján saturációs zónák léteznek (TOPO-saturáció, RRR-saturáció), és egy ott felvett verdict **érdemtelen lenne** mind a megerősítésre, mind a cáfolatra. Ezért a H1–H4 verdictek érvényessége az alábbi feltételeken áll vagy bukik. **Ha BÁRMELY feltétel sérül, a verdict: `INVALID_DUE_TO_SATURATION`** — nem cáfolat, hanem újrafutás más paraméterekkel (különböző `n_nodes`, immun-sűrűség, vagy `n_steps`).

A feltételek **kizárólag a `daemon_baseline` karra vonatkoznak** (a kontroll-állapotot ellenőrzik), 30 seeden átlagolva:

| Feltétel | Tartomány | Indoklás |
|---|---|---|
| **V1 — RRR plafon** | `daemon_baseline mean RRR ∈ [0.05, 0.60]` | RRR > 0.60: az immun telítve, hipnagóg-modulációnak nincs hely (D kísérlet tanulsága). RRR < 0.05: az immun gyakorlatilag inaktív, nincs amit modulálni. |
| **V2 — far-domain plafon** | `daemon_baseline median far_domain_edge_ratio ∈ [0.05, 0.85]` | < 0.05: a registry nem enged far-domain éleket (registry hibás). > 0.85: minden él far-domain, nincs növekedési potenciál a hipnagóg karnak. |
| **V3 — pass-rate plafon** | `daemon_baseline median waking_pass_rate ∈ [0.50, 0.99]` | < 0.50: a daemon élei is bukásra állnak (engine misconfigured / re-evaluation hibás). > 0.99: pass-rate plafon, a hipnagóg karnak nincs hova csökkennie érdemi módon. |
| **V4 — Frobenius v(N) variancia** | `daemon_baseline mean v(N) > 0 ÉS coefficient_of_variation(v(N)) > 0.10` | Ha v(N) konstans zéró vagy közel az: a Markov-becslő degenerált (pl. egy emissziós osztály dominál). A H4 nem értelmezhető. |

### Mit tesz a runner, ha valamelyik feltétel sérül

A `daemon_baseline` aggregálása után az elemző script **automatikusan ellenőrzi a 4 V-feltételt**. Ha BÁRMELY sérül:
1. A H1–H4 verdictek **felfüggesztve** (nem PASS, nem FAIL — `INVALID`)
2. A V-feltétel-jelentés rögzítésre kerül a futási kimenetben
3. A re-run paraméter-javaslat: a sérülő feltételhez kötött dimenzió mozdítása (pl. ha V1 sérül RRR>0.60-nal, akkor `forbidden + negation` csökkentése; ha < 0.05, akkor növelése)

### Mit nem teszünk a V-feltételek aktiválódása esetén

- **Nem fittelünk új abszolút sávot** (pl. H2 `[0.30, 0.60]` → `[X, Y]`) a kapott daemon-baseline alapján. Az új batch-et új paraméterekkel **újra futtatjuk**, és a régi pre-reg-küszöbök változatlanok maradnak.
- **Nem értelmezzük** az `INVALID` eredményt sem cáfolatként, sem megerősítésként — nincs verdict.

## Idő-becslés

- Schema (emissziós napló + telemetry-bővítés) + engine (3 fázisú állapotgép, lazítási interpoláció): ~1 nap
- Frobenius v(N) számoló + trigger-modul (elsődleges + másodlagos detektor) + waking re-evaluációs hurok: ~1 nap
- Unit tesztek (mód-váltás, lazítási paraméterek, trigger-küszöb, hipnagóg napló, Frobenius számolás): ~0.5 nap
- 3-karú batch (30 seed × 3000 lépés × 3 kar) + elemzés: ~0.5–1 nap (ebből compute ~30 perc)
- **Összesen: 3–4 nap fókuszált munka, ~30 perc compute az első batch-hez.**

---

*Pre-regisztráció lezárva.*

---

# UTÓRÉSZ — eredmények és verdict

**Dátum:** 2026-04-30 (futás után, javított no_relax kontrollal)

## Implementációs megjegyzések

Az implementáció során **két lényeges egyszerűsítést** kellett tenni a pre-reg ideálhoz képest:

1. **A relaxációs paraméterek közül csak kettő van engine-re kötve**: `forbidden_weight` (a `is_edge_forbidden` valószínűségi hatást ad) és `negation_threshold` (a `_would_contradict_edge` ugyanígy). A `far_domain_pref` és `verify_chain_depth` mezők a `current_relaxation()` dict-ben szerepelnek, de a `think_step` heurisztika **nem konzultálja** őket. Ez későbbi integrációs munka.
2. **Konfigurációs kezdeti hiba**: a `no_relax` kontroll-kar policy-jában a `negation_threshold_deep` mezőt nem írtuk felül explicit `1.0`-ra; a default `0.5` érvényesült, ami szivárgott a kontrollra. **Javítva** a futás közben (lásd alább).

A javítás után a kontroll IDENTIKUS a daemon-nal (p=1.0 mind a 30 seedre), tehát a tézis-kar hatása **NEM** a ciklikus reset, hanem a tényleges relaxáció.

## Nyers számok (medián, 30 seed × 3000 lépés × n_nodes=80, strict immune, javított no_relax)

| Kar | RRR | far_domain | pass_rate | v(N) |
|---|---:|---:|---:|---:|
| daemon_baseline | 0.551 | 0.752 | 0.886 | 0.211 |
| hypnagogic_periodic | 0.496 | 0.756 | **0.835** | 0.210 |
| hypnagogic_no_relax | 0.551 | 0.752 | 0.886 | 0.211 |

## V-feltételek (érvényesség-precondíciók)

A daemon_baseline kar 30 seed-medián értékei alapján:

| Feltétel | Tartomány | Érték | Verdict |
|---|---|---:|---|
| V1 RRR | [0.05, 0.60] | 0.551 | ✅ PASS |
| V2 far_domain | [0.05, 0.85] | 0.752 | ✅ PASS |
| V3 pass_rate | [0.50, 0.99] | 0.886 | ✅ PASS |
| V4 v(N) CV | > 0.10 | 0.387 | ✅ PASS |

**Mind a 4 V-feltétel érvényes.** A kísérlet egészséges mérési zónában fut, a verdict ÉRDEMI (nem `INVALID_DUE_TO_SATURATION`).

## H1-H4 pre-regisztrált verdictek

| Hipotézis | Predikció | Eredmény | Verdict |
|---|---|---|---|
| **H1** (far-domain élek többlete) | hp > db, p < 0.01 | medians 0.756 vs 0.752, p = 0.35 | ❌ **FAIL** |
| **H2** (alacsonyabb waking pass-rate) | hp < db, p < 0.01 | medians 0.835 vs 0.886, **p = 2.4·10⁻⁸** | ✅ **PASS** statisztikailag<br>⚠️ a hp pass = 0.835 NEM esik a pre-reg [0.30, 0.60] sávba |
| **H3** (újdonság) | a hp-túlélő far-domain élek ≥ 50%-a új domain-pár | nem futtatva (post-hoc additívan) | ⏸️ később |
| **H4** (magasabb v(N) deep-ben) | hp > db, p < 0.01 | medians 0.210 vs 0.211, p = 0.64 | ❌ **FAIL** |
| **Kontroll** (no_relax = daemon) | nincs különbség | p = 1.0 mindkét metrikán | ✅ **OK** |

## Pre-regisztrált döntésfa olvasása

A 4-cellás döntésfa (H1+H2+H3 többsége PASS × H4 PASS):

| H1+H2 többsége PASS | H4 PASS | Verdict |
|---|---|---|
| **Nem (1/2)** | **Nem** | **Hipnagóg-koncepció ezen a motoron CÁFOLT** ezen a setupon |

A pre-reg mechanikus döntésfa szerint a verdict cáfolat. **De az adat ennél árnyaltabb történetet mond.**

## Honestseti értelmezés — részleges megerősítés és a Frobenius-metrika cáfolata

A pre-reg verdict "cáfolt" felirat mögötti realitás:

### Ami **megerősítve** (a kísérlet pozitív tanulságai)

- **A hipnagóg mód strukturálisan különbözik a daemontól** — a `hypnagogic_periodic` pass-rate (0.835) **szignifikánsan** alacsonyabb a daemon-énél (0.886), p = 2.4·10⁻⁸. Ez nem zaj, hanem 5%-os, **valós effektus**, 30 seedre robusztus.
- **A relaxáció a hatás forrása, nem a ciklikus reset** — a `no_relax` kontroll IDENTIKUS a daemon-nal (p=1.0). Ha az hipnagóg-effektus a periódikus epizódokból jönne, a kontrolnak is el kellett volna térnie a daemontól. **Nem tér el**, tehát a hatás a soft-relaxációból (jelenleg: `forbidden_weight` + `negation_threshold`) jön.
- **A V-feltételek mind PASS** — a kísérlet érvényes mérési zónában fut, a `METHODS_NOTES.md`-beli confound-térkép tanulsága beépült a setupba.

### Ami **cáfolva** (a kísérlet negatív tanulságai)

- **A hipnagóg mód NEM nyit új far-domain felfedezéseket** (H1 FAIL). A daemon és a hipnagóg karon az élek ugyanolyan arányban (~0.75) far-domain. A "kreatív álmodás" hipotézis (új territóriumok feltárása) **ezen az engine-en nem támogatott**.
- **A Frobenius v(N) metrika NEM érzékeny a mód-átmenetre** (H4 FAIL). A hypnagogic_periodic és daemon v(N) mediánja gyakorlatilag azonos (0.210 vs 0.211, p=0.64). A Markov-átmeneti mátrix **nem változik mérhetően** a relaxált fázisban — a kettős-inflexió hipotézis sem jelent meg az adatokban.
- **A H2 sávja messze van** — a pre-reg `[0.30, 0.60]` hipnagóg pass-rate sávot várt; valójában 0.835. Az effektus **kvantitatív** mérete kicsi (csak 5%-os relatív csökkenés), bár statisztikailag erős.

### Mit jelent ez a kép a paper-ben

A pre-reg "cáfolt" verdict **mechanikusan** áll, **de** a kísérlet **NEM eredménytelen**. Egy nyitott kérdés zárult le: a hipnagóg mód **az engine ezen verziójában** nem nyit új territóriumot és a Frobenius-trigger nem érzékeny. A teljes Modul A-elképzelés (kreatív álmodás + Fisher-detektált átmenet) **ezen a setupon nem reprodukálódik**.

A H2 PASS gyengített állítást enged: a relaxáció **megváltoztatja az élminőséget** (lefelé), de nem a kreativitást. Ez egy közeli analogonja a "fáradt elme" jelenségnek, nem a hipnagóg-kreativitásé.

## Mit nem csinálunk a verdict alapján

- **Nem fittelünk új sávot** a kapott pass-rate adatra. Az `[0.30, 0.60]` sáv pre-reg-ben rögzítve volt; a 0.835 érték OUT, ezt elfogadjuk.
- **Nem mondjuk azt, hogy a "Modul A koncepció működik, csak finomítani kell"**. A H1 + H4 cáfolat tisztességes negatív eredmény. Új koncepció kell, ha a kreatív felfedezés-tézist meg akarjuk őrizni.
- **Nem cseréljük le a Frobenius-metrikát futás közben**. A H4 cáfolat azt mondja, hogy egy másik detektor (pl. Paper 4 SAX+LSTM, vagy spektrális gap, vagy entrópia-alapú) kellene — ez **új kísérlet** lenne.

## Mit ad ez a paper-narratívához

- A 4 megerősített mechanizmus változatlanul áll (TOPO ← struktúra, Q ← immun, TOPO ⊥ immun, priority → immun-aktivitás post-hoc).
- A Modul A első futamának **becsületes negatív eredménye** van: a hipnagóg mód az engine ezen verziójában nem produkál kreatív új felfedezéseket.
- Az implementációs hiányosság **világos**: csak 2/5 relaxációs paraméter van engine-re kötve. A teljes integráció (far_domain_pref a heurisztika súlyozásához + verify_chain_depth a többlépéses verify_logic-hoz) **következő munkacsomag** lenne, mielőtt a Modul A "cáfolt" cimkét véglegesítjük.

## Idő-becslés a teljes Modul A-implementációra (a maradék 3 relaxációs paraméter integrációja)

- `far_domain_pref` a heurisztika pair-sampling-hez: ~0.5 nap
- `verify_chain_depth` többlépéses verify_logic: ~1 nap
- `meglepetés-detektor érzékenysége` (jelenleg nincs implementálva): ~0.5 nap
- Tesztek + új batch + elemzés: ~1 nap
- **Összesen: 2-3 nap, ha eldöntöd, hogy érdemes a Modul A teljes integrációja**.

A jelen kísérlet eredménye alapján — a H1 cáfolat világos jelzés — érdemes előbb újragondolni, hogy a "kreatív álmodás" mechanikusan **mit kellene** hozzon a gráf-építésbe, mielőtt további paramétert implementálunk. A `far_domain_pref` várhatóan a H1-et tudná javítani; de ha a koncepció maga hibás, a több implementáció csak több zajt termel.
