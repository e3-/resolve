from __future__ import annotations

from typing import ClassVar

import pint
from kit.core.custom_model import units
from pyomo import environ as pyo
from typing_extensions import deprecated

from resolve.core.component import LastUpdatedOrderedDict
from resolve.system.generics.demand import Demand
from resolve.system.generics.product import Product


class _EnergyCarrier(Product):
    """Parent class for electricity & fuels."""

    ...


class Electricity(_EnergyCarrier):
    """Electricity energy carrier for electric sector modeling.

    This class represents electricity as a special energy carrier that integrates
    with the electric sector optimization model components including resources (generators),
    loads (consumption), and storage systems.

    Attributes:
        SAVE_PATH: Directory path for saving electricity product configurations.
        unit: Physical unit for electricity accounting (kWh).

    Note:
        For any electric sector optimization (e.g., system includes resources), one non-commodity
        Electricity product must be specified.

        Electricity production and consumption methods override the base Product
        methods to include flows from electric sector resources and loads that
        may not be explicitly linked through product relationships.

        Unit conversion: Electric sector components use MWh while product
        accounting uses kWh, requiring a 1e3 multiplication factor.
    """

    SAVE_PATH: ClassVar[str] = "electricity_products"
    unit: pint.Unit | str = units.kWh

    # TODO when fuels and electric sector refactor occurs: We should ensure _consumers and _producers to include
    #  resources and loads.

    def _total_production(self, block, modeled_year, dispatch_window, timestamp):
        """Calculate total electricity production including electric sector resources, demands, and plants.

        Aggregates electricity production from both explicitly linked producers
        (through product relationships) and all electric sector resources and
        resource groups. This comprehensive approach ensures all electricity
        generation is captured regardless of linkage methodology.

        Args:
            block: Pyomo block containing production variables.
            modeled_year: Year for production calculation.
            dispatch_window: Dispatch window (e.g., representative day).
            timestamp: Specific hour within the dispatch window.

        Returns:
            Total hourly electricity production in kWh, including
            production from explicitly linked producers plus all electric
            sector resources with power output capabilities.

        Note:
            Unit conversion: Electric sector resources use MWh while electricity
            products use kWh, requiring multiplication by 1e3.

        Todo:
            Ideally, an Electricity instance would be linked to all Resource
            instances through explicit product relationships, eliminating the
            need for system-wide resource iteration.
        """
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
        """Calculate total electricity consumption including electric sector resources, demands, and plants.

        Aggregates electricity consumption from explicitly linked consumers (through
        product relationships), electric sector resources with power input (e.g.,
        storage charging, pumped hydro), and all system loads. This comprehensive
        approach ensures all electricity consumption is captured.

        Args:
            block: Pyomo block containing consumption variables.
            modeled_year: Year for consumption calculation.
            dispatch_window: Dispatch window (e.g., representative day).
            timestamp: Specific hour within the dispatch window.

        Returns:
            float: Total hourly electricity consumption in kWh, including:
                - Consumption from explicitly linked consumers
                - Power input from resources (storage charging, etc.)
                - Consumption from all system loads

        Note:
            Unit conversion: Electric sector resources and loads use MWh while
            electricity products use kWh, requiring multiplication by 1e3.

        Todo:
            Ideally, an Electricity instance would be linked to all Resource
            and Load instances through explicit product relationships, eliminating
            the need for system-wide iteration.
        """
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
    """Energy-specific demand component for non-electric sector energy consumption.

    This class represents energy demands in non-electric sectors of the economy
    that consume energy carriers such as candidate fuels (natural gas, hydrogen,
    etc.) or electricity. It extends the base Demand class with energy-specific
    constraints and validation while maintaining nearly identical functionality.

    The class enforces that consumed inputs must be subclasses of _EnergyCarrier.

    Attributes:
        SAVE_PATH: Directory path for saving energy demand configurations.
    """

    SAVE_PATH: ClassVar[str] = "demands/energy_demands"

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        return super()._construct_operational_rules(model, construct_costs)

    # TODO: think about a validator which can be used to enforce that EnergyDemand must have units associated with energy carrier


class FinalFuelDemand(EnergyDemand):
    """Deprecated alias for EnergyDemand class.

    This class provides backward compatibility for models that use the old
    FinalFuelDemand class name. It is functionally identical to EnergyDemand
    but is deprecated and should not be used in new model implementations.

    Attributes:
        SAVE_PATH: Directory path for saving final fuel demand configurations.

    Note:
        This class is deprecated. Use EnergyDemand instead for new implementations.
        The renaming reflects a broader scope beyond just "final fuels" to include
        all types of energy carrier demands in non-electric sectors.

    Deprecated:
        FinalFuelDemand has been renamed to EnergyDemand. This class will be
        removed in a future version.
    """

    SAVE_PATH: ClassVar[str] = "final_fuels"

    @deprecated("FinalFuelDemand has been renamed EnergyDemand")
    def __init__(self, **kwargs):
        """Initialize FinalFuelDemand with deprecation warning.

        Args:
            **kwargs: Keyword arguments passed to the parent EnergyDemand class.

        Deprecated:
            Use EnergyDemand instead of FinalFuelDemand.
        """
        super().__init__(**kwargs)
