.. currentmodule:: safir.uws

###########################
Define job parameter models
###########################

A UWS job is defined by its input parameters.
Unfortunately, due to issues with the IVOA UWS standard and the need for separation between the API and backend processing, the input parameters for a job have to be defined in five different ways.

#. A Pydantic API model representing the validated input parameters for a job.
   This is the canonical input form and corresponds to a native JSON API.
#. The parameters sent to the backend worker.
   Often, this may be the same as the API model, but best practice is to define two separate models.
   This allows the two models to change independently, permitting changes to the backend without changing the API or changes to the API without changing the backend code.
#. An XML representation of the input parameters.
   This is essentially a list of key/value pairs wrapped in a child class of `~vo_models.uws.models.Parameters` and is used for XML serialization and deserialization for the IVOA UWS protocol.
   This separate model is required because the IVOA UWS standard requires a very simplistic XML serialization of job parameters that flattens any complex structure into strings, and thus is not suitable for use as the general API model for many applications.
#. The input parameters for job creation via ``POST``, since the IVOA UWS standard requires support for job creation via form ``POST``.
#. The input parameters for job creation via ``GET``, used for sync jobs.
   Supporting this is optional.

In some cases (jobs whose parameters are all simple strings or numbers), the same model can be used for 1 and 4 by specifying it as a form parameter model.
Unfortunately, the same model cannot be used for 1 and 3 even for simple applications because the XML model requires additional structure that obscures the parameters and should not be included in the JSON API model.

Therefore, in the most general case, UWS applications must define three models for input parameters: the API model of parameters as provided by users via a JSON API, the model passed to the backend worker, and an XML model that flattens all parameters to strings.
The input parameters for job creation via ``POST`` and ``GET`` are discussed in :doc:`define-inputs`.

What parameters look like
=========================

In the IVOA UWS standard, input parameters for a job are a list of key/value pairs.
The value is always a string.
Other data types are not directly supported.

In the Safir UWS support, however, job parameters are allowed to be arbitrary Pydantic models.
The only requirement is that it must be possible to serialize the parameters to a list of key/value pairs so that they can be returned by IVOA UWS standard routes.
In other words, the internal representation can be as complex as you wish, but the IVOA UWS standard requires the input parameters come from query or form parameters and be representable as a list of key/value pairs.

Therefore, if your service needs a different data type as a parameter value, you will need to accept it as a string and then parse it into a more complex structure, and you will need to be able to convert your Pydantic model back to that list of strings.

.. _uws-worker-model:

Worker parameter model
======================

The UWS library uses a Pydantic model to convey the job parameters to the backend worker.
This Pydantic model is serialized to a JSON-compatible dictionary before being sent to the backend worker and then deserialized back into a Pydantic model in the backend.
Every field must therefore be JSON-serializable and deserializable.

Here is a simple example for a cutout service:

.. code-block:: python
   :caption: domain.py

   from pydantic import BaseModel, Field


   class Point(BaseModel):
       ra: float = Field(..., title="ICRS ra in degrees")
       dec: float = Field(..., title="ICRS dec in degrees")


   class WorkerCircleStencil(BaseModel):
       center: Point = Field(..., title="Center")
       radius: float = Field(..., title="Radius")


   class WorkerCutout(BaseModel):
       dataset_ids: list[str]
       stencils: list[WorkerCircleStencil]

This model will be imported by both the frontend and the backend worker, and therefore must not depend on any of the other frontend code or any Python libraries that will not be present in the worker backend.

Using complex data types in the worker model
--------------------------------------------

It will often be tempting to use more complex data types in the worker model because they are closer to the underlying implementation code and allow more validation to be performed in the frontend.
For example, one may wish the worker model to use astropy_ ``Angle`` and ``SkyCoord`` data types instead of simple Python floats.

.. _astropy: https://www.astropy.org/

This is possible, but be careful of serialization.
Astropy types do not serialize to JSON by default, so you will need to add serialization and deserialization support using Pydantic's facilities.

If you do this, consider adding a test case for your application that serializes your worker model to JSON, deserializes it back from JSON, and verifies that the resulting object matches the original object.

.. _uws-xml-model:

XML parameter model
===================

The XML parameter model must be a subclass of `~vo_models.uws.models.Parameters`.
Each parameter must be either a `~vo_models.uws.models.Parameter` or a ``MultiValuedParameter`` (for the case where the parameter can be specified more than once for simple list support).

This effectively requires serialization of all parameter values to strings, since the value attribute of a `~vo_models.uws.models.Parameter` only accepts simple strings to follow the IVOA UWS standard.

Here is a simple example for the same cutout service:

