import pandas as pd
import pytest

from new_modeling_toolkit.system import ThermalResourceGroup
from new_modeling_toolkit.system.electric.resources import ThermalResource
from new_modeling_toolkit.system.electric.resources.thermal import ThermalUnitCommitmentResource
from tests.system.component_test_template import ComponentTestTemplate
from tests.system.electric.resources import test_generic
from tests.system.electric.resources import test_unit_commitment


class TestThermalResource(test_generic.TestGenericResource):
    _COMPONENT_CLASS = ThermalResource
    _COMPONENT_NAME = "ThermalResource1"
    _SYSTEM_COMPONENT_DICT_NAME = "thermal_resources"

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
            "fuel_burn_slope",
        ]

    def test_operational_linkages(self, make_component_copy):
        assert make_component_copy().operational_linkages == [
            "emissions_policies",
            "annual_energy_policies",
            "hourly_energy_policies",
            "zones",
            "reserves",
            "candidate_fuels",
        ]

    def test_results_reporting(self, make_component_with_block_copy):
        super().test_results_reporting(make_component_with_block_copy)
        resource = make_component_with_block_copy()
        resource._construct_output_expressions(construct_costs=True)

        assert (
            resource.formulation_block.annual_total_resource_fuel_consumption_mmbtu.doc
            == "Annual Fuel Consumption (MMBtu)"
        )
        assert resource.formulation_block.annual_total_resource_fuel_cost.doc == "Annual Fuel Cost ($)"

    def test_resource_fuel_consumption_variable(
        self,
        make_component_with_block_copy,
    ):
        """
        Test the Resource_Fuel_Consumption_In_Timepoint_MMBTU variable. Assert that:
        - the variable is indexed
        - the lower bound is 0
        - there is no upper bound
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        assert block.resource_fuel_consumption_in_timepoint_mmbtu.is_indexed()
        assert (
            block.resource_fuel_consumption_in_timepoint_mmbtu[
                "CandidateFuel1",
                pd.Timestamp("2025-01-01 00:00:00"),
                pd.Timestamp("2010-06-21 00:00:00"),
                pd.Timestamp("2010-06-21 00:00:00"),
            ].lower
            == 0
        )
        assert (
            block.resource_fuel_consumption_in_timepoint_mmbtu[
                "CandidateFuel1",
                pd.Timestamp("2025-01-01 00:00:00"),
                pd.Timestamp("2010-06-21 00:00:00"),
                pd.Timestamp("2010-06-21 00:00:00"),
            ].upper
            is None
        )

    def test_total_resource_fuel_consumption(
        self,
        make_component_with_block_copy,
        first_index,
    ):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        year, dispatch_window, timestamp = first_index

        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel1", year, dispatch_window, timestamp] = 10
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel2", year, dispatch_window, timestamp] = 20

        assert block.total_resource_fuel_consumption_in_timepoint_mmbtu[year, dispatch_window, timestamp].expr() == 30

    def test_annual_total_resource_fuel_consumption(
        self,
        make_component_with_block_copy,
    ):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        for fuel in ["CandidateFuel1", "CandidateFuel2"]:
            block.resource_fuel_consumption_in_timepoint_mmbtu[
                fuel,
                pd.Timestamp("2025-01-01 00:00:00"),
                pd.Timestamp("2010-06-21 00:00:00"),
                pd.Timestamp("2010-06-21 00:00:00"),
            ] = 1
            block.resource_fuel_consumption_in_timepoint_mmbtu[
                fuel,
                pd.Timestamp("2025-01-01 00:00:00"),
                pd.Timestamp("2010-06-21 00:00:00"),
                pd.Timestamp("2010-06-21 01:00:00"),
            ] = 2
            block.resource_fuel_consumption_in_timepoint_mmbtu[
                fuel,
                pd.Timestamp("2025-01-01 00:00:00"),
                pd.Timestamp("2010-06-21 00:00:00"),
                pd.Timestamp("2010-06-21 02:00:00"),
            ] = 3
            block.resource_fuel_consumption_in_timepoint_mmbtu[
                fuel,
                pd.Timestamp("2025-01-01 00:00:00"),
                pd.Timestamp("2012-02-15 00:00:00"),
                pd.Timestamp("2012-02-15 12:00:00"),
            ] = 4
            block.resource_fuel_consumption_in_timepoint_mmbtu[
                fuel,
                pd.Timestamp("2025-01-01 00:00:00"),
                pd.Timestamp("2012-02-15 00:00:00"),
                pd.Timestamp("2012-02-15 13:00:00"),
            ] = 5
            block.resource_fuel_consumption_in_timepoint_mmbtu[
                fuel,
                pd.Timestamp("2025-01-01 00:00:00"),
                pd.Timestamp("2012-02-15 00:00:00"),
                pd.Timestamp("2012-02-15 14:00:00"),
            ] = 6

        assert block.annual_total_resource_fuel_consumption_mmbtu[pd.Timestamp("2025-01-01 00:00:00")].expr() == (
            ((1 + 2 + 3) * 2 * 0.6 + (4 + 5 + 6) * 2 * 0.4) * 365
        )

    def test_resource_fuel_consumption_constraint(
        self,
        make_component_with_block_copy,
        first_index,
    ):
        """
        Test the Resource_Fuel_Consumption_Constraint. Assert that:
        - the constraint holds/doesn't hold after assigning values to the power_output and Resource_Fuel_Consumption_In_Timepoint_MMBTU variable
        - the constraint is indexed
        - the constraint upper and lower bounds are 0
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.power_output[first_index].fix(20)
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel1", first_index].fix(30)
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel2", first_index].fix(10)
        assert block.resource_fuel_consumption_constraint.is_indexed()
        assert block.resource_fuel_consumption_constraint[first_index].body() == pytest.approx(0.0)
        assert block.resource_fuel_consumption_constraint[first_index].upper() == pytest.approx(0.0)
        assert block.resource_fuel_consumption_constraint[first_index].lower() == pytest.approx(0.0)
        assert block.resource_fuel_consumption_constraint[first_index].expr()

        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel2", first_index].fix(20)
        assert block.resource_fuel_consumption_constraint[first_index].body() == pytest.approx(-10.0)
        assert block.resource_fuel_consumption_constraint[first_index].upper() == pytest.approx(0.0)
        assert block.resource_fuel_consumption_constraint[first_index].lower() == pytest.approx(0.0)
        assert not block.resource_fuel_consumption_constraint[first_index].expr()

    def test_resource_fuel_cost(
        self,
        make_component_with_block_copy,
        first_index,
    ):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        year, dispatch_window, timestamp = first_index

        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel1", year, dispatch_window, timestamp] = 10
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel2", year, dispatch_window, timestamp] = 10

        assert block.resource_fuel_cost[year, dispatch_window, timestamp].expr() == 3 * 10.0

    def test_annual_total_resource_fuel_cost(
        self,
        make_component_with_block_copy,
    ):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        for i in range(1, 7):
            block.resource_fuel_consumption_in_timepoint_mmbtu[
                "CandidateFuel1", pd.Timestamp("2025-01-01 00:00:00"), block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS[i]
            ] = (10 * i)

        assert block.annual_total_resource_fuel_cost[pd.Timestamp("2025-01-01 00:00:00")].expr() == (
            ((10 * 3 + 20 * 3 + 30 * 3) * 0.6 + (40 * 3 + 50 * 3 + 60 * 3) * 0.4) * 365
        )

    def test_annual_total_operational_cost(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        model = block.model()
        first_year = model.MODELED_YEARS[1]
        last_year = model.MODELED_YEARS[4]

        block.power_output.fix(10)

        for i, (dispatch_window, timestamp) in enumerate(model.DISPATCH_WINDOWS_AND_TIMESTAMPS):
            block.resource_fuel_cost[first_year, dispatch_window, timestamp] = i + 1
            block.resource_fuel_cost[last_year, dispatch_window, timestamp] = i + 10

        assert block.annual_total_operational_cost[first_year].expr() == (
            0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (2 + 2 + 2))
            + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (2 + 2 + 2))
            + 0.6 * 365 * (1 + 2 + 3)
            + 0.4 * 365 * (4 + 5 + 6)
        )

        assert block.annual_total_operational_cost[last_year].expr() == (
            0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (0 + 0 + 0))
            + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (0 + 0 + 0))
            + 0.6 * 365 * (10 + 11 + 12)
            + 0.4 * 365 * (13 + 14 + 15)
        )

    def test_power_output_by_fuel_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        assert resource.fuel_burn_slope == 2.0

        # Check Fuel 1 power output
        block.power_output_by_fuel["CandidateFuel1", first_index].fix(10)
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel1", first_index].fix(20)
        assert block.power_output_by_fuel_constraint["CandidateFuel1", first_index].upper() == 0
        assert block.power_output_by_fuel_constraint["CandidateFuel1", first_index].lower() == 0
        assert block.power_output_by_fuel_constraint["CandidateFuel1", first_index].body() == 0
        assert block.power_output_by_fuel_constraint["CandidateFuel1", first_index].expr()

        # Check Fuel 2 power output
        block.power_output_by_fuel["CandidateFuel2", first_index].fix(20)
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel2", first_index].fix(40)
        assert block.power_output_by_fuel_constraint["CandidateFuel2", first_index].upper() == 0
        assert block.power_output_by_fuel_constraint["CandidateFuel2", first_index].lower() == 0
        assert block.power_output_by_fuel_constraint["CandidateFuel2", first_index].body() == 0
        assert block.power_output_by_fuel_constraint["CandidateFuel2", first_index].expr()

        # Check failures
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel1", first_index].fix(15)
        assert block.power_output_by_fuel_constraint["CandidateFuel1", first_index].body() == 5
        assert not block.power_output_by_fuel_constraint["CandidateFuel1", first_index].expr()
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel2", first_index].fix(50)
        assert block.power_output_by_fuel_constraint["CandidateFuel2", first_index].body() == -10
        assert not block.power_output_by_fuel_constraint["CandidateFuel2", first_index].expr()

    def test_annual_power_output_by_fuel(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year = first_index[0]

        block.power_output_by_fuel["CandidateFuel1", modeled_year, :, :] = 100
        block.power_output_by_fuel["CandidateFuel2", modeled_year, :, :] = 200

        assert (
            block.annual_power_output_by_fuel["CandidateFuel1", modeled_year].expr()
            == 100 * 3 * 0.6 * 365 + 100 * 3 * 0.4 * 365
        )
        assert (
            block.annual_power_output_by_fuel["CandidateFuel2", modeled_year].expr()
            == 200 * 3 * 0.6 * 365 + 200 * 3 * 0.4 * 365
        )


class TestThermalUnitCommitmentResource(test_unit_commitment.TestUnitCommitmentResource, TestThermalResource):
    _COMPONENT_CLASS = ThermalUnitCommitmentResource
    _COMPONENT_NAME = "ThermalUnitCommitmentResource"
    _SYSTEM_COMPONENT_DICT_NAME = "thermal_uc_resources"

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
            "fuel_burn_slope",
            "fuel_burn_intercept",
            "start_fuel_use",
        ]

    def test_annual_total_operational_cost(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.power_output.fix(10)
        block.start_units.fix(4)
        block.shutdown_units.fix(2)
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel1", :, :, :] = 1

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
        ]:
            assert block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (2 + 2 + 2) + (10 * 2 * 3) + (5 * 4 * 3) + (3 * 3))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (2 + 2 + 2) + (10 * 2 * 3) + (5 * 4 * 3) + (3 * 3))
            )

        for year in [
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            assert block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (0 + 0 + 0) + (10 * 2 * 3) + (5 * 4 * 3) + (3 * 3))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (0 + 0 + 0) + (10 * 2 * 3) + (5 * 4 * 3) + (3 * 3))
            )

        assert block.annual_total_operational_cost

    @pytest.mark.parametrize(
        "committed_units, start_units, power_output, fuel_consumption_fuel_1, fuel_consumption_fuel_2, expr, upper, body",
        [
            (5, 3, 4, 15, 5, False, 0, 5 + 4 + 3 * 2 - 20),
            (5, 3, 4, 2, 8, False, 0, 5 + 4 + 3 * 2 - 10),
            (5, 3, 4, 15, 0, True, 0, 0),
        ],
    )
    def test_resource_fuel_consumption_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units,
        start_units,
        power_output,
        fuel_consumption_fuel_1,
        fuel_consumption_fuel_2,
        expr,
        upper,
        body,
    ):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.committed_units[first_index] = committed_units
        block.start_units[first_index] = start_units
        block.power_output[first_index] = power_output

        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel1", first_index] = fuel_consumption_fuel_1
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel2", first_index] = fuel_consumption_fuel_2

        assert block.resource_fuel_consumption_constraint[first_index].expr() == expr
        assert block.resource_fuel_consumption_constraint[first_index].upper() == upper
        assert block.resource_fuel_consumption_constraint[first_index].body() == body

    def test_synchronous_condenser_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy(component_name="ThermalUnitCommitmentResource2")
        block = resource.formulation_block

        assert resource.addition_to_load == 0.1

        block.committed_capacity[first_index] = 5
        block.sync_cond_power_input[first_index] = 0.5
        assert block.synchronous_condenser_constraint[first_index].expr()

        block.committed_capacity[first_index] = 5
        block.sync_cond_power_input[first_index] = 0.6
        assert not block.synchronous_condenser_constraint[first_index].expr()

        block.committed_capacity[first_index] = 10
        block.sync_cond_power_input[first_index] = 0.9
        assert not block.synchronous_condenser_constraint[first_index].expr()

    def test_annual_sync_cond_power_input(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy(component_name="ThermalUnitCommitmentResource2")
        block = resource.formulation_block
        modeled_year = first_index[0]
        assert resource.addition_to_load == 0.1

        for dw, ts in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
            block.sync_cond_power_input[modeled_year, dw, ts] = 1.0

        assert block.annual_sync_cond_power_input[modeled_year].expr() == 1.0 * 3 * 0.6 * 365 + 1.0 * 3 * 0.4 * 365

    @pytest.mark.parametrize(
        "committed_units, start_units, power_output_fuel1, power_output_fuel2, fuel_consumption_fuel_1, fuel_consumption_fuel_2, expr, body",
        [
            (5, 3, 4, 8, 15, 19, True, 0.0),
            (5, 3, 4, 8, 0, 19, True, -15.0),
            (5, 3, 4, 8, 19, 19, False, 4.0),
        ],
    )
    def test_power_output_by_fuel_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units,
        start_units,
        power_output_fuel1,
        power_output_fuel2,
        fuel_consumption_fuel_1,
        fuel_consumption_fuel_2,
        expr,
        body,
    ):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.committed_units[first_index] = committed_units
        block.start_units[first_index] = start_units
        block.power_output_by_fuel["CandidateFuel1", first_index] = power_output_fuel1
        block.power_output_by_fuel["CandidateFuel2", first_index] = power_output_fuel2

        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel1", first_index] = fuel_consumption_fuel_1
        block.resource_fuel_consumption_in_timepoint_mmbtu["CandidateFuel2", first_index] = fuel_consumption_fuel_2

        # Candidate fuel 1 inputs change
        assert block.power_output_by_fuel_constraint["CandidateFuel1", first_index].expr() == expr
        assert block.power_output_by_fuel_constraint["CandidateFuel1", first_index].upper() == 0.0
        assert block.power_output_by_fuel_constraint["CandidateFuel1", first_index].body() == body

        # Candidate fuel 2 stays the same
        assert block.power_output_by_fuel_constraint["CandidateFuel2", first_index].expr()
        assert block.power_output_by_fuel_constraint["CandidateFuel2", first_index].upper() == 0.0
        assert block.power_output_by_fuel_constraint["CandidateFuel2", first_index].body() == 0.0

    def test_total_power_output_by_fuel_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.power_output[first_index].fix(20)
        assert block.total_power_output_by_fuel_constraint[first_index].upper() == 0
        assert block.total_power_output_by_fuel_constraint[first_index].lower() == 0

        # power output by fuel equals total -- constraint holds
        for fuel in resource.candidate_fuels.keys():
            block.power_output_by_fuel[fuel, first_index].fix(10)
        assert block.total_power_output_by_fuel_constraint[first_index].body() == 0
        assert block.total_power_output_by_fuel_constraint[first_index].expr()

        # change total power output -- constraint does not hold
        block.power_output[first_index].fix(25)
        assert block.total_power_output_by_fuel_constraint[first_index].body() == 5
        assert not block.total_power_output_by_fuel_constraint[first_index].expr()


