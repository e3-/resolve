import pandas as pd
import pytest

from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.system.electric.resources.flex_load import FlexLoadResource
from new_modeling_toolkit.system.electric.resources.flex_load import FlexLoadResourceGroup
from tests.system.electric.resources import test_shed_dr
from tests.system.electric.resources import test_storage
from tests.system.electric.resources import test_unit_commitment
from tests.system.electric.resources.test_thermal import TestThermalResourceUnitCommitmentSingleUnit


class TestFlexLoadResource(test_shed_dr.TestShedDrResource, test_storage.TestStorageResource):
    _COMPONENT_CLASS = FlexLoadResource
    _COMPONENT_NAME = "FlexLoadResource"
    _SYSTEM_COMPONENT_DICT_NAME = "flex_load_resources"

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
            "adjacency",
        ]

    @pytest.mark.parametrize(
        "committed_units, committed_capacity",
        [
            (0, 0),
            (1, 50.0),
            (2, 100.0),
        ],
    )
    def test_committed_capacity_mw_power_output(
        self, make_component_with_block_copy, first_index, committed_units, committed_capacity
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        resource_block.committed_units_power_output[first_index].fix(committed_units)
        assert resource_block.committed_capacity_mw_power_output[first_index].expr() == committed_capacity

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
    def test_commitment_power_output_tracking_constraint(
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
        resource_block.committed_units_power_output[first_index].fix(committed_units_first)
        resource_block.committed_units_power_output[next_index].fix(committed_units_next)
        resource_block.start_units_power_output[next_index].fix(start_units_next)
        resource_block.shutdown_units_power_output[next_index].fix(shutdown_units_next)
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].upper() == commitment_tracking_upper
        )
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].lower() == commitment_tracking_lower
        )
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].body() == commitment_tracking_body
        )
        assert resource_block.commitment_power_output_tracking_constraint[first_index].expr() == expr

    @pytest.mark.parametrize(
        "committed_units, committed_capacity",
        [
            (0, 0),
            (1, 50.0),
            (2, 100.0),
        ],
    )
    def test_committed_capacity_mw_power_output(
        self, make_component_with_block_copy, first_index, committed_units, committed_capacity
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        resource_block.committed_units_power_output[first_index].fix(committed_units)
        assert resource_block.committed_capacity_mw_power_output[first_index].expr() == committed_capacity

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
    def test_commitment_power_output_tracking_constraint(
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
        resource_block.committed_units_power_output[first_index].fix(committed_units_first)
        resource_block.committed_units_power_output[next_index].fix(committed_units_next)
        resource_block.start_units_power_output[next_index].fix(start_units_next)
        resource_block.shutdown_units_power_output[next_index].fix(shutdown_units_next)
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].upper() == commitment_tracking_upper
        )
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].lower() == commitment_tracking_lower
        )
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].body() == commitment_tracking_body
        )
        assert resource_block.commitment_power_output_tracking_constraint[first_index].expr() == expr

    def test_power_output_adjacency_constraint_intra(self, make_component_with_block_copy, first_index, last_index):
        """
        Verify _power_output_adjacency_constraint behavior within a representative period when
        inter-period sharing is NOT skipping.

        It should enforce:
            power_output[t+adj] <= sum_{n in 0..adj_offset-1} power_input[t+n]
        """
        resource: FlexLoadResource = make_component_with_block_copy()
        b = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        t = timestamp
        # Set deterministic values for power_input over the adjacency window and check output bound
        b.power_input[modeled_year, dispatch_window, t].fix(10.0)
        b.power_input[modeled_year, dispatch_window, t + pd.DateOffset(hours=1)].fix(20.0)
        b.power_input[modeled_year, dispatch_window, t + pd.DateOffset(hours=2)].fix(30.0)
        # Set power_output at t+adjacency (adjacency=1) to 50 to satisfy inequality 50 <= 60
        b.power_output[modeled_year, dispatch_window, t + pd.DateOffset(hours=1)].fix(50.0)
        c = b.power_output_adjacency_constraint[modeled_year, dispatch_window, t]
        assert bool(c.expr()) is True  # satisfied (50 <= 60)
        # Now set power_output to 70 which violates 70 <= 60
        b.power_output[modeled_year, dispatch_window, t + pd.DateOffset(hours=1)].fix(70.0)
        c = b.power_output_adjacency_constraint[modeled_year, dispatch_window, t]
        assert bool(c.expr()) is False
        # assert not skipped when not inter period
        assert last_index in b.power_output_adjacency_constraint

    def test_power_output_adjacency_constraint_skip_when_inter_period(
        self, make_component_with_block_copy_inter_period_sharing, last_index
    ):
        """
        When inter-period sharing is active and allowed, and the adjacency range would span beyond
        the last timepoint of the dispatch window, the intra-period constraint should be skipped
        because the inter-period version handles it.
        """
        resource: FlexLoadResource = make_component_with_block_copy_inter_period_sharing()
        assert last_index not in resource.formulation_block.power_output_adjacency_constraint

    def test_max_dr_call_duration_intra_period_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        resource_block.start_units_power_output.fix(0)
        timestamp = timestamp + pd.DateOffset(hours=2)

        resource_block.committed_units_power_output[modeled_year, dispatch_window, timestamp].fix(1)
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

        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=1)].fix(
            1
        )
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

        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=1)].fix(
            0
        )
        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=2)].fix(
            1
        )
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

    @pytest.mark.parametrize(
        "committed_units, provide_power_capacity",
        [
            # Case 1: no committed units → expected available capacity is 0
            (0, 0),
            # Case 2: committed units = 50 → expected available capacity is 50
            (50.0, 50.0),
        ],
    )
    def test_power_output_max(
        self, make_component_with_block_copy, first_index, committed_units, provide_power_capacity
    ):
        """
        Verify that power_output_max correctly reflects the committed capacity
        (i.e., the maximum available power output equals committed units).
        """

        # Build the resource and access its Pyomo formulation block
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        # Assign committed capacity directly for the test case
        resource_block.committed_capacity_mw_power_output[first_index] = committed_units

        # Assert that power_output_max expression equals the expected capacity
        assert resource_block.power_output_max[first_index].expr() == provide_power_capacity

    @pytest.mark.parametrize(
        "committed_units, provide_power_min_capacity",
        [
            # Case 1: no committed units → minimum available capacity is 0
            (0, 0),
            # Case 2: committed units = 25 → minimum available capacity is 25 * 0.1 (pmin)
            (25.0, 25.0 * 0.1),
        ],
    )
    def test_power_output_min(
        self, make_component_with_block_copy, first_index, committed_units, provide_power_min_capacity
    ):
        """
        Verify that power_output_min correctly scales with committed capacity.
        In this simplified setup, the minimum power output is equal to the
        committed capacity (no derating factor applied).
        """

        # Build the resource and access its Pyomo formulation block
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        # Assign committed capacity directly for the test case
        resource_block.committed_capacity_mw_power_output[first_index] = committed_units

        # Check that the power_output_min expression equals the expected value
        # (here it's directly equal to committed capacity for simplicity)
        assert resource_block.power_output_min[first_index].expr() == provide_power_min_capacity

    @pytest.mark.parametrize(
        "committed_capacity, expected_body, expected_expr",
        [
            # Case 1: committed capacity = 120 → 0.8 * 120 = 96
            # body = 100 - 96 = 4 → inequality violated (above max) → expr() False
            pytest.param(120.0, 100 - 0.8 * 120, False, id="output_above_max"),
            # Case 2: committed capacity = 3000 → 0.8 * 3000 = 2400
            # body = 100 - 2400 = -2300 → inequality satisfied (below max) → expr() True
            pytest.param(3000.0, 100 - 0.8 * 3000, True, id="output_below_max"),
            # Case 3: committed capacity = 125 → 0.8 * 125 = 100
            # body = 100 - 100 = 0 → binding case, still satisfies inequality → expr() True
            pytest.param(125.0, 100 - 0.8 * 125, True, id="output_exact_max"),
        ],
    )
    def test_power_output_max_constraint(
        self, make_component_with_block_copy, first_index, committed_capacity, expected_body, expected_expr
    ):
        """
        Verify that power_output_max_constraint enforces the maximum operating
        requirement correctly across different committed_capacity_mw_power_output values.

        Constraint canonical form: power_output - committed_capacity * power_output_max(t) <= 0
        We set power_output_max(t) = 0.8 and fix power_output at 100.
        """

        resource = make_component_with_block_copy()
        block = resource.formulation_block

        modeled_year, dispatch_window_id, timestamp = first_index
        timestamp = timestamp + pd.DateOffset(hours=1)

        # Assign committed capacity and power_output
        block.committed_capacity_mw_power_output[modeled_year, dispatch_window_id, timestamp] = committed_capacity
        block.power_output[modeled_year, dispatch_window_id, timestamp] = 100

        c = block.power_output_max_constraint[modeled_year, dispatch_window_id, timestamp]

        # Upper bound is always zero
        assert c.upper() == 0

        # Body is (power_output - committed_capacity * profile)
        assert c.body() == expected_body

        # expr() truthiness:
        #   body > 0  → violation    → False
        #   body == 0 → binding      → True
        #   body < 0  → satisfied    → True
        assert bool(c.expr()) == expected_expr

    @pytest.mark.parametrize(
        "power_output, expected_body, expected_expr",
        [
            # Case 1: committed capacity = 160 → minimum requirement = 16
            # body = 0.1 * 160 - 100 = -84 → inequality violated → expr() is True
            pytest.param(160.0, 160 * 0.1 - 100, True, id="output_above_min"),
            # Case 2: committed capacity = 3000 → minimum requirement = 300
            # body = 0.1 * 3000 - 100 = 200 → inequality satisfied → expr() is False
            pytest.param(3000.0, 0.1 * 3000 - 100, False, id="output_below_min"),
            # Case 3: committed capacity = 1000 → minimum requirement = 100
            # body = 0.1 * 1000 - 100 = 0 → binding case → expr() is False
            pytest.param(1000.0, 0.1 * 1000 - 100, True, id="output_exact_min"),
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
        block.committed_capacity_mw_power_output[modeled_year, dispatch_window_id, timestamp] = power_output
        block.power_output[modeled_year, dispatch_window_id, timestamp] = 100

        # Constraint is always enforced as ≤ 0
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0

        # Body should equal 0.1 * committed_capacity - power_output
        assert block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == expected_body

        # expr() evaluates whether the inequality is violated (True) or satisfied (False)
        assert (
            bool(block.power_output_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()) == expected_expr
        )

    @pytest.mark.parametrize(
        "power_output, reserves, expected_body, expected_expr",
        [
            # Case 1: power_output=160, reserves=30, power_input=30, Pmax=200
            # body = 160 + 30 - 30 - 200 = -40 → satisfied → expr() True
            pytest.param(160.0, 30.0, -40.0, True, id="within_capacity"),
            # Case 2: power_output=600, reserves=30, power_input=30, Pmax=200
            # body = 600 + 30 - 30 - 200 = 400 → violated → expr() False
            pytest.param(600.0, 30.0, 400.0, False, id="exceeds_capacity"),
            # Case 3: power_output=0, reserves=0, power_input=30, Pmax=200
            # body = 0 + 0 - 30 - 200 = -230 → satisfied → expr() True
            pytest.param(0.0, 0.0, -230.0, True, id="equal_capacity"),
        ],
    )
    def test_total_up_reserves_max_constraint(
        self, make_component_with_block_copy, first_index, power_output, reserves, expected_body, expected_expr
    ):
        """
        Verify total_up_reserves_max_constraint ensures that the sum of power output,
        reserves, and net input never exceeds the Pmax profile.

        Constraint canonical form:
            (power_output + total_up_reserves - power_input) - power_output_max <= 0
        """

        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        # Fixture setup: operational capacity is 200, 4 committed units
        block.operational_capacity[modeled_year] = 200
        block.committed_units.fix(4)

        # Assign test values
        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(power_output)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(reserves)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(30.0)
        block.power_output_max[modeled_year, dispatch_window_id, timestamp] = 200.0

        c = block.total_up_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp]

        # Upper bound is always zero
        assert c.upper() == 0

        # Body = power_output + reserves - power_input - power_output_max
        assert c.body() == expected_body

        # expr(): True if inequality satisfied/binding, False if violated
        assert bool(c.expr()) == expected_expr

    @pytest.mark.parametrize(
        "power_input, reserves, power_output, expected_body, expected_expr",
        [
            # Case 1: power_input=100, reserves=20, power_output=0, Imax=150
            # body = 100 + 20 - 0 - 150 = -30 → satisfied → expr() True
            pytest.param(100.0, 20.0, 0.0, -30.0, True, id="within_capacity"),
            # Case 2: power_input=200, reserves=50, power_output=0, Imax=150
            # body = 200 + 50 - 0 - 150 = 100 → violated → expr() False
            pytest.param(200.0, 50.0, 0.0, 100.0, False, id="exceeds_capacity"),
            # Case 3: power_input=150, reserves=0, power_output=0, Imax=150
            # body = 150 + 0 - 0 - 150 = 0 → binding → expr() True
            pytest.param(150.0, 0.0, 0.0, 0.0, True, id="equal_capacity"),
            # Case 4: power_input=100, reserves=20, power_output=50, Imax=150
            # body = 100 + 20 - 50 - 150 = -80 → satisfied (net load reduced by output) → expr() True
            pytest.param(100.0, 20.0, 50.0, -80.0, True, id="with_power_output"),
        ],
    )
    def test_total_down_reserves_max_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        power_input,
        reserves,
        power_output,
        expected_body,
        expected_expr,
    ):
        """
        Verify total_down_reserves_max_constraint ensures that the sum of power input,
        down reserves, and net output never exceeds the Imax profile.

        Constraint canonical form:
            (power_input + total_down_reserves - power_output) - power_input_max <= 0
        """

        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        # Fixture setup: set Imax = 150
        block.power_input_max[modeled_year, dispatch_window_id, timestamp] = 150.0

        # Assign test values
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(power_input)
        block.provide_reserve["TestRegulationDown", modeled_year, dispatch_window_id, timestamp].fix(reserves)
        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(power_output)

        c = block.total_down_reserves_max_constraint[modeled_year, dispatch_window_id, timestamp]

        # Upper bound is always zero
        assert c.upper() == 0

        # Body = power_input + reserves - power_output - power_input_max
        assert c.body() == expected_body

        # expr(): True if inequality satisfied/binding, False if violated
        assert bool(c.expr()) == expected_expr

    @pytest.mark.parametrize(
        "committed_capacity, power_input, expected_body, expected_expr",
        [
            # Case 1: half of capacity → satisfied (binding)
            # body = 50 - (100 * 0.5) = 0 → satisfied → expr() True
            pytest.param(100.0, 50.0, 0.0, True, id="half_capacity"),
            # Case 2: below capacity → satisfied
            # body = 20 - (100 * 0.5) = -30 → satisfied → expr() True
            pytest.param(100.0, 20.0, -30.0, True, id="below_capacity"),
            # Case 3: exceeds capacity → violated
            # body = 120 - (100 * 0.5) = 70 → violation → expr() False
            pytest.param(100.0, 120.0, 70.0, False, id="exceeds_capacity"),
        ],
    )
    def test_power_input_max_constraint(
        self, make_component_with_block_copy, first_index, committed_capacity, power_input, expected_body, expected_expr
    ):
        """
        Verify that power_input_max enforces the upper bound on input.

        Constraint canonical form:
            power_input - (committed_capacity_mw_power_input * imax_profile[t]) <= 0

        For this test we assume imax_profile[t] = 0.5.
        """

        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        # Assign committed capacity for power input and fix imax profile at 0.5
        block.committed_capacity_mw_power_input[modeled_year, dispatch_window_id, timestamp] = committed_capacity

        # Fix actual power_input
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(power_input)

        c = block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp]

        # Upper bound is always zero
        assert c.upper() == 0

        # Body = power_input - (committed_capacity * 0.5)
        assert c.body() == expected_body

        # expr(): True if inequality satisfied/binding, False if violated
        assert bool(c.expr()) == expected_expr

    def test_power_input_min_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window_id, timestamp = first_index

        block.committed_capacity_mw_power_input[pd.Timestamp("2025-01-01"), :, :] = 200

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

    def test_power_input_max(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.committed_capacity_mw_power_input[pd.Timestamp("2025-01-01"), :, :] = 200
        block.committed_capacity_mw_power_input[pd.Timestamp("2035-01-01"), :, :] = 150

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

        block.committed_capacity_mw_power_input[pd.Timestamp("2025-01-01"), :, :] = 200
        block.committed_capacity_mw_power_input[pd.Timestamp("2035-01-01"), :, :] = 150

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

    def test_power_input_adjacency_constraint_intra(self, make_component_with_block_copy, first_index, last_index):
        """
        Verify _power_input_adjacency_constraint behavior within a representative period when
        inter-period sharing is NOT skipping.

        It should enforce:
            power_input[t+adj] <= sum_{n in 0..adj_offset-1} power_output[t+n]
        """
        resource: FlexLoadResource = make_component_with_block_copy()
        b = resource.formulation_block

        modeled_year, dispatch_window, timestamp = first_index
        t = timestamp

        # Set deterministic values for power_output over the adjacency window and check input bound
        b.power_output[modeled_year, dispatch_window, t].fix(10.0)
        b.power_output[modeled_year, dispatch_window, t + pd.DateOffset(hours=1)].fix(20.0)
        b.power_output[modeled_year, dispatch_window, t + pd.DateOffset(hours=2)].fix(30.0)

        # Set power_input at t+adjacency to satisfy inequality (RHS sum = 60)
        b.power_input[modeled_year, dispatch_window, t + pd.DateOffset(hours=1)].fix(50.0)

        c = b.power_input_adjacency_constraint[modeled_year, dispatch_window, t]
        assert bool(c.expr()) is True  # satisfied (50 <= 60)

        # Now set power_input to 70 which violates 70 <= 60
        b.power_input[modeled_year, dispatch_window, t + pd.DateOffset(hours=1)].fix(70.0)
        c = b.power_input_adjacency_constraint[modeled_year, dispatch_window, t]
        assert bool(c.expr()) is False
        # assert not skipped when not inter period
        assert last_index in b.power_input_adjacency_constraint

    def test_power_input_adjacency_constraint_skip_when_inter_period(
        self, make_component_with_block_copy_inter_period_sharing, first_index, last_index
    ):
        """
        When inter-period sharing is active and allowed, and the adjacency range would span beyond
        the last timepoint of the dispatch window, the intra-period constraint should be skipped
        because the inter-period version handles it.
        """
        resource: FlexLoadResource = make_component_with_block_copy_inter_period_sharing()
        assert last_index not in resource.formulation_block.power_input_adjacency_constraint

    def test_power_input_inter_adjacency_constraint(self, make_component_with_block_copy_inter_period_sharing):
        """
        Verify _power_input_inter_adjacency_constraint behavior between representative periods.

        It should enforce for inter-period indices (chrono_period, hour_offset):
            power_input[nextw(dispatch_window,timestamp, step=adjacency+hour_offset)]
                <= sum_{t in 0..adj_offset-1} power_output[find_next_chronological(..., hour_offset + t)]
        """
        resource: FlexLoadResource = make_component_with_block_copy_inter_period_sharing()
        b = resource.formulation_block
        model = b.model()
        assert model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
        assert resource.allow_inter_period_sharing is True

        # Choose a chrono period and hour_offset=0 for simplicity
        chrono_period = pd.Timestamp("2012-01-03")
        modeled_year = next(iter(model.MODELED_YEARS))

        # Resolve base dispatch_window,timestamp at start of chrono_period
        dispatch_window, timestamp = model.find_next_chronological_dispatch_window_and_timepoint(chrono_period, 0)

        # Set RHS sum using adjacency_offset consecutive power_output values
        rhs_sum = 0.0
        for t in range(-resource.adjacency, resource.adjacency + 1):
            dw_t, ts_t = model.find_next_chronological_dispatch_window_and_timepoint(chrono_period, t)
            val = (t + 1) * 10.0  # 10, 20, 30, ...
            b.power_output[modeled_year, dw_t, ts_t].fix(val)
            rhs_sum += val

        # Case 1: satisfy inequality
        b.power_input[modeled_year, dispatch_window, timestamp].fix(rhs_sum - 5.0)
        c = b.power_input_inter_adjacency_constraint[modeled_year, chrono_period, 1]
        assert bool(c.expr()) is True

        # Case 2: violate inequality
        b.power_input[modeled_year, dispatch_window, timestamp].fix(rhs_sum + 1.0)
        c = b.power_input_inter_adjacency_constraint[modeled_year, chrono_period, 1]
        assert bool(c.expr()) is False

    def test_power_output_inter_adjacency_constraint(self, make_component_with_block_copy_inter_period_sharing):
        """
        Verify _power_output_inter_adjacency_constraint behavior between representative periods.

        It should enforce for inter-period indices (chrono_period, hour_offset):
            power_output[find_next_chronological(chrono_period, adjacency - hour_offset)]
                <= sum_{t in 0..adj_offset-1} power_input[find_next_chronological(chrono_period, t - hour_offset)]
        """
        resource: FlexLoadResource = make_component_with_block_copy_inter_period_sharing()
        b = resource.formulation_block
        model = b.model()
        assert model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
        assert resource.allow_inter_period_sharing is True

        # Choose a chrono period and hour_offset=0 for simplicity
        chrono_period = pd.Timestamp("2012-01-03")
        modeled_year = next(iter(model.MODELED_YEARS))

        # Determine LHS index for power_output at step = adjacency - hour_offset
        dispatch_window, timestamp = model.find_next_chronological_dispatch_window_and_timepoint(chrono_period, 0)

        # Set RHS sum using adjacency_offset consecutive power_input values at t - hour_offset
        rhs_sum = 0.0
        for t in range(-resource.adjacency, resource.adjacency + 1):
            dw_t, ts_t = model.find_next_chronological_dispatch_window_and_timepoint(chrono_period, t)
            val = (t + 2) * 10.0  # 10, 20, 30, ...
            b.power_input[modeled_year, dw_t, ts_t].fix(val)
            rhs_sum += val

        # Case 1: satisfy inequality
        b.power_output[modeled_year, dispatch_window, timestamp].fix(rhs_sum - 5.0)
        c = b.power_output_inter_adjacency_constraint[modeled_year, chrono_period, 1]
        assert bool(c.expr()) is True
        assert c.body() == -5

        # Case 2: violate inequality
        b.power_output[modeled_year, dispatch_window, timestamp].fix(rhs_sum + 1.0)
        c = b.power_output_inter_adjacency_constraint[modeled_year, chrono_period, 1]
        assert bool(c.expr()) is False
        assert c.body() == 1

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_net_power_output(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index_erm,
    ):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_charging_efficiency(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index_erm,
    ):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_discharging_efficiency(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index_erm,
    ):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_power_input_max_constraint(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_soc_tracking_constraint(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_power_output_max_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_annual_energy_budget_constraint(self, block_comp_for_budget_tests, first_index_erm):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_daily_energy_budget_constraint(self, block_comp_for_budget_tests, first_index_erm):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_dispatch_cost(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_annual_dispatch_cost(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_committed_capacity(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_commitment_tracking_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_daily_call_limit_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_max_dr_call_duration_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_committed_units_ub_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm, last_index_erm
    ):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_start_units_ub_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm, last_index_erm
    ):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResource")
    def test_erm_shutdown_units_ub_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm, last_index_erm
    ):
        pass

    def test_daily_dr_call_limit_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        day = pd.Timestamp("2010-06-21 00:00:00")
        modeled_year, dispatch_window, timestamp = first_index
        resource_block.start_units_power_output.fix(0)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].upper() == 0
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 0 - (100 / 50)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp].fix(1)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 1 - (100 / 50)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=1)].fix(
            1
        )
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 2 - (100 / 50)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=2)].fix(
            8
        )
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 10 - (100 / 50)
        assert not resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

    def test_annual_dr_call_limit_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        resource_block.start_units_power_output.fix(0)
        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp].fix(1)
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].upper() == 0
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].body() == 1 * 219 - (365 * (100 / 50))
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].expr()

        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=1)].fix(
            1
        )
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].body() == 2 * 219 - (365 * (100 / 50))
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].expr()

        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=2)].fix(
            8
        )
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].body() == 10 * 219 - (365 * (100 / 50))
        assert not resource_block.annual_dr_call_limit_constraint[modeled_year].expr()