.. code-block:: python

   from pydantic import Field
   from vo_models.uws import MultiValuedParameter, Parameters


   class CutoutXmlParameters(Parameters):
       id: MultiValuedParameter = Field([])
       circle: MultiValuedParameter = Field([])

This class should not do any input validation other than validation of the permitted parameter IDs.
Input validation will be done by the input parameter model.

Single-valued parameters can use the syntax shown in `the vo-models documentation <https://vo-models.readthedocs.io/latest/pages/protocols/uws.html#parameters>`__ to define the parameter ID if it differs from the attribute name.
Optional multi-valued parameters, such as the above, have to use attribute names that match the XML parameter ID and the ``Field([])`` syntax to define the default to be an empty list, or you will get typing errors.

.. _uws-model-parameters:

Input parameter model
=====================

Every UWS application must define a Pydantic model for its input parameters.
This model must inherit from `ParametersModel`.

In addition to defining the parameter model, it must provide two methods: an instance method named ``to_worker_parameters`` that converts the model to the one that will be passed to the backend worker (see :ref:`uws-worker-model`), and an instance method named ``to_xml_model`` that converts the model to the XML model (see :ref:`uws-xml-model`).

Often, the worker parameter model will look very similar to the input parameter model.
They are still kept separate, since the input parameter model defines the API and the worker model defines the interface to the backend.
Over the lifetime of a service, those two interfaces often have to diverge, and it's cleaner to maintain that separation from the start.

Here is an example of a simple model for a cutout service:

.. code-block:: python
   :caption: models.py

   from typing import Self

   from pydantic import Field
   from safir.uws import ParametersModel
   from vo_models.uws import Parameter

   from .domain.cutout import Point, WorkerCircleStencil, WorkerCutout


   class CircleStencil(WorkerCircleStencil):
       @classmethod
       def from_string(cls, params: str) -> Self:
           ra, dec, radius = (float(p) for p in params.split())
           return cls(center=Point(ra=ra, dec=dec), radius=radius)

       def to_string(self) -> str:
           return f"{c.center.ra!s} {c.center.dec!s} {c.radius!s}"


   class CutoutParameters(ParametersModel[WorkerCutout, CutoutXmlParameters]):
       ids: list[str] = Field(..., title="Dataset IDs")
       stencils: list[CircleStencil] = Field(..., title="Cutout stencils")

       def to_worker_parameters(self) -> WorkerCutout:
           return WorkerCutout(dataset_ids=self.ids, stencils=self.stencils)

       def to_xml_model(self) -> CutoutXmlParameters:
           ids = [Parameter(id="id", value=i) for i in self.ids]
           circles = []
           for circle in self.stencils:
               circles.append(Parameter(id="circle", value=circle.to_string()))
           return CutoutXmlParameters(id=ids, circle=circles)

Notice that the input parameter model reuses some models from the worker (``Point`` and ``WorkerCircleStencil``), but adds a new class method to the latter via inheritance.
It also uses a different parameter for the dataset IDs (``ids`` instead of ``dataset_ids``), which is a trivial example of the sort of divergence one might see between input models and backend worker models.
``CutoutXmlParameters`` is defined in :ref:`uws-xml-model`.

The ``from_string`` class method of ``CircleStencil`` is not used here directly.
This will be used when parsing query or form inputs into a Pydantic model.
See :doc:`define-inputs` for more details.

The input models are also responsible for input parsing and validation, and converting to the worker and XML models.
The worker model should be in a separate file and kept as simple as possible, since it has to be imported by the backend worker, which may not have the dependencies installed to be able to import other frontend code.

The XML model must use simple key/value pairs of strings to satisfy the UWS XML API, so ``to_xml_model`` may need to do some conversion from the model to a string representation of the parameters.
This string representation should match the input accepted by the dependencies defined in :doc:`define-inputs`.

Update the application configuration
====================================

Now that you've defined the parameters model, you can update :file:`config.py` to pass that model to `UWSAppSettings.build_uws_config`, as mentioned in :ref:`uws-config`.

Set the ``parameters_type`` argument to the class name of the parameters model.
In the example above, that would be ``CutoutParameters``.

Set the ``job_summary_type`` argument to ``JobSummary[XmlModel]`` where ``XmlModel`` is whatever the class name of your XML parameter model is.
In the example above, that would be ``JobSummary[CutoutXmlParameters]``.
(Although this type is theoretically knowable through type propagation, limitations in the pydantic-xml_ library require specifying it separately.)

Next steps
==========

- Define the API parameters: :doc:`define-inputs`
- Write the backend worker :doc:`write-backend`
