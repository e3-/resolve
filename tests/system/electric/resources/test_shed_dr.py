import pandas as pd
import pytest
from pyomo.environ import value

from new_modeling_toolkit.system.electric.resources.shed_dr import ShedDrResource
from tests.system.electric.resources import test_unit_commitment


class TestShedDrResource(test_unit_commitment.TestUnitCommitmentResource):
    @pytest.fixture(scope="function")
    def block_comp_for_budget_tests(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm, first_index
    ):
        block = make_component_with_block_copy_inter_period_sharing().formulation_block
        model = block.model()
        modeled_year, weather_period, weather_timestamp = first_index_erm
        second_index = modeled_year, model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS.nextw(
            (weather_period, weather_timestamp)
        )
        third_index = modeled_year, model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS.nextw(
            (weather_period, weather_timestamp), 2
        )
        for chrono_per, timestamp in model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS:
            block.erm_power_output[modeled_year, chrono_per, timestamp].fix(0)
        # These two need to sum to (751 / 584) = 1.2859. For these tests, the budget is 751 and
        # 584 is the constant factor in sum_weather_timestamp_component_slice_to_annual().
        block.erm_power_output[second_index].fix(0.5)
        block.erm_power_output[third_index].fix(0.7859)

        # Now set up the non-ERM power_output:
        second_index = modeled_year, model.DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(first_index[1:])
        third_index = modeled_year, model.DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(first_index[1:], 2)
        for dispatch_window, timestamp in model.DISPATCH_WINDOWS_AND_TIMESTAMPS:
            block.power_output[modeled_year, dispatch_window, timestamp].fix(0)
        block.power_output[second_index].fix(1)
        block.power_output[third_index].fix(1.5)

        return block

    _COMPONENT_CLASS = ShedDrResource
    _COMPONENT_NAME = "ShedDRResource"
    _SYSTEM_COMPONENT_DICT_NAME = "shed_dr_resources"

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
            "unit_size",
            "unit_commitment_mode",
            "min_down_time",
            "min_up_time",
            "min_stable_level",
            "start_cost",
            "shutdown_cost",
            "initial_committed_units",
            "max_call_duration",
            "max_annual_calls",
            "max_monthly_calls",
            "max_daily_calls",
        ]

    @pytest.mark.skip(reason="Functionality not implemented yet for ShedDrResource")
    def test_check_if_operationally_equal(self, make_component_with_block_copy, test_zone_1, test_zone_2):
        super().test_check_if_operationally_equal(make_component_with_block_copy, test_zone_1, test_zone_2)

    def test_annual_dr_call_limit_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        resource_block.start_units.fix(0)
        resource_block.start_units[modeled_year, dispatch_window, timestamp].fix(1)
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].upper() == 0
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].body() == 1 * 219 - (365 * (100 / 50))
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].expr()

        resource_block.start_units[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=1)].fix(1)
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].body() == 2 * 219 - (365 * (100 / 50))
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].expr()

        resource_block.start_units[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=2)].fix(8)
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].body() == 10 * 219 - (365 * (100 / 50))
        assert not resource_block.annual_dr_call_limit_constraint[modeled_year].expr()

    # TODO (2024-06-18): Come back to monthly_dr_call tests after monthly calls are implemented in shed_dr.py
    # def test_monthly_dr_call_limit_constraint(self, make_component_with_block_copy, first_index):
    #     resource = make_component_with_block_copy()
    #     resource_block = resource.formulation_block
    #     modeled_year, dispatch_window, timestamp = first_index
    #     month = pd.Timestamp("2010-06-01 00:00:00")
    #     resource_block.start_units.fix(0)
    #     assert resource_block.monthly_dr_call_limit_constraint[modeled_year, month].upper() == 1
    #     assert resource_block.monthly_dr_call_limit_constraint[modeled_year, month].body() == 0
    #     assert resource_block.monthly_dr_call_limit_constraint[modeled_year, month].expr()
    #
    #     resource_block.start_units[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=2)].fix(1)
    #     assert resource_block.monthly_dr_call_limit_constraint[modeled_year, month].body() == 1
    #     assert resource_block.monthly_dr_call_limit_constraint[modeled_year, month].expr()
    #
    #     resource_block.start_units[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=3)].fix(1)
    #     assert resource_block.monthly_dr_call_limit_constraint[modeled_year, month].body() == 2
    #     assert not resource_block.monthly_dr_call_limit_constraint[modeled_year, month].expr()

    # TODO (2024-06-18): Come back to monthly_dr_call tests after monthly calls are implemented in shed_dr.py
    # def test_monthly_dr_call_limit_power_output_constraint(self, make_component_with_block_copy, first_index):
    #     resource = make_component_with_block_copy()
    #     resource_block = resource.formulation_block
    #     modeled_year, dispatch_window, timestamp = first_index
    #     month = pd.Timestamp("2010-06-01 00:00:00")
    #     resource_block.start_units_power_output.fix(0)
    #     assert resource_block.monthly_dr_call_limit_power_output_constraint[modeled_year, month].upper() == 1
    #     assert resource_block.monthly_dr_call_limit_power_output_constraint[modeled_year, month].body() == 0
    #     assert resource_block.monthly_dr_call_limit_power_output_constraint[modeled_year, month].expr()
    #
    #     resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=2)].fix(1)
    #     assert resource_block.monthly_dr_call_limit_power_output_constraint[modeled_year, month].body() == 1
    #     assert resource_block.monthly_dr_call_limit_power_output_constraint[modeled_year, month].expr()
    #
    #     resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=3)].fix(1)
    #     assert resource_block.monthly_dr_call_limit_power_output_constraint[modeled_year, month].body() == 2
    #     assert not resource_block.monthly_dr_call_limit_power_output_constraint[modeled_year, month].expr()

    def test_daily_dr_call_limit_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        day = pd.Timestamp("2010-06-21 00:00:00")
        modeled_year, dispatch_window, timestamp = first_index
        resource_block.start_units.fix(0)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].upper() == 0
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 0 - (100 / 50)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

        resource_block.start_units[modeled_year, dispatch_window, timestamp].fix(1)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 1 - (100 / 50)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

        resource_block.start_units[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=1)].fix(1)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 2 - (100 / 50)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

        resource_block.start_units[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=2)].fix(8)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 10 - (100 / 50)
        assert not resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

    def test_max_dr_call_duration_intra_period_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        resource_block.start_units.fix(0)
        timestamp = timestamp + pd.DateOffset(hours=2)

        resource_block.committed_units[modeled_year, dispatch_window, timestamp].fix(1)
        assert (
            resource_block.max_dr_call_duration_intra_period_constraint[modeled_year, dispatch_window, timestamp].body()
            == 1
        )
        assert (
            resource_block.max_dr_call_duration_intra_period_constraint[
                modeled_year, dispatch_window, timestamp
            ].upper()
            == 0
        )
        assert not resource_block.max_dr_call_duration_intra_period_constraint[
            modeled_year, dispatch_window, timestamp
        ].expr()

        resource_block.start_units[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=1)].fix(1)
        assert (
            resource_block.max_dr_call_duration_intra_period_constraint[modeled_year, dispatch_window, timestamp].body()
            == 0
        )
        assert (
            resource_block.max_dr_call_duration_intra_period_constraint[
                modeled_year, dispatch_window, timestamp
            ].upper()
            == 0
        )
        assert resource_block.max_dr_call_duration_intra_period_constraint[
            modeled_year, dispatch_window, timestamp
        ].expr()

        resource_block.start_units[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=1)].fix(0)
        resource_block.start_units[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=2)].fix(1)
        assert (
            resource_block.max_dr_call_duration_intra_period_constraint[modeled_year, dispatch_window, timestamp].body()
            == 0
        )
        assert (
            resource_block.max_dr_call_duration_intra_period_constraint[
                modeled_year, dispatch_window, timestamp
            ].upper()
            == 0
        )
        assert resource_block.max_dr_call_duration_intra_period_constraint[
            modeled_year, dispatch_window, timestamp
        ].expr()

    def test_max_dr_call_duration_inter_period_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index, last_index
    ):
        resource = make_component_with_block_copy_inter_period_sharing()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # timestamps = [
        #     "2010-06-21 00:00",
        #     "2010-06-21 01:00",
        #     "2010-06-21 02:00",
        #     "2012-02-15 12:00",
        #     "2012-02-15 13:00",
        #     "2012-02-15 14:00",
        # ]

        chrono_period = list(resource_block.model().CHRONO_PERIODS)[0]

        (
            chrono_period_1_index,
            chrono_period_2_index,
        ) = resource_block.model().return_timepoints_connecting_chrono_periods(modeled_year, chrono_period)
        _, dispatch_window, last_timestamp_chrono_period = chrono_period_1_index
        _, next_dispatch_window, first_timestamp_next_chrono_period = chrono_period_2_index

        resource_block.start_units.fix(0)
        resource_block.committed_units[modeled_year, dispatch_window, first_timestamp_next_chrono_period].fix(1)
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].body() == 1
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].upper() == 0
        assert not resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].expr()

        resource_block.start_units[modeled_year, dispatch_window, first_timestamp_next_chrono_period].fix(1)
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].body() == 0
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].upper() == 0
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].expr()

        resource_block.start_units[modeled_year, dispatch_window, last_timestamp_chrono_period].fix(1)
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].body() == -1
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].upper() == 0
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].expr()

        resource_block.committed_units[
            modeled_year, dispatch_window, first_timestamp_next_chrono_period + pd.DateOffset(hours=1)
        ].fix(2)
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 1].body() == 0
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 1].upper() == 0
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 1].expr()

        resource_block.committed_units[modeled_year, dispatch_window, first_timestamp_next_chrono_period].fix(3)
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].body() == 1
        assert resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].upper() == 0
        assert not resource_block.max_dr_call_duration_inter_period_constraint[modeled_year, chrono_period, 0].expr()

    def test_erm_power_output_max_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        modeled_year, _, weather_timestamp = first_index_erm
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        # Asserting this so that future readers can understand the calculations below
        assert asset.pmax_profile[weather_timestamp] == 0.5

        block.erm_power_output[first_index_erm] = 45.0
        block.erm_committed_capacity[first_index_erm] = 100.0
        assert block.erm_power_output_max_constraint[first_index_erm].upper() == 0.0
        assert block.erm_power_output_max_constraint[first_index_erm].body() == -5.0
        assert block.erm_power_output_max_constraint[first_index_erm].expr()

        block.erm_power_output[first_index_erm] = 55.0
        assert block.erm_power_output_max_constraint[first_index_erm].upper() == 0.0
        assert block.erm_power_output_max_constraint[first_index_erm].body() == 5.0
        assert not block.erm_power_output_max_constraint[first_index_erm].expr()

        block.erm_power_output[first_index_erm] = 50.0
        block.erm_committed_capacity[first_index_erm] = 100.0
        assert block.erm_power_output_max_constraint[first_index_erm].upper() == 0.0
        assert block.erm_power_output_max_constraint[first_index_erm].body() == 0.0
        assert block.erm_power_output_max_constraint[first_index_erm].expr()

    def test_erm_annual_energy_budget_constraint(self, block_comp_for_budget_tests, first_index_erm):
        block = block_comp_for_budget_tests
        model = block.model()
        modeled_year = model.MODELED_YEARS.first()
        constraint_index_1 = modeled_year, model.WEATHER_YEARS.first()

        block.operational_capacity[modeled_year] = 100

        # test that it passes if annual mwh is equal to budget
        assert block.erm_annual_energy_budget_constraint[constraint_index_1].body() == pytest.approx(
            ((1.2859 / 15.0) * 24 * 365) - 751
        )

        assert block.erm_annual_energy_budget_constraint[constraint_index_1].upper() == pytest.approx(0)

        assert block.erm_annual_energy_budget_constraint[constraint_index_1].expr()

        # test that it fails if annual mwh is greater than budget
        block.erm_power_output[
            modeled_year, model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS.nextw(first_index_erm[1:], 2)
        ].fix(5)
        assert block.erm_annual_energy_budget_constraint[constraint_index_1].body() == pytest.approx(
            ((5.5 / 15.0) * 24 * 365) - 751
        )

        assert block.erm_annual_energy_budget_constraint[constraint_index_1].upper() == pytest.approx(0)

        assert not block.erm_annual_energy_budget_constraint[constraint_index_1].expr()

        # test that it passes if annual mwh is less than budget

        block.erm_power_output[
            modeled_year, model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS.nextw(first_index_erm[1:], 2)
        ].fix(0.0)
        assert block.erm_annual_energy_budget_constraint[constraint_index_1].body() == pytest.approx(
            ((0.5 / 15.0) * 24 * 365) - 751
        )

        assert block.erm_annual_energy_budget_constraint[constraint_index_1].upper() == pytest.approx(0)

        assert block.erm_annual_energy_budget_constraint[constraint_index_1].expr()

    def test_erm_daily_energy_budget_constraint(self, block_comp_for_budget_tests, first_index_erm):
        block = block_comp_for_budget_tests
        model = block.model()
        modeled_year, weather_period, _ = first_index_erm
        constraint_index_1 = modeled_year, weather_period

        block.operational_capacity[modeled_year] = 100

        # test that it passes if daily mwh is equal to budget
        assert block.erm_daily_energy_budget_MWh[constraint_index_1].expr() == pytest.approx(
            250
        )  # 100 * 24 * 0.1041666667
        for weather_timestamp in model.WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period]:
            block.erm_power_output[modeled_year, weather_period, weather_timestamp].fix(
                250 / len(model.WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period])
            )
        assert block.erm_daily_energy_budget_constraint[constraint_index_1].body() == pytest.approx(
            0 - 1
        )  # 1 is the budget tolerance
        assert block.erm_daily_energy_budget_constraint[constraint_index_1].upper() == 0
        assert block.erm_daily_energy_budget_constraint[constraint_index_1].expr()

        # test that it fails if annual mwh is greater than budget
        for weather_timestamp in model.WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period]:
            block.erm_power_output[modeled_year, weather_period, weather_timestamp].fix(250)
        assert block.erm_daily_energy_budget_constraint[constraint_index_1].body() == pytest.approx(
            len(model.WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period]) * 250 - 250 - 1
        )
        assert block.erm_daily_energy_budget_constraint[constraint_index_1].upper() == 0
        assert not block.erm_daily_energy_budget_constraint[constraint_index_1].expr()

        # test that it passes if annual mwh is less than budget
        for weather_timestamp in model.WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period]:
            block.erm_power_output[modeled_year, weather_period, weather_timestamp].fix(0)
        assert block.erm_daily_energy_budget_constraint[constraint_index_1].body() == pytest.approx(
            -250 - 1
        )  # 1 is the budget tolerance
        assert block.erm_daily_energy_budget_constraint[constraint_index_1].upper() == 0
        assert block.erm_daily_energy_budget_constraint[constraint_index_1].expr()

    def test_erm_dispatch_cost(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        assert block.erm_dispatch_cost_per_MWh.value == 0.01

        # Expression is:
        # block.erm_dispatch_cost_per_MWh * (block.erm_power_output[modeled_year, weather_period, weather_timestamp]
        # + block.erm_start_units[modeled_year, weather_period, weather_timestamp]
        # + block.erm_committed_units[modeled_year, weather_period, weather_timestamp])

        block.erm_power_output[first_index_erm].fix(10.0)
        block.erm_start_units[first_index_erm].fix(1.0)
        block.erm_committed_units[first_index_erm].fix(1.0)
        assert block.erm_dispatch_cost[first_index_erm].expr() == pytest.approx(0.12)

        block.erm_power_output[first_index_erm].fix(5.0)
        block.erm_start_units[first_index_erm].fix(0.0)
        block.erm_committed_units[first_index_erm].fix(1.0)
        assert block.erm_dispatch_cost[first_index_erm].expr() == pytest.approx(0.06)

    def test_erm_annual_dispatch_cost(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        NUM_HOURS_PER_DAY = 24
        assert block.erm_dispatch_cost_per_MWh.value == 0.01

        first_modeled_year = pd.Timestamp("2025-01-01")
        block.erm_dispatch_cost[first_modeled_year, :, :] = 1.5
        num_days_per_year = block.model().num_days_per_modeled_year[first_modeled_year]
        assert block.erm_annual_dispatch_cost[first_modeled_year].expr() == 1.5 * num_days_per_year * NUM_HOURS_PER_DAY

        second_modeled_year = pd.Timestamp("2030-01-01")
        block.erm_dispatch_cost[second_modeled_year, :, :] = 2.5
        num_days_per_year = block.model().num_days_per_modeled_year[second_modeled_year]
        assert block.erm_annual_dispatch_cost[second_modeled_year].expr() == 2.5 * num_days_per_year * NUM_HOURS_PER_DAY

    def test_erm_committed_capacity(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block

        assert asset.unit_size == 50.0
        block.erm_committed_units[first_index_erm] = 10.0
        assert block.erm_committed_capacity[first_index_erm].expr() == 500.0

        block.erm_committed_units[first_index_erm] = 20.0
        assert block.erm_committed_capacity[first_index_erm].expr() == 1000.0

    def test_erm_commitment_tracking_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        modeled_year, weather_period, weather_timestamp = first_index_erm
        next_timestamp = block.model().WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period].nextw(weather_timestamp)
        block.erm_committed_units[first_index_erm] = 50.0
        block.erm_committed_units[modeled_year, weather_period, next_timestamp] = 60.0
        block.erm_shutdown_units[modeled_year, weather_period, next_timestamp] = 10.0
        block.erm_start_units[modeled_year, weather_period, next_timestamp] = 20.0

        assert block.erm_commitment_tracking_constraint[first_index_erm].expr()
        assert block.erm_commitment_tracking_constraint[first_index_erm].upper() == 0.0
        assert block.erm_commitment_tracking_constraint[first_index_erm].body() == 0.0

        block.erm_start_units[modeled_year, weather_period, next_timestamp] = 10.0
        assert not block.erm_commitment_tracking_constraint[first_index_erm].expr()
        assert block.erm_commitment_tracking_constraint[first_index_erm].upper() == 0.0
        assert block.erm_commitment_tracking_constraint[first_index_erm].body() == 10.0

        block.erm_start_units[modeled_year, weather_period, next_timestamp] = 30.0
        assert not block.erm_commitment_tracking_constraint[first_index_erm].expr()
        assert block.erm_commitment_tracking_constraint[first_index_erm].upper() == 0.0
        assert block.erm_commitment_tracking_constraint[first_index_erm].body() == -10.0

    def test_erm_daily_call_limit_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        modeled_year, weather_period, weather_timestamp = first_index_erm
        block.operational_capacity[modeled_year] = 100.0

        assert value(asset._annual_num_units(modeled_year)) == 2.0

        for weather_timestamp in block.model().WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period]:
            block.erm_start_units[modeled_year, weather_period, weather_timestamp] = 1.0

        assert not block.erm_daily_call_limit_constraint[modeled_year, weather_period].expr()
        assert block.erm_daily_call_limit_constraint[modeled_year, weather_period].upper() == 0.0
        assert block.erm_daily_call_limit_constraint[modeled_year, weather_period].body() == 1.0

        for i, weather_timestamp in enumerate(block.model().WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period]):
            if i % 2 == 1:
                block.erm_start_units[modeled_year, weather_period, weather_timestamp] = 1.0
            else:
                block.erm_start_units[modeled_year, weather_period, weather_timestamp] = 0.0
        assert block.erm_daily_call_limit_constraint[modeled_year, weather_period].expr()
        assert block.erm_daily_call_limit_constraint[modeled_year, weather_period].upper() == 0.0
        assert block.erm_daily_call_limit_constraint[modeled_year, weather_period].body() == -1.0

    def test_erm_max_dr_call_duration_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        modeled_year, weather_period, weather_timestamp = first_index_erm

        for w_t in block.model().WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period]:
            block.erm_start_units[modeled_year, weather_period, w_t] = 1.0

        end_timestamp = (
            block.model().WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period].nextw(weather_timestamp, step=2)
        )

        block.erm_committed_units[modeled_year, weather_period, end_timestamp] = 1.0
        assert block.erm_max_dr_call_duration_constraint[modeled_year, weather_period, end_timestamp].expr()
        assert block.erm_max_dr_call_duration_constraint[modeled_year, weather_period, end_timestamp].upper() == 0.0
        assert block.erm_max_dr_call_duration_constraint[modeled_year, weather_period, end_timestamp].body() == -2.0

        block.erm_committed_units[modeled_year, weather_period, end_timestamp] = 10.0
        assert not block.erm_max_dr_call_duration_constraint[modeled_year, weather_period, end_timestamp].expr()
        assert block.erm_max_dr_call_duration_constraint[modeled_year, weather_period, end_timestamp].upper() == 0.0
        assert block.erm_max_dr_call_duration_constraint[modeled_year, weather_period, end_timestamp].body() == 7.0

    def test_erm_committed_units_ub_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm, last_index_erm
    ):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        block.operational_capacity[first_index_erm[0]] = 100.0
        block.operational_capacity[last_index_erm[0]] = 100.0

        assert (
            value(asset._annual_num_units(first_index_erm[0]))
            == value(asset._annual_num_units(last_index_erm[0]))
            == 2.0
        )

        # Constraint satisfied in first index
        block.erm_committed_units[first_index_erm] = 1.0
        assert block.erm_committed_units_ub_constraint[first_index_erm].upper() == 0.0
        assert block.erm_committed_units_ub_constraint[first_index_erm].body() == -1.0
        assert block.erm_committed_units_ub_constraint[first_index_erm].expr()

        # Constraint violated in last index
        block.erm_committed_units[last_index_erm] = 3.0
        assert block.erm_committed_units_ub_constraint[last_index_erm].upper() == 0.0
        assert block.erm_committed_units_ub_constraint[last_index_erm].body() == 1.0
        assert not block.erm_committed_units_ub_constraint[last_index_erm].expr()

    def test_erm_start_units_ub_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm, last_index_erm
    ):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        block.operational_capacity[first_index_erm[0]] = 100.0
        block.operational_capacity[last_index_erm[0]] = 100.0

        assert (
            value(asset._annual_num_units(first_index_erm[0]))
            == value(asset._annual_num_units(last_index_erm[0]))
            == 2.0
        )

        # Constraint satisfied in first index
        block.erm_start_units[first_index_erm] = 1.0
        assert block.erm_start_units_ub_constraint[first_index_erm].upper() == 0.0
        assert block.erm_start_units_ub_constraint[first_index_erm].body() == -1.0
        assert block.erm_start_units_ub_constraint[first_index_erm].expr()

        # Constraint violated in last index
        block.erm_start_units[last_index_erm] = 3.0
        assert block.erm_start_units_ub_constraint[last_index_erm].upper() == 0.0
        assert block.erm_start_units_ub_constraint[last_index_erm].body() == 1.0
        assert not block.erm_start_units_ub_constraint[last_index_erm].expr()

    def test_erm_shutdown_units_ub_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm, last_index_erm
    ):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        block.operational_capacity[first_index_erm[0]] = 100.0
        block.operational_capacity[last_index_erm[0]] = 100.0

        assert (
            value(asset._annual_num_units(first_index_erm[0]))
            == value(asset._annual_num_units(last_index_erm[0]))
            == 2.0
        )

        # Constraint satisfied in first index
        block.erm_shutdown_units[first_index_erm] = 1.0
        assert block.erm_shutdown_units_ub_constraint[first_index_erm].upper() == 0.0
        assert block.erm_shutdown_units_ub_constraint[first_index_erm].body() == -1.0
        assert block.erm_shutdown_units_ub_constraint[first_index_erm].expr()

        # Constraint violated in last index
        block.erm_shutdown_units[last_index_erm] = 3.0
        assert block.erm_shutdown_units_ub_constraint[last_index_erm].upper() == 0.0
        assert block.erm_shutdown_units_ub_constraint[last_index_erm].body() == 1.0
        assert not block.erm_shutdown_units_ub_constraint[last_index_erm].expr()
