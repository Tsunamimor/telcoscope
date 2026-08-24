# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial repository scaffold
- Project documentation skeleton (ARCHITECTURE, ARCHITECTURE_EVOLUTION, KPI_DEFINITIONS, DATA_MODEL)
- Docker Compose stack (PostgreSQL + TimescaleDB, Grafana, Adminer)
- Python package skeleton with synth, ingest, detect, rca, narrate, alerts modules
- dbt project skeleton with staging / intermediate / marts model layout
- GitHub Actions CI workflow
- Pre-commit hooks (ruff, mypy, gitleaks)
- Makefile for common lifecycle operations
