##############################################
Sending messages and alerts to a Slack webhook
##############################################

It is sometimes useful for a web application to have a mechanism for reporting an urgent error or the results of a consistency audit to human administrators.
One convenient way to do this is to set up a Slack channel for that purpose and a `Slack incoming webhook <https://api.slack.com/messaging/webhooks>`__ for posting to that channel.

This is a write-only way of putting messages on a Slack channel.
The application cannot read messages; it can only send messages by posting them to the webhook URL.
Messages are normally formatted using Slack's `Block Kit API <https://api.slack.com/block-kit>`__.

Safir provides a client for posting such messages and support for using that client to post common types of alerts, such as uncaught exceptions.

Posting a message to a Slack webhook
====================================

Creating a Slack webhook client
-------------------------------

To post a message to Slack, first create a `~safir.slack.webhook.SlackWebhookClient`.
You will need to pass in the webhook URL (which should be injected into your application as a secret, since anyone who possesses the URL can post to the channel), the human-readable name of the application (used when reporting exceptions), and a structlog_ logger for reporting failures to post messages to Slack.

.. code-block:: python

   import structlog
   from safir.slack.webhook import SlackWebhookClient


   logger = structlog.get_logger(__name__)
   client = SlackWebhookClient(config.webhook_url, "App Name", logger)

This is a simplified example.
Often the logger will instead come from a FastAPI dependency (see :ref:`logging-in-handlers`).

Creating a Slack message
------------------------

Then, construct a `~safir.slack.blockkit.SlackMessage` that you want to post.
This has a main message in Slack's highly-simplified `mrkdwn variant of Markdown <https://api.slack.com/reference/surfaces/formatting>`__, zero or more fields, zero or more extra blocks, and zero or more attachments.

A field is a heading and a short amount of data (normally a few words or a short line) normally used to hold supplemental information about the message.
Possible examples are the username of the user that triggered the message, a formatted time when some event happened, or the route that was being accessed.
Fields will be formatted in two columns in the order given, left to right and then top to bottom.
Text in fields is limited to 2000 characters (after formatting) and will be truncated if it is longer, but normally should be much shorter than this.
A message may have at most 10 fields.

Longer additional data should go into an additional block.
Those blocks will be displayed in one column below the fields and main message.
Text in those fields is limited to 3000 characters (after formatting) and will be truncated if it is longer.

Attachments are additional blocks added after the message.
Slack will automatically shorten long attachments and add a "See more" option to expand them.
Attachments are also limited to 3000 characters (after formatting).

.. warning::

   Slack has declared attachments "legacy" and has warned that their behavior may change in the future to make them less visible.
   However, attachments are the only current supported way to collapse long fields by default with a "See more" option.
   Only use attachments if you need that Slack functionality; otherwise, use blocks.

Both fields and blocks can have either text, which is formatted in mrkdwn the same as the main message, or code, which is formatted in a code block.
If truncation is needed, text fields are truncated at the bottom and code blocks are truncated at the top.
(The code block truncation behavior is because JupyterLab failure messages have the most useful information at the bottom.)

All text fields except the main message are marked as verbatim from Slack's perspective, which means that channel and user references will not turn into links or notifications.
The main message is also verbatim by default, but this can be disabled by passing ``verbatim=False``
If it is disabled, so channel and user references will work as normal in Slack.
``verbatim=False`` should only be used when the message comes from trusted sources, not from user input.

Here's an example of constructing a message:

.. code-block:: python

   from safir.datetime import current_datetime, format_datetime_for_logging
   from safir.slack.blockkit import (
       SlackCodeBlock,
       SlackCodeField,
       SlackTextBlock,
       SlackTextField,
       SlackMessage,
   )


   now = format_datetime_for_logging(current_datetime())
   message = SlackMessage(
       message="This is the main part of the message *in mrkdwn*",
       fields=[
           SlackTextField(heading="Timestamp", text=now),
           SlackCodeField(heading="Code", code="some code"),
       ],
       blocks=[SlackTextBlock(heading="Log", text="some longer log data")],
       attachments=[SlackCodeBlock(heading="Errors", code="some long error")],
   )

