"""
Source configuration shared by every script.

One entry per entity = one folder under data/initial/ and data/incoming/:

    data/<initial|incoming>/<source>/<entity>/<any sub folders>/<file>

Keep this file in step with snowflake/04_audit_tables.sql (INGEST_CONFIG).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    key: str                 # "<source>/<entity>"
    source_system: str
    load_mode: str           # BATCH | STREAM
    file_type: str           # CSV | JSON | NDJSON | XML | PARQUET | XLSX
    stage: str               # stage name inside S2C_<ENV>.RAW
    stage_prefix: str        # folder inside the stage (must match COPY / PIPE definitions)
    raw_table: str
    csv_delimiter: str | None = None
    expected_header: tuple[str, ...] | None = None
    json_records_key: str | None = None   # where the records live inside a JSON document


PO_HEADER = ("EBELN", "EBELP", "BUKRS", "LIFNR", "BEDAT", "MATKL", "TXZ01", "MENGE", "MEINS",
             "NETPR", "PEINH", "NETWR", "WAERS", "KOSTL", "KONNR", "LOEKZ", "AEDAT")

ENTITIES: dict[str, Entity] = {e.key: e for e in [
    # ------------------------------------------------------------------ SAP ERP
    Entity("sap/po_items", "SAP ERP", "BATCH", "CSV", "STG_BATCH", "sap/po_items", "SAP_PO_ITEMS",
           csv_delimiter=";", expected_header=PO_HEADER),
    Entity("sap/invoices", "SAP ERP", "BATCH", "PARQUET", "STG_BATCH", "sap/invoices", "SAP_INVOICES"),
    Entity("sap/suppliers", "SAP ERP", "BATCH", "XML", "STG_BATCH", "sap/suppliers", "SAP_SUPPLIERS"),
    Entity("sap/cost_centers", "SAP ERP", "BATCH", "CSV", "STG_BATCH", "sap/cost_centers", "SAP_COST_CENTERS",
           csv_delimiter=",", expected_header=("kostl", "kokrs", "bukrs", "cost_center_name", "business_unit",
                                               "responsible", "valid_from", "valid_to", "updated_at")),
    Entity("sap/fx_rates", "SAP ERP", "BATCH", "XML", "STG_BATCH", "sap/fx_rates", "SAP_FX_RATES"),
    # ----------------------------------------------------------- Ariba Sourcing
    Entity("ariba_sourcing/requests", "Ariba Sourcing", "BATCH", "JSON", "STG_BATCH", "ariba_sourcing/requests",
           "ARIBA_SOURCING_REQUESTS", json_records_key="result"),
    Entity("ariba_sourcing/events", "Ariba Sourcing", "BATCH", "JSON", "STG_BATCH", "ariba_sourcing/events",
           "ARIBA_SOURCING_EVENTS", json_records_key="records"),
    # ---------------------------------------------------------- Ariba Contracts
    Entity("ariba_contracts/contracts", "Ariba Contracts", "BATCH", "JSON", "STG_BATCH",
           "ariba_contracts/contracts", "ARIBA_CONTRACTS", json_records_key="contracts"),
    Entity("ariba_contracts/approvals", "Ariba Contracts", "BATCH", "CSV", "STG_BATCH",
           "ariba_contracts/approvals", "ARIBA_CONTRACT_APPROVALS", csv_delimiter=",",
           expected_header=("approval_id", "contract_id", "step", "approver_id", "approver_name",
                            "approver_email", "approver_manager_id", "approver_title", "decision", "decided_at")),
    # ------------------------------------------------------------ Supplier risk
    Entity("supplier_risk/risk_esg", "Supplier Risk", "BATCH", "JSON", "STG_BATCH", "supplier_risk/risk_esg",
           "RISK_ESG", json_records_key="suppliers"),
    Entity("supplier_risk/risk_events", "Supplier Risk", "STREAM", "NDJSON", "STG_STREAM", "risk_events",
           "RISK_EVENTS"),
    # ------------------------------------------------------- Reference / manual
    Entity("reference/categories", "Reference", "BATCH", "CSV", "STG_BATCH", "reference/categories",
           "REF_CATEGORIES", csv_delimiter=",",
           expected_header=("category_id", "category_name", "parent_category_id", "level", "unspsc_code",
                            "sap_material_group", "is_active", "valid_from", "valid_to", "updated_at")),
    Entity("reference/savings_tracker", "Reference", "BATCH", "XLSX", "STG_BATCH", "reference/savings_tracker",
           "MANUAL_SAVINGS", csv_delimiter=",",
           expected_header=("_sheet_row", "Savings ID", "Event ID", "Category", "Supplier", "Baseline (EUR)",
                            "Negotiated (EUR)", "Savings (EUR)", "Savings Date", "Validated by Finance",
                            "Owner", "Comments")),
]}

PIPE_NAME = "RAW.PIPE_RISK_EVENTS"      # loads STG_STREAM/risk_events/


def entity_for_path(repo_path: str) -> Entity | None:
    """data/<initial|incoming>/<source>/<entity>/... -> Entity, or None if not a data file."""
    parts = repo_path.replace("\\", "/").split("/")
    if len(parts) < 5 or parts[0] != "data" or parts[1] not in ("initial", "incoming"):
        return None
    return ENTITIES.get(f"{parts[2]}/{parts[3]}")
