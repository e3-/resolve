import importlib.metadata

__version__ = importlib.metadata.version(__package__)

from resolve.core import linkage, three_way_linkage


__all__ = [
    "linkage",
    "system",
    "three_way_linkage",
]