Posting the message to Slack
----------------------------

Finally, post the message to the Slack webhook:

.. code-block:: python

   await client.post(message)

This method will never return an error.
If posting the message to Slack fails, an exception will be logged using the logger provided when constructing the client, but the caller will not be notified.

Reporting an exception to a Slack webhook
=========================================

One useful thing to use a Slack webhook for is to report unexpected or worrisome exceptions.
Safir provides a base class, `~safir.slack.blockkit.SlackException`, which can be used as a parent class for your application exceptions to produce a nicely-formatted error message in Slack.

The default `~safir.slack.blockkit.SlackException` constructor takes the username of the user who triggered the exception as an additional optional argument.
The username is also exposed as the ``user`` attribute of the class and can be set and re-raised by a calling context that knows the user.
For example, assuming that ``SomeAppException`` is a child class of `~safir.slack.blockkit.SlackException`:

.. code-block:: python

   try:
       do_something_that_may_raise()
   except SomeAppException as e:
       e.user = username
       raise

This same pattern can be used with additional attributes added by your derived exception class to annotate it with additional information from its call stack.

Then, to send the exception (here, ``exc``) to Slack, do:

.. code-block:: python

   await client.post_exception(exc)

Under the hood, this will call the ``to_slack`` method on the exception to get a formatted Slack message.
The default implementation uses the exception message as the main Slack message and adds fields for the exception type, the time at which the exception was raised, and the username if set.
Child classes can override this method to add additional information.
For example:

.. code-block:: python

   from safir.slack.blockkit import (
       SlackException,
       SlackMessage,
       SlackTextField,
   )


   class SomeAppException(SlackException):
       def __init__(self, msg: str, user: str, data: str) -> None:
           super().__init__(msg, user)
           self.data = data

       def to_slack(self) -> SlackMessage:
           message = super().to_slack()
           message.fields.append(
               SlackTextField(heading="Data", text=self.data)
           )
           return message

.. warning::

   The full exception message (although not the traceback) is sent to Slack, so it should not contain any sensitive information, security keys, or similar data.

Reporting HTTPX exceptions
--------------------------

A common source of exceptions in Safir applications are exceptions raised by HTTPX_ while making calls to other web services.
Safir provides a base class for those exceptions, `~safir.slack.blockkit.SlackWebException`, which behaves the same as `~safir.slack.blockkit.SlackException` but captures additional information from the underlying HTTPX exception.

The advantages of `~safir.slack.blockkit.SlackWebException` over using `~safir.slack.blockkit.SlackException` directly, possibly with the text of the HTTPX exception, are:

- If the exception is due to an error returned by the remote server, the stringification of the exception, and the main Slack message if posted to Slack, always includes the URL, method, and status code.
  (You therefore will want to override the ``__str__`` method if your URLs may contain secret data that should not be sent in Slack alerts, such as Slack webhook URLs.)
- The body of any reply is included in the stringification and in a block of the Slack message.
  (Again, override this behavior if the bodies of error replies may include secrets that should not be sent to Slack.)
- For other exceptions, the stringification and main Slack message include both the type and the stringification of the underlying exception.
- Where possible, the URL and method are included in a field in the Slack message.

The normal way to use this class or exception classes derived from it is to call the class method ``from_exception``, passing in the underlying HTTPX exception.
For example:

.. code-block:: python

   from httpx import AsyncClient, HTTPError
   from safir.slack.blockkit import SlackWebException


   class FooServiceError(SlackWebException):
       """An error occurred sending a request to the foo service."""


   async def do_something(client: AsyncClient) -> None:
       # ... set up some request to the foo service ...
       try:
           r = await client.get(url)
           r.raise_for_status()
       except HTTPError as e:
           raise FooServiceError.from_exception(e) from e

