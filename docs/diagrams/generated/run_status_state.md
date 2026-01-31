# Run status (success/partial/failed)

```mermaid
stateDiagram-v2
  [*] --> Running
  note right of Running
    representational (non-normative)
    authority: ADR-0005, 025_data_contracts
  end note
  Running --> Failed: any enabled stage outcome has status="failed" and fail_mode="fail_closed" (dominates partial) (exit 20)
  Running --> Partial: else if any enabled stage outcome has status="failed" and fail_mode="warn_and_skip" (exit 10)
  Running --> Success: else (all enabled stage outcomes have status="success") (exit 0)
  Failed --> [*]
  Partial --> [*]
  Success --> [*]
```
