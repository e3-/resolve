import copy

import pandas as pd
import pytest

import new_modeling_toolkit.core.temporal.timeseries as ts
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.system import VariableResourceGroup
from new_modeling_toolkit.system.electric.resources import VariableResource
from tests.system.electric.resources import test_generic


class TestVariableResource(test_generic.TestGenericResource):
    """This class holds tests for VariableResource functionality, but these tests cannot be run directly because
    VariableResource is an abstract class. However, the test classes for all classes that inherit from
    VariableResource should also inherit from this class, so that the tests will be run."""

    _COMPONENT_CLASS = VariableResource
    _COMPONENT_NAME = "Does Not Exist"
    _SYSTEM_COMPONENT_DICT_NAME = "variable_resources"

    @pytest.fixture(scope="class")
    def make_component_with_block_copy_non_curtailable(self, test_system, test_temporal_settings):
        system_copy = test_system.copy()
        asset = getattr(system_copy, self._SYSTEM_COMPONENT_DICT_NAME)[self._COMPONENT_NAME]
        asset.curtailable = False

        # Resample the timeseries attributes of the System to ensure data is interpolated and extrapolated correctly
        #  to cover all required model years and weather years
        modeled_years = test_temporal_settings.modeled_years.data.loc[
            test_temporal_settings.modeled_years.data.values
        ].index
        system_copy.resample_ts_attributes(
            modeled_years=(min(modeled_years).year, max(modeled_years).year),
            weather_years=(
                min(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
                max(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
            ),
        )

        # Construct the model
        model = ModelTemplate(
            system=system_copy,
            temporal_settings=test_temporal_settings,
            construct_investment_rules=True,
            construct_operational_rules=True,
            construct_costs=True,
        )

        def _make_custom_asset():
            asset_copy = copy.deepcopy(asset)
            return asset_copy

        return _make_custom_asset

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
            "curtailment_cost",
            "curtailable",
        ]

    def test_results_reporting(self, make_component_with_block_copy):
        super().test_results_reporting(make_component_with_block_copy)
        resource = make_component_with_block_copy()
        resource._construct_output_expressions(construct_costs=True)

        assert resource.formulation_block.scheduled_curtailment.doc == "Curtailed Energy (MWh)"
        assert resource.formulation_block.annual_total_scheduled_curtailment.doc == "Annual Curtailed Energy (MWh)"
        assert resource.formulation_block.resource_curtailment_cost_in_timepoint.doc == "Curtailment Cost ($)"
        assert resource.formulation_block.annual_total_curtailment_cost.doc == "Annual Curtailment Cost ($)"

    def update_block_for_expression_tests(self, block):
        """
        Hard code values to the selected capacity (updating the power_output_max) and power_output at selected indices.
        """
        block.selected_capacity.fix(0)
        block.power_output.fix(20)

        return block

    def test_scheduled_curtailment(self, make_component_with_block_copy):
        """
        Test the scheduled_curtailment expression.
        After assigning values to power_output and power_output_max, assert that the expression values are expected.
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.operational_capacity[pd.Timestamp("2025-01-01")] = 100
        block.operational_capacity[pd.Timestamp("2030-01-01")] = 100
        block.power_output.fix(20)

        assert block.scheduled_curtailment[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
        ].expr() == pytest.approx(80.0)

        assert block.scheduled_curtailment[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
            pd.Timestamp("2010-06-21 01:00:00"),
        ].expr() == pytest.approx(60.0)

        assert block.scheduled_curtailment[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
            pd.Timestamp("2010-06-21 02:00:00"),
        ].expr() == pytest.approx(30.0)

        assert block.scheduled_curtailment[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2012-02-15 00:00:00"),
            pd.Timestamp("2012-02-15 12:00:00"),
        ].expr() == pytest.approx(30.0)

        assert block.scheduled_curtailment[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2012-02-15 00:00:00"),
            pd.Timestamp("2012-02-15 13:00:00"),
        ].expr() == pytest.approx(10.0)

        assert block.scheduled_curtailment[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2012-02-15 00:00:00"),
            pd.Timestamp("2012-02-15 14:00:00"),
        ].expr() == pytest.approx(50.0)

        assert block.scheduled_curtailment[
            pd.Timestamp("2030-01-01 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
        ].expr() == pytest.approx(80.0)

    def test_annual_total_scheduled_curtailment(self, make_component_with_block_copy):
        """
        Test the annual_total_scheduled_curtailment expression.
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        block.operational_capacity[pd.Timestamp("2025-01-01")] = 100
        block.power_output.fix(20)

        assert block.annual_total_scheduled_curtailment[pd.Timestamp("2025-01-01 00:00:00")].expr() == pytest.approx(
            ((80 + 60 + 30) * 0.6 + (30 + 10 + 50) * 0.4) * 365
        )

    def test_resource_curtailment_cost_in_timepoint(self, make_component_with_block_copy):
        """
        Test the resource_curtailment_cost_in_timepoint expression.
        After assigning values to power_output and power_output_max, assert that the expression values are expected.
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.operational_capacity[pd.Timestamp("2025-01-01")] = 100
        block.operational_capacity[pd.Timestamp("2030-01-01")] = 100
        block.power_output.fix(20)

        assert block.resource_curtailment_cost_in_timepoint[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
        ].expr() == pytest.approx(240.0)

        assert block.resource_curtailment_cost_in_timepoint[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
            pd.Timestamp("2010-06-21 01:00:00"),
        ].expr() == pytest.approx(180.0)

        assert block.resource_curtailment_cost_in_timepoint[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
            pd.Timestamp("2010-06-21 02:00:00"),
        ].expr() == pytest.approx(90.0)

        assert block.resource_curtailment_cost_in_timepoint[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2012-02-15 00:00:00"),
            pd.Timestamp("2012-02-15 12:00:00"),
        ].expr() == pytest.approx(90.0)

        assert block.resource_curtailment_cost_in_timepoint[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2012-02-15 00:00:00"),
            pd.Timestamp("2012-02-15 13:00:00"),
        ].expr() == pytest.approx(30.0)

        assert block.resource_curtailment_cost_in_timepoint[
            pd.Timestamp("2025-01-01 00:00:00"),
            pd.Timestamp("2012-02-15 00:00:00"),
            pd.Timestamp("2012-02-15 14:00:00"),
        ].expr() == pytest.approx(150.0)

        assert block.resource_curtailment_cost_in_timepoint[
            pd.Timestamp("2030-01-01 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
            pd.Timestamp("2010-06-21 00:00:00"),
        ].expr() == pytest.approx(160.0)

    def test_annual_total_curtailment_cost(self, make_component_with_block_copy):
        """
        Test the annual_total_curtailment_cost expression.
        After assigning values to power_output and power_output_max, assert that the expression value for the
        first model year is expected based on the dispatch window weights and number of days in the year.
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        block.operational_capacity[pd.Timestamp("2025-01-01")] = 100
        block.power_output.fix(20)

        assert block.annual_total_curtailment_cost[pd.Timestamp("2025-01-01 00:00:00")].expr() == pytest.approx(
            ((240 + 180 + 90) * 0.6 + (90 + 30 + 150) * 0.4) * 365
        )

    def test_annual_total_operational_cost(
        self, make_component_with_block_copy, make_component_with_block_copy_non_curtailable
    ):
        """
        Test the annual_total_operational_cost expression for both curtailable and non-curtailable variable resource.
        Assert that expression is the expected value of definition defined in Asset class plus the annual total curtailment cost.
        """

        curtailable_resource = make_component_with_block_copy()
        curtailable_block = curtailable_resource.formulation_block
        curtailable_block.operational_capacity[pd.Timestamp("2025-01-01")] = 100
        curtailable_block.operational_capacity[pd.Timestamp("2030-01-01")] = 100
        curtailable_block.operational_capacity[pd.Timestamp("2035-01-01")] = 100
        curtailable_block.operational_capacity[pd.Timestamp("2045-01-01")] = 100
        curtailable_block.power_output.fix(10)

        non_curtailable_resource = make_component_with_block_copy_non_curtailable()
        non_curtailable_block = non_curtailable_resource.formulation_block
        non_curtailable_block.operational_capacity[pd.Timestamp("2025-01-01")] = 100
        non_curtailable_block.operational_capacity[pd.Timestamp("2030-01-01")] = 100
        non_curtailable_block.operational_capacity[pd.Timestamp("2035-01-01")] = 100
        non_curtailable_block.operational_capacity[pd.Timestamp("2045-01-01")] = 100
        non_curtailable_block.power_output.fix(10)

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
        ]:
            assert non_curtailable_block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (2 + 2 + 2))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (2 + 2 + 2))
            )

            assert curtailable_block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (2 + 2 + 2))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (2 + 2 + 2))
            ) + (curtailable_block.annual_total_curtailment_cost[year].expr())

        for year in [
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            assert non_curtailable_block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (0 + 0 + 0))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (0 + 0 + 0))
            )

            assert curtailable_block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (0 + 0 + 0))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (0 + 0 + 0))
            ) + (curtailable_block.annual_total_curtailment_cost[year].expr())

    def test_expressions_for_non_curtailable_resource(
        self,
        make_component_with_block_copy_non_curtailable,
    ):
        """
        Test the expressions for a non-curtailable variable resource. Assert that the expressions are not initialized.
        """
        resource = make_component_with_block_copy_non_curtailable()
        with pytest.raises(AttributeError):
            scheduled_curtailment = resource.formulation_block.scheduled_curtailment
            total_scheduled_curtailment = resource.formulation_block.annual_total_scheduled_curtailment
            resource_curtailment_cost = resource.formulation_block.resource_curtailment_cost_in_timepoint
            total_curtailment_cost = resource.formulation_block.annual_total_curtailment_cost

            assert scheduled_curtailment is None
            assert total_scheduled_curtailment is None
            assert resource_curtailment_cost is None
            assert total_curtailment_cost is None

    def test_provide_power_curtailment_constraint(
        self,
        make_custom_component_with_block,
    ):
        """
        Test the Provide_Power_Curtailment_Constraint.  After assigning values to power_output and power_output_max,
        assert that the constraint lower and upper bounds are zero, and that the constraint holds.
        """
        resource = make_custom_component_with_block(
            curtailable=False,
            energy_budget_daily=None,
        )
        block = resource.formulation_block
        model = block.model()

        # fix variables in body of constraint
        block.operational_capacity[pd.Timestamp("2025-01-01")] = 100

        for i in range(1, 7):
            block.power_output[pd.Timestamp("2025-01-01 00:00:00"), model.DISPATCH_WINDOWS_AND_TIMESTAMPS[i]].fix(
                block.power_output_max[
                    pd.Timestamp("2025-01-01 00:00:00"),
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS[i],
                ].expr()
            )

        for dw, ts in model.DISPATCH_WINDOWS_AND_TIMESTAMPS:
            assert block.provide_power_curtailment_constraint[
                pd.Timestamp("2025-01-01 00:00:00"),
                dw,
                ts,
            ].body() == pytest.approx(0.0)

            assert block.provide_power_curtailment_constraint[
                pd.Timestamp("2025-01-01 00:00:00"),
                dw,
                ts,
            ].upper() == pytest.approx(0.0)

            assert block.provide_power_curtailment_constraint[
                pd.Timestamp("2025-01-01 00:00:00"),
                dw,
                ts,
            ].upper() == pytest.approx(0.0)

            assert block.provide_power_curtailment_constraint[
                pd.Timestamp("2025-01-01 00:00:00"),
                dw,
                ts,
            ].expr()

    def test_provide_power_curtailment_constraint_for_curtailable_resource(
        self,
        make_component_with_block_copy,
    ):
        """
        Test the Provide_Power_Curtailment_Constraint for a curtailable variable resource.
        Assert that the constraint is not initialized.
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        with pytest.raises(AttributeError):
            result = block.provide_power_curtailment_constraint
            assert result is None

    def test_provide_power_curtailment_constraint_for_no_daily_energy_budget(
        self,
        make_custom_component_with_block,
    ):
        """
        Test the Provide_Power_Curtailment_Constraint for a variable resource with undefined energy_budget_daily.
        Assert that the constraint is not initialized.
        """
        resource = make_custom_component_with_block(energy_budget_daily=None)
        with pytest.raises(AttributeError):
            result = resource.formulation_block.provide_power_curtailment_constraint
            assert result is None

    def test_get_sampled_profile_cf(self, make_component_copy, test_temporal_settings_full_day):
        resource = make_component_copy()
        test_temporal_settings_full_day = copy.deepcopy(test_temporal_settings_full_day)
        data = ts.NumericTimeseries(
            name="annual_energy_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-06-21 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2010-06-21 03:00",
                        "2010-06-21 04:00",
                        "2010-06-21 05:00",
                        "2010-06-21 06:00",
                        "2010-06-21 07:00",
                        "2010-06-21 08:00",
                        "2010-06-21 09:00",
                        "2010-06-21 10:00",
                        "2010-06-21 11:00",
                        "2010-06-21 12:00",
                        "2010-06-21 13:00",
                        "2010-06-21 14:00",
                        "2010-06-21 15:00",
                        "2010-06-21 16:00",
                        "2010-06-21 17:00",
                        "2010-06-21 18:00",
                        "2010-06-21 19:00",
                        "2010-06-21 20:00",
                        "2010-06-21 21:00",
                        "2010-06-21 22:00",
                        "2010-06-21 23:00",
                        "2012-02-15 00:00",
                        "2012-02-15 01:00",
                        "2012-02-15 02:00",
                        "2012-02-15 03:00",
                        "2012-02-15 04:00",
                        "2012-02-15 05:00",
                        "2012-02-15 06:00",
                        "2012-02-15 07:00",
                        "2012-02-15 08:00",
                        "2012-02-15 09:00",
                        "2012-02-15 10:00",
                        "2012-02-15 11:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                        "2012-02-15 15:00",
                        "2012-02-15 16:00",
                        "2012-02-15 17:00",
                        "2012-02-15 18:00",
                        "2012-02-15 19:00",
                        "2012-02-15 20:00",
                        "2012-02-15 21:00",
                        "2012-02-15 22:00",
                        "2012-02-15 23:00",
                    ],
                    name="timestamp",
                ),
                data=[
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                ],
                name="value",
            ),
        )
        cf = resource.get_sampled_profile_cf(data, test_temporal_settings_full_day)
        assert cf == 0.6875

    def test_update_resource_profiles(
        self, make_component_copy, test_temporal_settings_full_day, dir_structure, monkeypatch
    ):
        # TODO: this does not work in skipping the saving of the profile, it's getting saved in reports folder
        def pass_function():
            pass

        # skip saving the profile
        monkeypatch.setattr(pd.DataFrame, "to_csv", pass_function)
        resource = make_component_copy()
        resource.power_output_max = ts.FractionalTimeseries(
            name="power_output_max",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-06-21 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2010-06-21 03:00",
                        "2010-06-21 04:00",
                        "2010-06-21 05:00",
                        "2010-06-21 06:00",
                        "2010-06-21 07:00",
                        "2010-06-21 08:00",
                        "2010-06-21 09:00",
                        "2010-06-21 10:00",
                        "2010-06-21 11:00",
                        "2010-06-21 12:00",
                        "2010-06-21 13:00",
                        "2010-06-21 14:00",
                        "2010-06-21 15:00",
                        "2010-06-21 16:00",
                        "2010-06-21 17:00",
                        "2010-06-21 18:00",
                        "2010-06-21 19:00",
                        "2010-06-21 20:00",
                        "2010-06-21 21:00",
                        "2010-06-21 22:00",
                        "2010-06-21 23:00",
                        "2012-02-15 00:00",
                        "2012-02-15 01:00",
                        "2012-02-15 02:00",
                        "2012-02-15 03:00",
                        "2012-02-15 04:00",
                        "2012-02-15 05:00",
                        "2012-02-15 06:00",
                        "2012-02-15 07:00",
                        "2012-02-15 08:00",
                        "2012-02-15 09:00",
                        "2012-02-15 10:00",
                        "2012-02-15 11:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                        "2012-02-15 15:00",
                        "2012-02-15 16:00",
                        "2012-02-15 17:00",
                        "2012-02-15 18:00",
                        "2012-02-15 19:00",
                        "2012-02-15 20:00",
                        "2012-02-15 21:00",
                        "2012-02-15 22:00",
                        "2012-02-15 23:00",
                    ],
                    name="timestamp",
                ),
                data=[
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    0.8,
                    0.6,
                    0.6,
                    0.4,
                    0.1,
                    1.0,
                ],
                name="value",
            ),
        )
        test_temporal_settings = copy.deepcopy(test_temporal_settings_full_day)
        before_cf = resource.get_sampled_profile_cf(resource.power_output_max, test_temporal_settings)
        resource.update_resource_profiles(test_temporal_settings, dir_structure.results_dir)
        after_cf = resource.get_sampled_profile_cf(resource.power_output_max, test_temporal_settings)
        assert pytest.approx(0) == after_cf - before_cf

    def test_scale_resource_profile(self, make_component_copy):
        resource = make_component_copy()
        before = resource.power_output_max.data.sum()
        resource.scale_resource_profile(resource.power_output_max, 0.5)
        after = resource.power_output_max.data.sum()
        assert before / after == 2

        resource.scale_resource_profile(resource.power_output_max, 3)
        assert max(resource.power_output_max.data) == 1


class TestVariableResourceGroup(test_generic.TestGenericResourceGroup, TestVariableResource):
    _COMPONENT_CLASS = VariableResourceGroup
    _COMPONENT_NAME = "variable_resource_group_0"
    _SYSTEM_COMPONENT_DICT_NAME = "variable_resource_groups"

    @pytest.fixture(scope="class")
    def make_component_with_block_copy_non_curtailable(
        self, test_temporal_settings, test_system_with_operational_groups
    ):
        system = test_system_with_operational_groups.copy()

        for resource in system.variable_resources.values():
            resource.curtailable = False

        for resource in system.variable_resource_groups.values():
            resource.curtailable = False

        # Resample the timeseries attributes of the System to ensure data is interpolated and extrapolated correctly
        #  to cover all required model years and weather years
        modeled_years = test_temporal_settings.modeled_years.data.loc[
            test_temporal_settings.modeled_years.data.values
        ].index
        system.resample_ts_attributes(
            modeled_years=(min(modeled_years).year, max(modeled_years).year),
            weather_years=(
                min(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
                max(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
            ),
        )

        # Construct the model

        model = ModelTemplate(
            system=system,
            temporal_settings=test_temporal_settings,
            construct_investment_rules=True,
            construct_operational_rules=True,
            construct_costs=True,
        )

        def _make_custom_asset():
            asset_copy = copy.deepcopy(getattr(model.system, self._SYSTEM_COMPONENT_DICT_NAME)[self._COMPONENT_NAME])
            return asset_copy

        return _make_custom_asset

    @pytest.fixture(scope="class")
    def make_custom_component_with_block(self, test_system_with_operational_groups, test_temporal_settings):
        def _make_custom_asset(**kwargs):
            system_copy = test_system_with_operational_groups.copy()

            for resource in system_copy.variable_resources.values():
                for key, value in kwargs.items():
                    setattr(resource, key, value)

            for resource in system_copy.variable_resource_groups.values():
                for key, value in kwargs.items():
                    setattr(resource, key, value)

            # Resample the timeseries attributes of the System to ensure data is interpolated and extrapolated correctly
            #  to cover all required model years and weather years
            modeled_years = test_temporal_settings.modeled_years.data.loc[
                test_temporal_settings.modeled_years.data.values
            ].index
            system_copy.resample_ts_attributes(
                modeled_years=(min(modeled_years).year, max(modeled_years).year),
                weather_years=(
                    min(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
                    max(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
                ),
            )

            # Construct the model
            model = ModelTemplate(
                system=system_copy,
                temporal_settings=test_temporal_settings,
                construct_investment_rules=True,
                construct_operational_rules=True,
                construct_costs=True,
            )

            asset = getattr(system_copy, self._SYSTEM_COMPONENT_DICT_NAME)[self._COMPONENT_NAME]

            return asset

        return _make_custom_asset
