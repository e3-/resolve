from .linkage import Linkage
from kit.core.utils import util

# Initialize class to intercept print statements from Pyomo
stream = util.StreamToLogger(level="INFO")
dir_str = util.BaseDirStructure()
