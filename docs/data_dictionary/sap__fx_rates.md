# FX rates

Monthly average rates (type M): 1 EUR = rate x currency. Attributes read with GET(..., '@rate').

| | |
|---|---|
| **Entity folder** | `data/*/sap/fx_rates/` |
| **Source system** | SAP S/4HANA (TCURR) |
| **File name** | `sap_fx_rates_tcurr_YYYYMMDD.xml` |
| **Format** | XML, ECB style `<Cube time='YYYY-MM'><Cube currency rate rateType/></Cube>` |
| **Grain** | One rate per currency per month |
| **Business key** | `currency + month` |
| **Load pattern** | Batch, monthly |
| **RAW table** | `RAW.SAP_FX_RATES (VARIANT)` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `time` | attribute | No | Month YYYY-MM | Internal |  |
| `currency` | attribute | No | Currency code | Internal |  |
| `rate` | attribute | No | Units of currency per 1 EUR | Internal | INR missing for 2026-08 -> amount_eur NULL |
| `rateType` | attribute | No | M = monthly average | Internal |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Envelope sender="Sample Pharma Treasury" subject="Monthly average rates (rate type M), 1 EUR = rate x currency">
  <Cube time="2025-01">
    <Cube currency="USD" rate="1.0789" rateType="M"/>
    <Cube currency="GBP" rate="0.8428" rateType="M"/>
    <Cube currency="CHF" rate="0.9614" rateType="M"/>
    <Cube currency="CNY" rate="7.7766" rateType="M"/>
    <Cube currency="INR" rate="89.6400" rateType="M"/>
  </Cube>
  <Cube time="2025-02">
    <Cube currency="USD" rate="1.0800" rateType="M"/>
    <Cube currency="GBP" rate="0.8437" rateType="M"/>
    <Cube currency="CHF" rate="0.9623" rateType="M"/>
    <Cube currency="CNY" rate="7.7844" rateType="M"/>
    <Cube currency="INR" rate="89.7300" rateType="M"/>
  </Cube>
  <Cube time="2025-03">
    <Cube currency="USD" rate="1.0811" rateType="M"/>
    <Cube currency="GBP" rate="0.8445" rateType="M"/>
    <Cube currency="CHF" rate="0.9633" rateType="M"/>
    <Cube currency="CNY" rate="7.7922" rateType="M"/>
    <Cube currency="INR" rate="89.8200" rateType="M"/>
```
