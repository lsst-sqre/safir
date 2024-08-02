"""Help command implementation for Click."""

from __future__ import annotations

import click

__all__ = ["display_help"]


def display_help(
    main: click.Group,
    ctx: click.Context,
    topic: str | None = None,
    subtopic: str | None = None,
) -> None:
    """Show help for a Click command.

    This function implements a help command for command-line interfaces using
    Click_. It supports commands and subcommands, displaying the same
    information as would be shown by ``--help``. The resulting help text is
    displayed with `click.echo`.

    Parameters
    ----------
    main
        Top-level Click command group.
    ctx
        Click context.
    topic
        Command for which to get help.
    subtopic
        Subcommand of that command for which to get help.

    Raises
    ------
    click.UsageError
        Raised if the given help topic or subtopic does not correspond to a
        registered Click command.
    RuntimeError
        Raised if the Click context has no parent, meaning that this was
        called with an invalid context or from the top-level Click command.

    Returns
    -------
    `None`

    Examples
    --------
    This function should normally be called from a top-level ``help`` command.
    Assuming that the top-level Click group is named ``main``, here is the
    typical usage:

    .. code-block:: python

       @main.command()
       @click.argument("topic", default=None, required=False, nargs=1)
       @click.argument("subtopic", default=None, required=False, nargs=1)
       @click.pass_context
       def help(
           ctx: click.Context, topic: str | None, subtopic: str | None
       ) -> None:
           display_help(main, ctx, topic, subtopic)
    """
    if not topic:
        if not ctx.parent:
            raise RuntimeError("help called without topic or parent")
        click.echo(ctx.parent.get_help())
        return
    if topic not in main.commands:
        raise click.UsageError(f"Unknown help topic {topic}", ctx)
    if not subtopic:
        ctx.info_name = topic
        click.echo(main.commands[topic].get_help(ctx))
        return

    # Subtopic handling. This requires some care with typing, since the
    # commands attribute (although present) is not documented, and the
    # get_command method is only available on MultiCommands.
    group = main.commands[topic]
    if isinstance(group, click.MultiCommand):
        command = group.get_command(ctx, subtopic)
        if command:
            ctx.info_name = f"{topic} {subtopic}"
            click.echo(command.get_help(ctx))
            return

    # Fall through to the error case of no subcommand found.
    msg = f"Unknown help topic {topic} {subtopic}"
    raise click.UsageError(msg, ctx)
