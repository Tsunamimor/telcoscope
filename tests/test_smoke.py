"""Smoke tests — fastest signal that the package is importable and wired up."""
from __future__ import annotations


def test_package_imports() -> None:
    """Package can be imported and exposes a version string."""
    import telcoscope

    assert telcoscope.__version__
    assert isinstance(telcoscope.__version__, str)


def test_config_loads() -> None:
    """Settings instantiates without raising and exposes expected fields."""
    from telcoscope.config import settings

    assert settings.postgres_host
    assert settings.postgres_port > 0
    assert settings.narrator_mode in {"mock", "live"}


def test_postgres_url_is_well_formed() -> None:
    """SQLAlchemy URL is constructed from settings without raising."""
    from telcoscope.config import settings

    url = settings.postgres_url
    assert url.startswith("postgresql+psycopg://")
    assert str(settings.postgres_port) in url
