import pandas as pd
import pytest

from new_modeling_toolkit.system.generics.transportation import Transportation
from tests.system.test_asset import TestAsset


class TestTransportation(TestAsset):
    _COMPONENT_CLASS = Transportation
    _COMPONENT_NAME = "Transportation_1"
    _SYSTEM_COMPONENT_DICT_NAME = "transportations"

    @pytest.fixture(scope="class")
    def product_names(self, make_component_with_block_copy) -> list[str]:
        transportation = make_component_with_block_copy()
        product_names = [product_linkage.product.name for product_linkage in transportation.products.values()]
        return product_names

    @pytest.fixture(scope="class")
    def unit_string(self):
        return "MWh"

    def test_annual_capital_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert asset.physical_lifetime == 20
        assert asset.annualized_capital_cost == 20
        block.selected_capacity.fix(100)

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
            pd.Timestamp("2035-01-01 00:00"),
        ]:
            assert block.annual_capital_cost[year].expr() == 2_000

        assert block.annual_capital_cost[pd.Timestamp("2045-01-01 00:00")].expr() == 0

    def test_annual_fixed_om_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert asset.annualized_fixed_om_cost.data.at[asset.build_year] == 10
        assert asset.planned_capacity.data.at[asset.build_year] == 100

        block.selected_capacity.fix(50)
        block.retired_capacity.fix(0)
        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            assert block.annual_fixed_om_cost[year].expr() == 1_500

        block.selected_capacity.fix(50)
        block.retired_capacity[pd.Timestamp("2035-01-01 00:00")].fix(50)
        for year, expected in [
            (pd.Timestamp("2025-01-01 00:00"), 1_500),
            (pd.Timestamp("2030-01-01 00:00"), 1_500),
            (pd.Timestamp("2035-01-01 00:00"), 1_000),
            (pd.Timestamp("2045-01-01 00:00"), 1_000),
        ]:
            assert block.annual_fixed_om_cost[year].expr() == expected

    def test_annual_total_investment_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert asset.physical_lifetime == 20
        assert asset.annualized_capital_cost == 20
        assert asset.annualized_fixed_om_cost.data.at[asset.build_year] == 10
        assert asset.planned_capacity.data.at[asset.build_year] == 100

        block.selected_capacity.fix(50)
        block.retired_capacity.fix(0)
        for year, expected in [
            (pd.Timestamp("2025-01-01 00:00"), 2_500),
            (pd.Timestamp("2030-01-01 00:00"), 2_500),
            (pd.Timestamp("2035-01-01 00:00"), 2_500),
            (pd.Timestamp("2045-01-01 00:00"), 1_500),
        ]:
            assert block.annual_total_investment_cost[year].expr() == expected

        block.selected_capacity.fix(50)
        block.retired_capacity[pd.Timestamp("2035-01-01 00:00")].fix(50)
        for year, expected in [
            (pd.Timestamp("2025-01-01 00:00"), 2_500),
            (pd.Timestamp("2030-01-01 00:00"), 2_500),
            (pd.Timestamp("2035-01-01 00:00"), 2_000),
            (pd.Timestamp("2045-01-01 00:00"), 1_000),
        ]:
            assert block.annual_total_investment_cost[year].expr() == expected

    def test_transmit_product_forward_constraint(self, make_component_with_block_copy, product_names, first_index):
        transportation = make_component_with_block_copy()
        block = transportation.formulation_block
        block.operational_capacity[first_index[0]] = 200

        for id, product in enumerate(product_names):
            block.transmit_product_forward[product, first_index].fix(100 * (id + 1))

        assert block.transmit_product_forward_constraint[first_index].ub == 0
        assert block.transmit_product_forward_constraint[first_index].body() == 100 + 200 - 200
        assert not block.transmit_product_forward_constraint[first_index].expr()

        for product in product_names:
            block.transmit_product_forward[product, first_index].fix(100)

        assert block.transmit_product_forward_constraint[first_index].body() == 0
        assert block.transmit_product_forward_constraint[first_index].expr()

    def test_transmit_product_reverse_constraint(self, make_component_with_block_copy, product_names, first_index):
        transportation = make_component_with_block_copy()
        block = transportation.formulation_block
        block.operational_capacity[first_index[0]] = 200

        for id, product in enumerate(product_names):
            block.transmit_product_reverse[product, first_index].fix(100 * (id + 1))

        assert block.transmit_product_reverse_constraint[first_index].ub == 0
        assert block.transmit_product_reverse_constraint[first_index].body() == 100 + 200 - 200
        assert not block.transmit_product_reverse_constraint[first_index].expr()

        for product in product_names:
            block.transmit_product_reverse[product, first_index].fix(100)

        assert block.transmit_product_reverse_constraint[first_index].body() == 0
        assert block.transmit_product_reverse_constraint[first_index].expr()

    def test_transportation_mileage_constraint(self, make_component_with_block_copy, product_names, last_index):
        transportation = make_component_with_block_copy()
        block = transportation.formulation_block
        block.operational_capacity[last_index[0]] = 150

        for product in product_names:
            block.transmit_product_forward[product, last_index].fix(100)
            block.transmit_product_reverse[product, last_index].fix(20)

        assert block.transportation_mileage_constraint[last_index].ub == 0
        assert block.transportation_mileage_constraint[last_index].body() == (100 + 20) * len(product_names) - 150
        assert not block.transportation_mileage_constraint[last_index].expr()

        for product in product_names:
            block.transmit_product_forward[product, last_index].fix(150 / 2 / len(product_names))
            block.transmit_product_reverse[product, last_index].fix(150 / 2 / len(product_names))

        assert block.transportation_mileage_constraint[last_index].body() == 0
        assert block.transportation_mileage_constraint[last_index].expr()

    def test_net_transmit_product(self, make_component_with_block_copy, product_names, first_index, last_index):
        transportation = make_component_with_block_copy()
        block = transportation.formulation_block

        product_name = product_names[0]
        block.transmit_product_forward[product_name, first_index].fix(10)
        block.transmit_product_reverse[product_name, first_index].fix(5)
        assert block.net_transmit_product[product_name, first_index].expr() == 5

        block.transmit_product_forward[product_name, last_index].fix(5)
        block.transmit_product_reverse[product_name, last_index].fix(5)
        assert block.net_transmit_product[product_name, last_index].expr() == 0

    def test_hurdle_cost_forward_and_reverse(self, make_component_with_block_copy, product_names, first_index):
        transportation = make_component_with_block_copy()
        block = transportation.formulation_block

        for product_name in product_names:
            block.transmit_product_forward[product_name, first_index].fix(20)
            block.transmit_product_reverse[product_name, first_index].fix(10)

        assert block.hurdle_cost_forward[first_index].expr() == 20 * 4 * len(product_names)
        assert block.hurdle_cost_reverse[first_index].expr() == 10 * 2 * len(product_names)

    def test_annual_total_operational_cost(self, make_component_with_block_copy, first_index):
        transportation = make_component_with_block_copy()
        block = transportation.formulation_block

        modeled_year = first_index[0]
        total_operational_cost = 0
        for dispatch_window, timestamp in list(block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS):
            block.hurdle_cost_forward[modeled_year, dispatch_window, timestamp] = 10
            block.hurdle_cost_reverse[modeled_year, dispatch_window, timestamp] = 15
            total_operational_cost += (
                25
                * block.model().dispatch_window_weights[dispatch_window]
                * block.model().num_days_per_modeled_year[modeled_year]
            )

        assert block.annual_total_operational_cost[modeled_year].expr() == total_operational_cost

    def test_results_reporting(self, make_component_with_block_copy, unit_string):
        transportation = make_component_with_block_copy()
        block = transportation.formulation_block
        transportation._construct_output_expressions(construct_costs=True)
        assert block.from_zone.doc == "Zone From"
        assert block.to_zone.doc == "Zone To"
        assert block.annual_gross_forward_flow.doc == f"Total Gross Forward Flow ({unit_string})"
        assert block.annual_gross_reverse_flow.doc == f"Total Gross Reverse Flow ({unit_string})"
        assert block.annual_net_forward_flow.doc == f"Total Net Forward Flow ({unit_string})"
        assert block.annual_forward_hurdle_cost.doc == "Forward Hurdle Cost ($)"
        assert block.annual_reverse_hurdle_cost.doc == "Reverse Hurdle Cost ($)"
