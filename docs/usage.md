# Using brasildb

Collect the TSE urna logs, load the official turnout, and query both with SQL. A full round
(514,464 sections) is about 120 GB on disk with raw files kept, 34 GB without.

## Setup

```sh
uv sync
export BRASILDB_DATA=$PWD/data   # lake/, raw/ and state.sqlite go here
```

## Load the reference tables (once per election)

```sh
uv run brasildb load-municipios            # TSE to IBGE municipality codes, names
uv run brasildb load-turnout --members BR  # turnout per section, both rounds (president)
```

## Collect urna logs

```sh
# whole states
uv run brasildb collect-logs --turno 2 --ufs rr ac
# chosen towns, by TSE code (needs load-municipios)
uv run brasildb collect-logs --turno 2 --municipios 85367
# a sample: all of rr plus 1% of sections in every other state
uv run brasildb collect-logs --turno 2 --ufs rr --sample-fraction 0.01 --seed 1
# the whole country
uv run brasildb collect-logs --turno 2 --ufs ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to
```

- **Resume:** run the same command again. It skips sections already in the lake with status
  `ok`, `agregada` or `sem_log`, so it collects only `erro` sections and sections a killed run
  never wrote. A killed run loses at most one unwritten batch (`--batch`, 200 sections).
- **Speed:** about 17 sections/s at 40 req/s. An ok section takes 2 requests (index and log);
  an aggregated section takes none. The TSE allows about 100 req/s per IP.
- **Network loss:** timeouts and 5xx retry 5 times; network errors retry for about 5 minutes,
  then the section is `erro` and the next run picks it up.
- **Long runs on a laptop:** use AC power and keep the lid open. `caffeinate -i` does not stop
  sleep when the lid closes.

| Variable | Default | Meaning |
| --- | --- | --- |
| `BRASILDB_DATA` | `data` | root for the three paths below |
| `BRASILDB_LAKE` | `$DATA/lake` | Parquet tables; a local path or `s3://bucket/prefix` |
| `BRASILDB_RAW` | `$DATA/raw` | original `-log.jez` files |
| `BRASILDB_STATE` | `$DATA/state.sqlite` | per-section record of the last run |
| `BRASILDB_KEEP_RAW` | `1` | `0` skips saving raw files (about 70% of the disk) |
| `BRASILDB_RPS` | `20` | global requests per second to resultados.tse.jus.br |
| `BRASILDB_CONCURRENCY` | `20` | downloads in flight |
| `BRASILDB_PARSE_WORKERS` | CPU count - 1 | processes that unzip and parse logs |
| `BRASILDB_S3_ENDPOINT` | none | S3-compatible endpoint for an `s3://` lake |

## Query

`brasildb sql` opens the lake in DuckDB with the views in `sql/views/` and the checks in
`sql/checks/` loaded. A view whose tables are missing is skipped.

```sh
uv run brasildb sql "SELECT status, count(*) FROM main.check_comparecimento WHERE turno = 2 GROUP BY 1"
```

| Name | What it holds |
| --- | --- |
| `br_tse_urna_logs.eventos` | one row per log line, typed (`tipo_evento`: `voto_computado`, `urna_pronta`, `encerramento`, `energia`, `solicita_digital`, `contingencia`, ...; the list is `EVENT_TYPES` in `brasildb/tse/logparse.py`) |
| `br_tse_urna_logs.secoes_coleta` | one row per section collected: status, number of logs, error |
| `br_tse_eleicoes.detalhes_votacao_secao` | official turnout per section and office |
| `br_bd_diretorios_brasil.municipio` | municipality codes and names |
| `main.eleicoes` | election rounds and their dates |
| `main.fuso_municipio` | each town's clock offset from Brasilia, derived from its first votes |
| `main.votos_hora`, `main.votos_hora_uf` | votes per hour, local and Brasilia time |
| `main.check_comparecimento` | votes in the log vs official turnout, per section |

To read a vote time in Brasilia time: `e.data_hora - to_hours(f.fuso)`, joining
`main.fuso_municipio f USING (ano, turno, sigla_uf, id_municipio_tse)`.

## What to expect in the turnout check

Round 2, whole country: 496,464 sections `ok` before the nested-archive fix. When an urna is
replaced during the day (`contingencia`), the closing urna's `-log.jez` carries the replaced
urna's whole log as a nested `<id>.jez`; the parser reads both, and `arquivo_membro` tells them
apart (`logd.dat` is the closing urna). A lake collected before that fix shows those 1,429
sections as `diferente`; rebuild it with `reparse`. A handful differ by one vote, and a section
with no published log shows `sem_log`.

## Reparse after a parser change

```sh
uv run brasildb reparse --turno 2 --out data/lake-v2          # all states, about 45 sections/s
uv run brasildb reparse --turno 2 --ufs rr --out data/lake-v2  # one state
```

It reads `raw/<ano>/<turno>/<uf>/*-log.jez`, no network, and writes only
`br_tse_urna_logs.eventos` under `--out`. Copy the other tables over (`secoes_coleta`,
`br_tse_eleicoes`, `br_bd_diretorios_brasil`), then point `BRASILDB_LAKE` at the new lake. After
a reparse `arquivo_hash` is the 12-hex prefix kept in the raw file name.

## Docker

```sh
docker build -t brasildb:dev .
docker run --rm -v $PWD/data:/data -e BRASILDB_RPS=40 brasildb:dev collect-logs --turno 2 --ufs rr
```
