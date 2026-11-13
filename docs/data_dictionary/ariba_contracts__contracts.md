# Contracts

Agreements with suppliers. Uses Ariba supplier IDs, matched to SAP by VAT number.

| | |
|---|---|
| **Entity folder** | `data/*/ariba_contracts/contracts/` |
| **Source system** | SAP Ariba Contracts (CLM) |
| **File name** | `ariba_contracts_YYYYMMDD*.json` |
| **Format** | JSON `{contracts:[...]}`, nested supplier / value / term / lineItems[] / amendments[] |
| **Grain** | One row per contract |
| **Business key** | `contractId` |
| **Load pattern** | Batch, full export then deltas; soft deletes |
| **RAW table** | `RAW.ARIBA_CONTRACTS (VARIANT)` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `contractId` | text | No | Contract workspace ID (CW...) | Internal |  |
| `supplier.aribaId / vatNumber` | text | No | Ariba supplier; VAT used for SAP matching | Confidential | 4 suppliers not in SAP |
| `categoryId` | text | No | Category | Internal |  |
| `eventId` | text | Yes | Sourcing event that led to it | Internal |  |
| `value.amount` | number | No | Contract value EUR | Confidential |  |
| `term.startDate / endDate / signedDate` | date text | No | Term | Internal | End before start (3), signed after start (4), overlaps (5) |
| `term.autoRenew` | mixed | No | true/false, 'Y'/'N', 'true' | Internal | Mixed boolean types |
| `status` | text | No | Draft, Active, Expired, Terminated | Internal | SCD2 in dbt |
| `isDeleted` | boolean | No | Soft delete | Internal |  |
| `lineItems[]` | array | No | Agreed unit price per material group | Confidential | Used for price variance |
| `amendments[]` | array | No | Value changes | Confidential |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

```json
{
  "count": 268,
  "contracts": [
    {
      "contractId": "CW1000001",
      "title": "Management consulting agreement - Harbor Packaging GmbH",
      "supplier": {
        "aribaId": "S2000026",
        "name": "Harbor Packaging GmbH",
        "vatNumber": "DE173574218"
      },
      "categoryId": "CAT-221",
      "eventId": "Doc6100001",
      "value": {
        "amount": 715540.69,
        "currency": "EUR"
      },
      "term": {
        "startDate": "2026-10-24",
        "endDate": "2028-10-22",
        "signedDate": "2026-10-12",
        "noticePeriodDays": 30,
        "autoRenew": "N"
      },
      "status": "Active",
      "owner": {
        "name": "Jonas Schmidt",
        "email": "jonas.schmidt@samplepharma.example"
      },
      "isDeleted": false,
      "lastStatusChangeAt": "2026-10-24T09:00:00Z",
      "lineItems": [
        {
          "lineNo": 10,
          "materialGroup": "PS-CON",
          "description": "Management consulting",
          "unitPrice": 2170.23,
          "uom": "DAY"
        }
      ],
      "amendments": []
    }
  ]
}
```
