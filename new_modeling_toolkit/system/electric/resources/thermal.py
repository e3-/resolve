from typing import ClassVar

import pandas as pd
import pyomo.environ as pyo
from pydantic import computed_field
from pydantic import Field
from typing_extensions import Annotated

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.linkage import CandidateFuelToResource
from new_modeling_toolkit.system.electric.resources.generic import GenericResource
from new_modeling_toolkit.system.electric.resources.generic import GenericResourceGroup
from new_modeling_toolkit.system.electric.resources.unit_commitment import UnitCommitmentResource


class ThermalResource(GenericResource):
    """Fuel-burning resource."""

    SAVE_PATH: ClassVar[str] = "resources/thermal"

    _DOCS_URL: ClassVar[str] = (
        "https://docs.ethree.com/projects/kit/en/main/system/electric/resources/thermal.html#new_modeling_toolkit.system.thermal.ThermalResource."
    )

    ###################################
    # Operational Dispatch Attributes #
    ###################################

    fuel_burn_slope: Annotated[
        float | None, Metadata(category=FieldCategory.OPERATIONS, units=units.MMBtu / units.MWh, warning_bounds=(0, 17))
    ] = Field(
        default=None,
        description="Fuel burn slope (MMBTU/MWh). Aka average heat rate. The average heat rate = average fuel "
        "consumption per unit of output over a certain range of output levels. It is calculated by dividing "
        "the total fuel consumption by the total output over that range (a(x) = f(x) / x). It provides a "
        "measure of the overall efficiency of the power generation system over a given period of time or "
        "output range. Required when resource is an operational group or does not belong to one.",
        title=f"Heat Rate (Average or Marginal)",
        ge=0,
        alias="average_heat_rate",
    )

    ############
    # Linkages #
    ############
    candidate_fuels: Annotated[
        dict[str, CandidateFuelToResource], Metadata(linkage_order="from", category=FieldCategory.OPERATIONS)
    ] = Field(
        {},
        description="String Input. This input links a specified `candidate_fuels` to this `ThermalResource` . (e.g. Natural_Gas to gas_CCGT).",
    )

    @computed_field(title="Fuel(s)")
    @property
    def fuel_names_string(self) -> str:
        """This property concatenates the keys in the candidate_fuels dictionary for results reporting."""
        if len(self.candidate_fuels) == 0:
            return "None"
        else:
            return ",".join(map(str, self.candidate_fuels.keys()))

    def revalidate(self):
        super().revalidate()
        # Validate that there is at least one candidate fuel linked to the thermal resource.
        if self.has_operational_rules and len(self.candidate_fuels) == 0:
            raise ValueError(
                f"{self.name} Thermal Resource that's not in an operational group needs at least one CandidateFuel. "
                f"Please add 'CandidateFuelToResource' linkage(s)."
            )
        # Validate that fuel burn slope is defined if resource is an operational group or does not belong to one.
        if self.has_operational_rules and self.fuel_burn_slope is None:
            raise ValueError(
                f"{self.name} Thermal Resource that's not in an operational group needs a fuel burn slope defined."
            )
        # Check that the resource's candidate fuel(s) are linked to any annual energy policy it's linked to.
        if self.annual_energy_policies:
            for policy_linkage in self.annual_energy_policies.values():
                policy = policy_linkage.instance_to
                # Give warning if its candidate fuels are not linked
                if not set(self.candidate_fuels.keys()).intersection(set(policy.candidate_fuels.keys())):
                    raise ValueError(
                        f"{self.__class__.__name__} instance {self.name} is linked to the {policy.__class__.__name__} "
                        f"instance {policy.name}, but none of the resource's candidate fuels are linked to this policy. "
                        f"Check your linkages.csv."
                    )

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        candidate_fuels = pyo.Set(initialize=list(self.candidate_fuels.keys()))
        pyomo_components.update(CANDIDATE_FUELS=candidate_fuels)

        pyomo_components.update(
            resource_fuel_consumption_in_timepoint_mmbtu=pyo.Var(
                candidate_fuels,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                units=pyo.units.MBtu,
                within=pyo.NonNegativeReals,
                doc="Resource Fuel Consumption by Fuel (MMBtu/hr)",
            ),
            power_output_by_fuel=pyo.Var(
                candidate_fuels,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                units=pyo.units.MW,
                within=pyo.NonNegativeReals,
                doc="Resource Power Output by Fuel (MW)",
            ),
            power_output_by_fuel_constraint=pyo.Constraint(
                candidate_fuels,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._power_output_by_fuel_constraint,
            ),
            annual_resource_fuel_consumption_by_fuel=pyo.Expression(
                candidate_fuels,
                model.MODELED_YEARS,
                rule=self._annual_resource_fuel_consumption_by_fuel,
                doc="Annual Fuel Consumption (MMBtu)",
            ),
            annual_power_output_by_fuel=pyo.Expression(
                candidate_fuels,
                model.MODELED_YEARS,
                rule=self._annual_power_output_by_fuel,
                doc="Annual Power Output by Fuel (MWh)",
            ),
            total_resource_fuel_consumption_in_timepoint_mmbtu=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._total_resource_fuel_consumption_in_timepoint_mmbtu,
                doc="Total Resource Fuel Consumption (MW)",
            ),
            annual_total_resource_fuel_consumption_mmbtu=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_total_resource_fuel_consumption_mmbtu,
                doc="Annual Fuel Consumption (MMBtu)",
            ),
            resource_fuel_cost=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._resource_fuel_cost,
            ),
            annual_total_resource_fuel_cost=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_total_resource_fuel_cost,
                doc="Annual Fuel Cost ($)",
            ),
            annual_total_operational_cost=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_total_operational_cost,
                doc="Annual Total Operational Cost ($)",
            ),
            resource_fuel_consumption_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._resource_fuel_consumption_constraint,
            ),
        )

        return pyomo_components

    def _annual_resource_fuel_consumption_by_fuel(self, block, candidate_fuel: str, modeled_year: pd.Timestamp):
        """Calculate the total fuel consumption of each fuel linked to this resource."""
        return block.model().sum_timepoint_component_slice_to_annual(
            block.resource_fuel_consumption_in_timepoint_mmbtu[candidate_fuel, modeled_year, :, :]
        )

    def _total_resource_fuel_consumption_in_timepoint_mmbtu(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Calculate the resource's fuel consumption across all candidate fuels
        Args:
            block: The block object associated with the expression
            modeled_year (pd.Timestamp): The timestamp representing the modeled year
            dispatch_window (pd.Timestamp): The timestamp representing the dispatch window
            timestamp (pd.Timestamp): The timestamp for which the constraint is being evaluated

        Returns:
            pyo.Expression.
        """
        total_fuel_consumption = sum(
            self.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                fuel, modeled_year, dispatch_window, timestamp
            ]
            for fuel in self.candidate_fuels
        )
        return total_fuel_consumption

    def _annual_total_resource_fuel_consumption_mmbtu(self, block, modeled_year: pd.Timestamp):
        """
        Calculate the resource's total annual fuel consumption across all candidate fuels
        Args:
            block: The block object associated with the expression
            modeled_year (pd.Timestamp): The timestamp representing the modeled year
            dispatch_window (pd.Timestamp): The timestamp representing the dispatch window
            timestamp (pd.Timestamp): The timestamp for which the constraint is being evaluated

        Returns:
            pyo.Expression.
        """
        annual_total_fuel_consumption = self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.total_resource_fuel_consumption_in_timepoint_mmbtu[modeled_year, :, :]
        )
        return annual_total_fuel_consumption

    def _resource_fuel_cost(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Calculate fuel costs from all candidate fuels that are flagged as commodities
        Args:
            block: The block object associated with the expression
            modeled_year (pd.Timestamp): The timestamp representing the modeled year
            dispatch_window (pd.Timestamp): The timestamp representing the dispatch window
            timestamp (pd.Timestamp): The timestamp for which the constraint is being evaluated
        Returns:
            pyo.Expression. The sum of the resource's candidate fuel costs
        """
        fuel_costs = sum(
            self.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                fuel, modeled_year, dispatch_window, timestamp
            ]
            # TODO: Use timeseries.resample_simple_extend_years(weather_years) instead of timestamp.replace to be
            #  robust against leap years
            * self.candidate_fuels[fuel].instance_from.fuel_price_per_mmbtu.data.at[
                timestamp.replace(year=modeled_year.year)
            ]
            for fuel in self.candidate_fuels
            if self.candidate_fuels[fuel].instance_from.fuel_is_commodity_bool
        )
        return fuel_costs

    def _annual_total_resource_fuel_cost(self, block, modeled_year: pd.Timestamp):
        annual_total_fuel_costs = self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.resource_fuel_cost[modeled_year, :, :]
        )
        return annual_total_fuel_costs

    def _resource_fuel_consumption_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        The sum of the power provided by a resource's candidate fuels should equal the resource's total power_output
        multiplied by the resource's heat rate
        Args:
            block: The block object associated with the constraint
            modeled_year (pd.Timestamp): The timestamp representing the modeled year
            dispatch_window (pd.Timestamp): The timestamp representing the dispatch window
            timestamp (pd.Timestamp): The timestamp for which the constraint is being evaluated
        Returns:
            pyo.Constraint
        """
        linearized_fuel_burn = (
            self.fuel_burn_slope * self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
        )

        return linearized_fuel_burn == sum(
            self.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                fuel, modeled_year, dispatch_window, timestamp
            ]
            for fuel in self.candidate_fuels
        )

    def _power_output_by_fuel_constraint(
        self,
        block: pyo.Block,
        candidate_fuel: str,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        """Same as resource fuel consumption constraint, but by candidate fuel"""
        linearized_fuel_burn = (
            self.fuel_burn_slope * block.power_output_by_fuel[candidate_fuel, modeled_year, dispatch_window, timestamp]
        )

        return (
            linearized_fuel_burn
            == block.resource_fuel_consumption_in_timepoint_mmbtu[
                candidate_fuel, modeled_year, dispatch_window, timestamp
            ]
        )

    def _annual_power_output_by_fuel(
        self,
        block: pyo.Block,
        candidate_fuel: str,
        modeled_year: pd.Timestamp,
    ):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.power_output_by_fuel[candidate_fuel, modeled_year, :, :]
        )

    def _annual_total_operational_cost(self, block, modeled_year: pd.Timestamp):
        """
        The total annual operational costs of the resource. This expression is updated from the definition in GenericResource to include the resource_fuel_cost.
        Args:
            block: The block object associated with the expression
            modeled_year (pd.Timestamp): The timestamp representing the modeled year
        Returns:
            pyo.Expression
        """
        total_operational_cost = (
            super()._annual_total_operational_cost(block, modeled_year)
            + self.formulation_block.annual_total_resource_fuel_cost[modeled_year]
        )

        return total_operational_cost


class ThermalUnitCommitmentResource(ThermalResource, UnitCommitmentResource):
    SAVE_PATH: ClassVar[str] = "resources/thermal"

    ###################################
    # Operational Dispatch Attributes #
    ###################################

    fuel_burn_slope: Annotated[
        float | None, Metadata(category=FieldCategory.OPERATIONS, units=units.MMBtu / units.MWh, warning_bounds=(0, 17))
    ] = Field(
        default=None,
        description="The marginal heat rate represents the rate of change of fuel consumption with respect to the level of output. Mathematically, it is the derivative of the heat input function with respect to output level (m(x) = δy / δx). It tells us how much additional fuel is required to produce one more unit of output (megawatt hour). Required when resource is an operational group or does not belong to one.",
        title=f"Heat Rate (Average or Marginal)",
        ge=0,
        alias="marginal_heat_rate",
    )

    # todo: this should be MMBTU/whatever frequency the model is in. Will the unit conversion handle that? Or is unit conversion a thing?
    fuel_burn_intercept: Annotated[
        float | None,
        Metadata(category=FieldCategory.OPERATIONS, units=units.MMBtu / units.hour, warning_bounds=(0, 1000)),
    ] = Field(
        default=None,
        description="Fuel burn intercept per generating unit. Represents the minimum amount of fuel used when a unit is on. Required when resource is an operational group or does not belong to one.",
        title=f"No-Load Fuel Burn",
    )
    start_fuel_use: Annotated[float, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        0, description="[UC] Amount of fuel used per unit start [MMBTU/start]", title=f"Start Fuel Use", ge=0
    )
    addition_to_load: float = Field(
        0,
        ge=0,
        warning_bounds=(0, 1),
        description="Synchronous condenser addition to load. Multiplier to commited capacity. Default 0.",
    )

    def revalidate(self):
        """
        Validate that there is at least one candidate fuel linked to the thermal UC resource.
        """
        super().revalidate()
        if self.has_operational_rules and self.fuel_burn_intercept is None:
            raise ValueError(
                f"{self.name} Thermal Resource that's not in an operational group needs a fuel burn intercept defined."
            )

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)
        candidate_fuels = pyo.Set(initialize=list(self.candidate_fuels.keys()))

        pyomo_components.update(
            resource_fuel_consumption_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._resource_fuel_consumption_constraint,
            ),
            power_output_by_fuel_constraint=pyo.Constraint(
                candidate_fuels,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._power_output_by_fuel_constraint,
            ),
            total_power_output_by_fuel_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._total_power_output_by_fuel_constraint,
            ),
            synchronous_condenser_addition_to_load=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._synchronous_condenser_addition_to_load,
                doc="Synchronous Condenser Additional Load (MW)",
            ),
        )

        if construct_costs:
            pyomo_components.update(
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                )
            )

        return pyomo_components

    def _resource_fuel_consumption_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp
    ):
        """
        Fuel consumption is represented by a simplified linear equation: fuel_consumption = (marginal_heat_rate[MMBtu/MWh] * power_output[MWh]) + (committed_units * min_fuel_burn[MMBTU/committed_unit]) + (start_units * start_fuel_use[MMBTU/start_unit])

        Args:
            block: The block object associated with the constraint.
            modeled_year (pd.Timestamp): The timestamp representing the modeled year.
            dispatch_window (pd.Timestamp): The timestamp representing the dispatch window.
            timestamp (pd.Timestamp): The timestamp for which the constraint is being evaluated.

        Returns: pyo.Constraint. The sum of fuel consumption of a resource's candidate fuels == the resource's total fuel burn

        """

        linearized_fuel_burn = (
            self.fuel_burn_slope * self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
        )
        commitment_fuel_burn = (
            self.formulation_block.committed_units[modeled_year, dispatch_window, timestamp]  # from unitcommitment
            * self.fuel_burn_intercept
        )
        start_fuel_use = (
            self.formulation_block.start_units[modeled_year, dispatch_window, timestamp]  # from unitcommitment
            * self.start_fuel_use
        )
        return linearized_fuel_burn + commitment_fuel_burn + start_fuel_use == sum(
            self.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                fuel, modeled_year, dispatch_window, timestamp
            ]
            for fuel in self.candidate_fuels
        )

    def _power_output_by_fuel_constraint(
        self,
        block: pyo.Block,
        candidate_fuel: str,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        """Same as resource fuel consumption constraint, but by candidate fuel"""
        linearized_fuel_burn = (
            self.fuel_burn_slope * block.power_output_by_fuel[candidate_fuel, modeled_year, dispatch_window, timestamp]
        )
        commitment_fuel_burn = (
            block.committed_units[modeled_year, dispatch_window, timestamp]  # from unitcommitment
            * self.fuel_burn_intercept
        )
        start_fuel_use = (
            self.formulation_block.start_units[modeled_year, dispatch_window, timestamp]  # from unitcommitment
            * self.start_fuel_use
        )

        return (
            linearized_fuel_burn + commitment_fuel_burn + start_fuel_use
            >= block.resource_fuel_consumption_in_timepoint_mmbtu[
                candidate_fuel, modeled_year, dispatch_window, timestamp
            ]
        )

    def _total_power_output_by_fuel_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        return block.power_output[modeled_year, dispatch_window, timestamp] == sum(
            block.power_output_by_fuel[candidate_fuel, modeled_year, dispatch_window, timestamp]
            for candidate_fuel in self.candidate_fuels.keys()
        )

    def _synchronous_condenser_addition_to_load(
        self,
        block,
        modeled_year: pd.Timestamp,
        dispatch_window,
        timestamp: pd.Timestamp,
    ):
        return (
            self.addition_to_load * self.formulation_block.committed_capacity[modeled_year, dispatch_window, timestamp]
        )

    def _annual_total_operational_cost(self, block, modeled_year: pd.Timestamp):
        total_operational_cost = (
            self.formulation_block.annual_power_output_variable_cost[modeled_year]
            - self.formulation_block.annual_production_tax_credit[modeled_year]
            + self.formulation_block.annual_total_resource_fuel_cost[modeled_year]
            + self.formulation_block.annual_start_and_shutdown_cost[modeled_year]
        )

        return total_operational_cost


class ThermalResourceGroup(GenericResourceGroup, ThermalResource):
    SAVE_PATH: ClassVar[str] = "resources/thermal/groups"
    _NAME_PREFIX: ClassVar[str] = "thermal_resource_group"
    _GROUPING_CLASS = ThermalResource


    def revalidate(self):
        """
        Validate that there is at least one candidate fuel linked to the thermal resource.
        """
        super().revalidate()
        if self.has_operational_rules and len(self.candidate_fuels) == 0:
            raise ValueError(
                f"{self.name} Thermal Resource Group operational group needs at least one CandidateFuel. "
                f"Please add 'CandidateFuelToResource' linkage(s)."
            )
        if self.has_operational_rules and self.fuel_burn_slope is None:
            raise ValueError(f"{self.name} Thermal Resource Group operational group needs a fuel burn slope defined.")


class ThermalUnitCommitmentResourceGroup(GenericResourceGroup, ThermalUnitCommitmentResource):
    SAVE_PATH: ClassVar[str] = "resources/thermal/groups"
    _NAME_PREFIX: ClassVar[str] = "thermal_unit_commitment_resource_group"
    _GROUPING_CLASS = ThermalUnitCommitmentResource

    def revalidate(self):
        """
        Validate that there is at least one candidate fuel linked to the thermal resource.
        """
        super().revalidate()
        if self.has_operational_rules and len(self.candidate_fuels) == 0:
            raise ValueError(
                f"{self.name} Thermal UC Resource Group operational group needs at least one CandidateFuel. "
                f"Please add 'CandidateFuelToResource' linkage(s)."
            )
        if self.has_operational_rules and self.fuel_burn_slope is None:
            raise ValueError(
                f"{self.name} Thermal UC Resource Group operational group needs a fuel burn slope defined."
            )
        if self.has_operational_rules and self.fuel_burn_intercept is None:
            raise ValueError(
                f"{self.name} Thermal UC Resource Group operational group needs a fuel burn intercept defined."
            )
