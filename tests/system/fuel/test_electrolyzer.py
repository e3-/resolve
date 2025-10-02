from new_modeling_toolkit.system.fuel.electrolyzer import Electrolyzer
from tests.system.fuel.test_fuel_production_plant import TestFuelProductionPlant
from tests.system.fuel.test_fuel_production_plant import TestFuelProductionPlantGroup


class TestElectrolyzer(TestFuelProductionPlant):
    _COMPONENT_CLASS = Electrolyzer
    _COMPONENT_NAME = "Electrolyzer1"
    _SYSTEM_COMPONENT_DICT_NAME = "electrolyzers"

    def test_production(self, make_component_with_block_copy, first_index):
        electrolyzer = make_component_with_block_copy()
        block = electrolyzer.formulation_block
        assert isinstance(electrolyzer.primary_product, str)

        block.operation[first_index] = 10
        assert block.production[electrolyzer.primary_product, first_index].expr() == 10

    def test_consumed_commodity_product_cost(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        assert block.consumed_commodity_product_cost[first_index].expr() == 0.0
        assert block.consumed_commodity_product_cost[last_index].expr() == 0.0

    def test_annual_consumed_commodity_product_cost(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        first_modeled_year, _, _ = first_index
        last_modeled_year, _, _ = last_index
        assert block.annual_consumed_commodity_product_cost[first_modeled_year].expr() == 0.0
        assert block.annual_consumed_commodity_product_cost[last_modeled_year].expr() == 0.0


class TestElectrolyzerGroup(TestFuelProductionPlantGroup, TestElectrolyzer):
    _COMPONENT_CLASS = Electrolyzer
    _COMPONENT_NAME = "electrolyzer_group"
    _SYSTEM_COMPONENT_DICT_NAME = "electrolyzer_groups"
