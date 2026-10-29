# Week 4 — Retro

> **Theme:** From per-row detections to actionable incidents + a working
> notification channel.
>
> **Dates covered:** 2026-10-13 → 2026-10-29.
> **Branch(es):** `wk4/day1-incidents-schema` (merged), `wk4/day3-incidents-mart` (open).
> **PRs:** #2 (Days 1 + 2 — schema, grouper, upsert persistence, ADRs — merged).

---

## 1. What shipped

| Day | Deliverable | State |
|---|---|---|
| 1 | `analytics.incidents` table + indexes, Alembic migration, DEC-004 (grouping model ADR) | ✅ merged in PR #2 |
| 2 | Grouper + 11 unit tests (100% coverage), upsert persistence, orchestrator, severity threshold reconciliation via wk3 merge, DEC-003/005 ADRs | ✅ merged in PR #2 |
| 3 | `mart_incidents_timeline` enrichment mart (KPI values at `ts_start`, 24h baseline, per-KPI deltas), Grafana ops dashboard (severity filter, Top N bar chart, incident timeline, incident table with repeat-offender heat column) | ✅ working on `wk4/day3-incidents-mart` branch |
| 4 | `notifier.py` webhook sender with rate-limit + per-run cap, `run.py` wires in post-upsert notification pass, verified end-to-end against self-hosted webhook-tester on Synology NAS | ✅ working on `wk4/day3-incidents-mart` branch |

**End-to-end numbers (synthetic data, 30 days × 100 cells):**
- 22,314 anomalies → 11,093 non-info after filter → 7,077 incidents (1.6× compression)
- Severity split: 75% minor / 23% major / 2% critical — healthy ops pyramid
- Webhook delivery confirmed: ~232 payloads received in webhook-tester UI before Ctrl-C

**Portfolio-visible artefacts added:**
- Three new ADRs (DEC-003/004/005) — bringing the decision log coverage to Weeks 1–4
- Four new backlog items (BKL-003/004/005/006) with full context — reviewer-friendly trail
- Master HLD updated to v0.4 with Week 4 incidents section
- Master Cheatsheet updated to v0.2 with Week 4 commands and `make incidents` target

---

## 2. What went well

- **Interface-first detector pattern (DEC-003)** carried through cleanly to incidents: `Incident` dataclass + pure `group_anomalies` + separate `persistence.py` + `notifier.py`. Each module is independently testable, and the grouper hit 100% coverage with 11 tests inside a single morning.
- **Upsert idempotency on `(cell_id, ts_start)`** meant rerunning `make incidents` after any mart edit was always safe — no doubled rows, no manual TRUNCATE needed.
- **Honest numbers everywhere.** The compression ratio (1.6×) was lower than my initial 5–20× guess, and the severity distribution revealed the pre-tune thresholds were still running — rather than hand-wave either, both got investigated, documented and fixed. That turned a potential "silent wrong" into DEC-005 (severity calibration philosophy) and CLS-004 (resolved threshold mystery).
- **Self-hosted webhook-tester on the NAS** gave us a reusable catch-all webhook target that doesn't throttle. Faster feedback than webhook.site, free, and now available for every future webhook project.

---

## 3. What tripped us up (and what we did about it)

| Gotcha | Resolution |
|---|---|
| Pre-tune severity thresholds silently in effect (37% critical observed) | Grep confirmed; root cause was unmerged `wk3/severity-threshold-tune` branch; merged + rebased → textbook ~50/40/1 split. Captured as CLS-004. |
| `cell_id` type mismatch (TEXT in `analytics.*`, BIGINT elsewhere) broke `mart_incidents_timeline` join | Workaround: `k.cell_id::text = i.cell_id`. Proper fix in BKL-004. |
| My Week 4 guide used wrong column names (`ts_hour`, `prb_util_dl_pct`, `handover_success_pct`) | Checked the real mart with `\d dbt_dev_marts.mart_kpi_cell_hourly`; rewrote the mart against actual columns. |
| Model SQL ended with trailing `;` → dbt compile error | Removed it. dbt wraps the SELECT; semicolons break the wrap. Noted. |
| `_sources.yml` had `incidents` registered as a top-level source instead of a table under `analytics` → `source('analytics', 'incidents') not found` | Fixed indentation (6 spaces, under `tables:` of the `analytics` source). |
| webhook.site rate-limited at 429 after ~50 requests → found the retry logic in `run.py` works perfectly | Added rate-limit sleep (`INCIDENT_NOTIFY_SLEEP_SECONDS=0.5`) and max-per-run cap (`INCIDENT_NOTIFY_MAX_PER_RUN=100`), both env-configurable. |
| Pipeline reported `7077 sent, 0 skipped` while webhook-tester UI showed zero — payloads were going to the placeholder URL `abc123def456` | Fixed the env var; added BKL-006 to make the notifier verify the endpoint, not just trust 2xx. |

