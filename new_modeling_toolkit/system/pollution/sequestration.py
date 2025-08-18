from typing import ClassVar

from pyomo import environ as pyo

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.system.generics.plant import Plant
from new_modeling_toolkit.system.generics.plant import PlantGroup
from new_modeling_toolkit.system.generics.process import SequestrationProcess
from new_modeling_toolkit.system.pollution.pollutant import Pollutant


class Sequestration(Plant):
    SAVE_PATH: ClassVar[str] = "plants/sequestration_plants"

    @property
    def primary_processes(self) -> dict:
        """Primary process defined as process in which both consumed and produced products are the primary product."""
        return {
            process_name: process
            for process_name, process in self.processes.items()
            if isinstance(process, SequestrationProcess)
        }

    @property
    def primary_sequestration_rate(self) -> float:
        primary_sequestration_process = list(self.primary_processes.values())[0]
        return primary_sequestration_process.sequestration_rate

    def revalidate(self):
        super().revalidate()

        # Primary product should be pollutant
        if not isinstance(self.products[self.primary_product], Pollutant):
            raise AssertionError(
                f"`{self.__class__.__name__}` `{self.name}` should have a Pollutant as its primary product."
            )

        # Should have one SequestrationProcess where the consumed- and produced-product is the primary_product
        if len(self.primary_processes) != 1:
            raise AssertionError(
                f"`{self.__class__.__name__}` `{self.name}` should be linked to one SequestrationProcess where its "
                f"primary product `{self.primary_product}` is both the input product and output product."
                f"Check your `three_way_linkages.csv` file."
            )

    def _construct_operational_rules(
            self, model: ModelTemplate, construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        OUTPUTS = pyomo_components["OUTPUTS"]

        pyomo_components.update(
            # TODO: might want to redefine consumption: 0 if primary_product, otherwise same as Plant.consumption.
            #  Leaving as is for now because Plant.production depends on consumption expression
            produced_product_sequestered=pyo.Expression(
                OUTPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._produced_product_sequestered,
                doc=f"Hourly Sequestration of Output Product (({self.capacity_unit:e3})",
            ),
            produced_product_release=pyomo_components["produced_product_release"],
        )
        return pyomo_components

    def _produced_product_sequestered(self, block, output, modeled_year, dispatch_window, timestamp):
        """This represents sequestration of output product."""
        if output == self.primary_product:
            return block.operation[modeled_year, dispatch_window, timestamp] * self.primary_sequestration_rate
        else:
            return 0

    def _produced_product_release(self, block, output, modeled_year, dispatch_window, timestamp):
        """This represents release of output product **external** of the system. This will typically be 0,
        unless it is believed that the output product is instead a released atmospheric pollutant."""
        return (
            block.production[output, modeled_year, dispatch_window, timestamp]
            - block.produced_product_to_zone[output, modeled_year, dispatch_window, timestamp]
            - block.produced_product_sequestered[output, modeled_year, dispatch_window, timestamp]
        )


class SequestrationGroup(PlantGroup, Sequestration):
    SAVE_PATH: ClassVar[str] = "plants/sequestration_plants/groups"
    _NAME_PREFIX: ClassVar[str] = "sequestration_groups"
    _GROUPING_CLASS = Sequestration
