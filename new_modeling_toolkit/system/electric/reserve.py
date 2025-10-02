import enum
from typing import Annotated
from typing import ClassVar
from typing import Optional

import pyomo.environ as pyo
from loguru import logger
from pydantic import Field

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import dir_str
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.linkage import IncrementalReserveType
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.three_way_linkage import CustomConstraintLinkage


@enum.unique
class ReserveDirection(enum.Enum):
    DOWN = "down"
    UP = "up"


class Reserve(component.Component):
    SAVE_PATH: ClassVar[str] = "reserves"

    direction: ReserveDirection
    exclusive: bool = True
    load_following_percentage: Optional[float] = None
    custom_constraints: Annotated[
        dict[str, CustomConstraintLinkage], Metadata(linkage_order=3, default_exclude=True)
    ] = {}

    requirement: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero,
        default_freq="H",
        up_method="interpolate",
        down_method="first",
    )
    _dynamic_requirement: ts.NumericTimeseries
    category: Optional[str] = None

    ######################
    # Mapping Attributes #
    ######################

    resources: Annotated[dict[str, linkage.ResourceToReserve], Metadata(linkage_order="from")] = {}
    zones: Annotated[dict[str, linkage.ReserveToZone], Metadata(linkage_order="to")] = {}
    loads: Annotated[dict[str, linkage.LoadToReserve], Metadata(linkage_order="from")] = {}

    #######################################
    # Unserved Reserve Penalty #
    #######################################

    penalty_unserved_reserve: float = Field(
        10000,
        description="Modeled penalty for unserved operating reserves.",
    )  # $10,000 / MW

    def revalidate(self):
        # Warn that operating reserve % of gross load will override any ``requirement`` timeseries.
        if self.zones:
            for zone, l in self.zones.items():
                if (l.incremental_requirement_hourly_scalar.data > 0).any() and (self.requirement.data > 0).any():
                    logger.warning(
                        f"For {self.name}: Operating reserve requirement as percentage of {zone} gross load "
                        f"(from {l.__class__.__name__} linkage) will be added to `requirement` timeseries attribute."
                    )
                # Raise an error to avoid double counting of zones and loads therein both linked to reserve requirement
                if self.loads:
                    for load in l.instance_to.loads.keys():
                        if load in self.loads.keys():
                            raise ValueError(
                                f"The Zone {zone} and one of the load components within it, {load}, are "
                                f"both linked to the Reserve {self.name}, which would result in "
                                f"double-counting of the operating reserve requirement. Check your "
                                f"linkages.csv file."
                            )

        # Guard against double-counting of incremental reserve requirements from resource groups and member resources
        if self.resources:
            for r, l in self.resources.items():
                resource = l.instance_from
                if (l.incremental_requirement_hourly_scalar.data > 0).any() and hasattr(resource, "asset_instances"):
                    member_assets = set(resource.asset_instances.keys())
                    linked_resources = set(self.resources.keys())
                    if member_assets & linked_resources:
                        raise ValueError(
                            f"The resource group {resource.name} and some of its member assets are both contributing to "
                            f"the incremental reserve requirement of {self.name}. This could result in double-counting. "
                            f"Check your linkages.csv."
                        )

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:

        #############
        # Variables #
        #############

        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        pyomo_components.update(
            unserved_reserve_MW=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                units=pyo.units.MWh,
                within=pyo.NonNegativeReals,
            )
        )

        RESERVE_RESOURCES = pyo.Set(initialize=self.resources.keys())
        pyomo_components.update(
            total_provided_reserve_MW=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._total_provided_reserve,
                doc="Total Provided Reserve (MW)",
            ),
            resource_incremental_reserve_requirement=pyo.Expression(
                RESERVE_RESOURCES,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._resource_incremental_reserve_requirement,
                doc="Incremental Reserve Requirement (MW)",
            ),
            operating_reserve_requirement=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._operating_reserve_requirement,
                doc="Operating Reserve Requirement (MW)",
            ),
            annual_reserve_requirement=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_reserve_requirement,
                doc="Annual Reserve Requirement (MW)",
            ),
            annual_provided_reserve=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_provided_reserve,
                doc="Annual Provided Reserve (MW)",
            ),
            operating_reserve_balance_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._operating_reserve_balance_constraint,
            ),
            annual_unserved_reserve=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_unserved_reserve,
                doc="Annual Unserved Reserve (MW)",
            ),
            annual_reserve_provided_by_resource=pyo.Expression(
                RESERVE_RESOURCES,
                model.MODELED_YEARS,
                rule=self._annual_reserve_provided_by_resource,
                doc="Annual Provided Reserve (MW)",
            ),
        )

        if construct_costs:
            pyomo_components.update(
                unserved_reserve_cost_in_timepoint=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._unserved_reserve_cost_in_timepoint,
                ),
                annual_unserved_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_unserved_cost,
                    doc="Annual Unserved Reserve Cost ($)",
                ),
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                ),
            )
        return pyomo_components

    def _resource_incremental_reserve_requirement(self, block, resource, modeled_year, dispatch_window, timestamp):
        """The incremental hourly reserve requirement from a specific resource"""
        linkage = self.resources[resource]
        resource_instance = linkage.instance_from
        hourly_scalar = linkage.incremental_requirement_hourly_scalar.data
        return hourly_scalar.at[timestamp.replace(year=modeled_year.year)] * (
            resource_instance.formulation_block.power_output_max[modeled_year, dispatch_window, timestamp]
            if linkage.scalar_type == IncrementalReserveType.HOURLY_PROFILE
            and hasattr(resource_instance.formulation_block, "power_output_max")
            else resource_instance.formulation_block.operational_capacity[modeled_year]
        )

    def _operating_reserve_requirement(self, block, modeled_year, dispatch_window, timestamp):
        """The calculated operating reserve requirement, including increment reserve needs."""
        requirement = (
            # flat requirement
            self.requirement.data.at[timestamp.replace(year=modeled_year.year)]

            # incremental requirement for individual load components
            # because load components are assigned a zone, this captures any reserve-zone relationships
            + sum(
                load.incremental_requirement_hourly_scalar.data.at[timestamp.replace(year=modeled_year.year)]
                * load.instance_from.get_load(modeled_year.year, timestamp)
                for load in self.loads.values()
            )
            # incremental requirements for resource additions
            + sum(
                block.resource_incremental_reserve_requirement[resource, modeled_year, dispatch_window, timestamp]
                for resource in self.resources.keys()
            )
            # TODO: Add resource incremental requirement annual scalar? Currently not used or tested
            # + sum(
            #     resource.incremental_requirement_annual_scalar.data.at[modeled_year]
            #     for resource in self.resources.values()
            # )
            # incremental requirement from zonal gross load
            + sum(
                zone.incremental_requirement_hourly_scalar.data.at[timestamp.replace(year=modeled_year.year)]
                * zone.instance_to.get_aggregated_load(modeled_year.year, timestamp)
                for zone in self.zones.values()
            )
        )

        return requirement

    def _operating_reserve_balance_constraint(self, block, modeled_year, dispatch_window, timestamp):
        """Operating reserve requirements must be met by eligible resources on the system.

        If a ``LoadToReserve.incremental_requirement_hourly_scalar`` is defined, this requirement will override
        any ``Reserve.requirement``. For now, this is calculated in the Pyomo model, but this seems like
        it could be calculated as a property of the ``Reserve`` instance.
        """
        return (
            self.formulation_block.total_provided_reserve_MW[modeled_year, dispatch_window, timestamp]
            + self.formulation_block.unserved_reserve_MW[modeled_year, dispatch_window, timestamp]
            == self.formulation_block.operating_reserve_requirement[modeled_year, dispatch_window, timestamp]
        )

    def _total_provided_reserve(self, block, modeled_year, dispatch_window, timestamp):
        return sum(
            (
                resource_linkage.instance_from.formulation_block.provide_reserve[
                    self.name, modeled_year, dispatch_window, timestamp
                ]
                if hasattr(resource_linkage.instance_from.formulation_block, "provide_reserve")
                else 0
            )
            for resource_linkage in self.resources.values()
        )

    def _annual_reserve_requirement(self, block, modeled_year):
        annual_reserve_requirement = self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.operating_reserve_requirement[modeled_year, :, :]
        )
        return annual_reserve_requirement

    def _annual_provided_reserve(self, block, modeled_year):
        annual_provided_reserve = self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.total_provided_reserve_MW[modeled_year, :, :]
        )
        return annual_provided_reserve

    def _annual_reserve_provided_by_resource(self, block, resource: str, modeled_year):
        if hasattr(self.resources[resource].instance_from.formulation_block, "provide_reserve"):
            return block.model().sum_timepoint_component_slice_to_annual(
                self.resources[resource].instance_from.formulation_block.provide_reserve[self.name, modeled_year, :, :]
            )
        else:
            return 0

    def _annual_unserved_reserve(self, block, modeled_year):
        annual_unserved_reserve = self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.unserved_reserve_MW[modeled_year, :, :]
        )
        return annual_unserved_reserve

    def _annual_total_operational_cost(self, block, modeled_year):
        return self.penalty_unserved_reserve * block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.unserved_reserve_MW[modeled_year, :, :]
        )

    def _unserved_reserve_cost_in_timepoint(self, block, modeled_year, dispatch_window, timestamp):
        return (
            self.formulation_block.unserved_reserve_MW[modeled_year, dispatch_window, timestamp]
            * self.penalty_unserved_reserve
        )

    def _annual_unserved_cost(self, block, modeled_year):
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.unserved_reserve_cost_in_timepoint[modeled_year, :, :]
        )


if __name__ == "__main__":
    # r = Reserve(name="load following")
    # print(r)

    r3 = Reserve.from_dir(dir_str.data_dir / "interim" / "reserves")
    print(r3)
