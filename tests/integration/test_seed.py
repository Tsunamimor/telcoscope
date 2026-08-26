"""Integration test: generator runs end-to-end at small scale."""
import pytest

from telcoscope.synth.generator import generate


@pytest.mark.integration
def test_small_generation():
    data = generate(num_cells=5, num_days=2, seed=42)
    assert len(data.dim_cell) == 5
    assert len(data.pm_measurements) == 5 * 2 * 24 * 14
    assert len(data.dim_counter) == 14
    assert data.pm_measurements.select("value").min().item() >= 0