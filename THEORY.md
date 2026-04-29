# Elméleti tézis és a motor viszonya

> **Megjegyzés:** ez a dokumentum az **átfogalmazott tézist** rögzíti, miután a 30-seedes kontroll-kísérletek (lásd [EXPERIMENT_IMMUNE_DENSITY.md](EXPERIMENT_IMMUNE_DENSITY.md)) mérhetően kimutatták, hogy az eredeti egy-mechanizmus kép pontatlan volt. Az átfogalmazás **adatvezérelt**, nem post-hoc retorika: a két statisztikailag megerősített mechanizmust (TOPO ← strukturáltság, Q ← immunrendszer) szétválasztottuk.

## Eredeti tézis (történeti, korrigált)

Az eredeti formuláció szerint *"a topológiai sorrend a logikai tiltások és a negációs immunrendszer miatt nem járható vissza, és ez együtt hordozza az időnyíl-metaforát"* — az immunrendszert és a topológiát egyetlen mechanizmusnak tekintette. A 4-karú strict-immune kísérlet (30 seed, 10000 lépés, két regiszter-méreten) ezt **két független mechanizmusra** bontotta szét, eltérő mérhető hatással.

## Aktuális tézis — kettő-mechanizmus kép

### Mechanizmus 1: topológiai mélység ← strukturált kauzalitás

Egy irányított axióma-gráfon, amelyben a `causal_edges` **strukturált** (pl. lánc + ágak — szakaszhomérséklet, Hamilton-formalizmus, Born-szabály konkrét logikai/matematikai sorrendje), a `think_step` heurisztikus + abduktív bővítése **emergens topológiai mélységet** hoz létre: a TOPO (leghosszabb irányított út) szignifikánsan magasabb, mint random gráfon.

- Operacionalizálva: TOPO_med(timeless 48 csúcs) = 24 vs TOPO_med(random 48 csúcs) = 16.
- Statisztikai jel: Mann-Whitney U, p = 1.1·10⁻¹¹ (egyoldali, n=30 seed).
- **Az immunrendszer aktivitása erre nincs detektálható hatással** (p > 0.2 minden összevetésen).

Ez a mechanizmus megfelel az eredeti "időnyíl-metafora" intuitív magjának: a kauzális struktúra önmagában elegendő egyirányú, mélyülő láncok kialakulásához.

### Mechanizmus 2: élsűrűség (Q) ← immunrendszer aktivitása

A `forbidden_edges` és `logical_negation_pairs` alkotta immunrendszer (operacionalizáltan: `_try_add_edge_with_reason` `forbidden` és `contradiction` rejekt-jei) **szignifikánsan csökkenti a Q-t** (élsűrűséget):

- 48-csúcsos timeless: Q_med(immun aktív) = 0.163 vs Q_med(immun nélkül) = 0.196 (~17% különbség, p = 1.2·10⁻¹¹).
- 15-csúcsos sűrű: Q_med(immun aktív) = 0.1943 vs Q_med(immun nélkül) = 0.1956 (p = 3.1·10⁻⁴).
- A hatás **a specifikusságtól független**: random pozícióba helyezett immun ugyanígy csökkenti a Q-t (timeless Q < random_immune Q, p = 1.4·10⁻¹¹).

Ez **nem volt** az eredeti tézis része; a kísérletekből bukkant elő. Az értelmezés: az immunrendszer egy **független szabályozó réteg**, amely a hálózat növekedési ütemét tartja kontroll alatt.

### A két mechanizmus független

A pre-regisztrált döntésfa 3. ágában mértük: az immun aktív (RRR>0.001 a megfelelő karokon), de a TOPO-eloszlása nem különbözik a no_immune kar TOPO-eloszlásától. A Q-eloszlások ezzel szemben szignifikánsan különböznek. Tehát:

| Hatás | TOPO | Q |
|---|:---:|:---:|
| Strukturált causal_edges hozzáadása | ✅ ↑ (p=10⁻¹¹) | ↑ kissé / nem mérve külön |
| Immun bekapcsolása | ❌ nincs hatás (p>0.2) | ✅ ↓ (p=10⁻¹¹) |

A két mechanizmus **különböző gráf-tulajdonságot ír**.

## Mi a "időnyíl-metafora" pontos státusza?

A metafora **megtartható**, de a forrását más mechanizmushoz kell rendelni:

- **Igen:** a strukturált causal_edges egyirányú, mélyülő láncokat hoz létre (TOPO-szignál). Ez emergens, nem külső paraméter.
- **Nem:** az immunrendszer **nem** építi a "időnyilat" — a kísérleti adatok ezt cáfolják. Az immunrendszer a hálózat sűrűségét szabályozza, nem az irányítottságát/mélységét.

