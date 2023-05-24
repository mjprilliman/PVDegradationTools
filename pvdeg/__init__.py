import logging
from pathlib import Path
import sys

#TODO: Delete once all functions are split up into separate files
from .main import StressFactors, Degradation, Scenario

from . import cli
from . import design
from . import humidity
from . import spectral
from . import standards
from . import temperature
from . import utilities
from . import collection
from . import letid
from . import weather
from . import _version

__version__ = _version.get_versions()['version']

PVD_DIR = Path(__file__).parent
REPO_NAME = __name__
TEST_DATA_DIR = PVD_DIR.parent / "tests" / "data"

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
logger.setLevel("DEBUG")