class TestFlexLoadSingleUnitResource(TestThermalResourceUnitCommitmentSingleUnit):
    _COMPONENT_CLASS = FlexLoadResource
    _COMPONENT_NAME = "FlexLoadSingleUnitResource"
    _SYSTEM_COMPONENT_DICT_NAME = "flex_load_resources"

    @pytest.mark.parametrize(
        "committed_units_power_output, committed_capacity_mw_power_output, expected_body, expected_expr",
        [
            # If not committed, committed_capacity_mw_power_output must be 0 (<= 0*max_potential)
            pytest.param(0, 0.0, 0.0, True, id="not_committed_zero_capacity"),
            pytest.param(0, 10.0, 10.0, False, id="not_committed_positive_capacity_violates"),
            # If committed (1), capacity must be <= fixed max_potential (=300)
            pytest.param(1, 100.0, 100.0 - 300.0, True, id="committed_within_max"),
            pytest.param(1, 300.0, 0.0, True, id="committed_equal_max"),
            pytest.param(1, 310.0, 10.0, False, id="committed_above_max"),
        ],
    )
    def test_committed_capacity_mw_power_output_ub(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units_power_output,
        committed_capacity_mw_power_output,
        expected_body,
        expected_expr,
    ):
        """
        Unit test for UnitCommitmentResource._committed_capacity_mw_power_output_ub():
        committed_capacity_mw_power_output[yt] <= max_potential[y] * committed_units_power_output[yt]

        We directly set/fix the relevant variables and parameters on the resource block and
        verify the constructed constraint's body, bound, and truthiness without solving.
        """
        resource = make_component_with_block_copy()
        b = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Ensure SINGLE_UNIT path is active for committed_capacity_mw_power_output var and constraint
        # The fixture should already be configured appropriately in tests; we only set parameters/vars.
        b.committed_units_power_output[modeled_year, dispatch_window, timestamp].fix(committed_units_power_output)
        b.committed_capacity_mw_power_output[modeled_year, dispatch_window, timestamp].fix(
            committed_capacity_mw_power_output
        )

        c = b.committed_capacity_mw_power_output_ub[modeled_year, dispatch_window, timestamp]
        # Upper bound is None for <=; evaluation happens via expr()
        assert c.upper() == 0
        # Body is LHS - RHS
        assert c.body() == expected_body
        # expr(): True if inequality satisfied/binding, False if violated
        assert bool(c.expr()) is expected_expr

    @pytest.mark.parametrize(
        "unit_size, committed_capacity_mw_power_output, expected_body, expected_expr",
        [
            # committed_capacity_mw_power_output <= unit_size (satisfied)
            pytest.param(100.0, 50.0, 50.0 - 100.0, True, id="below_unit_size"),
            # committed_capacity_mw_power_output == unit_size (binding)
            pytest.param(100.0, 100.0, 0.0, True, id="equal_unit_size"),
            # committed_capacity_mw_power_output > unit_size (violation)
            pytest.param(100.0, 110.0, 10.0, False, id="above_unit_size"),
        ],
    )
    def test_committed_capacity_mw_power_output_unit_size_max(
        self,
        make_component_with_block_copy,
        first_index,
        unit_size,
        committed_capacity_mw_power_output,
        expected_body,
        expected_expr,
    ):
        """
        Unit test for UnitCommitmentResource._committed_capacity_mw_power_output_unit_size_max():
        committed_capacity_mw_power_output[yt] <= unit_size[y]

        For SINGLE_UNIT mode, unit_size is defined as an Expression equal to operational_capacity[year].
        We explicitly set operational_capacity for the modeled year to a chosen unit_size and fix
        committed_capacity_mw_power_output, then verify the constraint body and satisfaction.
        """
        resource = make_component_with_block_copy()
        b = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Set the unit size via operational_capacity (since SINGLE_UNIT uses dynamic unit_size Expression)
        b.operational_capacity[modeled_year] = unit_size
        # Fix committed_capacity_mw_power_output at the specific timepoint
        b.committed_capacity_mw_power_output[modeled_year, dispatch_window, timestamp].fix(
            committed_capacity_mw_power_output
        )

        c = b.committed_capacity_mw_power_output_unit_size_max[modeled_year, dispatch_window, timestamp]
        assert c.upper() == 0
        assert c.body() == expected_body  # LHS - RHS = committed_capacity_mw_power_output - unit_size
        assert bool(c.expr()) is expected_expr

    @pytest.mark.parametrize(
        "unit_size, committed_units_power_output, committed_capacity_mw_power_output, expected_body, expected_expr",
        [
            # When not committed (0), RHS = unit_size - max_potential.
            # With max_potential large (e.g., 300), constraint relaxes; any nonnegative committed_capacity_mw_power_output satisfies.
            pytest.param(100.0, 0, 0.0, (100.0 - 300.0) - 0, True, id="not_committed_zero_capacity_relaxed"),
            pytest.param(100.0, 0, 50.0, (100.0 - 300.0) - 50, True, id="not_committed_positive_capacity_relaxed"),
            # When committed (1), constraint enforces committed_capacity_mw_power_output >= unit_size.
            pytest.param(100.0, 1, 90.0, 100.0 - 90, False, id="committed_below_unit_size"),
            pytest.param(100.0, 1, 100.0, 0.0, True, id="committed_equal_unit_size"),
            pytest.param(100.0, 1, 120.0, -20.0, True, id="committed_above_unit_size"),
        ],
    )
    def test_committed_capacity_mw_power_output_unit_size_min(
        self,
        make_component_with_block_copy,
        first_index,
        unit_size,
        committed_units_power_output,
        committed_capacity_mw_power_output,
        expected_body,
        expected_expr,
    ):
        """
        Unit test for UnitCommitmentResource._committed_capacity_mw_power_output_unit_size_min():
        committed_capacity_mw_power_output[yt] >= unit_size[y] - max_potential[y] * (1 - committed_units_power_output[yt])

        For SINGLE_UNIT, unit_size is dynamic via operational_capacity. We set operational_capacity,
        max_potential for the modeled year, fix committed_units_power_output and committed_capacity_mw_power_output, and verify the
        constraint body/value and truthiness.
        """
        resource = make_component_with_block_copy()
        b = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Configure parameters/expressions
        b.operational_capacity[modeled_year] = unit_size

        # Fix variables
        b.committed_units_power_output[modeled_year, dispatch_window, timestamp].fix(committed_units_power_output)
        b.committed_capacity_mw_power_output[modeled_year, dispatch_window, timestamp].fix(
            committed_capacity_mw_power_output
        )

        c = b.committed_capacity_mw_power_output_unit_size_min[modeled_year, dispatch_window, timestamp]
        # Lower-bound constraint has lower() == 0 after moving all to LHS
        assert c.upper() == 0
        # Body is LHS - RHS
        assert c.body() == expected_body
        assert bool(c.expr()) is expected_expr

    @pytest.mark.parametrize(
        "committed_units_power_input, committed_capacity_mw_power_input, expected_body, expected_expr",
        [
            # If not committed, committed_capacity_mw_power_input must be 0 (<= 0*max_potential)
            pytest.param(0, 0.0, 0.0, True, id="not_committed_zero_capacity"),
            pytest.param(0, 10.0, 10.0, False, id="not_committed_positive_capacity_violates"),
            # If committed (1), capacity must be <= fixed max_potential (=300)
            pytest.param(1, 100.0, 100.0 - 300.0, True, id="committed_within_max"),
            pytest.param(1, 300.0, 0.0, True, id="committed_equal_max"),
            pytest.param(1, 310.0, 10.0, False, id="committed_above_max"),
        ],
    )
    def test_committed_capacity_mw_power_input_ub(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units_power_input,
        committed_capacity_mw_power_input,
        expected_body,
        expected_expr,
    ):
        """
        Unit test for UnitCommitmentResource._committed_capacity_mw_power_input_ub():
        committed_capacity_mw_power_input[yt] <= max_potential[y] * committed_units_power_input[yt]

        We directly set/fix the relevant variables and parameters on the resource block and
        verify the constructed constraint's body, bound, and truthiness without solving.
        """
        resource = make_component_with_block_copy()
        b = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Ensure SINGLE_UNIT path is active for committed_capacity_mw_power_input var and constraint
        # The fixture should already be configured appropriately in tests; we only set parameters/vars.
        b.committed_units_power_input[modeled_year, dispatch_window, timestamp].fix(committed_units_power_input)
        b.committed_capacity_mw_power_input[modeled_year, dispatch_window, timestamp].fix(
            committed_capacity_mw_power_input
        )

        c = b.committed_capacity_mw_power_input_ub[modeled_year, dispatch_window, timestamp]
        # Upper bound is None for <=; evaluation happens via expr()
        assert c.upper() == 0
        # Body is LHS - RHS
        assert c.body() == expected_body
        # expr(): True if inequality satisfied/binding, False if violated
        assert bool(c.expr()) is expected_expr

    @pytest.mark.parametrize(
        "unit_size, committed_capacity_mw_power_input, expected_body, expected_expr",
        [
            # committed_capacity_mw_power_input <= unit_size (satisfied)
            pytest.param(100.0, 50.0, 50.0 - 100.0, True, id="below_unit_size"),
            # committed_capacity_mw_power_input == unit_size (binding)
            pytest.param(100.0, 100.0, 0.0, True, id="equal_unit_size"),
            # committed_capacity_mw_power_input > unit_size (violation)
            pytest.param(100.0, 110.0, 10.0, False, id="above_unit_size"),
        ],
    )
    def test_committed_capacity_mw_power_input_unit_size_max(
        self,
        make_component_with_block_copy,
        first_index,
        unit_size,
        committed_capacity_mw_power_input,
        expected_body,
        expected_expr,
    ):
        """
        Unit test for UnitCommitmentResource._committed_capacity_mw_power_input_unit_size_max():
        committed_capacity_mw_power_input[yt] <= unit_size[y]

        For SINGLE_UNIT mode, unit_size is defined as an Expression equal to operational_capacity[year].
        We explicitly set operational_capacity for the modeled year to a chosen unit_size and fix
        committed_capacity_mw_power_input, then verify the constraint body and satisfaction.
        """
        resource = make_component_with_block_copy()
        b = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Set the unit size via operational_capacity (since SINGLE_UNIT uses dynamic unit_size Expression)
        b.operational_capacity[modeled_year] = unit_size
        # Fix committed_capacity_mw_power_input at the specific timepoint
        b.committed_capacity_mw_power_input[modeled_year, dispatch_window, timestamp].fix(
            committed_capacity_mw_power_input
        )

        c = b.committed_capacity_mw_power_input_unit_size_max[modeled_year, dispatch_window, timestamp]
        assert c.upper() == 0
        assert c.body() == expected_body  # LHS - RHS = committed_capacity_mw_power_input - unit_size
        assert bool(c.expr()) is expected_expr

    @pytest.mark.parametrize(
        "unit_size, committed_units_power_input, committed_capacity_mw_power_input, expected_body, expected_expr",
        [
            # When not committed (0), RHS = unit_size - max_potential.
            # With max_potential large (e.g., 300), constraint relaxes; any nonnegative committed_capacity_mw_power_input satisfies.
            pytest.param(100.0, 0, 0.0, (100.0 - 300.0) - 0, True, id="not_committed_zero_capacity_relaxed"),
            pytest.param(100.0, 0, 50.0, (100.0 - 300.0) - 50, True, id="not_committed_positive_capacity_relaxed"),
            # When committed (1), constraint enforces committed_capacity_mw_power_input >= unit_size.
            pytest.param(100.0, 1, 90.0, 100.0 - 90, False, id="committed_below_unit_size"),
            pytest.param(100.0, 1, 100.0, 0.0, True, id="committed_equal_unit_size"),
            pytest.param(100.0, 1, 120.0, -20.0, True, id="committed_above_unit_size"),
        ],
    )
    def test_committed_capacity_mw_power_input_unit_size_min(
        self,
        make_component_with_block_copy,
        first_index,
        unit_size,
        committed_units_power_input,
        committed_capacity_mw_power_input,
        expected_body,
        expected_expr,
    ):
        """
        Unit test for UnitCommitmentResource._committed_capacity_mw_power_input_unit_size_min():
        committed_capacity_mw_power_input[yt] >= unit_size[y] - max_potential[y] * (1 - committed_units_power_input[yt])

        For SINGLE_UNIT, unit_size is dynamic via operational_capacity. We set operational_capacity,
        max_potential for the modeled year, fix committed_units_power_input and committed_capacity_mw_power_input, and verify the
        constraint body/value and truthiness.
        """
        resource = make_component_with_block_copy()
        b = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Configure parameters/expressions
        b.operational_capacity[modeled_year] = unit_size

        # Fix variables
        b.committed_units_power_input[modeled_year, dispatch_window, timestamp].fix(committed_units_power_input)
        b.committed_capacity_mw_power_input[modeled_year, dispatch_window, timestamp].fix(
            committed_capacity_mw_power_input
        )

        c = b.committed_capacity_mw_power_input_unit_size_min[modeled_year, dispatch_window, timestamp]
        # Lower-bound constraint has lower() == 0 after moving all to LHS
        assert c.upper() == 0
        # Body is LHS - RHS
        assert c.body() == expected_body
        assert bool(c.expr()) is expected_expr


