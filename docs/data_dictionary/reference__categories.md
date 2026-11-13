# Category taxonomy

3 levels: Direct/Indirect -> family -> leaf. Leaf has the SAP material group.

| | |
|---|---|
| **Entity folder** | `data/*/reference/categories/` |
| **Source system** | Category management (UNSPSC mapped to SAP material groups) |
| **File name** | `category_taxonomy_YYYYMMDD.csv` |
| **Format** | CSV, comma |
| **Grain** | One row per category |
| **Business key** | `category_id` |
| **Load pattern** | Batch, on change |
| **RAW table** | `RAW.REF_CATEGORIES` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `category_id` | text | No | CAT-xxx | Internal |  |
| `category_name` | text | No | Name | Internal |  |
| `parent_category_id` | text | Yes | Parent (empty at level 1) | Internal | Use for recursive CTEs |
| `level` | int | No | 1, 2, 3 | Internal |  |
| `unspsc_code` | text | Yes | UNSPSC code (leaf) | Internal |  |
| `sap_material_group` | text | Yes | SAP MATKL (leaf) | Internal |  |
| `is_active` | Y/N | No | Active flag | Internal | 2 inactive categories still used on POs |
| `valid_from / valid_to` | date | No | Validity | Internal |  |
| `updated_at` | timestamp | No | Last change | Internal |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

```text
category_id,category_name,parent_category_id,level,unspsc_code,sap_material_group,is_active,valid_from,valid_to,updated_at
CAT-100,Direct materials,,1,,,Y,2015-01-01,9999-12-31,2026-01-02T08:00:00Z
CAT-200,Indirect spend,,1,,,Y,2015-01-01,9999-12-31,2026-01-02T08:00:00Z
CAT-110,Raw materials,CAT-100,2,,,Y,2015-01-01,9999-12-31,2026-01-02T08:00:00Z
```
