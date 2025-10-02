from new_modeling_toolkit.system.electric.resources.variable.solar import SolarResource
from new_modeling_toolkit.system.electric.resources.variable.solar import SolarResourceGroup
from tests.system.electric.resources import test_variable


class TestSolarResource(test_variable.TestVariableResource):
    _COMPONENT_CLASS = SolarResource
    _COMPONENT_NAME = "SolarResource1"
    _SYSTEM_COMPONENT_DICT_NAME = "solar_resources"


class TestSolarResourceGroup(test_variable.TestVariableResourceGroup, TestSolarResource):
    _COMPONENT_CLASS = SolarResourceGroup
    _COMPONENT_NAME = "solar_resource_group_0"
    _SYSTEM_COMPONENT_DICT_NAME = "solar_resource_groups"