---

## 4. Nice-to-have for Week 5

Beyond the open backlog items, these payload enhancements would make `notifier.py` output genuinely consumer-ready for Slack / PagerDuty / ServiceNow out of the box. Both are pure derivation from existing fields — no DB change, no new infrastructure:

### 4.1 Add a `url` field pointing at Grafana for the incident

Deep-link the payload to the incident's row on the ops dashboard, so a Slack message is one click from the triage view. Shape would be something like:

```python
f"{settings.grafana_base_url}/d/incidents-ops?var-cell_id={cell_id}&from={ts_start_ms}&to={ts_end_ms}"
```

Adds one `url` key to the JSON payload. Downstream consumers that render links (Slack blocks, PagerDuty custom details, email HTML) get a one-click deep link for free. No API changes.

### 4.2 Add a human-readable `summary` field

Pre-compute the one-line incident description so downstream consumers don't have to format it themselves:

```python
summary = (
    f"{severity.title()} incident on cell {cell_id} "
    f"at {ts_start:%Y-%m-%d %H:%M} UTC — "
    f"{dominant_kpi} ({detection_count} detections)"
)
```

Means Slack/Teams/email templates can use the one field verbatim rather than string-joining four others. Keeps the structured fields alongside for consumers that want them.

### 4.3 Backlog items ready to pick up (not blocking)

- **BKL-002** — Detect persistence idempotency (upsert pattern, like incidents)
- **BKL-003** — Move `_score_to_severity` to `base.py` (cosmetic refactor)
- **BKL-004** — Harmonise `cell_id` TEXT → BIGINT (removes `::text` casts in dbt)
- **BKL-005** — Highlight dual-method confirmed incidents in Grafana
- **BKL-006** — Notifier should verify the webhook endpoint, not just trust 2xx

---

## 5. What I'd do differently

- **Grep the running code before trusting the branch-level diff.** The threshold mystery cost half an evening because I assumed the wk3 PR had merged when it hadn't. One `grep -A5 "_SEVERITY_THRESHOLDS" src/telcoscope/detect/statistical.py` at the start of Day 2 would have surfaced it immediately.
- **Confirm column names before writing dbt SQL.** `\d dbt_dev_marts.mart_kpi_cell_hourly` takes two seconds and would have caught the three fictional column names in my Week 4 guide draft before they wasted debug cycles.
- **Smoke-test the webhook URL once before draining.** The pipeline is only as honest as its most trusting dependency. BKL-006 is the proper fix; even without it, a single `curl -v -X POST` against `$INCIDENT_WEBHOOK_URL` before the drain would have caught the placeholder-paste in 5 seconds.

---

## 6. Where to go next

**Option 1 — Close Week 4 cleanly and start Week 5 fresh.** Open PR for `wk4/day3-incidents-mart` (schema source edit, mart SQL, dashboard JSON export, notifier, run.py changes), merge to master, delete the branch. Then pick a Week 5 theme from the HLD §11 roadmap (streaming / forecasting / API service / RCA engine).

**Option 2 — Pick up BKL items while the context is warm.** BKL-002 (detect idempotency) and BKL-004 (cell_id type) both reuse patterns we just built; low cognitive overhead to tackle this week before switching domains.

My call: **Option 1, with BKL-004 as the first Week 5 task** because it unblocks cleaner Grafana queries and removes the `::text` casts in `mart_incidents_timeline`.
