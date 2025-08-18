import pytest

from new_modeling_toolkit.system.pollution.negative_emissions_technology import NegativeEmissionsTechnology
from new_modeling_toolkit.system.pollution.negative_emissions_technology import NegativeEmissionsTechnologyGroup
from tests.system.generics.test_plant import TestPlant
from tests.system.generics.test_plant import TestPlantGroup


class TestNegativeEmissionsTechnology(TestPlant):
    _COMPONENT_CLASS = NegativeEmissionsTechnology
    _COMPONENT_NAME = "NegativeEmissionsTechnology1"
    _SYSTEM_COMPONENT_DICT_NAME = "negative_emissions_technologies"

    primary_product = "Pollutant1"

    @pytest.fixture(scope="class")
    def capacity_unit_string(self):
        return "metric_ton/h"

    def test_production(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        assert plant.primary_product == self.primary_product
        assert isinstance(plant.primary_product, str)

        # Process 1: production = operation
        block.operation[first_index] = 10
        assert block.production[plant.primary_product, first_index].expr() == 10

    def test_consumed_commodity_product_cost(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        assert block.consumed_commodity_product_cost[first_index].expr() == 0

    def test_annual_consumed_commodity_product_cost(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        modeled_year, _, _ = first_index
        assert block.annual_consumed_commodity_product_cost[modeled_year].expr() == 0


class TestNegativeEmissionsTechnologyGroup(TestPlantGroup, TestNegativeEmissionsTechnology):
    _COMPONENT_CLASS = NegativeEmissionsTechnologyGroup
    _COMPONENT_NAME = "negative_emissions_technology_group"
    _SYSTEM_COMPONENT_DICT_NAME = "negative_emissions_technology_groups"
