#!/usr/bin/env bash
# ============================================================
#  telcoscope - session startup (called by start-telcoscope.bat)
#  Version:      v1.1  (Week 3, Day 2)
#  Last updated: 2026-09-25
#  Changelog:
#    v1.1 - surface conda activate errors; land in usable shell
#           even if activation fails; print sourced conda path
#    v1.0 - initial version
# ============================================================
#  What this does:
#   1. Sources conda and activates the telcoscope env
#   2. Brings up the Docker stack (Postgres, Grafana, Adminer)
#   3. Waits for Postgres to be ready
#   4. Verifies the KPI marts and ground truth are populated
#   5. Runs the Python detection stack import check
#   6. Prints a "ready to work" summary + suggested next steps
#
#  Update this file when a new week adds startup requirements.
# ============================================================

# Do NOT `set -e` — we want to continue past soft failures like
# "marts not yet built" so the user still lands in a usable shell.

CONDA_ENV="telcoscope"
SLEEP_AFTER_UP=20

# Colour helpers (fall back gracefully if terminal lacks them)
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
RED=$'\033[0;31m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

echo ""
echo "${BOLD}==========================================${RESET}"
echo "${BOLD}  telcoscope session startup  (v1.1)${RESET}"
echo "${BOLD}==========================================${RESET}"

# ------------------------------------------------------------
# [1/5] Activate conda env
# ------------------------------------------------------------
echo ""
echo "${BOLD}[1/5] Activating conda env: ${CONDA_ENV}${RESET}"

# Locate conda.sh — try user's anaconda3, then miniconda3
CONDA_SH_FOUND=""
for candidate in \
    "$HOME/anaconda3/etc/profile.d/conda.sh" \
    "/c/Users/$USER/anaconda3/etc/profile.d/conda.sh" \
    "/c/Users/paddy/anaconda3/etc/profile.d/conda.sh" \
    "$HOME/miniconda3/etc/profile.d/conda.sh"
do
    if [ -f "$candidate" ]; then
        # shellcheck disable=SC1090
        source "$candidate"
        CONDA_SH_FOUND="$candidate"
        break
    fi
done

if [ -z "$CONDA_SH_FOUND" ]; then
    echo "      ${RED}ERROR: could not locate conda.sh${RESET}"
    echo "      Edit scripts/startup.sh to add your conda path."
    echo "      Continuing without conda active..."
else
    echo "      Sourced: ${CONDA_SH_FOUND}"

    # Attempt activation. Surface any error rather than hiding it.
    conda activate "$CONDA_ENV"
    ACTIVATE_RC=$?

    if [ "$CONDA_DEFAULT_ENV" = "$CONDA_ENV" ]; then
        echo "      ${GREEN}Active: ${CONDA_ENV}${RESET}"
    else
        echo ""
        echo "      ${RED}conda activate '${CONDA_ENV}' failed (rc=${ACTIVATE_RC})${RESET}"
        echo "      Available envs:"
        conda env list 2>&1 | sed 's/^/        /'
        echo ""
        echo "      ${YELLOW}Common fixes:${RESET}"
        echo "        - If the env name differs, edit CONDA_ENV at the top of this script."
        echo "        - If no envs listed, conda may not be initialised in this shell."
        echo "          Try in an interactive Git Bash:  conda init bash  (then restart)"
        echo "        - If activation just needs a re-run, once this script finishes"
        echo "          run:  conda activate ${CONDA_ENV}"
        echo ""
        echo "      ${YELLOW}Continuing with checks so you can still see stack state...${RESET}"
    fi
fi

# ------------------------------------------------------------
# [2/5] Bring up the Docker stack
# ------------------------------------------------------------
echo ""
echo "${BOLD}[2/5] Bringing up Docker stack${RESET}"
if command -v make >/dev/null 2>&1; then
    make up
    echo "      Waiting ${SLEEP_AFTER_UP}s for services to boot..."
    sleep "$SLEEP_AFTER_UP"
else
    echo "      ${YELLOW}'make' not on PATH - trying 'docker compose' directly${RESET}"
    docker compose -f infra/docker/docker-compose.yml up -d
    sleep "$SLEEP_AFTER_UP"
fi

