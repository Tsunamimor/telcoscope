"""Verify the bundled RCA rule library loads and validates."""
from __future__ import annotations

from pathlib import Path

import yaml

from telcoscope.rca.schema import RuleLibrary


def test_rules_yaml_validates() -> None:
    """The shipped rules.yaml conforms to the RuleLibrary schema."""
    rules_path = Path(__file__).parents[2] / "src" / "telcoscope" / "rca" / "rules.yaml"
    assert rules_path.exists(), f"Expected rules.yaml at {rules_path}"

    with rules_path.open() as f:
        data = yaml.safe_load(f)

    library = RuleLibrary.model_validate(data)
    assert len(library.rules) >= 1


def test_rule_ids_unique() -> None:
    """No two rules share an id."""
    rules_path = Path(__file__).parents[2] / "src" / "telcoscope" / "rca" / "rules.yaml"
    with rules_path.open() as f:
        data = yaml.safe_load(f)
    library = RuleLibrary.model_validate(data)

    ids = [r.id for r in library.rules]
    assert len(ids) == len(set(ids)), "Duplicate rule ids found"


def test_every_rule_has_at_least_one_trigger() -> None:
    """No rule is firable without at least one trigger."""
    rules_path = Path(__file__).parents[2] / "src" / "telcoscope" / "rca" / "rules.yaml"
    with rules_path.open() as f:
        data = yaml.safe_load(f)
    library = RuleLibrary.model_validate(data)

    for rule in library.rules:
        assert len(rule.triggers) >= 1, f"Rule {rule.id} has no triggers"
