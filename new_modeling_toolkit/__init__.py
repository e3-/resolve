import importlib.metadata

__version__ = importlib.metadata.version(__package__)

from new_modeling_toolkit.core import linkage, three_way_linkage


__all__ = [
    "linkage",
    "system",
    "three_way_linkage",
]
