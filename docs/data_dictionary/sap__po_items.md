# Purchase order lines

Every purchase order line. The core of spend analytics.

| | |
|---|---|
| **Entity folder** | `data/*/sap/po_items/` |
| **Source system** | SAP S/4HANA (MM: EKKO/EKPO) |
| **File name** | `sap_po_items_ekpo_YYYYMMDD*.csv` |
| **Format** | CSV, `;` separated, decimal comma, SAP column names |
| **Grain** | One row per PO line |
| **Business key** | `EBELN + EBELP` |
| **Load pattern** | Batch, daily delta; changed lines re-sent with a new AEDAT |
| **RAW table** | `RAW.SAP_PO_ITEMS` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `EBELN` | CHAR(10) | No | Purchase order number | Internal | Wave 6: missing in shifted rows |
| `EBELP` | NUMC(5) | No | PO line number with leading zeros (00010) | Internal | Keep as text, never as number |
| `BUKRS` | CHAR(4) | No | Company code (business unit) | Internal |  |
| `LIFNR` | CHAR(10) | No | SAP supplier number with leading zeros | Internal | Wave 6: empty; blocked suppliers used |
| `BEDAT` | DATS | No | PO date YYYYMMDD | Internal | Wave 6: invalid date 20261345 |
| `MATKL` | CHAR(9) | No | Material group, maps to category | Internal | ZZ-MISC unknown; PK-LFL / IT-SRV inactive |
| `TXZ01` | CHAR(40) | Yes | Short text | Internal | Trailing spaces; wave 6: `;` inside text, Latin-1 bytes |
| `MENGE` | QUAN | No | Quantity, decimal comma (388,000) | Internal | Wave 6: shifted text |
| `MEINS` | UNIT | No | Unit of measure | Internal |  |
| `NETPR` | CURR | No | Net price per price unit, decimal comma | Confidential |  |
| `PEINH` | DEC | No | Price unit (usually 1) | Internal |  |
| `NETWR` | CURR | No | Net value = MENGE x NETPR / PEINH | Confidential | 4 lines do not add up; wave 6: 'n/a' |
| `WAERS` | CUKY | No | Currency (EUR, USD, GBP, CHF, CNY, INR) | Internal | Wave 9: renamed to CURRENCY |
| `KOSTL` | CHAR(10) | No | Cost centre | Internal | 6 lines charged to closed cost centres |
| `KONNR` | CHAR(10) | Yes | Contract ID; empty = no contract (maverick) | Internal |  |
| `LOEKZ` | CHAR(1) | Yes | Deletion flag, L = deleted in SAP | Internal | Deleted lines are kept and flagged |
| `AEDAT` | DATS | No | Last changed date YYYYMMDD; use to pick the latest version | Internal |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

```text
EBELN;EBELP;BUKRS;LIFNR;BEDAT;MATKL;TXZ01;MENGE;MEINS;NETPR;PEINH;NETWR;WAERS;KOSTL;KONNR;LOEKZ;AEDAT
4500000045;00010;2000;0000100175;20260101;LB-CON;Lab consumables;388,000;BOX;25,99;1;10084,12;CHF;0000007100;;;20260101
4500000048;00010;5000;0000100163;20260101;PS-CON;Management consulting;3,000;DAY;1549,93;1;4649,79;USD;0000013100;;;20260102
4500000330;00010;2000;0000100106;20260101;RM-API;Active pharmaceutical ingredients;2,000;KG;2842,91;1;5685,82;INR;0000008100;;;20260101
```
