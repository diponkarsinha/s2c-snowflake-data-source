# Source-to-target mapping

From the RAW tables in this repo to the dbt staging models in **s2c-dbt-analytics**. Staging only renames, casts, cleans and de-duplicates. Business logic starts in intermediate.

Conventions used in every staging model:

- Rows from `AUDIT.V_ROW_DQ_STATUS` with `DQ_STATUS = 'ERROR'` go to a `*_quarantine` model, not to staging
- CSV RAW tables: `WHERE _FILE_ROW_NUMBER > 1` (row 1 is the header)
- Keep `_FILE_NAME` and `_LOADED_AT` as `source_file` and `loaded_at` for lineage
- One row per business key: `QUALIFY ROW_NUMBER() OVER (PARTITION BY <key> ORDER BY <change date> DESC, _LOADED_AT DESC) = 1`

## RAW.SAP_PO_ITEMS → stg_sap__po_items

| RAW column | Target column | Transformation |
|---|---|---|
| `EBELN` | `po_number` | as text |
| `EBELP` | `po_line_number` | as text (keep leading zeros) |
| `EBELN \|\| '-' \|\| EBELP` | `po_item_key` | business key |
| `BUKRS` | `company_code` | |
| `LIFNR` | `sap_supplier_id` | as text (keep leading zeros) |
| `BEDAT` | `po_date` | `TRY_TO_DATE(BEDAT, 'YYYYMMDD')` |
| `MATKL` | `material_group` | `TRIM` |
| `TXZ01` | `item_text` | `TRIM`, replace U+FFFD |
| `MENGE` | `quantity` | `TRY_TO_NUMBER(REPLACE(MENGE, ',', '.'), 18, 3)` |
| `MEINS` | `unit_of_measure` | |
| `NETPR` | `net_price` | decimal comma → number |
| `PEINH` | `price_unit` | number, default 1 |
| `NETWR` | `net_value` | decimal comma → number |
| `WAERS` (or `CURRENCY` after drift) | `currency` | `COALESCE` over both header versions |
| `KOSTL` | `cost_center_id` | |
| `KONNR` | `contract_id` | `NULLIF(TRIM(KONNR), '')` |
| `LOEKZ` | `is_deleted` | `LOEKZ = 'L'` |
| `AEDAT` | `changed_on` | `TRY_TO_DATE(AEDAT, 'YYYYMMDD')`, used for "latest version" |

## RAW.SAP_INVOICES → stg_sap__invoices

| RAW path | Target | Transformation |
|---|---|---|
| `RAW:"BELNR"`, `"GJAHR"`, `"BUZEI"` | `invoice_item_key` | concatenated business key |
| `RAW:"BUDAT"` | `posting_date` | `TRY_TO_DATE(...::STRING)` |
| `RAW:"EBELN"`, `"EBELP"` | `po_item_key` | |
| `RAW:"MENGE"` | `quantity` | number (negative on credit) |
| `RAW:"WRBTR"` | `amount` | number |
| `RAW:"SHKZG"` | `is_credit` | `= 'H'` |
| `RAW:"STBLG"` | `reversed_invoice_number` | |

## RAW.SAP_SUPPLIERS → stg_sap__suppliers (+ snapshot)

| RAW path | Target | Transformation |
|---|---|---|
| `XMLGET(XMLGET(RAW,'E1LFA1M'),'LIFNR'):"$"` | `sap_supplier_id` | |
| `...'NAME1'` | `supplier_name` | `TRIM`, collapse double spaces |
| `...'STCEG'` | `vat_number` | upper, no spaces: **cross-system key** |
| `...'SPERR'` | `is_blocked` | `= 'X'` |
| `...'ORT01'` | `city` | empty tag → NULL |
| `XMLGET(XMLGET(XMLGET(RAW,'E1LFA1M'),'E1LFBKM'),'IBAN'):"$"` | `iban` | masked downstream |
| `...'UPDAT'` | `changed_on` | snapshot `updated_at` |

## RAW.SAP_FX_RATES → stg_sap__fx_rates

| RAW path | Target | Transformation |
|---|---|---|
| `GET(RAW, '@time')` | `rate_month` | `TO_DATE(... || '-01')` |
| `FLATTEN(RAW:"$")` → `GET(value, '@currency')` | `from_currency` | |
| `GET(value, '@rate')` | `rate_per_eur` | `amount_eur = amount / rate`; EUR = 1 |

## RAW.ARIBA_SOURCING_REQUESTS → stg_ariba__requests

`FLATTEN(RAW:result)`, one row per request; latest by `updated_at` across pages and files. `estimated_value` text → number. `requested_by.email` → masked.

## RAW.ARIBA_SOURCING_EVENTS → stg_ariba__sourcing_events, stg_ariba__bids

Events: `FLATTEN(RAW:records)`. Bids: second `FLATTEN(event.value:bids)`, dedup on `eventId + bidId + round`.

## RAW.ARIBA_CONTRACTS → stg_ariba__contracts (+ snapshot), stg_ariba__contract_lines

`FLATTEN(RAW:contracts)`; `autoRenew` normalised with a macro (`true`, `'Y'`, `'true'` → TRUE); `isDeleted = TRUE` rows kept but flagged; latest by `lastStatusChangeAt`.

## RAW.RISK_ESG, STREAMING.RISK_CURRENT → stg_risk__assessments, stg_risk__current

Assessments: `FLATTEN(RAW:suppliers)`; score outside 1-9 → NULL. Current: read directly from the speed layer.

## RAW.MANUAL_SAVINGS → stg_manual__savings

Drop TOTAL and blank rows; `Savings Date`: `COALESCE(TRY_TO_DATE(x,'YYYY-MM-DD'), TRY_TO_DATE(x,'DD/MM/YYYY'))`; `Validated by Finance`: `UPPER(LEFT(x,1)) = 'Y'`; dedup on `Savings ID` (pasted rows).

## RAW.REF_CATEGORIES, SAP_COST_CENTERS, ARIBA_CONTRACT_APPROVALS

Straight renames and casts; `is_active = 'Y'`; `valid_to = '9999-12-31'` means open.
