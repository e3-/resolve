import pytest

from new_modeling_toolkit.system.generics.process import SequestrationProcess
from new_modeling_toolkit.system.pollution.sequestration import Sequestration
from new_modeling_toolkit.system.pollution.sequestration import SequestrationGroup
from tests.system.generics.test_plant import TestPlant
from tests.system.generics.test_plant import TestPlantGroup


class TestSequestration(TestPlant):
    _COMPONENT_CLASS = Sequestration
    _COMPONENT_NAME = "Sequestration1"
    _SYSTEM_COMPONENT_DICT_NAME = "sequestration_plants"

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

    def test_primary_processes(self, make_component_with_block_copy):
        plant = make_component_with_block_copy()
        primary_processes = plant.primary_processes

        assert len(primary_processes) == 1
        assert isinstance(list(plant.primary_processes.values())[0], SequestrationProcess)

    def test_primary_sequestration_rate(self, make_component_with_block_copy):
        plant = make_component_with_block_copy()

        assert plant.primary_sequestration_rate == 0.8

    def test_produced_product_sequestered(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        primary_sequestration_rate = 0.8
        pollutant_name = self.primary_product

        block.operation[first_index] = 100
        assert (
            block.produced_product_sequestered[pollutant_name, first_index].expr() == 100 * primary_sequestration_rate
        )

    def test_produced_product_release(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        primary_capture_rate = 0.1
        primary_sequestration_rate = 0.8
        pollutant_name = self.primary_product

        block.operation[first_index] = 100

        production = 100
        produced_product_to_zone = production * primary_capture_rate
        produced_product_sequestered = production * primary_sequestration_rate

        assert (
            block.produced_product_release[pollutant_name, first_index].expr()
            == production - produced_product_to_zone - produced_product_sequestered
        )


class TestSequestrationGroup(TestPlantGroup, TestSequestration):
    _COMPONENT_CLASS = SequestrationGroup
    _COMPONENT_NAME = "sequestration_group"
    _SYSTEM_COMPONENT_DICT_NAME = "sequestration_groups"
