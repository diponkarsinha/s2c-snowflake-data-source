"""
S2C synthetic data generator
============================

Builds every source file for the Source-to-Contract (S2C) project of a
fictional "Sample pharmaceutical company", in the format each real system
would deliver it:

    SAP ERP           suppliers (XML IDoc), PO items (semicolon CSV, decimal comma),
                      invoices (Parquet), cost centres (CSV), FX rates (XML)
    Ariba Sourcing    sourcing requests (paginated JSON), sourcing events + bids (JSON)
    Ariba Contracts   contracts (nested JSON), contract approvals (CSV)
    Supplier Risk     weekly risk + ESG (JSON), risk events stream (NDJSON)
    Reference files   category taxonomy (CSV), savings tracker (Excel, kept by hand)

Outputs
-------
    data/initial/...           first load (pushed on day one)
    pending/wave_XX/...        12 "drop waves" that are pushed one by one later
    answer_key/planted_issues.csv   every problem planted on purpose

Everything is fictional. The random seed is fixed, so running the script
again produces exactly the same files.

Usage
-----
    python generator/generate_data.py            # build everything
    python generator/generate_data.py --clean    # delete old output first
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
INITIAL = ROOT / "data" / "initial"
PENDING = ROOT / "pending"
ANSWER_KEY = ROOT / "answer_key"

AS_OF = date(2026, 10, 31)          # "today" for the initial load
HISTORY_START = date(2026, 1, 1)

rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# Planted issues (the answer key)
# ---------------------------------------------------------------------------

PLANTED: list[dict] = []


def plant(wave: str, entity: str, file_name: str, record_key: str, issue_type: str,
          caught_by: str, expected_check: str, description: str) -> None:
    """Record a problem we put into the data on purpose."""
    PLANTED.append({
        "issue_id": f"PI-{len(PLANTED) + 1:04d}",
        "wave": wave,
        "entity": entity,
        "file_name": file_name,
        "record_key": record_key,
        "issue_type": issue_type,
        "caught_by": caught_by,            # audit (Snowflake, pre-dbt) | dbt | stream
        "expected_check": expected_check,  # rule id that should catch it
        "description": description,
    })


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def rand_date(start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def sap_date(d: date | None) -> str:
    return d.strftime("%Y%m%d") if d else ""


def dec_comma(x: float, places: int = 2) -> str:
    """SAP style number: decimal comma, no thousands separator."""
    return f"{x:.{places}f}".replace(".", ",")


def iso(dt: datetime | date | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return dt.isoformat()


def write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding, newline="")


def write_csv(path: Path, header: list[str], rows: list[list], delimiter: str = ",") -> None:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    write_text(path, buf.getvalue())


def write_json(path: Path, obj) -> None:
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_ndjson(path: Path, events: list[dict]) -> None:
    write_text(path, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))


def xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# Reference data: countries, categories, cost centres, employees
# ---------------------------------------------------------------------------

COUNTRIES = {
    # country: (currency, cities, legal suffix)
    "DE": ("EUR", ["Frankfurt", "Munich", "Hamburg", "Berlin"], "GmbH"),
    "IE": ("EUR", ["Dublin", "Cork", "Limerick"], "Ltd"),
    "BE": ("EUR", ["Brussels", "Antwerp", "Ghent"], "NV"),
    "NL": ("EUR", ["Leiden", "Amsterdam", "Rotterdam"], "BV"),
    "FR": ("EUR", ["Lyon", "Paris", "Strasbourg"], "SA"),
    "US": ("USD", ["Boston", "New Brunswick", "Chicago", "Raleigh"], "Inc"),
    "GB": ("GBP", ["London", "Cambridge", "Manchester"], "Ltd"),
    "CH": ("CHF", ["Basel", "Zurich", "Geneva"], "AG"),
    "IN": ("INR", ["Hyderabad", "Bengaluru", "Pune"], "Pvt Ltd"),
    "CN": ("CNY", ["Shanghai", "Suzhou", "Shenzhen"], "Co Ltd"),
}
COUNTRY_WEIGHTS = {"DE": 18, "IE": 8, "BE": 7, "NL": 7, "FR": 6, "US": 22, "GB": 10, "CH": 8, "IN": 8, "CN": 6}

NAME_A = ["Alpine", "Nordic", "Helix", "Crescent", "Summit", "Bluewater", "Granite", "Meridian",
          "Quantum", "Silverline", "Evergreen", "Northstar", "Pinnacle", "Riverside", "Lumen",
          "Vertex", "Harbor", "Cobalt", "Aurora", "Keystone", "Oakridge", "Sapphire", "Tandem",
          "Unity", "Westbrook", "Zenith", "Brightpath", "Clearwater", "Ironwood", "Maple"]
NAME_B = ["Chemicals", "Labs", "Packaging", "Logistics", "Consulting", "Biotech", "Solutions",
          "Instruments", "Clinical Services", "Facilities", "IT Services", "Pharma Supplies",
          "Glassworks", "Analytics", "Freight", "Media", "Travel", "Engineering"]

# category_id, name, parent, level, unspsc, sap material group, is_active
CATEGORIES = [
    ("CAT-100", "Direct materials", None, 1, None, None, True),
    ("CAT-200", "Indirect spend", None, 1, None, None, True),
    ("CAT-110", "Raw materials", "CAT-100", 2, None, None, True),
    ("CAT-120", "Packaging", "CAT-100", 2, None, None, True),
    ("CAT-130", "Lab supplies", "CAT-100", 2, None, None, True),
    ("CAT-210", "IT and software", "CAT-200", 2, None, None, True),
    ("CAT-220", "Professional services", "CAT-200", 2, None, None, True),
    ("CAT-230", "Facilities", "CAT-200", 2, None, None, True),
    ("CAT-240", "Clinical services", "CAT-200", 2, None, None, True),
    ("CAT-250", "Logistics", "CAT-200", 2, None, None, True),
    ("CAT-111", "Active pharmaceutical ingredients", "CAT-110", 3, "12352100", "RM-API", True),
    ("CAT-112", "Excipients", "CAT-110", 3, "12352200", "RM-EXC", True),
    ("CAT-121", "Primary packaging (vials, blisters)", "CAT-120", 3, "24112400", "PK-PRI", True),
    ("CAT-122", "Secondary packaging (cartons, labels)", "CAT-120", 3, "24121500", "PK-SEC", True),
    ("CAT-131", "Lab consumables", "CAT-130", 3, "41121500", "LB-CON", True),
    ("CAT-132", "Lab equipment", "CAT-130", 3, "41100000", "LB-EQP", True),
    ("CAT-211", "Software licences", "CAT-210", 3, "43230000", "IT-SWL", True),
    ("CAT-212", "IT hardware", "CAT-210", 3, "43210000", "IT-HW", True),
    ("CAT-221", "Management consulting", "CAT-220", 3, "80101500", "PS-CON", True),
    ("CAT-222", "Legal services", "CAT-220", 3, "80121600", "PS-LEG", True),
    ("CAT-231", "Cleaning and maintenance", "CAT-230", 3, "76110000", "FM-CLN", True),
    ("CAT-241", "Clinical trial services (CRO)", "CAT-240", 3, "85101700", "CL-CRO", True),
    ("CAT-251", "Cold-chain freight", "CAT-250", 3, "78101800", "LG-CCF", True),
    # inactive categories that are still used on POs (planted)
    ("CAT-123", "Printed leaflets (retired)", "CAT-120", 3, "55101500", "PK-LFL", False),
    ("CAT-213", "On-premise servers (retired)", "CAT-210", 3, "43211500", "IT-SRV", False),
]
LEAF_CATS = [c for c in CATEGORIES if c[3] == 3 and c[6]]
INACTIVE_CATS = [c for c in CATEGORIES if c[3] == 3 and not c[6]]
CAT_BY_ID = {c[0]: c for c in CATEGORIES}
PRICE_RANGE = {  # unit price range per material group
    "RM-API": (200, 4000), "RM-EXC": (5, 120), "PK-PRI": (0.2, 3), "PK-SEC": (0.05, 1.5),
    "LB-CON": (2, 80), "LB-EQP": (800, 25000), "IT-SWL": (50, 900), "IT-HW": (300, 3000),
    "PS-CON": (900, 2200), "PS-LEG": (250, 650), "FM-CLN": (40, 400), "CL-CRO": (5000, 60000),
    "LG-CCF": (150, 2500), "PK-LFL": (0.02, 0.4), "IT-SRV": (2000, 9000),
}
UOM = {"RM-API": "KG", "RM-EXC": "KG", "PK-PRI": "EA", "PK-SEC": "EA", "LB-CON": "BOX",
       "LB-EQP": "EA", "IT-SWL": "LIC", "IT-HW": "EA", "PS-CON": "DAY", "PS-LEG": "HR",
       "FM-CLN": "SRV", "CL-CRO": "MS", "LG-CCF": "SHP", "PK-LFL": "EA", "IT-SRV": "EA"}

BUSINESS_UNITS = ["Pharmaceuticals", "MedTech", "Consumer Health", "R&D", "Corporate"]
COMPANY_CODES = {"Pharmaceuticals": "1000", "MedTech": "2000", "Consumer Health": "3000",
                 "R&D": "4000", "Corporate": "5000"}

FIRST = ["Anna", "Ben", "Clara", "David", "Eva", "Felix", "Grace", "Hugo", "Ines", "Jonas",
         "Kara", "Liam", "Mila", "Noah", "Olga", "Paul", "Quinn", "Rosa", "Sam", "Tara",
         "Uma", "Victor", "Wen", "Ximena", "Yusuf", "Zoe", "Arjun", "Bea", "Carlos", "Dana"]
LAST = ["Novak", "Schmidt", "Murphy", "Janssen", "Dubois", "Miller", "Patel", "Chen", "Rossi",
        "Kowalski", "Svoboda", "Brown", "Garcia", "Larsen", "Meyer", "Okafor", "Silva", "Weber"]


@dataclass
class Employee:
    emp_id: str
    name: str
    email: str
    manager_id: str | None
    title: str


def build_employees() -> list[Employee]:
    """Procurement org: CPO -> 4 heads -> 8 managers -> 17 buyers (for recursive CTEs)."""
    emps: list[Employee] = []
    names = rng.sample([(f, l) for f in FIRST for l in LAST], 30)

    def mk(i, title, mgr):
        f, l = names[i]
        e = Employee(f"E{i + 1:03d}", f"{f} {l}", f"{f.lower()}.{l.lower()}@samplepharma.example", mgr, title)
        emps.append(e)
        return e

    cpo = mk(0, "Chief Procurement Officer", None)
    heads = [mk(i, "Head of Category", cpo.emp_id) for i in range(1, 5)]
    mgrs = [mk(i, "Category Manager", heads[(i - 5) % 4].emp_id) for i in range(5, 13)]
    for i in range(13, 30):
        mk(i, "Buyer", mgrs[(i - 13) % 8].emp_id)
    return emps


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

@dataclass
class Supplier:
    lifnr: str
    ariba_id: str
    name: str
    country: str
    city: str
    vat: str
    currency: str
    blocked: bool = False
    created: date = HISTORY_START
    updated: date = HISTORY_START
    iban: str = ""
    bank_key: str = ""
    duns: str = ""
    is_duplicate_of: str | None = None
    account_group: str = "KRED"


def build_suppliers(n: int = 200) -> list[Supplier]:
    sups: list[Supplier] = []
    used_names: set[str] = set()
    countries = list(COUNTRY_WEIGHTS)
    weights = list(COUNTRY_WEIGHTS.values())
    for i in range(n):
        c = rng.choices(countries, weights)[0]
        cur, cities, suffix = COUNTRIES[c]
        while True:
            nm = f"{rng.choice(NAME_A)} {rng.choice(NAME_B)} {suffix}"
            if nm not in used_names:
                used_names.add(nm)
                break
        created = rand_date(date(2015, 1, 1), date(2025, 12, 31))
        s = Supplier(
            lifnr=f"{100001 + i:010d}",            # SAP keeps leading zeros
            ariba_id=f"S{2000001 + i}",
            name=nm, country=c, city=rng.choice(cities),
            vat=f"{c}{rng.randint(100000000, 999999999)}",
            currency=cur, created=created,
            updated=rand_date(created, AS_OF),
            iban=f"{c}{rng.randint(10, 99)}{rng.randint(10**15, 10**16 - 1)}",
            bank_key=str(rng.randint(10000000, 99999999)),
            duns=str(rng.randint(100000000, 999999999)),
        )
        sups.append(s)
    return sups


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

@dataclass
class World:
    employees: list[Employee] = field(default_factory=list)
    suppliers: list[Supplier] = field(default_factory=list)
    cost_centers: list[dict] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    contracts: list[dict] = field(default_factory=list)
    po_lines: list[dict] = field(default_factory=list)
    invoices: list[dict] = field(default_factory=list)
    risk: dict = field(default_factory=dict)          # vat -> current score
    savings: list[dict] = field(default_factory=list)
    next_po: int = 4500000001
    next_belnr: int = 5100000001
    next_event_seq: int = 1


W = World()


# ---------- SAP: suppliers (XML IDoc CREMAS05) ------------------------------

PO_HEADER = ["EBELN", "EBELP", "BUKRS", "LIFNR", "BEDAT", "MATKL", "TXZ01", "MENGE", "MEINS",
             "NETPR", "PEINH", "NETWR", "WAERS", "KOSTL", "KONNR", "LOEKZ", "AEDAT"]


def supplier_xml(sups: list[Supplier], docnum_start: int = 1) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<CREMAS05>"]
    for i, s in enumerate(sups):
        city = "" if (s.lifnr.endswith("7") and not s.is_duplicate_of) else s.city   # some empty tags
        parts.append(
            f'  <IDOC BEGIN="1">\n'
            f'    <EDI_DC40 SEGMENT="1"><DOCNUM>{docnum_start + i:016d}</DOCNUM><MESTYP>CREMAS</MESTYP>'
            f'<CREDAT>{sap_date(s.updated)}</CREDAT></EDI_DC40>\n'
            f'    <E1LFA1M SEGMENT="1">\n'
            f'      <LIFNR>{s.lifnr}</LIFNR>\n'
            f'      <NAME1>{xml_escape(s.name)}</NAME1>\n'
            f'      <LAND1>{s.country}</LAND1>\n'
            f'      <ORT01>{xml_escape(city)}</ORT01>\n'
            f'      <STCEG>{s.vat}</STCEG>\n'
            f'      <KTOKK>{s.account_group}</KTOKK>\n'
            f'      <SPERR>{"X" if s.blocked else ""}</SPERR>\n'
            f'      <ERDAT>{sap_date(s.created)}</ERDAT>\n'
            f'      <UPDAT>{sap_date(s.updated)}</UPDAT>\n'
            f'      <E1LFBKM SEGMENT="1"><BANKS>{s.country}</BANKS><BANKL>{s.bank_key}</BANKL>'
            f'<IBAN>{s.iban}</IBAN></E1LFBKM>\n'
            f'    </E1LFA1M>\n'
            f'  </IDOC>'
        )
    parts.append("</CREMAS05>")
    return "\n".join(parts) + "\n"


# ---------- SAP: cost centres ------------------------------------------------

def build_cost_centers() -> list[dict]:
    ccs = []
    names = ["Plant Operations", "Quality Control", "Packaging Line", "R&D Biology", "R&D Chemistry",
             "Clinical Operations", "IT Infrastructure", "Digital", "Finance", "Legal",
             "Facilities Mgmt", "Supply Chain", "Marketing", "Regulatory Affairs", "HR",
             "Medical Affairs", "Warehouse", "Procurement", "Data & Analytics", "Sustainability"]
    for i, nm in enumerate(names):
        bu = BUSINESS_UNITS[i % len(BUSINESS_UNITS)]
        closed = i in (4, 11, 16)
        ccs.append({
            "kostl": f"{(i + 1) * 1000 + 100:010d}",
            "kokrs": "SP01",
            "bukrs": COMPANY_CODES[bu],
            "cost_center_name": nm,
            "business_unit": bu,
            "responsible": rng.choice(W.employees).name,
            "valid_from": "2015-01-01",
            "valid_to": "2026-06-30" if closed else "9999-12-31",
            "updated_at": "2026-07-01T06:00:00Z" if closed else "2025-01-05T06:00:00Z",
            "closed": closed,
        })
    return ccs


# ---------- Ariba: sourcing requests, events, bids ---------------------------

REQ_STATUS_FLOW = ["New", "In Review", "Sourcing", "Awarded", "Cancelled"]


def build_requests(n: int = 300) -> list[dict]:
    reqs = []
    for i in range(n):
        cat = rng.choice(LEAF_CATS)
        created = datetime.combine(rand_date(date(2025, 11, 1), date(2026, 10, 15)),
                                   datetime.min.time()) + timedelta(hours=rng.randint(7, 18))
        requester = rng.choice(W.employees)
        bu = rng.choice(BUSINESS_UNITS)
        reqs.append({
            "request_id": f"REQ{1001001 + i}",
            "short_description": f"{cat[1]} for {bu}",
            "category_id": cat[0],
            "business_unit": bu,
            "estimated_value": rng.randint(5, 900) * 1000,
            "currency": "EUR",
            "requested_by": {"name": requester.name, "email": requester.email},
            "status": "New",
            "created_at": created,
            "updated_at": created,
            "sla_due_date": (created + timedelta(days=45)).date(),
            "_event": None,
        })
    return reqs


def build_events_and_bids() -> None:
    """180 sourcing events linked to requests, each with bids from Ariba suppliers."""
    reqs = rng.sample(W.requests, 180)
    base_sups = [s for s in W.suppliers if not s.is_duplicate_of]
    for r in reqs:
        cat_id = r["category_id"]
        open_dt = r["created_at"] + timedelta(days=rng.randint(3, 20))
        close_dt = open_dt + timedelta(days=rng.randint(7, 30))
        status = "Completed" if close_dt.date() < AS_OF - timedelta(days=10) else rng.choice(["Open", "Closed"])
        if rng.random() < 0.05:
            status = "Cancelled"
        n_bids = 1 if rng.random() < 0.12 else rng.randint(2, 6)       # ~12% single-source
        bidders = rng.sample(base_sups, n_bids)
        baseline = r["estimated_value"] * rng.uniform(0.9, 1.3)
        bids = []
        for rnd in (1, 2) if n_bids > 2 else (1,):
            for b in bidders:
                amt = baseline * rng.uniform(0.72, 1.05) * (0.97 if rnd == 2 else 1)
                bids.append({
                    "bidId": f"BID-{len(bids) + 1:03d}",
                    "round": rnd,
                    "supplier": {"aribaId": b.ariba_id, "name": b.name, "vatNumber": b.vat},
                    "bidAmount": round(amt, 2),
                    "currency": "EUR",
                    "submittedAt": iso(open_dt + timedelta(days=rng.randint(1, 6), hours=rng.randint(0, 9))),
                })
        last_round = max(b["round"] for b in bids)
        best = min((b for b in bids if b["round"] == last_round), key=lambda b: b["bidAmount"])
        award_dt = close_dt + timedelta(days=rng.randint(2, 12)) if status == "Completed" else None
        ev_id = f"Doc{6100000 + W.next_event_seq}"
        W.next_event_seq += 1
        owner = rng.choice([e for e in W.employees if e.title in ("Buyer", "Category Manager")])
        ev = {
            "eventId": ev_id,
            "title": f"{CAT_BY_ID[cat_id][1]} - {r['business_unit']} {open_dt.year}",
            "eventType": rng.choice(["RFP", "RFQ", "RFQ", "RFI", "Auction"]),
            "status": status,
            "request": {"requestId": r["request_id"]},
            "category": {"id": cat_id, "name": CAT_BY_ID[cat_id][1]},
            "owner": {"name": owner.name, "email": owner.email},
            "createdDate": iso(open_dt - timedelta(days=2)),
            "openDate": iso(open_dt),
            "closeDate": iso(close_dt),
            "awardDate": iso(award_dt) if award_dt else None,
            "baselineSpend": {"amount": round(baseline, 2), "currency": "EUR"},
            "bids": bids,
            "award": ({"aribaSupplierId": best["supplier"]["aribaId"], "awardedAmount": best["bidAmount"]}
                      if status == "Completed" else None),
            "updatedAt": iso((award_dt or close_dt) + timedelta(hours=3)),
        }
        r["_event"] = ev_id
        r["status"] = {"Completed": "Awarded", "Cancelled": "Cancelled"}.get(status, "Sourcing")
        r["updated_at"] = (award_dt or open_dt) + timedelta(hours=2)
        W.events.append(ev)
    # requests never sourced
    for r in W.requests:
        if r["_event"] is None:
            r["status"] = rng.choice(["New", "In Review", "In Review", "Cancelled"])
            r["updated_at"] = r["created_at"] + timedelta(days=rng.randint(0, 20))


# ---------- Ariba: contracts --------------------------------------------------

def build_contracts() -> None:
    completed = [e for e in W.events if e["status"] == "Completed"]
    sup_by_ariba = {s.ariba_id: s for s in W.suppliers}
    base_sups = [s for s in W.suppliers if not s.is_duplicate_of]
    seq = 1000001
    sources = [("event", e) for e in completed] + [("direct", None)] * 110
    for kind, ev in sources:
        if kind == "event":
            sup = sup_by_ariba[ev["award"]["aribaSupplierId"]]
            cat_id = ev["category"]["id"]
            start = datetime.fromisoformat(ev["awardDate"].replace("Z", "")).date() + timedelta(days=rng.randint(5, 30))
            value = ev["award"]["awardedAmount"]
            event_id = ev["eventId"]
        else:
            sup = rng.choice(base_sups)
            cat_id = rng.choice(LEAF_CATS)[0]
            start = rand_date(date(2023, 1, 1), date(2026, 9, 30))
            value = rng.randint(20, 2500) * 1000
            event_id = None
        end = start + timedelta(days=365 * rng.choice([1, 2, 3]) - 1)
        signed = start - timedelta(days=rng.randint(1, 25))
        status = "Active" if start <= AS_OF <= end else ("Expired" if end < AS_OF else "Draft")
        matkl = CAT_BY_ID[cat_id][5]
        lo, hi = PRICE_RANGE[matkl]
        owner = rng.choice([e for e in W.employees if e.title in ("Buyer", "Category Manager")])
        c = {
            "contractId": f"CW{seq}",
            "title": f"{CAT_BY_ID[cat_id][1]} agreement - {sup.name}",
            "supplier": {"aribaId": sup.ariba_id, "name": sup.name, "vatNumber": sup.vat},
            "categoryId": cat_id,
            "eventId": event_id,
            "value": {"amount": round(value, 2), "currency": "EUR"},
            "term": {
                "startDate": start.isoformat(), "endDate": end.isoformat(),
                "signedDate": signed.isoformat(), "noticePeriodDays": rng.choice([30, 60, 90]),
                "autoRenew": rng.choice([True, False, "Y", "N", "true"]),   # mixed types on purpose
            },
            "status": status,
            "owner": {"name": owner.name, "email": owner.email},
            "isDeleted": False,
            "lastStatusChangeAt": iso(datetime.combine(min(AS_OF, max(start, signed)), datetime.min.time())
                                      + timedelta(hours=9)),
            "lineItems": [{
                "lineNo": 10, "materialGroup": matkl, "description": CAT_BY_ID[cat_id][1],
                "unitPrice": round(rng.uniform(lo, hi), 2), "uom": UOM[matkl],
            }],
            "amendments": [],
        }
        for a in range(rng.choice([0, 0, 0, 1, 2])):
            c["amendments"].append({
                "amendmentId": f"{c['contractId']}-A{a + 1}",
                "effectiveDate": (start + timedelta(days=90 * (a + 1))).isoformat(),
                "valueChange": round(value * rng.uniform(0.02, 0.15), 2),
                "reason": rng.choice(["Volume increase", "Price indexation", "Scope extension"]),
            })
        c["_sup"] = sup
        W.contracts.append(c)
        seq += 1

    f = "ariba_contracts_20261031.json"
    # contract ends before it starts
    for c in rng.sample(W.contracts, 3):
        c["term"]["endDate"], c["term"]["startDate"] = c["term"]["startDate"], c["term"]["endDate"]
        plant("initial", "ariba_contracts/contracts", f, c["contractId"], "end_before_start", "dbt",
              "DBT: fct_contract end_date after start_date", "Contract end date is before its start date")
    # signed after start
    for c in rng.sample(W.contracts, 4):
        sd = date.fromisoformat(c["term"]["startDate"])
        c["term"]["signedDate"] = (sd + timedelta(days=rng.randint(3, 40))).isoformat()
        plant("initial", "ariba_contracts/contracts", f, c["contractId"], "signed_after_start", "dbt",
              "DBT: signed_date on or before start_date", "Contract signed after it started")
    # unknown Ariba suppliers (do not exist in SAP)
    for c in rng.sample(W.contracts, 4):
        fake = f"S{2999001 + len(PLANTED)}"
        c["supplier"] = {"aribaId": fake, "name": f"{rng.choice(NAME_A)} Trading Ltd", "vatNumber": f"GB{rng.randint(100000000, 999999999)}"}
        plant("initial", "ariba_contracts/contracts", f, c["contractId"], "supplier_not_in_sap", "dbt",
              "DBT: every contract maps to a SAP supplier", "Ariba supplier with no SAP vendor (no VAT match)")
    # overlapping active contracts: same supplier + category
    for c in rng.sample([x for x in W.contracts if x["status"] == "Active"], 5):
        dup = json.loads(json.dumps({k: v for k, v in c.items() if k != "_sup"}))
        dup["contractId"] = f"CW{seq}"
        seq += 1
        sd = date.fromisoformat(c["term"]["startDate"])
        dup["term"]["startDate"] = (sd + timedelta(days=60)).isoformat()
        dup["term"]["signedDate"] = (sd + timedelta(days=50)).isoformat()
        dup["eventId"] = None
        dup["title"] += " (renewal)"
        dup["_sup"] = c["_sup"]
        W.contracts.append(dup)
        plant("initial", "ariba_contracts/contracts", f, dup["contractId"], "overlapping_contract", "dbt",
              "SQL: overlapping contracts per supplier + category",
              f"Overlaps {c['contractId']} for the same supplier and category")
    # soft deletes
    for c in rng.sample(W.contracts, 5):
        c["isDeleted"] = True
        plant("initial", "ariba_contracts/contracts", f, c["contractId"], "soft_delete", "dbt",
              "DBT: exclude soft-deleted contracts", "Contract flagged isDeleted = true")
    # completed events with no award date
    for ev in rng.sample([e for e in W.events if e["status"] == "Completed"], 5):
        ev["awardDate"] = None
        plant("initial", "ariba_sourcing/events", "ariba_sourcing_events_20261031.json", ev["eventId"],
              "completed_no_award_date", "dbt", "DBT: completed event has award date",
              "Completed sourcing event has no awardDate")
    # unknown category on events
    for ev in rng.sample(W.events, 3):
        ev["category"] = {"id": "CAT-999", "name": "Unmapped"}
        plant("initial", "ariba_sourcing/events", "ariba_sourcing_events_20261031.json", ev["eventId"],
              "unknown_category", "dbt", "DBT: relationships category_id", "Event category not in taxonomy")
    # duplicated bid rows (same bid submitted twice)
    for ev in rng.sample([e for e in W.events if len(e["bids"]) > 1], 4):
        ev["bids"].append(dict(ev["bids"][0]))
        plant("initial", "ariba_sourcing/events", "ariba_sourcing_events_20261031.json",
              f"{ev['eventId']}|{ev['bids'][0]['bidId']}", "duplicate_bid", "dbt",
              "SQL: dedup bids after FLATTEN", "Same bid appears twice in the bids array")


def build_approvals() -> list[list]:
    """One row per approval step. approver -> manager gives a recursive chain."""
    emp = {e.emp_id: e for e in W.employees}
    rows = []
    for c in W.contracts:
        first = rng.choice([e for e in W.employees if e.title == "Buyer"])
        value = c["value"]["amount"]
        steps = 1 if value < 100000 else (2 if value < 1000000 else 3)
        cur = first
        signed = date.fromisoformat(c["term"]["signedDate"])
        for s in range(1, steps + 1):
            decided = signed - timedelta(days=(steps - s + 1) * rng.randint(1, 4))
            rows.append([f"APR-{len(rows) + 1:05d}", c["contractId"], s, cur.emp_id, cur.name, cur.email,
                         cur.manager_id or "", cur.title, "Approved", f"{decided.isoformat()}T10:00:00Z"])
            if cur.manager_id:
                cur = emp[cur.manager_id]
    return rows


# ---------- SAP: purchase orders ---------------------------------------------

def active_contract_for(sup: Supplier, matkl: str, on: date) -> dict | None:
    for c in W.contracts:
        if c.get("_sup") is sup and CAT_BY_ID[c["categoryId"]][5] == matkl and not c["isDeleted"]:
            try:
                sd, ed = date.fromisoformat(c["term"]["startDate"]), date.fromisoformat(c["term"]["endDate"])
            except ValueError:
                continue
            if sd <= on <= ed:
                return c
    return None


def make_po(bedat: date, sup: Supplier | None = None, n_lines: int | None = None,
            matkl_override: str | None = None) -> list[dict]:
    """Create one purchase order with 1-4 lines."""
    base_sups = [s for s in W.suppliers if not s.blocked]
    sup = sup or rng.choice(base_sups)
    ebeln = str(W.next_po)
    W.next_po += 1
    bu = rng.choice(BUSINESS_UNITS)
    open_ccs = [c for c in W.cost_centers if not c["closed"] or bedat <= date(2026, 6, 30)]
    kostl = rng.choice(open_ccs)["kostl"]
    lines = []
    # favour categories where the supplier has a contract
    sup_contracts = [c for c in W.contracts if c.get("_sup") is sup and not c["isDeleted"]]
    for i in range(n_lines or rng.choice([1, 1, 2, 2, 3, 4])):
        if matkl_override:
            matkl = matkl_override
        elif sup_contracts and rng.random() < 0.7:
            matkl = CAT_BY_ID[rng.choice(sup_contracts)["categoryId"]][5]
        else:
            matkl = rng.choice(LEAF_CATS)[5]
        lo, hi = PRICE_RANGE[matkl]
        contract = active_contract_for(sup, matkl, bedat)
        netpr = contract["lineItems"][0]["unitPrice"] if contract and rng.random() < 0.8 else round(rng.uniform(lo, hi), 2)
        menge = rng.randint(1, 40) if hi > 1000 else rng.randint(10, 2000)
        cur = sup.currency if rng.random() < 0.85 else "EUR"
        lines.append({
            "EBELN": ebeln, "EBELP": f"{(i + 1) * 10:05d}", "BUKRS": COMPANY_CODES[bu], "LIFNR": sup.lifnr,
            "BEDAT": bedat, "MATKL": matkl,
            "TXZ01": f"{CAT_BY_ID[[c for c in CATEGORIES if c[5] == matkl][0][0]][1]}",
            "MENGE": float(menge), "MEINS": UOM[matkl], "NETPR": netpr, "PEINH": 1,
            "NETWR": round(menge * netpr, 2), "WAERS": cur, "KOSTL": kostl,
            "KONNR": contract["contractId"] if contract and rng.random() < 0.85 else "",
            "LOEKZ": "", "AEDAT": bedat + timedelta(days=rng.choice([0, 0, 0, 1, 3])),
        })
    W.po_lines.extend(lines)
    return lines


def po_row(l: dict) -> list:
    return [l["EBELN"], l["EBELP"], l["BUKRS"], l["LIFNR"], sap_date(l["BEDAT"]), l["MATKL"], l["TXZ01"],
            dec_comma(l["MENGE"], 3), l["MEINS"], dec_comma(l["NETPR"]), str(l["PEINH"]),
            dec_comma(l["NETWR"]), l["WAERS"], l["KOSTL"], l["KONNR"], l["LOEKZ"], sap_date(l["AEDAT"])]


def po_key(l: dict) -> str:
    return f"{l['EBELN']}-{l['EBELP']}"


def build_initial_pos(n_pos: int = 1500) -> list[dict]:
    lines: list[dict] = []
    for _ in range(n_pos):
        lines += make_po(rand_date(HISTORY_START, date(2026, 10, 30)))
    lines.sort(key=lambda l: (l["BEDAT"], l["EBELN"], l["EBELP"]))
    f = "sap_po_items_ekpo_20261031.csv"
    # POs to blocked suppliers
    blocked = [s for s in W.suppliers if s.blocked]
    for s in blocked[:5]:
        for l in make_po(rand_date(date(2026, 6, 1), date(2026, 10, 30)), sup=s, n_lines=1):
            lines.append(l)
            plant("initial", "sap/po_items", f, po_key(l), "po_to_blocked_supplier", "dbt",
                  "DBT: no PO to a blocked supplier", f"Supplier {s.lifnr} is blocked (SPERR = X)")
    # POs charged to closed cost centres
    closed = [c for c in W.cost_centers if c["closed"]]
    for l in rng.sample([x for x in lines if x["BEDAT"] > date(2026, 7, 5)], 6):
        l["KOSTL"] = rng.choice(closed)["kostl"]
        plant("initial", "sap/po_items", f, po_key(l), "closed_cost_center", "dbt",
              "DBT: PO not charged to a closed cost centre", "Cost centre closed on 2026-06-30")
    # NETWR != MENGE x NETPR
    for l in rng.sample(lines, 4):
        l["NETWR"] = round(l["NETWR"] * rng.choice([0.9, 1.1, 10]), 2)
        plant("initial", "sap/po_items", f, po_key(l), "netwr_mismatch", "audit",
              "AUD-R05", "NETWR is not MENGE x NETPR (±1%)")
    # inactive category used
    for l in make_po(date(2026, 9, 15), n_lines=2, matkl_override=INACTIVE_CATS[0][5]) + \
             make_po(date(2026, 8, 3), n_lines=1, matkl_override=INACTIVE_CATS[1][5]):
        lines.append(l)
        plant("initial", "sap/po_items", f, po_key(l), "inactive_category", "dbt",
              "DBT: category active for material group", f"Material group {l['MATKL']} maps to an inactive category")
    # unknown material group
    for l in rng.sample(lines, 3):
        l["MATKL"] = "ZZ-MISC"
        plant("initial", "sap/po_items", f, po_key(l), "unknown_material_group", "dbt",
              "DBT: relationships material group -> category", "Material group not in taxonomy")
    # deletion flag
    for l in rng.sample(lines, 20):
        l["LOEKZ"] = "L"
    plant("initial", "sap/po_items", f, "(20 lines)", "deletion_flag", "dbt",
          "DBT: keep and flag deleted PO lines", "20 PO lines carry LOEKZ = L (deleted in SAP)")
    # trailing spaces in text
    for l in rng.sample(lines, 10):
        l["TXZ01"] = l["TXZ01"] + "   "
    return lines


# ---------- SAP: invoices (Parquet) ------------------------------------------

def make_invoice_lines(po_lines: list[dict], post_from: date, post_to: date | None = None) -> list[dict]:
    """Group PO lines by PO, one invoice document per PO."""
    out = []
    by_po: dict[str, list[dict]] = {}
    for l in po_lines:
        by_po.setdefault(l["EBELN"], []).append(l)
    for ebeln, lines in by_po.items():
        belnr = str(W.next_belnr)
        W.next_belnr += 1
        bldat = max(post_from, lines[0]["BEDAT"] + timedelta(days=rng.randint(5, 40)))
        if post_to:
            bldat = min(bldat, post_to)
        budat = bldat + timedelta(days=rng.randint(0, 3))
        for j, l in enumerate(lines):
            out.append({
                "BELNR": belnr, "GJAHR": budat.year, "BUZEI": j + 1, "BLDAT": bldat, "BUDAT": budat,
                "CPUDT": budat, "LIFNR": l["LIFNR"], "EBELN": l["EBELN"], "EBELP": l["EBELP"],
                "MENGE": l["MENGE"], "WRBTR": round(l["MENGE"] * l["NETPR"], 2), "WAERS": l["WAERS"],
                "SHKZG": "S", "XBLNR": f"INV-{rng.randint(10000, 99999)}", "STBLG": None,
            })
    return out


def inv_key(i: dict) -> str:
    return f"{i['BELNR']}-{i['GJAHR']}-{i['BUZEI']}"


def build_initial_invoices(lines: list[dict]) -> list[dict]:
    eligible = [l for l in lines if l["BEDAT"] < date(2026, 10, 1) and l["LOEKZ"] == ""]
    invoiced = rng.sample(eligible, int(len(eligible) * 0.85))
    invs = make_invoice_lines(invoiced, HISTORY_START, AS_OF)
    f = "sap_invoices_rseg_20261031.parquet"
    by_key = {(l["EBELN"], l["EBELP"]): l for l in lines}
    # price above PO / contract price
    for i in rng.sample(invs, 20):
        i["WRBTR"] = round(i["WRBTR"] * rng.uniform(1.03, 1.12), 2)
        plant("initial", "sap/invoices", f, inv_key(i), "price_variance", "dbt",
              "KPI: invoice price variance", "Invoice unit price above PO price")
    # invoiced quantity above ordered quantity
    for i in rng.sample(invs, 6):
        i["MENGE"] = i["MENGE"] + rng.randint(1, 20)
        plant("initial", "sap/invoices", f, inv_key(i), "qty_above_po", "dbt",
              "DBT: invoiced quantity <= ordered quantity", "Invoiced quantity exceeds PO quantity")
    # orphan invoices (PO does not exist)
    for i in rng.sample(invs, 5):
        i["EBELN"] = str(4590000000 + rng.randint(1, 9999))
        plant("initial", "sap/invoices", f, inv_key(i), "orphan_invoice", "dbt",
              "DBT: every invoice line has a PO line", "Invoice references a PO that does not exist")
    # invoice on a deleted PO line
    deleted = [l for l in lines if l["LOEKZ"] == "L"][:3]
    for l in deleted:
        x = make_invoice_lines([l], l["BEDAT"] + timedelta(days=10), AS_OF)[0]
        invs.append(x)
        plant("initial", "sap/invoices", f, inv_key(x), "invoice_on_deleted_po", "dbt",
              "DBT: no invoice on a deleted PO line", "PO line is flagged deleted (LOEKZ = L)")
    # credit memos (negative amounts)
    for i in rng.sample(invs, 15):
        cm = dict(i)
        cm["BELNR"] = str(W.next_belnr); W.next_belnr += 1
        cm["BUZEI"] = 1
        cm["BUDAT"] = cm["CPUDT"] = min(i["BUDAT"] + timedelta(days=rng.randint(5, 30)), AS_OF)
        cm["MENGE"] = -min(i["MENGE"], rng.randint(1, 10))
        cm["WRBTR"] = round(-abs(i["WRBTR"]) * rng.uniform(0.05, 0.3), 2)
        cm["SHKZG"] = "H"
        cm["XBLNR"] = f"CM-{i['XBLNR']}"
        invs.append(cm)
        plant("initial", "sap/invoices", f, inv_key(cm), "credit_memo", "dbt",
              "DBT: credit memos reduce spend", "Negative invoice (credit memo, SHKZG = H)")
    # reversals: full negative copy pointing to the original
    for i in rng.sample(invs[:2000], 5):
        rv = dict(i)
        rv["BELNR"] = str(W.next_belnr); W.next_belnr += 1
        rv["WRBTR"], rv["MENGE"], rv["SHKZG"] = -i["WRBTR"], -i["MENGE"], "H"
        rv["STBLG"] = i["BELNR"]
        invs.append(rv)
        plant("initial", "sap/invoices", f, inv_key(rv), "reversal", "dbt",
              "DBT: reversed invoices net to zero", f"Reverses invoice {i['BELNR']}")
    return invs


def write_parquet(path: Path, invs: list[dict]) -> bool:
    """Write invoices as Parquet with typed columns. Needs pyarrow."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        print(f"  ! pyarrow not installed - skipped {path.name} (pip install pyarrow)")
        return False
    schema = pa.schema([
        ("BELNR", pa.string()), ("GJAHR", pa.int32()), ("BUZEI", pa.int32()),
        ("BLDAT", pa.date32()), ("BUDAT", pa.date32()), ("CPUDT", pa.date32()),
        ("LIFNR", pa.string()), ("EBELN", pa.string()), ("EBELP", pa.string()),
        ("MENGE", pa.float64()), ("WRBTR", pa.float64()), ("WAERS", pa.string()),
        ("SHKZG", pa.string()), ("XBLNR", pa.string()), ("STBLG", pa.string()),
    ])
    cols = {name: [r.get(name) for r in invs] for name in schema.names}
    table = pa.table(cols, schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return True


# ---------- SAP: FX rates (XML, ECB style) -----------------------------------

FX_BASE = {"USD": 1.08, "GBP": 0.86, "CHF": 0.95, "CNY": 7.8, "INR": 90.0}


def fx_xml(months: list[str], skip: set[tuple[str, str]] = frozenset()) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<Envelope sender="Sample Pharma Treasury" subject="Monthly average rates (rate type M), 1 EUR = rate x currency">']
    for m in months:
        lines.append(f'  <Cube time="{m}">')
        for cur, base in FX_BASE.items():
            if (m, cur) in skip:
                continue
            drift = 1 + (sum(ord(ch) for ch in m + cur) % 40 - 20) / 1000
            lines.append(f'    <Cube currency="{cur}" rate="{base * drift:.4f}" rateType="M"/>')
        lines.append("  </Cube>")
    lines.append("</Envelope>")
    return "\n".join(lines) + "\n"


# ---------- Supplier risk -----------------------------------------------------

def band(score: int) -> str:
    return "Low" if score <= 3 else ("Medium" if score <= 6 else "High")


def build_risk_esg(generated: datetime, assessed_share: float = 0.85) -> dict:
    base_sups = [s for s in W.suppliers if not s.is_duplicate_of]
    assessed = rng.sample(base_sups, int(len(base_sups) * assessed_share))
    out = []
    for s in assessed:
        score = W.risk.setdefault(s.vat, rng.choices(range(1, 10), [8, 14, 16, 16, 14, 12, 9, 7, 4])[0])
        assessed_at = rand_date(date(2025, 6, 1), generated.date())
        medal = rng.choice([None, "Bronze", "Silver", "Gold", "Platinum", None])
        out.append({
            "supplier": {"name": s.name, "vatNumber": s.vat, "dunsNumber": s.duns, "country": s.country},
            "scores": {"financialRisk": score, "paydex": rng.randint(40, 80), "failureScore": rng.randint(1, 100)},
            "esg": {"ecovadisScore": rng.randint(25, 85), "medal": medal},
            "assessedAt": assessed_at.isoformat(),
            "nextReviewDue": (assessed_at + timedelta(days=365)).isoformat(),
        })
    return {"provider": "RiskCo Intelligence (fictional)", "generatedAt": iso(generated),
            "schemaVersion": "1.0", "suppliers": out}


def risk_event(s_vat: str, score, event_time: datetime, version: int = 1, reason: str = "Periodic re-score",
               event_id: str | None = None, **extra) -> dict:
    prev = W.risk.get(s_vat)
    e = {
        "event_id": event_id or f"RSK-{rng.randint(10**9, 10**10 - 1)}",
        "event_type": "RISK_SCORE_CHANGED",
        "payload_version": version,
        "supplier_vat": s_vat,
        "risk_score": score,
        "previous_score": prev,
        "reason": reason,
        "event_time": iso(event_time),
        "source": "RiskCo",
    }
    e.update(extra)
    if isinstance(score, int) and 1 <= score <= 9:
        W.risk[s_vat] = score
    return e


# ---------- Reference: savings tracker (Excel) -------------------------------

SAVINGS_HEADER = ["Savings ID", "Event ID", "Category", "Supplier", "Baseline (EUR)", "Negotiated (EUR)",
                  "Savings (EUR)", "Savings Date", "Validated by Finance", "Owner", "Comments"]


def build_savings() -> list[dict]:
    sup_by_ariba = {s.ariba_id: s for s in W.suppliers}
    rows = []
    completed = [e for e in W.events if e["status"] == "Completed" and e["award"]]
    for i, e in enumerate(completed[:60]):
        base = e["baselineSpend"]["amount"]
        neg = e["award"]["awardedAmount"]
        d = datetime.fromisoformat((e["awardDate"] or e["closeDate"]).replace("Z", "")).date()
        rows.append({
            "Savings ID": f"SAV-{i + 1:04d}", "Event ID": e["eventId"], "Category": e["category"]["name"],
            "Supplier": sup_by_ariba[e["award"]["aribaSupplierId"]].name,
            "Baseline (EUR)": round(base, 2), "Negotiated (EUR)": round(neg, 2),
            "Savings (EUR)": round(base - neg, 2),
            # mix of real Excel dates and dd/mm/yyyy text (typed by hand)
            "Savings Date": d if i % 3 else d.strftime("%d/%m/%Y"),
            "Validated by Finance": rng.choice(["Yes", "No", "yes", "Y", "Yes", "No"]),
            "Owner": e["owner"]["name"], "Comments": rng.choice(["", "", "Verified with finance", "Pending PO data", ""]),
        })
    return rows


def write_savings_xlsx(path: Path, rows: list[dict], wave: str) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Savings FY2026"
    ws["A1"] = "Procurement savings tracker FY2026 (kept by Procurement Finance)"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Do not change column order. Last edited by hand."
    ws.append(SAVINGS_HEADER)                     # header on row 3
    for c in ws[3]:
        c.font = Font(bold=True)
    for r in rows:
        if r is None:
            ws.append([])                         # blank row pasted in the middle
            continue
        ws.append([r[h] for h in SAVINGS_HEADER])
        cell = ws.cell(row=ws.max_row, column=8)
        if isinstance(r["Savings Date"], date):
            cell.number_format = "dd/mm/yyyy"
    total_row = ws.max_row + 1
    ws.cell(row=total_row, column=1, value="TOTAL")
    ws.cell(row=total_row, column=7, value=f"=SUM(G4:G{total_row - 1})")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    plant(wave, "reference/savings_tracker", path.name, "TOTAL", "excel_total_row", "audit", "AUD-R12",
          "Hand-made TOTAL row at the bottom of the sheet")


# ---------------------------------------------------------------------------
# Writers for the initial load
# ---------------------------------------------------------------------------

def paginate(records: list[dict], page_size: int = 100) -> list[dict]:
    pages = []
    total = len(records)
    for p in range(0, total, page_size):
        page_no = p // page_size + 1
        has_next = p + page_size < total
        pages.append({
            "result": records[p:p + page_size],
            "meta": {"page": page_no, "page_size": page_size, "total": total,
                     "next_page": page_no + 1 if has_next else None},
        })
    return pages


def request_record(r: dict) -> dict:
    """API returns every value as text, like many REST APIs do."""
    return {
        "request_id": r["request_id"], "short_description": r["short_description"],
        "category_id": r["category_id"], "business_unit": r["business_unit"],
        "estimated_value": str(r["estimated_value"]), "currency": r["currency"],
        "requested_by": r["requested_by"], "status": r["status"],
        "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": r["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "sla_due_date": r["sla_due_date"].isoformat(),
        "linked_event_id": r["_event"] or "",
    }


def clean_contract(c: dict) -> dict:
    return {k: v for k, v in c.items() if not k.startswith("_")}


def write_initial() -> None:
    d = INITIAL
    # ---- SAP
    write_text(d / "sap/suppliers/sap_suppliers_cremas_20261031.xml", supplier_xml(W.suppliers))
    write_csv(d / "sap/po_items/sap_po_items_ekpo_20261031.csv", PO_HEADER,
              [po_row(l) for l in W.initial_po_lines], delimiter=";")
    write_parquet(d / "sap/invoices/sap_invoices_rseg_20261031.parquet", W.initial_invoices)
    write_csv(d / "sap/cost_centers/sap_cost_centers_csks_20261031.csv",
              ["kostl", "kokrs", "bukrs", "cost_center_name", "business_unit", "responsible",
               "valid_from", "valid_to", "updated_at"],
              [[c[k] for k in ["kostl", "kokrs", "bukrs", "cost_center_name", "business_unit",
                               "responsible", "valid_from", "valid_to", "updated_at"]] for c in W.cost_centers])
    months = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13) if (y, m) <= (2026, 10)]
    write_text(d / "sap/fx_rates/sap_fx_rates_tcurr_20261031.xml", fx_xml(months, skip={("2026-08", "INR")}))
    plant("initial", "sap/fx_rates", "sap_fx_rates_tcurr_20261031.xml", "INR|2026-08", "missing_fx_rate",
          "dbt", "DBT: no null amount_eur (FX found)", "INR rate missing for 2026-08")
    # ---- Ariba sourcing
    recs = [request_record(r) for r in sorted(W.requests, key=lambda r: r["request_id"])]
    for i, page in enumerate(paginate(recs), start=1):
        write_json(d / f"ariba_sourcing/requests/ariba_sourcing_requests_20261031_page_{i:03d}.json", page)
    write_json(d / "ariba_sourcing/events/ariba_sourcing_events_20261031.json",
               {"records": W.events, "exportedAt": iso(datetime(2026, 10, 31, 1, 0))})
    # ---- Ariba contracts
    write_json(d / "ariba_contracts/contracts/ariba_contracts_20261031.json",
               {"contracts": [clean_contract(c) for c in W.contracts], "count": len(W.contracts)})
    write_csv(d / "ariba_contracts/approvals/ariba_contract_approvals_20261031.csv",
              ["approval_id", "contract_id", "step", "approver_id", "approver_name", "approver_email",
               "approver_manager_id", "approver_title", "decision", "decided_at"], build_approvals())
    # ---- Supplier risk (weekly full file)
    esg = build_risk_esg(datetime(2026, 10, 26, 5, 0))
    for s in rng.sample(esg["suppliers"], 3):
        s["scores"]["financialRisk"] = rng.choice([0, 11, 12])
        plant("initial", "supplier_risk/risk_esg", "supplier_risk_esg_20261026.json", s["supplier"]["vatNumber"],
              "risk_score_out_of_range", "audit", "AUD-R11", "financialRisk outside 1-9")
    for s in rng.sample(esg["suppliers"], 10):
        s["nextReviewDue"] = rand_date(date(2026, 1, 1), date(2026, 9, 30)).isoformat()
        plant("initial", "supplier_risk/risk_esg", "supplier_risk_esg_20261026.json", s["supplier"]["vatNumber"],
              "risk_review_overdue", "dbt", "DBT: risk review not overdue", "nextReviewDue is in the past")
    write_json(d / "supplier_risk/risk_esg/supplier_risk_esg_20261026.json", esg)
    # ---- Reference
    write_csv(d / "reference/categories/category_taxonomy_20261031.csv",
              ["category_id", "category_name", "parent_category_id", "level", "unspsc_code",
               "sap_material_group", "is_active", "valid_from", "valid_to", "updated_at"],
              [[c[0], c[1], c[2] or "", c[3], c[4] or "", c[5] or "", "Y" if c[6] else "N",
                "2015-01-01", "9999-12-31" if c[6] else "2025-12-31", "2026-01-02T08:00:00Z"]
               for c in CATEGORIES])
    rows = build_savings()
    W.savings = rows
    for r in rng.sample(rows, 5):
        r["Savings (EUR)"] = round(r["Savings (EUR)"] * rng.choice([1.1, 0.5, 2]), 2)
        plant("initial", "reference/savings_tracker", "savings_tracker_fy2026_20261030.xlsx", r["Savings ID"],
              "savings_mismatch", "dbt", "DBT: savings = baseline - negotiated", "Reported savings do not add up")
    pasted = [dict(r) for r in rng.sample(rows, 3)]
    for p in pasted:
        plant("initial", "reference/savings_tracker", "savings_tracker_fy2026_20261030.xlsx", p["Savings ID"],
              "pasted_duplicate_row", "dbt", "DBT: unique savings_id", "Row pasted twice by hand")
    sheet_rows = rows[:30] + [None] + rows[30:] + pasted
    write_savings_xlsx(d / "reference/savings_tracker/savings_tracker_fy2026_20261030.xlsx", sheet_rows, "initial")


