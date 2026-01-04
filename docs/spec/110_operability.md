# Operability

## Deployment model
- Single-node dev/lab deployment (Docker Compose or local services)
- Optional distributed mode later

## Observability of the range itself
- Range service logs are structured and correlated by run_id.
- Health endpoints for each component.

## Failure modes & handling
- Partial run: preserve artifacts and mark run status = failed with reason.
- Collector lag: record ingestion delay and include in report.
