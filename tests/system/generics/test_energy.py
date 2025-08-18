import pytest

from new_modeling_toolkit.system import Demand
from new_modeling_toolkit.system import Plant
from new_modeling_toolkit.system.generics.energy import _EnergyCarrier
from new_modeling_toolkit.system.generics.energy import Electricity
from new_modeling_toolkit.system.generics.energy import EnergyDemand
from tests.system.generics.test_demand import TestDemand
from tests.system.generics.test_product import TestCommodityProduct
from tests.system.generics.test_product import TestProduct


class TestEnergyDemand(TestDemand):
    _COMPONENT_CLASS = EnergyDemand
    _COMPONENT_NAME = "GenericEnergyDemand1"
    _SYSTEM_COMPONENT_DICT_NAME = "energy_demands"

    @pytest.fixture(scope="class")
    def unit_string(self):
        return "MMBtu"


class TestElectricity(TestProduct):
    _COMPONENT_NAME = "Electricity"
    _COMPONENT_CLASS = Electricity
    _SYSTEM_COMPONENT_DICT_NAME = "electricity_products"

    def test_total_consumption(self, make_component_with_block_copy, first_index, last_index):
        product = make_component_with_block_copy()
        block = product.formulation_block
        resources = block.model().system.resources
        loads = block.model().system.loads

        for consumer in product.consumers.keys():
            if isinstance(product.consumers[consumer], Plant) or isinstance(product.consumers[consumer], Demand):
                product.consumers[consumer].formulation_block.consumption[self._COMPONENT_NAME, first_index] = 0

        input_resources = 0
        for resource in resources.values():
            if hasattr(resource.formulation_block, "power_input"):
                resource.formulation_block.power_input[first_index].fix(0)
                input_resources += 1

        total_load = sum(load.get_load(first_index[0].year, first_index[2]) for load in loads.values()) * 1000

        assert not block.total_consumption[first_index].expr() == 100
        assert block.total_consumption[first_index].expr() == total_load

        for consumer in product.consumers.keys():
            if isinstance(product.consumers[consumer], Plant) or isinstance(product.consumers[consumer], Demand):
                product.consumers[consumer].formulation_block.consumption[self._COMPONENT_NAME, last_index] = 100

        for resource in resources.values():
            if hasattr(resource.formulation_block, "power_input"):
                resource.formulation_block.power_input[last_index].fix(100)

        total_load = sum(load.get_load(last_index[0].year, last_index[2]) for load in loads.values()) * 1000

        assert (
            block.total_consumption[last_index].expr()
            == (100 * len(product.consumers) + 100 * 1e3 * input_resources * isinstance(product, Electricity))
            + total_load
        )


class TestEnergyCarrier(TestProduct):
    _COMPONENT_NAME = "GenericEnergyCarrier1"
    _COMPONENT_CLASS = _EnergyCarrier
    _SYSTEM_COMPONENT_DICT_NAME = "energy_carriers"


class TestCommodityEnergyCarrier(TestCommodityProduct):
    _COMPONENT_NAME = "CommodityEnergyCarrier"
    _COMPONENT_CLASS = _EnergyCarrier
    _SYSTEM_COMPONENT_DICT_NAME = "energy_carriers"
