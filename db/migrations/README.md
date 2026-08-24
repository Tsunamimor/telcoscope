# Database migrations

This directory will hold [Alembic](https://alembic.sqlalchemy.org/) migrations
for the raw, dimension, and analytics-layer tables.

## Initial setup (run once during Week 1)

From the project root:

```bash
# 1. Install the dev extras (alembic is included)
make install

# 2. Initialise alembic
alembic init -t async db/migrations

# 3. Point alembic at the package's metadata
#    Edit db/migrations/env.py to import the SQLAlchemy models from
#    src/telcoscope/db/models.py (to be created).

# 4. Generate the first migration once the models are defined
alembic revision --autogenerate -m "initial schema"

# 5. Apply
alembic upgrade head
```

## Why Alembic and not the postgres-init script?

The `postgres-init/` SQL files run only once, on first container start. That's
fine for extensions and schemas, but unsuitable for tables that evolve over
the life of the project. Alembic gives versioned, reversible, reviewable
schema changes — the same `up/down` discipline used in production systems.
