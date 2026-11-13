"""
Profile a file BEFORE it is uploaded: checksum, row counts, header, parse check.
Also converts the Excel savings tracker to CSV (Snowflake cannot read .xlsx).

Nothing here ever blocks a file. Results are logged to AUDIT.PRELOAD_CHECK_LOG
and the file is uploaded anyway ("land everything, then validate").
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from source_config import Entity


@dataclass
class Check:
    name: str          # NOT_EMPTY | SCHEMA | PARSE | ENCODING | VOLUME
    status: str        # PASS | WARN | FAIL
    detail: str


@dataclass
class Profile:
    md5: str
    size_bytes: int
    data_row_count: int          # business records (no header)
    expected_raw_rows: int       # rows Snowflake should load into RAW
    header: list[str] | None
    upload_path: Path            # file to PUT (converted CSV for Excel)
    checks: list[Check] = field(default_factory=list)


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):   # read in chunks: works for huge files
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ helpers --

def _profile_csv(raw: bytes, ent: Entity) -> tuple[int, int, list[str] | None, list[Check]]:
    checks = []
    try:
        text = raw.decode("utf-8")
        checks.append(Check("ENCODING", "PASS", "valid UTF-8"))
    except UnicodeDecodeError as e:
        text = raw.decode("utf-8", errors="replace")
        checks.append(Check("ENCODING", "WARN", f"not valid UTF-8 at byte {e.start}; Snowflake will replace bad bytes"))
    rows = list(csv.reader(io.StringIO(text), delimiter=ent.csv_delimiter or ","))
    rows = [r for r in rows if r != []]          # Snowflake ignores completely empty lines
    if not rows:
        return 0, 0, None, checks
    header = rows[0]
    return len(rows) - 1, len(rows), header, checks


def _schema_check(header: list[str] | None, expected: tuple[str, ...] | None) -> Check | None:
    if expected is None:
        return None
    if header is None:
        return Check("SCHEMA", "WARN", "no header (empty file)")
    if tuple(header) == expected:
        return Check("SCHEMA", "PASS", "header matches")
    missing = [c for c in expected if c not in header]
    extra = [c for c in header if c not in expected]
    moved = [] if missing or extra else ["column order changed"]
    parts = []
    if missing:
        parts.append("missing: " + ", ".join(missing))
    if extra:
        parts.append("new: " + ", ".join(extra))
    parts += moved
    return Check("SCHEMA", "FAIL", "; ".join(parts))


def _cell_to_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == datetime.min.time() else v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def excel_to_csv(xlsx: Path, out_dir: Path, header_first_cell: str = "Savings ID") -> tuple[Path, int, list[str]]:
    """
    Convert a hand-kept Excel sheet to CSV without "cleaning" it:
      * finds the real header row (it is not row 1: there is a title above it)
      * keeps blank rows and the TOTAL row (the audit layer flags them, dbt drops them)
      * adds _sheet_row so every CSV row can be traced back to the Excel row
      * writes dates as YYYY-MM-DD; text dates (dd/mm/yyyy) stay as typed
    """
    from openpyxl import load_workbook
    wb = load_workbook(xlsx, data_only=False, read_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header_idx = next((i for i, r in enumerate(rows) if r and r[0] == header_first_cell), None)
    if header_idx is None:
        raise ValueError(f"header row starting with '{header_first_cell}' not found in {xlsx.name}")
    header = ["_sheet_row"] + [_cell_to_text(c) for c in rows[header_idx]]
    out = out_dir / (xlsx.stem + ".csv")
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for i, r in enumerate(rows[header_idx + 1:], start=header_idx + 2):   # Excel rows are 1-based
            w.writerow([i] + [_cell_to_text(c) for c in r])
            n += 1
    return out, n, header


# --------------------------------------------------------------- main entry --

def profile_file(path: Path, ent: Entity, work_dir: Path) -> Profile:
    raw = path.read_bytes()
    md5 = hashlib.md5(raw).hexdigest()
    size = len(raw)
    checks: list[Check] = []
    header = None
    upload = path

    if ent.file_type == "CSV":
        data_rows, raw_rows, header, c = _profile_csv(raw, ent)
        checks += c
        sc = _schema_check(header, ent.expected_header)
        if sc:
            checks.append(sc)

    elif ent.file_type == "XLSX":
        try:
            upload, data_rows, header = excel_to_csv(path, work_dir)
            raw_rows = data_rows + 1
            checks.append(Check("PARSE", "PASS", f"converted to CSV ({data_rows} rows incl. blank/total rows)"))
            sc = _schema_check(header, ent.expected_header)
            if sc:
                checks.append(sc)
        except Exception as e:     # still upload the original? Snowflake cannot read xlsx -> nothing to load
            data_rows, raw_rows = 0, 0
            checks.append(Check("PARSE", "FAIL", f"Excel conversion failed: {e}"))

    elif ent.file_type == "JSON":
        try:
            doc = json.loads(raw.decode("utf-8")) if raw.strip() else None
            records = doc.get(ent.json_records_key, []) if isinstance(doc, dict) and ent.json_records_key else []
            data_rows = len(records or [])
            raw_rows = 1 if doc is not None else 0          # one document = one RAW row
            checks.append(Check("PARSE", "PASS", f"valid JSON, {data_rows} records under '{ent.json_records_key}'"))
        except Exception as e:
            data_rows, raw_rows = 0, 1
            checks.append(Check("PARSE", "FAIL", f"invalid JSON: {e}"))

    elif ent.file_type == "NDJSON":
        lines = [l for l in raw.decode("utf-8", errors="replace").splitlines() if l.strip()]
        bad = 0
        for l in lines:
            try:
                json.loads(l)
            except Exception:
                bad += 1
        data_rows = raw_rows = len(lines)
        checks.append(Check("PARSE", "PASS" if bad == 0 else "WARN", f"{len(lines)} events, {bad} unparsable lines"))

    elif ent.file_type == "XML":
        try:
            root = ET.fromstring(raw) if raw.strip() else None
            data_rows = raw_rows = len(list(root)) if root is not None else 0   # STRIP_OUTER_ELEMENT
            checks.append(Check("PARSE", "PASS", f"valid XML, {data_rows} elements under <{root.tag if root is not None else ''}>"))
        except ET.ParseError as e:
            data_rows, raw_rows = 0, 1
            checks.append(Check("PARSE", "FAIL", f"invalid XML: {e}"))

    elif ent.file_type == "PARQUET":
        try:
            import pyarrow.parquet as pq
            data_rows = raw_rows = pq.read_metadata(path).num_rows
            checks.append(Check("PARSE", "PASS", f"valid Parquet, {data_rows} rows"))
        except ImportError:
            data_rows = raw_rows = -1
            checks.append(Check("PARSE", "WARN", "pyarrow not installed: row count unknown"))
        except Exception as e:
            data_rows, raw_rows = 0, 0
            checks.append(Check("PARSE", "FAIL", f"invalid Parquet: {e}"))
    else:
        raise ValueError(f"unknown file type {ent.file_type}")

    checks.insert(0, Check("NOT_EMPTY", "PASS" if data_rows != 0 else "WARN",
                           f"{data_rows} data rows, {size} bytes"))
    return Profile(md5=md5, size_bytes=size, data_row_count=data_rows, expected_raw_rows=raw_rows,
                   header=header, upload_path=upload, checks=checks)
