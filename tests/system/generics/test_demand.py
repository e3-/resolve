import copy

import pandas as pd
import pytest

import new_modeling_toolkit.core.temporal.timeseries as ts
from new_modeling_toolkit.system import Demand
from tests.system.component_test_template import ComponentTestTemplate


class TestDemand(ComponentTestTemplate):
    _COMPONENT_CLASS = Demand
    _COMPONENT_NAME = "GenericDemand1"
    _SYSTEM_COMPONENT_DICT_NAME = "demands"

    @pytest.fixture(scope="class")
    def unit_string(self):
        return "metric_ton"

    @pytest.fixture(scope="class")
    def modeled_year_tuple(self, test_temporal_settings):
        return (test_temporal_settings.first_modeled_year, test_temporal_settings.last_modeled_year)

    @pytest.fixture(scope="class")
    def weather_year_tuple(self, test_temporal_settings):
        return (test_temporal_settings.first_weather_year, test_temporal_settings.last_weather_year)

    def test_demand_unit(self, make_component_with_block_copy, unit_string):
        demand = make_component_with_block_copy()
        assert f"{demand.unit:e3}" == f"{unit_string}"

    @pytest.mark.parametrize(
        "scale_by_capacity, scale_by_energy, result_2025, result_2026",
        [
            (False, True, 2190000000, 2920000000),
            (True, False, 2600, 3000),
        ],
    )
    def test_forecast_demand(
        self,
        make_component_copy,
        weather_year_tuple,
        scale_by_capacity,
        scale_by_energy,
        result_2025,
        result_2026,
    ):
        demand = make_component_copy()
        demand.scale_by_energy = scale_by_energy
        demand.scale_by_capacity = scale_by_capacity
        demand.forecast_demand([2025, 2026], weather_year_tuple)
        assert demand.model_year_profiles[2025].data.sum() == pytest.approx(result_2025)
        assert demand.model_year_profiles[2026].data.sum() == pytest.approx((result_2026 * 0.9))

    @pytest.mark.parametrize(
        "scale_by_capacity, scale_by_energy,custom_scalars, result_2025, result_2026",
        [
            (False, True, [1.2, 1.5], 2190000000 * 1.2, 2920000000 * 1.5),
            (True, False, [1.2, 1.5], 2600, 3000),
        ],
    )
    def test_forecast_demand_w_custom_scalars(
        self,
        make_component_copy,
        weather_year_tuple,
        scale_by_capacity,
        scale_by_energy,
        custom_scalars,
        result_2025,
        result_2026,
    ):
        demand = make_component_copy()
        demand.scale_by_energy = scale_by_energy
        demand.scale_by_capacity = scale_by_capacity
        custom_scalars = pd.Series(
            index=pd.DatetimeIndex(
                [
                    "2025-01-01 00:00",
                    "2026-01-01 00:00",
                ],
                name="timestamp",
            ),
            data=custom_scalars,
        )
        demand.forecast_demand([2025, 2026], weather_year_tuple, custom_scalars=custom_scalars)
        assert pytest.approx(demand.model_year_profiles[2025].data.sum(), rel=1) == result_2025
        assert pytest.approx(demand.model_year_profiles[2026].data.sum()) == result_2026 * 0.9

    @pytest.mark.parametrize(
        "to_peak, to_energy, td_losses_adjustment, leap_year, profile_data",
        [
            (False, False, 1.1, False, [1 * 1.1, 2 * 1.1, 3 * 1.1, 2 * 1.1, 1 * 1.1, 1 * 1.1]),
            (False, 3000, 1, False, [600, 1200, 1800, 1200, 600, 600]),
            (3000, False, 1, False, [1200, 2400, 3600, 2400, 1200, 1200]),
            (3000, 3000, 1, False, [1199.80, 2399.93, 3600.07, 2399.93, 1199.79, 1199.79]),
            (3000, 3000, 1, True, [1199.80, 2399.93, 3600.07, 2399.93, 1199.79, 1199.79]),
        ],
    )
    def test_scale_demand(self, make_component_copy, to_peak, to_energy, td_losses_adjustment, leap_year, profile_data):
        demand = make_component_copy()
        profile = demand.profile
        new_profile = Demand.scale_demand(
            profile,
            to_peak=to_peak,
            to_energy=to_energy,
            td_losses_adjustment=td_losses_adjustment,
            leap_year=leap_year,
        )
        pd.testing.assert_series_equal(
            new_profile.data,
            pd.Series(index=profile.data.index, data=profile_data),
            check_names=False,
            check_dtype=False,
        )

    @pytest.mark.parametrize(
        "profile_data, sum_before",
        [
            ([2, 3, 5, 3, 4, 3], [10.0 * 365, 12.0 * 365, 20.0 * 365, 30.0 * 365]),
            ([1, 1, 6, 4, 4, 4], [9.6 * 365, 11.52 * 365, 19.2 * 365, 28.8 * 365]),
        ],
    )
    def test_update_demand_components(
        self, make_component_copy, weather_year_tuple, test_temporal_settings, profile_data, sum_before
    ):
        demand = make_component_copy()
        demand.annual_energy_forecast.data[:] = [10, 11, 12, 20, 30]
        demand_profile = ts.NumericTimeseries(
            name="profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-06-21 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=profile_data,
                name="value",
            ),
        )

        # setting up test data, `modeled_year_profiles` only exists after calling `forecast_demand` or as a direct input
        # demand.profile = copy.deepcopy(demand_profile)
        demand.profile = demand_profile
        demand.model_year_profiles[2025] = copy.deepcopy(demand_profile)
        demand.model_year_profiles[2030] = copy.deepcopy(demand_profile)
        demand.model_year_profiles[2030].data *= 1.2
        demand.model_year_profiles[2035] = copy.deepcopy(demand_profile)
        demand.model_year_profiles[2035].data *= 2
        demand.model_year_profiles[2045] = copy.deepcopy(demand_profile)
        demand.model_year_profiles[2045].data *= 3

        # test profile before scaling
        weighted_sum_before = demand._adjusted_hourly_demand(test_temporal_settings).groupby(level=0).sum()
        pd.testing.assert_series_equal(
            weighted_sum_before.squeeze(),
            pd.Series(
                index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2035-01-01", "2045-01-01"]), data=sum_before
            ),
            check_exact=False,
            check_names=False,
        )

        demand.update_demand_components(test_temporal_settings)

        weighted_sum_after = demand._adjusted_hourly_demand(test_temporal_settings).groupby(level=0).sum()

        pd.testing.assert_series_equal(
            weighted_sum_after.squeeze(),
            pd.Series(
                index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2035-01-01", "2045-01-01"]),
                data=[10.0, 12.0, 20.0, 30.0],
            ),
            check_exact=False,
            check_names=False,
        )

    def test_production(self, make_component_with_block_copy):
        demand = make_component_with_block_copy()
        block = demand.formulation_block

        if demand.processes is None:
            assert getattr(block, "production", None) is None
        else:
            assert block.production.is_indexed()

    def test_produced_product_to_zone(self, make_component_with_block_copy, first_index):
        demand = make_component_with_block_copy()
        block = demand.formulation_block

        if demand.processes is None:
            assert getattr(block, "produced_product_to_zone", None) is None
        else:
            for process in demand.processes.values():
                block.consumption[process.consumed_product.name, first_index] = 100
            assert all(
                block.produced_product_to_zone[output, first_index].expr()
                == sum(
                    100 * process.conversion_rate * process.output_capture_rate
                    for process in demand.processes.values()
                    if process.produced_product.name == output
                )
                for output in demand.produced_products.keys()
            )

    def test_produced_product_release(self, make_component_with_block_copy, first_index):
        demand = make_component_with_block_copy()
        block = demand.formulation_block

        if demand.processes is None:
            assert getattr(block, "produced_product_release", None) is None
        else:
            for process in demand.processes.values():
                block.production[process.produced_product.name, first_index] = 100
                block.produced_product_to_zone[process.produced_product.name, first_index] = 90
            assert all(
                block.produced_product_release[output, first_index].expr() == 10
                for output in demand.produced_products.keys()
            )

    def test_consumption(self, make_component_with_block_copy):
        demand = make_component_with_block_copy()
        block = demand.formulation_block
        assert block.consumption.is_indexed()

    def test_consumption_must_equal_demand(self, make_component_with_block_copy, first_index):
        demand = make_component_with_block_copy()
        block = demand.formulation_block
        input_product = list(demand.consumed_products.keys())[0]
        modeled_year, _, timestamp = first_index
        actual_demand = demand.get_demand(modeled_year.year, timestamp)

        block.consumption[input_product, first_index].fix(200_000)
        assert not block.consumption_must_equal_demand[input_product, first_index].expr()
        assert block.consumption_must_equal_demand[input_product, first_index].body() == (200_000 - actual_demand)

        block.consumption[input_product, first_index].fix(actual_demand)
        assert block.consumption_must_equal_demand[input_product, first_index].expr()

    def test_results_reporting(self, make_component_with_block_copy, unit_string):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        resource._construct_output_expressions(construct_costs=True)

        assert block.consumption.doc == f"Hourly Consumption ({unit_string} per hour)"
        assert block.demand.doc == f"Hourly Demand ({unit_string} per hour)"
        assert block.production.doc == f"Hourly Production (Product Units per hour)"
        assert block.produced_product_to_zone.doc == "Hourly Produced Product To Zone (Product Units per hour)"
        assert block.produced_product_release.doc == "Hourly Produced Product Release (Product Units per hour)"

        assert block.rep_annual_energy.doc == f"Representative Annual Energy ({unit_string})"
        assert block.annual_energy.doc == f"Average Annual Energy ({unit_string})"
        assert block.rep_annual_peak.doc == f"Representative Annual Peak ({unit_string})"
        assert block.annual_peak.doc == f"Average Annual Peak ({unit_string})"

        assert block.annual_consumed_commodity_product_cost.doc == f"Annual Total Consumed Commodity Product Cost ($)"
        assert block.annual_consumption.doc == f"Annual Consumption ({unit_string})"
        assert block.annual_demand.doc == f"Annual Demand ({unit_string})"
        assert block.annual_production.doc == f"Annual Production (Product Units)"
        assert block.annual_produced_product_to_zone.doc == f"Annual Produced Product To Zone (Product Units)"
        assert block.annual_produced_product_release.doc == f"Annual Produced Product Release (Product Units)"

        assert resource.model_fields["scale_by_capacity"].title == "Scale by Median Peak"
        assert resource.model_fields["scale_by_energy"].title == "Scale by Mean Annual Energy"


class TestDemandWithCommodityProduct(ComponentTestTemplate):
    _COMPONENT_CLASS = Demand
    _COMPONENT_NAME = "GenericDemand2"
    _SYSTEM_COMPONENT_DICT_NAME = "demands"

    def _update_consumption(self, block, modeled_year, value):
        for product in block.INPUTS:
            block.consumption[product, modeled_year, :, :] = value

    def test_consumed_commodity_product_cost(self, make_component_with_block_copy, first_index):
        demand = make_component_with_block_copy()
        block = demand.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        self._update_consumption(block, modeled_year, 100)

        assert block.consumed_commodity_product_cost[first_index].expr() == 100.0 * 3.0

    def test_annual_consumed_commodity_product_cost(self, make_component_with_block_copy, first_index):
        demand = make_component_with_block_copy()
        block = demand.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        self._update_consumption(block, modeled_year, 100)

        assert block.annual_consumed_commodity_product_cost[modeled_year].expr() == 100.0 * 3.0 * 365.0 * 3.0
