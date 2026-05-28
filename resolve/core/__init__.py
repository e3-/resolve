from kit.core.utils.util import StreamToLogger

from resolve.core.utils import util

# Initialize common directory structure
dir_str = util.DirStructure()


# Initialize class to intercept print statements from Pyomo
stream = StreamToLogger(level="INFO")


__all__ = [
    "linkage",
    "component",
    "three_way_linkage",
]
