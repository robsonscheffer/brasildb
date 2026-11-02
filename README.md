# brasildb

Brazilian public data as Parquet tables, queried with DuckDB, and a site that answers one question
at a time from that data. The first case is **O Brasil votando**: the 2026 second round, minute by
minute, from the urnas' own logs.

**Status:** prototype, parked on 2026-11-02. The site and the data stay online; nothing new is being
built. It comes back if a clear use for more public data shows up.

## What is here

- **The site:** [votando.brasildb.org](https://votando.brasildb.org/), in Portuguese. The walk from one
  vote to the whole country, [the count night](https://votando.brasildb.org/apuracao.html), and
  [how it works and how it was made](https://votando.brasildb.org/como.html). Source: `docs/site/`.
- **The lake:** a collector for TSE urna logs and results (`brasildb/`), the table contract
  (`catalog.yaml`), and DuckDB views (`sql/views/`).
- **Plans:** what was built, P1 to P5, in `docs/plans/`. Ideas for more data (social data per city,
  campaign money, contracts) are drafts in [PR #63](https://github.com/robsonscheffer/brasildb/pull/63).

## Run it

```sh
uv sync
uv run pytest
uv run brasildb --help
```

Collecting, querying and rebuilding the site: [docs/usage.md](docs/usage.md).

## How it was made

Built as a prototype in five days, 2026-10-28 to 2026-11-01, by Robson Scheffer with AI coding
agents. What it taught, for a rebuild: [docs/learnings.md](docs/learnings.md).

## Licence

No licence yet: ask before reusing the code or the data files. The source data is public TSE data
([dadosabertos.tse.jus.br](https://dadosabertos.tse.jus.br/)).
