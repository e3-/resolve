import copy

import numpy as np
import pandas as pd
import pytest

from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.system import GenericResource
from new_modeling_toolkit.system.fuel.candidate_fuel import CandidateFuel
from new_modeling_toolkit.system.generics.energy import _EnergyCarrier
from new_modeling_toolkit.system.pollution.pollutant import Pollutant
from tests.system.generics.test_energy import TestCommodityEnergyCarrier
from tests.system.generics.test_energy import TestEnergyCarrier


class TestCandidatefuel(TestEnergyCarrier):
    _COMPONENT_CLASS = CandidateFuel
    _COMPONENT_NAME = "CandidateFuel2"
    _SYSTEM_COMPONENT_DICT_NAME = "candidate_fuels"


class TestCommodityCandidateFuel(TestCommodityEnergyCarrier):

    _COMPONENT_CLASS = CandidateFuel
    _COMPONENT_NAME = "CandidateFuel1"
    _SYSTEM_COMPONENT_DICT_NAME = "candidate_fuels"

    def test_commodity_flag(self, test_candidate_fuel_1):
        cfuel = test_candidate_fuel_1.copy()

        assert cfuel.commodity is cfuel.fuel_is_commodity_bool
        assert cfuel.commodity == cfuel.fuel_is_commodity_bool
        assert cfuel.model_fields["commodity"].description == _EnergyCarrier.model_fields["commodity"].description

    def test_fuel_price_per_mmbtu(self, test_candidate_fuel_1):

        cfuel = test_candidate_fuel_1.copy()

        assert cfuel.price_per_unit is cfuel.fuel_price_per_mmbtu
        pd.testing.assert_series_equal(cfuel.price_per_unit.data, cfuel.fuel_price_per_mmbtu.data, check_names=True)

    def update_resources_fuel_consumption(self, cfuel: CandidateFuel):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        second_year = pd.Timestamp("2030-01-01 00:00:00")

        cfuel.resources["ThermalResource1"].instance_to.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
            cfuel.name,
            first_year,
            :,
            :,
        ] = 15
        cfuel.resources["ThermalResource1"].instance_to.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
            cfuel.name,
            second_year,
            :,
            :,
        ] = 100

        cfuel.resources["ThermalResource2"].instance_to.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
            cfuel.name,
            first_year,
            :,
            :,
        ] = 20
        cfuel.resources["ThermalResource2"].instance_to.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
            cfuel.name,
            second_year,
            :,
            :,
        ] = 200

        cfuel.resources[
            "ThermalUnitCommitmentResource"
        ].instance_to.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
            cfuel.name,
            first_year,
            :,
            :,
        ] = 25
        cfuel.resources[
            "ThermalUnitCommitmentResource"
        ].instance_to.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
            cfuel.name,
            second_year,
            :,
            :,
        ] = 300

        return cfuel

    def update_non_resource_consumption(self, cfuel: CandidateFuel):
        for consumer in cfuel.consumers.values():
            if not isinstance(consumer, GenericResource):
                consumer.formulation_block.consumption[cfuel.name, :, :, :] = 0

        return cfuel

    def test_total_consumption(self, make_component_with_block_copy):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        second_year = pd.Timestamp("2030-01-01 00:00:00")

        cfuel = make_component_with_block_copy()
        cfuel = self.update_resources_fuel_consumption(cfuel)
        cfuel = self.update_non_resource_consumption(cfuel)

        block = cfuel.formulation_block
        (dispatch_window, timestamp) = block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS[1]

        assert block.total_consumption[first_year, dispatch_window, timestamp].expr() == 15 + 20 + 25
        assert block.total_consumption[second_year, dispatch_window, timestamp].expr() == 100 + 200 + 300

    def test_annual_total_consumption(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        second_year = pd.Timestamp("2030-01-01 00:00:00")

        cfuel = make_component_with_block_copy()
        cfuel = self.update_resources_fuel_consumption(cfuel)
        cfuel = self.update_non_resource_consumption(cfuel)
        block = cfuel.formulation_block

        assert block.annual_total_consumption[first_year].expr() == (
            0.6 * 365 * (15 * 3)
            + 0.4 * 365 * (15 * 3)
            + 0.6 * 365 * (20 * 3)
            + 0.4 * 365 * (20 * 3)
            + 0.6 * 365 * (25 * 3)
            + 0.4 * 365 * (25 * 3)
        )

        assert block.annual_total_consumption[second_year].expr() == (
            0.6 * 365 * (100 * 3)
            + 0.4 * 365 * (100 * 3)
            + 0.6 * 365 * (200 * 3)
            + 0.4 * 365 * (200 * 3)
            + 0.6 * 365 * (300 * 3)
            + 0.4 * 365 * (300 * 3)
        )

    # TODO: Return to those tests that rely on the mini_fuels_system. They look to be used for PATHWAYS, so we will
    #  need to make sure they work if PATHWAYS updates to using a more recent version of kit.
    @pytest.mark.skip(reason="mini_fuels_system is currently not active in test suite")
    def test_final_fuel_name(self, mini_fuels_system):
        """
        Test final_fuel_name property. Assert that:
        - the final_fuel_name is expected for every candidate fuel in the mini_fuels_system
        - the final_fuel_name is type str
        """
        candidate_fuel = mini_fuels_system.candidate_fuels["Fossil Natural Gas"]
        assert candidate_fuel.final_fuel_name == "Natural Gas"

        for final_fuel in mini_fuels_system.final_fuels.values():
            cfuel_final_fuel_name_list = [cfuel.final_fuel_name for cfuel in final_fuel.candidate_fuels_list]
            assert all(element == final_fuel.name for element in cfuel_final_fuel_name_list)
            assert all(isinstance(name, str) for name in cfuel_final_fuel_name_list)

    @pytest.mark.skip(reason="mini_fuels_system is currently not active in test suite")
    def test_pollutant_list(self, mini_fuels_system):
        """
        Test the pollutant_list property. Assert that:
        - it returns a list of the expected Pollutant type
        """
        for cfuel_name, cfuel in mini_fuels_system.candidate_fuels.items():
            pollutant_list = cfuel.pollutant_list
            expected_list = [linkage.instance_to for linkage in list(cfuel.pollutants.values())]

            assert isinstance(pollutant_list, list)
            assert all(isinstance(p, Pollutant) for p in pollutant_list)
            assert all([a == b for a, b in zip(expected_list, pollutant_list)])

    @pytest.mark.skip(reason="mini_fuels_system is currently not active in test suite")
    def test_candidate_fuel_blend(self, mini_fuels_system):
        """
        Test the candidate_fuel_blend function. Assert that:
        - it returns a pd Series type
        - it returns expected values based on hard-coded attributes in the mini_fuels_system class fixture
        """
        sector = "Industry"
        candidate_fuel = mini_fuels_system.candidate_fuels["Fossil Natural Gas"]

        result = candidate_fuel.candidate_fuel_blend(sector)
        assert isinstance(result, pd.Series)

        result_array = result.values
        assert result_array == pytest.approx(1.0)

    @pytest.fixture(scope="class")
    def energy_demand_for_tests(
        self,
        pathways_series_index,
    ) -> pd.Series:
        data = pd.Series(
            index=pathways_series_index,
            data=np.array([2, 4, 6, 8, 10]),
            name="value",
        )
        return data

    @pytest.mark.skip(reason="mini_fuels_system is currently not active in test suite")
    def test_calc_energy_demand(self, mini_fuels_system, energy_demand_for_tests):
        """
        Test the calc_energy_demand function. Assert that:
        - the output is a pd.Series type
        - the output is assigned to the out_energy_demand attribute of the final fuel linkage
        - the output matches expected values based on hard-coded attributes in the mini_fuels_system class fixture
        """
        system = copy.deepcopy(mini_fuels_system)
        system.candidate_fuels["Fossil Natural Gas"].sector_candidate_fuel_blending[
            ("Industry", "Natural Gas")
        ].blend_override.data[
            pd.DatetimeIndex(
                [
                    "2031-01-01",
                    "2032-01-01",
                    "2033-01-01",
                    "2034-01-01",
                    "2035-01-01",
                ]
            )
        ] = np.array(
            [0.75, 0.5, 0.25, 1, 0]
        )

        sector = "Industry"
        final_fuel_name = "Natural Gas"
        candidate_fuel = system.candidate_fuels["Fossil Natural Gas"]
        ed = candidate_fuel.calc_energy_demand(sector, energy_demand_for_tests)

        assert isinstance(ed, pd.Series)
        assert candidate_fuel.final_fuels[final_fuel_name].out_energy_demand.data.values == pytest.approx(ed)
        assert ed.values == pytest.approx(np.array([2 * 0.75, 4 * 0.5, 6 * 0.25, 8.0, 0.0]))

    @pytest.mark.skip(reason="mini_fuels_system is currently not active in test suite")
    def test_calc_fuel_cost(self, mini_fuels_system, energy_demand_for_tests):
        """
        Test the calc_fuel_cost function. Assert that:
        - the output is assigned to the out_fuel_cost attribute of the final fuel linkage
        - the output matches expected values based on hard-coded attributes in the mini_fuels_system class fixture
        """
        system = copy.deepcopy(mini_fuels_system)
        candidate_fuel = system.candidate_fuels["Fossil Natural Gas"]
        candidate_fuel.fuel_price_per_mmbtu.data[
            pd.DatetimeIndex(
                [
                    "2031-01-01",
                    "2032-01-01",
                    "2033-01-01",
                    "2034-01-01",
                    "2035-01-01",
                ]
            )
        ] = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        candidate_fuel.calc_fuel_cost(energy_demand_for_tests)
        fuel_linkage = candidate_fuel.final_fuels["Natural Gas"]

        assert isinstance(fuel_linkage.out_fuel_cost, ts.NumericTimeseries)
        assert isinstance(fuel_linkage.out_fuel_cost.data, pd.Series)
        assert fuel_linkage.out_fuel_cost.data.values == pytest.approx(
            np.array([2 * 0.1, 4 * 0.2, 6 * 0.3, 8 * 0.4, 10 * 0.5])
        )

    @pytest.mark.skip(reason="mini_fuels_system is currently not active in test suite")
    def test_check_fuel_price(self, mini_fuels_system):
        """
        Test the check_fuel_price validator. Assert that:
        - Error is raised when fuel_is_commodity_bool is True and fuel_price_per_mmbtu is not specified
        """
        candidate_fuel = copy.deepcopy(mini_fuels_system).candidate_fuels["Fossil Natural Gas"]
        candidate_fuel.fuel_is_commodity_bool = 1

        # error is raised by model validator
        with pytest.raises(ValueError):
            candidate_fuel.fuel_price_per_mmbtu = None

    @pytest.fixture(scope="class")
    def timeseries_for_tests(
        self,
        pathways_series_index,
    ) -> ts.NumericTimeseries:
        series = ts.NumericTimeseries(
            name="random data for tests",
            data=pd.Series(
                index=pathways_series_index,
                data=np.ones(len(pathways_series_index)),
                name="value",
            ),
        )

        return series
