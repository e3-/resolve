from typing import ClassVar

from new_modeling_toolkit.system.electric.resources.variable.variable import VariableResource
from new_modeling_toolkit.system.electric.resources.variable.variable import VariableResourceGroup


class SolarResource(VariableResource):
    SAVE_PATH: ClassVar[str] = "resources/solar"


class SolarResourceGroup(VariableResourceGroup, SolarResource):
    SAVE_PATH: ClassVar[str] = "resources/solar/groups"
    _NAME_PREFIX: ClassVar[str] = "solar_resource_group"
    _GROUPING_CLASS = SolarResource
