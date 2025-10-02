import copy

import pandas as pd
import pytest

import new_modeling_toolkit.core.temporal.timeseries as ts
from new_modeling_toolkit.system.electric.resources import StorageResource
from new_modeling_toolkit.system.electric.resources.storage import StorageDurationConstraint
from new_modeling_toolkit.system.electric.resources.storage import StorageResourceGroup
from tests.system.electric.resources import test_generic


class TestStorageResource(test_generic.TestGenericResource):
    _COMPONENT_CLASS = StorageResource
    _COMPONENT_NAME = "StorageResource1"
    _SYSTEM_COMPONENT_DICT_NAME = "storage_resources"

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
            "duration",
            "duration_constraint",
            "variable_cost_power_input",
            "power_input_min",
            "power_input_min__type",
            "power_input_max",
            "power_input_max__type",
            "charging_efficiency",
            "charging_efficiency__type",
            "discharging_efficiency",
            "discharging_efficiency__type",
            "parasitic_loss",
            "state_of_charge_min",
        ]

    def test_variable_bounds(self, make_component_with_block_copy):
        super().test_variable_bounds(make_component_with_block_copy=make_component_with_block_copy)

        resource = make_component_with_block_copy()
        block = resource.formulation_block

        for index in block.power_input:
            assert block.power_input[index].lb == 0
            assert block.power_input[index].ub is None

        for index in block.soc_intra_period:
            assert block.soc_intra_period[index].lb is None
            assert block.soc_intra_period[index].ub is None

        for index in block.soc_inter_period:
            assert block.soc_inter_period[index].lb == 0
            assert block.soc_inter_period[index].ub is None

    def test_power_input_max(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.operational_capacity[pd.Timestamp("2025-01-01")] = 200
        block.operational_capacity[pd.Timestamp("2035-01-01")] = 150

        assert (
            block.power_input_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00")
            ].expr()
            == 200 * 0.5
        )
        assert (
            block.power_input_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 01:00")
            ].expr()
            == 200 * 0.5
        )
        assert (
            block.power_input_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 02:00")
            ].expr()
            == 200 * 0.5
        )
        assert (
            block.power_input_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 12:00")
            ].expr()
            == 200 * 0.5
        )
        assert (
            block.power_input_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00")
            ].expr()
            == 200 * 0.5
        )
        assert (
            block.power_input_max[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00")
            ].expr()
            == 200 * 0.5
        )

        assert (
            block.power_input_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00")
            ].expr()
            == 150 * 0.5
        )
        assert (
            block.power_input_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 01:00")
            ].expr()
            == 150 * 0.5
        )
        assert (
            block.power_input_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 02:00")
            ].expr()
            == 150 * 0.5
        )
        assert (
            block.power_input_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 12:00")
            ].expr()
            == 150 * 0.5
        )
        assert (
            block.power_input_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00")
            ].expr()
            == 150 * 0.5
        )
        assert (
            block.power_input_max[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00")
            ].expr()
            == 150 * 0.5
        )

    def test_power_input_min(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.operational_capacity[pd.Timestamp("2025-01-01")] = 200
        block.operational_capacity[pd.Timestamp("2035-01-01")] = 150

        assert (
            block.power_input_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00")
            ].expr()
            == 200 * 0.1
        )
        assert (
            block.power_input_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 01:00")
            ].expr()
            == 200 * 0.1
        )
        assert (
            block.power_input_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 02:00")
            ].expr()
            == 200 * 0.1
        )
        assert (
            block.power_input_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 12:00")
            ].expr()
            == 200 * 0.1
        )
        assert (
            block.power_input_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00")
            ].expr()
            == 200 * 0.1
        )
        assert (
            block.power_input_min[
                pd.Timestamp("2025-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00")
            ].expr()
            == 200 * 0.1
        )

        assert (
            block.power_input_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00")
            ].expr()
            == 150 * 0.1
        )
        assert (
            block.power_input_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 01:00")
            ].expr()
            == 150 * 0.1
        )
        assert (
            block.power_input_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 02:00")
            ].expr()
            == 150 * 0.1
        )
        assert (
            block.power_input_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 12:00")
            ].expr()
            == 150 * 0.1
        )
        assert (
            block.power_input_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00")
            ].expr()
            == 150 * 0.1
        )
        assert (
            block.power_input_min[
                pd.Timestamp("2035-01-01"), pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00")
            ].expr()
            == 150 * 0.1
        )

    def test_power_input_max_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        block.operational_capacity[modeled_year] = 200

        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(80.0)
        assert (
            block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].body()
            == -20  # 80 - 0.5 * 200
        )
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(250.0)
        assert (
            block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == 150
        )  # 250 - 0.5*200
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert not block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0 - 0.5 * 200
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

    def test_power_input_min_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        block.operational_capacity[pd.Timestamp("2025-01-01")] = 200

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(160.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(120.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0.1 * 200 - 120
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(30.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(10.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0.1 * 200 - 10
        assert not block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0.1 * 200 - 0
        assert not block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()

    def test_total_up_reserves_max_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        block.operational_capacity[modeled_year] = 200

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(160.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(120.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert (
            block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == -130
        )  # 160 + 30 - 120 - 200
        assert block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(600.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(50.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert (
            block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == 380
        )  # 600 + 30 - 50 - 200
        assert block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert not block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(0.0)
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
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(80.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert (
            block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body()
            == -140  # 80 - 120 - 0.5 * 200
        )
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(120.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(250.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert (
            block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == 30
        )  # 250 - 120 - 0.5*200
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert not block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(0.0)
        assert (
            block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].body()
            == 0 - 0.5 * 200
        )
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

    def test_mileage_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        block.operational_capacity[modeled_year] = 200

        block.power_output[modeled_year, dispatch_window, timestamp].fix(100)
        block.power_input[modeled_year, dispatch_window, timestamp].fix(50)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window, timestamp].fix(30.0)
        assert block.mileage_constraint[modeled_year, dispatch_window, timestamp].body() == (100 + 50 + 30 - 200 * 1.0)
        assert block.mileage_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        assert block.mileage_constraint[modeled_year, dispatch_window, timestamp].expr()

        block.power_output[modeled_year, dispatch_window, timestamp].fix(100)
        block.power_input[modeled_year, dispatch_window, timestamp].fix(150)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window, timestamp].fix(30.0)
        assert block.mileage_constraint[modeled_year, dispatch_window, timestamp].body() == (100 + 150 + 30 - 200 * 1.0)
        assert block.mileage_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        assert not block.mileage_constraint[modeled_year, dispatch_window, timestamp].expr()

        block.power_output[modeled_year, pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00:00")].fix(100)
        block.power_input[modeled_year, pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00:00")].fix(150)
        block.provide_reserve[
            "TestRegulationUp", modeled_year, pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00:00")
        ].fix(30.0)
        assert block.mileage_constraint[
            modeled_year, pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00:00")
        ].body() == (100 + 150 + 30 - 200 * 0.5)
        assert (
            block.mileage_constraint[
                modeled_year, pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00:00")
            ].upper()
            == 0
        )
        assert not block.mileage_constraint[
            modeled_year, pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 13:00:00")
        ].expr()

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
        resource_block.power_input.fix(0)
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
        resource_block.power_input.fix(0)
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
        resource_block.power_input.fix(0)
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
        resource_block.power_input.fix(0)
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

    def test_soc_intra_operating_reserve_up_max(self, make_component_with_block_copy, first_index):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.power_input[modeled_year, dispatch_window, timestamp].fix(0)
        resource_block.power_output[modeled_year, dispatch_window, timestamp].fix(0)

        # Test 1a: Basic : Should not be able to provide more reserve than SOC * discharge_efficiency
        resource_block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window, timestamp].fix(1200)
        resource_block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(1300)
        assert (
            resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].body() == 30
        )  # 1200 - (0.9 * 1300)
        assert resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].upper() == 0
        assert not resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].expr()

        # Test 1b Basic : Reserve / discharge_eff - SOC <= 0 (LHS should return 225)
        resource_block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window, timestamp].fix(1100)
        assert (
            resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].body() == -70
        )  # 1100 - (0.9 * 1300)
        assert resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].upper() == 0
        assert resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].expr()

        # Test 2a: Reserve / discharging_eff <= SOC + power_input - power_output / discharging_efficiency
        resource_block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(1800)
        resource_block.power_output[modeled_year, dispatch_window, timestamp].fix(200)
        resource_block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window, timestamp].fix(1200)
        assert (
            resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].body() == -220
        )  # 1200 - (0.9 * 1800 - 200)
        assert resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].upper() == 0
        assert resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].expr()

        # Test 2b
        resource_block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window, timestamp].fix(1500)
        assert (
            resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].body() == 80
        )  # 1500 - (0.9 * 1800 - 200)
        assert resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].upper() == 0
        assert not resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].expr()

        # Test 3 : Reserves  <= Power_Input + SOC * discharge_efficiency
        # No charging_efficiency required (see Storage formulation)
        resource_block.power_output[modeled_year, dispatch_window, timestamp].fix(0)
        resource_block.power_input[modeled_year, dispatch_window, timestamp].fix(100)
        resource_block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(1000)
        resource_block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window, timestamp].fix(1500)
        assert (
            resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].body() == 500
        )  # 1500 - (0.9 * 1000 + 100)
        assert resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].upper() == 0
        assert not resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].expr()

        resource_block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window, timestamp].fix(900)
        assert (
            resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].body() == -100
        )  # 1500 - (0.9 * 1000 + 100)
        assert resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].upper() == 0
        assert resource_block.soc_intra_operating_reserve_up_max[modeled_year, dispatch_window, timestamp].expr()

    def test_soc_inter_intra_max_constraint(self, make_component_with_block_copy, first_index_storage):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, chrono_period, timestamp = first_index_storage
        dispatch_window = chrono_period

        # Test 1: SOC is 0
        resource_block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(0)
        resource_block.soc_inter_period[modeled_year, chrono_period].fix(0)
        assert not resource_block.soc_inter_intra_joint[modeled_year, chrono_period, timestamp].expr()

        resource_block.operational_storage_capacity[modeled_year] = 50

        assert resource_block.soc_inter_intra_max_constraint[
            modeled_year, chrono_period, timestamp
        ].body() == pytest.approx(
            -55.5555555
        )  # 0 - 50 / 0.9
        assert resource_block.soc_inter_intra_max_constraint[modeled_year, chrono_period, timestamp].upper() == 0
        assert resource_block.soc_inter_intra_max_constraint[modeled_year, chrono_period, timestamp].expr()

        # Test 2: SOC is max
        resource_block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(35)
        resource_block.soc_inter_period[modeled_year, chrono_period].fix(25)

        assert resource_block.soc_inter_intra_max_constraint[
            modeled_year, chrono_period, timestamp
        ].body() == pytest.approx(4.4444444)
        assert resource_block.soc_inter_intra_max_constraint[modeled_year, chrono_period, timestamp].upper() == 0
        assert not resource_block.soc_inter_intra_max_constraint[modeled_year, chrono_period, timestamp].expr()

    def test_soc_inter_intra_min_constraint(self, make_component_with_block_copy, first_index_storage):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, chrono_period, timestamp = first_index_storage
        dispatch_window = chrono_period

        resource_block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(0)
        resource_block.soc_inter_period[modeled_year, chrono_period].fix(0)
        assert resource_block.soc_inter_intra_joint[modeled_year, chrono_period, timestamp].expr() == 0

        resource_block.operational_storage_capacity[modeled_year] = 50

        assert resource_block.soc_inter_intra_min_constraint[modeled_year, chrono_period, timestamp]

    def test_soc_intra_tracking_constraint(self, make_component_with_block_copy, first_index):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.power_input[modeled_year, dispatch_window, timestamp].fix(40)
        resource_block.power_output[modeled_year, dispatch_window, timestamp].fix(30)
        resource_block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(20)
        resource_block.soc_intra_period[
            modeled_year,
            storage_resource.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.next(
                (dispatch_window, timestamp)
            ),
        ].fix(10)

        assert resource_block.soc_intra_tracking_constraint[
            modeled_year, dispatch_window, timestamp
        ].body() == pytest.approx(
            -10.66666666
        )  # 10 - (20 + 0.85 * 40 - 30 / 0.9)
        assert resource_block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].lower() == 0
        assert resource_block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        assert not resource_block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].expr()

        resource_block.power_input[modeled_year, dispatch_window, timestamp].fix(100)
        resource_block.power_output[modeled_year, dispatch_window, timestamp].fix(90)
        resource_block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(200)
        resource_block.soc_intra_period[
            modeled_year,
            storage_resource.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.next(
                (dispatch_window, timestamp)
            ),
        ].fix(185)

        assert resource_block.soc_intra_tracking_constraint[
            modeled_year, dispatch_window, timestamp
        ].body() == pytest.approx(
            0
        )  # 185 - (200 + 0.85 * 100 - 90 / 0.9)
        assert resource_block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].lower() == 0
        assert resource_block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        assert resource_block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].expr()

    def test_soc_inter_tracking_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_inter_period_sharing
    ):
        storage_resource = make_component_with_block_copy_inter_period_sharing()
        resource_block = storage_resource.formulation_block
        modeled_year, chrono_period, timestamp = first_index_inter_period_sharing
        dispatch_window = pd.Timestamp("2012-02-15")

        final_hour = resource_block.model().last_timepoint_in_dispatch_window[dispatch_window]
        resource_block.power_input[modeled_year, dispatch_window, timestamp].fix(40)
        resource_block.power_output[modeled_year, dispatch_window, timestamp].fix(30)
        resource_block.power_input[modeled_year, dispatch_window, final_hour].fix(40)
        resource_block.power_output[modeled_year, dispatch_window, final_hour].fix(30)

        resource_block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(0)
        resource_block.soc_intra_period[modeled_year, dispatch_window, final_hour].fix(0)
        resource_block.soc_inter_period[modeled_year, resource_block.model().CHRONO_PERIODS.next(chrono_period)].fix(0)
        resource_block.soc_inter_period[modeled_year, chrono_period].fix(0)

        assert not resource_block.soc_inter_tracking_constraint[modeled_year, chrono_period].expr()

    def test_soc_inter_zero_constraint_no_inter_period_sharing(
        self, make_component_with_block_copy, first_index_storage
    ):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block

        resource_block.soc_inter_period.fix(0)

        for modeled_year in [
            pd.Timestamp("2025-01-01"),
            pd.Timestamp("2030-01-01"),
            pd.Timestamp("2035-01-01"),
            pd.Timestamp("2045-01-01"),
        ]:
            for chrono_period in [pd.Timestamp("2010-06-21"), pd.Timestamp("2012-02-15")]:
                assert resource_block.soc_inter_tracking_constraint[modeled_year, chrono_period].lower() == 0
                assert resource_block.soc_inter_tracking_constraint[modeled_year, chrono_period].upper() == 0
                assert resource_block.soc_inter_tracking_constraint[modeled_year, chrono_period].body() == 0
                assert resource_block.soc_inter_tracking_constraint[modeled_year, chrono_period].expr()

    def test_soc_intra_anchoring_constraint_loopback(self, make_component_with_block_copy, first_index, last_index):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, _ = first_index

        resource_block.power_input[last_index].fix(40)
        resource_block.power_output[last_index].fix(30)
        resource_block.soc_intra_period[last_index].fix(20)
        resource_block.soc_intra_period[first_index].fix(10)

        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].body() == pytest.approx(
            -10.66666666
        )  # 10 - (20 + 0.85 * 40 - 30 / 0.9)
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].lower() == 0
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].upper() == 0
        assert not resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].expr()

        resource_block.power_input[last_index].fix(100)
        resource_block.power_output[last_index].fix(90)
        resource_block.soc_intra_period[last_index].fix(200)
        resource_block.soc_intra_period[first_index].fix(185)

        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].body() == pytest.approx(
            0
        )  # 185 - (200 + 0.85 * 100 - 90 / 0.9)
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].lower() == 0
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].upper() == 0
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].expr()

    def test_soc_intra_anchoring_constraint_interperiod(
        self, make_component_with_block_copy_inter_period_sharing, first_index
    ):
        storage_resource = make_component_with_block_copy_inter_period_sharing()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, _ = first_index

        resource_block.soc_intra_period[first_index].fix(10)
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].body() == 10
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].lower() == 0
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].upper() == 0
        assert not resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].expr()

        resource_block.soc_intra_period[first_index].fix(0)
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].body() == 0
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].lower() == 0
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].upper() == 0
        assert resource_block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].expr()

    def test_simultaneous_charging_constraint(self, make_component_with_block_copy, first_index):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.operational_capacity[modeled_year] = 100

        # Test 1
        resource_block.power_output[modeled_year, dispatch_window, timestamp].fix(50)
        resource_block.power_input[modeled_year, dispatch_window, timestamp].fix(50)
        resource_block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window, timestamp].fix(40)

        assert not resource_block.simultaneous_charging_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test 2
        resource_block.power_output[modeled_year, dispatch_window, timestamp].fix(20)
        resource_block.power_input[modeled_year, dispatch_window, timestamp].fix(50)
        resource_block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window, timestamp].fix(4)

        assert resource_block.simultaneous_charging_constraint[modeled_year, dispatch_window, timestamp].expr()

    def test_storage_capacity_duration_constraint_fixed(self, make_component_with_block_copy, first_index):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.operational_storage_capacity[modeled_year] = 40.0
        resource_block.operational_capacity[modeled_year] = 10.0

        assert resource_block.storage_capacity_duration_constraint[modeled_year].expr()

    def test_storage_capacity_duration_constraint_minimum(self, make_custom_component_with_block, first_index):
        storage_resource = make_custom_component_with_block(duration_constraint=StorageDurationConstraint.MINIMUM)
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.operational_storage_capacity[modeled_year] = 40.0
        resource_block.operational_capacity[modeled_year] = 9

        assert resource_block.storage_capacity_duration_constraint[modeled_year].expr()

    def test_storage_capacity_duration_constraint_maximum(self, make_custom_component_with_block, first_index):
        storage_resource = make_custom_component_with_block(duration_constraint=StorageDurationConstraint.MAXIMUM)
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.operational_storage_capacity[modeled_year] = 40.0
        resource_block.operational_capacity[modeled_year] = 11.0

        assert resource_block.storage_capacity_duration_constraint[modeled_year].expr()

    def test_retired_storage_capacity_max_constraint_can_retire(self, make_component_with_block_copy, first_index):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Tests retireable resources during their physical lifetime
        resource_block.retired_storage_capacity[modeled_year] = 800.0

        assert not resource_block.retired_storage_capacity_max_constraint[modeled_year].expr()

    def test_retired_storage_capacity_max_constraint_cannot_retire(self, make_custom_component_with_block, first_index):
        storage_resource = make_custom_component_with_block(can_retire=False)
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Tests retireable resources during their physical lifetime
        resource_block.retired_storage_capacity[modeled_year] = 300.0

        assert not resource_block.retired_storage_capacity_max_constraint[modeled_year].expr()

    def test_retired_storage_capacity_max_constraint_cannot_retire_no_lifetime(
        self, make_custom_component_with_block, first_index
    ):
        storage_resource = make_custom_component_with_block(can_retire=False, physical_lifetime=100)
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Tests retireable resources during their physical lifetime
        resource_block.retired_storage_capacity[modeled_year] = 300.0

        assert not resource_block.retired_storage_capacity_max_constraint[modeled_year].expr()

    def test_storage_physical_lifetime_constraint(self, make_component_with_block_copy, last_modeled_year):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = last_modeled_year

        resource_block.operational_storage_capacity[modeled_year] = 30.0

        assert not resource_block.storage_physical_lifetime_constraint[modeled_year].expr()

    def test_power_input_variable_cost(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        assert resource.variable_cost_power_input.data.at[timestamp] == 1

        block.power_output[first_index].fix(100)
        block.power_input[first_index].fix(50)
        assert block.power_input_variable_cost[first_index].expr() == 50

    def test_annual_total_operational_cost(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.power_output.fix(10)
        block.power_input.fix(5)

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
        ]:
            assert block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (2 + 2 + 2) + 5 * (1 + 1 + 1))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (2 + 2 + 2) + 5 * (1 + 1 + 1))
            )

        for year in [
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            assert block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (0 + 0 + 0) + 5 * (1 + 1 + 1))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (0 + 0 + 0) + 5 * (1 + 1 + 1))
            )

        assert block.annual_total_operational_cost

    @pytest.mark.skip(
        "RG: I don't think this constraint is relevant anymore given E3's current practice for modeling fixed storage durations."
    )
    def test_reliability_capacity_duration_constraint(self, make_component_with_block_copy, first_index, last_index):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        policy = storage_resource.policies["TestPRM"].instance_to

        # First year: constriant holds
        first_year = first_index[0]
        resource_block.reliability_capacity["TestPRM", first_year] = 100.0
        resource_block.operational_storage_capacity[first_year] = 400.0
        assert policy.reliability_event_length.data.at[first_year] == 4.0
        assert resource_block.reliability_capacity_duration_constraint["TestPRM", first_year].upper() == 0.0
        assert resource_block.reliability_capacity_duration_constraint["TestPRM", first_year].body() == 0.0
        assert resource_block.reliability_capacity_duration_constraint["TestPRM", first_year].expr()

        # Last year: constraint does not hold
        last_year = last_index[0]
        resource_block.reliability_capacity["TestPRM", last_year] = 100.0
        resource_block.operational_storage_capacity[last_year] = 200.0
        assert policy.reliability_event_length.data.at[last_year] == 4.0
        assert resource_block.reliability_capacity_duration_constraint["TestPRM", last_year].upper() == 0.0
        assert resource_block.reliability_capacity_duration_constraint["TestPRM", last_year].body() == 50.0
        assert not resource_block.reliability_capacity_duration_constraint["TestPRM", last_year].expr()

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
            # ("annualized_storage_capital_cost", 10),
            # ("annualized_storage_fixed_om_cost", 15),
        ],
    )
    def test_check_if_operationally_equal_true(self, make_component_copy, attr_name, new_value):
        super().test_check_if_operationally_equal_true(
            make_component_copy=make_component_copy, attr_name=attr_name, new_value=new_value
        )

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
            ("duration", 12),
            ("duration_constraint", StorageDurationConstraint.MAXIMUM),
            (
                "variable_cost_power_input",
                ts.NumericTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "power_input_min",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "power_input_max",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "charging_efficiency",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.25, 0.5]),
                ),
            ),
            (
                "discharging_efficiency",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.6, 0.6]),
                ),
            ),
            ("parasitic_loss", 0.05),
            ("state_of_charge_min", 0.1),
        ],
    )
    def test_check_if_operationally_equal_false(self, make_component_copy, attr_name, new_value):
        # Test 3: An modified copy of the resource should not be equal to the original
        generic_resource = make_component_copy()
        curr_test_copy = generic_resource.copy(include_linkages=True, update={attr_name: new_value})
        assert not generic_resource.check_if_operationally_equal(curr_test_copy)
        assert not curr_test_copy.check_if_operationally_equal(generic_resource)

    def test_results_reporting(self, make_component_with_block_copy):
        super().test_results_reporting(make_component_with_block_copy)
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        assert block.power_input.doc == "Power Input (MW)"
        assert block.power_output_max.doc == "Power Output Upper Bound (MW)"
        assert block.power_output_min.doc == "Power Output Lower Bound (MW)"
        assert block.power_input_max.doc == "Power Input Upper Bound (MW)"
        assert block.power_input_min.doc == "Power Input Lower Bound (MW)"
        assert block.power_input_annual.doc == "Annual Power Input (MWh)"
        assert block.power_input_variable_cost.doc == "Power Input Variable Cost ($)"
        assert block.annual_power_input_variable_cost.doc == "Annual Power Input Variable Cost ($)"
        assert block.planned_storage_capacity.doc == "Planned Storage Capacity (MWh)"
        assert block.selected_storage_capacity.doc == "Selected Storage Capacity (MWh)"
        assert block.retired_storage_capacity.doc == "Retired Storage Capacity (MWh)"
        assert block.operational_storage_capacity.doc == "Operational Storage Capacity (MWh)"
        assert block.annual_storage_capital_cost.doc == "Annual Storage Capacity Capital Cost ($)"
        assert block.annual_storage_fixed_om_cost.doc == "Annual Storage Capacity Fixed O&M Cost ($)"
        assert block.annual_total_investment_cost.doc == "Annual Total Investment Cost ($)"
        assert block.soc_inter_intra_joint.doc == "SOC Inter-Intra Joint (MWh)"
        assert block.soc_intra_period.doc == "SOC Intra Period (MWh)"

    def test_save_operational_storage_capacity(self, make_component_with_block_copy):
        storage_resource = make_component_with_block_copy()
        block = storage_resource.formulation_block
        modeled_years = list(block.model().MODELED_YEARS)

        block.operational_storage_capacity[:] = 10
        storage_resource.save_operational_storage_capacity()

        assert (storage_resource.operational_storage_capacity.data == pd.Series(index=modeled_years, data=10)).all()

    def test_save_selected_storage_capacity(self, make_component_with_block_copy):
        storage_resource = make_component_with_block_copy()
        block = storage_resource.formulation_block

        block.selected_storage_capacity = 10
        storage_resource.save_selected_storage_capacity()

        assert storage_resource.selected_storage_capacity == 10

    def test_save_retired_storage_capacity(self, make_component_with_block_copy):
        storage_resource = make_component_with_block_copy()
        block = storage_resource.formulation_block
        modeled_years = list(block.model().MODELED_YEARS)

        block.retired_storage_capacity[:] = 10
        storage_resource.save_retired_storage_capacity()

        assert (storage_resource.retired_storage_capacity.data == pd.Series(index=modeled_years, data=10)).all()

    def test_save_cumulative_retired_storage_capacity(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        modeled_years = list(block.model().MODELED_YEARS)

        block.retired_storage_capacity[:] = 10
        asset.save_cumulative_retired_storage_capacity()

        cumulative_value = 0
        for year in modeled_years:
            cumulative_value += 10
            assert asset.cumulative_retired_storage_capacity.data.at[year] == cumulative_value

    def test_prod_sim_selected_storage_capacity_constraint(self, make_component_with_block_copy_production_simulation):
        # All selected, retired, and operational capacities are set to zero
        asset = make_component_with_block_copy_production_simulation()
        block = asset.formulation_block

        # Constraint is valid
        assert block.prod_sim_selected_storage_capacity_constraint.upper() == 0
        assert block.prod_sim_selected_storage_capacity_constraint.lower() == 0
        block.selected_storage_capacity = 0
        assert block.prod_sim_selected_storage_capacity_constraint.expr()

        # Constraint is violated
        block.selected_storage_capacity = 4
        assert not block.prod_sim_selected_storage_capacity_constraint.expr()

    def test_prod_sim_retired_storage_capacity_constraint(
        self, make_component_with_block_copy_production_simulation, first_index
    ):
        # All selected, retired, and operational capacities are set to zero
        storage_resource = make_component_with_block_copy_production_simulation()
        block = storage_resource.formulation_block
        first_year = first_index[0]

        # Constraint is valid
        assert block.prod_sim_retired_storage_capacity_constraint[first_year].upper() == 0
        assert block.prod_sim_retired_storage_capacity_constraint[first_year].lower() == 0
        block.retired_storage_capacity[first_year] = 0
        assert block.prod_sim_retired_storage_capacity_constraint[first_year].expr()

        # Constraint is violated
        block.retired_storage_capacity[first_year] = 4
        assert not block.prod_sim_retired_storage_capacity_constraint[first_year].expr()

    def test_prod_sim_operational_storage_capacity_constraint(
        self, make_component_with_block_copy_production_simulation, first_index
    ):
        # All selected, retired, and operational capacities are set to zero
        asset = make_component_with_block_copy_production_simulation()
        block = asset.formulation_block
        first_year = first_index[0]

        # Constraint is valid
        assert block.prod_sim_operational_storage_capacity_constraint[first_year].upper() == 0
        assert block.prod_sim_operational_storage_capacity_constraint[first_year].lower() == 0
        block.operational_storage_capacity[first_year] = 0
        assert block.prod_sim_operational_storage_capacity_constraint[first_year].expr()

        # Constraint is violated
        block.operational_storage_capacity[first_year] = 4
        assert not block.prod_sim_operational_storage_capacity_constraint[first_year].expr()

    def test_erm_net_power_output(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index_erm,
    ):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        block.erm_power_output[first_index_erm] = 100.0
        block.erm_power_input[first_index_erm] = 50.0
        assert block.erm_net_power_output[first_index_erm].expr() == 50.0  # 100.0 - 50.0

    def test_erm_charging_efficiency(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index_erm,
    ):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        _, _, weather_timestamp = first_index_erm
        assert asset.charging_efficiency.data.at[weather_timestamp] == 0.85
        assert block.erm_charging_efficiency[weather_timestamp].expr() == 0.85

    def test_erm_discharging_efficiency(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index_erm,
    ):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        _, _, weather_timestamp = first_index_erm
        assert asset.discharging_efficiency.data.at[weather_timestamp] == 0.9
        assert block.erm_discharging_efficiency[weather_timestamp].expr() == 0.9

    def test_erm_power_output_max_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        modeled_year, _, weather_timestamp = first_index_erm
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block

        block.erm_power_output[first_index_erm] = 45.0
        block.operational_capacity[modeled_year] = 100.0

        # Asserting this so that future readers can understand the calculations below
        assert asset.pmax_profile[weather_timestamp] == 0.5

        assert block.erm_power_output_max_constraint[first_index_erm].upper() == 0.0
        assert block.erm_power_output_max_constraint[first_index_erm].body() == -5.0
        assert block.erm_power_output_max_constraint[first_index_erm].expr()

        block.erm_power_output[first_index_erm] = 55.0
        assert block.erm_power_output_max_constraint[first_index_erm].upper() == 0.0
        assert block.erm_power_output_max_constraint[first_index_erm].body() == 5.0
        assert not block.erm_power_output_max_constraint[first_index_erm].expr()

        block.erm_power_output[first_index_erm] = 50.0
        assert block.erm_power_output_max_constraint[first_index_erm].upper() == 0.0
        assert block.erm_power_output_max_constraint[first_index_erm].body() == 0.0
        assert block.erm_power_output_max_constraint[first_index_erm].expr()

    def test_erm_power_input_max_constraint(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        modeled_year, _, weather_timestamp = first_index_erm
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block

        # Constraint is:
        # block.erm_power_input[modeled_year, weather_period, weather_timestamp]
        # <= block.operational_capacity[modeled_year] * self.imax_profile.at[weather_timestamp]

        block.erm_power_input[first_index_erm] = 45.0
        block.operational_capacity[modeled_year] = 100.0

        # Asserting this so that future readers can understand the calculations below
        assert asset.pmax_profile[weather_timestamp] == 0.5

        assert block.erm_power_input_max_constraint[first_index_erm].upper() == 0.0
        assert block.erm_power_input_max_constraint[first_index_erm].body() == -5.0
        assert block.erm_power_input_max_constraint[first_index_erm].expr()

        block.erm_power_input[first_index_erm] = 55.0
        assert block.erm_power_input_max_constraint[first_index_erm].upper() == 0.0
        assert block.erm_power_input_max_constraint[first_index_erm].body() == 5.0
        assert not block.erm_power_input_max_constraint[first_index_erm].expr()

        block.erm_power_input[first_index_erm] = 50.0
        assert block.erm_power_input_max_constraint[first_index_erm].upper() == 0.0
        assert block.erm_power_input_max_constraint[first_index_erm].body() == 0.0
        assert block.erm_power_input_max_constraint[first_index_erm].expr()

    def test_erm_soc_tracking_constraint(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        modeled_year, weather_period, weather_timestamp = first_index_erm
        asset = make_component_with_block_copy_inter_period_sharing()

        block = asset.formulation_block

        # constraint:
        # block.erm_state_of_charge[modeled_year, next_hour]
        # == block.erm_state_of_charge[modeled_year, weather_period, weather_timestamp]
        # + block.erm_power_input[modeled_year, weather_period, weather_timestamp] * self.charging_efficiency.data.at[weather_timestamp]
        # - block.erm_power_output[modeled_year, weather_period, weather_timestamp] / self.discharging_efficiency.data.at[weather_timestamp]

        next_hour = block.model().WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS.nextw((weather_period, weather_timestamp))

        # Simple charge-only case
        block.erm_power_input[first_index_erm].fix(10.0)
        block.erm_power_output[first_index_erm].fix(0.0)
        block.erm_state_of_charge[first_index_erm].fix(50.0)
        block.erm_state_of_charge[modeled_year, next_hour].fix(58.5)
        # Charging efficiency is 0.85 in pytest fixture
        assert block.erm_soc_tracking_constraint[first_index_erm].body() == 0.0

        # Simple discharge-only case
        block.erm_power_input[first_index_erm].fix(0.0)
        block.erm_power_output[first_index_erm].fix(10.0)
        block.erm_state_of_charge[first_index_erm].fix(50.0)
        block.erm_state_of_charge[modeled_year, next_hour].fix(50.0 - (10.0 / 0.9))
        # Discharging efficiency is 0.9 in pytest fixture
        assert block.erm_soc_tracking_constraint[first_index_erm].body() == 0.0

        # Charge > discharge
        block.erm_power_input[first_index_erm].fix(5.0)
        block.erm_power_output[first_index_erm].fix(10.0)
        block.erm_state_of_charge[first_index_erm].fix(50.0)
        block.erm_state_of_charge[modeled_year, next_hour].fix(50.0 + (5.0 * 0.85) - (10.0 / 0.9))
        assert block.erm_soc_tracking_constraint[first_index_erm].body() == 0.0

        # Charge > discharge
        block.erm_power_input[first_index_erm].fix(10.0)
        block.erm_power_output[first_index_erm].fix(5.0)
        block.erm_state_of_charge[first_index_erm].fix(50.0)
        block.erm_state_of_charge[modeled_year, next_hour].fix(50.0 + (10.0 * 0.85) - (5.0 / 0.9))
        assert block.erm_soc_tracking_constraint[first_index_erm].body() == 0.0

    def test_erm_dispatch_cost(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        assert block.erm_dispatch_cost_per_MWh.value == -0.001

        # Expression is:
        # block.erm_dispatch_cost_per_MWh * block.erm_net_power_output[modeled_year, weather_period, weather_timestamp]
        # and erm_net_power_output is the erm_power_output - erm_power_input

        block.erm_power_output[first_index_erm].fix(10.0)
        block.erm_power_input[first_index_erm].fix(5.0)
        assert block.erm_dispatch_cost[first_index_erm].expr() == -0.005

        block.erm_power_output[first_index_erm].fix(5.0)
        block.erm_power_input[first_index_erm].fix(10.0)
        assert block.erm_dispatch_cost[first_index_erm].expr() == 0.005

    def test_erm_annual_dispatch_cost(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        asset = make_component_with_block_copy_inter_period_sharing()
        block = asset.formulation_block
        NUM_HOURS_PER_DAY = 24
        assert block.erm_dispatch_cost_per_MWh.value == -0.001

        first_modeled_year = pd.Timestamp("2025-01-01")
        block.erm_dispatch_cost[first_modeled_year, :, :] = 1.5
        num_days_per_year = block.model().num_days_per_modeled_year[first_modeled_year]
        assert block.erm_annual_dispatch_cost[first_modeled_year].expr() == 1.5 * num_days_per_year * NUM_HOURS_PER_DAY

        second_modeled_year = pd.Timestamp("2030-01-01")
        block.erm_dispatch_cost[second_modeled_year, :, :] = 2.5
        num_days_per_year = block.model().num_days_per_modeled_year[second_modeled_year]
        assert block.erm_annual_dispatch_cost[second_modeled_year].expr() == 2.5 * num_days_per_year * NUM_HOURS_PER_DAY


class TestStorageResourceGroup(test_generic.TestGenericResourceGroup, TestStorageResource):
    _COMPONENT_CLASS = StorageResourceGroup
    _COMPONENT_NAME = "storage_resource_group_0"
    _SYSTEM_COMPONENT_DICT_NAME = "storage_resource_groups"

    @pytest.fixture(scope="class")
    def make_component_with_block_copy_inter_period_sharing(
        self, test_model_with_operational_groups_inter_period_sharing
    ):
        def _make_copy_with_block():
            return copy.deepcopy(
                getattr(
                    test_model_with_operational_groups_inter_period_sharing.system, self._SYSTEM_COMPONENT_DICT_NAME
                )[self._COMPONENT_NAME]
            )

        return _make_copy_with_block

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_storage_capacity_duration_constraint_fixed(self, make_component_with_block_copy, first_index):
        super().test_storage_capacity_duration_constraint_fixed(make_component_with_block_copy, first_index)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_storage_capacity_duration_constraint_minimum(self, make_custom_component_with_block, first_index):
        super().test_storage_capacity_duration_constraint_minimum(make_custom_component_with_block, first_index)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_storage_capacity_duration_constraint_maximum(self, make_custom_component_with_block, first_index):
        super().test_storage_capacity_duration_constraint_maximum(make_custom_component_with_block, first_index)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_retired_storage_capacity_max_constraint_can_retire(self, make_component_with_block_copy, first_index):
        super().test_retired_storage_capacity_max_constraint_can_retire(make_component_with_block_copy, first_index)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_retired_storage_capacity_max_constraint_cannot_retire(self, make_custom_component_with_block, first_index):
        super().test_retired_storage_capacity_max_constraint_cannot_retire(
            make_custom_component_with_block, first_index
        )

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_retired_storage_capacity_max_constraint_cannot_retire_no_lifetime(
        self, make_custom_component_with_block, first_index
    ):
        super().test_retired_storage_capacity_max_constraint_cannot_retire_no_lifetime(
            make_custom_component_with_block, first_index
        )

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_storage_physical_lifetime_constraint(self, make_component_with_block_copy, last_modeled_year):
        super().test_storage_physical_lifetime_constraint(make_component_with_block_copy, last_modeled_year)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_reliability_capacity_duration_constraint(self, make_component_with_block_copy, last_modeled_year):
        super().test_reliability_capacity_duration_constraint(make_component_with_block_copy, last_modeled_year)

    def test_results_reporting(self, make_component_with_block_copy):
        super().test_results_reporting(make_component_with_block_copy)
        resource_group = make_component_with_block_copy()
        block = resource_group.formulation_block

        assert block.power_input_max.doc == "Power Input Upper Bound (MW)"
        assert block.power_input_min.doc == "Power Input Lower Bound (MW)"
        assert block.total_up_reserves_by_timepoint.doc == "Total Up Reserves (MW)"
        assert block.total_down_reserves_by_timepoint.doc == "Total Down Reserves (MW)"
        assert block.power_input_annual.doc == "Annual Power Input (MWh)"
        assert block.power_input_variable_cost.doc == "Power Input Variable Cost ($)"
        assert block.annual_power_input_variable_cost.doc == "Annual Power Input Variable Cost ($)"

    def test_operational_storage_capacity(self, make_component_with_block_copy):
        resource_group = make_component_with_block_copy()
        block = resource_group.formulation_block
        original_build_asset = [r for r in list(resource_group.build_assets.keys()) if "_copy" not in r][0]

        resource_group.build_assets[original_build_asset].formulation_block.operational_storage_capacity[
            pd.Timestamp("2025-01-01")
        ] = 10
        resource_group.build_assets[f"{original_build_asset}_copy"].formulation_block.operational_storage_capacity[
            pd.Timestamp("2025-01-01")
        ] = 10
        resource_group.formulation_block.operational_storage_capacity[pd.Timestamp("2025-01-01")] = 20
        assert block.group_operational_storage_capacity_constraint[pd.Timestamp("2025-01-01")].expr()

        resource_group.build_assets[original_build_asset].formulation_block.operational_storage_capacity[
            pd.Timestamp("2030-01-01")
        ] = 20
        resource_group.build_assets[f"{original_build_asset}_copy"].formulation_block.operational_storage_capacity[
            pd.Timestamp("2030-01-01")
        ] = 25
        resource_group.formulation_block.operational_storage_capacity[pd.Timestamp("2030-01-01")] = 45
        assert block.group_operational_storage_capacity_constraint[pd.Timestamp("2030-01-01")].expr()

        resource_group.formulation_block.operational_storage_capacity[pd.Timestamp("2030-01-01")] = 40
        assert not block.group_operational_storage_capacity_constraint[pd.Timestamp("2030-01-01")].expr()

    def test_cumulative_selected_storage_capacity(self, make_component_with_block_copy):
        resource_group = make_component_with_block_copy()
        block = resource_group.formulation_block
        original_build_asset = [r for r in list(resource_group.build_assets.keys()) if "_copy" not in r][0]

        resource_group.build_assets[original_build_asset].formulation_block.selected_storage_capacity = 50
        resource_group.build_assets[f"{original_build_asset}_copy"].formulation_block.selected_storage_capacity = 50
        for year in [
            pd.Timestamp("2025-01-01"),
            pd.Timestamp("2030-01-01"),
            pd.Timestamp("2035-01-01"),
            pd.Timestamp("2045-01-01"),
        ]:
            assert block.cumulative_selected_storage_capacity[year].expr() == 100

    def test_selected_storage_capacity(self, make_component_with_block_copy):
        resource_group = make_component_with_block_copy()
        block = resource_group.formulation_block
        original_build_asset = [r for r in list(resource_group.build_assets.keys()) if "_copy" not in r][0]

        resource_group.build_assets[original_build_asset].formulation_block.selected_storage_capacity = 50
        resource_group.build_assets[f"{original_build_asset}_copy"].formulation_block.selected_storage_capacity = 50
        assert block.selected_storage_capacity[pd.Timestamp("2025-01-01")].expr() == 100

        for year in [
            pd.Timestamp("2030-01-01"),
            pd.Timestamp("2035-01-01"),
            pd.Timestamp("2045-01-01"),
        ]:
            assert block.selected_storage_capacity[year].expr() == 0

    def test_retired_storage_capacity(self, make_component_with_block_copy):
        resource_group = make_component_with_block_copy()
        block = resource_group.formulation_block
        original_build_asset = [r for r in list(resource_group.build_assets.keys()) if "_copy" not in r][0]

        resource_group.build_assets[original_build_asset].formulation_block.retired_storage_capacity[
            pd.Timestamp("2025-01-01")
        ] = 100
        resource_group.build_assets[f"{original_build_asset}_copy"].formulation_block.retired_storage_capacity[
            pd.Timestamp("2025-01-01")
        ] = 50
        assert block.retired_storage_capacity[pd.Timestamp("2025-01-01")].expr() == 150

        resource_group.build_assets[original_build_asset].formulation_block.retired_storage_capacity[
            pd.Timestamp("2045-01-01")
        ] = 30
        resource_group.build_assets[f"{original_build_asset}_copy"].formulation_block.retired_storage_capacity[
            pd.Timestamp("2045-01-01")
        ] = 30
        assert block.retired_storage_capacity[pd.Timestamp("2045-01-01")].expr() == 60

    def test_cumulative_retired_storage_capacity(self, make_component_with_block_copy):
        resource_group = make_component_with_block_copy()
        block = resource_group.formulation_block

        block.retired_storage_capacity[pd.Timestamp("2025-01-01")] = 50
        block.retired_storage_capacity[pd.Timestamp("2030-01-01")] = 75
        block.retired_storage_capacity[pd.Timestamp("2035-01-01")] = 100
        block.retired_storage_capacity[pd.Timestamp("2045-01-01")] = 25

        assert block.cumulative_retired_storage_capacity[pd.Timestamp("2025-01-01")].expr() == 50
        assert block.cumulative_retired_storage_capacity[pd.Timestamp("2030-01-01")].expr() == 125
        assert block.cumulative_retired_storage_capacity[pd.Timestamp("2035-01-01")].expr() == 225
        assert block.cumulative_retired_storage_capacity[pd.Timestamp("2045-01-01")].expr() == 250

    def test_erm_charging_efficiency(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index_erm,
    ):
        resource_group = make_component_with_block_copy_inter_period_sharing()
        block = resource_group.formulation_block
        _, _, weather_timestamp = first_index_erm
        assert (
            block.erm_charging_efficiency[weather_timestamp].expr()
            == sum(
                resource.charging_efficiency.data.at[weather_timestamp]
                for resource in resource_group.build_assets.values()
            )
            / len(resource_group.build_assets)
            == 0.85
        )

    def test_erm_discharging_efficiency(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index_erm,
    ):
        resource_group = make_component_with_block_copy_inter_period_sharing()
        block = resource_group.formulation_block
        _, _, weather_timestamp = first_index_erm
        assert (
            block.erm_discharging_efficiency[weather_timestamp].expr()
            == sum(
                resource.discharging_efficiency.data.at[weather_timestamp]
                for resource in resource_group.build_assets.values()
            )
            / len(resource_group.build_assets)
            == 0.9
        )

    @pytest.mark.skip(reason=("Selected capacities are not saved for AssetGroups."))
    def test_save_selected_storage_capacity(self, make_component_with_block_copy_production_simulation):
        pass

    @pytest.mark.skip(reason=("Operational capacities are not saved for AssetGroups."))
    def test_save_operational_storage_capacity(self, make_component_with_block_copy):
        pass

    @pytest.mark.skip(reason=("Retired capacities are not saved for AssetGroups."))
    def test_save_retired_storage_capacity(self, make_component_with_block_copy):
        pass

    @pytest.mark.skip(reason=("Retired capacities are not saved for AssetGroups."))
    def test_save_cumulative_retired_storage_capacity(self, make_component_with_block_copy):
        pass

    @pytest.mark.skip(reason=("Production Simulation constraints only apply to individual assets, not their groups."))
    def test_prod_sim_selected_storage_capacity_constraint(self, make_component_with_block_copy_production_simulation):
        """Production Simulation constraints only apply to individual assets, not their groups."""
        super().test_prod_sim_selected_storage_capacity_constraint(make_component_with_block_copy_production_simulation)

    @pytest.mark.skip(reason=("Production Simulation constraints only apply to individual assets, not their groups."))
    def test_prod_sim_retired_storage_capacity_constraint(self, make_component_with_block_copy_production_simulation):
        """Production Simulation constraints only apply to individual assets, not their groups."""
        super().test_prod_sim_retired_storage_capacity_constraint(make_component_with_block_copy_production_simulation)

    @pytest.mark.skip(reason=("Production Simulation constraints only apply to individual assets, not their groups."))
    def test_prod_sim_operational_storage_capacity_constraint(
        self, make_component_with_block_copy_production_simulation
    ):
        """Production Simulation constraints only apply to individual assets, not their groups."""
        super().test_prod_sim_operational_storage_capacity_constraint(
            make_component_with_block_copy_production_simulation
        )
