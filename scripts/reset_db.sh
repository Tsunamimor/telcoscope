#!/usr/bin/env bash
# scripts/reset_db.sh
#
# Tear down the Docker stack including volumes, then bring it back up empty.
# Useful when iterating on the schema during Week 1.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "Stopping containers and removing volumes..."
docker compose -f infra/docker/docker-compose.yml --env-file .env down -v

echo "Bringing the stack back up..."
docker compose -f infra/docker/docker-compose.yml --env-file .env up -d

echo
echo "Database reset complete. Run 'make seed' to repopulate with synthetic data."
