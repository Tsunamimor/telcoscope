# Contributing

Thanks for looking! This is primarily a portfolio project, but pull requests
and issues are welcome.

## Local development

### Prerequisites

- Python 3.11+
- Docker Desktop (or equivalent)
- `make`
- Recommended: [`uv`](https://github.com/astral-sh/uv) for dependency
  management — falls back to `pip` if `uv` is not on PATH

### Setup

```bash
git clone https://github.com/YOUR-USERNAME/telcoscope.git
cd telcoscope
cp .env.example .env
make install        # Python dependencies (uv preferred, pip fallback)
pre-commit install  # Git hooks
make up             # Bring up the Docker stack
```

### Running things

```bash
make test           # Run pytest
make lint           # ruff + mypy
make format         # ruff format + autofix
make seed           # Generate synthetic data
make dbt            # Build dbt marts
make app            # Launch Streamlit
make api            # Launch FastAPI
make down           # Stop containers (preserve volumes)
make destroy        # Stop containers + delete volumes (full reset)
```

## Coding standards

- **Formatting / linting**: `ruff` (configured in `pyproject.toml`). Pre-commit
  runs this automatically.
- **Type hints**: required on all public functions. `mypy` runs in CI but is
  non-blocking initially — tighten over time.
- **Docstrings**: Google-style. Required on public functions and classes.
- **Tests**: pytest, with `pytest-cov` for coverage. New features land with
  tests in the same PR.
- **Commits**: imperative mood, scope where helpful (e.g. `synth: add rural
  archetype`). Conventional Commits is not enforced but encouraged.

## Branching

- `main` is the only protected branch. PRs land via squash merge.
- Feature branches are named `wk{N}-{topic}` (e.g. `wk3-isolation-forest`)
  to mirror the project's weekly cadence.

## Adding a new KPI

1. Add the counter rows to `dbt/seeds/counter_catalog.csv`.
2. Add the KPI calculation to `dbt/models/marts/mart_kpi_cell_hourly.sql`.
3. Document it in `docs/KPI_DEFINITIONS.md`.
4. Add detection coverage in `src/telcoscope/detect/`.
5. Add at least one matching RCA rule in `src/telcoscope/rca/rules.yaml`
   (or document why none applies).

## Adding a new vendor

The whole point of the data model is that this should *not* require code
changes. Add rows to `dim_vendor` and `dim_counter` (with appropriate
`vendor_counter_name` mappings) and let the existing dbt models handle the
rest. If something forces a code change, please open an issue — that's a
data-model bug.
