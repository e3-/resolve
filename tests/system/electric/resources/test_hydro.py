import pandas as pd
import pytest

from new_modeling_toolkit.system import HydroResourceGroup
from new_modeling_toolkit.system.electric.resources import HydroResource
from tests.system.electric.resources import test_variable


class TestHydroResource(test_variable.TestVariableResource):
    _COMPONENT_CLASS = HydroResource
    _COMPONENT_NAME = "HydroResource1"
    _SYSTEM_COMPONENT_DICT_NAME = "hydro_resources"

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
        non_curtailable_block.daily_budget_slack_cost[pd.Timestamp("2025-01-01")] = 10_000
        non_curtailable_block.daily_budget_slack_cost[pd.Timestamp("2030-01-01")] = 10_000
        non_curtailable_block.daily_budget_slack_cost[pd.Timestamp("2035-01-01")] = 0
        non_curtailable_block.daily_budget_slack_cost[pd.Timestamp("2045-01-01")] = 0
        non_curtailable_block.annual_budget_slack_cost[pd.Timestamp("2025-01-01")] = 10_000
        non_curtailable_block.annual_budget_slack_cost[pd.Timestamp("2030-01-01")] = 10_000
        non_curtailable_block.annual_budget_slack_cost[pd.Timestamp("2035-01-01")] = 10_000
        non_curtailable_block.annual_budget_slack_cost[pd.Timestamp("2045-01-01")] = 10_000
        non_curtailable_block.power_output.fix(10)
        non_curtailable_block.daily_budget_slack_up.fix()

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
        ]:
            assert (
                non_curtailable_block.annual_total_operational_cost[year].expr()
                == (
                    0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (2 + 2 + 2))
                    + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (2 + 2 + 2))
                )
                + 10_000
                + 10_000
            )

            assert curtailable_block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (2 + 2 + 2))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (2 + 2 + 2))
            ) + (curtailable_block.annual_total_curtailment_cost[year].expr())

        for year in [
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            assert (
                non_curtailable_block.annual_total_operational_cost[year].expr()
                == (
                    0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (0 + 0 + 0))
                    + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (0 + 0 + 0))
                )
                + 10_000
            )

            assert curtailable_block.annual_total_operational_cost[year].expr() == (
                0.6 * 365 * (10 * (5 + 2.5 + 6) - 10 * (0 + 0 + 0))
                + 0.4 * 365 * (10 * (-10 + 1 + 3) - 10 * (0 + 0 + 0))
            ) + (curtailable_block.annual_total_curtailment_cost[year].expr())

    def test_daily_budget_slack_cost(
        self, make_component_with_block_copy, make_component_with_block_copy_non_curtailable, first_index
    ):
        non_curtailable_hydro = make_component_with_block_copy_non_curtailable()
        block = non_curtailable_hydro.formulation_block
        model = make_component_with_block_copy().formulation_block.model()
        modeled_year, dispatch_window, timestamp = first_index

        # Test 1: no slack cost
        for day in model.DAYS:
            block.daily_budget_slack_up[modeled_year, day] = 0
            block.daily_budget_slack_down[modeled_year, day] = 0
        assert block.daily_budget_slack_cost[modeled_year].expr() == 0

        # Test 2: slack up cost
        for day in model.DAYS:
            block.daily_budget_slack_up[modeled_year, day] = 10
            block.daily_budget_slack_down[modeled_year, day] = 0
        assert block.daily_budget_slack_cost[modeled_year].expr() == 10 * 50_000_000 * len(model.DAYS)

        # Test 3: slack up and slack down costs
        for day in model.DAYS:
            block.daily_budget_slack_up[modeled_year, day] = 10
            block.daily_budget_slack_down[modeled_year, day] = 10
        assert block.daily_budget_slack_cost[modeled_year].expr() == 2 * 10 * 50_000_000 * len(model.DAYS)

        # Test 4: curtailable hydro has no slack cost
        curtailable_hydro = make_component_with_block_copy()
        assert not hasattr(curtailable_hydro.formulation_block, "daily_budget_slack_up")
        assert not hasattr(curtailable_hydro.formulation_block, "daily_budget_slack_down")
        assert not hasattr(curtailable_hydro.formulation_block, "daily_budget_slack_cost")

    def test_annual_budget_slack_cost(
        self, make_component_with_block_copy, make_component_with_block_copy_non_curtailable, first_index
    ):
        non_curtailable_hydro = make_component_with_block_copy_non_curtailable()
        block = non_curtailable_hydro.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Test 1: no slack cost
        block.annual_budget_slack_up[modeled_year] = 0
        block.annual_budget_slack_down[modeled_year] = 0
        assert block.annual_budget_slack_cost[modeled_year].expr() == 0

        # Test 2: slack up cost
        block.annual_budget_slack_up[modeled_year] = 10
        block.annual_budget_slack_down[modeled_year] = 0
        assert block.annual_budget_slack_cost[modeled_year].expr() == 10 * 50_000_000

        # Test 3: slack up and slack down costs
        block.annual_budget_slack_up[modeled_year] = 10
        block.annual_budget_slack_down[modeled_year] = 10
        assert block.annual_budget_slack_cost[modeled_year].expr() == 2 * 10 * 50_000_000

        # Test 4: curtailable hydro has no slack cost
        curtailable_hydro = make_component_with_block_copy()
        assert not hasattr(curtailable_hydro.formulation_block, "annual_budget_slack_up")
        assert not hasattr(curtailable_hydro.formulation_block, "annual_budget_slack_down")
        assert not hasattr(curtailable_hydro.formulation_block, "annual_budget_slack_cost")

    def test_daily_energy_budget_constraint(
        self, make_component_with_block_copy, make_component_with_block_copy_non_curtailable, first_index
    ):
        non_curtailable_hydro = make_component_with_block_copy_non_curtailable()
        block = non_curtailable_hydro.formulation_block
        model = make_component_with_block_copy().formulation_block.model()
        modeled_year, dispatch_window, timestamp = first_index
        day_1 = list(model.DAYS)[0]
        block.operational_capacity[modeled_year] = 100

        # Test 1: budget is met exactly with no slack
        assert block.daily_energy_budget_MWh[modeled_year, day_1].expr() == pytest.approx(100 * 24 * 1000 / (400 * 24))
        block.daily_budget_slack_up[modeled_year, day_1] = 0.0
        block.daily_budget_slack_down[modeled_year, day_1] = 0.0
        for dispatch_window, timestamp in model.DAY_TO_TIMESTAMPS_MAPPING[day_1]:
            block.power_output[modeled_year, dispatch_window, timestamp] = (100 * 24 * 1000 / (400 * 24)) / len(
                model.DAY_TO_TIMESTAMPS_MAPPING[day_1]
            )
        assert block.daily_energy_budget_constraint[modeled_year, day_1].body() == pytest.approx(0)
        assert block.daily_energy_budget_constraint[modeled_year, day_1].upper() == pytest.approx(0)
        assert block.daily_energy_budget_constraint[modeled_year, day_1].lower() == pytest.approx(0)

        # Test 2: budget is met with non-zero down slack
        block.daily_budget_slack_down[modeled_year, day_1] = 1.0
        for dispatch_window, timestamp in model.DAY_TO_TIMESTAMPS_MAPPING[day_1]:
            block.power_output[modeled_year, dispatch_window, timestamp] = ((100 * 24 * 1000 / (400 * 24)) - 1.0) / len(
                model.DAY_TO_TIMESTAMPS_MAPPING[day_1]
            )
        assert block.daily_energy_budget_constraint[modeled_year, day_1].body() == pytest.approx(0)
        assert block.daily_energy_budget_constraint[modeled_year, day_1].upper() == pytest.approx(0)
        assert block.daily_energy_budget_constraint[modeled_year, day_1].lower() == pytest.approx(0)

        # Test 3: budget is met with non-zero up slack
        block.daily_budget_slack_up[modeled_year, day_1] = 1.0
        block.daily_budget_slack_down[modeled_year, day_1] = 0.0
        for dispatch_window, timestamp in model.DAY_TO_TIMESTAMPS_MAPPING[day_1]:
            block.power_output[modeled_year, dispatch_window, timestamp] = ((100 * 24 * 1000 / (400 * 24)) + 1.0) / len(
                model.DAY_TO_TIMESTAMPS_MAPPING[day_1]
            )
        assert block.daily_energy_budget_constraint[modeled_year, day_1].body() == pytest.approx(0)
        assert block.daily_energy_budget_constraint[modeled_year, day_1].upper() == pytest.approx(0)
        assert block.daily_energy_budget_constraint[modeled_year, day_1].lower() == pytest.approx(0)

        # Test 4: budget is met with non-zero up slack
        block.daily_budget_slack_up[modeled_year, day_1] = 1.0
        block.daily_budget_slack_down[modeled_year, day_1] = 0.0
        for dispatch_window, timestamp in model.DAY_TO_TIMESTAMPS_MAPPING[day_1]:
            block.power_output[modeled_year, dispatch_window, timestamp] = ((100 * 24 * 1000 / (400 * 24)) + 1.0) / len(
                model.DAY_TO_TIMESTAMPS_MAPPING[day_1]
            )
        assert block.daily_energy_budget_constraint[modeled_year, day_1].body() == pytest.approx(0)
        assert block.daily_energy_budget_constraint[modeled_year, day_1].upper() == pytest.approx(0)
        assert block.daily_energy_budget_constraint[modeled_year, day_1].lower() == pytest.approx(0)

        # Test 5: budget equality is not met (less than)
        block.daily_budget_slack_up[modeled_year, day_1] = 0.0
        block.daily_budget_slack_down[modeled_year, day_1] = 0.0
        for dispatch_window, timestamp in model.DAY_TO_TIMESTAMPS_MAPPING[day_1]:
            block.power_output[modeled_year, dispatch_window, timestamp] = 10
        assert block.daily_energy_budget_constraint[modeled_year, day_1].body() == pytest.approx(
            (10 * len(model.DAY_TO_TIMESTAMPS_MAPPING[day_1])) - (100 * 24 * 1000 / (400 * 24))
        )
        assert block.daily_energy_budget_constraint[modeled_year, day_1].upper() == pytest.approx(0)
        assert block.daily_energy_budget_constraint[modeled_year, day_1].lower() == pytest.approx(0)
        assert not block.daily_energy_budget_constraint[modeled_year, day_1].expr()

        # Test 6: budget equality is not met (greater than)
        block.daily_budget_slack_up[modeled_year, day_1] = 0.0
        block.daily_budget_slack_down[modeled_year, day_1] = 0.0
        for dispatch_window, timestamp in model.DAY_TO_TIMESTAMPS_MAPPING[day_1]:
            block.power_output[modeled_year, dispatch_window, timestamp] = 1000
        assert block.daily_energy_budget_constraint[modeled_year, day_1].body() == pytest.approx(
            (1000 * len(model.DAY_TO_TIMESTAMPS_MAPPING[day_1])) - (100 * 24 * 1000 / (400 * 24))
        )
        assert block.daily_energy_budget_constraint[modeled_year, day_1].upper() == pytest.approx(0)
        assert block.daily_energy_budget_constraint[modeled_year, day_1].lower() == pytest.approx(0)
        assert not block.daily_energy_budget_constraint[modeled_year, day_1].expr()


class TestHydroResourceGroup(test_variable.TestVariableResourceGroup, TestHydroResource):
    _COMPONENT_CLASS = HydroResourceGroup
    _COMPONENT_NAME = "hydro_resource_group_0"
    _SYSTEM_COMPONENT_DICT_NAME = "hydro_resource_groups"
