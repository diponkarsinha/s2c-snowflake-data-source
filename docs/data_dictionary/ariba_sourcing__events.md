# Sourcing events, bids and awards

RFI / RFP / RFQ / auctions, with every supplier bid. FLATTEN bids for competition KPIs.

| | |
|---|---|
| **Entity folder** | `data/*/ariba_sourcing/events/` |
| **Source system** | SAP Ariba Sourcing |
| **File name** | `ariba_sourcing_events_YYYYMMDD*.json` |
| **Format** | JSON `{records:[...]}`, camelCase, nested request / category / owner / bids[] / award |
| **Grain** | One row per event; bids[] one row per bid per round |
| **Business key** | `eventId (bids: eventId + bidId + round)` |
| **Load pattern** | Batch, full export then deltas |
| **RAW table** | `RAW.ARIBA_SOURCING_EVENTS (VARIANT)` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `eventId` | text | No | Event ID (Doc...) | Internal |  |
| `eventType` | text | No | RFI, RFP, RFQ, Auction | Internal |  |
| `status` | text | No | Open, Closed, Completed, Cancelled | Internal |  |
| `request.requestId` | text | No | Link to the request | Internal |  |
| `category.id` | text | No | Category | Internal | CAT-999 = unknown |
| `owner.email` | text | No | Event owner email | PII |  |
| `openDate / closeDate / awardDate` | ISO timestamp | awardDate yes | Timeline | Internal | Completed events without awardDate |
| `baselineSpend.amount` | number | No | Baseline for savings | Confidential |  |
| `bids[]` | array | No | Bids: bidId, round, supplier{aribaId,name,vatNumber}, bidAmount | Confidential | Same bid duplicated in 4 events; ~12% single bidder |
| `award` | object | Yes | aribaSupplierId + awardedAmount | Confidential |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

```json
{
  "exportedAt": "2026-10-31T01:00:00Z",
  "records": [
    {
      "eventId": "Doc6100001",
      "title": "Management consulting - R&D 2026",
      "eventType": "Auction",
      "status": "Completed",
      "request": {
        "requestId": "REQ1001219"
      },
      "category": {
        "id": "CAT-221",
        "name": "Management consulting"
      },
      "owner": {
        "name": "Mila Kowalski",
        "email": "mila.kowalski@samplepharma.example"
      },
      "createdDate": "2026-09-05T09:00:00Z",
      "openDate": "2026-09-07T09:00:00Z",
      "closeDate": "2026-09-28T09:00:00Z",
      "awardDate": "2026-10-03T09:00:00Z",
      "baselineSpend": {
        "amount": 999996.51,
        "currency": "EUR"
      },
      "bids": [
        {
          "bidId": "BID-001",
          "round": 1,
          "supplier": {
            "aribaId": "S2000127",
            "name": "Crescent Media SA",
            "vatNumber": "FR178910051"
          },
          "bidAmount": 980277.47,
          "currency": "EUR",
          "submittedAt": "2026-09-12T12:00:00Z"
        },
        {
          "bidId": "BID-002",
          "round": 1,
          "supplier": {
            "aribaId": "S2000097",
            "name": "Sapphire Media Inc",
            "vatNumber": "US579476614"
          },
          "bidAmount": 773673.95,
          "currency": "EUR",
          "submittedAt": "2026-09-08T09:00:00Z"
        },
        {
          "bidId": "BID-003",
          "round": 1,
          "supplier": {
            "aribaId": "S2000090",
            "name": "Evergreen Clinical Services SA",
            "vatNumber": "FR929517022"
          },
          "bidAmount": 817316.99,
          "currency": "EUR",
          "submittedAt": "2026-09-10T13:00:00Z"
        },
        {
          "bidId"
```
