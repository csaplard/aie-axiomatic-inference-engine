# Útiterv: matek–fizika mag + válasz + hipotézis + szabályértés

**Cél:** egy rendszer, amely **matematikát és fizikát** axióma-gráfon következtet, **magyarul válaszol**, **érti a szabályokat** (tiltás, negáció, kauzalitás), és **új hipotéziseket** javasol (discovery), emberi vagy automatikus szűréssel.

A lépések **sorban** épülnek; a kész részek a repo-ban maradnak, a következő fázisokra lehet építeni.

---

## Fázis 1 — **Szabályok láthatóvá tétele** (kész: alap)

- Regiszterből emberi olvasható összefoglaló: negációs párok, tiltott élek, axióma-lista.
- Csevegőparancsok: `/szabályok`, `/axiómák`, `/útiter`.
- Modul: `aie_knowledge.py`.

**Elfogadási kritérium:** egy új felhasználó 5 perc alatt lássa, *mik* a játékszabályok.

---

## Fázis 2 — **Válasz + következtetés összekötése** (kész: alap)

- Chat: prioritás — tanult párok → small talk → **derive_statement**.
- **`/indoklás`** — utolsó sikeres következtetés magyar magyarázata (`aie_knowledge.format_indoklas_hu`).
- Strukturális hiány esén tipp: `/status`, `/warmup`; siker után: „Részletes magyar indoklás: /indoklás”.

**Elfogadási kritérium:** tipikus fizikai/matematikai mondat → strukturált válasz vagy egyértelmű „strukturális hiány” + javasolt warmup.

---

## Fázis 3 — **Hipotézis-napló** (kész: alap)

- **`hypothesis_sync.py`** — discovery napló sorai → **`hypotheses/discovered_edges.jsonl`** (strukturált JSONL).
- Csevegő: **`/hipotézis-sync`** (ugyanaz a `--discovery-log` és `--hypotheses-jsonl`), **`/hipotézis`** — utolsó sorok a discovery fájlból.
- Kézi jegyzet: `hypotheses/journal_template.md`.

**Elfogadási kritérium:** új él felvétele nyomon követhető JSONL-ben és nyers discovery szövegben.

---

## Fázis 4 — **Regiszter bővítése (matek/fizika „zseni” tartalom)** — KÉSZ

- Új csúcsok: klasszikus mechanika, analízis, QM kulcsfogalmak — **kulcsszavak + formulák**.
- `causal_edges` finomhangolása: tényleges előfeltételek (pl. derivált → Newton, Hamilton → Schrödinger, Coulomb ↔ Gauss).
- Nyelvi axiómák: opcionális csúcsok a logikai/nyelvtani összekapcsoláshoz (`hun_subject_verb_agreement`, `hun_case_system`).

**Elfogadási kritérium:** több témakörből érkező kérdés **eléri** a megfelelő csúcsot kulcsszóval.

---

## Fázis 5 — **Önjavítás / visszacsatolás** — KÉSZ (alap)

- `source_trust` per él: `hypotheses/edge_trust.json` + csevegő **`/jó`**, **`/rossz`**, **`/trust`** (`--trust-store`).
- Policy (`discovery`): `discovery_trust_weight`, `discovery_skip_log_trust_below` — a naplózási küszöbhöz **effektív Q** = `q * (1 + weight * trust)`; nagyon negatív trustnál nincs új discovery sor.
- `hypothesis_sync` / **`/hipotézis-sync`**: JSONL sorokban **`source_trust`** mező.

**Elfogadási kritérium:** rossz hipotézis visszaszorítható anélkül, hogy a teljes gráfot törölnénk.

---

## Fázis 6 — **Külső eszközök (opcionális)** — KÉSZ (alap)

- **Telemetria → Fisher-sweep:** `tools/telemetry_fisher_sweep.py` — az AIE `Q=` idősorra csúszóablakos, egyszerűsített Fisher-trace sweep és **heurisztikus N\*** (nem a teljes Grammar Fingerprinting archívum; ahhoz külön repo).
- **HTTP API:** `aie_http_server.py` — `GET /health`, `GET /status`, `POST /chat` JSON (`process_chat_message`, REPL-parancsok nélkül).

---

## Mit *nem* ígérünk

- Nem egy **zárt LLM**; a „zseni” itt **strukturált tudás + következtetés + felfedezés**, nem végtelen természetes nyelv.
- **Új hipotézis** = **új él javaslat** a gráfon, **nem** automatikus Nobel-díj.

---

*Utolsó frissítés: a repo fejlesztésében; lépésekhez igazítsd a checklistet a PR-ekben.*
