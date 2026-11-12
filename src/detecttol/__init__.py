"""detectTOL: verifiable mechanical tolerance stack-up analysis.

Units are millimetres and radians internally.
"""

import logging

from detecttol.core.analyze import analyze
from detecttol.core.models import (
    AnalysisConfig,
    Contributor,
    MonteCarloConfig,
    Requirement,
    Stack,
)
from detecttol.core.results import StackResult

__version__ = "0.1.0.dev0"

# Library convention: stay silent unless the application configures logging.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "AnalysisConfig",
    "Contributor",
    "MonteCarloConfig",
    "Requirement",
    "Stack",
    "StackResult",
    "__version__",
    "analyze",
]
