# Sourcing requests (intake)

Business asks Procurement to buy something. Start of the S2C chain.

| | |
|---|---|
| **Entity folder** | `data/*/ariba_sourcing/requests/` |
| **Source system** | SAP Ariba Sourcing (intake) |
| **File name** | `ariba_sourcing_requests_YYYYMMDD_page_NNN.json` |
| **Format** | JSON, paginated API: `{result:[...], meta:{page, page_size, total, next_page}}`; every value is text |
| **Grain** | One row per request |
| **Business key** | `request_id` |
| **Load pattern** | Batch, pages of 100 |
| **RAW table** | `RAW.ARIBA_SOURCING_REQUESTS (VARIANT, one row per page)` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `request_id` | text | No | Request ID | Internal |  |
| `short_description` | text | No | What is needed | Internal |  |
| `category_id` | text | No | Requested category | Internal |  |
| `business_unit` | text | No | Requesting business unit | Internal |  |
| `estimated_value` | text | No | Estimate, as text | Confidential | Number stored as text |
| `currency` | text | No | Currency | Internal |  |
| `requested_by.name` | text | No | Requester name | PII |  |
| `requested_by.email` | text | No | Requester email | PII (masked downstream) |  |
| `status` | text | No | New, In Review, Sourcing, Awarded, Cancelled | Internal |  |
| `created_at` | text | No | Created (YYYY-MM-DD HH:MM:SS) | Internal |  |
| `updated_at` | text | No | Last update | Internal | Sometimes earlier than created_at |
| `sla_due_date` | text | No | Due date (created + 45 days) | Internal |  |
| `linked_event_id` | text | Yes | Sourcing event started for this request | Internal |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

```json
{
  "meta": {
    "page": 1,
    "page_size": 100,
    "total": 300,
    "next_page": 2
  },
  "result": [
    {
      "request_id": "REQ1001001",
      "short_description": "Lab consumables for R&D",
      "category_id": "CAT-131",
      "business_unit": "R&D",
      "estimated_value": "787000",
      "currency": "EUR",
      "requested_by": {
        "name": "Liam Miller",
        "email": "liam.miller@samplepharma.example"
      },
      "status": "Awarded",
      "created_at": "2025-12-08 13:00:00",
      "updated_at": "2025-12-29 15:00:00",
      "sla_due_date": "2026-01-22",
      "linked_event_id": "Doc6100102"
    }
  ]
}
```
