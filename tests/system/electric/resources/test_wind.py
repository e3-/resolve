import pytest

from new_modeling_toolkit.system.electric.resources.variable.wind import WindResource
from tests.system.electric.resources import test_variable

class TestWindResource(test_variable.TestVariableResource):
    _COMPONENT_CLASS = WindResource
    _COMPONENT_NAME = "WindResource1"
    _SYSTEM_COMPONENT_DICT_NAME = "wind_resources"

    def test_scale_resource_profile(self, make_component_copy):
        resource = make_component_copy()
        before = resource.power_output_max.data.sum()
        scalar = (
            1
            - 4 * 0.5
            + 0.5 * resource.power_output_max.data ** (-1 / 3)
            + 0.5 * 3 * resource.power_output_max.data ** (-2 / 3)
        )
        expected_after = (scalar * resource.power_output_max.data).clip(lower=0.0, upper=1.0).fillna(0).sum()
        expected_ratio = before / expected_after
        resource.scale_resource_profile(resource.power_output_max, 0.5)
        after = resource.power_output_max.data.sum()
        assert before / after == pytest.approx(expected_ratio)

        resource.scale_resource_profile(resource.power_output_max, 3)
        assert max(resource.power_output_max.data) == 1


class TestWindResourceGroup(test_variable.TestVariableResourceGroup, TestWindResource):
    _COMPONENT_CLASS = WindResource
    _COMPONENT_NAME = "wind_resource_group_0"
    _SYSTEM_COMPONENT_DICT_NAME = "wind_resource_groups"
