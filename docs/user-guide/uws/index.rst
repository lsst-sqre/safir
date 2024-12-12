#########################
Building UWS applications
#########################

Universal Worker Service (UWS) is an `IVOA standard <https://www.ivoa.net/documents/UWS/20161024/REC-UWS-1.1-20161024.html>`__ for writing possibly-asynchronous web services for astronomy.
Safir provides a comprehensive library for writing services that use this standard.
In addition to implementing the UWS protocol, this library dispatches the underlying work to an arq_ worker, allowing that worker to be based on a Rubin Science Pipelines stack container and reuse the astronomy code written for Rubin Observatory.

Applications built with this framework have three components:

#. A frontend web service that takes requests that follow the UWS protocol.
#. A backend arq_ worker, possibly running on a different software stack, that does the work.
#. A database arq_ worker that handles bookkeeping and result processing for the backend worker.
   This bookkeeping is done via the Wobbly_ service so that services do not have to manage their own underying PostgreSQL database.

Incoming requests are turned into arq_ jobs, processed by the backend worker, uploaded to Google Cloud Storage, recorded in a database, and then returned to the user via a frontend that reads the result URLs and other metadata from the database.

Frontend applications that use this library must depend on ``safir[uws]``.
The backend worker (see :doc:`write-backend`) will depend on ``safir-arq``.

Guides
======

.. toctree::
   :titlesonly:

   create-a-service
   define-models
   define-inputs
   write-backend
   testing
