.. currentmodule:: safir.uws

###########################
Define job parameter models
###########################

UWS models all parameters as simple lists of key/value pairs with string values.
However, for internal purposes, most applications will want a more sophisticated parameter model than that, with better input validation.
The frontend should parse and validate the input parameters so that it can fail quickly if they are invalid, rather than creating a job, dispatching it, and only then having it fail due to invalid parameters.

UWS applications therefore must define two models for input parameters, both Pydantic models.
The first is the model of parameters as provided by users, and is used to validate the input parameters.
The second is the model that will be passed to the backend worker.

.. _uws-worker-model:

Worker parameter model
======================

The UWS library uses a Pydantic model to convey the job parameters to the backend worker.
This Pydantic model is serialized to a JSON-compatible dictionary before being sent to the backend worker and then deserialized back into a Pydantic model in the backend.
Every field must therefore be JSON-serializable and deserializable.

Here is a simple example for a cutout service:

.. code-block:: python
   :caption: models/domain/cutout.py

   from pydantic import BaseModel, Field


   class Point(BaseModel):
       ra: float = Field(..., title="ICRS ra in degrees")
       dec: float = Field(..., title="ICRS dec in degrees")


   class CircleStencil(BaseModel):
       center: Point = Field(..., title="Center")
       radius: float = Field(..., title="Radius")


   class WorkerCutout(BaseModel):
       dataset_ids: list[str]
       stencils: list[WorkerCircleStencil]

This model will be imported by both the frontend and the backend worker, and therefor must not depend on any of the other frontend code or any Python libraries that will not be present in the worker backend.

Using complex data types in the worker model
--------------------------------------------

It will often be tempting to use more complex data types in the worker model because they are closer to the underlying implementation code and allow more validation to be performed in the frontend.
For example, one may wish the worker model to use astropy_ ``Angle`` and ``SkyCoord`` data types instead of simple Python floats.

.. _astropy: https://www.astropy.org/

This is possible, but be careful of serialization.
Astropy types do not serialize to JSON by default, so you will need to add serialization and deserialization support using Pydantic's facilities.

If you do this, consider adding a test case for your application that serializes your worker model to JSON, deserializes it back from JSON, and verifies that the resulting object matches the original object.

Input parameter model
=====================

Every UWS application must define a Pydantic model for its input parameters.
This model must inherit from `ParametersModel`.
In addition to defining the parameter model, it must provide two methods: a class method named ``from_job_parameters`` that takes as input the list of `UWSJobParameter` objects and returns an instance of the model, and an instance method named ``to_worker_parameters`` that converts the model to the one that will be passed to the backend worker (see :ref:`uws-worker-model`).

Often, the worker parameter model will look very similar to the input parameter model.
They are still kept separate, since the input parameter model defines the API and the worker model defines the interface to the backend.
Over the lifetime of a service, those two interfaces often have to diverge, and it's cleaner to maintain that separation from the start.

Here is an example of a simple model for a cutout service:

.. code-block:: python
   :caption: models/cutout.py

   from typing import Self

   from pydantic import Field
   from safir.uws import ParameterParseError, ParametersModel, UWSJobParameter

   from .domain.cutout import Point, WorkerCircleStencil, WorkerCutout


   class CircleStencil(WorkerCircleStencil):
       @classmethod
       def from_string(cls, params: str) -> Self:
           ra, dec, radius = (float(p) for p in params.split())
           return cls(center=Point(ra=ra, dec=dec), radius=radius)


   class CutoutParameters(ParametersModel[WorkerCutout]):
       ids: list[str] = Field(..., title="Dataset IDs")
       stencils: list[CircleStencil] = Field(..., title="Cutout stencils")

       @classmethod
       def from_job_parameters(cls, params: list[UWSJobParameter]) -> Self:
           ids = []
           stencils = []
           try:
               for param in params:
                   if param.parameter_id == "id":
                       ids.append(param.value)
                   else:
                       stencils.append(CircleStencil.from_string(param.value))
           except Exception as e:
               msg = f"Invalid cutout parameter: {type(e).__name__}: {e!s}"
               raise ParameterParseError(msg, params) from e
           return cls(ids=ids, stencils=stencils)

       def to_worker_parameters(self) -> WorkerCutout:
           return WorkerCutout(dataset_ids=self.ids, stencils=self.stencils)

Notice that the input parameter model reuses some models from the worker (``Point`` and ``WorkerCircleStencil``), but adds a new class method to the latter via inheritance.
It also uses a different parameter for the dataset IDs (``ids`` instead of ``dataset_ids``), which is a trivial example of the sort of divergence one might see between input models and backend worker models.

The input models are also responsible for input parsing and validation (note the ``from_job_parameters`` and ``from_string`` methods) and converting to the worker model.
The worker model should be in a separate file and kept as simple as possible, since it has to be imported by the backend worker, which may not have the dependencies installed to be able to import other frontend code.

Update the application configuration
====================================

Now that you've defined the parameters model, you can update :file:`config.py` to pass that model to `UWSAppSettings.build_uws_config`, as mentioned in :ref:`uws-config`.
Set the ``parameters_type`` argument to the class name of the parameters model.
In the example above, that would be ``CutoutParameters``.

Next steps
==========

- Write the backend worker :doc:`write-backend`
