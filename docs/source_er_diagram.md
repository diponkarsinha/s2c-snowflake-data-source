# Source data model (ER diagram)

How the source entities relate **before** any cleaning. Keys are the source systems' own keys. The two important cross-system joins are marked:

- **Ariba → SAP supplier:** there is no shared ID. Match on **VAT number** (`supplier.vatNumber` = `STCEG`). This is `int_supplier_mapping` in dbt.
- **PO → contract:** `KONNR` holds the Ariba contract ID. Empty means the purchase had no contract (maverick spend).

```mermaid
erDiagram
    SAP_SUPPLIER ||--o{ SAP_PO_LINE : "LIFNR"
    SAP_SUPPLIER ||--o{ SAP_INVOICE_LINE : "LIFNR"
    SAP_PO_LINE ||--o{ SAP_INVOICE_LINE : "EBELN + EBELP"
    SAP_COST_CENTER ||--o{ SAP_PO_LINE : "KOSTL"
    CATEGORY ||--o{ SAP_PO_LINE : "sap_material_group = MATKL"
    CATEGORY ||--o{ CATEGORY : "parent_category_id"
    FX_RATE }o--o{ SAP_PO_LINE : "WAERS + month"

    SOURCING_REQUEST ||--o| SOURCING_EVENT : "requestId"
    SOURCING_EVENT ||--|{ BID : "bids[]"
    SOURCING_EVENT ||--o| CONTRACT : "eventId"
    CATEGORY ||--o{ SOURCING_EVENT : "category.id"
    CONTRACT ||--o{ CONTRACT_APPROVAL : "contract_id"
    CONTRACT ||--o{ SAP_PO_LINE : "contractId = KONNR"
    EMPLOYEE ||--o{ CONTRACT_APPROVAL : "approver_id"
    EMPLOYEE ||--o{ EMPLOYEE : "approver_manager_id"

    SAP_SUPPLIER ||--o{ CONTRACT : "STCEG = supplier.vatNumber"
    SAP_SUPPLIER ||--o{ BID : "STCEG = supplier.vatNumber"
    SAP_SUPPLIER ||--o{ RISK_ASSESSMENT : "STCEG = vatNumber"
    SAP_SUPPLIER ||--o{ RISK_EVENT : "STCEG = supplier_vat"
    SOURCING_EVENT ||--o{ SAVINGS_LINE : "Event ID"

    SAP_SUPPLIER {
        string LIFNR PK
        string NAME1
        string STCEG "VAT, cross-system key"
        string SPERR "X = blocked"
        string IBAN
    }
    SAP_PO_LINE {
        string EBELN PK
        string EBELP PK
        string LIFNR FK
        string MATKL FK
        string KOSTL FK
        string KONNR "contract id or empty"
        string LOEKZ "L = deleted"
        string AEDAT "change date"
    }
    SAP_INVOICE_LINE {
        string BELNR PK
        int GJAHR PK
        int BUZEI PK
        string EBELN FK
        string EBELP FK
        double WRBTR "negative = credit"
        string STBLG "reversed doc"
    }
    SAP_COST_CENTER {
        string kostl PK
        date valid_to "past = closed"
    }
    FX_RATE {
        string currency PK
        string month PK
        number rate
    }
    CATEGORY {
        string category_id PK
        string parent_category_id FK
        string sap_material_group
        string is_active
    }
    SOURCING_REQUEST {
        string request_id PK
        string category_id FK
        string created_at
        string updated_at
    }
    SOURCING_EVENT {
        string eventId PK
        string requestId FK
        string status
        string awardDate
        number baselineSpend
    }
    BID {
        string eventId FK
        string bidId PK
        int round PK
        string vatNumber
        number bidAmount
    }
    CONTRACT {
        string contractId PK
        string eventId FK
        string vatNumber
        date startDate
        date endDate
        boolean isDeleted
    }
    CONTRACT_APPROVAL {
        string approval_id PK
        string contract_id FK
        int step
        string approver_id FK
    }
    EMPLOYEE {
        string approver_id PK
        string approver_manager_id FK
    }
    RISK_ASSESSMENT {
        string vatNumber PK
        string generatedAt PK
        int financialRisk
        string medal
    }
    RISK_EVENT {
        string event_id PK
        string supplier_vat
        int risk_score
        string event_time
    }
    SAVINGS_LINE {
        string savings_id PK
        string event_id FK
        number baseline
        number negotiated
    }
```

## The S2C chain

```mermaid
flowchart LR
    A["Request<br/>(intake)"] --> B["Sourcing event<br/>RFx + bids"] --> C["Award"] --> D["Contract<br/>+ approvals"] --> E["Purchase order<br/>KONNR = contract"] --> F["Invoice"]
    B -. "savings claimed" .-> G["Savings tracker"]
    H["Supplier risk / ESG"] -. "checked at award<br/>and on every PO" .-> C
```

Cycle time (request → award), spend under contract (PO with `KONNR`), savings (baseline − awarded) and risk exposure (spend with High-risk suppliers) all come from walking this chain.
