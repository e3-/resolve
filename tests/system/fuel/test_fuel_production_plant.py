import pytest

from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlant
from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlantGroup
from tests.system.generics.test_plant import TestPlant
from tests.system.generics.test_plant import TestPlantGroup


class TestFuelProductionPlant(TestPlant):
    _COMPONENT_CLASS = FuelProductionPlant
    _COMPONENT_NAME = "FuelProductionPlant1"
    _SYSTEM_COMPONENT_DICT_NAME = "fuel_production_plants"

    primary_product = "CandidateFuel2"

    @pytest.fixture(scope="class")
    def capacity_unit_string(self):
        return "MMBtu/h"


class TestFuelProductionPlantGroup(TestPlantGroup, TestFuelProductionPlant):
    _COMPONENT_CLASS = FuelProductionPlantGroup
    _COMPONENT_NAME = "fuel_production_plant_group"
    _SYSTEM_COMPONENT_DICT_NAME = "fuel_production_plant_groups"
