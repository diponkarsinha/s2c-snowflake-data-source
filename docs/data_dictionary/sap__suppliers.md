# Supplier master

System of record for suppliers. Read with XMLGET in staging.

| | |
|---|---|
| **Entity folder** | `data/*/sap/suppliers/` |
| **Source system** | SAP S/4HANA, governed in SAP MDG (LFA1, LFBK) |
| **File name** | `sap_suppliers_cremas_YYYYMMDD.xml` |
| **Format** | XML, SAP IDoc CREMAS05 (`<IDOC><E1LFA1M>...<E1LFBKM/></E1LFA1M></IDOC>`) |
| **Grain** | One IDOC per supplier |
| **Business key** | `LIFNR` |
| **Load pattern** | Batch, FULL reload (whole master each time) -> SCD2 snapshot in dbt |
| **RAW table** | `RAW.SAP_SUPPLIERS (VARIANT)` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `LIFNR` | CHAR(10) | No | SAP supplier number | Internal | 8 suppliers duplicated under new IDs |
| `NAME1` | CHAR(35) | No | Supplier name | Internal | Name variants: upper case, double spaces, 'Limited' |
| `LAND1` | CHAR(3) | No | Country | Internal |  |
| `ORT01` | CHAR(35) | Yes | City | Internal | Empty tags `<ORT01></ORT01>` |
| `STCEG` | CHAR(20) | No | VAT number: the key to match duplicates and Ariba suppliers | Confidential (tax) |  |
| `KTOKK` | CHAR(4) | No | Account group | Internal |  |
| `SPERR` | CHAR(1) | Yes | Posting block, X = blocked | Internal | Blocked suppliers still get POs |
| `ERDAT` | DATS | No | Created on | Internal |  |
| `UPDAT` | DATS | No | Last changed | Internal | Wave 8: name, address, bank changes |
| `E1LFBKM/BANKS` | CHAR(3) | Yes | Bank country | Confidential (bank) |  |
| `E1LFBKM/BANKL` | CHAR(15) | Yes | Bank key | Confidential (bank) |  |
| `E1LFBKM/IBAN` | CHAR(34) | Yes | IBAN | Confidential (bank) | Wave 8: changed for 2 suppliers |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CREMAS05>
  <IDOC BEGIN="1">
    <EDI_DC40 SEGMENT="1"><DOCNUM>0000000000000001</DOCNUM><MESTYP>CREMAS</MESTYP><CREDAT>20250503</CREDAT></EDI_DC40>
    <E1LFA1M SEGMENT="1">
      <LIFNR>0000100001</LIFNR>
      <NAME1>Northstar Clinical Services BV</NAME1>
      <LAND1>NL</LAND1>
      <ORT01>Leiden</ORT01>
      <STCEG>NL883543540</STCEG>
      <KTOKK>KRED</KTOKK>
      <SPERR></SPERR>
      <ERDAT>20240119</ERDAT>
      <UPDAT>20250503</UPDAT>
      <E1LFBKM SEGMENT="1"><BANKS>NL</BANKS><BANKL>60806024</BANKL><IBAN>NL789765045239749496</IBAN></E1LFBKM>
    </E1LFA1M>
  </IDOC>
  <IDOC BEGIN="1">
    <EDI_DC40 SEGMENT="1"><DOCNUM>0000000000000002</DOCNUM><MESTYP>CREMAS</MESTYP><CREDAT>20211111</CREDAT></EDI_DC40>
    <E1LFA1M SEGMENT="1">
      <LIFNR>0000100002</LIFNR>
      <NAME1>Brightpath Pharma Supplies Inc</NAME1>
```
