from typing import ClassVar

from pyomo import environ as pyo

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.system.generics.plant import Plant
from new_modeling_toolkit.system.generics.plant import PlantGroup
from new_modeling_toolkit.system.generics.product import Process
from new_modeling_toolkit.system.pollution.pollutant import Pollutant


class NegativeEmissionsTechnology(Plant):
    SAVE_PATH: ClassVar[str] = "plants/negative_emissions_technologies"

    @property
    def primary_processes(self) -> dict[tuple[str, str], Process]:
        """Primary process defined as process in which both consumed and produced products are the primary product."""
        return {
            process_name: process
            for process_name, process in self.processes.items()
            if (
                process.consumed_product.name == self.primary_product
                and process.produced_product.name == self.primary_product
            )
        }

    def revalidate(self):
        super().revalidate()

        # Primary product should be a Pollutant
        if not isinstance(self.products[self.primary_product], Pollutant):
            raise AssertionError(
                f"`{self.__class__.__name__}` `{self.name}` should have a Pollutant as its primary product."
            )
        # Should have one process where the consumed- and produced-product is the primary_product
        if len(self.primary_processes) < 1:
            raise AssertionError(
                f"`{self.__class__.__name__}` `{self.name}` is not linked to any processes where the primary product "
                f"`{self.primary_product}` is both the input product and output product."
                f"Check your `three_way_linkages.csv` file."
            )

        # Primary process input- and output- capture rates should be nonzero.
        def non_zero_capture_rates(process):
            return process.input_capture_rate > 0 and process.output_capture_rate > 0

        if not all([non_zero_capture_rates(process) for process in self.primary_processes.values()]):
            raise AssertionError(
                f"The primary process(es) linked to `{self.__class__.__name__}` `{self.name}` "
                f"should have non-zero input and output capture rates. Check your `three_way_linkages.csv` file."
            )

    def _construct_operational_rules(
        self, model: ModelTemplate, construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        return pyomo_components


class NegativeEmissionsTechnologyGroup(PlantGroup, NegativeEmissionsTechnology):
    SAVE_PATH: ClassVar[str] = "plants/negative_emissions_technologies/groups"
    _NAME_PREFIX: ClassVar[str] = "negative_emissions_technology_groups"
    _GROUPING_CLASS = NegativeEmissionsTechnology
