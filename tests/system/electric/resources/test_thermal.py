import pandas as pd
import pytest

from new_modeling_toolkit.system import ThermalResourceGroup
from new_modeling_toolkit.system.electric.resources import ThermalResource
from new_modeling_toolkit.system.electric.resources.thermal import ThermalUnitCommitmentResource
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


# _RESOURCE_INIT_KWARGS = dict(
#     capacity_planned=ts.NumericTimeseries(
#         name="capacity_planned",
#         data=pd.Series(
#             index=pd.DatetimeIndex(["2020-01-01", "2030-01-01"], name="timestamp"),
#             data=[200.0, 100.0],
#             name="value",
#         ),
#     )
# )

# @pytest.fixture(scope="class")
# def resource_for_budget_tests(self, make_resource_copy):
#     resource = make_resource_copy()
#     resource.capacity_planned = ts.NumericTimeseries(
#         name="capacity_planned",
#         data=pd.Series(
#             index=pd.DatetimeIndex(["2020-01-01", "2030-01-01"], name="timestamp"),
#             data=[200.0, 400.0],
#             name="value",
#         ),
#     )
#     return resource
#
# def test_scaled_annual_energy_budget(self, resource_for_budget_tests):
#     resource = copy.deepcopy(resource_for_budget_tests)
#     resource.energy_budget_annual = ts.FractionalTimeseries(
#         name="energy_budget_annual",
#         data=pd.Series(
#             index=pd.DatetimeIndex(["2010-01-01", "2019-01-01"], name="timestamp"), data=[0.000856164, 0.001141553]
#         ),
#         freq_="YS",
#         weather_year=True,
#     )
#
#     load_calendar = pd.date_range(start="2010-01-01 00:00", end="2010-01-01 12:00", freq="H", name="timestamp")
#     resource.upsample(load_calendar)
#     expected_energy_budget_annual = pd.Series(
#         index=pd.date_range(start="2010-01-01 00:00", end="2010-12-31 23:00", freq="YS", name="timestamp"),
#         data=0.000856164,
#     )
#     pd.testing.assert_series_equal(
#         resource.energy_budget_annual.data,
#         expected_energy_budget_annual,
#     )
#
# def test_scaled_daily_energy_budget(self, resource_for_budget_tests):
#     resource = copy.deepcopy(resource_for_budget_tests)
#     resource.energy_budget_daily = ts.FractionalTimeseries(
#         name="energy_budget_daily",
#         data=pd.Series(
#             index=pd.DatetimeIndex(["2010-07-01", "2010-07-02"], name="timestamp"), data=[0.104166667, 0.114583333]
#         ),
#         freq_="D",
#         weather_year=True,
#     )
#
#     expected_profile = {
#         2020: pd.Series(
#             index=pd.DatetimeIndex(["2010-07-01", "2010-07-02"], name="timestamp"),
#             data=[500.0, 550.0],
#         ),
#         2030: pd.Series(
#             index=pd.DatetimeIndex(["2010-07-01", "2010-07-02"], name="timestamp"),
#             data=[1000.0, 1100.0],
#         ),
#     }
#     assert resource.scaled_daily_energy_budget.keys() == expected_profile.keys()
#     for modeled_year, profile in resource.scaled_daily_energy_budget.items():
#         pd.testing.assert_series_equal(profile, expected_profile[modeled_year])
#
# def test_scaled_monthly_energy_budget(self, resource_for_budget_tests):
#     resource = copy.deepcopy(resource_for_budget_tests)
#     resource.energy_budget_monthly = ts.FractionalTimeseries(
#         name="energy_budget_monthly",
#         data=pd.Series(
#             index=pd.DatetimeIndex(["2010-07-01", "2010-08-01"], name="timestamp"), data=[0.00672043, 0.008400538]
#         ),
#         freq_="MS",
#         weather_year=True,
#     )
#
#     expected_profile = {
#         2020: pd.Series(
#             index=pd.DatetimeIndex(["2010-07-01", "2010-08-01"], name="timestamp"),
#             data=[1000.0, 1250.0],
#         ),
#         2030: pd.Series(
#             index=pd.DatetimeIndex(["2010-07-01", "2010-08-01"], name="timestamp"),
#             data=[2000.0, 2500.0],
#         ),
#     }
#     assert resource.scaled_monthly_energy_budget.keys() == expected_profile.keys()
#     for modeled_year, profile in resource.scaled_monthly_energy_budget.items():
#         pd.testing.assert_series_equal(profile, expected_profile[modeled_year])
#
# def test_rescale_incremental(self, make_resource_copy):
#     """Test the `rescale()` function with `incremental=True`."""
#     resource = make_resource_copy()
#
#     resource.rescale(modeled_year=2020, capacity=100, incremental=True)
#     pd.testing.assert_series_equal(
#         resource.capacity_planned.data,
#         pd.Series(
#             index=pd.DatetimeIndex(["2020-01-01", "2030-01-01"], name="timestamp"),
#             data=[300.0, 100.0],
#             name="value",
#         ),
#     )
#
# def test_scaled_pmax_profile(self, make_resource_copy):
#     resource = make_resource_copy()
#
#     expected_profile = {
#         2020: pd.Series(
#             index=pd.DatetimeIndex(
#                 ["2010-01-01 00:00", "2010-01-01 01:00", "2010-01-01 02:00", "2010-01-01 03:00"], name="timestamp"
#             ),
#             data=[200.0, 0.0, 50.0, 100.0],
#             name="value",
#         ),
#         2030: pd.Series(
#             index=pd.DatetimeIndex(
#                 ["2010-01-01 00:00", "2010-01-01 01:00", "2010-01-01 02:00", "2010-01-01 03:00"], name="timestamp"
#             ),
#             data=[100.0, 0.0, 25.0, 50.0],
#             name="value",
#         ),
#     }
#
#     assert resource.scaled_pmax_profile.keys() == expected_profile.keys()
#     for modeled_year, profile in resource.scaled_pmax_profile.items():
#         pd.testing.assert_series_equal(profile, expected_profile[modeled_year])
#
# def test_dispatch_second_modeled_year(self, make_resource_copy):
#     resource = make_resource_copy()
#
#     net_load = pd.Series(
#         index=pd.DatetimeIndex(["2010-01-01 00:00", "2010-01-01 01:00", "2010-01-01 02:00", "2010-01-01 03:00"]),
#         data=[50.0, -20.0, 0, 150.0],
#     )
#     updated_net_load = resource.dispatch(net_load=net_load, modeled_year=2030)
#
#     pd.testing.assert_series_equal(
#         resource.heuristic_provide_power_mw,
#         pd.Series(
#             index=pd.DatetimeIndex(
#                 ["2010-01-01 00:00", "2010-01-01 01:00", "2010-01-01 02:00", "2010-01-01 03:00"], name="timestamp"
#             ),
#             data=[100.0, 0.0, 25.0, 50.0],
#             name="value",
#         ),
#     )
#     pd.testing.assert_series_equal(
#         updated_net_load,
#         pd.Series(
#             index=pd.DatetimeIndex(
#                 ["2010-01-01 00:00", "2010-01-01 01:00", "2010-01-01 02:00", "2010-01-01 03:00"]
#             ),
#             data=[-50.0, -20.0, -25.0, 100.0],
#         ),
#     )
#
# def test_construct_operational_block(self, make_dispatch_model_copy, monkeypatch):
#     construct_operational_block_mock = mock.Mock()
#     monkeypatch.setattr(ThermalResource, "construct_operational_block", construct_operational_block_mock)
#     model = make_dispatch_model_copy()
#     assert len(model.blocks) == 0
#     construct_operational_block_mock.assert_not_called()
#
# def test_variable_bounds(self):
#     pass
#
# def test_power_output_max_constraint(self):
#     pass
#
# def test_power_output_min_constraint(self):
#     pass
#
# def test_power_input_max_constraint(self):
#     pass
#
# def test_adjust_budgets_for_optimization(self):
#     pass
#
# def test_annual_energy_budget_constraint(self):
#     pass
#
# def test_daily_energy_budget_constraint(self):
#     pass
#
# def test_monthly_energy_budget_constraint(self):
#     pass


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

    def test_synchronous_condenser_addition_to_load(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy(component_name="ThermalUnitCommitmentResource2")
        block = resource.formulation_block

        block.committed_capacity[first_index] = 5
        assert block.synchronous_condenser_addition_to_load[first_index].expr() == 20

        block.committed_capacity[first_index] = 11
        assert block.synchronous_condenser_addition_to_load[first_index].expr() == 44

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


class TestThermalResourceGroup(test_generic.TestGenericResourceGroup, TestThermalResource):
    _COMPONENT_CLASS = ThermalResourceGroup
    _COMPONENT_NAME = "thermal_resource_group_0"
    _SYSTEM_COMPONENT_DICT_NAME = "thermal_resource_groups"
