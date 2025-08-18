import copy

import numpy as np
import pandas as pd
import pytest

from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.system import Pollutant
from tests.system.component_test_template import ComponentTestTemplate
from tests.system.generics.test_product import TestProduct


class TestPollutant(TestProduct):
    _COMPONENT_CLASS = Pollutant
    _COMPONENT_NAME = "Pollutant1"
    _SYSTEM_COMPONENT_DICT_NAME = "pollutants"

    def test_unit(self, make_component_copy):
        product: Pollutant = make_component_copy()
        assert f"{product.unit:e3}" == "metric_ton"


@pytest.mark.skip("Skip until fuels opt tests are written")
class TestPollutantForPathways(ComponentTestTemplate):
    _TEST_SYSTEM_NAME: str = "TEST_fuels"
    _START_YEAR: int = 2031
    _END_YEAR: int = 2035

    def create_emission_factor_ts(
        self, pathways_series_index, emissions_type: str, multiplier: float
    ) -> ts.NumericTimeseries:
        """
        Helper function to create emission_factor attributes on CandidateFuelToPollutant linkage for testing.
        """
        series = ts.NumericTimeseries(
            name=f"{emissions_type}_emission_factor",
            data=pd.Series(
                index=pathways_series_index,
                data=np.ones(len(pathways_series_index)) * multiplier,
                name="value",
            ),
        )
        return series

    @pytest.fixture(scope="class")
    def candidate_fuel_for_tests(self, mini_fuels_system):
        candidate_fuel = copy.deepcopy(mini_fuels_system.candidate_fuels["Fossil Natural Gas"])
        return candidate_fuel

    @pytest.fixture(scope="class")
    def pollutant_for_tests(self, mini_fuels_system):
        pollutant = copy.deepcopy(mini_fuels_system.pollutants["CH4"])
        pollutant.GWP = 2
        return pollutant

    @pytest.fixture(scope="class")
    def linkage_for_tests(self, candidate_fuel_for_tests, pathways_series_index):
        linkage = copy.deepcopy(candidate_fuel_for_tests.pollutants["CH4"])
        linkage.net_emission_factor = self.create_emission_factor_ts(pathways_series_index, "net", 0.01)
        linkage.gross_emission_factor = self.create_emission_factor_ts(pathways_series_index, "gross", 0.02)
        linkage.upstream_emission_factor = self.create_emission_factor_ts(pathways_series_index, "upstream", 0.0)
        return linkage

    @pytest.fixture(scope="class")
    def energy_demand_for_tests(
        self,
        pathways_series_index,
    ) -> pd.Series:
        data = pd.Series(
            index=pathways_series_index,
            data=np.ones(len(pathways_series_index)),
            name="value",
        )
        return data

    def test_calc_emissions(
        self,
        candidate_fuel_for_tests,
        pollutant_for_tests,
        linkage_for_tests,
        energy_demand_for_tests,
    ):
        """
        Test the _calc_emissions function of Pollutant class. Dependent components and their attributes are defined in fixtures above. Assert that:
        - the function output is a tuple of pd.Series type
        - net, gross, and upstream emissions values are as expected
        - net, gross, and upstream emissions are related to their respective CO2 equivalent emissions based on pollutant.GWP attribute
        """
        net_results = pollutant_for_tests._calc_emissions("net", linkage_for_tests, energy_demand_for_tests)
        gross_results = pollutant_for_tests._calc_emissions("gross", linkage_for_tests, energy_demand_for_tests)
        upstream_results = pollutant_for_tests._calc_emissions("upstream", linkage_for_tests, energy_demand_for_tests)

        assert all([isinstance(results, tuple) for results in [net_results, gross_results, upstream_results]])
        assert all([isinstance(results[0], pd.Series) for results in [net_results, gross_results, upstream_results]])
        assert net_results[0].values == pytest.approx(0.01)
        assert gross_results[0].values == pytest.approx(0.02)
        assert upstream_results[0].values == pytest.approx(0.0)
        assert all(
            [
                results[0].values * pollutant_for_tests.GWP == pytest.approx(results[1].values)
                for results in [net_results, gross_results, upstream_results]
            ]
        )