# ---------------------------------------------------------------------------
# Drop waves
# ---------------------------------------------------------------------------

WAVES: list[dict] = []


def wave_dir(n: int) -> Path:
    return PENDING / f"wave_{n:02d}"


def inc(n: int, rel: str) -> Path:
    """Path inside a wave folder that mirrors the repo: data/incoming/<rel>."""
    return wave_dir(n) / "data" / "incoming" / rel


def register_wave(n: int, title: str, path_type: str, what: str, expect: str) -> None:
    WAVES.append({"wave": n, "title": title, "path": path_type, "what": what, "expect": expect})


def po_csv_text(lines: list[dict], header: list[str] = PO_HEADER, extra=None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(header)
    for l in lines:
        row = po_row(l)
        if extra:
            row = extra(row, l)
        w.writerow(row)
    return buf.getvalue()


def daily_pos(day: date, n: int) -> list[dict]:
    out = []
    for _ in range(n):
        out += make_po(day)
    return out


def build_waves() -> None:
    # ---- Wave 1: normal daily batch --------------------------------------
    d1 = date(2026, 11, 2)
    pos1 = daily_pos(d1, 25)
    W.wave1_pos = pos1
    write_text(inc(1, "sap/po_items/sap_po_items_ekpo_20261102.csv"), po_csv_text(pos1))
    inv1 = make_invoice_lines([l for l in W.initial_po_lines if date(2026, 10, 1) <= l["BEDAT"] <= date(2026, 10, 20)
                               and l["LOEKZ"] == ""][:60], d1, d1)
    write_parquet(inc(1, "sap/invoices/sap_invoices_rseg_20261102.parquet"), inv1)
    register_wave(1, "Normal daily batch", "Batch",
                  "New PO lines (CSV) and invoices (Parquet) for 2026-11-02",
                  "Loaded on the next 10-minute batch run. No DQ errors. Incremental models pick up only new rows.")

    # ---- Wave 2: risk stream, normal + spike -----------------------------
    vats = list(W.risk)
    t0 = datetime(2026, 11, 2, 9, 0)
    for k in range(5):
        evs = []
        for j in range(8):
            v = rng.choice(vats)
            cur = W.risk[v]
            evs.append(risk_event(v, max(1, min(9, cur + rng.choice([-1, 0, 1]))), t0 + timedelta(minutes=k * 5 + j)))
        if k == 3:   # spike -> alert
            v = rng.choice([x for x in vats if W.risk[x] <= 4])
            e = risk_event(v, 8, t0 + timedelta(minutes=k * 5 + 9), reason="Credit downgrade")
            evs.append(e)
            plant("wave_02", "supplier_risk/risk_events", f"risk_events_20261102_{k + 1:02d}.ndjson", e["event_id"],
                  "risk_spike", "stream", "STREAM: alert when score >= 7 or jump >= 3", f"Score jumps to 8 for {v}")
        write_ndjson(inc(2, f"supplier_risk/risk_events/risk_events_20261102_{k + 1:02d}.ndjson"), evs)
    register_wave(2, "Risk stream: normal events + one spike", "Stream",
                  "5 NDJSON files of risk score events; one supplier jumps to score 8",
                  "Each file lands within about a minute (Snowpipe). RISK_CURRENT updates; the spike raises HIGH_RISK and SCORE_JUMP alerts.")

    # ---- Wave 3: exact duplicate file re-delivered (same name, same content)
    src = inc(1, "sap/po_items/sap_po_items_ekpo_20261102.csv")
    dst = inc(3, "sap/po_items/redelivery_20261103/sap_po_items_ekpo_20261102.csv")
    write_text(dst, src.read_text(encoding="utf-8"))
    plant("wave_03", "sap/po_items", "sap_po_items_ekpo_20261102.csv", "(file)", "exact_duplicate_file",
          "audit", "AUD-F02", "Same file name and same content delivered again (SAP re-extract)")
    register_wave(3, "Exact duplicate file", "Batch",
                  "The wave-1 PO file delivered again in a 'redelivery' folder: same name, same content",
                  "It lands in RAW (unique stage path), AUD-F02 flags it, dbt dedup keeps one row per PO line.")

    # ---- Wave 4: same content, different name ---------------------------
    write_text(inc(4, "sap/po_items/sap_po_items_ekpo_20261102_resend.csv"), src.read_text(encoding="utf-8"))
    plant("wave_04", "sap/po_items", "sap_po_items_ekpo_20261102_resend.csv", "(file)", "same_content_new_name",
          "audit", "AUD-F04", "Identical content to sap_po_items_ekpo_20261102.csv under a new name")
    register_wave(4, "Same content, different name", "Batch",
                  "The wave-1 PO file resent as *_resend.csv",
                  "Snowflake load history cannot catch this. AUD-F04 (same MD5) flags it; RAW has duplicates; staging dedups.")

    # ---- Wave 5: same name, different content (corrected file) -----------
    corrected = [dict(l) for l in pos1]
    for l in corrected[:5]:
        l["MENGE"] = l["MENGE"] + 10
        l["NETWR"] = round(l["MENGE"] * l["NETPR"], 2)
        l["AEDAT"] = date(2026, 11, 4)
        plant("wave_05", "sap/po_items", "sap_po_items_ekpo_20261102.csv", po_key(l), "corrected_line",
              "dbt", "DBT: keep latest version per PO line", "Quantity corrected in a re-sent file with the same name")
    write_text(inc(5, "sap/po_items/correction_20261104/sap_po_items_ekpo_20261102.csv"), po_csv_text(corrected))
    plant("wave_05", "sap/po_items", "sap_po_items_ekpo_20261102.csv", "(file)", "same_name_new_content",
          "audit", "AUD-F03", "Same file name as wave 1 but the content changed")
    # risk side: same name different content
    evs = [risk_event(v, max(1, min(9, W.risk[v] + 1)), datetime(2026, 11, 4, 10, i)) for i, v in enumerate(rng.sample(vats, 4))]
    write_ndjson(inc(5, "supplier_risk/risk_events/correction_20261104/risk_events_20261102_01.ndjson"), evs)
    plant("wave_05", "supplier_risk/risk_events", "risk_events_20261102_01.ndjson", "(file)", "same_name_new_content",
          "audit", "AUD-F03", "Stream file re-sent with the same name and new content")
    register_wave(5, "Same name, different content", "Both",
                  "Corrected PO file and a risk file re-sent with the SAME file names as before, new content",
                  "With unique stage paths both land (no silent skip). AUD-F03 flags them; staging keeps the latest AEDAT/load.")

    # ---- Wave 6: bad rows -------------------------------------------------
    d6 = date(2026, 11, 5)
    pos6 = daily_pos(d6, 12)
    text = po_csv_text(pos6).splitlines()
    bad_idx = [3, 7, 11, 15, 19]
    issues = {
        3: ("extra_delimiter", "AUD-R02", "Unquoted ';' inside the text column shifts every field"),
        7: ("text_in_amount", "AUD-R02", "NETWR contains text 'n/a'"),
        11: ("missing_key", "AUD-R03", "LIFNR (supplier) is empty"),
        15: ("invalid_date", "AUD-R04", "BEDAT is '20261345'"),
    }
    for i in bad_idx:
        if i >= len(text):
            continue
        parts = text[i].split(";")
        key = f"{parts[0]}-{parts[1]}"
        if i == 3:
            parts[6] = parts[6] + "; nitrile, size M"
        elif i == 7:
            parts[11] = "n/a"
        elif i == 11:
            parts[3] = ""
        elif i == 15:
            parts[4] = "20261345"
        elif i == 19:
            parts[6] = "Soci\x00t\x00 G\x00n\x00rale reagents"   # placeholder, replaced below with latin-1 bytes
        text[i] = ";".join(parts)
        if i in issues:
            t, rule, desc = issues[i]
            plant("wave_06", "sap/po_items", "sap_po_items_ekpo_20261105.csv", key, t, "audit", rule, desc)
    raw = ("\n".join(text) + "\n").encode("utf-8")
    raw = raw.replace("Soci\x00t\x00 G\x00n\x00rale".encode("utf-8"), "Société Générale".encode("latin-1"))
    p = inc(6, "sap/po_items/sap_po_items_ekpo_20261105.csv")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw)
    if len(text) > 19:
        parts = text[19].split(";")
        plant("wave_06", "sap/po_items", p.name, f"{parts[0]}-{parts[1]}", "invalid_encoding", "audit", "AUD-R06",
              "Latin-1 bytes in a UTF-8 file (é); Snowflake replaces them with �")
    register_wave(6, "Bad rows", "Batch",
                  "PO file with an extra delimiter, text in an amount, a missing supplier, an invalid date, bad encoding",
                  "Whole file still lands (all VARCHAR, ON_ERROR=CONTINUE). Row rules flag the 5 rows; dbt quarantines them.")

    # ---- Wave 7: late-arriving + changed + deleted -----------------------
    d7 = date(2026, 11, 6)
    late_src = [l for l in W.initial_po_lines if date(2026, 9, 1) <= l["BEDAT"] <= date(2026, 9, 20) and l["LOEKZ"] == ""]
    late_invs = make_invoice_lines(rng.sample(late_src, 30), date(2026, 9, 25), date(2026, 9, 28))
    for i in late_invs[:3]:
        plant("wave_07", "sap/invoices", "sap_invoices_rseg_20261106.parquet", inv_key(i), "late_arriving",
              "dbt", "DBT: incremental lookback window", "Invoice posted in September, delivered in November")
    write_parquet(inc(7, "sap/invoices/sap_invoices_rseg_20261106.parquet"), late_invs)
    changed = [dict(l) for l in rng.sample([l for l in W.initial_po_lines if l["LOEKZ"] == ""], 15)]
    for k, l in enumerate(changed):
        l["AEDAT"] = d7
        if k < 10:
            l["MENGE"] = l["MENGE"] + rng.randint(1, 5)
            l["NETWR"] = round(l["MENGE"] * l["NETPR"], 2)
            plant("wave_07", "sap/po_items", "sap_po_items_ekpo_20261106_delta.csv", po_key(l), "changed_record",
                  "dbt", "DBT: keep latest AEDAT per PO line", "PO line quantity changed (new AEDAT)")
        else:
            l["LOEKZ"] = "L"
            plant("wave_07", "sap/po_items", "sap_po_items_ekpo_20261106_delta.csv", po_key(l), "deleted_record",
                  "dbt", "DBT: keep and flag deleted PO lines", "PO line deleted in SAP (LOEKZ = L)")
    write_text(inc(7, "sap/po_items/sap_po_items_ekpo_20261106_delta.csv"), po_csv_text(changed))
    register_wave(7, "Late, changed and deleted records", "Batch",
                  "Invoices posted in September arriving now; PO lines changed or deleted (new AEDAT)",
                  "Incremental models must use a lookback window or late rows are missed; staging keeps latest AEDAT.")

    # ---- Wave 8: supplier master changes (full reload, SCD2) -------------
    d8 = date(2026, 11, 7)
    changes = rng.sample([s for s in W.suppliers if not s.is_duplicate_of and not s.blocked], 8)
    for k, s in enumerate(changes):
        s.updated = d8
        if k < 2:
            s.name = s.name.replace(" ", "  ", 1) if k == 0 else s.name + " (formerly " + s.name.split()[0] + ")"
            what = "name changed"
        elif k < 4:
            s.city = rng.choice(COUNTRIES[s.country][1])
            what = "address changed"
        elif k < 6:
            s.iban = f"{s.country}{rng.randint(10, 99)}{rng.randint(10**15, 10**16 - 1)}"
            what = "bank account changed"
        else:
            s.blocked = True
            what = "supplier blocked"
        plant("wave_08", "sap/suppliers", "sap_suppliers_cremas_20261107.xml", s.lifnr, "scd2_change", "dbt",
              "DBT: snapshot (SCD2) on supplier", what)
    newdup_src = rng.choice([s for s in W.suppliers if not s.is_duplicate_of and s not in changes])
    nd = Supplier(**{**newdup_src.__dict__})
    nd.lifnr = f"{100001 + len(W.suppliers):010d}"
    nd.ariba_id = f"S{2000001 + len(W.suppliers)}"
    nd.name = newdup_src.name.upper()
    nd.is_duplicate_of = newdup_src.lifnr
    nd.created = nd.updated = d8
    W.suppliers.append(nd)
    plant("wave_08", "sap/suppliers", "sap_suppliers_cremas_20261107.xml", nd.lifnr, "duplicate_supplier", "dbt",
          "DBT: one golden ID per VAT number", f"New vendor ID for existing supplier {newdup_src.lifnr} (same VAT)")
    write_text(inc(8, "sap/suppliers/sap_suppliers_cremas_20261107.xml"), supplier_xml(W.suppliers, 500))
    register_wave(8, "Supplier master changes", "Batch",
                  "Full reload of the vendor master: names, addresses, bank accounts changed, 2 newly blocked, 1 new duplicate",
                  "dbt snapshot creates new SCD2 versions; golden record merges the new duplicate by VAT.")

    # ---- Wave 9: schema drift --------------------------------------------
    d9 = date(2026, 11, 9)
    pos9 = daily_pos(d9, 10)
    hdr = [("CURRENCY" if h == "WAERS" else h) for h in PO_HEADER] + ["ZZ_PROJECT"]
    write_text(inc(9, "sap/po_items/sap_po_items_ekpo_20261109.csv"),
               po_csv_text(pos9, header=hdr, extra=lambda row, l: row + [f"PRJ-{rng.randint(100, 999)}"]))
    plant("wave_09", "sap/po_items", "sap_po_items_ekpo_20261109.csv", "(file)", "schema_drift", "audit", "AUD-S01",
          "Column WAERS renamed to CURRENCY and new column ZZ_PROJECT appended")
    evs = []
    for i, v in enumerate(rng.sample(vats, 6)):
        evs.append(risk_event(v, max(1, min(9, W.risk[v] + rng.choice([-1, 1]))), datetime(2026, 11, 9, 11, i),
                              version=2, sanctions_hit=(i == 2), data_provider_ref=f"RC-{rng.randint(1000, 9999)}"))
    plant("wave_09", "supplier_risk/risk_events", "risk_events_20261109_01.ndjson", evs[2]["event_id"],
          "payload_v2_sanctions", "stream", "STREAM: v2 payload handled + sanctions alert",
          "payload_version 2 adds sanctions_hit and data_provider_ref")
    write_ndjson(inc(9, "supplier_risk/risk_events/risk_events_20261109_01.ndjson"), evs)
    register_wave(9, "Schema drift", "Both",
                  "PO file with a renamed column and a new column; risk events with payload_version 2",
                  "Data still lands (header row kept, extra column in _EXTRA_1). AUD-S01 flags drift; stream handles v2.")

    # ---- Wave 10: contracts + sourcing updates ---------------------------
    upd = []
    act = [c for c in W.contracts if c["status"] == "Active" and not c["isDeleted"]]
    for c in rng.sample(act, 6):
        c2 = clean_contract(c)
        c2 = json.loads(json.dumps(c2))
        c2["amendments"].append({"amendmentId": f"{c['contractId']}-A{len(c['amendments']) + 1}",
                                 "effectiveDate": "2026-11-10", "valueChange": round(c["value"]["amount"] * 0.1, 2),
                                 "reason": "Volume increase"})
        c2["value"]["amount"] = round(c2["value"]["amount"] * 1.1, 2)
        c2["lastStatusChangeAt"] = "2026-11-10T09:00:00Z"
        upd.append(c2)
        plant("wave_10", "ariba_contracts/contracts", "ariba_contracts_20261110_delta.json", c["contractId"],
              "contract_amended", "dbt", "DBT: snapshot contract status (SCD2)", "New amendment, value +10%")
    for c in rng.sample(act, 3):
        c2 = json.loads(json.dumps(clean_contract(c)))
        c2["status"] = "Terminated"
        c2["lastStatusChangeAt"] = "2026-11-10T10:00:00Z"
        upd.append(c2)
        plant("wave_10", "ariba_contracts/contracts", "ariba_contracts_20261110_delta.json", c["contractId"],
              "status_change", "dbt", "DBT: dim_contract_status one current row", "Active -> Terminated")
    c2 = json.loads(json.dumps(clean_contract(rng.choice(act))))
    c2["isDeleted"] = True
    c2["lastStatusChangeAt"] = "2026-11-10T11:00:00Z"
    upd.append(c2)
    plant("wave_10", "ariba_contracts/contracts", "ariba_contracts_20261110_delta.json", c2["contractId"],
          "soft_delete", "dbt", "DBT: exclude soft-deleted contracts", "Contract soft-deleted")
    write_json(inc(10, "ariba_contracts/contracts/ariba_contracts_20261110_delta.json"),
               {"contracts": upd, "count": len(upd)})
    open_evs = [e for e in W.events if e["status"] in ("Open", "Closed")][:4]
    ev_upd = []
    for k, e in enumerate(open_evs):
        e2 = json.loads(json.dumps(e))
        e2["status"] = "Completed"
        e2["award"] = {"aribaSupplierId": e2["bids"][0]["supplier"]["aribaId"], "awardedAmount": e2["bids"][0]["bidAmount"]}
        e2["awardDate"] = None if k == 0 else "2026-11-10T12:00:00Z"
        e2["updatedAt"] = "2026-11-10T12:00:00Z"
        ev_upd.append(e2)
        if k == 0:
            plant("wave_10", "ariba_sourcing/events", "ariba_sourcing_events_20261110_delta.json", e2["eventId"],
                  "completed_no_award_date", "dbt", "DBT: completed event has award date", "Completed without awardDate")
    write_json(inc(10, "ariba_sourcing/events/ariba_sourcing_events_20261110_delta.json"),
               {"records": ev_upd, "exportedAt": "2026-11-10T13:00:00Z"})
    new_reqs = build_requests(12)
    for r in new_reqs:
        r["request_id"] = f"REQ{1002001 + new_reqs.index(r)}"
        r["created_at"] = datetime(2026, 11, 10, 9) + timedelta(minutes=new_reqs.index(r) * 13)
        r["updated_at"] = r["created_at"]
    new_reqs[0]["updated_at"] = new_reqs[0]["created_at"] - timedelta(hours=5)
    plant("wave_10", "ariba_sourcing/requests", "ariba_sourcing_requests_20261110_page_001.json",
          new_reqs[0]["request_id"], "updated_before_created", "audit", "AUD-R09", "updated_at earlier than created_at")
    for i, page in enumerate(paginate([request_record(r) for r in new_reqs], 5), start=1):
        write_json(inc(10, f"ariba_sourcing/requests/ariba_sourcing_requests_20261110_page_{i:03d}.json"), page)
    register_wave(10, "Contract and sourcing updates", "Batch",
                  "Contract deltas (amendments, terminations, soft delete), events completed, 12 new requests in 3 pages",
                  "Snapshots capture status history; soft deletes excluded; new pages flattened.")

    # ---- Wave 11: empty, header-only, huge file --------------------------
    write_text(inc(11, "sap/po_items/sap_po_items_ekpo_20261111.csv"), "")
    write_text(inc(11, "sap/po_items/sap_po_items_ekpo_20261111_b.csv"), ";".join(PO_HEADER) + "\n")
    plant("wave_11", "sap/po_items", "sap_po_items_ekpo_20261111.csv", "(file)", "empty_file", "audit", "AUD-F01",
          "0-byte file")
    plant("wave_11", "sap/po_items", "sap_po_items_ekpo_20261111_b.csv", "(file)", "header_only_file", "audit",
          "AUD-F01", "File with a header and no data rows")
    big = []
    for _ in range(9000):
        big += make_po(rand_date(date(2026, 11, 1), date(2026, 11, 11)))
    write_text(inc(11, "sap/po_items/sap_po_items_ekpo_20261111_bulk.csv"), po_csv_text(big))
    plant("wave_11", "sap/po_items", "sap_po_items_ekpo_20261111_bulk.csv", "(file)", "volume_spike", "audit",
          "AUD-F08", f"{len(big)} rows, far above the usual daily volume")
    register_wave(11, "Empty, header-only and bulk files", "Batch",
                  f"A 0-byte file, a header-only file, and a bulk file with {len(big)} PO lines",
                  "Empty files are logged, not errors. Volume check warns on the bulk file. Python reads it in chunks.")

    # ---- Wave 12: stream chaos + Excel + FX ------------------------------
    t = datetime(2026, 11, 12, 14, 0)
    v = rng.choice(vats)
    e_new = risk_event(v, 3, t + timedelta(minutes=10))
    e_old = risk_event(v, 7, t, reason="Out-of-order: older event arrives after newer")
    W.risk[v] = 3
    f1 = [e_new, e_old]
    plant("wave_12", "supplier_risk/risk_events", "risk_events_20261112_01.ndjson", e_old["event_id"],
          "out_of_order", "stream", "STREAM: MERGE only if event_time is newer", "Older event delivered after newer one")
    dup = dict(e_new)
    f1.append(dup)
    plant("wave_12", "supplier_risk/risk_events", "risk_events_20261112_01.ndjson", e_new["event_id"],
          "duplicate_event", "stream", "STREAM: dedup on event_id", "Same event_id delivered twice")
    late = risk_event(rng.choice(vats), 5, t - timedelta(hours=6), reason="Late delivery")
    f1.append(late)
    plant("wave_12", "supplier_risk/risk_events", "risk_events_20261112_01.ndjson", late["event_id"],
          "late_event", "stream", "STREAM: is_late flag", "event_time 6 hours before arrival")
    bad1 = risk_event("", 4, t + timedelta(minutes=12))
    bad2 = risk_event(rng.choice(vats), 15, t + timedelta(minutes=13))
    bad3 = risk_event(rng.choice(vats), 4, t + timedelta(minutes=14), version=3)
    bad4 = risk_event(rng.choice(vats), "high", t + timedelta(minutes=15))
    for b, why in [(bad1, "missing supplier_vat"), (bad2, "risk_score 15 out of range"),
                   (bad3, "unsupported payload_version 3"), (bad4, "risk_score is text")]:
        f1.append(b)
        plant("wave_12", "supplier_risk/risk_events", "risk_events_20261112_01.ndjson", b["event_id"],
              "invalid_event", "stream", "STREAM: dead letter", why)
    write_ndjson(inc(12, "supplier_risk/risk_events/risk_events_20261112_01.ndjson"), f1)
    burst = [risk_event(rng.choice(vats), rng.randint(1, 9), t + timedelta(minutes=20, seconds=s)) for s in range(500)]
    write_ndjson(inc(12, "supplier_risk/risk_events/risk_events_20261112_02_burst.ndjson"), burst)
    plant("wave_12", "supplier_risk/risk_events", "risk_events_20261112_02_burst.ndjson", "(file)", "burst",
          "stream", "STREAM: throughput", "500 events in one minute (quarter-end style burst)")
    # updated savings tracker with more pasted rows
    rows = [dict(r) for r in W.savings]
    pasted = [dict(r) for r in rng.sample(rows, 2)]
    for p_ in pasted:
        plant("wave_12", "reference/savings_tracker", "savings_tracker_fy2026_20261113.xlsx", p_["Savings ID"],
              "pasted_duplicate_row", "dbt", "DBT: unique savings_id", "Row pasted twice by hand")
    write_savings_xlsx(inc(12, "reference/savings_tracker/savings_tracker_fy2026_20261113.xlsx"),
                       rows[:45] + [None, None] + rows[45:] + pasted, "wave_12")
    write_text(inc(12, "sap/fx_rates/sap_fx_rates_tcurr_20261201.xml"), fx_xml(["2026-11"]))
    register_wave(12, "Stream chaos + manual Excel + FX", "Both",
                  "Out-of-order, duplicate, late and invalid risk events; a 500-event burst; new savings Excel; November FX",
                  "Dead letter gets 4 invalid events + 1 duplicate; the out-of-order event does not overwrite the newer score; the late event is flagged.")


