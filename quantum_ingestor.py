"""
Kvantum readout (readout_raw_data) streamelése chunkokban, lokális Shannon-meta,
hash-elt lenyomat → AIE derive_statement / jelentés.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Optional, Tuple, Union

# AIE
from axiom_kernel import AxiomaticInferenceEngine, InferenceResult

# Chunkolás: alap (kímélő memóriához). „Információs sokkterápiához” lásd SHOCK_THERAPY_MAX_ROWS.
DEFAULT_MAX_ROWS_PER_CHUNK = 1000
SHOCK_THERAPY_MAX_ROWS = 500_000
DEFAULT_MAX_CHUNK_BYTES = 10 * 1024 * 1024
# Sok sor mellett a bájt-limit ne vágja ketté a chunkot:
SHOCK_THERAPY_MAX_CHUNK_BYTES = 512 * 1024 * 1024

# Hosszú kulcsszó-sor: a regiszterben lévő quantum_data_stream + born + unitary illeszkedik
CANONICAL_QUANTUM_QUERY = (
    "quantum data stream sycamore readout born rule probability measurement"
)


def qubit_width_from_filename(name: str) -> Optional[int]:
    m = re.match(r"^(\d+)q_.+", name, re.I)
    return int(m.group(1)) if m else None


def int_to_bitlist(value: int, width: int) -> List[int]:
    mask = (1 << width) - 1
    v = value & mask
    return [(v >> i) & 1 for i in range(width)]


def binary_entropy_p1(p1: float) -> float:
    if p1 <= 0.0 or p1 >= 1.0:
        return 0.0
    p0 = 1.0 - p1
    return -(p0 * math.log2(p0) + p1 * math.log2(p1))


def shannon_row_entropy(outputs: List[int], width: int) -> List[float]:
    """Soronkénti bit-entrópia (max 1 bit / sor bináris eloszlásra)."""
    out: List[float] = []
    for v in outputs:
        bits = int_to_bitlist(v, width)
        p1 = sum(bits) / len(bits)
        out.append(binary_entropy_p1(p1))
    return out


def chunk_bit_distribution(outputs: List[int], width: int) -> Tuple[float, float]:
    """Összes kimeneti bitre: p(1), H."""
    flat: List[int] = []
    for v in outputs:
        flat.extend(int_to_bitlist(v, width))
    if not flat:
        return 0.0, 0.0
    p1 = sum(flat) / len(flat)
    return p1, binary_entropy_p1(p1)


def parse_readout_lines(path: Path) -> Iterator[Tuple[int, int]]:
    with path.open(encoding="utf-8", errors="replace") as f:
        first = True
        for line in f:
            line = line.strip()
            if not line:
                continue
            if first:
                first = False
                if line.lower().startswith("input"):
                    continue
            parts = line.split()
            if len(parts) >= 2:
                yield int(parts[0]), int(parts[1])


@dataclass
class ChunkMeta:
    """Egy chunk statisztikai lenyomata (nem bitenkénti gráf-csúcs)."""

    source_file: str
    chunk_index: int
    row_start: int
    row_count: int
    qubit_width: int
    shannon_H_bits: float
    entropy_variance: float
    p1_global: float
    fingerprint_sha256: str
    approx_bytes: int = 0


def build_fingerprint_payload(meta: Dict[str, Any]) -> bytes:
    return json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fingerprint_chunk(meta_dict: Dict[str, Any]) -> str:
    h = hashlib.sha256(build_fingerprint_payload(meta_dict)).hexdigest()
    return h


@dataclass
class QuantumIngestReport:
    """Vizsgálati kimenet: batch, út, Q, javaslat (ASCII)."""

    input_batch: str
    path_axiom_ids: List[str]
    result_line: str
    q_density: float
    suggestion: str
    chunk: ChunkMeta
    inference: Union[InferenceResult, str, None] = None

    def format_report_ascii(self) -> str:
        path_s = " -> ".join(self.path_axiom_ids)
        lines = [
            f"INPUT_BATCH: {self.input_batch}",
            f"PATH: {path_s}",
            f"RESULT: {self.result_line}",
            f"Q_DENSITY: {self.q_density:.4f}",
            f"SUGGESTION: {self.suggestion}",
            "---",
            f"chunk_fp: {self.chunk.fingerprint_sha256[:16]}...",
            f"H={self.chunk.shannon_H_bits:.4f} bit/bit var_H={self.chunk.entropy_variance:.6f} p1={self.chunk.p1_global:.4f}",
        ]
        return "\n".join(lines)


def iter_raw_row_batches(
    paths: List[Path],
    *,
    max_rows: int = DEFAULT_MAX_ROWS_PER_CHUNK,
    max_bytes: int = DEFAULT_MAX_CHUNK_BYTES,
) -> Generator[Tuple[Path, int, List[Tuple[int, int]], int], None, None]:
    """
    Fájlonként, max_rows sor vagy max_bytes bájt (sorhossz összeg) után chunk.
    Vissza: (path, chunk_index, rows, row_start_global_in_file).
    """
    for path in paths:
        if not path.is_file():
            continue
        chunk: List[Tuple[int, int]] = []
        bytes_acc = 0
        row_in_file = 0
        chunk_idx = 0
        row_start = 0
        for inp, out in parse_readout_lines(path):
            line_b = len(f"{inp} {out}\n".encode("utf-8"))
            if chunk and (
                len(chunk) >= max_rows or bytes_acc + line_b > max_bytes
            ):
                yield path, chunk_idx, chunk, row_start
                chunk_idx += 1
                chunk = []
                bytes_acc = 0
                row_start = row_in_file
            chunk.append((inp, out))
            bytes_acc += line_b
            row_in_file += 1
        if chunk:
            yield path, chunk_idx, chunk, row_start


def rows_to_chunk_meta(
    path: Path,
    chunk_index: int,
    rows: List[Tuple[int, int]],
    row_start: int,
) -> ChunkMeta:
    qw = qubit_width_from_filename(path.name) or 12
    outputs = [b for _, b in rows]
    p1, H = chunk_bit_distribution(outputs, qw)
    row_H = shannon_row_entropy(outputs, qw)
    n = len(row_H)
    mean_h = sum(row_H) / n if n else 0.0
    var_h = sum((x - mean_h) ** 2 for x in row_H) / n if n else 0.0
    meta_d = {
        "file": path.name,
        "chunk": chunk_index,
        "rows": len(rows),
        "q": qw,
        "H": round(H, 8),
        "var_H": round(var_h, 8),
        "p1": round(p1, 8),
    }
    fp = fingerprint_chunk(meta_d)
    approx_b = sum(len(f"{a} {b}\n".encode("utf-8")) for a, b in rows)
    return ChunkMeta(
        source_file=str(path.name),
        chunk_index=chunk_index,
        row_start=row_start,
        row_count=len(rows),
        qubit_width=qw,
        shannon_H_bits=H,
        entropy_variance=var_h,
        p1_global=p1,
        fingerprint_sha256=fp,
        approx_bytes=approx_b,
    )


def synthetic_prompt_for_chunk(meta: ChunkMeta, batch_label: str) -> str:
    """A gráf kulcsszavait garantáló lekérdezés + opcionális hash-részlet."""
    return (
        f"{CANONICAL_QUANTUM_QUERY} chunk_{batch_label} fp_{meta.fingerprint_sha256[:12]}"
    )


def suggest_from_chunk(meta: ChunkMeta) -> str:
    """Heurisztikus szöveges javaslat (klasszikus vs. kvantum jelleg)."""
    if meta.entropy_variance < 0.001 and 0.48 < meta.p1_global < 0.52:
        return (
            "Az adatfolyam klasszikus kauzalitast nem tartalmaz. "
            "Kerem a kvantum-szimulacios backend (B) aktivalasat."
        )
    if meta.shannon_H_bits > 0.85:
        return (
            "Magas bit-szintu Shannon-entropia: a chunk illeszkedik a Born-szabaly "
            "sokasagi leirasahoz; erdemes a QM axióma-lancot tartani."
        )
    return "Chunk meta feldolgozva; tovabbi batch-ek osszevetese ajanlott."


def run_ingest_analysis(
    data_dir: Union[str, Path],
    *,
    engine: Optional[AxiomaticInferenceEngine] = None,
    max_rows: int = DEFAULT_MAX_ROWS_PER_CHUNK,
    max_bytes: int = DEFAULT_MAX_CHUNK_BYTES,
    max_chunks: Optional[int] = None,
) -> List[QuantumIngestReport]:
    """
    readout_raw_data könyvtár (vagy egy fájl) feldolgozása; chunkonként derive_statement.
    """
    data_dir = Path(data_dir)
    if data_dir.is_file():
        paths = [data_dir]
    else:
        paths = sorted(data_dir.glob("*.txt"))
    engine = engine or AxiomaticInferenceEngine(
        policy_enabled=False,
        enable_self_optimization=False,
    )
    engine.deductive_saturate()
    reports: List[QuantumIngestReport] = []
    n_done = 0
    for path, cidx, rows, rstart in iter_raw_row_batches(
        paths, max_rows=max_rows, max_bytes=max_bytes
    ):
        meta = rows_to_chunk_meta(path, cidx, rows, rstart)
        batch_label = f"{path.stem}_c{cidx}_r{rstart}_{rstart + len(rows) - 1}"
        prompt = synthetic_prompt_for_chunk(meta, batch_label)
        inf = engine.derive_statement(prompt, source_id=f"quantum:{batch_label}")
        q = engine.calculate_q()
        if isinstance(inf, InferenceResult):
            path_ids = inf.path_axiom_ids
            res = inf.verdict
        else:
            path_ids = ["(nincs ut)"]
            res = str(inf)
        sug = suggest_from_chunk(meta)
        if isinstance(inf, InferenceResult):
            res = (
                "Igazolt (A bemenet determinisztikus uniter evolucio meresebol szarmazo kvantumzaj)."
                if q >= engine.q_threshold
                else inf.verdict
            )
        reports.append(
            QuantumIngestReport(
                input_batch=batch_label,
                path_axiom_ids=path_ids,
                result_line=res,
                q_density=q,
                suggestion=sug,
                chunk=meta,
                inference=inf,
            )
        )
        n_done += 1
        if max_chunks is not None and n_done >= max_chunks:
            break
    return reports


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Sycamore readout ingest: chunkok → derive_statement. "
        "Alap: kímélő chunk; --shock = nagy max_rows (információs sokkterápia)."
    )
    ap.add_argument(
        "data_dir",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parent / "readout_raw_data",
        help="readout .txt fájl vagy könyvtár",
    )
    ap.add_argument(
        "--max-rows",
        type=int,
        default=DEFAULT_MAX_ROWS_PER_CHUNK,
        metavar="N",
        help=f"Sorok chunkonként (alap: {DEFAULT_MAX_ROWS_PER_CHUNK})",
    )
    ap.add_argument(
        "--shock",
        action="store_true",
        help=f"max_rows = {SHOCK_THERAPY_MAX_ROWS} (egy chunkban extrém sok sor)",
    )
    ap.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Legfeljebb ennyi chunk (teszteléshez)",
    )
    args = ap.parse_args()
    mr = SHOCK_THERAPY_MAX_ROWS if args.shock else args.max_rows
    mb = SHOCK_THERAPY_MAX_CHUNK_BYTES if args.shock else DEFAULT_MAX_CHUNK_BYTES
    reps = run_ingest_analysis(
        args.data_dir,
        max_rows=mr,
        max_bytes=mb,
        max_chunks=args.max_chunks,
    )
    print(f"max_rows={mr}  max_bytes={mb}  chunks={len(reps)}", flush=True)
    for r in reps:
        print(r.format_report_ascii())
        print()
