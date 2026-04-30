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

## Idő-becslés

- Schema (emissziós napló + telemetry-bővítés) + engine (3 fázisú állapotgép, lazítási interpoláció): ~1 nap
- Frobenius v(N) számoló + trigger-modul (elsődleges + másodlagos detektor) + waking re-evaluációs hurok: ~1 nap
- Unit tesztek (mód-váltás, lazítási paraméterek, trigger-küszöb, hipnagóg napló, Frobenius számolás): ~0.5 nap
- 3-karú batch (30 seed × 3000 lépés × 3 kar) + elemzés: ~0.5–1 nap (ebből compute ~30 perc)
- **Összesen: 3–4 nap fókuszált munka, ~30 perc compute az első batch-hez.**

---

*Pre-regisztráció lezárva. Most következik a kódolás (Modul A implementáció), majd a diagnosztikai futás, majd a 30-seed batch.*
