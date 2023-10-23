from resolve.core.utils import util

# Initialize common directory structure
dir_str = util.DirStructure()

# Initialize class to intercept print statements from Pyomo
stream = util.StreamToLogger(level="INFO")
