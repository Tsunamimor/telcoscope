# telcoscope — Cheatsheet

## Startup (every session)

```bash
docker info | grep "Server Version"   # verify Docker up (else launch Docker Desktop, wait 90s)
cd /d/Paddy/GitHub/Telcoscope
conda activate telcoscope             # prompt shows (telcoscope)
make up                               # bring up stack
```

## Access

| Service | URL | Credentials / notes |
|---|---|---|
| Grafana | http://localhost:3000 | `admin` / `admin` — set time range to **Last 30 days** |
| Adminer | http://localhost:8080 | Server=`postgres`, DB/user/pw = `telcoscope` |
| dbt docs | http://localhost:8081 | `cd dbt && dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir . --port 8081` |
| Webhook-tester (NAS) | `http://192.168.68.5:<port>/<uuid>` | Set `INCIDENT_WEBHOOK_URL` to the UUID path before `make incidents` |
| GitHub Actions | https://github.com/Tsunamimor/telcoscope/actions | Fires on push/PR to `master` or `main` |

**Coming soon:** Streamlit (Wk 5, `:8501`) · FastAPI (Wk 5, `:8000`, `/docs`) · LLM narrator (Wk 5, needs `ANTHROPIC_API_KEY`) · AWS deploy (Wk 7 stretch).

## Full pipeline — one session

```bash
make up                     # bring up docker stack
make seed                   # generate + load 30 days of synthetic data
make dbt                    # deps + run + test (stg → int → marts)
make detect                 # statistical + isolation_forest → analytics.anomalies
make incidents              # group anomalies → analytics.incidents + webhook notify
make rca                    # evaluate rules against incidents → analytics.rca_hypotheses
```

Each step is idempotent on its own — re-running `make incidents` or `make rca` with no upstream changes produces the same DB state.

## Postgres via psql

```bash
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -c "SELECT ..."   # one-shot
winpty docker exec -it telcoscope-postgres psql -U telcoscope -d telcoscope        # interactive; \q
```

Handy: `\dn` (schemas) · `\dt raw.*` (tables) · `SELECT count(*) FROM raw.pm_measurements;` (~1M rows) · `SELECT extname FROM pg_extension;` (TimescaleDB check)

**Pipeline health — row counts at each stage:**

```bash
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -c "
  SELECT 'anomalies' AS stage, COUNT(*) FROM analytics.anomalies
  UNION ALL SELECT 'incidents (all)', COUNT(*) FROM analytics.incidents
  UNION ALL SELECT 'incidents (non-info)', COUNT(*) FROM analytics.incidents WHERE severity != 'info'
  UNION ALL SELECT 'incidents (notified)', COUNT(*) FROM analytics.incidents WHERE notified_at IS NOT NULL
  UNION ALL SELECT 'rca_hypotheses', COUNT(*) FROM analytics.rca_hypotheses
  UNION ALL SELECT 'rca_hypotheses (distinct incidents)', COUNT(DISTINCT incident_id) FROM analytics.rca_hypotheses;"
```

**Verify `cell_id` type across schemas** (post-BKL-004 / CLS-005 — all should be `bigint`):

```bash
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -c "
  SELECT table_schema, table_name, data_type
  FROM information_schema.columns
  WHERE column_name='cell_id'
  ORDER BY table_schema, table_name;"
```

**Top-confidence RCA hypothesis right now:**

```bash
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -c "
  SELECT incident_id, hypothesis_rank, rule_id, confidence,
         jsonb_pretty(evidence) AS evidence
  FROM analytics.rca_hypotheses
  ORDER BY confidence DESC
  LIMIT 1;"
```

**Rule firing frequency** (which rules match most often — spot the one carrying all the load):

```bash
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -c "
  SELECT rule_id, COUNT(*) AS fires, ROUND(AVG(confidence)::numeric, 3) AS avg_conf
  FROM analytics.rca_hypotheses
  GROUP BY rule_id
  ORDER BY fires DESC;"
```

