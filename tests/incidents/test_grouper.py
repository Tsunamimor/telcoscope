"""Unit tests for the incident grouper.

Pure-function tests — no DB, no I/O, no fixtures. Each test builds its
inputs inline so a failing test tells you exactly what it exercises.
"""

from datetime import UTC, datetime, timedelta

from telcoscope.incidents.grouper import GAP_THRESHOLD, Incident, group_anomalies

T0 = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)


def _anom(
    cell: int = 1001,
    offset_hours: float = 0,
    severity: str = "minor",
    method: str = "statistical",
    kpi: str = "rrc_conn_setup_sr",
) -> dict:
    return {
        "cell_id": cell,
        "ts": T0 + timedelta(hours=offset_hours),
        "severity": severity,
        "method": method,
        "kpi_name": kpi,
    }


def test_empty_input_returns_empty_list():
    assert group_anomalies([]) == []


def test_single_anomaly_produces_one_incident():
    result = group_anomalies([_anom()])
    assert len(result) == 1
    inc = result[0]
    assert inc.cell_id == 1001
    assert inc.ts_start == T0
    assert inc.ts_end == T0
    assert inc.detection_count == 1


def test_two_anomalies_within_gap_group_into_one_incident():
    anoms = [_anom(offset_hours=0), _anom(offset_hours=1)]
    result = group_anomalies(anoms)
    assert len(result) == 1
    assert result[0].detection_count == 2
    assert result[0].ts_start == T0
    assert result[0].ts_end == T0 + timedelta(hours=1)


def test_two_anomalies_beyond_gap_split_into_two_incidents():
    anoms = [_anom(offset_hours=0), _anom(offset_hours=3)]
    result = group_anomalies(anoms)
    assert len(result) == 2
    assert all(i.detection_count == 1 for i in result)


def test_different_cells_always_split():
    anoms = [_anom(cell=1001), _anom(cell=1002)]
    result = group_anomalies(anoms)
    assert len(result) == 2
    assert {i.cell_id for i in result} == {1001, 1002}


def test_mixed_severity_rolls_up_to_max():
    anoms = [
        _anom(offset_hours=0, severity="minor"),
        _anom(offset_hours=1, severity="critical"),
        _anom(offset_hours=1.5, severity="major"),
    ]
    result = group_anomalies(anoms)
    assert len(result) == 1
    assert result[0].severity == "critical"


def test_methods_deduplicated_and_sorted():
    anoms = [
        _anom(offset_hours=0, method="statistical"),
        _anom(offset_hours=1, method="isolation_forest"),
        _anom(offset_hours=1.5, method="statistical"),
    ]
    result = group_anomalies(anoms)
    assert result[0].methods == ("isolation_forest", "statistical")


def test_dominant_kpi_is_most_frequent():
    anoms = [
        _anom(offset_hours=0, kpi="erab_drop_rate"),
        _anom(offset_hours=0.5, kpi="erab_drop_rate"),
        _anom(offset_hours=1, kpi="rrc_conn_setup_sr"),
    ]
    result = group_anomalies(anoms)
    assert result[0].dominant_kpi == "erab_drop_rate"


def test_ts_span_covers_min_to_max_regardless_of_input_order():
    anoms = [
        _anom(offset_hours=1),
        _anom(offset_hours=0),  # out of order on purpose
        _anom(offset_hours=2),
    ]
    result = group_anomalies(anoms)
    assert result[0].ts_start == T0
    assert result[0].ts_end == T0 + timedelta(hours=2)


def test_exact_gap_boundary_still_groups():
    """A gap of exactly GAP_THRESHOLD should still count as 'within gap'."""
    anoms = [
        _anom(offset_hours=0),
        _anom(offset_hours=GAP_THRESHOLD.total_seconds() / 3600),
    ]
    result = group_anomalies(anoms)
    assert len(result) == 1


def test_returns_frozen_incident_instances():
    result = group_anomalies([_anom()])
    assert isinstance(result[0], Incident)
