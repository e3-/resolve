from __future__ import annotations

from typing import ClassVar

import pint
from pyomo import environ as pyo
from typing_extensions import deprecated

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.system.generics.demand import Demand
from new_modeling_toolkit.system.generics.product import Product


class _EnergyCarrier(Product):
    """Parent class for electricity & fuels."""
    ...


class Electricity(_EnergyCarrier):
    SAVE_PATH: ClassVar[str] = "electricity_products"
    unit: pint.Unit | str = units.kWh

    # TODO when fuels and electric sector refactor occurs: We should ensure _consumers and _producers to include
    #  resources and loads.

    def _total_production(self, block, modeled_year, dispatch_window, timestamp):
        """Total production for electricity includes resource production as well as production by demands and plants.
        Ideally, an `Electricity` instance would be linked to all `Resource` instances in the system, but this is
        worked around by looping over all system resources. Note that electricity units from resources are MWh,
        while the units for `Electricity` products are kWh, hence the 1e3 factor."""
        resources = block.model().system.resources | block.model().system.resource_groups
        return (
            super()._total_production(block, modeled_year, dispatch_window, timestamp)
            + sum(
                resource.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
                for resource in resources.values()
                if hasattr(resource.formulation_block, "power_output")
            )
            * 1e3
        )

    def _total_consumption(self, block, modeled_year, dispatch_window, timestamp):
        """Total consumption for electricity includes resource  and load consumption as well as production by demands and plants.
        Ideally, an `Electricity` instance would be linked to all `Resource` instances in the system, but this is
        worked around by looping over all system resources and loads. Note that electricity units from resources are MWh,
        while the units for `Electricity` products are kWh, hence the 1e3 factor."""
        resources = block.model().system.resources | block.model().system.resource_groups
        loads = block.model().system.loads
        return (
            super()._total_consumption(block, modeled_year, dispatch_window, timestamp)
            + sum(
                resource.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
                for resource in resources.values()
                if hasattr(resource.formulation_block, "power_input")
            )
            * 1e3
            + sum(load.get_load(modeled_year.year, timestamp) for load in loads.values()) * 1e3
        )


# TODO: Do we really need an EnergyDemand class? Seems to be redundant with `Demand` class
class EnergyDemand(Demand):
    """
    An energy demand is an element of the non-electric sector economy that demands a CandidateFuel or electricity. It
    operates nearly identically to a Demand but requires a subclass of _EnergyCarrier as its consumed input.
    """

    SAVE_PATH: ClassVar[str] = "demands/energy_demands"

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        return super()._construct_operational_rules(model, construct_costs)

    # TODO: think about a validator which can be used to enforce that EnergyDemand must have units associated with energy carrier



class FinalFuelDemand(EnergyDemand):
    SAVE_PATH: ClassVar[str] = "final_fuels"
    @deprecated("FinalFuelDemand has been renamed EnergyDemand")
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