**Reset the notified_at trail** (safe — doesn't delete incidents, just clears the "has been sent" mark):

```bash
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -c "
  UPDATE analytics.incidents SET notified_at = NULL;"
```

## dbt — day-to-day

```bash
cd dbt
dbt build --target dev                            # full run: seeds + models + tests
dbt build --select mart_incidents_timeline        # one model only (fastest iteration)
dbt test --select source:analytics                # the new relationships guards + source tests
dbt test --select source:analytics.incidents      # one source only
cd ..
```

**Remember.** A dbt model file cannot end with `;` — dbt wraps the SELECT and the semicolon breaks the wrap. Column names in models must match the actual mart (`\d dbt_dev_marts.mart_kpi_cell_hourly` before writing SQL).

## Make targets

`make up`/`down`/`destroy` (destroy wipes volume) · `seed` (load 30d data) · `dbt` (deps + run + test) · `detect` (run all detectors) · `incidents` (group + notify) · `rca` (evaluate rules → rca_hypotheses) · `lint`/`format`/`test`

**RCA env vars** (defaults OK for a full run):
- `RCA_TOP_N` — hypotheses to keep per incident (default `5`)
- `RCA_INCIDENT_SEVERITY_FILTER` — comma-separated (default `minor,major,critical`, skips `info`)
- `RCA_MAX_INCIDENTS` — cap for a staged run (default `0` = unlimited, useful: `RCA_MAX_INCIDENTS=10 make rca`)
- `RCA_RULES_PATH` — override the shipped `rca/rules.yaml` for a custom library

**Incident webhook env vars** (set once per session):
- `INCIDENT_WEBHOOK_URL` — the exact UUID path on webhook-tester / your endpoint
- `INCIDENT_NOTIFY_SLEEP_SECONDS` — per-POST rate limit (default `0.5`)
- `INCIDENT_NOTIFY_MAX_PER_RUN` — cap per invocation (default `100`)

## Git — daily flow

```bash
git status                                      # see what's changed
git diff <file>                                 # inspect changes before staging
git pull --rebase                               # sync with GitHub before starting work
git add <file>                                  # stage specific files
git commit -m "wk<N>(day<M>): short description"
git push                                        # or `git push -u origin <branch>` on first push
```

**Branch naming:** `wk<N>/<slug>` (e.g. `wk5/day2-rca-engine`).

**PR flow:** push → `gh pr create --title "..." --body "..."` → `gh pr checks <num> --watch` → `gh pr merge <num> --squash --delete-branch`.

**Stuck on pull with uncommitted changes:** `git stash -u && git pull --rebase && git stash pop`
**Undo last commit but keep changes:** `git reset --soft HEAD~1` · **Discard local file changes:** `git restore <file>` (no undo)
**See history:** `git log --oneline -10` · **See what's in a commit:** `git show <hash>`

## Running individual tests

```bash
pytest                                              # whole suite (with coverage)
pytest -x --tb=short                                # stop on first failure, concise traceback
pytest tests/rca/                                   # one directory
pytest tests/rca/test_engine.py -v                  # one file
pytest tests/rca/test_engine.py::test_top_n_truncates   # one test
```

## Lint / format

```bash
ruff format src tests apps                      # format files in place
ruff check --fix src tests apps                 # auto-fix lint errors
ruff format --check src tests apps              # CI check mode (no changes)
mypy src                                        # type-check (CI runs this)
```

CI runs all three on every PR. If a pre-commit or local lint pass reformats files, commit the diff (don't amend — the project prefers new commits per fix).

## Common fixes

| Symptom | Fix |
|---|---|
| `docker info` errors | Task Mgr → end all Docker Desktop procs → PowerShell (Admin) `wsl --shutdown` → relaunch → 90s |
| `bash: make: not found` | Install GnuWin32 make + add `C:\Program Files (x86)\GnuWin32\bin` to PATH manually. Or run the underlying `python -m telcoscope.<module>.run` directly. |
| `docker exec -it` TTY error | Drop `-t`, or prefix with `winpty` |
| Path resolves to `C:/Program Files/Git/...` | Prefix container paths with `//` (e.g. `//etc/foo`) |
| `couldn't find env file: .env` | `cp .env.example .env` |
| Grafana datasource missing | UI: PostgreSQL, host `postgres:5432`, DB/user/pw all `telcoscope`, TLS `disable`, TimescaleDB **ON** |
| TimescaleDB/schemas missing after `make up` | Run restore block below |
| CI not triggering | `.github/workflows/ci.yml` needs `branches: [main, master]` |
| `LF will be replaced by CRLF` warnings on `git add` | Harmless on Windows — just continue with `git commit` |
| `git pull` fails with "unstaged changes" | `git stash -u && git pull --rebase && git stash pop` |
| Heredoc paste into Git Bash truncates / sticks on `>` prompt | Use Notepad++ or a small Python script to write multi-line content; Git Bash has a paste-buffer limit |
| Alembic `cannot alter type of a column used by a view` | DROP the dependent dbt artefact first (TABLE for `mart_detector_evaluation`, VIEW for `mart_incidents_timeline`) in the migration's upgrade(), then recreate via `dbt build` |
| Webhook delivered 2xx but UI empty | Placeholder URL — BKL-006 open. Verify endpoint with `curl -v -X POST $INCIDENT_WEBHOOK_URL -d '{}'` before draining |

## Manual DB restore

```bash
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE; CREATE EXTENSION IF NOT EXISTS pg_stat_statements; CREATE SCHEMA IF NOT EXISTS raw; CREATE SCHEMA IF NOT EXISTS dims; CREATE SCHEMA IF NOT EXISTS marts; CREATE SCHEMA IF NOT EXISTS analytics;"
alembic upgrade head && make seed && make dbt && make detect && make incidents && make rca
```

## Clean-room test — prove the quickstart still holds

Run in a **fresh terminal**. Take your normal stack down first (`make down` in the real project) to avoid port conflicts on 3000/8080/5432.

```bash
cd /tmp
git clone https://github.com/Tsunamimor/telcoscope.git verify && cd verify
cp .env.example .env
conda env create -f environment.yml && conda activate telcoscope
make up && sleep 30
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE; CREATE SCHEMA IF NOT EXISTS raw; CREATE SCHEMA IF NOT EXISTS dims; CREATE SCHEMA IF NOT EXISTS marts; CREATE SCHEMA IF NOT EXISTS analytics;"
alembic upgrade head && make seed && make dbt && make detect && make incidents && make rca
```

Target: under 7 minutes from `git clone` to green `make rca`. Then check Grafana at http://localhost:3000.

**Cleanup after test:**
```bash
cd /tmp && docker compose -f verify/infra/docker/docker-compose.yml down -v && rm -rf verify && conda env remove -n telcoscope
```

*Update this block as new weeks add steps (Wk 5 Day 3 will add `export ANTHROPIC_API_KEY=...` before `make narrate`).*
