from documenteer.conf.guide import *

# Disable JSON schema because it doesn't seem that useful and apparently can't
# deal with generics, so it produces warnings for the UWS Job model.
autodoc_pydantic_model_show_json = False

html_sidebars["api"] = []  # no sidebar on the API page

# Bug in sphinx-autodoc-typehints 3.11.0 with PaginatedList.from_transform.
# Revisit once Sphinx is no longer pinned to an old version by documenteer.
suppress_warnings = ["sphinx_autodoc_typehints"]
