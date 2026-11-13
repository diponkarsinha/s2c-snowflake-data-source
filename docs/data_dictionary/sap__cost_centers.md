# Cost centres

Who pays. Closed cost centres have valid_to in the past.

| | |
|---|---|
| **Entity folder** | `data/*/sap/cost_centers/` |
| **Source system** | SAP S/4HANA (CO: CSKS/CSKT) |
| **File name** | `sap_cost_centers_csks_YYYYMMDD.csv` |
| **Format** | CSV, comma |
| **Grain** | One row per cost centre |
| **Business key** | `kostl` |
| **Load pattern** | Batch, full reload |
| **RAW table** | `RAW.SAP_COST_CENTERS` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `kostl` | CHAR(10) | No | Cost centre number | Internal |  |
| `kokrs` | CHAR(4) | No | Controlling area | Internal |  |
| `bukrs` | CHAR(4) | No | Company code | Internal |  |
| `cost_center_name` | text | No | Name | Internal |  |
| `business_unit` | text | No | Business unit | Internal |  |
| `responsible` | text | No | Person responsible | PII (name) |  |
| `valid_from` | date | No | Valid from | Internal |  |
| `valid_to` | date | No | Valid to; 9999-12-31 = open | Internal | 3 closed on 2026-06-30 but still charged |
| `updated_at` | timestamp | No | Last change | Internal |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

```text
kostl,kokrs,bukrs,cost_center_name,business_unit,responsible,valid_from,valid_to,updated_at
0000001100,SP01,1000,Plant Operations,Pharmaceuticals,Ben Garcia,2015-01-01,9999-12-31,2025-01-05T06:00:00Z
0000002100,SP01,2000,Quality Control,MedTech,Felix Kowalski,2015-01-01,9999-12-31,2025-01-05T06:00:00Z
0000003100,SP01,3000,Packaging Line,Consumer Health,Mila Kowalski,2015-01-01,9999-12-31,2025-01-05T06:00:00Z
```
