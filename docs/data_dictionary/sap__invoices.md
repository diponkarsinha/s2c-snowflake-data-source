# Supplier invoice lines

Invoices posted against PO lines. Credit memos and reversals are negative.

| | |
|---|---|
| **Entity folder** | `data/*/sap/invoices/` |
| **Source system** | SAP S/4HANA (FI: RBKP/RSEG) |
| **File name** | `sap_invoices_rseg_YYYYMMDD.parquet` |
| **Format** | Parquet, typed columns (DATE, DOUBLE, INT) |
| **Grain** | One row per invoice line |
| **Business key** | `BELNR + GJAHR + BUZEI` |
| **Load pattern** | Batch, daily delta |
| **RAW table** | `RAW.SAP_INVOICES (VARIANT)` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `BELNR` | string | No | Invoice document number | Internal |  |
| `GJAHR` | int32 | No | Fiscal year | Internal |  |
| `BUZEI` | int32 | No | Line inside the invoice | Internal |  |
| `BLDAT` | date | No | Document date | Internal |  |
| `BUDAT` | date | No | Posting date | Internal | Wave 7: September invoices arrive in November (late) |
| `CPUDT` | date | No | Entry date (change tracking) | Internal |  |
| `LIFNR` | string | No | SAP supplier number | Internal |  |
| `EBELN` | string | No | PO number | Internal | 5 orphan invoices point to non-existent POs |
| `EBELP` | string | No | PO line | Internal | 3 invoices on deleted PO lines |
| `MENGE` | double | No | Invoiced quantity (negative on credit memos) | Internal | 6 lines above ordered quantity |
| `WRBTR` | double | No | Amount in document currency | Confidential | 20 lines priced above PO price |
| `WAERS` | string | No | Currency | Internal |  |
| `SHKZG` | string | No | S = debit, H = credit | Internal | 15 credit memos, 5 reversals |
| `XBLNR` | string | Yes | Supplier's invoice reference | Internal |  |
| `STBLG` | string | Yes | Reversed document number | Internal |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

`sap_invoices_rseg_20261031.parquet` (.parquet)
