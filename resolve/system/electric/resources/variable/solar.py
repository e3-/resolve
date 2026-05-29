from typing import ClassVar

from kit.system.electric.resources.variable.solar import BaseSolarResource
from kit.system.electric.resources.variable.solar import BaseSolarResourceGroup

from resolve.system.electric.resources.variable.variable import VariableResource
from resolve.system.electric.resources.variable.variable import VariableResourceGroup


class SolarResource(BaseSolarResource, VariableResource):
    SAVE_PATH: ClassVar[str] = "resources/solar"


class SolarResourceGroup(BaseSolarResourceGroup, VariableResourceGroup, SolarResource):
    SAVE_PATH: ClassVar[str] = "resources/solar/groups"
    _NAME_PREFIX: ClassVar[str] = "solar_resource_group"
    _GROUPING_CLASS = SolarResource
