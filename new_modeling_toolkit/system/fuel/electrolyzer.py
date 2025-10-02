from typing import ClassVar

from pyomo import environ as pyo

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlant
from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlantGroup
from new_modeling_toolkit.system.generics.energy import Electricity


class Electrolyzer(FuelProductionPlant):
    """
    Electrolyzer produces hydrogen directly from electricity or heat.
    """

    SAVE_PATH: ClassVar[str] = "plants/fuel_production_plants/electrolyzers"

    def revalidate(self):
        super().revalidate()

        def only_one_process():
            return len(self.processes) == 1

        def consumed_product_is_electricity():
            consumed_product = list(self.consumed_products.values())[0]
            return isinstance(consumed_product, Electricity)

        if not only_one_process():
            raise ValueError(
                f"Electrolyzer `{self.name}` is linked to more than one Process. Check your `three_way_linkages.csv` file."
            )
        if not consumed_product_is_electricity():
            raise ValueError(
                f"Electrolyzer `{self.name}` must be linked to a Process with electricity as the consumed product. Check your `three_way_linkages.csv` file."
            )

    def _construct_operational_rules(
            self, model: ModelTemplate, construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        return pyomo_components


class ElectrolyzerGroup(FuelProductionPlantGroup, Electrolyzer):
    SAVE_PATH: ClassVar[str] = "plants/fuel_production_plants/electrolyzers/groups"
    _NAME_PREFIX: ClassVar[str] = "electrolyzer_groups"
    _GROUPING_CLASS = Electrolyzer