Ez egy **elegánsabb és pontosabb** kép, mint az eredeti volt: két szétválasztott mechanizmus, mindkettő független, mindkettő statisztikailag mérhető szignifikáns hatással.

## Mit nem állít ez a dokumentum

- Nem állítja, hogy a fizikai időnyíl így keletkezik.
- Nem állítja, hogy a TOPO-jel univerzális — más típusú strukturált gráfokon (pl. random-permutált causal_edges) az effektus mértéke más lehet.
- Nem állítja, hogy az immun-Q hatás **csak** rejekciós; lehet, hogy a Q-csökkenés más másodlagos hatásokon keresztül is elérhető (pl. discovery-trust).

## Falszifikációs kapcsolatok

- A jelen tézis **2. mechanizmusa cáfolható**, ha új kísérletben az immun-Q hatás eltűnik (pl. nagyon nagy regiszteren, vagy más think_step heurisztikán). A pre-regisztrált küszöb p<0.05 minden szigorú összevetésen.
- A jelen tézis **1. mechanizmusa cáfolható**, ha új strukturált kontroll (pl. azonos él-szám, de random irányítás) is megadja a TOPO-jelet. Ez a [EXPERIMENT_IMMUNE_DENSITY.md](EXPERIMENT_IMMUNE_DENSITY.md) "opcionális következő megerősítő futás" pontja alatt szerepel.

A részletes kísérleti protokoll, pre-regisztrált küszöbök és számszerű eredmények: [EXPERIMENT_IMMUNE_DENSITY.md](EXPERIMENT_IMMUNE_DENSITY.md).

---

## Mi köthető a jelenlegi implementációhoz (operacionalizálás)

| Fogalom | A motorban megjelenő megfelelő |
|--------|--------------------------------|
| Irányított lánc | `knowledge_matrix`, `shortest_path`, `verify_logic` (tranzitív lépés) |
| „Visszafordíthatatlanság” | Nem külön modul: **`forbidden_edges`**, **`logical_negation_pairs`** + `_would_contradict_edge` — bizonyos **vissza** irányú vagy paradox él **elutasítva** (`reject=...`) |
| Információ-robbanás | Magas \(H_0\), sok chunk / bemenet; **Q** nő, ha új élek kerülnek be |
| „Idő feltalálása” | Metafora: **egyirányú követhető mélység** nő, nem `t` változó |

### Mérhető „Idő nyila” indexek (`graph_metrics.py`, telemetria, `SystemMetrics`)

| Metrika | Jelentés | Falszifikációs olvasat |
|--------|----------|-------------------------|
| **TOPO** (topológiai mélység) | Leghosszabb irányított út becslése (DAG: pontos; kör: SCC-súlyozott kondenzátum). | Ha magas entrópiájú terhelés mellett **nem** nő — a „mélyülő kauzális réteg” narratíva gyengül. |
| **RRR** (reverse rejection rate) | `reverse_rejects_contradiction / reverse_attempts`, ahol a próba: már van **j→…→i** út és **i→j** felvétele ellentmondásra fut. | Ha **oda-vissza** minden ellenállás nélkül menne — a „súrlódás” narratíva cáfolva. |
| **ASYM** (asymmetry ratio) | Azon irányított élek aránya, ahol a fordított él **nincs** meg (mindkét irány = szimmetrikus pár kiesik a számlálóból). | Irányított, egyre kevésbé „kétirányú” gráf felé **1.0** környéke (heurisztika). |

---

## Mi számít „bizonyítéknak” a szimulációban vs. mi formális matematika

- **Empirikus jel** a futásból: Q és a makro–mikro távolság viselkedése, **`hyp_edge` / `reject`** mintázat, hosszú futású **`telemetry.log`** — ezek **illeszkednek-e** ahhoz a narratívához, hogy a gráf **egyre inkább egyirányú, immunilag stabil** struktúrákat preferál.
- **Formális bizonyítás** (gráfelmélet, logika, fizikai idő): a kód **nem** váltja ki — külön matematikai / modellezési munka.

---

## Mit nem állít ez a README / a motor

- Hogy a fizikai világ időiránya **ekképp** keletkezik.
- Hogy egyetlen skalár „idő” változó **emergál** a `think_loop`-ból **definíció szerint**.

---

*Ez a fájl a kutatási irány rögzítésére szolgál; a `EXPERIMENT_TIMELESS.md` a konkrét kísérleti protokollt írja le.*
