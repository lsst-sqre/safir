from documenteer.conf.guide import *

# Disable JSON schema because it doesn't seem that useful and apparently can't
# deal with generics, so it produces warnings for the UWS Job model.
autodoc_pydantic_model_show_json = False

html_sidebars["api"] = []  # no sidebar on the API page
