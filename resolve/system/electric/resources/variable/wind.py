from typing import ClassVar

from kit.system.electric.resources.variable.wind import BaseWindResource
from kit.system.electric.resources.variable.wind import BaseWindResourceGroup

from resolve.core.temporal import timeseries as ts
from resolve.system.electric.resources.variable.variable import VariableResource
from resolve.system.electric.resources.variable.variable import VariableResourceGroup


class WindResource(BaseWindResource, VariableResource):
    SAVE_PATH: ClassVar[str] = "resources/wind"

    @classmethod
    def scale_resource_profile(cls, profile: ts.Timeseries, scalar: float) -> ts.Timeseries:
        """
        Wind power scales cubicly with wind speed
        """
        scalar = 1 - 4 * scalar + scalar * profile.data ** (-1 / 3) + scalar * 3 * profile.data ** (-2 / 3)
        profile.data = (scalar * profile.data).clip(lower=0.0, upper=1.0).fillna(0)
        return profile


class WindResourceGroup(BaseWindResourceGroup, VariableResourceGroup, WindResource):
    SAVE_PATH: ClassVar[str] = "resources/wind/groups"
    _NAME_PREFIX: ClassVar[str] = "wind_resource_group"
    _GROUPING_CLASS = WindResource
