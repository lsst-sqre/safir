#######################################
Using Click for command-line interfaces
#######################################

The Python library Click_ is the recommended way of creating command-line interfaces for applications that use Safir.
Click provides a simple API for creating command-line interfaces that use the easily-extensible command and subcommand pattern, similar to Git and many other tools.

Safir provides some support functions to make those command-line interfaces easier to write.

Implementing a help command
===========================

Click provides native support for the ``--help`` command-line flag for all commands and subcommands.
However, another common pattern for good command-line tools is to support a separate ``help`` command that takes other commands as arguments.

For example, if the command-line tool :command:`example` has a command :command:`example create`, a common pattern is for :command:`example help create` to show the help output for that ``create`` command.
This should also work with nested subcommands, such as the command :command:`example create object` and the corresponding help command :command:`example help create object`.

Safir provides a utility function, `safir.click.display_help`, which implements this ``help`` command.
Here is the typical usage:

.. code-block:: python

   import click

   from safir.click import display_help


   @click.group(context_settings={"help_option_names": ["-h", "--help"]})
   @click.version_option(message="%(version)s")
   def main() -> None:
       """Example command-line interface."""


   @main.command()
   @click.argument("topic", default=None, required=False, nargs=1)
   @click.argument("subtopic", default=None, required=False, nargs=1)
   @click.pass_context
   def help(
       ctx: click.Context, topic: str | None, subtopic: str | None
   ) -> None:
       """Show help for any command."""
       display_help(main, ctx, topic, subtopic)

This also shows the recommended pattern for defining the top-level Click command group, which is conventionally called ``main``.

Additional commands can then be defined in the normal way, using the ``@main.command()`` decorator (or a nested command group under ``main``), and documented in the normal way using the ``help`` parameter to Click decorators and the docstring of the function defining the command.
That documentation will be picked up automatically by `safir.click.display_help`.

Running Click commands using asyncio
====================================

Click itself is a synchronous library and has no built-in support for command handlers using asyncio.
To make it easier to write command-line interfaces for asyncio applications, Safir provides the decorator `safir.asyncio.run_with_asyncio` that integrates with Click commands.

For example, here is the definition of a ``do-something`` command that uses asyncio:

.. code-block:: python

   import click

   from safir.asyncio import run_with_asyncio


   # Definition of main omitted.


   @main.command()
   @run_with_asyncio
   async def do_something() -> None:
       await some_async_call()

This decorator will invoke the decorated function with `asyncio.run`, so the caller must not already be inside an asyncio task.

This decorator can be used in any situation where a function needs to be invoked via `asyncio.run`, not just for Click commands, but Click commands are the most common instance of this need for applications based on Safir.
