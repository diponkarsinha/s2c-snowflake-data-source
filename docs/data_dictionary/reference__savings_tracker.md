# Savings tracker (manual Excel)

Savings claimed per sourcing event. Must be validated against event data.

| | |
|---|---|
| **Entity folder** | `data/*/reference/savings_tracker/` |
| **Source system** | Excel on SharePoint, kept by Procurement Finance |
| **File name** | `savings_tracker_fy2026_YYYYMMDD.xlsx` |
| **Format** | Excel: title on row 1, header on row 3, blank rows, TOTAL row with a formula. Converted to CSV on upload (+ _sheet_row). |
| **Grain** | One row per savings line |
| **Business key** | `Savings ID` |
| **Load pattern** | Batch, weekly, full file |
| **RAW table** | `RAW.MANUAL_SAVINGS` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `Savings ID` | text | No | SAV-nnnn | Internal | Pasted duplicate rows; TOTAL row |
| `Event ID` | text | No | Sourcing event | Internal |  |
| `Category / Supplier` | text | No | Names typed by hand | Internal |  |
| `Baseline (EUR)` | number | No | Baseline | Confidential |  |
| `Negotiated (EUR)` | number | No | Awarded value | Confidential |  |
| `Savings (EUR)` | number | No | Should be Baseline - Negotiated | Confidential | 5 rows do not add up |
| `Savings Date` | date or text | No | Real Excel dates mixed with dd/mm/yyyy text | Internal | Parse as DD/MM, never MM/DD |
| `Validated by Finance` | text | No | Yes / yes / Y / No | Internal | Normalise |
| `Owner` | text | No | Name | PII |  |
| `Comments` | text | Yes | Free text | Internal |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

Excel: open `data/initial/reference/savings_tracker/savings_tracker_fy2026_20261030.xlsx` (title row 1, header row 3).
