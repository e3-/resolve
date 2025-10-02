import copy

import pytest

from new_modeling_toolkit.system import System
from new_modeling_toolkit.system.fuel.candidate_fuel import CandidateFuel
from tests.system.component_test_template import ComponentTestTemplate


@pytest.mark.skip("Skip until fuels opt tests are written")
class TestFinalFuel(ComponentTestTemplate):
    _TEST_SYSTEM_NAME: str = "TEST_fuels"
    _START_YEAR: int = 2020
    _END_YEAR: int = 2050

    @pytest.fixture(scope="class")
    def mini_system(self, dir_structure):
        """Creates an instance of the resource group that is associated with the class to be tested.

        This method is not intended to be called directly. Instead, use the `make_resource_group_copy()` fixture,
        which is a factory for generating a clean copy of the resource group.
        """
        group = System(
            name=self._TEST_SYSTEM_NAME,
            dir_str=dir_structure,
            year_start=self._START_YEAR,
            year_end=self._END_YEAR,
            scenarios=["Test Scenario"],
            tool_name="pathways",
        )

        return group

    def test_candidate_fuels_list(self, mini_fuels_system):
        """
        Test the candidate_fuels_list property. Assert that:
        - the output is a list of expected CandidateFuel objects for every final fuel
        """
        for final_fuel in mini_fuels_system.final_fuels.values():
            candidate_fuels_list = final_fuel.candidate_fuels_list
            assert isinstance(candidate_fuels_list, list)
            assert all(isinstance(value, CandidateFuel) for value in final_fuel.candidate_fuels_list)
            assert len(final_fuel.candidate_fuels) == len(candidate_fuels_list)

    def test_validate_emissions_trajectory_override_fuel(self, mini_fuels_system):
        """
        Test the validate_emissions_trajectory_override_fuel function. Assert that:
        - for every final_fuel that is not electricity, default emissions trajectory override is False
        - for every final_fuel that is not electricity, error will be raised if emissions trajectory override is True
        - for electricity, no error will be raised regardless of emissions trajectory override
        """
        for final_fuel_name in mini_fuels_system.final_fuels.keys():
            final_fuel = copy.deepcopy(mini_fuels_system.final_fuels[final_fuel_name])
            # no error should be raised, attribute default should be False
            if final_fuel_name is not "Electricity":
                final_fuel.validate_emissions_trajectory_override_fuel()

                # update attribute to True, assert that error is raised
                with pytest.raises(NotImplementedError):
                    final_fuel.fuel_is_using_emissions_trajectory_override = True

            else:
                # should not raise any errors for Electricity regardless of emissions trajectory override
                final_fuel.fuel_is_using_emissions_trajectory_override = False
                final_fuel.validate_emissions_trajectory_override_fuel()

                final_fuel.fuel_is_using_emissions_trajectory_override = True
                final_fuel.validate_emissions_trajectory_override_fuel()
