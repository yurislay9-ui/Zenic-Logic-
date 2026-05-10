"""
TITAN OMNISCALE X - AppGenerator (Facade)

Thin facade that re-exports all public symbols from the
app_gen_parts sub-package.  The original 1 297-line module has been
split into logical sub-modules; this file preserves the public API.

Sub-modules:
  - app_gen_parts.types:                GeneratedProject dataclass, PROJECTS_DIR constant
  - app_gen_parts.file_generators:      FileGeneratorMixin (model, route, config file generation)
  - app_gen_parts.service_generators:   ServiceGeneratorMixin (service layer generation)
  - app_gen_parts.template_generators:  TemplateGeneratorMixin (template-based code generation)
  - app_gen_parts.utils:                UtilsMixin (utility and helper methods)
  - app_gen_parts.core:                 AppGenerator class (inherits all mixins)

Import path unchanged:
    from src.core.app_generator import AppGenerator, GeneratedProject

Public API:
  Classes:    AppGenerator, GeneratedProject, FileGeneratorMixin, ServiceGeneratorMixin,
              TemplateGeneratorMixin, UtilsMixin
  Constants:  PROJECTS_DIR
"""

from src.core.app_gen_parts import (
    AppGenerator,
    GeneratedProject,
    PROJECTS_DIR,
    FileGeneratorMixin,
    ServiceGeneratorMixin,
    TemplateGeneratorMixin,
    UtilsMixin,
)

__all__ = [
    "AppGenerator",
    "GeneratedProject",
    "PROJECTS_DIR",
    "FileGeneratorMixin",
    "ServiceGeneratorMixin",
    "TemplateGeneratorMixin",
    "UtilsMixin",
]
