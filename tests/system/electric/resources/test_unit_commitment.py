import copy

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.system.electric.resources import UnitCommitmentResource
from new_modeling_toolkit.system.electric.resources.unit_commitment import UnitCommitmentResourceGroup
from tests.system.electric.resources import test_generic
from tests.system.electric.resources.test_generic import TestGenericResourceGroup


class TestUnitCommitmentResource(test_generic.TestGenericResource):
    """This class holds tests for UnitCommitmentResource functionality, but these tests cannot be run directly because
    UnitCommitmentResource is an abstract class. However, the test classes for all classes that inherit from
    UnitCommitmentResource should also inherit from this class, so that the tests will be run."""

    _COMPONENT_CLASS = UnitCommitmentResource
    _COMPONENT_NAME = "Does Not Exist"
    _SYSTEM_COMPONENT_DICT_NAME = "unit_commitment_resources"

    @pytest.fixture(scope="class")
    def test_model_initial_condition(self, test_temporal_settings, test_system):
        # change edge effects so constraint will activate
        test_temporal_settings.dispatch_window_edge_effects = DispatchWindowEdgeEffects.FIXED_INITIAL_CONDITION
        test_model = ModelTemplate(
            system=test_system,
            temporal_settings=test_temporal_settings,
            construct_investment_rules=True,
            construct_operational_rules=True,
            construct_costs=True,
        )

        return test_model

    @pytest.fixture(scope="class")
    def resource_with_fixed_initial_constraints(self, test_model_initial_condition):
        def _make_copy_with_block():
            return copy.deepcopy(
                getattr(test_model_initial_condition.system, self._SYSTEM_COMPONENT_DICT_NAME)[self._COMPONENT_NAME]
            )

        return _make_copy_with_block

    @pytest.fixture(scope="class")
    def first_inter_index(self, test_model_inter_period_sharing):
        modeled_year = test_model_inter_period_sharing.MODELED_YEARS.first()
        first_chrono_period = test_model_inter_period_sharing.CHRONO_PERIODS.first()
        dispatch_window = test_model_inter_period_sharing.chrono_periods_map[first_chrono_period]
        timestamp = test_model_inter_period_sharing.first_timepoint_in_dispatch_window[dispatch_window]

        return modeled_year, dispatch_window, timestamp

    @pytest.fixture(scope="class")
    def last_inter_index(self, test_model_inter_period_sharing):
        modeled_year = test_model_inter_period_sharing.MODELED_YEARS.first()
        last_chrono_period = test_model_inter_period_sharing.CHRONO_PERIODS.last()
        dispatch_window = test_model_inter_period_sharing.chrono_periods_map[last_chrono_period]
        timestamp = test_model_inter_period_sharing.last_timepoint_in_dispatch_window[dispatch_window]

        return modeled_year, dispatch_window, timestamp

    def test_check_potential_required_validator(self, test_thermal_unit_commitment_resource):
        """
        Test that the `check_potential_required` validator enforces correct behavior
        when `unit_commitment_mode` is set to 'single_unit'.

        This test covers two cases:
        1. When `unit_commitment_mode='single_unit'` and `potential` is defined
           (valid input) → the model should build successfully.
        2. When `unit_commitment_mode='single_unit'` and `potential=None`
           (invalid input) → the model should raise a `ValueError` with the expected message.

        The validator ensures that resources using the 'single_unit' commitment
        formulation always have a valid `potential` value specified.
        """
        init_kwargs = test_thermal_unit_commitment_resource.model_dump()
        init_kwargs.update(
            unit_commitment_mode="single_unit",
        )
        UnitCommitmentResource(**init_kwargs)  # check that it passes build

        init_kwargs.update(potential=None)
        with pytest.raises(ValueError, match="Potential required for unit commitment"):
            UnitCommitmentResource(**init_kwargs)  # check that it fails build

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
        ]

    def test_operational_units_in_timepoint(self, make_component_with_block_copy, first_index):
        """
        Test return number of units
        """
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        resource_block.operational_capacity[first_index[0]] = 100
        operational_units = resource_block.operational_units_in_timepoint[first_index]
        assert operational_units.expr() == 2.0

    @pytest.mark.parametrize(
        "committed_units, provide_power_capacity",
        [
            (0, 0),
            (1, 50.0),
            (2, 100.0),
        ],
    )
    def test_power_output_max(
        self, make_component_with_block_copy, first_index, committed_units, provide_power_capacity
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        resource_block.committed_units[first_index].fix(committed_units)
        assert resource_block.power_output_max[first_index].expr() == provide_power_capacity

    @pytest.mark.parametrize(
        "committed_units, provide_power_min_capacity",
        [
            (0, 0),
            (1, 25.0),
            (2, 50.0),
        ],
    )
    def test_power_output_min(
        self, make_component_with_block_copy, first_index, committed_units, provide_power_min_capacity
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        resource_block.committed_units[first_index].fix(committed_units)
        assert resource_block.power_output_min[first_index].expr() == provide_power_min_capacity

    @pytest.mark.skip  # skipping for resolve, fix for recap
    def test_initial_committed_units(self, resource_with_fixed_initial_constraints, first_index):
        resource = copy.deepcopy(resource_with_fixed_initial_constraints())
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.committed_units[first_index].fix(0)

        assert resource_block.initial_committed_units[(modeled_year, dispatch_window)].upper() == 0
        assert resource_block.initial_committed_units[(modeled_year, dispatch_window)].lower() == 0
        assert resource_block.initial_committed_units[(modeled_year, dispatch_window)].body() == 0
        assert resource_block.initial_committed_units[(modeled_year, dispatch_window)].expr()

        resource_block.committed_units[first_index].fix(1)
        assert not resource_block.initial_committed_units[(modeled_year, dispatch_window)].expr()

    @pytest.mark.skip  # skipping for resolve, fix for recap
    def test_initial_start_units(self, test_model_initial_condition, first_index):
        resource = copy.deepcopy(test_model_initial_condition)
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.start_units[first_index].fix(0)
        assert resource_block.zero_start_units_in_first_timepoint[(modeled_year, dispatch_window)].upper() == 0
        assert resource_block.zero_start_units_in_first_timepoint[(modeled_year, dispatch_window)].lower() == 0
        assert resource_block.zero_start_units_in_first_timepoint[(modeled_year, dispatch_window)].body() == 0
        assert resource_block.zero_start_units_in_first_timepoint[(modeled_year, dispatch_window)].expr()

        resource_block.start_units[first_index].fix(1)
        assert not resource_block.zero_start_units_in_first_timepoint[(modeled_year, dispatch_window)].expr()

    @pytest.mark.skip  # skipping for resolve, fix for recap
    def test_initial_committed_units_in_last_timepoint(self, test_model_initial_condition, last_index):
        resource = copy.deepcopy(test_model_initial_condition)
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = last_index

        resource_block.committed_units[last_index].fix(0)

        assert resource_block.zero_committed_units_in_last_timepoint[(modeled_year, dispatch_window)].upper() == 0
        assert resource_block.zero_committed_units_in_last_timepoint[(modeled_year, dispatch_window)].lower() == 0
        assert resource_block.zero_committed_units_in_last_timepoint[(modeled_year, dispatch_window)].body() == 0
        assert resource_block.zero_committed_units_in_last_timepoint[(modeled_year, dispatch_window)].expr()

        resource_block.committed_units[last_index].fix(1)
        assert not resource_block.zero_committed_units_in_last_timepoint[(modeled_year, dispatch_window)].expr()

    @pytest.mark.parametrize(
        "power_output, expected_body, expected_expr",
        [
            # Case 1: committed capacity = 160 → minimum requirement = 16
            # body = 0.5 * 160 - 100 = -84 → inequality violated → expr() is True
            pytest.param(160.0, 160 * 0.5 - 100, True, id="output_above_min"),
            # Case 2: committed capacity = 3000 → minimum requirement = 300
            # body = 0.5 * 3000 - 100 = 200 → inequality satisfied → expr() is False
            pytest.param(3000.0, 0.5 * 3000 - 100, False, id="output_below_min"),
            # Case 3: committed capacity = 1000 → minimum requirement = 100
            # body = 0.5 * 200 - 100 = 0 → binding case → expr() is True
            pytest.param(200.0, 0.5 * 200 - 100, True, id="output_exact_min"),
        ],
    )
    def test_power_output_min_constraint(
        self, make_component_with_block_copy, first_index, power_output, expected_body, expected_expr
    ):
        """
        Verify that power_output_min_constraint enforces the minimum operating
        requirement correctly across different committed_capacity_mw_power_output values.
        """

        # Build resource and get its formulation block
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        # Unpack test index (modeled_year, dispatch_window_id, timestamp)
        modeled_year, dispatch_window_id, timestamp = first_index

        # Planned capacity should equal 100 (fixture setup assumption)
        assert resource.planned_capacity.data.at[modeled_year] == 100

        # Set committed capacity (Var or Expression) and fix power output at 100
        block.committed_capacity[modeled_year, dispatch_window_id, timestamp] = power_output
        block.power_output[modeled_year, dispatch_window_id, timestamp] = 100

        # Constraint is always enforced as ≤ 0
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0

        # Body should equal 0.1 * committed_capacity - power_output
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == expected_body

        # expr() evaluates whether the inequality is violated (True) or satisfied (False)
        assert (
            bool(block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()) == expected_expr
        )

    def test_power_output_max_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        block.committed_units.fix(4)

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

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        assert block.power_output_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == -200
        assert block.power_output_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_output_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

    def test_total_up_reserves_max_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        block.operational_capacity[modeled_year] = 200
        block.committed_units.fix(4)

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
        block.committed_units.fix(4)

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

    @pytest.mark.parametrize(
        "committed_units, committed_units_ub_body, committed_units_ub_upper, expr",
        [
            (1, -1, 0.0, True),
            (2, 0, 0.0, True),
            (3, 1, 0.0, False),
        ],
    )
    def test_committed_units_ub_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units,
        committed_units_ub_body,
        committed_units_ub_upper,
        expr,
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        resource_block.operational_capacity[first_index[0]] = 100

        resource_block.committed_units[first_index].fix(committed_units)
        assert resource_block.committed_units_ub_constraint[first_index].upper() == committed_units_ub_upper
        assert resource_block.committed_units_ub_constraint[first_index].body() == committed_units_ub_body
        assert resource_block.committed_units_ub_constraint[first_index].expr() == expr

    @pytest.mark.parametrize(
        "start_units, start_units_ub_body, start_units_ub_upper, expr",
        [
            (1, -1, 0.0, True),
            (2, 0, 0.0, True),
            (3, 1, 0.0, False),
        ],
    )
    def test_start_units_ub_constraint(
        self, make_component_with_block_copy, first_index, start_units, start_units_ub_body, start_units_ub_upper, expr
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        resource_block.operational_capacity[first_index[0]] = 100

        resource_block.start_units[first_index].fix(start_units)
        assert resource_block.start_units_ub_constraint[first_index].upper() == start_units_ub_upper
        assert resource_block.start_units_ub_constraint[first_index].body() == start_units_ub_body
        assert resource_block.start_units_ub_constraint[first_index].expr() == expr

    @pytest.mark.parametrize(
        "shutdown_units, shutdown_units_ub_body, shutdown_units_ub_upper, expr",
        [
            (1, -1, 0.0, True),
            (2, 0, 0.0, True),
            (3, 1, 0.0, False),
        ],
    )
    def test_shutdown_units_ub_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        shutdown_units,
        shutdown_units_ub_body,
        shutdown_units_ub_upper,
        expr,
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        resource_block.operational_capacity[first_index[0]] = 100

        resource_block.shutdown_units[first_index].fix(shutdown_units)
        assert resource_block.shutdown_units_ub_constraint[first_index].upper() == shutdown_units_ub_upper
        assert resource_block.shutdown_units_ub_constraint[first_index].body() == shutdown_units_ub_body
        assert resource_block.shutdown_units_ub_constraint[first_index].expr() == expr

    @pytest.mark.parametrize(
        "committed_units_first, committed_units_next, start_units_next, shutdown_units_next, commitment_tracking_upper, commitment_tracking_lower, commitment_tracking_body, expr",
        [
            (0, 0, 1, 0, 0.0, 0.0, -1.0, False),
            (0, 1, 1, 0, 0.0, 0.0, 0.0, True),
            (0, 0, 1, 1, 0.0, 0.0, 0.0, True),
            (1, 1, 0, 0, 0.0, 0.0, 0.0, True),
            (1, 0, 0, 1, 0.0, 0.0, 0.0, True),
            (1, 1, 1, 1, 0.0, 0.0, 0.0, True),
            (0, 1, 1, 1, 0.0, 0.0, 1.0, False),
        ],
    )
    def test_commitment_tracking_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units_first,
        committed_units_next,
        start_units_next,
        shutdown_units_next,
        commitment_tracking_upper,
        commitment_tracking_lower,
        commitment_tracking_body,
        expr,
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        next_index = (modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=1))
        resource_block.committed_units[first_index].fix(committed_units_first)
        resource_block.committed_units[next_index].fix(committed_units_next)
        resource_block.start_units[next_index].fix(start_units_next)
        resource_block.shutdown_units[next_index].fix(shutdown_units_next)
        assert resource_block.commitment_tracking_constraint[first_index].upper() == commitment_tracking_upper
        assert resource_block.commitment_tracking_constraint[first_index].lower() == commitment_tracking_lower
        assert resource_block.commitment_tracking_constraint[first_index].body() == commitment_tracking_body
        assert resource_block.commitment_tracking_constraint[first_index].expr() == expr

    @pytest.mark.parametrize(
        "committed_units, start_unit_0, start_unit_1, start_unit_2, min_up_upper, min_up_body, expr",
        [
            (2, 0, 1, 1, 0.0, 0.0, True),
            (1, 0, 1, 0, 0.0, 0.0, True),
            (3, 1, 1, 0, 0.0, -1.0, True),
            (1, 0, 1, 1, 0.0, 1.0, False),
        ],
    )
    def test_min_uptime_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units,
        start_unit_0,
        start_unit_1,
        start_unit_2,
        min_up_upper,
        min_up_body,
        expr,
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        timestamp = timestamp + pd.DateOffset(hours=2)
        first_index = (modeled_year, dispatch_window, timestamp)

        resource_block.committed_units[first_index].fix(committed_units)
        resource_block.start_units[modeled_year, dispatch_window, timestamp].fix(start_unit_0)
        resource_block.start_units[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=1)].fix(start_unit_1)
        resource_block.start_units[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=2)].fix(start_unit_2)
        assert resource_block.min_uptime_constraint[first_index].upper() == min_up_upper
        assert resource_block.min_uptime_constraint[first_index].body() == min_up_body
        assert resource_block.min_uptime_constraint[first_index].expr() == expr

    @pytest.mark.parametrize(
        "committed_units, start_unit_3, start_unit_2, start_unit_1, start_unit_0, offset, min_up_upper, min_up_body, expr",
        [
            (2, 0, 1, 1, 0, 0, 0.0, 0.0, True),
            (1, 0, 1, 0, 0, 0, 0.0, 0.0, True),
            (3, 0, 1, 1, 0, 0, 0.0, -1.0, True),
            (1, 0, 1, 1, 0, 0, 0.0, 1.0, False),
            (1, 1, 1, 1, 1, 1, 0.0, 2.0, False),
            (3, 1, 1, 1, 1, 1, 0.0, 0.0, True),
            (1, 1, 1, 1, 1, 1, 0.0, 2.0, False),
        ],
    )
    def test_min_uptime_constraint_inter(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index,
        committed_units,
        start_unit_0,
        start_unit_1,
        start_unit_2,
        start_unit_3,
        offset,
        min_up_upper,
        min_up_body,
        expr,
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

        chrono_period_3_index = (
            modeled_year,
            next_dispatch_window,
            first_timestamp_next_chrono_period + pd.Timedelta(hours=1),
        )
        chrono_period_2_index = (modeled_year, next_dispatch_window, first_timestamp_next_chrono_period)
        chrono_period_1_index = (modeled_year, dispatch_window, last_timestamp_chrono_period)
        chrono_period_0_index = (modeled_year, dispatch_window, last_timestamp_chrono_period - pd.Timedelta(hours=1))
        # assert the first index of intra contraint was skipped because it would cross the dispatch window boundary
        with pytest.raises(KeyError):
            resource_block.min_uptime_constraint[first_index]

        resource_block.committed_units[
            modeled_year, next_dispatch_window, first_timestamp_next_chrono_period + pd.Timedelta(hours=offset)
        ].fix(committed_units)
        resource_block.start_units.fix(0)
        resource_block.start_units[chrono_period_3_index].fix(start_unit_3)
        resource_block.start_units[chrono_period_2_index].fix(start_unit_2)
        resource_block.start_units[chrono_period_1_index].fix(start_unit_1)
        resource_block.start_units[chrono_period_0_index].fix(start_unit_0)
        constraint_index = (modeled_year, next_chrono_period, offset)

        assert resource_block.min_uptime_constraint_inter[constraint_index].expr() == expr
        assert resource_block.min_uptime_constraint_inter[constraint_index].body() == min_up_body
        assert resource_block.min_uptime_constraint_inter[constraint_index].upper() == min_up_upper

    @pytest.mark.parametrize(
        "committed_units, shutdown_unit_0, shutdown_unit_1, shutdown_unit_2, min_down_upper, min_down_body, expr",
        [
            (2, 0, 1, 1, 0.0, 2.0, False),
            (1, 0, 1, 0, 0.0, 0.0, True),
            (0, 0, 1, 1, 0.0, 0.0, True),
            (2, 1, 1, 0, 0.0, 2.0, False),
        ],
    )
    def test_min_downtime_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units,
        shutdown_unit_0,
        shutdown_unit_1,
        shutdown_unit_2,
        min_down_upper,
        min_down_body,
        expr,
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        timestamp = timestamp + pd.DateOffset(hours=2)
        first_index = (modeled_year, dispatch_window, timestamp)

        resource_block.operational_capacity[modeled_year] = 100

        resource_block.committed_units[first_index].fix(committed_units)
        # operational will always be 0 or 1 for integer unit commitment
        resource_block.shutdown_units[modeled_year, dispatch_window, timestamp].fix(shutdown_unit_0)
        resource_block.shutdown_units[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=1)].fix(
            shutdown_unit_1
        )
        resource_block.shutdown_units[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=2)].fix(
            shutdown_unit_2
        )
        assert resource_block.min_downtime_constraint[first_index].upper() == min_down_upper
        assert resource_block.min_downtime_constraint[first_index].body() == min_down_body
        assert resource_block.min_downtime_constraint[first_index].expr() == expr

    @pytest.mark.parametrize(
        "committed_units, shutdown_unit_3, shutdown_unit_2, shutdown_unit_1, shutdown_unit_0, offset, min_down_upper, min_down_body, expr",
        [
            (1, 0, 3, 1, 0, 0, 0.0, 2.0, False),
            (2, 0, 0, 1, 0, 0, 0.0, 0.0, True),
            (3, 0, 0, 0, 1, 0, 0.0, 1.0, False),
            (0, 0, 1, 1, 0, 0, 0.0, -1.0, True),
            (1, 1, 1, 1, 1, 1, 0.0, 1.0, False),
            (0, 0, 2, 0, 0, 1, 0.0, -1.0, True),
            (1, 0, 2, 1, 0, 1, 0.0, 1.0, False),
        ],
    )
    def test_min_downtime_constraint_inter(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index,
        committed_units,
        shutdown_unit_3,
        shutdown_unit_2,
        shutdown_unit_1,
        shutdown_unit_0,
        offset,
        min_down_upper,
        min_down_body,
        expr,
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

        chrono_period_3_index = (
            modeled_year,
            next_dispatch_window,
            first_timestamp_next_chrono_period + pd.Timedelta(hours=1),
        )
        chrono_period_2_index = (modeled_year, next_dispatch_window, first_timestamp_next_chrono_period)
        chrono_period_1_index = (modeled_year, dispatch_window, last_timestamp_chrono_period)
        chrono_period_0_index = (modeled_year, dispatch_window, last_timestamp_chrono_period - pd.Timedelta(hours=1))
        # assert the first index of intra constraint was skipped because it would cross the dispatch window boundary
        with pytest.raises(KeyError):
            resource_block.min_downtime_constraint[first_index]

        resource_block.committed_units[
            modeled_year, next_dispatch_window, first_timestamp_next_chrono_period + pd.Timedelta(hours=offset)
        ].fix(committed_units)
        resource_block.shutdown_units.fix(0)
        resource_block.operational_units_in_timepoint[
            modeled_year, next_dispatch_window, first_timestamp_next_chrono_period + pd.Timedelta(hours=offset)
        ] = 3
        resource_block.shutdown_units[chrono_period_3_index].fix(shutdown_unit_3)
        resource_block.shutdown_units[chrono_period_2_index].fix(shutdown_unit_2)
        resource_block.shutdown_units[chrono_period_1_index].fix(shutdown_unit_1)
        resource_block.shutdown_units[chrono_period_0_index].fix(shutdown_unit_0)
        # note: because of small test & wrapping system chrono_period_0_index and chrono_period_3_index are the same timepoint

        constraint_index = (modeled_year, next_chrono_period, offset)

        assert resource_block.min_downtime_constraint_inter[constraint_index].body() == min_down_body
        assert resource_block.min_downtime_constraint_inter[constraint_index].upper() == min_down_upper
        assert resource_block.min_downtime_constraint_inter[constraint_index].expr() == expr

    @pytest.mark.parametrize(
        "start_units, start_costs",
        [(4, 20), (0, 0)],
    )
    def test_start_cost_in_timepoint(self, make_component_with_block_copy, first_index, start_units, start_costs):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        resource_block.start_units[first_index].fix(start_units)
        assert resource_block.start_cost_in_timepoint[first_index].expr() == start_costs

    @pytest.mark.parametrize(
        "shutdown_units, shutdown_costs",
        [(4, 40), (0, 0)],
    )
    def test_shutdown_cost_in_timepoint(
        self, make_component_with_block_copy, first_index, shutdown_units, shutdown_costs
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        resource_block.shutdown_units[first_index].fix(shutdown_units)
        assert resource_block.shutdown_cost_in_timepoint[first_index].expr() == shutdown_costs

    @pytest.mark.parametrize(
        "start_units, shutdown_units, total_costs",
        [(4, 2, 40 * 0.6 * 365), (0, 0, 0), (0, 2, 20 * 0.6 * 365), (2, 0, 10 * 0.6 * 365)],
    )
    def test_annual_start_and_shutdown_cost(
        self, make_component_with_block_copy, first_index, start_units, shutdown_units, total_costs
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        # set all start units to 0 except first timepoint
        resource_block.start_units.fix(0)
        resource_block.start_units[first_index].fix(start_units)
        # set all shutdown units to 0 expect first timepoint
        resource_block.shutdown_units.fix(0)
        resource_block.shutdown_units[first_index].fix(shutdown_units)
        modeled_year, dispatch_window, timestamp = first_index
        assert resource_block.annual_start_and_shutdown_cost[modeled_year].expr() == total_costs

    @pytest.mark.parametrize(
        "committed_units_first, committed_units_next, start_units_next, shutdown_units_next, commitment_tracking_upper, commitment_tracking_lower, commitment_tracking_body, expr",
        [
            (0, 0, 1, 0, 0.0, 0.0, -1.0, False),
            (0, 1, 1, 0, 0.0, 0.0, 0.0, True),
            (0, 0, 1, 1, 0.0, 0.0, 0.0, True),
            (1, 1, 0, 0, 0.0, 0.0, 0.0, True),
            (1, 0, 0, 1, 0.0, 0.0, 0.0, True),
            (1, 1, 1, 1, 0.0, 0.0, 0.0, True),
            (0, 1, 1, 1, 0.0, 0.0, 1.0, False),
        ],
    )
    def test_commitment_tracking_inter_period(
        self,
        make_component_with_block_copy_inter_period_sharing,
        committed_units_first,
        committed_units_next,
        start_units_next,
        shutdown_units_next,
        commitment_tracking_upper,
        commitment_tracking_lower,
        commitment_tracking_body,
        expr,
    ):
        resource = make_component_with_block_copy_inter_period_sharing()
        resource_block = resource.formulation_block
        modeled_year = pd.Timestamp("2025-01-01")

        first_index = (modeled_year, pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00"))
        next_index = (modeled_year, pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00"))
        resource_block.committed_units[first_index].fix(committed_units_first)
        resource_block.committed_units[next_index].fix(committed_units_next)
        resource_block.start_units[next_index].fix(start_units_next)
        resource_block.shutdown_units[next_index].fix(shutdown_units_next)

        # assert the first index of intra contraint was skipped because it would cross the dispatch window boundary
        with pytest.raises(KeyError):
            resource_block.commitment_tracking_constraint[first_index]

        constraint_index = (modeled_year, pd.Timestamp("2012-01-02"))
        assert (
            resource_block.commitment_tracking_inter_period_constraint[constraint_index].upper()
            == commitment_tracking_upper
        )
        assert (
            resource_block.commitment_tracking_inter_period_constraint[constraint_index].lower()
            == commitment_tracking_lower
        )
        assert (
            resource_block.commitment_tracking_inter_period_constraint[constraint_index].body()
            == commitment_tracking_body
        )
        assert resource_block.commitment_tracking_inter_period_constraint[constraint_index].expr() == expr

    def test_ramp_rate_validator(self, make_component_copy):
        resource = make_component_copy()
        # ensure that an error is raised if a user tries to do multi hour ramp rates for unit commitment
        with pytest.raises(ValidationError):
            resource.ramp_rate_2_hour = 0.7
            resource.ramp_rate_3_hour = 0.8
            resource.ramp_rate_4_hour = 0.9

    @pytest.mark.parametrize(
        "ramp_rate_hour, power_output, committed_units, start_units, shutdown_units, expr, upper, body",
        [
            (1, 1000, 100, 1, 1, True, 0.0, 990 - (((100 - 1) * 0.4 * 50) - (0.5 * 1 * 50) + (0.5 * 1 * 50))),
            (1, 100, 3, 1, 2, False, 0.0, 90 - (((3 - 1) * 0.4 * 50) - (0.5 * 2 * 50) + (0.5 * 1 * 50))),
        ],
    )
    def test_ramp_rate_intra_period_up_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        ramp_rate_hour,
        power_output,
        committed_units,
        start_units,
        shutdown_units,
        expr,
        upper,
        body,
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        ramp_index = (modeled_year, dispatch_window, timestamp + pd.Timedelta(hours=ramp_rate_hour))
        resource_block.power_output.fix(10)
        resource_block.power_output[ramp_index].fix(power_output)
        resource_block.committed_units[ramp_index].fix(committed_units)
        resource_block.start_units[ramp_index].fix(start_units)
        resource_block.shutdown_units[ramp_index].fix(shutdown_units)

        assert resource_block.ramp_rate_intra_period_up_constraint[first_index, ramp_rate_hour].expr() == expr
        assert resource_block.ramp_rate_intra_period_up_constraint[first_index, ramp_rate_hour].body() == body
        assert resource_block.ramp_rate_intra_period_up_constraint[first_index, ramp_rate_hour].upper() == upper

    @pytest.mark.parametrize(
        "ramp_rate_hour, power_output, committed_units, start_units, shutdown_units, expr, upper, body",
        [
            (1, 1000, 100, 1, 1, True, 0.0, -800 - (((100 - 1) * 0.4 * 50) - (0.5 * 1 * 50) + (0.5 * 1 * 50))),
            (1, 100, 3, 1, 2, False, 0.0, 100 - (((3 - 1) * 0.4 * 50) - (0.5 * 1 * 50) + (0.5 * 2 * 50))),
        ],
    )
    def test_ramp_rate_intra_period_down_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        ramp_rate_hour,
        power_output,
        committed_units,
        start_units,
        shutdown_units,
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
        resource_block.committed_units[ramp_index].fix(committed_units)
        resource_block.start_units[ramp_index].fix(start_units)
        resource_block.shutdown_units[ramp_index].fix(shutdown_units)

        assert resource_block.ramp_rate_intra_period_down_constraint[first_index, ramp_rate_hour].expr() == expr
        assert resource_block.ramp_rate_intra_period_down_constraint[first_index, ramp_rate_hour].body() == body
        assert resource_block.ramp_rate_intra_period_down_constraint[first_index, ramp_rate_hour].upper() == upper

    @pytest.mark.parametrize(
        "ramp_rate_hour, power_output, committed_units, start_units, shutdown_units, expr, upper, body",
        [
            (1, 1000, 100, 1, 1, True, 0.0, 990 - (((100 - 1) * 0.4 * 50) - (0.5 * 1 * 50) + (0.5 * 1 * 50))),
            (1, 100, 3, 1, 2, False, 0.0, 90 - (((3 - 1) * 0.4 * 50) - (0.5 * 2 * 50) + (0.5 * 1 * 50))),
        ],
    )
    def test_ramp_rate_inter_period_up_constraint(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index,
        last_index,
        ramp_rate_hour,
        power_output,
        committed_units,
        start_units,
        shutdown_units,
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

        chrono_period_1_index = (modeled_year, dispatch_window, last_timestamp_chrono_period)
        ramp_index = (
            modeled_year,
            next_dispatch_window,
            first_timestamp_next_chrono_period + pd.Timedelta(hours=ramp_rate_hour - 1),
        )
        # assert the first index of intra contraint was skipped because it would cross the dispatch window boundary
        with pytest.raises(KeyError):
            resource_block.ramp_rate_intra_period_up_constraint[chrono_period_1_index]
        resource_block = resource.formulation_block
        resource_block.power_output.fix(10)
        resource_block.power_output[ramp_index].fix(power_output)
        resource_block.committed_units[ramp_index].fix(committed_units)
        resource_block.start_units[ramp_index].fix(start_units)
        resource_block.shutdown_units[ramp_index].fix(shutdown_units)

        assert resource_block.ramp_rate_inter_period_up_constraint[chrono_index, ramp_rate_hour, 0].expr() == expr
        assert resource_block.ramp_rate_inter_period_up_constraint[chrono_index, ramp_rate_hour, 0].body() == body
        assert resource_block.ramp_rate_inter_period_up_constraint[chrono_index, ramp_rate_hour, 0].upper() == upper

    @pytest.mark.parametrize(
        "ramp_rate_hour, power_output, committed_units, start_units, shutdown_units, expr, upper, body",
        [
            (1, 1000, 100, 1, 1, True, 0.0, -800 - (((100 - 1) * 0.4 * 50) - (0.5 * 1 * 50) + (0.5 * 1 * 50))),
            (1, 100, 3, 1, 2, False, 0.0, 100 - (((3 - 1) * 0.4 * 50) - (0.5 * 1 * 50) + (0.5 * 2 * 50))),
        ],
    )
    def test_ramp_rate_inter_period_down_constraint(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index,
        ramp_rate_hour,
        power_output,
        committed_units,
        start_units,
        shutdown_units,
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

        chrono_period_1_index = (modeled_year, dispatch_window, last_timestamp_chrono_period)
        ramp_index = (
            modeled_year,
            next_dispatch_window,
            first_timestamp_next_chrono_period + pd.Timedelta(hours=ramp_rate_hour - 1),
        )
        # assert the first index of intra contraint was skipped because it would cross the dispatch window boundary
        with pytest.raises(KeyError):
            resource_block.ramp_rate_inter_period_down_constraint[chrono_period_1_index]
        resource_block.power_output.fix(200)
        resource_block.power_output[ramp_index].fix(power_output)
        resource_block.committed_units[ramp_index].fix(committed_units)
        resource_block.start_units[ramp_index].fix(start_units)
        resource_block.shutdown_units[ramp_index].fix(shutdown_units)

        assert resource_block.ramp_rate_inter_period_down_constraint[chrono_index, ramp_rate_hour, 0].expr() == expr
        assert resource_block.ramp_rate_inter_period_down_constraint[chrono_index, ramp_rate_hour, 0].body() == body
        assert resource_block.ramp_rate_inter_period_down_constraint[chrono_index, ramp_rate_hour, 0].upper() == upper

    def test_annual_total_operational_cost(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.power_output.fix(10)
        block.start_units.fix(4)
        block.shutdown_units.fix(2)

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
        ]:
            assert block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (2 + 2 + 2) + (10 * 2 * 3) + (5 * 4 * 3))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (2 + 2 + 2) + (10 * 2 * 3) + (5 * 4 * 3))
            )

        for year in [
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            assert block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (0 + 0 + 0) + (10 * 2 * 3) + (5 * 4 * 3))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (0 + 0 + 0) + (10 * 2 * 3) + (5 * 4 * 3))
            )

        assert block.annual_total_operational_cost

    @pytest.mark.skip(reason="Functionality not implemented yet for UnitCommitmentResource")
    def test_check_if_operationally_equal_copy(self, make_component_copy):
        super().test_check_if_operationally_equal_copy(make_component_copy=make_component_copy)

    @pytest.mark.skip(reason="Functionality not implemented yet for UnitCommitmentResource")
    def test_check_if_operationally_equal_true(self, make_component_copy, attr_name, new_value):
        super().test_check_if_operationally_equal_true(
            make_component_copy=make_component_copy, attr_name=attr_name, new_value=new_value
        )

    @pytest.mark.skip(reason="Functionality not implemented yet for UnitCommitmentResource")
    def test_check_if_operationally_equal_false(self, make_component_copy, attr_name, new_value):
        super().test_check_if_operationally_equal_false(
            make_component_copy=make_component_copy, attr_name=attr_name, new_value=new_value
        )

    @pytest.mark.skip(reason="Functionality not implemented yet for UnitCommitmentResource")
    def test_check_if_operationally_equal_linkages(self, make_component_copy, test_zone_1, test_zone_2):
        super().test_check_if_operationally_equal_linkages(
            make_component_copy=make_component_copy, test_zone_1=test_zone_1, test_zone_2=test_zone_2
        )

    def test_results_reporting(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        resource._construct_output_expressions(construct_costs=True)

        assert resource.formulation_block.start_units.doc == "Number of Starts"
        assert resource.formulation_block.annual_start_units.doc == "Annual Number of Starts"
        assert resource.formulation_block.shutdown_units.doc == "Number of Shutdowns"
        assert resource.formulation_block.annual_shutdown_units.doc == "Annual Number of Shutdowns"
        assert resource.formulation_block.annual_start_cost.doc == "Annual Start Cost ($)"
        assert resource.formulation_block.annual_shutdown_cost.doc == "Annual Shutdown Cost ($)"
        assert resource.formulation_block.committed_units.doc == "Number of Committed Units"
        assert resource.formulation_block.operational_units_in_timepoint.doc == "Number of available units"

        assert resource.model_fields["unit_size"].title == "Unit Size"


class TestUnitCommitmentResourceGroup(TestGenericResourceGroup):

    def test_check_potential_required_validator(self, test_generic_resource_group):
        """
        Test that the `check_potential_required` validator enforces correct behavior
        for `UnitCommitmentResourceGroup` when using the 'single_unit' commitment mode.

        This test covers three cases:

        1. **Valid case** — `unit_commitment_mode='single_unit'` with `cumulative_potential`
           defined and finite (while other optional fields such as ramp rates and
           individual `potential` are absent). The model should build successfully.

        2. **Missing cumulative potential** — when `cumulative_potential` is omitted,
           the model should raise a `ValidationError` with the expected message
           ("Cumulative potential required for unit commitment resource group").

        3. **Invalid cumulative potential** — when `cumulative_potential` is defined
           but takes the value `inf`, the model should raise a `ValueError` with the
           same expected message.

        Together these checks ensure that resource groups committed under the
        'single_unit' formulation always specify a valid, finite `cumulative_potential`.
        """
        init_kwargs = test_generic_resource_group.model_dump()
        init_kwargs.pop("ramp_rate_2_hour")
        init_kwargs.pop("ramp_rate_4_hour")
        init_kwargs.pop("potential")
        init_kwargs.update(
            unit_commitment_mode="single_unit",
        )
        UnitCommitmentResourceGroup(**init_kwargs)  # check that it passes build

        init_kwargs.pop("cumulative_potential")
        with pytest.raises(ValidationError, match="Cumulative potential required for unit commitment resource group"):
            UnitCommitmentResourceGroup(**init_kwargs)  # check that it fails build

        init_kwargs.update(
            cumulative_potential=ts.NumericTimeseries(name="cumulative_potential", data=pd.Series(np.inf))
        )
        with pytest.raises(ValueError, match="Cumulative potential required for unit commitment resource group"):
            UnitCommitmentResourceGroup(**init_kwargs)  # check that it fails build
