# Hipotézis-napló (Fázis 3)

A motor **discovery** módja új éleket **hipotézisként** vehet fel (ha az immunrendszer engedi). A futás közbeni részletek a policy szerinti **`discovery_log`** fájlban vannak (pl. `discovery_log_relaxed.txt`).

**Strukturált napló:** `discovered_edges.jsonl` — előállítás:

```bash
python hypothesis_sync.py --discovery discovery_log_relaxed.txt --out hypotheses/discovered_edges.jsonl
```

vagy a csevegőben: **`/hipotézis-sync`** (ugyanazok az útvonalak, mint `--discovery-log` / `--hypotheses-jsonl`).

**Fázis 5 — trust:** `edge_trust.json` per-él érték [-1, 1]; a csevegő **`/jó`** / **`/rossz`** frissíti; a daemon policy a discovery naplót ehhez igazítja. Szinkronnál a JSONL-ben megjelenik a **`source_trust`** mező (`--trust-store`).

Sablon kézi jegyzethez: `journal_template.md`.