class TestThermalResourceUnitCommitmentSingleUnit(ComponentTestTemplate):
    _COMPONENT_CLASS = ThermalResource
    _COMPONENT_NAME = "ThermalUnitCommitmentResourceSingleUnit"
    _SYSTEM_COMPONENT_DICT_NAME = "thermal_uc_resources"

    @pytest.mark.parametrize(
        "committed_units, committed_capacity, expected_body, expected_expr",
        [
            # If not committed, committed_capacity must be 0 (<= 0*max_potential)
            pytest.param(0, 0.0, 0.0, True, id="not_committed_zero_capacity"),
            pytest.param(0, 10.0, 10.0, False, id="not_committed_positive_capacity_violates"),
            # If committed (1), capacity must be <= fixed max_potential (=300)
            pytest.param(1, 100.0, 100.0 - 300.0, True, id="committed_within_max"),
            pytest.param(1, 300.0, 0.0, True, id="committed_equal_max"),
            pytest.param(1, 310.0, 10.0, False, id="committed_above_max"),
        ],
    )
    def test_committed_capacity_ub(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units,
        committed_capacity,
        expected_body,
        expected_expr,
    ):
        """
        Unit test for UnitCommitmentResource._committed_capacity_ub():
        committed_capacity[yt] <= max_potential[y] * committed_units[yt]

        We directly set/fix the relevant variables and parameters on the resource block and
        verify the constructed constraint's body, bound, and truthiness without solving.
        """
        resource = make_component_with_block_copy()
        b = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Ensure SINGLE_UNIT path is active for committed_capacity var and constraint
        # The fixture should already be configured appropriately in tests; we only set parameters/vars.
        b.committed_units[modeled_year, dispatch_window, timestamp].fix(committed_units)
        b.committed_capacity[modeled_year, dispatch_window, timestamp].fix(committed_capacity)

        c = b.committed_capacity_ub[modeled_year, dispatch_window, timestamp]
        # Upper bound is None for <=; evaluation happens via expr()
        assert c.upper() == 0
        # Body is LHS - RHS
        assert c.body() == expected_body
        # expr(): True if inequality satisfied/binding, False if violated
        assert bool(c.expr()) is expected_expr

    @pytest.mark.parametrize(
        "unit_size, committed_capacity, expected_body, expected_expr",
        [
            # committed_capacity <= unit_size (satisfied)
            pytest.param(100.0, 50.0, 50.0 - 100.0, True, id="below_unit_size"),
            # committed_capacity == unit_size (binding)
            pytest.param(100.0, 100.0, 0.0, True, id="equal_unit_size"),
            # committed_capacity > unit_size (violation)
            pytest.param(100.0, 110.0, 10.0, False, id="above_unit_size"),
        ],
    )
    def test_committed_capacity_unit_size_max(
        self,
        make_component_with_block_copy,
        first_index,
        unit_size,
        committed_capacity,
        expected_body,
        expected_expr,
    ):
        """
        Unit test for UnitCommitmentResource._committed_capacity_unit_size_max():
        committed_capacity[yt] <= unit_size[y]

        For SINGLE_UNIT mode, unit_size is defined as an Expression equal to operational_capacity[year].
        We explicitly set operational_capacity for the modeled year to a chosen unit_size and fix
        committed_capacity, then verify the constraint body and satisfaction.
        """
        resource = make_component_with_block_copy()
        b = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Set the unit size via operational_capacity (since SINGLE_UNIT uses dynamic unit_size Expression)
        b.operational_capacity[modeled_year] = unit_size
        # Fix committed_capacity at the specific timepoint
        b.committed_capacity[modeled_year, dispatch_window, timestamp].fix(committed_capacity)

        c = b.committed_capacity_unit_size_max[modeled_year, dispatch_window, timestamp]
        assert c.upper() == 0
        assert c.body() == expected_body  # LHS - RHS = committed_capacity - unit_size
        assert bool(c.expr()) is expected_expr

    @pytest.mark.parametrize(
        "unit_size, committed_units, committed_capacity, expected_body, expected_expr",
        [
            # When not committed (0), RHS = unit_size - max_potential.
            # With max_potential large (e.g., 300), constraint relaxes; any nonnegative committed_capacity satisfies.
            pytest.param(100.0, 0, 0.0, (100.0 - 300.0) - 0, True, id="not_committed_zero_capacity_relaxed"),
            pytest.param(100.0, 0, 50.0, (100.0 - 300.0) - 50, True, id="not_committed_positive_capacity_relaxed"),
            # When committed (1), constraint enforces committed_capacity >= unit_size.
            pytest.param(100.0, 1, 90.0, 100.0 - 90, False, id="committed_below_unit_size"),
            pytest.param(100.0, 1, 100.0, 0.0, True, id="committed_equal_unit_size"),
            pytest.param(100.0, 1, 120.0, -20.0, True, id="committed_above_unit_size"),
        ],
    )
    def test_committed_capacity_unit_size_min(
        self,
        make_component_with_block_copy,
        first_index,
        unit_size,
        committed_units,
        committed_capacity,
        expected_body,
        expected_expr,
    ):
        """
        Unit test for UnitCommitmentResource._committed_capacity_unit_size_min():
        committed_capacity[yt] >= unit_size[y] - max_potential[y] * (1 - committed_units[yt])

        For SINGLE_UNIT, unit_size is dynamic via operational_capacity. We set operational_capacity,
        max_potential for the modeled year, fix committed_units and committed_capacity, and verify the
        constraint body/value and truthiness.
        """
        resource = make_component_with_block_copy()
        b = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Configure parameters/expressions
        b.operational_capacity[modeled_year] = unit_size

        # Fix variables
        b.committed_units[modeled_year, dispatch_window, timestamp].fix(committed_units)
        b.committed_capacity[modeled_year, dispatch_window, timestamp].fix(committed_capacity)

        c = b.committed_capacity_unit_size_min[modeled_year, dispatch_window, timestamp]
        # Lower-bound constraint has lower() == 0 after moving all to LHS
        assert c.upper() == 0
        # Body is LHS - RHS
        assert c.body() == expected_body
        assert bool(c.expr()) is expected_expr


class TestThermalResourceGroup(test_generic.TestGenericResourceGroup, TestThermalResource):
    _COMPONENT_CLASS = ThermalResourceGroup
    _COMPONENT_NAME = "thermal_resource_group_0"
    _SYSTEM_COMPONENT_DICT_NAME = "thermal_resource_groups"
