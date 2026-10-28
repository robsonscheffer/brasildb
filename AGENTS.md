# brasildb

Brazilian public data as Parquet tables with Base dos Dados naming, queried with DuckDB.
TSE urna logs first. Runs on a laptop with a sample; the full run is a Kubernetes Job.

- Python with uv: `uv sync`, `uv run pytest`.
- `catalog.yaml` is the schema contract. A table or column change starts there.
- Code never assumes a laptop path: settings come from env (`brasildb/config.py`).
- Tests never hit the network. Real TSE samples live in `tests/fixtures/`.
- One global request limiter for resultados.tse.jus.br (about 100 req/s per IP; default 20).
- Plans live in `docs/plans/`. How to run it: `docs/usage.md`.
