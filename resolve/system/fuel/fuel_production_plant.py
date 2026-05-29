from typing import ClassVar

from pyomo import environ as pyo

from resolve.core.component import LastUpdatedOrderedDict
from resolve.core.model import ModelTemplate
from resolve.system.fuel.candidate_fuel import CandidateFuel
from resolve.system.generics.plant import Plant
from resolve.system.generics.plant import PlantGroup


class FuelProductionPlant(Plant):
    """
    A subclass of Plant that is specifically designed to produce some kind of "fuel" rather than electricity.
    """

    SAVE_PATH: ClassVar[str] = "fuel_production_plants"

    def revalidate(self):
        super().revalidate()

        # Validate that the primary product is a candidate fuel
        primary_product = self.produced_products[self.primary_product]
        if not isinstance(primary_product, CandidateFuel):
            raise AssertionError(
                f"A `{self.__class__.__name__}` must have a candidate fuel as a primary product. "
                f"`{self.name}` primary product `{self.primary_product}` is not a candidate fuel."
            )

    def _construct_operational_rules(
        self, model: ModelTemplate, construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        return pyomo_components


class FuelProductionPlantGroup(PlantGroup, FuelProductionPlant):
    SAVE_PATH: ClassVar[str] = "plants/fuel_production_plants/groups"
    _NAME_PREFIX: ClassVar[str] = "fuel_production_plant_groups"
    _GROUPING_CLASS = FuelProductionPlant
