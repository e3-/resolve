import pandas as pd
import pytest

import new_modeling_toolkit.core.temporal.timeseries as ts
from new_modeling_toolkit.core.linkage import AnnualEnergyStandardContribution
from new_modeling_toolkit.core.linkage import EmissionsContribution
from new_modeling_toolkit.core.linkage import ReliabilityContribution
from new_modeling_toolkit.core.linkage import ResourceToReserve
from new_modeling_toolkit.core.linkage import ResourceToZone
from new_modeling_toolkit.system.electric.reserve import Reserve
from new_modeling_toolkit.system.electric.resources import GenericResource
from new_modeling_toolkit.system.electric.resources.generic import GenericResourceGroup
from tests.system import test_asset


class TestGenericResource(test_asset.TestAsset):
    _COMPONENT_CLASS = GenericResource
    _COMPONENT_NAME = "GenericResource1"
    _SYSTEM_COMPONENT_DICT_NAME = "generic_resources"

    @pytest.fixture(scope="function")
    def block_comp_for_budget_tests(self, make_component_with_block_copy, first_index):
        block = make_component_with_block_copy().formulation_block
        model = block.model()
        year = model.MODELED_YEARS.first()
        second_index = year, model.DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(first_index[1:])
        third_index = year, model.DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(first_index[1:], 2)
        for dispatch_window, timestamp in model.DISPATCH_WINDOWS_AND_TIMESTAMPS:
            block.power_output[year, dispatch_window, timestamp].fix(0)
        block.power_output[second_index].fix(1)
        block.power_output[third_index].fix(1.5)
        return block

    def test_operational_attributes(self, make_component_copy):
        assert make_component_copy().operational_attributes == [
            "stochastic_outage_rate",
            "mean_time_to_repair",
            "random_seed",
            "variable_cost_power_output",
            "power_output_min",
            "power_output_min__type",
            "power_output_max",
            "power_output_max__type",
            "outage_profile",
            "outage_profile__type",
            "energy_budget_daily",
            "energy_budget_monthly",
            "energy_budget_annual",
            "ramp_rate_1_hour",
            "ramp_rate_2_hour",
            "ramp_rate_3_hour",
            "ramp_rate_4_hour",
            "allow_inter_period_sharing",
        ]

    def test_operational_linkages(self, make_component_copy):
        assert make_component_copy().operational_linkages == [
            "emissions_policies",
            "annual_energy_policies",
            "hourly_energy_policies",
            "zones",
            "reserves",
        ]

    def test_variable_bounds(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        for index in block.power_output:
            assert block.power_output[index].lb == 0
            assert block.power_output[index].ub is None

        for index in block.provide_reserve:
            assert block.provide_reserve[index].lb == 0
            assert block.provide_reserve[index].ub is None

    def test_power_output_max(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.operational_capacity[pd.Timestamp("2025-01-01")] = 200
        block.operational_capacity[pd.Timestamp("2035-01-01")] = 150

        assert (
            block.power_output_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00")
            ].expr()
            == 200 * 1.0
        )
        assert (
            block.power_output_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 01:00")
            ].expr()
            == 200 * 0.8
        )
        assert (
            block.power_output_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 02:00")
            ].expr()
            == 200 * 0.5
        )
        assert (
            block.power_output_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 12:00")
            ].expr()
            == 200 * 0.5
        )
        assert (
            block.power_output_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00")
            ].expr()
            == 200 * 0.3
        )
        assert (
            block.power_output_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00")
            ].expr()
            == 200 * 0.7
        )

        assert (
            block.power_output_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00")
            ].expr()
            == 150 * 1.0
        )
        assert (
            block.power_output_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 01:00")
            ].expr()
            == 150 * 0.8
        )
        assert (
            block.power_output_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 02:00")
            ].expr()
            == 150 * 0.5
        )
        assert (
            block.power_output_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 12:00")
            ].expr()
            == 150 * 0.5
        )
        assert (
            block.power_output_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00")
            ].expr()
            == 150 * 0.3
        )
        assert (
            block.power_output_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00")
            ].expr()
            == 150 * 0.7
        )

    def test_power_output_min(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.operational_capacity[pd.Timestamp("2025-01-01")] = 200
        block.operational_capacity[pd.Timestamp("2035-01-01")] = 150

        assert (
            block.power_output_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00")
            ].expr()
            == 200 * 0.10
        )
        assert (
            block.power_output_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 01:00")
            ].expr()
            == 200 * 0.10
        )
        assert (
            block.power_output_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 02:00")
            ].expr()
            == 200 * 0.10
        )
        assert (
            block.power_output_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 12:00")
            ].expr()
            == 200 * 0.10
        )
        assert (
            block.power_output_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00")
            ].expr()
            == 200 * 0.10
        )
        assert (
            block.power_output_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00")
            ].expr()
            == 200 * 0.10
        )

        assert (
            block.power_output_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00")
            ].expr()
            == 150 * 0.10
        )
        assert (
            block.power_output_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 01:00")
            ].expr()
            == 150 * 0.10
        )
        assert (
            block.power_output_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 02:00")
            ].expr()
            == 150 * 0.10
        )
        assert (
            block.power_output_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 12:00")
            ].expr()
            == 150 * 0.10
        )
        assert (
            block.power_output_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00")
            ].expr()
            == 150 * 0.10
        )
        assert (
            block.power_output_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00")
            ].expr()
            == 150 * 0.10
        )

    def test_power_output_max_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        block.operational_capacity[modeled_year] = 200

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(160.0)
        assert block.power_output_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == -40  # 160 - 200
        assert block.power_output_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_output_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(600.0)
        assert block.power_output_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == 400  # 600 - 200
        assert block.power_output_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert not block.power_output_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

    def test_power_output_min_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        block.operational_capacity[pd.Timestamp("2025-01-01")] = 200

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(160.0)
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0.10 * 200 - 160
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(10.0)
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0.10 * 200 - 10
        assert not block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0.10 * 200 - 0
        assert not block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()


    def test_total_up_reserves_max_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        block.operational_capacity[modeled_year] = 200

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(160.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert (
            block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == -10
        )  # 160 + 30 - 200
        assert block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(600.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert (
            block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == 430
        )  # 600 + 30 - 200
        assert block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert not block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(0.0)
        assert block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == -200
        assert block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

    def test_total_down_reserves_max_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        block.operational_capacity[modeled_year] = 200

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(120.0)
        block.provide_reserve["TestRegulationDown", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert (
            block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body()
            == -90  # 30 - 120
        )
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(120.0)
        block.provide_reserve["TestRegulationDown", modeled_year, dispatch_window_id, timestamp].fix(150.0)
        assert (
            block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == 30
        )  # 150 - 120
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert not block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        block.provide_reserve["TestRegulationDown", modeled_year, dispatch_window_id, timestamp].fix(0.0)
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

    def test_annual_energy_budget_constraint(self, block_comp_for_budget_tests, first_index):
        block = block_comp_for_budget_tests
        model = block.model()
        year = model.MODELED_YEARS.first()
        constraint_index_1 = year, model.WEATHER_YEARS.first()

        block.operational_capacity[year] = 100

        # fractional budget is equal to 750 MWh for 100 MW of capacity (plus one for tolerance)
        # test that it passes if annual mwh is less than budget
        assert block.annual_energy_budget_constraint[constraint_index_1].body() == pytest.approx(
            (2.5 * 0.6 * 365) - 751
        )

        assert block.annual_energy_budget_constraint[constraint_index_1].upper() == pytest.approx(0)

        assert block.annual_energy_budget_constraint[constraint_index_1].expr()

        # test that it fails if annual mwh is less than budget
        block.power_output[year, model.DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(first_index[1:], 2)].fix(5)
        assert block.annual_energy_budget_constraint[constraint_index_1].body() == pytest.approx((6 * 0.6 * 365) - 751)

        assert block.annual_energy_budget_constraint[constraint_index_1].upper() == pytest.approx(0)

        assert not block.annual_energy_budget_constraint[constraint_index_1].expr()

    # TODO: Update this test after monthly budgets are implemented
    @pytest.mark.skip("Skip this test until monthly budgets are implemented")
    def test_monthly_energy_budget_constraint(self, block_comp_for_budget_tests, first_index):
        block = block_comp_for_budget_tests
        model = block.model()
        year = model.MODELED_YEARS.first()
        constraint_index_1 = year, model.MONTHS.first()

        block.operational_capacity[year] = 100

        # fractional budget is equal to 500 MWh for 100 MW of capacity (plus one for tolerance)
        assert block.monthly_energy_budget_constraint[constraint_index_1].body() == pytest.approx(2.5 - 501)

        # test that if passes if monthly mwh less than budget
        assert block.monthly_energy_budget_constraint[constraint_index_1].upper() == pytest.approx(0)  # Tolerance

        assert block.monthly_energy_budget_constraint[constraint_index_1].expr()

        # test that it fails if monthly mwh exceeds budget
        block.power_output[year, model.DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(first_index[1:], 2)].fix(600)
        assert block.monthly_energy_budget_constraint[constraint_index_1].body() == pytest.approx(601 - 501)

        assert block.monthly_energy_budget_constraint[constraint_index_1].upper() == pytest.approx(0)

        assert not block.monthly_energy_budget_constraint[constraint_index_1].expr()

    def test_daily_energy_budget_constraint(self, block_comp_for_budget_tests, first_index):
        block = block_comp_for_budget_tests
        model = block.model()
        year = model.MODELED_YEARS.first()
        constraint_index_1 = year, model.DAYS.first()

        block.operational_capacity[year] = 100

        # fractional budget is equal to 250 MWh in a day for 100 MW
        # test that if passes if daily mwh less than budget
        assert block.daily_energy_budget_constraint[constraint_index_1].body() == pytest.approx(2.5 - 251)

        assert block.daily_energy_budget_constraint[constraint_index_1].upper() == pytest.approx(0)

        assert block.daily_energy_budget_constraint[constraint_index_1].expr()

        # test that if fails if daily mwh less than budget
        block.power_output[year, model.DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(first_index[1:], 2)].fix(300)
        assert block.daily_energy_budget_constraint[constraint_index_1].body() == pytest.approx(301 - 251)

        assert block.daily_energy_budget_constraint[constraint_index_1].upper() == pytest.approx(0)

        assert not block.daily_energy_budget_constraint[constraint_index_1].expr()

    def test_power_output_variable_cost(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        assert resource.variable_cost_power_output.data.at[timestamp] == 5

        block.power_output[first_index].fix(50)
        assert block.power_output_variable_cost[first_index].expr() == 250

    def test_production_tax_credit(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        assert resource.production_tax_credit == 2

        block.power_output[first_index].fix(100)
        assert block.production_tax_credit[first_index].expr() == 200

    def test_annual_total_operational_cost(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.power_output.fix(10)

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
        ]:
            assert block.annual_total_operational_cost[year].expr() == (
                # Rep period weight * # of days per year * (power output variable cost - production tax credit)
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (2 + 2 + 2))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (2 + 2 + 2))
            )

        for year in [
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            assert block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (0 + 0 + 0))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (0 + 0 + 0))
            )

        assert block.annual_total_operational_cost

    @pytest.mark.parametrize(
        "ramp_rate_hour, power_output, operational_capacity, expr, upper, body",
        [
            (1, 1000, 100, False, 0.0, 800 - (100 * 0.2)),
            (1, 100, 100, True, 0.0, -100 - (100 * 0.2)),
            (2, 1000, 100, False, 0.0, 800 - (100 * 0.4)),
            (2, 100, 100, True, 0.0, -100 - (100 * 0.4)),
        ],
    )
    def test_ramp_rate_intra_period_up_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        ramp_rate_hour,
        power_output,
        operational_capacity,
        expr,
        upper,
        body,
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        ramp_index = (modeled_year, dispatch_window, timestamp + pd.Timedelta(hours=ramp_rate_hour))
        resource_block.power_output.fix(200)
        resource_block.power_output[ramp_index].fix(power_output)
        resource_block.operational_capacity[modeled_year] = operational_capacity

        assert resource_block.ramp_rate_intra_period_up_constraint[first_index, ramp_rate_hour].expr() == expr
        assert resource_block.ramp_rate_intra_period_up_constraint[first_index, ramp_rate_hour].body() == body
        assert resource_block.ramp_rate_intra_period_up_constraint[first_index, ramp_rate_hour].upper() == upper

    @pytest.mark.parametrize(
        "ramp_rate_hour, power_output, operational_capacity, expr, upper, body",
        [
            (1, 1000, 100, True, 0.0, -800 - (100 * 0.2)),
            (1, 100, 100, False, 0.0, 100 - (100 * 0.2)),
            (2, 1000, 100, True, 0.0, -800 - (100 * 0.4)),
            (2, 100, 100, False, 0.0, 100 - (100 * 0.4)),
        ],
    )
    def test_ramp_rate_intra_period_down_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        ramp_rate_hour,
        power_output,
        operational_capacity,
        expr,
        upper,
        body,
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        ramp_index = (modeled_year, dispatch_window, timestamp + pd.Timedelta(hours=ramp_rate_hour))
        resource_block.power_output.fix(200)
        resource_block.power_output[ramp_index].fix(power_output)
        resource_block.operational_capacity[modeled_year] = operational_capacity

        assert resource_block.ramp_rate_intra_period_down_constraint[first_index, ramp_rate_hour].expr() == expr
        assert resource_block.ramp_rate_intra_period_down_constraint[first_index, ramp_rate_hour].body() == body
        assert resource_block.ramp_rate_intra_period_down_constraint[first_index, ramp_rate_hour].upper() == upper

    @pytest.mark.parametrize(
        "ramp_rate_hour, ramp_rate_offset, power_output, operational_capacity, expr, upper, body",
        [
            (1, 0, 1000, 100, False, 0.0, 800 - (100 * 0.2)),
            (1, 0, 100, 100, True, 0.0, -100 - (100 * 0.2)),
            (2, 0, 1000, 100, False, 0.0, 800 - (100 * 0.4)),
            (2, 0, 100, 100, True, 0.0, -100 - (100 * 0.4)),
            (2, 1, 1000, 100, False, 0.0, 800 - (100 * 0.4)),
            (2, 1, 100, 100, True, 0.0, -100 - (100 * 0.4)),
            (4, 2, 1000, 100, False, 0.0, 800 - (100 * 0.8)),
            (4, 2, 100, 100, True, 0.0, -100 - (100 * 0.8)),
        ],
    )
    def test_ramp_rate_inter_period_up_constraint(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index,
        last_index,
        ramp_rate_hour,
        ramp_rate_offset,
        power_output,
        operational_capacity,
        expr,
        upper,
        body,
    ):
        resource = make_component_with_block_copy_inter_period_sharing()
        resource_block = resource.formulation_block
        modeled_year = pd.Timestamp("2025-01-01")
        chrono_period = pd.Timestamp("2012-01-03")
        dispatch_window = resource_block.model().chrono_periods_map[chrono_period]
        next_chrono_period = resource_block.model().CHRONO_PERIODS.nextw(chrono_period)
        next_dispatch_window = resource_block.model().chrono_periods_map[next_chrono_period]

        last_timestamp_chrono_period = resource_block.model().last_timepoint_in_dispatch_window[dispatch_window]

        first_timestamp_next_chrono_period = resource_block.model().first_timepoint_in_dispatch_window[
            next_dispatch_window
        ]

        chrono_index = (modeled_year, chrono_period)

        chrono_period_1_index = (
            modeled_year,
            dispatch_window,
            last_timestamp_chrono_period - pd.Timedelta(hours=ramp_rate_offset),
        )
        ramp_index = (
            modeled_year,
            next_dispatch_window,
            first_timestamp_next_chrono_period + pd.Timedelta(hours=ramp_rate_hour - ramp_rate_offset - 1),
        )
        # assert the first index of intra contraint was skipped because it would cross the dispatch window boundary
        with pytest.raises(KeyError):
            resource_block.ramp_rate_intra_period_up_constraint[chrono_period_1_index]
        resource_block = resource.formulation_block
        resource_block.power_output.fix(200)
        resource_block.power_output[ramp_index].fix(power_output)
        resource_block.operational_capacity[modeled_year] = operational_capacity

        assert (
            resource_block.ramp_rate_inter_period_up_constraint[chrono_index, ramp_rate_hour, ramp_rate_offset].expr()
            == expr
        )
        assert (
            resource_block.ramp_rate_inter_period_up_constraint[chrono_index, ramp_rate_hour, ramp_rate_offset].body()
            == body
        )
        assert (
            resource_block.ramp_rate_inter_period_up_constraint[chrono_index, ramp_rate_hour, ramp_rate_offset].upper()
            == upper
        )

    @pytest.mark.parametrize(
        "ramp_rate_hour, ramp_rate_offset, power_output, operational_capacity, expr, upper, body",
        [
            (1, 0, 1000, 100, True, 0.0, -800 - (100 * 0.2)),
            (1, 0, 100, 100, False, 0.0, 100 - (100 * 0.2)),
            (2, 0, 1000, 100, True, 0.0, -800 - (100 * 0.4)),
            (2, 0, 100, 100, False, 0.0, 100 - (100 * 0.4)),
            (2, 1, 1000, 100, True, 0.0, -800 - (100 * 0.4)),
            (2, 1, 100, 100, False, 0.0, 100 - (100 * 0.4)),
            (4, 2, 1000, 100, True, 0.0, -800 - (100 * 0.8)),
            (4, 2, 100, 100, False, 0.0, 100 - (100 * 0.8)),
        ],
    )
    def test_ramp_rate_inter_period_down_constraint(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index,
        last_index,
        ramp_rate_hour,
        ramp_rate_offset,
        power_output,
        operational_capacity,
        expr,
        upper,
        body,
    ):
        resource = make_component_with_block_copy_inter_period_sharing()
        resource_block = resource.formulation_block
        modeled_year = pd.Timestamp("2025-01-01")
        chrono_period = pd.Timestamp("2012-01-03")
        dispatch_window = resource_block.model().chrono_periods_map[chrono_period]
        next_chrono_period = resource_block.model().CHRONO_PERIODS.nextw(chrono_period)
        next_dispatch_window = resource_block.model().chrono_periods_map[next_chrono_period]

        last_timestamp_chrono_period = resource_block.model().last_timepoint_in_dispatch_window[dispatch_window]

        first_timestamp_next_chrono_period = resource_block.model().first_timepoint_in_dispatch_window[
            next_dispatch_window
        ]

        chrono_index = (modeled_year, chrono_period)

        chrono_period_1_index = (
            modeled_year,
            dispatch_window,
            last_timestamp_chrono_period - pd.Timedelta(ramp_rate_offset),
        )
        ramp_index = (
            modeled_year,
            next_dispatch_window,
            first_timestamp_next_chrono_period + pd.Timedelta(hours=ramp_rate_hour - ramp_rate_offset - 1),
        )
        # assert the first index of intra contraint was skipped because it would cross the dispatch window boundary
        with pytest.raises(KeyError):
            resource_block.ramp_rate_inter_period_down_constraint[chrono_period_1_index]
        resource_block.power_output.fix(200)
        resource_block.power_output[ramp_index].fix(power_output)
        resource_block.operational_capacity[modeled_year] = operational_capacity

        assert (
            resource_block.ramp_rate_inter_period_down_constraint[chrono_index, ramp_rate_hour, ramp_rate_offset].expr()
            == expr
        )
        assert (
            resource_block.ramp_rate_inter_period_down_constraint[chrono_index, ramp_rate_hour, ramp_rate_offset].body()
            == body
        )
        assert (
            resource_block.ramp_rate_inter_period_down_constraint[
                chrono_index, ramp_rate_hour, ramp_rate_offset
            ].upper()
            == upper
        )

    def test_check_operational_linkages_are_equal(
        self, test_generic_resource, test_reserve_up, test_zone_1, test_zone_2
    ):
        generic_resource = test_generic_resource.copy()
        reserve = test_reserve_up.copy()
        zone_1 = test_zone_1.copy()
        zone_2 = test_zone_2.copy()

        # Test 3: A copy of the resource with the same linkages should be equal
        # TODO (skramer): update after policies are merged
        generic_resource.emissions_policies = {}
        generic_resource.annual_energy_policies = {}
        generic_resource.hourly_energy_policies = {}
        generic_resource.prm_policies = {}
        generic_resource.reserves = {
            reserve.name: ResourceToReserve(
                name=(generic_resource.name, reserve.name),
                instance_from=generic_resource,
                instance_to=reserve,
            )
        }
        generic_resource.zones = {
            zone_1.name: ResourceToZone(
                name=(generic_resource.name, zone_1.name),
                instance_from=generic_resource,
                instance_to=zone_1,
            )
        }

        generic_resource_copy = generic_resource.copy(include_linkages=True, update=dict(name="resource_copy"))
        assert generic_resource.check_operational_linkages_are_equal(generic_resource_copy)
        assert generic_resource_copy.check_operational_linkages_are_equal(generic_resource)

        # Test 3a: A copy of the resource with the different linkages should not be equal
        # TODO (skramer): update after policies are merged
        generic_resource_copy = generic_resource.copy(include_linkages=True, update=dict(name="resource_copy"))
        generic_resource_copy.reserves = {
            reserve.name: ResourceToReserve(
                name=(generic_resource_copy.name, "new_reserve"),
                instance_from=generic_resource_copy,
                instance_to=ResourceToReserve(
                    name=(generic_resource_copy.name, "new_reserve"),
                    instance_from=generic_resource_copy,
                    instance_to=Reserve(
                        name="new_reserve",
                        requirement=ts.NumericTimeseries(
                            name="requirement", data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00"]), data=[0.0])
                        ),
                        direction="up",
                    ),
                ),
            )
        }
        assert not generic_resource.check_operational_linkages_are_equal(generic_resource_copy)
        assert not generic_resource_copy.check_operational_linkages_are_equal(generic_resource)

        # Test 3b: A copy of the resource with the different linkages should not be equal
        generic_resource_copy = generic_resource.copy(include_linkages=True, update=dict(name="resource_copy"))
        generic_resource_copy.zones = {
            zone_2.name: ResourceToZone(
                name=(generic_resource_copy.name, zone_2.name),
                instance_from=generic_resource_copy,
                instance_to=zone_2,
            ),
        }
        assert not generic_resource.check_operational_linkages_are_equal(generic_resource_copy)
        assert not generic_resource_copy.check_operational_linkages_are_equal(generic_resource)

    def test_check_if_operationally_equal_copy(self, make_component_copy):
        generic_resource = make_component_copy()

        # Test 1: An exact copy of the resource should be equal to the original (no linkages)
        generic_resource_copy = generic_resource.copy(include_linkages=True, update={"name": "generic_resource_copy"})
        assert generic_resource.check_if_operationally_equal(generic_resource_copy)
        assert generic_resource_copy.check_if_operationally_equal(generic_resource)

    @pytest.mark.parametrize(
        "attr_name, new_value",
        [
            ("can_build_new", False),
            ("can_retire", False),
            ("financial_lifetime", 1000),
            ("physical_lifetime", 1000),
            # ("potential", 1000),
            # ("annualized_capital_cost", 1000),
            # ("annualized_fixed_om_cost", 1000),
        ],
    )
    def test_check_if_operationally_equal_true(self, make_component_copy, attr_name, new_value):
        generic_resource = make_component_copy()

        # Test 2: A modified copy of the resource that only has non-operational attributes edited should still be equal
        #  to the original (no linkages)
        curr_test_copy = generic_resource.copy(include_linkages=True, update={attr_name: new_value})
        assert generic_resource.check_if_operationally_equal(curr_test_copy)
        assert curr_test_copy.check_if_operationally_equal(generic_resource)

    @pytest.mark.parametrize(
        "attr_name, new_value",
        [
            ("stochastic_outage_rate", 0.1),
            ("mean_time_to_repair", 50),
            ("random_seed", 8),
            (
                "power_output_max",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "power_output_min",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "outage_profile",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "energy_budget_daily",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-02 00:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "energy_budget_monthly",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-02-01 00:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "energy_budget_annual",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2021-01-01 00:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "variable_cost_power_output",
                ts.NumericTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
        ],
    )
    def test_check_if_operationally_equal_false(self, make_component_copy, attr_name, new_value):
        # Test 3: An modified copy of the resource should not be equal to the original
        generic_resource = make_component_copy()
        curr_test_copy = generic_resource.copy(include_linkages=True, update={attr_name: new_value})
        assert not generic_resource.check_if_operationally_equal(curr_test_copy)
        assert not curr_test_copy.check_if_operationally_equal(generic_resource)

    def test_check_if_operationally_equal_linkages(
        self, make_component_copy, test_zone_1, test_zone_2, test_ghg_policy, test_rps, test_prm_policy
    ):
        generic_resource = make_component_copy().copy(include_linkages=False)

        # Test 4a: A copy of the resource with the same linkages should be equal
        zone_1 = test_zone_1.copy()
        generic_resource.emissions_policies = {
            test_ghg_policy.name: EmissionsContribution(
                name=(generic_resource.name, test_ghg_policy.name),
                instance_from=generic_resource,
                instance_to=test_ghg_policy,
            )
        }
        generic_resource.annual_energy_policies = {
            test_rps.name: AnnualEnergyStandardContribution(
                name=(generic_resource.name, test_rps.name),
                instance_from=generic_resource,
                instance_to=test_rps,
            )
        }
        generic_resource.prm_policies = {
            test_prm_policy.name: ReliabilityContribution(
                name=(generic_resource.name, test_prm_policy.name),
                instance_from=generic_resource,
                instance_to=test_prm_policy,
            )
        }
        generic_resource.zones = {
            zone_1.name: ResourceToZone(
                name=(generic_resource.name, zone_1.name),
                instance_from=generic_resource,
                instance_to=zone_1,
            )
        }
        test_generic_resource_copy = generic_resource.copy(
            include_linkages=True, update={"name": "generic_resource_copy"}
        )
        assert generic_resource.check_if_operationally_equal(test_generic_resource_copy)
        assert test_generic_resource_copy.check_if_operationally_equal(generic_resource)

        # Test 4b: A copy of the resource with the different linkages should not be equal
        test_generic_resource_copy = generic_resource.copy(update={"name": "generic_resource_copy"})
        zone_2 = test_zone_2.copy()
        test_generic_resource_copy.zones = {
            zone_2.name: ResourceToZone(
                name=(test_generic_resource_copy.name, zone_2.name),
                instance_from=test_generic_resource_copy,
                instance_to=zone_2,
            )
        }
        assert not generic_resource.check_if_operationally_equal(test_generic_resource_copy)
        assert not test_generic_resource_copy.check_if_operationally_equal(generic_resource)

        # Test 4c: A copy of the resource with only a non-operational linkage changed should still be equal
        test_generic_resource_copy = generic_resource.copy(
            include_linkages=True, update={"name": "generic_resource_copy"}
        )
        test_generic_resource_copy.prm_policies = {}
        assert test_generic_resource_copy.prm_policies is not generic_resource.prm_policies
        assert generic_resource.check_if_operationally_equal(test_generic_resource_copy)
        assert test_generic_resource_copy.check_if_operationally_equal(generic_resource)

    def test_results_reporting(self, make_component_with_block_copy):
        super().test_results_reporting(make_component_with_block_copy)

        resource = make_component_with_block_copy()
        block = resource.formulation_block

        assert block.power_output.doc == "Power Output (MW)"
        assert block.net_power_output.doc == "Net Power Output (MW)"
        assert block.total_up_reserves_by_timepoint.doc == "Total Up Reserves (MW)"
        assert block.total_down_reserves_by_timepoint.doc == "Total Down Reserves (MW)"
        assert block.total_provide_reserve.doc == "Total Provide Reserve (MW)"
        assert block.power_output_annual.doc == "Annual Power Output (MWh)"
        assert block.net_power_output_annual.doc == "Net Annual Power Output (MWh)"
        assert block.power_output_variable_cost.doc == "Power Output Variable Cost ($)"
        assert block.production_tax_credit.doc == "Production Tax Credit ($)"
        assert block.annual_power_output_variable_cost.doc == "Annual Power Output Variable Cost ($)"
        assert block.annual_production_tax_credit.doc == "Annual Production Tax Credit ($)"


class TestGenericResourceGroup(test_asset.TestAssetGroup, TestGenericResource):
    _COMPONENT_CLASS = GenericResourceGroup
    _COMPONENT_NAME = "generic_resource_group_0"
    _SYSTEM_COMPONENT_DICT_NAME = "generic_resource_groups"

    def test_results_reporting(self, make_component_with_block_copy):
        super().test_results_reporting(make_component_with_block_copy)
        resource_group = make_component_with_block_copy()
        block = resource_group.formulation_block

        assert block.power_output.doc == "Power Output (MW)"
        assert block.net_power_output.doc == "Net Power Output (MW)"
        assert block.power_output_max.doc == "Power Output Upper Bound (MW)"
        assert block.power_output_min.doc == "Power Output Lower Bound (MW)"
        assert block.total_up_reserves_by_timepoint.doc == "Total Up Reserves (MW)"
        assert block.total_down_reserves_by_timepoint.doc == "Total Down Reserves (MW)"
        assert block.total_provide_reserve.doc == "Total Provide Reserve (MW)"
        assert block.power_output_annual.doc == "Annual Power Output (MWh)"
        assert block.net_power_output_annual.doc == "Net Annual Power Output (MWh)"
        assert block.power_output_variable_cost.doc == "Power Output Variable Cost ($)"
        assert block.production_tax_credit.doc == "Production Tax Credit ($)"
        assert block.annual_power_output_variable_cost.doc == "Annual Power Output Variable Cost ($)"
        assert block.annual_production_tax_credit.doc == "Annual Production Tax Credit ($)"
