# Contract approvals

Approval chain. approver_manager_id builds the org hierarchy (recursive CTE practice).

| | |
|---|---|
| **Entity folder** | `data/*/ariba_contracts/approvals/` |
| **Source system** | SAP Ariba Contracts (approval flow) |
| **File name** | `ariba_contract_approvals_YYYYMMDD.csv` |
| **Format** | CSV, comma |
| **Grain** | One row per approval step |
| **Business key** | `approval_id` |
| **Load pattern** | Batch |
| **RAW table** | `RAW.ARIBA_CONTRACT_APPROVALS` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `approval_id` | text | No | Step ID | Internal |  |
| `contract_id` | text | No | Contract | Internal |  |
| `step` | int | No | 1, 2, 3 (higher value -> more steps) | Internal |  |
| `approver_id` | text | No | Employee ID | Internal |  |
| `approver_name` | text | No | Name | PII |  |
| `approver_email` | text | No | Email | PII (masked downstream) |  |
| `approver_manager_id` | text | Yes | Manager; empty for the CPO | Internal |  |
| `approver_title` | text | No | Job title | Internal |  |
| `decision` | text | No | Approved | Internal |  |
| `decided_at` | timestamp | No | When | Internal |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

```text
approval_id,contract_id,step,approver_id,approver_name,approver_email,approver_manager_id,approver_title,decision,decided_at
APR-00001,CW1000001,1,E022,Anna Patel,anna.patel@samplepharma.example,E006,Buyer,Approved,2026-10-04T10:00:00Z
APR-00002,CW1000001,2,E006,Hugo Silva,hugo.silva@samplepharma.example,E002,Category Manager,Approved,2026-10-08T10:00:00Z
APR-00003,CW1000002,1,E019,Mila Kowalski,mila.kowalski@samplepharma.example,E011,Buyer,Approved,2026-07-15T10:00:00Z
```
