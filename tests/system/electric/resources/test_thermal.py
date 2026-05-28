import copy

import pandas as pd
import pyomo.environ as pyo
import pytest

from resolve.core.model import ModelTemplate
from resolve.system import ThermalResourceGroup
from resolve.system.electric.resources import ThermalResource
from resolve.system.electric.resources.thermal import ThermalUnitCommitmentResource
from tests.system.component_test_template import ComponentTestTemplate
from tests.system.electric.resources import test_generic
from tests.system.electric.resources import test_unit_commitment


def _resample_system_for_temporal_settings(system, temporal_settings):
    modeled_years = temporal_settings.modeled_years.data.loc[temporal_settings.modeled_years.data.values].index
    system.resample_ts_attributes(
        modeled_years=(min(modeled_years).year, max(modeled_years).year),
        weather_years=(
            min(temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
            max(temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
        ),
    )


@pytest.mark.parametrize("construct_costs", [True, False])
def test_thermal_resources_construct_with_and_without_costs(test_system, test_temporal_settings, construct_costs):
    system = test_system.copy()
    _resample_system_for_temporal_settings(system, test_temporal_settings)

    model = ModelTemplate(
        system=system,
        temporal_settings=test_temporal_settings,
        construct_investment_rules=True,
        construct_operational_rules=True,
        construct_costs=construct_costs,
    )

    resources = [
        model.system.thermal_resources["ThermalResource1"],
        model.system.thermal_resources["ThermalResource2"],
        model.system.thermal_uc_resources["ThermalUnitCommitmentResource"],
        model.system.thermal_uc_resources["ThermalUnitCommitmentResource2"],
    ]
    for resource in resources:
        block = resource.formulation_block
        assert hasattr(block, "annual_power_output_by_fuel")
        if len(resource.candidate_fuels) > 1:
            assert hasattr(block, "power_output_by_fuel")
            assert hasattr(block, "power_output_by_fuel_constraint")
        else:
            assert not hasattr(block, "power_output_by_fuel")
            assert not hasattr(block, "power_output_by_fuel_constraint")

        if construct_costs:
            assert hasattr(block, "annual_total_resource_fuel_cost")
        else:
            assert not hasattr(block, "annual_total_resource_fuel_cost")


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
            0.6 * 365 * (10 * (10 + 5 + 12) - 10 * (0 + 0 + 0))
            + 0.4 * 365 * (10 * (-20 + 2 + 6) - 10 * (0 + 0 + 0))
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

    def test_multi_fuel_power_output_by_fuel_components(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        assert len(resource.candidate_fuels) > 1
        assert hasattr(block, "power_output_by_fuel")
        assert hasattr(block, "power_output_by_fuel_constraint")
        assert hasattr(block, "annual_power_output_by_fuel")

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

    def test_single_fuel_annual_power_output_by_fuel_falls_back_to_aggregate(
        self, make_component_with_block_copy, first_index
    ):
        component_names = {
            "thermal_resources": "ThermalResource2",
            "thermal_uc_resources": "ThermalUnitCommitmentResource2",
        }
        if self._SYSTEM_COMPONENT_DICT_NAME not in component_names:
            pytest.skip("Single-fuel fallback is tested on individual thermal resources.")
        component_name = component_names[self._SYSTEM_COMPONENT_DICT_NAME]
        resource = make_component_with_block_copy(component_name=component_name)
        block = resource.formulation_block
        modeled_year = first_index[0]
        candidate_fuel = next(iter(resource.candidate_fuels))

        assert len(resource.candidate_fuels) == 1
        assert not hasattr(block, "power_output_by_fuel")
        assert not hasattr(block, "power_output_by_fuel_constraint")
        assert hasattr(block, "annual_power_output_by_fuel")

        block.power_output[modeled_year, :, :] = 100

        assert (
            block.annual_power_output_by_fuel[candidate_fuel, modeled_year].expr()
            == block.power_output_annual[modeled_year].expr()
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
                0.6 * 365 * (10 * (10 + 5 + 12) - 10 * (0 + 0 + 0) + (20 * 2 * 3) + (10 * 4 * 3) + (3 * 3))
                + 0.4 * 365 * (10 * (-20 + 2 + 6) - 10 * (0 + 0 + 0) + (20 * 2 * 3) + (10 * 4 * 3) + (3 * 3))
            )

        assert block.annual_total_operational_cost

    def test_commitment_tracking_constraint(self, make_component_with_block_copy, first_index):
        """Thermal UC skips aggregate tracking because fuel-level tracking implies it."""
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        assert len(block.commitment_tracking_constraint) == 0
        with pytest.raises(KeyError):
            block.commitment_tracking_constraint[first_index]

    def test_single_fuel_commitment_tracking_uses_aggregate_state(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy(component_name="ThermalUnitCommitmentResource2")
        block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        next_timestamp = block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].nextw(timestamp)
        next_index = (modeled_year, dispatch_window, next_timestamp)

        assert len(resource.candidate_fuels) == 1
        assert not hasattr(block, "committed_units_by_fuel")
        assert not hasattr(block, "start_units_by_fuel")
        assert not hasattr(block, "shutdown_units_by_fuel")
        assert not hasattr(block, "committed_units_by_fuel_tracking_constraint")
        assert not hasattr(block, "power_output_by_fuel")
        assert not hasattr(block, "sync_cond_power_input_by_fuel")
        assert hasattr(block, "annual_sync_cond_power_input_by_fuel")
        assert len(block.commitment_tracking_constraint) > 0

        block.committed_units[first_index] = 1
        block.committed_units[next_index] = 2
        block.start_units[next_index] = 1
        block.shutdown_units[next_index] = 0
        assert block.commitment_tracking_constraint[first_index].expr()

        block.shutdown_units[next_index] = 1
        assert not block.commitment_tracking_constraint[first_index].expr()

    def test_commitment_tracking_inter_period(self, make_component_with_block_copy_inter_period_sharing):
        """Thermal UC skips aggregate inter-period tracking because fuel-level tracking implies it."""
        resource = make_component_with_block_copy_inter_period_sharing()
        block = resource.formulation_block
        modeled_year = pd.Timestamp("2025-01-01")
        first_index = (modeled_year, pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00"))
        constraint_index = (modeled_year, pd.Timestamp("2012-01-02"))

        assert len(block.commitment_tracking_constraint) == 0
        assert len(block.commitment_tracking_inter_period_constraint) == 0

        with pytest.raises(KeyError):
            block.commitment_tracking_constraint[first_index]
        with pytest.raises(KeyError):
            block.commitment_tracking_inter_period_constraint[constraint_index]

        assert hasattr(block, "committed_units_by_fuel_tracking_inter_period_constraint")

    def test_single_fuel_commitment_tracking_inter_period_uses_aggregate_state(self, test_model_inter_period_sharing):
        resource = copy.deepcopy(
            test_model_inter_period_sharing.system.thermal_uc_resources["ThermalUnitCommitmentResource2"]
        )
        block = resource.formulation_block
        modeled_year = pd.Timestamp("2025-01-01")
        first_index = (modeled_year, pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00"))
        next_index = (modeled_year, pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00"))
        constraint_index = (modeled_year, pd.Timestamp("2012-01-02"))

        assert len(resource.candidate_fuels) == 1
        assert len(block.commitment_tracking_constraint) > 0
        assert len(block.commitment_tracking_inter_period_constraint) > 0
        assert not hasattr(block, "committed_units_by_fuel_tracking_inter_period_constraint")

        block.committed_units[first_index] = 1
        block.committed_units[next_index] = 2
        block.start_units[next_index] = 1
        block.shutdown_units[next_index] = 0
        assert block.commitment_tracking_inter_period_constraint[constraint_index].expr()

        block.shutdown_units[next_index] = 1
        assert not block.commitment_tracking_inter_period_constraint[constraint_index].expr()

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

    def test_single_fuel_resource_fuel_consumption_constraint_uses_aggregate_uc_state(
        self, make_component_with_block_copy, first_index
    ):
        resource = make_component_with_block_copy(component_name="ThermalUnitCommitmentResource2")
        block = resource.formulation_block
        candidate_fuel = next(iter(resource.candidate_fuels))

        block.committed_units[first_index] = 5
        block.start_units[first_index] = 3
        block.power_output[first_index] = 4
        block.resource_fuel_consumption_in_timepoint_mmbtu[candidate_fuel, first_index] = 15

        assert block.resource_fuel_consumption_constraint[first_index].expr()
        assert block.resource_fuel_consumption_constraint[first_index].body() == 0

        block.resource_fuel_consumption_in_timepoint_mmbtu[candidate_fuel, first_index] = 14
        assert not block.resource_fuel_consumption_constraint[first_index].expr()
        assert block.resource_fuel_consumption_constraint[first_index].body() == 1

    def test_sync_cond_power_input_by_fuel(self, make_custom_component_with_block, first_index):
        """Test fuel-specific synchronous condenser input expression.

        Args:
            make_custom_component_with_block: Fixture that creates a custom resource with a Pyomo block.
            first_index: First modeled-year, dispatch-window, timestamp index tuple.
        """
        resource = make_custom_component_with_block(addition_to_load=0.1)
        block = resource.formulation_block
        candidate_fuel = "CandidateFuel1"

        assert resource.addition_to_load == 0.1

        block.committed_units_by_fuel[candidate_fuel, first_index] = 2
        assert pyo.value(block.sync_cond_power_input_by_fuel[candidate_fuel, first_index]) == 10
        assert not hasattr(block, "synchronous_condenser_by_fuel_constraint")

    def test_synchronous_condenser_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy(component_name="ThermalUnitCommitmentResource2")
        block = resource.formulation_block
        modeled_year = first_index[0]
        sync_cond_power_input_per_committed_unit = resource.addition_to_load * pyo.value(block.unit_size[modeled_year])

        block.committed_units[first_index] = 0.5 / sync_cond_power_input_per_committed_unit
        block.sync_cond_power_input[first_index] = 0.5
        assert block.synchronous_condenser_constraint[first_index].expr()

        block.sync_cond_power_input[first_index] = 0.6
        assert not block.synchronous_condenser_constraint[first_index].expr()

    def test_annual_sync_cond_power_input(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy(component_name="ThermalUnitCommitmentResource2")
        block = resource.formulation_block
        modeled_year = first_index[0]
        candidate_fuel = next(iter(resource.candidate_fuels))

        annual_weighted_hours = 3 * 0.6 * 365 + 3 * 0.4 * 365

        for dw, ts in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
            block.sync_cond_power_input[modeled_year, dw, ts] = 1.0

        assert block.annual_sync_cond_power_input_by_fuel[candidate_fuel, modeled_year].expr() == annual_weighted_hours
        assert block.annual_sync_cond_power_input[modeled_year].expr() == annual_weighted_hours

    def test_multi_fuel_annual_sync_cond_power_input(self, make_custom_component_with_block, first_index):
        resource = make_custom_component_with_block(addition_to_load=0.1)
        block = resource.formulation_block
        modeled_year = first_index[0]
        sync_cond_power_input_per_committed_unit = resource.addition_to_load * pyo.value(block.unit_size[modeled_year])
        annual_weighted_hours = 3 * 0.6 * 365 + 3 * 0.4 * 365

        for dw, ts in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
            block.committed_units_by_fuel["CandidateFuel1", modeled_year, dw, ts] = (
                1.0 / sync_cond_power_input_per_committed_unit
            )
            block.committed_units_by_fuel["CandidateFuel2", modeled_year, dw, ts] = (
                2.0 / sync_cond_power_input_per_committed_unit
            )
            block.committed_units[modeled_year, dw, ts] = 3.0 / sync_cond_power_input_per_committed_unit
            block.sync_cond_power_input[modeled_year, dw, ts] = 3.0

        fuel_1_annual = block.annual_sync_cond_power_input_by_fuel["CandidateFuel1", modeled_year].expr()
        fuel_2_annual = block.annual_sync_cond_power_input_by_fuel["CandidateFuel2", modeled_year].expr()

        assert fuel_1_annual == annual_weighted_hours
        assert fuel_2_annual == 2 * annual_weighted_hours
        assert block.annual_sync_cond_power_input[modeled_year].expr() == fuel_1_annual + fuel_2_annual

    def test_uc_state_by_fuel_sum_constraints(self, make_component_with_block_copy, first_index):
        """Test that fuel-specific unit commitment states sum to total states.

        Args:
            make_component_with_block_copy: Fixture that creates a resource with a Pyomo block.
            first_index: First modeled-year, dispatch-window, timestamp index tuple.
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.committed_units[first_index] = 5
        block.start_units[first_index] = 3
        block.shutdown_units[first_index] = 2

        block.committed_units_by_fuel["CandidateFuel1", first_index] = 2
        block.committed_units_by_fuel["CandidateFuel2", first_index] = 3
        block.start_units_by_fuel["CandidateFuel1", first_index] = 1
        block.start_units_by_fuel["CandidateFuel2", first_index] = 2
        block.shutdown_units_by_fuel["CandidateFuel1", first_index] = 1
        block.shutdown_units_by_fuel["CandidateFuel2", first_index] = 1

        assert block.committed_units_by_fuel_sum_constraint[first_index].expr()
        assert block.start_units_by_fuel_sum_constraint[first_index].expr()
        assert block.shutdown_units_by_fuel_sum_constraint[first_index].expr()

        block.shutdown_units_by_fuel["CandidateFuel2", first_index] = 0
        assert not block.shutdown_units_by_fuel_sum_constraint[first_index].expr()

    def test_committed_units_by_fuel_tracking_constraint(self, make_component_with_block_copy, first_index):
        """Fuel-level tracking plus sum constraints imply aggregate tracking."""
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        next_timestamp = block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].nextw(timestamp)
        next_index = (modeled_year, dispatch_window, next_timestamp)

        block.committed_units[first_index] = 3
        block.committed_units[next_index] = 4
        block.start_units[next_index] = 2
        block.shutdown_units[next_index] = 1

        block.committed_units_by_fuel["CandidateFuel1", modeled_year, dispatch_window, timestamp] = 1
        block.committed_units_by_fuel["CandidateFuel1", modeled_year, dispatch_window, next_timestamp] = 2
        block.start_units_by_fuel["CandidateFuel1", modeled_year, dispatch_window, next_timestamp] = 1
        block.shutdown_units_by_fuel["CandidateFuel1", modeled_year, dispatch_window, next_timestamp] = 0
        block.committed_units_by_fuel["CandidateFuel2", modeled_year, dispatch_window, timestamp] = 2
        block.committed_units_by_fuel["CandidateFuel2", modeled_year, dispatch_window, next_timestamp] = 2
        block.start_units_by_fuel["CandidateFuel2", modeled_year, dispatch_window, next_timestamp] = 1
        block.shutdown_units_by_fuel["CandidateFuel2", modeled_year, dispatch_window, next_timestamp] = 1

        assert block.committed_units_by_fuel_tracking_constraint[
            "CandidateFuel1", modeled_year, dispatch_window, timestamp
        ].expr()
        assert block.committed_units_by_fuel_tracking_constraint[
            "CandidateFuel2", modeled_year, dispatch_window, timestamp
        ].expr()
        assert block.committed_units_by_fuel_sum_constraint[first_index].expr()
        assert block.committed_units_by_fuel_sum_constraint[next_index].expr()
        assert block.start_units_by_fuel_sum_constraint[next_index].expr()
        assert block.shutdown_units_by_fuel_sum_constraint[next_index].expr()
        assert (
            pyo.value(
                block.committed_units[next_index]
                - block.committed_units[first_index]
                - block.start_units[next_index]
                + block.shutdown_units[next_index]
            )
            == 0
        )

        block.shutdown_units_by_fuel["CandidateFuel1", modeled_year, dispatch_window, next_timestamp] = 1
        assert not block.committed_units_by_fuel_tracking_constraint[
            "CandidateFuel1", modeled_year, dispatch_window, timestamp
        ].expr()

    def test_committed_units_by_fuel_tracking_inter_period_constraint(
        self, make_component_with_block_copy_inter_period_sharing
    ):
        """Inter-period fuel-level tracking plus sum constraints imply aggregate tracking."""
        resource = make_component_with_block_copy_inter_period_sharing()
        block = resource.formulation_block
        modeled_year = pd.Timestamp("2025-01-01")
        first_index = (modeled_year, pd.Timestamp("2012-02-15"), pd.Timestamp("2012-02-15 14:00"))
        next_index = (modeled_year, pd.Timestamp("2010-06-21"), pd.Timestamp("2010-06-21 00:00"))
        constraint_index = (modeled_year, pd.Timestamp("2012-01-02"))

        block.committed_units[first_index] = 3
        block.committed_units[next_index] = 4
        block.start_units[next_index] = 2
        block.shutdown_units[next_index] = 1

        block.committed_units_by_fuel["CandidateFuel1", first_index] = 1
        block.committed_units_by_fuel["CandidateFuel1", next_index] = 2
        block.start_units_by_fuel["CandidateFuel1", next_index] = 1
        block.shutdown_units_by_fuel["CandidateFuel1", next_index] = 0
        block.committed_units_by_fuel["CandidateFuel2", first_index] = 2
        block.committed_units_by_fuel["CandidateFuel2", next_index] = 2
        block.start_units_by_fuel["CandidateFuel2", next_index] = 1
        block.shutdown_units_by_fuel["CandidateFuel2", next_index] = 1

        assert block.committed_units_by_fuel_tracking_inter_period_constraint["CandidateFuel1", constraint_index].expr()
        assert block.committed_units_by_fuel_tracking_inter_period_constraint["CandidateFuel2", constraint_index].expr()
        assert block.committed_units_by_fuel_sum_constraint[first_index].expr()
        assert block.committed_units_by_fuel_sum_constraint[next_index].expr()
        assert block.start_units_by_fuel_sum_constraint[next_index].expr()
        assert block.shutdown_units_by_fuel_sum_constraint[next_index].expr()
        assert (
            pyo.value(
                block.committed_units[next_index]
                - block.committed_units[first_index]
                - block.start_units[next_index]
                + block.shutdown_units[next_index]
            )
            == 0
        )

    @pytest.mark.parametrize(
        "committed_units_fuel1, start_units_fuel1, power_output_fuel1, power_output_fuel2, fuel_consumption_fuel_1, fuel_consumption_fuel_2, expr, body",
        [
            (5, 3, 4, 8, 15, 19, True, 0.0),
            (5, 3, 4, 8, 19, 19, False, -4.0),
            (5, 3, 4, 8, 10, 19, False, 5.0),
        ],
    )
    def test_power_output_by_fuel_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units_fuel1,
        start_units_fuel1,
        power_output_fuel1,
        power_output_fuel2,
        fuel_consumption_fuel_1,
        fuel_consumption_fuel_2,
        expr,
        body,
    ):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.committed_units_by_fuel["CandidateFuel1", first_index] = committed_units_fuel1
        block.start_units_by_fuel["CandidateFuel1", first_index] = start_units_fuel1
        block.committed_units_by_fuel["CandidateFuel2", first_index] = 5
        block.start_units_by_fuel["CandidateFuel2", first_index] = 3
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

    def test_power_output_by_fuel_max_constraint(self, make_component_with_block_copy, first_index):
        """Test the maximum fuel-specific power output constraint.

        Args:
            make_component_with_block_copy: Fixture that creates a resource with a Pyomo block.
            first_index: First modeled-year, dispatch-window, timestamp index tuple.
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.committed_units_by_fuel["CandidateFuel1", first_index] = 0
        block.power_output_by_fuel["CandidateFuel1", first_index] = 1

        assert block.power_output_by_fuel_max_constraint["CandidateFuel1", first_index].body() == 1
        assert not block.power_output_by_fuel_max_constraint["CandidateFuel1", first_index].expr()

        block.committed_units_by_fuel["CandidateFuel1", first_index] = 1
        assert block.power_output_by_fuel_max_constraint["CandidateFuel1", first_index].body() == -49
        assert block.power_output_by_fuel_max_constraint["CandidateFuel1", first_index].expr()

    def test_power_output_by_fuel_min_constraint(self, make_component_with_block_copy, first_index):
        """Test the minimum fuel-specific power output constraint.

        Args:
            make_component_with_block_copy: Fixture that creates a resource with a Pyomo block.
            first_index: First modeled-year, dispatch-window, timestamp index tuple.
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.committed_units_by_fuel["CandidateFuel1", first_index] = 0
        block.power_output_by_fuel["CandidateFuel1", first_index] = 0

        assert block.power_output_by_fuel_min_constraint["CandidateFuel1", first_index].body() == 0
        assert block.power_output_by_fuel_min_constraint["CandidateFuel1", first_index].expr()

        block.committed_units_by_fuel["CandidateFuel1", first_index] = 1
        block.power_output_by_fuel["CandidateFuel1", first_index] = 24
        assert block.power_output_by_fuel_min_constraint["CandidateFuel1", first_index].body() == 1
        assert not block.power_output_by_fuel_min_constraint["CandidateFuel1", first_index].expr()

        block.power_output_by_fuel["CandidateFuel1", first_index] = 25
        assert block.power_output_by_fuel_min_constraint["CandidateFuel1", first_index].body() == 0
        assert block.power_output_by_fuel_min_constraint["CandidateFuel1", first_index].expr()

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
