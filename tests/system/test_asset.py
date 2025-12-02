import copy
import functools

import pandas as pd
import pytest

from new_modeling_toolkit.core.excel import LinkageFieldsToWrite
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.system.asset import Asset
from new_modeling_toolkit.system.asset import AssetGroup
from tests.system.component_test_template import ComponentTestTemplate


class TestAsset(ComponentTestTemplate):

    _COMPONENT_CLASS = Asset
    _COMPONENT_NAME = "GenericAsset1"
    _SYSTEM_COMPONENT_DICT_NAME = "generic_assets"


    def test_all_pyomo_rules_called(self):
        # Get the set of all functions that are defined on the current test class but not on the parent class
        # TODO: this doesn't totally work yet, I think it also returns attributes
        set(dir(self._COMPONENT_CLASS)) - functools.reduce(
            lambda s1, s2: s1.union(s2), map(lambda cls: set(dir(cls)), self._COMPONENT_CLASS.__mro__[1:])
        )

    def test_selected_capacity(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        assert not block.selected_capacity.is_indexed()
        assert block.selected_capacity.lower == 0
        assert block.selected_capacity.upper is None

    def test_asset_potential_slack(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        assert not block.asset_potential_slack.is_indexed()
        assert block.asset_potential_slack.lower == 0
        assert block.asset_potential_slack.upper is None

    def test_retired_capacity(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        assert block.retired_capacity.is_indexed()
        assert block.retired_capacity.index_set() is block.model().MODELED_YEARS
        assert all(var.lower == 0 for var in block.retired_capacity.values())
        assert all(var.upper is None for var in block.retired_capacity.values())

    def test_operational_capacity(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        # Check the attributes on the Asset to ensure they match expectations
        assert all(c == 100 for c in asset.planned_capacity.data)

        block.selected_capacity.fix(200)
        block.retired_capacity[pd.Timestamp("2025-01-01 00:00")].fix(0)
        block.retired_capacity[pd.Timestamp("2030-01-01 00:00")].fix(100)
        block.retired_capacity[pd.Timestamp("2035-01-01 00:00")].fix(0)
        block.retired_capacity[pd.Timestamp("2045-01-01 00:00")].fix(50)

        assert block.operational_capacity[pd.Timestamp("2025-01-01 00:00")].expr() == 300
        assert block.operational_capacity[pd.Timestamp("2030-01-01 00:00")].expr() == 200
        assert block.operational_capacity[pd.Timestamp("2035-01-01 00:00")].expr() == 200
        assert block.operational_capacity[pd.Timestamp("2045-01-01 00:00")].expr() == 150

    def test_planned_new_capacity(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        model = block.model()
        modeled_years = model.MODELED_YEARS

        first_year = modeled_years[1]
        assert block.planned_new_capacity[first_year].expr() == 100.0
        assert all(block.planned_new_capacity[year].expr() == 0.0 for year in modeled_years if year > first_year)

    def test_can_build_new_constraint(self, make_custom_component_with_block):
        asset = make_custom_component_with_block(can_build_new=False)
        block = asset.formulation_block

        assert not asset.can_build_new

        block.selected_capacity.fix(0)
        block.asset_potential_slack.fix(0)
        assert block.can_build_new_constraint.upper() == 0
        assert block.can_build_new_constraint.body() == 0
        assert block.can_build_new_constraint.expr()

        block.selected_capacity.fix(100)
        block.asset_potential_slack.fix(0)
        assert block.can_build_new_constraint.upper() == 0
        assert block.can_build_new_constraint.body() == 100
        assert not block.can_build_new_constraint.expr()

        block.selected_capacity.fix(0)
        block.asset_potential_slack.fix(10)
        assert block.can_build_new_constraint.upper() == 0
        assert block.can_build_new_constraint.body() == 10
        assert not block.can_build_new_constraint.expr()

        # Test with build year before first modeled year
        asset = make_custom_component_with_block(build_year="2000-01-01", can_build_new=True)
        block = asset.formulation_block
        assert asset.can_build_new

        block.selected_capacity.fix(0)
        block.asset_potential_slack.fix(0)
        assert block.can_build_new_constraint.upper() == 0
        assert block.can_build_new_constraint.body() == 0
        assert block.can_build_new_constraint.expr()

        block.selected_capacity.fix(100)
        block.asset_potential_slack.fix(10)
        assert block.can_build_new_constraint.upper() == 0
        assert block.can_build_new_constraint.body() == 110
        assert not block.can_build_new_constraint.expr()

        block.selected_capacity.fix(0)
        block.asset_potential_slack.fix(10)
        assert block.can_build_new_constraint.upper() == 0
        assert block.can_build_new_constraint.body() == 10
        assert not block.can_build_new_constraint.expr()

        # Test with build year between first and second modeled year
        asset = make_custom_component_with_block(build_year="2027-01-01", can_build_new=True)
        block = asset.formulation_block
        assert asset.can_build_new

        block.selected_capacity.fix(0)
        block.asset_potential_slack.fix(0)
        assert block.can_build_new_constraint.upper() == 0
        assert block.can_build_new_constraint.body() == 0
        assert block.can_build_new_constraint.expr()

        block.selected_capacity.fix(100)
        block.asset_potential_slack.fix(10)
        assert block.can_build_new_constraint.upper() == 0
        assert block.can_build_new_constraint.body() == 110
        assert not block.can_build_new_constraint.expr()

        block.selected_capacity.fix(0)
        block.asset_potential_slack.fix(10)
        assert block.can_build_new_constraint.upper() == 0
        assert block.can_build_new_constraint.body() == 10
        assert not block.can_build_new_constraint.expr()

    def test_potential_constraint(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        # Check the attributes on the Asset to ensure they match expectations
        assert all(c == 100 for c in asset.planned_capacity.data)
        assert asset.potential == 300

        # Test a value for selected capacity that should obey the constraint
        block.selected_capacity.fix(150)
        assert block.potential_constraint[pd.Timestamp("2025-01-01 00:00")].upper() == 300
        assert block.potential_constraint[pd.Timestamp("2025-01-01 00:00")].body() == 250
        assert block.potential_constraint[pd.Timestamp("2025-01-01 00:00")].expr()

        # Test a value for selected capacity that violates the constraint
        block.selected_capacity.fix(300)
        assert block.potential_constraint[pd.Timestamp("2025-01-01 00:00")].upper() == 300
        assert block.potential_constraint[pd.Timestamp("2025-01-01 00:00")].body() == 400
        assert not block.potential_constraint[pd.Timestamp("2025-01-01 00:00")].expr()

        # Test a value for selected capacity that violates the constraint, with slack to offset
        block.selected_capacity.fix(300)
        block.asset_potential_slack.fix(100)
        assert block.potential_constraint[pd.Timestamp("2025-01-01 00:00")].upper() == 300
        assert block.potential_constraint[pd.Timestamp("2025-01-01 00:00")].body() == 300
        assert block.potential_constraint[pd.Timestamp("2025-01-01 00:00")].expr()

    def test_physical_lifetime_constraint(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert block.physical_lifetime_constraint.is_indexed()
        assert block.physical_lifetime_constraint.index_set() is block.model().MODELED_YEARS
        assert list(block.physical_lifetime_constraint.keys()) == [pd.Timestamp("2045-01-01 00:00")]

        block.selected_capacity.fix(0)
        block.retired_capacity.fix(0)
        assert block.physical_lifetime_constraint[pd.Timestamp("2045-01-01 00:00")].upper() == 0
        assert block.physical_lifetime_constraint[pd.Timestamp("2045-01-01 00:00")].body() == 100
        assert not block.physical_lifetime_constraint[pd.Timestamp("2045-01-01 00:00")].expr()

        block.retired_capacity[pd.Timestamp("2035-01-01 00:00")].fix(50)
        assert block.physical_lifetime_constraint[pd.Timestamp("2045-01-01 00:00")].upper() == 0
        assert block.physical_lifetime_constraint[pd.Timestamp("2045-01-01 00:00")].body() == 50
        assert not block.physical_lifetime_constraint[pd.Timestamp("2045-01-01 00:00")].expr()

        block.retired_capacity[pd.Timestamp("2045-01-01 00:00")].fix(50)
        assert block.physical_lifetime_constraint[pd.Timestamp("2045-01-01 00:00")].upper() == 0
        assert block.physical_lifetime_constraint[pd.Timestamp("2045-01-01 00:00")].body() == 0
        assert block.physical_lifetime_constraint[pd.Timestamp("2045-01-01 00:00")].expr()

    def test_retired_capacity_max_constraint(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert block.retired_capacity_max_constraint.is_indexed()
        assert block.retired_capacity_max_constraint.index_set() is block.model().MODELED_YEARS

        assert all(c == 100 for c in asset.planned_capacity.data)

        block.retired_capacity[pd.Timestamp("2025-01-01 00:00")].fix(0)
        assert block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].upper() == 100
        assert block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].body() == 0
        assert block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].expr()
        block.retired_capacity[pd.Timestamp("2025-01-01 00:00")].fix(150)
        assert block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].upper() == 100
        assert block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].body() == 150
        assert not block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].expr()

        block.retired_capacity.fix(0)
        block.selected_capacity.fix(100)
        block.retired_capacity[pd.Timestamp("2030-01-01 00:00")].fix(150)
        assert block.retired_capacity_max_constraint[pd.Timestamp("2030-01-01 00:00")].upper() == 0
        assert block.retired_capacity_max_constraint[pd.Timestamp("2030-01-01 00:00")].body() == 150 - 100 - 100
        assert block.retired_capacity_max_constraint[pd.Timestamp("2030-01-01 00:00")].expr()
        block.retired_capacity[pd.Timestamp("2030-01-01 00:00")].fix(250)
        assert block.retired_capacity_max_constraint[pd.Timestamp("2030-01-01 00:00")].upper() == 0
        assert block.retired_capacity_max_constraint[pd.Timestamp("2030-01-01 00:00")].body() == 250 - 100 - 100
        assert not block.retired_capacity_max_constraint[pd.Timestamp("2030-01-01 00:00")].expr()

        block.retired_capacity.fix(0)
        block.selected_capacity.fix(100)
        block.retired_capacity[pd.Timestamp("2030-01-01 00:00")].fix(150)
        block.retired_capacity[pd.Timestamp("2035-01-01 00:00")].fix(50)
        assert block.retired_capacity_max_constraint[pd.Timestamp("2035-01-01 00:00")].upper() == 0
        assert block.retired_capacity_max_constraint[pd.Timestamp("2035-01-01 00:00")].body() == 50 - (100 + 100 - 150)
        assert block.retired_capacity_max_constraint[pd.Timestamp("2035-01-01 00:00")].expr()
        block.retired_capacity[pd.Timestamp("2035-01-01 00:00")].fix(100)
        assert block.retired_capacity_max_constraint[pd.Timestamp("2035-01-01 00:00")].upper() == 0
        assert block.retired_capacity_max_constraint[pd.Timestamp("2035-01-01 00:00")].body() == 100 - (100 + 100 - 150)
        assert not block.retired_capacity_max_constraint[pd.Timestamp("2035-01-01 00:00")].expr()

    def test_retired_capacity_max_constraint_early_build_year(self, make_custom_component_with_block):
        asset = make_custom_component_with_block(build_year=pd.Timestamp("2020-01-01"))
        block = asset.formulation_block

        assert all(c == 100 for c in asset.planned_capacity.data)

        block.retired_capacity[pd.Timestamp("2025-01-01 00:00")].fix(0)
        assert block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].upper() == 100
        assert block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].body() == 0
        assert block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].expr()
        block.retired_capacity[pd.Timestamp("2025-01-01 00:00")].fix(150)
        assert block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].upper() == 100
        assert block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].body() == 150
        assert not block.retired_capacity_max_constraint[pd.Timestamp("2025-01-01 00:00")].expr()

    def test_retired_capacity_max_constraint_cannot_retire(self, make_custom_component_with_block):
        asset = make_custom_component_with_block(can_retire=False, physical_lifetime=20)
        block = asset.formulation_block

        assert block.retired_capacity_max_constraint.is_indexed()
        assert block.retired_capacity_max_constraint.index_set() is block.model().MODELED_YEARS

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
            pd.Timestamp("2035-01-01 00:00"),
        ]:
            block.retired_capacity.fix(0)
            block.retired_capacity[year].fix(50)
            assert block.retired_capacity_max_constraint[year].upper() == 0
            assert block.retired_capacity_max_constraint[year].body() == 50
            assert not block.retired_capacity_max_constraint[year].expr()

        block.retired_capacity.fix(0)
        block.selected_capacity.fix(100)
        assert block.retired_capacity_max_constraint[pd.Timestamp("2045-01-01 00:00")].body() == 0 - 100 - 100
        assert block.retired_capacity_max_constraint[pd.Timestamp("2045-01-01 00:00")].upper() == 0
        assert block.retired_capacity_max_constraint[pd.Timestamp("2045-01-01 00:00")].expr()

    def test_retired_capacity_max_constraint_cannot_retire_no_lifetime(self, make_custom_component_with_block):
        asset = make_custom_component_with_block(can_retire=False, physical_lifetime=100)
        block = asset.formulation_block

        assert block.retired_capacity_max_constraint.is_indexed()
        assert block.retired_capacity_max_constraint.index_set() is block.model().MODELED_YEARS

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            block.retired_capacity.fix(0)
            block.retired_capacity[year].fix(50)
            assert block.retired_capacity_max_constraint[year].upper() == 0
            assert block.retired_capacity_max_constraint[year].body() == 50
            assert not block.retired_capacity_max_constraint[year].expr()

    def test_annual_capital_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert asset.annualized_capital_cost == 20
        block.selected_capacity.fix(100)

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
            pd.Timestamp("2035-01-01 00:00"),
        ]:
            assert block.annual_capital_cost[year].expr() == 2_000_000

        assert block.annual_capital_cost[pd.Timestamp("2045-01-01 00:00")].expr() == 0

    def test_annual_fixed_om_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert all(c == 10 for c in asset.annualized_fixed_om_cost.data)
        assert all(c == 100 for c in asset.planned_capacity.data)

        block.selected_capacity.fix(50)
        block.retired_capacity.fix(0)
        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            assert block.annual_fixed_om_cost[year].expr() == 1_500_000

        block.selected_capacity.fix(50)
        block.retired_capacity[pd.Timestamp("2035-01-01 00:00")].fix(50)
        for year, expected in [
            (pd.Timestamp("2025-01-01 00:00"), 1_500_000),
            (pd.Timestamp("2030-01-01 00:00"), 1_500_000),
            (pd.Timestamp("2035-01-01 00:00"), 1_000_000),
            (pd.Timestamp("2045-01-01 00:00"), 1_000_000),
        ]:
            assert block.annual_fixed_om_cost[year].expr() == expected

    def test_asset_potential_slack_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        block.asset_potential_slack.fix(100)

        assert block.asset_potential_slack_cost.expr() == 5_000_000_000

    def test_annual_total_investment_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert asset.physical_lifetime == 20
        assert asset.annualized_capital_cost == 20
        assert all(c == 10 for c in asset.annualized_fixed_om_cost.data)
        assert all(c == 100 for c in asset.planned_capacity.data)

        block.selected_capacity.fix(50)
        block.retired_capacity.fix(0)
        for year, expected in [
            (pd.Timestamp("2025-01-01 00:00"), 2_500_000),
            (pd.Timestamp("2030-01-01 00:00"), 2_500_000),
            (pd.Timestamp("2035-01-01 00:00"), 2_500_000),
            (pd.Timestamp("2045-01-01 00:00"), 1_500_000),
        ]:
            assert block.asset_potential_slack.value == 0
            assert block.annual_total_slack_investment_cost[year].expr() == 0
            assert block.annual_total_investment_cost[year].expr() == expected

        block.selected_capacity.fix(50)
        block.retired_capacity[pd.Timestamp("2035-01-01 00:00")].fix(50)
        for year, expected in [
            (pd.Timestamp("2025-01-01 00:00"), 2_500_000),
            (pd.Timestamp("2030-01-01 00:00"), 2_500_000),
            (pd.Timestamp("2035-01-01 00:00"), 2_000_000),
            (pd.Timestamp("2045-01-01 00:00"), 1_000_000),
        ]:
            assert block.asset_potential_slack.value == 0
            assert block.annual_total_slack_investment_cost[year].expr() == 0
            assert block.annual_total_investment_cost[year].expr() == expected

        # Additional test for non-zero slack cost in 2025 (not applied to investment cost of non-build years)
        assert asset.build_year == pd.Timestamp("2025-01-01 00:00")
        block.asset_potential_slack.fix(2)
        for year, expected in [
            (pd.Timestamp("2025-01-01 00:00"), 2_500_000),
            (pd.Timestamp("2030-01-01 00:00"), 2_500_000),
            (pd.Timestamp("2035-01-01 00:00"), 2_000_000),
            (pd.Timestamp("2045-01-01 00:00"), 1_000_000),
        ]:
            assert block.asset_potential_slack.value == 2
            assert block.asset_potential_slack_cost.expr() == 2 * 50_000_000
            if year == pd.Timestamp("2025-01-01 00:00"):
                assert block.annual_total_slack_investment_cost[year].expr() == 2 * 50_000_000
                assert block.annual_total_investment_cost[year].expr() == expected + 100_000_000
            else:
                assert block.annual_total_slack_investment_cost[year].expr() == 0
                assert block.annual_total_investment_cost[year].expr() == expected

    def test_annual_total_operational_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        for year in block.model().MODELED_YEARS:
            assert block.annual_total_operational_cost[year].expr() == 0

    def test_max_reliability_capacity_constraint(self, make_component_with_block_copy, first_index):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        policies = asset.policies
        first_year = first_index[0]

        # skip test for resources that don't have a PRM policy
        if "TestPRM" not in policies:
            pass

        # DeliverabilityStatus = FULLY_DELIVERABLE
        elif policies["TestPRM"].fully_deliverable:
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].upper() == 0.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].lower() == 0.0

            block.operational_capacity[first_year] = 100.0
            block.reliability_capacity["TestPRM", first_year] = 100.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].body() == 0.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].expr()
            block.reliability_capacity["TestPRM", first_year] = 110.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].body() == 10.0
            assert not block.max_reliability_capacity_constraint["TestPRM", first_year].expr()
            block.reliability_capacity["TestPRM", first_year] = 90.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].body() == -10.0
            assert not block.max_reliability_capacity_constraint["TestPRM", first_year].expr()

        else:
            # DeliverabilityStatus = not FULLY_DELIVERABLE
            assert not policies["TestPRM"].fully_deliverable
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].upper() == 0.0

            block.reliability_capacity["TestPRM", first_year] = 0.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].upper() == 0.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].body() == -100.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].expr()
            block.reliability_capacity["TestPRM", first_year] = 110.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].body() == 10.0
            assert not block.max_reliability_capacity_constraint["TestPRM", first_year].expr()
            block.reliability_capacity["TestPRM", first_year] = 90.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].body() == -10.0
            assert block.max_reliability_capacity_constraint["TestPRM", first_year].expr()

    def test_maintain_reliability_capacity_constraint(
        self, make_component_with_block_copy, make_custom_component_with_block, first_index
    ):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        policies = asset.policies
        first_year = first_index[0]
        second_year = block.model().MODELED_YEARS.next(first_year)
        last_year = list(block.model().MODELED_YEARS)[-1]
        first_const_index = ("TestPRM", first_year)
        second_const_index = ("TestPRM", second_year)
        last_const_index = ("TestPRM", last_year)

        # skip test for resources that don't have a PRM policy
        if "TestPRM" not in policies:
            pass

        # DeliverabilityStatus = FULLY_DELIVERABLE
        elif policies["TestPRM"].fully_deliverable:
            assert first_const_index not in block.maintain_reliability_capacity_constraint
            assert last_const_index not in block.maintain_reliability_capacity_constraint
            assert len(block.maintain_reliability_capacity_constraint) == 0

        else:
            # DeliverabilityStatus = NOT FULLY_DELIVERABLE
            assert first_const_index in block.maintain_reliability_capacity_constraint
            block.retired_capacity[first_year] = 0.0
            block.reliability_capacity[first_const_index] = 100.0
            block.reliability_capacity[second_const_index] = 100.0
            assert block.maintain_reliability_capacity_constraint[first_const_index].expr()
            block.reliability_capacity[second_const_index] = 90.0
            assert not block.maintain_reliability_capacity_constraint[first_const_index].expr()

            assert last_const_index not in block.maintain_reliability_capacity_constraint

        later_asset = make_custom_component_with_block(build_year=second_year)
        block = later_asset.formulation_block
        policies = later_asset.policies

        # skip test for resources that don't have a PRM policy
        if "TestPRM" not in policies:
            pass

        # DeliverabilityStatus = FULLY_DELIVERABLE
        elif policies["TestPRM"].fully_deliverable:
            assert first_const_index not in block.maintain_reliability_capacity_constraint
            assert last_const_index not in block.maintain_reliability_capacity_constraint
            assert len(block.maintain_reliability_capacity_constraint) == 0

        else:
            # DeliverabilityStatus = NOT FULLY_DELIVERABLE
            assert first_const_index not in block.maintain_reliability_capacity_constraint
            assert second_const_index in block.maintain_reliability_capacity_constraint
            assert last_const_index not in block.maintain_reliability_capacity_constraint
            assert len(block.maintain_reliability_capacity_constraint) > 0

    def test_NQC(self, make_component_with_block_copy, first_index):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        policies = asset.policies
        first_year = first_index[0]
        # skip test for resources that don't have a PRM policy
        if "TestPRM" not in policies.keys():
            pass
        # resources with an ELCC have an NQC of zero
        elif policies["TestPRM"].multiplier is None:
            assert block.NQC["TestPRM", first_year].expr() == 0.0
        else:
            link = policies["TestPRM"]
            NQC_multiplier = link.multiplier.data.at[first_year]
            block.reliability_capacity["TestPRM", first_year] = 100.0
            assert block.NQC["TestPRM", first_year].expr() == (NQC_multiplier * 100.0)

    def test_results_reporting(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert block.selected_capacity.doc == "Selected Capacity (MW)"
        assert block.retired_capacity.doc == "Retired Capacity (MW)"
        assert block.operational_capacity.doc == "Operational Capacity (MW)"
        assert block.annual_capital_cost.doc == "Annual Capital Cost ($)"
        assert block.annual_fixed_om_cost.doc == "Annual Fixed O&M Cost ($)"
        assert block.annual_total_investment_cost.doc == "Annual Total Investment Cost ($)"
        assert block.annual_total_operational_cost.doc == "Annual Total Operational Cost ($)"

    def test_integer_build(self, make_custom_component_with_block):
        """
        integer_build must be non-negative and selected_capacity = integer_build * integer_build_increment
        """
        asset = make_custom_component_with_block(integer_build_increment=50)
        block = asset.formulation_block

        # 1: Non-negative integer_build
        assert block.integer_build.domain.global_name == "NonNegativeIntegers"
        assert block.integer_build_constraint.body() == 0

        # 2: selected_capacity = integer_build * integer_build_increment
        # 2.1: integer_build_increment=50, with integer_build=2 --> selected capacity=100 (expected 100, valid)
        block.integer_build.fix(2)
        block.selected_capacity.fix(100)
        assert block.integer_build_constraint.body() == 0
        assert block.integer_build_constraint.upper() == 0
        assert block.integer_build_constraint.expr()

        # 2.2: integer_build_increment=50, with integer_build=1 --> selected capacity=50 (expected 100, invalid)
        block.integer_build.fix(1)
        assert block.integer_build_constraint.body() == 50
        assert block.integer_build_constraint.upper() == 0
        assert not block.integer_build_constraint.expr()

    def test_save_operational_capacity(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        modeled_years = list(block.model().MODELED_YEARS)

        block.operational_capacity[:] = 10
        asset.save_operational_capacity()

        assert (asset.operational_capacity.data == pd.Series(index=modeled_years, data=10)).all()

    def test_save_selected_capacity(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        block.selected_capacity = 10
        asset.save_selected_capacity()

        assert asset.selected_capacity == 10

    def test_save_retired_capacity(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        modeled_years = list(block.model().MODELED_YEARS)

        block.retired_capacity[:] = 10
        asset.save_retired_capacity()

        assert (asset.retired_capacity.data == pd.Series(index=modeled_years, data=10)).all()

    def test_save_cumulative_retired_capacity(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        modeled_years = list(block.model().MODELED_YEARS)

        block.retired_capacity[:] = 10
        asset.save_cumulative_retired_capacity()

        cumulative_value = 0
        for year in modeled_years:
            cumulative_value += 10
            assert asset.cumulative_retired_capacity.data.at[year] == cumulative_value

    def test_prod_sim_selected_capacity_constraint(self, make_component_with_block_copy_production_simulation):
        # All selected, retired, and operational capacities are set to zero
        asset = make_component_with_block_copy_production_simulation()
        block = asset.formulation_block

        # Constraint is valid
        assert block.prod_sim_selected_capacity_constraint.upper() == 0
        assert block.prod_sim_selected_capacity_constraint.lower() == 0
        assert block.prod_sim_selected_capacity_constraint.expr()

        # Constraint is violated
        block.selected_capacity = 4
        assert not block.prod_sim_selected_capacity_constraint.expr()

    def test_prod_sim_retired_capacity_constraint(
        self, make_component_with_block_copy_production_simulation, first_index
    ):
        # All selected, retired, and operational capacities are set to zero
        asset = make_component_with_block_copy_production_simulation()
        block = asset.formulation_block
        first_year = first_index[0]

        # Constraint is valid
        assert block.prod_sim_retired_capacity_constraint[first_year].upper() == 0
        assert block.prod_sim_retired_capacity_constraint[first_year].lower() == 0
        assert block.prod_sim_retired_capacity_constraint[first_year].expr()

        # Constraint is violated
        block.retired_capacity[first_year] = 4
        assert not block.prod_sim_retired_capacity_constraint[first_year].expr()

    def test_prod_sim_operational_capacity_constraint(
        self, make_component_with_block_copy_production_simulation, first_index
    ):
        # All selected, retired, and operational capacities are set to zero
        asset = make_component_with_block_copy_production_simulation()
        block = asset.formulation_block
        first_year = first_index[0]

        # Constraint is valid
        assert block.prod_sim_operational_capacity_constraint[first_year].upper() == 0
        assert block.prod_sim_operational_capacity_constraint[first_year].lower() == 0
        block.operational_capacity[first_year] = 0
        assert block.prod_sim_operational_capacity_constraint[first_year].expr()

        # Constraint is violated
        block.operational_capacity[first_year] = 4
        assert not block.prod_sim_operational_capacity_constraint[first_year].expr()

    def test_min_operational_capacity_constraint(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        assert block.min_operational_capacity_constraint.is_indexed()
        assert block.min_operational_capacity_constraint.index_set() is block.model().MODELED_YEARS

        asset.formulation_block.operational_capacity[pd.Timestamp("2025-01-01")] = 300
        assert block.min_operational_capacity_constraint[pd.Timestamp("2025-01-01")].body() == 300
        assert block.min_operational_capacity_constraint[pd.Timestamp("2025-01-01")].lower() == 100
        assert block.min_operational_capacity_constraint[pd.Timestamp("2025-01-01")].expr()

        asset.formulation_block.operational_capacity[pd.Timestamp("2030-01-01")] = 200
        assert block.min_operational_capacity_constraint[pd.Timestamp("2030-01-01")].body() == 200
        assert block.min_operational_capacity_constraint[pd.Timestamp("2030-01-01")].lower() == 200
        assert block.min_operational_capacity_constraint[pd.Timestamp("2030-01-01")].expr()

        asset.formulation_block.operational_capacity[pd.Timestamp("2035-01-01")] = 100
        assert block.min_operational_capacity_constraint[pd.Timestamp("2035-01-01")].body() == 100
        assert block.min_operational_capacity_constraint[pd.Timestamp("2035-01-01")].lower() == 200
        assert not block.min_operational_capacity_constraint[pd.Timestamp("2035-01-01")].expr()

    @pytest.mark.skip("Temporarily skip because this test takes a long time to complete.")
    def test_to_excel(self, test_asset, test_excel_api, test_model_template):
        if test_excel_api.platform in ["Darwin", "Windows"]:
            st = test_model_template

            # Test basic table writing
            st.book.sheets.add("Asset")
            sheet = st.book.sheets["Asset"]
            test_asset.to_excel(
                anchor_range=sheet.range("E11"), excel_api=test_excel_api, table_name=f"{test_asset.__class__.__name__}"
            )
            assert f"{test_asset.__class__.__name__}.__1" in [tbl.name for tbl in sheet.tables]

    # TODO: Fix this test.
    @pytest.mark.skip("This test is failing.")
    def test_to_excel_with_linkages_appended(self, test_asset, test_excel_api, test_model_template):
        if test_excel_api.platform in ["Darwin", "Windows"]:
            st = test_model_template
            # Test table with linkage instances
            st.book.sheets.add("Asset with Linkages")
            sheet = st.book.sheets["Asset with Linkages"]
            test_asset.to_excel(
                anchor_range=sheet.range("E11"),
                excel_api=test_excel_api,
                table_name=f"{test_asset.__class__.__name__}",
                linkages_to_write=[LinkageFieldsToWrite(name="ReliabilityContribution", instances=["PRM 1", "PRM 2"])],
                add_doc_hyperlinks=False,
            )
            assert f"{test_asset.__class__.__name__}.__2" in [tbl.name for tbl in sheet.tables]


class TestAssetGroup(TestAsset):
    _COMPONENT_CLASS = AssetGroup
    _COMPONENT_NAME = "AssetGroup1"
    _SYSTEM_COMPONENT_DICT_NAME = "asset_groups"

    @pytest.fixture(scope="class")
    def make_component_copy(self, test_model_with_operational_groups):
        def _make_copy():
            return getattr(test_model_with_operational_groups.system, self._SYSTEM_COMPONENT_DICT_NAME)[
                self._COMPONENT_NAME
            ]

        return _make_copy

    @pytest.fixture(scope="class")
    def make_component_with_block_copy(self, test_model_with_operational_groups):
        def _make_copy_with_block(component_name=None):
            if not component_name:
                return copy.deepcopy(
                    getattr(test_model_with_operational_groups.system, self._SYSTEM_COMPONENT_DICT_NAME)[
                        self._COMPONENT_NAME
                    ]
                )
            else:
                return copy.deepcopy(
                    getattr(test_model_with_operational_groups.system, self._SYSTEM_COMPONENT_DICT_NAME)[component_name]
                )

        return _make_copy_with_block

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

    @pytest.fixture(scope="class")
    def make_custom_component_with_block(self, test_system_with_operational_groups, test_temporal_settings):
        def _make_custom_asset(**kwargs):
            system_copy = test_system_with_operational_groups.copy()
            asset = getattr(system_copy, self._SYSTEM_COMPONENT_DICT_NAME)[self._COMPONENT_NAME]
            for key, value in kwargs.items():
                setattr(asset, key, value)

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

            return asset

        return _make_custom_asset

    def test_asset_potential_slack(self, make_component_with_block_copy):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision variables"""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "asset_potential_slack")

    def test_operational_capacity(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        for asset_instance in operational_group.asset_instances.values():
            asset_instance.formulation_block.operational_capacity[pd.Timestamp("2025-01-01")] = 50
        operational_group.formulation_block.operational_capacity[pd.Timestamp("2025-01-01")] = 100
        assert operational_group.formulation_block.group_operational_capacity_constraint[
            pd.Timestamp("2025-01-01")
        ].expr()

        for asset_instance in operational_group.asset_instances.values():
            asset_instance.formulation_block.operational_capacity[pd.Timestamp("2035-01-01")] = 75
        operational_group.formulation_block.operational_capacity[pd.Timestamp("2035-01-01")] = 150
        assert operational_group.formulation_block.group_operational_capacity_constraint[
            pd.Timestamp("2035-01-01")
        ].expr()

        operational_group.formulation_block.operational_capacity[pd.Timestamp("2035-01-01")] = 100
        assert not operational_group.formulation_block.group_operational_capacity_constraint[
            pd.Timestamp("2035-01-01")
        ].expr()

    def test_cumulative_selected_capacity(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        for asset in operational_group.asset_instances.values():
            asset.formulation_block.selected_capacity = 50
        assert (
            operational_group.formulation_block.cumulative_selected_capacity[pd.Timestamp("2025-01-01")].expr() == 100
        )
        assert (
            operational_group.formulation_block.cumulative_selected_capacity[pd.Timestamp("2035-01-01")].expr() == 100
        )
        for asset in operational_group.asset_instances.values():
            asset.formulation_block.selected_capacity = 25
        assert operational_group.formulation_block.cumulative_selected_capacity[pd.Timestamp("2025-01-01")].expr() == 50
        assert operational_group.formulation_block.cumulative_selected_capacity[pd.Timestamp("2035-01-01")].expr() == 50

    def test_selected_capacity(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        for asset in operational_group.asset_instances.values():
            asset.formulation_block.selected_capacity = 50
        assert operational_group.formulation_block.selected_capacity[pd.Timestamp("2025-01-01")].expr() == 50 * len(
            operational_group.asset_instances
        )
        assert operational_group.formulation_block.selected_capacity[pd.Timestamp("2030-01-01")].expr() == 0

        for ind, asset in enumerate(operational_group.asset_instances.values()):
            if ind == 0:
                asset.formulation_block.selected_capacity = 25
            else:
                asset.formulation_block.selected_capacity = 0
        assert operational_group.formulation_block.selected_capacity[pd.Timestamp("2025-01-01")].expr() == 25
        assert operational_group.formulation_block.selected_capacity[pd.Timestamp("2030-01-01")].expr() == 0

    def test_retired_capacity(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        for asset in operational_group.build_assets.values():
            asset.formulation_block.retired_capacity[pd.Timestamp("2025-01-01")] = 50
            asset.formulation_block.retired_capacity[pd.Timestamp("2030-01-01")] = 75

        assert operational_group.formulation_block.retired_capacity[pd.Timestamp("2025-01-01")].expr() == 100
        assert operational_group.formulation_block.retired_capacity[pd.Timestamp("2030-01-01")].expr() == 150

    def test_cumulative_retired_capacity(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        operational_group.formulation_block.retired_capacity[pd.Timestamp("2025-01-01")] = 50
        operational_group.formulation_block.retired_capacity[pd.Timestamp("2030-01-01")] = 75
        operational_group.formulation_block.retired_capacity[pd.Timestamp("2035-01-01")] = 100
        operational_group.formulation_block.retired_capacity[pd.Timestamp("2045-01-01")] = 25

        assert operational_group.formulation_block.cumulative_retired_capacity[pd.Timestamp("2025-01-01")].expr() == 50
        assert operational_group.formulation_block.cumulative_retired_capacity[pd.Timestamp("2030-01-01")].expr() == 125
        assert operational_group.formulation_block.cumulative_retired_capacity[pd.Timestamp("2035-01-01")].expr() == 225
        assert operational_group.formulation_block.cumulative_retired_capacity[pd.Timestamp("2045-01-01")].expr() == 250

    def test_planned_new_capacity(self, make_component_with_block_copy):
        """Planned new capacity is only defined at the Asset level, not AssetGroup."""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "planned_new_capacity")

    def test_can_build_new_constraint(self, make_component_with_block_copy):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision constraints"""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "can_build_new_constraint")

    def test_potential_constraint(self, make_component_with_block_copy):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision constraints"""
        operational_group = make_component_with_block_copy()
        block = operational_group.formulation_block
        assert block.potential_constraint.is_indexed()
        assert block.potential_constraint.index_set() is block.model().MODELED_YEARS

        assert len(operational_group.asset_instances) == 2
        for resource in operational_group.asset_instances.values():
            resource.formulation_block.selected_capacity.fix(250)
            resource.formulation_block.asset_potential_slack.fix(0)
        assert block.potential_constraint[pd.Timestamp("2025-01-01")].body() == 700  # 500 selected + 200 planned
        assert block.potential_constraint[pd.Timestamp("2025-01-01")].upper() == 600
        assert not block.potential_constraint[pd.Timestamp("2025-01-01")].expr()
        assert block.potential_constraint[pd.Timestamp("2030-01-01")].body() == 700  # 500 selected + 200 planned
        assert block.potential_constraint[pd.Timestamp("2030-01-01")].upper() == 700
        assert block.potential_constraint[pd.Timestamp("2030-01-01")].expr()

        for resource in operational_group.asset_instances.values():
            resource.formulation_block.selected_capacity.fix(250)
            resource.formulation_block.asset_potential_slack.fix(75)
        assert (
            block.potential_constraint[pd.Timestamp("2025-01-01")].body() == 550
        )  # 200 selected - 150 slack + 200 planned
        assert block.potential_constraint[pd.Timestamp("2025-01-01")].upper() == 600
        assert block.potential_constraint[pd.Timestamp("2025-01-01")].expr()

    def test_max_build_rate_constraint(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        block = operational_group.formulation_block

        assert block.max_build_rate_constraint.is_indexed()
        assert block.max_build_rate_constraint.index_set() is block.model().MODELED_YEARS

        for resource in operational_group.asset_instances.values():
            resource.formulation_block.selected_capacity.fix(500)
            resource.formulation_block.asset_potential_slack.fix(0)

        assert block.max_build_rate_constraint[pd.Timestamp("2025-01-01")].body() == 1200
        assert block.max_build_rate_constraint[pd.Timestamp("2025-01-01")].upper() == 600
        assert not block.max_build_rate_constraint[pd.Timestamp("2025-01-01")].expr()

        for resource in operational_group.asset_instances.values():
            resource.formulation_block.selected_capacity.fix(250)
            resource.formulation_block.asset_potential_slack.fix(75)

        assert block.max_build_rate_constraint[pd.Timestamp("2025-01-01")].body() == 550  # 500 selected - 150 slack +
        # 200 planned
        assert block.max_build_rate_constraint[pd.Timestamp("2025-01-01")].upper() == 600
        assert block.max_build_rate_constraint[pd.Timestamp("2025-01-01")].expr()

        assert list(block.max_build_rate_constraint.keys()) == [pd.Timestamp("2025-01-01")]  # This should be
        # true because asset group has no assets with build year besides 2025 and 0 planned new capacity

    def test_min_cumulative_new_build_constraint(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        block = operational_group.formulation_block
        assert block.min_cumulative_new_build_constraint.is_indexed()
        assert block.min_cumulative_new_build_constraint.index_set() is block.model().MODELED_YEARS

        assert len(operational_group.asset_instances) == 2
        for resource in operational_group.asset_instances.values():
            resource.formulation_block.selected_capacity.fix(100)
        assert block.min_cumulative_new_build_constraint[pd.Timestamp("2025-01-01")].body() == 200
        assert block.min_cumulative_new_build_constraint[pd.Timestamp("2025-01-01")].lower() == 100
        assert block.min_cumulative_new_build_constraint[pd.Timestamp("2025-01-01")].expr()

        assert block.min_cumulative_new_build_constraint[pd.Timestamp("2045-01-01")].body() == 200
        assert block.min_cumulative_new_build_constraint[pd.Timestamp("2045-01-01")].lower() == 250
        assert not block.min_cumulative_new_build_constraint[pd.Timestamp("2045-01-01")].expr()

        for resource in operational_group.asset_instances.values():
            resource.formulation_block.selected_capacity.fix(20)
        assert block.min_cumulative_new_build_constraint[pd.Timestamp("2025-01-01")].body() == 40
        assert block.min_cumulative_new_build_constraint[pd.Timestamp("2025-01-01")].lower() == 100
        assert not block.min_cumulative_new_build_constraint[pd.Timestamp("2025-01-01")].expr()

    def test_min_operational_capacity_constraint(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        block = operational_group.formulation_block
        assert block.min_operational_capacity_constraint.is_indexed()
        assert block.min_operational_capacity_constraint.index_set() is block.model().MODELED_YEARS
        for year in block.model().MODELED_YEARS:
            block.operational_capacity[year] = 200
        assert block.min_operational_capacity_constraint[pd.Timestamp("2025-01-01")].body() == 200
        assert block.min_operational_capacity_constraint[pd.Timestamp("2025-01-01")].lower() == 200
        assert block.min_operational_capacity_constraint[pd.Timestamp("2025-01-01")].expr()
        assert block.min_operational_capacity_constraint[pd.Timestamp("2030-01-01")].body() == 200
        assert block.min_operational_capacity_constraint[pd.Timestamp("2030-01-01")].lower() == 300
        assert not block.min_operational_capacity_constraint[pd.Timestamp("2030-01-01")].expr()
        for year in block.model().MODELED_YEARS:
            block.operational_capacity[year] = 100
        assert block.min_operational_capacity_constraint[pd.Timestamp("2025-01-01")].body() == 100
        assert block.min_operational_capacity_constraint[pd.Timestamp("2025-01-01")].lower() == 200
        assert not block.min_operational_capacity_constraint[pd.Timestamp("2025-01-01")].expr()

    def test_physical_lifetime_constraint(self, make_component_with_block_copy):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision constraints"""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "physical_lifetime_constraint")

    def test_retired_capacity_max_constraint(self, make_component_with_block_copy):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision constraints"""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "retired_capacity_max_constraint")

    def test_NQC(self, make_component_with_block_copy, first_index):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision constraints"""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "NQC")

    def test_max_reliability_capacity_constraint(self, make_component_with_block_copy, first_index):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision constraints"""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "max_reliability_capacity_constraint")

    def test_maintain_reliability_capacity_constraint(
        self, make_component_with_block_copy, make_custom_component_with_block, first_index, last_index
    ):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision constraints"""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "maintain_reliability_capacity_constraint")

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_retired_capacity_max_constraint_early_build_year(self, make_custom_component_with_block):
        super().test_retired_capacity_max_constraint_early_build_year(make_custom_component_with_block)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_retired_capacity_max_constraint_cannot_retire(self, make_custom_component_with_block):
        super().test_retired_capacity_max_constraint_cannot_retire(make_custom_component_with_block)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_retired_capacity_max_constraint_cannot_retire_no_lifetime(self, make_custom_component_with_block):
        super().test_retired_capacity_max_constraint_cannot_retire_no_lifetime(make_custom_component_with_block)

    def test_annual_capital_cost(self, make_component_with_block_copy):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision expressions"""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "annual_capital_cost")

    def test_annual_fixed_om_cost(self, make_component_with_block_copy):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision expressions"""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "annual_fixed_om_cost")

    def test_asset_potential_slack_cost(self, make_component_with_block_copy):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision expressions"""
        operational_group = make_component_with_block_copy()
        assert not hasattr(operational_group.formulation_block, "asset_potential_slack_cost")

    def test_annual_total_investment_cost(self, make_component_with_block_copy):
        """Because the operational group should just represent the sum of the investment decisions of the resources in
        that group, it should not have its own investment decision expressions"""
        operational_group = make_component_with_block_copy()
        assert list(operational_group.formulation_block.operational_capacity.index_set()) == [
            pd.Timestamp("2025-01-01"),
            pd.Timestamp("2030-01-01"),
            pd.Timestamp("2035-01-01"),
            pd.Timestamp("2045-01-01"),
        ]
        assert operational_group.formulation_block.annual_total_investment_cost[pd.Timestamp("2025-01-01")].expr() == 0
        assert operational_group.formulation_block.annual_total_investment_cost[pd.Timestamp("2030-01-01")].expr() == 0
        assert operational_group.formulation_block.annual_total_investment_cost[pd.Timestamp("2035-01-01")].expr() == 0
        assert operational_group.formulation_block.annual_total_investment_cost[pd.Timestamp("2045-01-01")].expr() == 0

    def test_results_reporting(self, make_component_with_block_copy):
        resource_group = make_component_with_block_copy()
        block = resource_group.formulation_block

        assert block.operational_capacity.doc == "Operational Capacity (MW)"
        assert block.annual_total_investment_cost.doc == "Annual Total Investment Cost ($)"
        assert block.annual_total_operational_cost.doc == "Annual Total Operational Cost ($)"

    @pytest.mark.skip(reason=("Retired capacities are not saved for AssetGroups."))
    def test_save_retired_capacity(self, make_component_with_block_copy):
        pass

    @pytest.mark.skip(reason=("Retired capacities are not saved for AssetGroups."))
    def test_save_cumulative_retired_capacity(self, make_component_with_block_copy):
        pass

    @pytest.mark.skip(reason=("Operational capacities are not saved for AssetGroups."))
    def test_save_operational_capacity(self, make_component_with_block_copy):
        pass

    @pytest.mark.skip(reason=("Selected capacities are not saved for AssetGroups."))
    def test_save_selected_capacity(self, make_component_with_block_copy_production_simulation):
        pass

    @pytest.mark.skip(reason=("Production Simulation constraints only apply to individual assets, not their groups."))
    def test_prod_sim_selected_capacity_constraint(self, make_component_with_block_copy_production_simulation):
        """Production Simulation constraints only apply to individual assets, not their groups."""
        super().test_prod_sim_selected_capacity_constraint(make_component_with_block_copy_production_simulation)

    @pytest.mark.skip(reason=("Production Simulation constraints only apply to individual assets, not their groups."))
    def test_prod_sim_retired_capacity_constraint(self, make_component_with_block_copy_production_simulation):
        """Production Simulation constraints only apply to individual assets, not their groups."""
        super().test_prod_sim_retired_capacity_constraint(make_component_with_block_copy_production_simulation)

    @pytest.mark.skip(reason=("Production Simulation constraints only apply to individual assets, not their groups."))
    def test_prod_sim_operational_capacity_constraint(self, make_component_with_block_copy_production_simulation):
        """Production Simulation constraints only apply to individual assets, not their groups."""
        super().test_prod_sim_operational_capacity_constraint(make_component_with_block_copy_production_simulation)

    @pytest.mark.skip
    def test_integer_build(self):
        """
        integer_build must be non-negative and selected_capacity = integer_build * integer_build_increment
        """