Note the ``from e`` clause when raising the derived exception, which tells Python to include the backtraces from both exceptions.
Higher-level code may then catch this exception and post it to Slack if desired.

As with `~safir.slack.blockkit.SlackException`, a username may be provided as a second argument to ``from_exception`` or set later by catching the exception, setting its ``user`` attribute, and re-raising it.

.. _slack-uncaught-exceptions:

Reporting uncaught exceptions to a Slack webhook
================================================

The above exception reporting mechanism only works with exceptions that were caught by the application code.
Uncaught exceptions are a common problem for most web applications and indicate some unanticipated error case.
Often, all uncaught exceptions should be reported to Slack so that someone can investigate, fix the error condition, and add code to detect that error in the future.

Safir provides a mechanism for a FastAPI app to automatically report all uncaught exceptions to Slack.
This is done through a custom route class, `~safir.slack.webhook.SlackRouteErrorHandler`, that checks every route for uncaught exceptions and reports them to Slack before re-raising them.

If the class is not configured with a Slack webhook, it does nothing but re-raise the exception, exactly as if it were not present.
Configuring a Slack incoming webhook is therefore not a deployment requirement for the application, only something that is used if it is available.

To configure this class, add code like the following in the same place the FastAPI app is constructed:

.. code-block:: python

   import structlog
   from safir.slack.webhook import SlackRouteErrorHandler


   structlog.get_logger(__name__)
   SlackRouteErrorHandler.initialize(
       config.slack_webhook, "Application Name", logger
   )

The arguments are the same as those to the constructor of `~safir.slack.webhook.SlackWebhookClient`.
The second argument, the application name, is used in the generated Slack message.
The logger will be used to report failures to send an alert to Slack, after which the original exception will be re-raised.

Then, use this as a custom class for every FastAPI router whose routes should report uncaught exceptions to Slack:

.. code-block:: python

   from fastapi import APIRouter
   from safir.slack.webhook import SlackRouteErrorHandler


   router = APIRouter(route_class=SlackRouteErrorHandler)

Exceptions inheriting from :exc:`fastapi.HTTPException`, :exc:`fastapi.exceptions.RequestValidationError`, or :exc:`starlette.exceptions.HTTPException` will not be reported.
These exceptions have default handlers and are therefore not uncaught exceptions.

.. warning::

   The full exception message (although not the traceback) is sent to Slack.
   Since the exception is by definition unknown, this carries some inherent risk of disclosing security-sensitive data to Slack.
   If you use this feature, consider making the Slack channel to which the incoming webhook is connected private, and closely review exception handling in any code related to secrets.

If your application has additional exceptions for which you are installing exception handlers, those exceptions should inherit from `~safir.slack.webhook.SlackIgnoredException`.
This exception class has no behavior and can be safely used as an additional parent class with other base classes.
It flags the exception for this route class so that it will not be reported to Slack.

Testing code that uses a Slack webhook
======================================

The `safir.testing.slack` module provides a simple mock of a Slack webhook that accumulates every message sent to it.

To use it, first define a fixture:

.. code-block:: python

   import pytest
   import respx
   from safir.testing.slack import MockSlackWebhook, mock_slack_webhook


   @pytest.fixture
   def mock_slack(respx_mock: respx.Router) -> MockSlackWebhook:
       return mock_slack_webhook(config.slack_webhook, respx_mock)

Replace ``config.slack_webhook`` with whatever webhook configuration your application uses.
You will need to add ``respx`` as a dev dependency of your application.

Then, in a test, use a pattern like the following:

.. code-block:: python

   import pytest
   from httpx import AsyncClient
   from safir.testing.slack import MockSlackWebhook


   @pytest.mark.asyncio
   def test_something(
       client: AsyncClient, mock_slack: MockSlackWebhook
   ) -> None:
       # Do something with client that generates Slack messages.
       assert mock_slack.messages == [{...}, {...}]

The ``url`` attribute of the `~safir.testing.slack.MockSlackWebhook` object contains the URL it was configured to mock, in case a test needs convenient access to it.
