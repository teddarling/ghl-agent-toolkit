"""Tests for the ghl CLI."""

import importlib.metadata

from typer.testing import CliRunner

from ghl_toolkit.cli import app

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Inspect GoHighLevel data and run gated agents against it." in result.output


def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.output.strip() == importlib.metadata.version("ghl-toolkit")
