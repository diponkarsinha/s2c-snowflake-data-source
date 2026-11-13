# Supplier risk and ESG (weekly)

Financial risk (1 low - 9 high) and ESG rating. Not every supplier is assessed.

| | |
|---|---|
| **Entity folder** | `data/*/supplier_risk/risk_esg/` |
| **Source system** | Third-party risk provider (fictional 'RiskCo') |
| **File name** | `supplier_risk_esg_YYYYMMDD.json` |
| **Format** | JSON `{provider, generatedAt, suppliers:[{supplier, scores, esg, assessedAt, nextReviewDue}]}` |
| **Grain** | One row per supplier assessment |
| **Business key** | `vatNumber + generatedAt` |
| **Load pattern** | Batch, weekly full file |
| **RAW table** | `RAW.RISK_ESG (VARIANT)` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `supplier.vatNumber` | text | No | Join key to SAP STCEG | Confidential |  |
| `supplier.dunsNumber` | text | No | D-U-N-S style number | Internal |  |
| `scores.financialRisk` | int | No | 1-9 | Licensed | 3 out of range (0, 11, 12) |
| `scores.paydex / failureScore` | int | No | Payment / failure scores | Licensed |  |
| `esg.ecovadisScore` | int | No | 0-100 | Licensed |  |
| `esg.medal` | text | Yes | Bronze..Platinum | Licensed | Often null |
| `assessedAt / nextReviewDue` | date | No | Review cycle | Internal | 10 reviews overdue |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

```json
{
  "provider": "RiskCo Intelligence (fictional)",
  "generatedAt": "2026-10-26T05:00:00Z",
  "schemaVersion": "1.0",
  "suppliers": [
    {
      "supplier": {
        "name": "Cobalt Chemicals GmbH",
        "vatNumber": "DE909134796",
        "dunsNumber": "329509408",
        "country": "DE"
      },
      "scores": {
        "financialRisk": 5,
        "paydex": 57,
        "failureScore": 27
      },
      "esg": {
        "ecovadisScore": 76,
        "medal": "Silver"
      },
      "assessedAt": "2026-03-21",
      "nextReviewDue": "2027-03-21"
    }
  ]
}
```
