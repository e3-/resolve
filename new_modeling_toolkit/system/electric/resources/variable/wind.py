from typing import ClassVar

from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.system.electric.resources.variable.variable import VariableResource
from new_modeling_toolkit.system.electric.resources.variable.variable import VariableResourceGroup


class WindResource(VariableResource):
    SAVE_PATH: ClassVar[str] = "resources/wind"

    @classmethod
    def scale_resource_profile(cls, profile: ts.Timeseries, scalar: float) -> ts.Timeseries:
        """
        Wind power scales cubicly with wind speed
        """
        scalar = 1 - 4 * scalar + scalar * profile.data ** (-1 / 3) + scalar * 3 * profile.data ** (-2 / 3)
        profile.data = (scalar * profile.data).clip(lower=0.0, upper=1.0).fillna(0)
        return profile


class WindResourceGroup(VariableResourceGroup, WindResource):
    SAVE_PATH: ClassVar[str] = "resources/wind/groups"
    _NAME_PREFIX: ClassVar[str] = "wind_resource_group"
    _GROUPING_CLASS = WindResource
