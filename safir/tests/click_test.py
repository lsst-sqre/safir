"""Tests for Click utility functions."""

from __future__ import annotations

import click
from click.testing import CliRunner

from safir.click import display_help


def test_display_help() -> None:
    @click.group()
    def main() -> None:
        """Run some command."""

    @main.command()
    @click.argument("topic", default=None, required=False, nargs=1)
    @click.argument("subtopic", default=None, required=False, nargs=1)
    @click.pass_context
    def help(
        ctx: click.Context, topic: str | None, subtopic: str | None
    ) -> None:
        """Show help for any command."""
        display_help(main, ctx, topic, subtopic)

    @main.command()
    def foo() -> None:
        """Run foo."""
        click.echo("Ran foo")

    @main.group()
    def bar() -> None:
        """Bar commands."""

    @bar.command()
    def something() -> None:
        """Do something with a bar."""

    runner = CliRunner()
    result = runner.invoke(main, ["help"], catch_exceptions=False)
    assert "Run some command" in result.output
    result = runner.invoke(main, ["help", "foo"], catch_exceptions=False)
    assert "main foo [OPTIONS]" in result.output
    assert "Run foo" in result.output
    result = runner.invoke(
        main, ["help", "bar", "something"], catch_exceptions=False
    )
    assert "main bar something [OPTIONS]" in result.output
    assert "Do something with a bar" in result.output