class TestFlexLoadResourceGroup(
    test_unit_commitment.TestUnitCommitmentResourceGroup, test_storage.TestStorageResourceGroup, TestFlexLoadResource
):
    _COMPONENT_CLASS = FlexLoadResourceGroup
    _COMPONENT_NAME = "shift_dr_resource_group_0"
    _SYSTEM_COMPONENT_DICT_NAME = "flex_load_resource_groups"

    @pytest.mark.skip(reason="No ERM in FlexLoadResourceGroup")
    def test_erm_charging_efficiency(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        pass

    @pytest.mark.skip(reason="No ERM in FlexLoadResourceGroup")
    def test_erm_discharging_efficiency(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        pass

    def test_annual_dr_call_limit_constraint(self, make_component_with_block_copy, first_index):
        """
        Validate the annual DR-call limit constraint construction.

        Context and parameterization (from fixtures/component defaults):
        - max_annual_calls = 100 calls/year
        - unit_size = 50 MW (each committed "unit" represents 50 MW of curtailable load)
        - power_output_max = 219 MW (system parameter for ShedDrResource in this test setup)
        - A "call" is triggered when start_units[t] > 0 at any hour t; the model aggregates
          calls across the year.

        Therefore, the annual limit on the number of calls scales with capacity as:
            annual_limit_calls = 365 * (max_annual_calls / unit_size)
        which in this test equals 365 * (100 / 50) = 730.

        The left-hand side (LHS) of the constraint is the sum over hours of start_units[t] * power_output_max.
        In this test, each unit start at an hour contributes 219 to the LHS (since power_output_max = 219).

        The constraint has the form (for the modeled year y):
            sum_t start_units[y, t] * 219 <= 365 * (100 / 50)
        which is equivalently tested here by checking the body() value (LHS - RHS).
        """
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Start with a clean slate: zero all starts.
        resource_block.start_units_power_output.fix(0)
        resource_block.operational_capacity[modeled_year] = 100

        # Trigger one DR call at the first timestamp: contributes 219 to the LHS.
        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp].fix(1)
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].upper() == 0
        # body() = LHS - RHS = (1 * 219) - (365 * (100 / 50))
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].body() == 1 * 219 - (365 * (100 / 50))
        # Constraint is still satisfied (<= 0)
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].expr()

        # Add a second call one hour later: now LHS = 2 * 219
        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=1)].fix(
            1
        )
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].body() == 2 * 219 - (365 * (100 / 50))
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].expr()

        # Add eight more units two hours later (simulating multiple units starting in the same hour):
        # total starts so far = 1 + 1 + 8 = 10; LHS = 10 * 219. This should now violate the constraint
        # given the test parameterization, so expr() should be False.
        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=2)].fix(
            8
        )
        assert resource_block.annual_dr_call_limit_constraint[modeled_year].body() == 10 * 219 - (365 * (100 / 50))
        assert not resource_block.annual_dr_call_limit_constraint[modeled_year].expr()

    def test_daily_dr_call_limit_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        day = pd.Timestamp("2010-06-21 00:00:00")
        modeled_year, dispatch_window, timestamp = first_index
        resource_block.start_units_power_output.fix(0)
        resource_block.operational_capacity[modeled_year] = 100

        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].upper() == 0
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 0 - (100 / 50)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp].fix(1)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 1 - (100 / 50)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=1)].fix(
            1
        )
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 2 - (100 / 50)
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()

        resource_block.start_units_power_output[modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=2)].fix(
            8
        )
        assert resource_block.daily_dr_call_limit_constraint[modeled_year, day].body() == 10 - (100 / 50)
        assert not resource_block.daily_dr_call_limit_constraint[modeled_year, day].expr()
