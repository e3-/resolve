import pytest

from new_modeling_toolkit.system.electric.reserve import Reserve
from tests.system.component_test_template import ComponentTestTemplate


class TestReserve(ComponentTestTemplate):
    _COMPONENT_CLASS = Reserve
    _COMPONENT_NAME = "TestRegulationUp"
    _SYSTEM_COMPONENT_DICT_NAME = "reserves"

    def test_operating_reserve_balance_constraint(self, make_component_with_block_copy, first_index):
        reserve = make_component_with_block_copy()

        for resource in [
            "HydroResource1",
            "GenericResource1",
            "ThermalResource1",
            "SolarResource1",
            "StorageResource1",
        ]:
            reserve.resources[resource].instance_from.formulation_block.provide_reserve[
                "TestRegulationUp", first_index
            ].fix(100)

        reserve.resources["ThermalUnitCommitmentResource"].instance_from.formulation_block.provide_reserve[
            "TestRegulationUp", first_index
        ].fix(0)

        reserve.formulation_block.unserved_reserve_MW[first_index].fix(0)
        reserve.formulation_block.operating_reserve_requirement[first_index] = 300

        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].body() == 200
        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].upper() == 0
        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].lower() == 0
        assert not reserve.formulation_block.operating_reserve_balance_constraint[first_index].expr()

        reserve.formulation_block.unserved_reserve_MW[first_index].fix(200)
        reserve.formulation_block.operating_reserve_requirement[first_index] = 700

        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].body() == 0
        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].upper() == 0
        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].lower() == 0
        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].expr()

        reserve.formulation_block.unserved_reserve_MW[first_index].fix(0)
        reserve.formulation_block.operating_reserve_requirement[first_index] = 500

        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].body() == 0
        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].upper() == 0
        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].lower() == 0
        assert reserve.formulation_block.operating_reserve_balance_constraint[first_index].expr()

    def test_total_provided_reserve(self, make_component_with_block_copy, first_index):
        reserve = make_component_with_block_copy()

        for resource in [
            "HydroResource1",
            "GenericResource1",
            "ThermalResource1",
            "SolarResource1",
            "StorageResource1",
            "ThermalUnitCommitmentResource",
        ]:
            reserve.resources[resource].instance_from.formulation_block.provide_reserve[
                "TestRegulationUp", first_index
            ].fix(100)

        reserve.resources["ThermalUnitCommitmentResource"].instance_from.formulation_block.provide_reserve[
            "TestRegulationUp", first_index
        ].fix(0)

        assert reserve.formulation_block.total_provided_reserve_MW[first_index].expr() == 500

    def test_operating_reserve_requirement(self, make_component_with_block_copy, first_index):
        reserve = make_component_with_block_copy()
        modeled_year, dispatch_window, timestamp = first_index

        # requirement
        assert reserve.requirement.data.at[timestamp.replace(year=modeled_year.year)] == 10

        # load incremental requirement
        assert (
            reserve.loads["Load_2"].incremental_requirement_hourly_scalar.data.at[
                timestamp.replace(year=modeled_year.year)
            ]
            == 0.9
        )
        assert reserve.loads["Load_2"].instance_from.get_load(modeled_year.year, timestamp) == pytest.approx(
            13107.596660636786
        )

        # resource incremental requirement
        assert (
            reserve.resources["SolarResource1"].incremental_requirement_hourly_scalar.data.at[
                timestamp.replace(year=modeled_year.year)
            ]
            == 0.9
        )
        assert (
            reserve.resources["SolarResource1"]
            .instance_from.formulation_block.operational_capacity[modeled_year]
            .expr()
            == 100.0
        )

        # zone incremental requirement
        assert (
            reserve.zones["Zone_1"].incremental_requirement_hourly_scalar.data.at[
                timestamp.replace(year=modeled_year.year)
            ]
            == 0.9
        )
        assert reserve.zones["Zone_1"].instance_to.get_aggregated_load(modeled_year.year, timestamp) == pytest.approx(
            131076.0025175916
        )

        # total reserve requirement
        assert reserve.formulation_block.operating_reserve_requirement[first_index].expr() == pytest.approx(
            10 + 0.9 * 13107.596660636786 + 0.9 * 100 + 131076.0025175916 * 0.9
        )  # requirement + resource inc req + zone inc req

    def test_unserved_reserve(self, make_component_with_block_copy):
        reserve = make_component_with_block_copy()
        block = reserve.formulation_block
        assert block.unserved_reserve_MW.is_indexed()
        assert all(var.lower == 0 for var in block.unserved_reserve_MW.values())
        assert all(var.upper is None for var in block.unserved_reserve_MW.values())

    def test_annual_total_operational_cost(self, make_component_with_block_copy, first_index, last_index):
        reserve = make_component_with_block_copy()
        block = reserve.formulation_block

        modeled_year = first_index[0]
        total_operational_cost = 0
        for dispatch_window, timestamp in list(block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS):
            block.unserved_reserve_MW[modeled_year, dispatch_window, timestamp] = 10.0
            total_operational_cost += (
                reserve.penalty_unserved_reserve
                * 10.0
                * block.model().dispatch_window_weights[dispatch_window]
                * block.model().num_days_per_modeled_year[modeled_year]
            )

        assert block.annual_total_operational_cost[modeled_year].expr() == total_operational_cost

    def test_results_reporting(self, make_component_with_block_copy):

        reserve = make_component_with_block_copy()

        assert reserve.formulation_block.annual_reserve_requirement.doc == "Annual Reserve Requirement (MW)"
        assert reserve.formulation_block.annual_unserved_cost.doc == "Annual Unserved Reserve Cost ($)"
        assert reserve.formulation_block.annual_unserved_reserve.doc == "Annual Unserved Reserve (MW)"
        assert reserve.formulation_block.total_provided_reserve_MW.doc == "Total Provided Reserve (MW)"
