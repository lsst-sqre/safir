.. currentmodule:: safir.uws

#######################
Defining service inputs
#######################

Your UWS service will take one more more input parameters.
The UWS library cannot know what those parameters are, so you will need to define them and pass that configuration into the UWS library configuration.
This is done by writing a FastAPI dependency that returns a Pydantic model for your job parameters.
See :doc:`define-models` for details on how to define that model.

Ways to create jobs
===================

There are three possible ways to create a job in UWS: ``POST`` to create an async job, ``POST`` to create a sync job, and ``GET`` to create a sync job.

An async job creates a job record and starts the operation in the background.
The client then needs to wait or poll for the job to complete and can retrieve the results from the job record.
Multiple results are supported, and each will have its own identifier.

A sync job creates the job, waits for it to complete, and returns the result.
Sync jobs can only be used for operations that complete relatively quickly, because many HTTP clients will not wait for long for a response.
Browsers will normally not wait more than a minute at most, and sync jobs are not suitable for any operation that takes longer than five minutes.
Sync jobs are not supported by default, but can be easily enabled.

Sync jobs can be created via either ``POST`` or ``GET``.
You can pick whether your application will support sync ``POST``, sync ``GET``, both, or neither.
Supporting ``GET`` makes it easier for people to assemble ad hoc jobs by writing the URL directly in their web browser.
However, due to unfixable web security limitations in the HTTP protocol, ``GET`` jobs can be created by any malicious site on the Internet, and therefore should not be supported if the operation of your service is destructive, expensive, or dangerous if performed by unauthorized people.

For each supported way to create a job, your application must provide a FastAPI dependency that reads input parameters via that method and returns the Pydantic model for parameters that you defined in :doc:`define-models`.

Async POST dependency
=====================

Supporting async ``POST`` is required.
First, writing a FastAPI dependency that accepts the input parameters for your job as `form parameters <https://fastapi.tiangolo.com/tutorial/request-forms/>`__.
Conventionally, this dependency goes into :file:`dependencies.py`.
Here is an example for a SODA service that performs circular cutouts:

.. code-block:: python
   :caption: dependencies.py

   from typing import Annotated

   from fastapi import Depends, Form

   from .models import CircleStencil, CutoutParameters


   async def post_params_dependency(
       *,
       id: Annotated[
           list[str] | None,
           Form(
               title="Source ID",
               description=(
                   "Identifiers of images from which to make a cutout. This"
                   " parameter is mandatory."
               ),
           ),
       ] = None,
       circle: Annotated[
           list[str] | None,
           Form(
               title="Cutout circle positions",
               description=(
                   "Circles to cut out. The value must be the ra and dec of the"
                   " center of the circle and then the radius, as"
                   " double-precision floating point numbers expressed as"
                   " strings and separated by spaces."
               ),
           ),
       ] = None,
   ) -> CutoutParameters:
       return CutoutParameters(
           ids=id,
           stencils=[CircleStencil.from_string(c) for c in circle],
       )

This first declares the input parameters, with full documentation, as FastAPI ``Form`` parameters.
Note that the type is ``list[str]``, which allows the parameter to be specified multiple times.
If the parameters for your service cannot be repeated, change this to `str` (or another appropriate basic type, such as `int`).

Then, it converts the form parameters into the Pydantic model for your job parameters.
Here, most of the work is done by the ``from_string`` static method on ``CircleStencil``, defined in :ref:`uws-model-parameters`.
This conversion should also perform any necessary input validation.

Async POST configuration
------------------------

Finally, you need to tell the UWS library about this configuration, and also provide some additional metadata for the route.
This is done in the ``async_post_route`` argument to `UWSAppSettings.build_uws_config` as mentioned in :ref:`uws-config`.
Now you can replace the ``...`` in that example with a full `UWSRoute` object.

Here is an example for the same cutout service:

.. code-block:: python
   :caption: config.py

   from safir.uws import UWSRoute

   from .dependencies import post_params_dependency


   async_post_route = UWSRoute(
       dependency=post_params_dependency,
       summary="Create async cutout job",
       description="Create a new UWS job to perform an image cutout",
   )

This would then be passed as the ``async_post_route`` argument.

The ``summary`` and ``description`` attributes are only used to generate the API documentation.
They contain a brief summary and a longer description of the async ``POST`` route and will be copied into the generated OpenAPI specification for the service.

Sync POST
=========

Supporting sync ``POST`` is very similar: define a FastAPI dependency that accepts ``POST`` parameters and returns your Pydantic parameter model, and then define a `UWSRoute` object including that dependency and pass it as the ``sync_post_route`` argument to `UWSAppSettings.build_uws_config`.
By default, sync ``POST`` is not supported.

Normally, the input parameters for sync ``POST`` will be the same as the input parameters for async ``POST``, so you can reuse the same FastAPI dependency.

Here is an example for the same cutout service:

.. code-block:: python
   :caption: config.py

   from safir.uws import UWSRoute

   from .dependencies import post_params_dependency


   sync_post_route = UWSRoute(
       dependency=post_params_dependency,
       summary="Synchronous cutout",
       description=(
           "Synchronously request a cutout. This will wait for the"
           " cutout to be completed and return the resulting image"
           " as a FITS file. The image will be returned via a"
           " redirect to a URL at the underlying object store."
       ),
   )

This would then be passed as the ``sync_post_route`` argument.

Sync GET
========

Supporting sync ``GET`` follows the same pattern, but here you will need to define a separate dependency that takes query parameters rather than form parameters.
Here is an example dependency for a cutout service:

.. code-block:: python
   :caption: dependencies.py

   from typing import Annotated

   from fastapi import Depends, Query

   from .models import CircleStencil, CutoutParameters


   async def get_params_dependency(
       *,
       id: Annotated[
           list[str],
           Query(
               title="Source ID",
               description=(
                   "Identifiers of images from which to make a cutout. This"
                   " parameter is mandatory."
               ),
           ),
       ],
       circle: Annotated[
           list[str],
           Query(
               title="Cutout circle positions",
               description=(
                   "Circles to cut out. The value must be the ra and dec of"
                   " the center of the circle and then the radius, as"
                   " double-precision floating point numbers expressed as"
                   " strings and separated by spaces."
               ),
           ),
       ],
   ) -> CutoutParameters:
       return CutoutParameters(
           ids=id,
           stencils=[CircleStencil.from_string(c) for c in circle],
       )

The body here is identical to the body of the dependency for ``POST``.
The difference is in how the parameters are defined (``Query`` vs. ``Form``).

As in the other cases, you will then need to pass a `UWSRoute` object as the ``sync_get_route`` argument to `UWSAppSettings.build_uws_config`.
Here is an example:

.. code-block:: python
   :caption: config.py

   from safir.uws import UWSRoute

   from .dependencies import get_params_dependency


   sync_post_route = UWSRoute(
       dependency=get_params_dependency,
       summary="Synchronous cutout",
       description=(
           "Synchronously request a cutout. This will wait for the"
           " cutout to be completed and return the resulting image"
           " as a FITS file. The image will be returned via a"
           " redirect to a URL at the underlying object store."
       ),
   )

This would then be passed as the ``sync_post_route`` argument.

Next steps
==========

- Write the backend worker :doc:`write-backend`
