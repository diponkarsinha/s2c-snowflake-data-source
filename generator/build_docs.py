"""
Builds documentation from code and data (docs-as-code). Re-run after changing data:

    python generator/build_docs.py

  docs/data_dictionary/*.md   column definitions below + real samples from data/initial/
  docs/drop_plan.md           the 12 waves and their planted issues (from answer_key/)
"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data_dictionary"
INIT = ROOT / "data" / "initial"

# entity -> (title, source system, file pattern, format, grain, key, load, raw table, description, columns)
# columns: (name, type in source, nullable, description, sensitivity, known issues)
DICT = {
    "sap/po_items": (
        "Purchase order lines", "SAP S/4HANA (MM: EKKO/EKPO)", "sap_po_items_ekpo_YYYYMMDD*.csv",
        "CSV, `;` separated, decimal comma, SAP column names", "One row per PO line", "EBELN + EBELP",
        "Batch, daily delta; changed lines re-sent with a new AEDAT", "RAW.SAP_PO_ITEMS",
        "Every purchase order line. The core of spend analytics.",
        [("EBELN", "CHAR(10)", "No", "Purchase order number", "Internal", "Wave 6: missing in shifted rows"),
         ("EBELP", "NUMC(5)", "No", "PO line number with leading zeros (00010)", "Internal", "Keep as text, never as number"),
         ("BUKRS", "CHAR(4)", "No", "Company code (business unit)", "Internal", ""),
         ("LIFNR", "CHAR(10)", "No", "SAP supplier number with leading zeros", "Internal", "Wave 6: empty; blocked suppliers used"),
         ("BEDAT", "DATS", "No", "PO date YYYYMMDD", "Internal", "Wave 6: invalid date 20261345"),
         ("MATKL", "CHAR(9)", "No", "Material group, maps to category", "Internal", "ZZ-MISC unknown; PK-LFL / IT-SRV inactive"),
         ("TXZ01", "CHAR(40)", "Yes", "Short text", "Internal", "Trailing spaces; wave 6: `;` inside text, Latin-1 bytes"),
         ("MENGE", "QUAN", "No", "Quantity, decimal comma (388,000)", "Internal", "Wave 6: shifted text"),
         ("MEINS", "UNIT", "No", "Unit of measure", "Internal", ""),
         ("NETPR", "CURR", "No", "Net price per price unit, decimal comma", "Confidential", ""),
         ("PEINH", "DEC", "No", "Price unit (usually 1)", "Internal", ""),
         ("NETWR", "CURR", "No", "Net value = MENGE x NETPR / PEINH", "Confidential", "4 lines do not add up; wave 6: 'n/a'"),
         ("WAERS", "CUKY", "No", "Currency (EUR, USD, GBP, CHF, CNY, INR)", "Internal", "Wave 9: renamed to CURRENCY"),
         ("KOSTL", "CHAR(10)", "No", "Cost centre", "Internal", "6 lines charged to closed cost centres"),
         ("KONNR", "CHAR(10)", "Yes", "Contract ID; empty = no contract (maverick)", "Internal", ""),
         ("LOEKZ", "CHAR(1)", "Yes", "Deletion flag, L = deleted in SAP", "Internal", "Deleted lines are kept and flagged"),
         ("AEDAT", "DATS", "No", "Last changed date YYYYMMDD; use to pick the latest version", "Internal", "")]),
    "sap/invoices": (
        "Supplier invoice lines", "SAP S/4HANA (FI: RBKP/RSEG)", "sap_invoices_rseg_YYYYMMDD.parquet",
        "Parquet, typed columns (DATE, DOUBLE, INT)", "One row per invoice line", "BELNR + GJAHR + BUZEI",
        "Batch, daily delta", "RAW.SAP_INVOICES (VARIANT)",
        "Invoices posted against PO lines. Credit memos and reversals are negative.",
        [("BELNR", "string", "No", "Invoice document number", "Internal", ""),
         ("GJAHR", "int32", "No", "Fiscal year", "Internal", ""),
         ("BUZEI", "int32", "No", "Line inside the invoice", "Internal", ""),
         ("BLDAT", "date", "No", "Document date", "Internal", ""),
         ("BUDAT", "date", "No", "Posting date", "Internal", "Wave 7: September invoices arrive in November (late)"),
         ("CPUDT", "date", "No", "Entry date (change tracking)", "Internal", ""),
         ("LIFNR", "string", "No", "SAP supplier number", "Internal", ""),
         ("EBELN", "string", "No", "PO number", "Internal", "5 orphan invoices point to non-existent POs"),
         ("EBELP", "string", "No", "PO line", "Internal", "3 invoices on deleted PO lines"),
         ("MENGE", "double", "No", "Invoiced quantity (negative on credit memos)", "Internal", "6 lines above ordered quantity"),
         ("WRBTR", "double", "No", "Amount in document currency", "Confidential", "20 lines priced above PO price"),
         ("WAERS", "string", "No", "Currency", "Internal", ""),
         ("SHKZG", "string", "No", "S = debit, H = credit", "Internal", "15 credit memos, 5 reversals"),
         ("XBLNR", "string", "Yes", "Supplier's invoice reference", "Internal", ""),
         ("STBLG", "string", "Yes", "Reversed document number", "Internal", "")]),
    "sap/suppliers": (
        "Supplier master", "SAP S/4HANA, governed in SAP MDG (LFA1, LFBK)", "sap_suppliers_cremas_YYYYMMDD.xml",
        "XML, SAP IDoc CREMAS05 (`<IDOC><E1LFA1M>...<E1LFBKM/></E1LFA1M></IDOC>`)", "One IDOC per supplier",
        "LIFNR", "Batch, FULL reload (whole master each time) -> SCD2 snapshot in dbt", "RAW.SAP_SUPPLIERS (VARIANT)",
        "System of record for suppliers. Read with XMLGET in staging.",
        [("LIFNR", "CHAR(10)", "No", "SAP supplier number", "Internal", "8 suppliers duplicated under new IDs"),
         ("NAME1", "CHAR(35)", "No", "Supplier name", "Internal", "Name variants: upper case, double spaces, 'Limited'"),
         ("LAND1", "CHAR(3)", "No", "Country", "Internal", ""),
         ("ORT01", "CHAR(35)", "Yes", "City", "Internal", "Empty tags `<ORT01></ORT01>`"),
         ("STCEG", "CHAR(20)", "No", "VAT number: the key to match duplicates and Ariba suppliers", "Confidential (tax)", ""),
         ("KTOKK", "CHAR(4)", "No", "Account group", "Internal", ""),
         ("SPERR", "CHAR(1)", "Yes", "Posting block, X = blocked", "Internal", "Blocked suppliers still get POs"),
         ("ERDAT", "DATS", "No", "Created on", "Internal", ""),
         ("UPDAT", "DATS", "No", "Last changed", "Internal", "Wave 8: name, address, bank changes"),
         ("E1LFBKM/BANKS", "CHAR(3)", "Yes", "Bank country", "Confidential (bank)", ""),
         ("E1LFBKM/BANKL", "CHAR(15)", "Yes", "Bank key", "Confidential (bank)", ""),
         ("E1LFBKM/IBAN", "CHAR(34)", "Yes", "IBAN", "Confidential (bank)", "Wave 8: changed for 2 suppliers")]),
    "sap/cost_centers": (
        "Cost centres", "SAP S/4HANA (CO: CSKS/CSKT)", "sap_cost_centers_csks_YYYYMMDD.csv", "CSV, comma",
        "One row per cost centre", "kostl", "Batch, full reload", "RAW.SAP_COST_CENTERS",
        "Who pays. Closed cost centres have valid_to in the past.",
        [("kostl", "CHAR(10)", "No", "Cost centre number", "Internal", ""),
         ("kokrs", "CHAR(4)", "No", "Controlling area", "Internal", ""),
         ("bukrs", "CHAR(4)", "No", "Company code", "Internal", ""),
         ("cost_center_name", "text", "No", "Name", "Internal", ""),
         ("business_unit", "text", "No", "Business unit", "Internal", ""),
         ("responsible", "text", "No", "Person responsible", "PII (name)", ""),
         ("valid_from", "date", "No", "Valid from", "Internal", ""),
         ("valid_to", "date", "No", "Valid to; 9999-12-31 = open", "Internal", "3 closed on 2026-06-30 but still charged"),
         ("updated_at", "timestamp", "No", "Last change", "Internal", "")]),
    "sap/fx_rates": (
        "FX rates", "SAP S/4HANA (TCURR)", "sap_fx_rates_tcurr_YYYYMMDD.xml",
        "XML, ECB style `<Cube time='YYYY-MM'><Cube currency rate rateType/></Cube>`",
        "One rate per currency per month", "currency + month", "Batch, monthly", "RAW.SAP_FX_RATES (VARIANT)",
        "Monthly average rates (type M): 1 EUR = rate x currency. Attributes read with GET(..., '@rate').",
        [("time", "attribute", "No", "Month YYYY-MM", "Internal", ""),
         ("currency", "attribute", "No", "Currency code", "Internal", ""),
         ("rate", "attribute", "No", "Units of currency per 1 EUR", "Internal", "INR missing for 2026-08 -> amount_eur NULL"),
         ("rateType", "attribute", "No", "M = monthly average", "Internal", "")]),
    "ariba_sourcing/requests": (
        "Sourcing requests (intake)", "SAP Ariba Sourcing (intake)", "ariba_sourcing_requests_YYYYMMDD_page_NNN.json",
        "JSON, paginated API: `{result:[...], meta:{page, page_size, total, next_page}}`; every value is text",
        "One row per request", "request_id", "Batch, pages of 100", "RAW.ARIBA_SOURCING_REQUESTS (VARIANT, one row per page)",
        "Business asks Procurement to buy something. Start of the S2C chain.",
        [("request_id", "text", "No", "Request ID", "Internal", ""),
         ("short_description", "text", "No", "What is needed", "Internal", ""),
         ("category_id", "text", "No", "Requested category", "Internal", ""),
         ("business_unit", "text", "No", "Requesting business unit", "Internal", ""),
         ("estimated_value", "text", "No", "Estimate, as text", "Confidential", "Number stored as text"),
         ("currency", "text", "No", "Currency", "Internal", ""),
         ("requested_by.name", "text", "No", "Requester name", "PII", ""),
         ("requested_by.email", "text", "No", "Requester email", "PII (masked downstream)", ""),
         ("status", "text", "No", "New, In Review, Sourcing, Awarded, Cancelled", "Internal", ""),
         ("created_at", "text", "No", "Created (YYYY-MM-DD HH:MM:SS)", "Internal", ""),
         ("updated_at", "text", "No", "Last update", "Internal", "Sometimes earlier than created_at"),
         ("sla_due_date", "text", "No", "Due date (created + 45 days)", "Internal", ""),
         ("linked_event_id", "text", "Yes", "Sourcing event started for this request", "Internal", "")]),
    "ariba_sourcing/events": (
        "Sourcing events, bids and awards", "SAP Ariba Sourcing", "ariba_sourcing_events_YYYYMMDD*.json",
        "JSON `{records:[...]}`, camelCase, nested request / category / owner / bids[] / award",
        "One row per event; bids[] one row per bid per round", "eventId (bids: eventId + bidId + round)",
        "Batch, full export then deltas", "RAW.ARIBA_SOURCING_EVENTS (VARIANT)",
        "RFI / RFP / RFQ / auctions, with every supplier bid. FLATTEN bids for competition KPIs.",
        [("eventId", "text", "No", "Event ID (Doc...)", "Internal", ""),
         ("eventType", "text", "No", "RFI, RFP, RFQ, Auction", "Internal", ""),
         ("status", "text", "No", "Open, Closed, Completed, Cancelled", "Internal", ""),
         ("request.requestId", "text", "No", "Link to the request", "Internal", ""),
         ("category.id", "text", "No", "Category", "Internal", "CAT-999 = unknown"),
         ("owner.email", "text", "No", "Event owner email", "PII", ""),
         ("openDate / closeDate / awardDate", "ISO timestamp", "awardDate yes", "Timeline", "Internal", "Completed events without awardDate"),
         ("baselineSpend.amount", "number", "No", "Baseline for savings", "Confidential", ""),
         ("bids[]", "array", "No", "Bids: bidId, round, supplier{aribaId,name,vatNumber}, bidAmount", "Confidential", "Same bid duplicated in 4 events; ~12% single bidder"),
         ("award", "object", "Yes", "aribaSupplierId + awardedAmount", "Confidential", "")]),
    "ariba_contracts/contracts": (
        "Contracts", "SAP Ariba Contracts (CLM)", "ariba_contracts_YYYYMMDD*.json",
        "JSON `{contracts:[...]}`, nested supplier / value / term / lineItems[] / amendments[]",
        "One row per contract", "contractId", "Batch, full export then deltas; soft deletes",
        "RAW.ARIBA_CONTRACTS (VARIANT)",
        "Agreements with suppliers. Uses Ariba supplier IDs, matched to SAP by VAT number.",
        [("contractId", "text", "No", "Contract workspace ID (CW...)", "Internal", ""),
         ("supplier.aribaId / vatNumber", "text", "No", "Ariba supplier; VAT used for SAP matching", "Confidential", "4 suppliers not in SAP"),
         ("categoryId", "text", "No", "Category", "Internal", ""),
         ("eventId", "text", "Yes", "Sourcing event that led to it", "Internal", ""),
         ("value.amount", "number", "No", "Contract value EUR", "Confidential", ""),
         ("term.startDate / endDate / signedDate", "date text", "No", "Term", "Internal", "End before start (3), signed after start (4), overlaps (5)"),
         ("term.autoRenew", "mixed", "No", "true/false, 'Y'/'N', 'true'", "Internal", "Mixed boolean types"),
         ("status", "text", "No", "Draft, Active, Expired, Terminated", "Internal", "SCD2 in dbt"),
         ("isDeleted", "boolean", "No", "Soft delete", "Internal", ""),
         ("lineItems[]", "array", "No", "Agreed unit price per material group", "Confidential", "Used for price variance"),
         ("amendments[]", "array", "No", "Value changes", "Confidential", "")]),
    "ariba_contracts/approvals": (
        "Contract approvals", "SAP Ariba Contracts (approval flow)", "ariba_contract_approvals_YYYYMMDD.csv",
        "CSV, comma", "One row per approval step", "approval_id", "Batch", "RAW.ARIBA_CONTRACT_APPROVALS",
        "Approval chain. approver_manager_id builds the org hierarchy (recursive CTE practice).",
        [("approval_id", "text", "No", "Step ID", "Internal", ""),
         ("contract_id", "text", "No", "Contract", "Internal", ""),
         ("step", "int", "No", "1, 2, 3 (higher value -> more steps)", "Internal", ""),
         ("approver_id", "text", "No", "Employee ID", "Internal", ""),
         ("approver_name", "text", "No", "Name", "PII", ""),
         ("approver_email", "text", "No", "Email", "PII (masked downstream)", ""),
         ("approver_manager_id", "text", "Yes", "Manager; empty for the CPO", "Internal", ""),
         ("approver_title", "text", "No", "Job title", "Internal", ""),
         ("decision", "text", "No", "Approved", "Internal", ""),
         ("decided_at", "timestamp", "No", "When", "Internal", "")]),
    "supplier_risk/risk_esg": (
        "Supplier risk and ESG (weekly)", "Third-party risk provider (fictional 'RiskCo')", "supplier_risk_esg_YYYYMMDD.json",
        "JSON `{provider, generatedAt, suppliers:[{supplier, scores, esg, assessedAt, nextReviewDue}]}`",
        "One row per supplier assessment", "vatNumber + generatedAt", "Batch, weekly full file", "RAW.RISK_ESG (VARIANT)",
        "Financial risk (1 low - 9 high) and ESG rating. Not every supplier is assessed.",
        [("supplier.vatNumber", "text", "No", "Join key to SAP STCEG", "Confidential", ""),
         ("supplier.dunsNumber", "text", "No", "D-U-N-S style number", "Internal", ""),
         ("scores.financialRisk", "int", "No", "1-9", "Licensed", "3 out of range (0, 11, 12)"),
         ("scores.paydex / failureScore", "int", "No", "Payment / failure scores", "Licensed", ""),
         ("esg.ecovadisScore", "int", "No", "0-100", "Licensed", ""),
         ("esg.medal", "text", "Yes", "Bronze..Platinum", "Licensed", "Often null"),
         ("assessedAt / nextReviewDue", "date", "No", "Review cycle", "Internal", "10 reviews overdue")]),
    "supplier_risk/risk_events": (
        "Supplier risk events (stream)", "Third-party risk provider (fictional 'RiskCo')", "risk_events_YYYYMMDD_NN.ndjson",
        "NDJSON (one JSON event per line)", "One row per event", "event_id",
        "STREAM: Snowpipe -> stream -> task (about 1 minute)", "RAW.RISK_EVENTS (VARIANT)",
        "Score changes pushed as they happen. Feeds STREAMING.RISK_CURRENT and RISK_ALERTS.",
        [("event_id", "text", "No", "Unique event ID", "Internal", "Wave 12: duplicates"),
         ("event_type", "text", "No", "RISK_SCORE_CHANGED", "Internal", ""),
         ("payload_version", "int", "No", "1 or 2 (v2 adds sanctions_hit, data_provider_ref)", "Internal", "Wave 12: version 3 -> dead letter"),
         ("supplier_vat", "text", "No", "Supplier VAT", "Confidential", "Wave 12: empty"),
         ("risk_score", "int", "No", "1-9", "Licensed", "Wave 12: 15 and 'high'"),
         ("previous_score", "int", "Yes", "Score before", "Licensed", ""),
         ("reason", "text", "Yes", "Why it changed", "Internal", ""),
         ("event_time", "ISO timestamp", "No", "When it happened (UTC)", "Internal", "Wave 12: out of order and 6 hours late"),
         ("sanctions_hit", "boolean", "v2 only", "Supplier on a sanctions list", "Confidential", "")]),
    "reference/categories": (
        "Category taxonomy", "Category management (UNSPSC mapped to SAP material groups)", "category_taxonomy_YYYYMMDD.csv",
        "CSV, comma", "One row per category", "category_id", "Batch, on change", "RAW.REF_CATEGORIES",
        "3 levels: Direct/Indirect -> family -> leaf. Leaf has the SAP material group.",
        [("category_id", "text", "No", "CAT-xxx", "Internal", ""),
         ("category_name", "text", "No", "Name", "Internal", ""),
         ("parent_category_id", "text", "Yes", "Parent (empty at level 1)", "Internal", "Use for recursive CTEs"),
         ("level", "int", "No", "1, 2, 3", "Internal", ""),
         ("unspsc_code", "text", "Yes", "UNSPSC code (leaf)", "Internal", ""),
         ("sap_material_group", "text", "Yes", "SAP MATKL (leaf)", "Internal", ""),
         ("is_active", "Y/N", "No", "Active flag", "Internal", "2 inactive categories still used on POs"),
         ("valid_from / valid_to", "date", "No", "Validity", "Internal", ""),
         ("updated_at", "timestamp", "No", "Last change", "Internal", "")]),
    "reference/savings_tracker": (
        "Savings tracker (manual Excel)", "Excel on SharePoint, kept by Procurement Finance", "savings_tracker_fy2026_YYYYMMDD.xlsx",
        "Excel: title on row 1, header on row 3, blank rows, TOTAL row with a formula. Converted to CSV on upload (+ _sheet_row).",
        "One row per savings line", "Savings ID", "Batch, weekly, full file", "RAW.MANUAL_SAVINGS",
        "Savings claimed per sourcing event. Must be validated against event data.",
        [("Savings ID", "text", "No", "SAV-nnnn", "Internal", "Pasted duplicate rows; TOTAL row"),
         ("Event ID", "text", "No", "Sourcing event", "Internal", ""),
         ("Category / Supplier", "text", "No", "Names typed by hand", "Internal", ""),
         ("Baseline (EUR)", "number", "No", "Baseline", "Confidential", ""),
         ("Negotiated (EUR)", "number", "No", "Awarded value", "Confidential", ""),
         ("Savings (EUR)", "number", "No", "Should be Baseline - Negotiated", "Confidential", "5 rows do not add up"),
         ("Savings Date", "date or text", "No", "Real Excel dates mixed with dd/mm/yyyy text", "Internal", "Parse as DD/MM, never MM/DD"),
         ("Validated by Finance", "text", "No", "Yes / yes / Y / No", "Internal", "Normalise"),
         ("Owner", "text", "No", "Name", "PII", ""),
         ("Comments", "text", "Yes", "Free text", "Internal", "")]),
}


def sample_lines(entity: str) -> str:
    d = INIT / entity
    files = sorted(p for p in d.glob("*") if p.is_file()) if d.exists() else []
    if not files:
        return "_(no sample in data/initial)_"
    f = files[0]
    if f.suffix == ".csv":
        txt = f.read_text(encoding="utf-8").splitlines()[:4]
        return "```text\n" + "\n".join(txt) + "\n```"
    if f.suffix == ".json":
        doc = json.loads(f.read_text(encoding="utf-8"))
        for k in ("result", "records", "contracts", "suppliers"):
            if isinstance(doc, dict) and k in doc:
                doc = {**{kk: vv for kk, vv in doc.items() if kk != k}, k: doc[k][:1]}
                break
        return "```json\n" + json.dumps(doc, indent=2, ensure_ascii=False)[:1800] + "\n```"
    if f.suffix == ".xml":
        return "```xml\n" + "\n".join(f.read_text(encoding="utf-8").splitlines()[:22]) + "\n```"
    if f.suffix == ".xlsx":
        return "Excel: open `" + f.relative_to(ROOT).as_posix() + "` (title row 1, header row 3)."
    return f"`{f.name}` ({f.suffix})"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = ["# Data dictionary", "", "One page per source entity. Generated by `generator/build_docs.py`.", "",
             "| Entity | Source system | Format | Grain | Key | Load | RAW table |", "|---|---|---|---|---|---|---|"]
    for ent, (title, system, pattern, fmt, grain, key, load, raw, desc, cols) in DICT.items():
        fname = ent.replace("/", "__") + ".md"
        md = [f"# {title}", "", desc, "",
              "| | |", "|---|---|",
              f"| **Entity folder** | `data/*/{ent}/` |",
              f"| **Source system** | {system} |",
              f"| **File name** | `{pattern}` |",
              f"| **Format** | {fmt} |",
              f"| **Grain** | {grain} |",
              f"| **Business key** | `{key}` |",
              f"| **Load pattern** | {load} |",
              f"| **RAW table** | `{raw}` |",
              "", "## Columns", "",
              "| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |",
              "|---|---|---|---|---|---|"]
        md += [f"| `{c[0]}` | {c[1]} | {c[2]} | {c[3]} | {c[4]} | {c[5]} |" for c in cols]
        md += ["", "## RAW lineage columns (every table)", "",
               "`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), "
               "`_FILE_LAST_MODIFIED`, `_LOADED_AT`.", "", "## Sample", "", sample_lines(ent), ""]
        (OUT / fname).write_text("\n".join(md), encoding="utf-8")
        index.append(f"| [{title}]({fname}) | {system} | {fmt.split(',')[0]} | {grain} | `{key}` | {load.split(',')[0]} | `{raw.split(' ')[0]}` |")
    (OUT / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"Wrote {len(DICT)} pages to {OUT.relative_to(ROOT)}")
    build_drop_plan()


def build_drop_plan() -> None:
    import collections
    waves = json.loads((ROOT / "answer_key" / "waves.json").read_text())
    planted = list(csv.DictReader(open(ROOT / "answer_key" / "planted_issues.csv", encoding="utf-8")))
    by_wave = collections.defaultdict(list)
    for p in planted:
        by_wave[p["wave"]].append(p)
    md = ["# Drop plan: initial load + 12 waves", "",
          "Push the initial load first, then drop one wave at a time and watch what happens.", "",
          "```bash", "python scripts/drop_wave.py --list      # status of every wave",
          "python scripts/drop_wave.py 1 --push    # copy wave 1 into data/incoming/, commit, push", "```", "",
          "Each wave's files and expected behaviour are also in `pending/wave_NN/WAVE.md`.", "",
          "| Wave | Path | What arrives | What should happen | Planted issues |", "|---|---|---|---|---|"]
    init = by_wave.get("initial", [])
    md.append(f"| initial | Batch | Full history for every source (Jan-Oct 2026) | Everything lands; business "
              f"issues are left for dbt | {len(init)} |")
    for w in waves:
        n = w["wave"]
        md.append(f"| {n:02d} | {w['path']} | {w['what']} | {w['expect']} | {len(by_wave.get(f'wave_{n:02d}', []))} |")
    md += ["", "## Planted issues by type", "", "| Issue type | Count | Caught by | Expected check |", "|---|---|---|---|"]
    agg = collections.OrderedDict()
    for p in planted:
        k = p["issue_type"]
        if k not in agg:
            agg[k] = [0, p["caught_by"], p["expected_check"]]
        agg[k][0] += 1
    for k, (c, by, chk) in sorted(agg.items(), key=lambda x: (x[1][1], x[0])):
        md.append(f"| {k} | {c} | {by} | {chk} |")
    md += ["", f"Total planted issues: **{len(planted)}**. Full list: `answer_key/planted_issues.csv`.",
           "Check them against Snowflake with `python scripts/check_planted.py`.", ""]
    (ROOT / "docs" / "drop_plan.md").write_text("\n".join(md), encoding="utf-8")
    print("Wrote docs/drop_plan.md")


if __name__ == "__main__":
    main()