# ---------------------------------------------------------------------------
# Answer key + wave notes
# ---------------------------------------------------------------------------

def write_answer_key() -> None:
    ANSWER_KEY.mkdir(parents=True, exist_ok=True)
    with open(ANSWER_KEY / "planted_issues.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(PLANTED[0].keys()))
        w.writeheader()
        w.writerows(PLANTED)
    for wv in WAVES:
        n = wv["wave"]
        files = sorted(p.relative_to(wave_dir(n)).as_posix() for p in wave_dir(n).rglob("*") if p.is_file()
                       and p.name != "WAVE.md")
        md = [f"# Wave {n:02d}: {wv['title']}", "", f"**Path:** {wv['path']}", "", f"**What is in it:** {wv['what']}", "",
              f"**What should happen:** {wv['expect']}", "", "**Files:**", ""] + [f"- `{f}`" for f in files]
        issues = [p for p in PLANTED if p["wave"] == f"wave_{n:02d}"]
        if issues:
            md += ["", "**Planted issues:**", "", "| Issue | Type | Key | Caught by | Check |", "|---|---|---|---|---|"]
            md += [f"| {p['issue_id']} | {p['issue_type']} | {p['record_key']} | {p['caught_by']} | {p['expected_check']} |"
                   for p in issues]
        write_text(wave_dir(n) / "WAVE.md", "\n".join(md) + "\n")
    with open(ANSWER_KEY / "waves.json", "w", encoding="utf-8") as fh:
        json.dump(WAVES, fh, indent=2)


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clean", action="store_true", help="delete data/initial, pending/ and answer_key/ first")
    args = ap.parse_args()
    if args.clean:
        for p in (INITIAL, PENDING, ANSWER_KEY):
            shutil.rmtree(p, ignore_errors=True)

    print("Building reference data ...")
    W.employees = build_employees()
    W.suppliers = build_suppliers(200)
    W.cost_centers = build_cost_centers()
    # duplicate suppliers (same VAT, new SAP ID, name variant)
    base = list(W.suppliers)
    for s in rng.sample(base, 8):
        variant = rng.choice([s.name.upper(), s.name.replace(" ", "  ", 1), s.name + ".", s.name.replace("Ltd", "Limited")])
        nd = Supplier(**{**s.__dict__})
        nd.lifnr = f"{100001 + len(W.suppliers):010d}"
        nd.ariba_id = f"S{2000001 + len(W.suppliers)}"
        nd.name = variant
        nd.is_duplicate_of = s.lifnr
        nd.created = rand_date(date(2024, 1, 1), date(2026, 9, 1))
        W.suppliers.append(nd)
        plant("initial", "sap/suppliers", "sap_suppliers_cremas_20261031.xml", nd.lifnr, "duplicate_supplier",
              "dbt", "DBT: one golden ID per VAT number", f"Same VAT as {s.lifnr}, name '{variant}'")
    for s in rng.sample([x for x in base if not x.is_duplicate_of], 6):
        s.blocked = True
    print("Building sourcing, contracts, purchasing, invoices ...")
    W.requests = build_requests(300)
    build_events_and_bids()
    build_contracts()
    W.initial_po_lines = build_initial_pos(1500)
    W.initial_invoices = build_initial_invoices(W.initial_po_lines)
    # requests with updated_at before created_at
    for r in rng.sample(W.requests, 4):
        r["updated_at"] = r["created_at"] - timedelta(hours=rng.randint(1, 30))
        plant("initial", "ariba_sourcing/requests", "ariba_sourcing_requests_20261031_page_*.json", r["request_id"],
              "updated_before_created", "audit", "AUD-R09", "updated_at earlier than created_at")
    print("Writing initial load ...")
    write_initial()
    print("Writing drop waves ...")
    build_waves()
    write_answer_key()
    n_files = sum(1 for p in INITIAL.rglob("*") if p.is_file())
    n_wave = sum(1 for p in PENDING.rglob("*") if p.is_file() and p.name != "WAVE.md")
    print(f"Done. initial files: {n_files}, wave files: {n_wave}, planted issues: {len(PLANTED)}")
    print(f"  PO lines (initial): {len(W.initial_po_lines)}, invoice lines (initial): {len(W.initial_invoices)}")


if __name__ == "__main__":
    main()