# ------------------------------------------------------------
# [3/5] Container status
# ------------------------------------------------------------
echo ""
echo "${BOLD}[3/5] Container status${RESET}"
docker ps --filter "name=telcoscope-" --format "      {{.Names}}  ({{.Status}})"

# Confirm Postgres is accepting connections
if docker exec telcoscope-postgres pg_isready -U telcoscope >/dev/null 2>&1; then
    echo "      ${GREEN}Postgres: accepting connections${RESET}"
else
    echo "      ${YELLOW}Postgres: not ready yet - giving it another 15s${RESET}"
    sleep 15
    if docker exec telcoscope-postgres pg_isready -U telcoscope >/dev/null 2>&1; then
        echo "      ${GREEN}Postgres: accepting connections${RESET}"
    else
        echo "      ${RED}Postgres still not ready - check 'docker logs telcoscope-postgres'${RESET}"
    fi
fi

# ------------------------------------------------------------
# [4/5] Verify data layer
# ------------------------------------------------------------
echo ""
echo "${BOLD}[4/5] Data layer checks${RESET}"

echo ""
echo "      KPI marts (dbt_dev_marts.mart_kpi_cell_hourly):"
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -tAc "
SELECT
  count(*) || ' rows, ' ||
  count(DISTINCT cell_id) || ' cells, ' ||
  coalesce(min(ts)::date::text, 'no data') || ' -> ' ||
  coalesce(max(ts)::date::text, 'no data')
FROM dbt_dev_marts.mart_kpi_cell_hourly;
" 2>/dev/null | sed 's/^/        /' || \
    echo "        ${YELLOW}(not built - run 'make dbt' when needed)${RESET}"

echo ""
echo "      Ground-truth injections (analytics.synth_truth):"
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -tAc "
SELECT pattern_type || ': ' || count(*)
FROM analytics.synth_truth
GROUP BY pattern_type
ORDER BY pattern_type;
" 2>/dev/null | sed 's/^/        /' || \
    echo "        ${YELLOW}(not populated - run 'make seed' when needed)${RESET}"

echo ""
echo "      Anomalies table (analytics.anomalies):"
docker exec telcoscope-postgres psql -U telcoscope -d telcoscope -tAc "
SELECT method || ': ' || count(*) || ' rows'
FROM analytics.anomalies
GROUP BY method
ORDER BY method;
" 2>/dev/null | sed 's/^/        /' || \
    echo "        ${YELLOW}(no rows yet - run 'make detect' when detectors are wired)${RESET}"

# ------------------------------------------------------------
# [5/5] Python detection stack import check
# ------------------------------------------------------------
echo ""
echo "${BOLD}[5/5] Python detection stack${RESET}"
if command -v python >/dev/null 2>&1; then
    if python -c "import sklearn, scipy, numpy, pandas, polars, psycopg" 2>/dev/null; then
        echo "      ${GREEN}sklearn, scipy, numpy, pandas, polars, psycopg all importable${RESET}"
    else
        echo "      ${RED}One or more detection packages missing${RESET}"
        echo "      Fix: pip install -e \".[dev,dbt]\""
    fi
else
    echo "      ${YELLOW}'python' not on PATH (likely because conda activate failed above)${RESET}"
fi

# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------
echo ""
echo "${BOLD}==========================================${RESET}"
echo "${BOLD}  Environment ready${RESET}"
echo "${BOLD}==========================================${RESET}"
echo ""
echo "  Working dir: $(pwd)"
echo "  Conda env:   ${CONDA_DEFAULT_ENV:-(none active)}"
echo "  Grafana:     http://localhost:3000  (admin/admin)"
echo "  Adminer:     http://localhost:8080  (postgres / telcoscope x3)"
echo ""
echo "${BOLD}  Where you are:${RESET}  Week 3, Day 2"
echo "${BOLD}  Suggested next steps:${RESET}"
echo "    1. Apply psycopg fix to src/telcoscope/detect/run.py"
echo "       and src/telcoscope/detect/persistence.py:"
echo "         psycopg.connect(settings.postgres_url"
echo "                         .replace(\"+psycopg\", \"\"))"
echo "    2. Verify:   grep 'replace' src/telcoscope/detect/*.py"
echo "    3. Run:      make detect"
echo "    4. Commit:   git add Makefile src/telcoscope/detect/ &&"
echo "                 git commit -m 'wk3: statistical detector' &&"
echo "                 git push"
echo ""
