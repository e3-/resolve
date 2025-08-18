from typing import Annotated
from typing import ClassVar

import pandas as pd
from pyomo import environ as pyo

from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.system.electric.reserve import ReserveDirection
from new_modeling_toolkit.system.electric.resources.storage import StorageResource
from new_modeling_toolkit.system.electric.resources.storage import StorageResourceGroup
from new_modeling_toolkit.system.electric.resources.variable.solar import SolarResource
from new_modeling_toolkit.system.electric.resources.variable.solar import SolarResourceGroup
from new_modeling_toolkit.system.electric.resources.variable.variable import VariableResource
from new_modeling_toolkit.system.electric.resources.variable.variable import VariableResourceGroup
from new_modeling_toolkit.system.electric.resources.variable.wind import WindResource
from new_modeling_toolkit.system.electric.resources.variable.wind import WindResourceGroup


class HybridVariableResource(VariableResource):
    SAVE_PATH: ClassVar[str] = "resources/hybrid_variable"

    hybrid_storage_resources: Annotated[
        dict[str, linkage.HybridStorageResourceToHybridVariableResource], Metadata(linkage_order="from")
    ] = {}

    @property
    def hybrid_linkage(self):
        hybrid_linkage_name = list(self.hybrid_storage_resources.keys())[0]
        hybrid_linkage = self.hybrid_storage_resources[hybrid_linkage_name]

        return hybrid_linkage

    def revalidate(self):
        super().revalidate()
        if len(self.hybrid_storage_resources) > 1:
            raise ValueError(
                f"A HybridStorageResource can only be linked to one other HybridVariableResource, but multiple linkages "
                f"were found on the Hybrid Storage Resource {self.name}: `{[link.instance_to.name for link in self.hybrid_variable_resources.values()]}`"
            )

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)
        return pyomo_components


class HybridSolarResource(HybridVariableResource, SolarResource):
    SAVE_PATH: ClassVar[str] = "resources/hybrid_solar"


class HybridWindResource(HybridVariableResource, WindResource):
    SAVE_PATH: ClassVar[str] = "resources/hybrid_wind"


class HybridStorageResource(StorageResource):
    SAVE_PATH: ClassVar[str] = "resources/hybrid_storage"

    hybrid_variable_resources: Annotated[
        dict[str, linkage.HybridStorageResourceToHybridVariableResource], Metadata(linkage_order="to")
    ] = {}

    def revalidate(self):
        super().revalidate()
        if len(self.hybrid_variable_resources) == 0:
            raise ValueError(
                f"A HybridStorageResource must be linked to exactly one HybridVariableResource, but no linkage "
                f"was found. Check your linkages.csv file."
            )
        if len(self.hybrid_variable_resources) > 1:
            raise ValueError(
                f"A HybridStorageResource can only be linked to one other HybridVariableResource, but multiple linkages "
                f"were found on the Hybrid Storage Resource {self.name}: `{[link.instance_to.name for link in self.hybrid_variable_resources.values()]}`"
            )

    @property
    def hybrid_linkage(self):
        hybrid_linkage_name = list(self.hybrid_variable_resources.keys())[0]
        hybrid_linkage = self.hybrid_variable_resources[hybrid_linkage_name]

        return hybrid_linkage

    @property
    def hybrid_erm_policy_linkage(self):
        """Gets the ERM policy linkage for the hybrid storage resource for accessibility."""
        if len(self.erm_policies) == 0:
            return None
        linkage_name = list(self.erm_policies.keys())[0]
        return self.erm_policies[linkage_name]

    @property
    def paired_variable_resource(self) -> HybridVariableResource:
        return self.hybrid_linkage.instance_to

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)

        if self.hybrid_linkage.pairing_ratio is not None:
            pyomo_components.update(
                hybrid_pairing_ratio_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    rule=self._hybrid_pairing_ratio_constraint,
                )
            )

        if self.erm_policies:
            pyomo_components.update(
                erm_hybrid_power_output_interconnection_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_hybrid_power_output_interconnection_constraint,
                ),
                erm_hybrid_power_output_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_hybrid_power_output_constraint,
                ),
                erm_hybrid_power_input_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_hybrid_power_input_constraint,
                ),
                erm_hybrid_power_input_interconnection_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_hybrid_power_input_interconnection_constraint,
                ),
            )

        return pyomo_components

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        # This writes constraints for the storage resource and
        # hybrid-specific constraints (interconnection limit, grid charging allowed)

        # Constraints for paired variable resource are already automatically written; hybrid_variable_resources
        # is included in self.resources_to_construct in updated_dispatch_model_v2.py as of 2023-06-20

        # IMPORTANT NOTE: The heuristic dispatch considers the hybrid resource as a single resource
        # and determines the output of the collective paired resource. HOWEVER, the constraints for the optimization
        # treat the two resources' power_output as separate.
        # They still enforce constraints that exist between the two resources.

        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        pyomo_components.update(
            hybrid_power_output_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._hybrid_power_output_constraint,
            ),
            hybrid_power_output_interconnection_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._hybrid_power_output_interconnection_constraint,
            ),
            hybrid_power_input_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._hybrid_power_input_constraint,
            ),
            hybrid_power_input_interconnection_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._hybrid_power_input_interconnection_constraint,
            ),
        )

        return pyomo_components

    def _hybrid_power_output_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        """The sum of the storage and paired variable resources' output power and reserves may
        not exceed the operational capacity"""

        if not self.hybrid_linkage.paired_charging_constraint_active_in_year.data.at[modeled_year]:
            return pyo.Constraint.Skip

        reserves = sum(
            block.provide_reserve[reserve_name, modeled_year, dispatch_window, timestamp]
            for reserve_name, reserve_link in self.reserves.items()
            if reserve_link.instance_to.direction == ReserveDirection.UP
        )

        paired_reserves = sum(
            self.paired_variable_resource.formulation_block.provide_reserve[
                reserve_name, modeled_year, dispatch_window, timestamp
            ]
            for reserve_name, reserve_link in self.paired_variable_resource.reserves.items()
            if reserve_link.instance_to.direction == ReserveDirection.UP
        )

        return (
            block.power_output[modeled_year, dispatch_window, timestamp]
            + reserves
            + self.paired_variable_resource.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            + paired_reserves
            <= self.paired_variable_resource.formulation_block.operational_capacity[modeled_year]
        )

    def _hybrid_power_output_interconnection_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        """The sum of the storage and paired variable resources' output power and reserves may
        not exceed the interconnection limit"""

        if not self.hybrid_linkage.paired_charging_constraint_active_in_year.data.at[modeled_year]:
            return pyo.Constraint.Skip
        if self.hybrid_linkage.interconnection_limit_mw is None:
            return pyo.Constraint.Skip

        reserves = sum(
            block.provide_reserve[reserve_name, modeled_year, dispatch_window, timestamp]
            for reserve_name, reserve_link in self.reserves.items()
            if reserve_link.instance_to.direction == ReserveDirection.UP
        )

        paired_reserves = sum(
            self.paired_variable_resource.formulation_block.provide_reserve[
                reserve_name, modeled_year, dispatch_window, timestamp
            ]
            for reserve_name, reserve_link in self.paired_variable_resource.reserves.items()
            if reserve_link.instance_to.direction == ReserveDirection.UP
        )

        return (
            block.power_output[modeled_year, dispatch_window, timestamp]
            + reserves
            + self.paired_variable_resource.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            + paired_reserves
            <= self.hybrid_linkage.interconnection_limit_mw.data.at[modeled_year]
        )

    def _hybrid_power_input_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        """The sum of the storage and paired variable resources' input power and reserves may
        not exceed the operational capacity"""

        if not self.hybrid_linkage.paired_charging_constraint_active_in_year.data.at[modeled_year]:
            return pyo.Constraint.Skip

        # If grid charging is allowed, power input cannot exceed paired resource output
        if not self.hybrid_linkage.grid_charging_allowed:
            power_input_limit = 0
        else:
            power_input_limit = self.paired_variable_resource.formulation_block.operational_capacity[modeled_year]

        reserves = sum(
            block.provide_reserve[reserve_name, modeled_year, dispatch_window, timestamp]
            for reserve_name, reserve_link in self.reserves.items()
            if reserve_link.instance_to.direction == ReserveDirection.DOWN
        )

        paired_reserves = sum(
            self.paired_variable_resource.formulation_block.provide_reserve[
                reserve_name, modeled_year, dispatch_window, timestamp
            ]
            for reserve_name, reserve_link in self.paired_variable_resource.reserves.items()
            if reserve_link.instance_to.direction == ReserveDirection.DOWN
        )

        return (
            self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
            + reserves
            - self.paired_variable_resource.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            - paired_reserves
            <= power_input_limit
        )

    def _hybrid_power_input_interconnection_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        """Neither the power_input nor power_output may exceed the interconnection limit"""

        # Check if paired charging constraint is active for this year
        if not self.hybrid_linkage.paired_charging_constraint_active_in_year.data.at[modeled_year]:
            return pyo.Constraint.Skip

        # If grid charging is not allowed, power input cannot exceed paired resource output
        if not self.hybrid_linkage.grid_charging_allowed:
            power_input_limit = 0
        # If grid charging is allowed and there's no interconnection limit, then constraint can be skipped
        elif self.hybrid_linkage.interconnection_limit_mw is None:
            return pyo.Constraint.Skip
        else:
            power_input_limit = self.hybrid_linkage.interconnection_limit_mw.data.at[modeled_year]

        reserves = sum(
            block.provide_reserve[reserve_name, modeled_year, dispatch_window, timestamp]
            for reserve_name, reserve_link in self.reserves.items()
            if reserve_link.instance_to.direction == ReserveDirection.DOWN
        )

        paired_reserves = sum(
            self.paired_variable_resource.formulation_block.provide_reserve[
                reserve_name, modeled_year, dispatch_window, timestamp
            ]
            for reserve_name, reserve_link in self.paired_variable_resource.reserves.items()
            if reserve_link.instance_to.direction == ReserveDirection.DOWN
        )

        return (
            self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
            + reserves
            - self.paired_variable_resource.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            - paired_reserves
            <= power_input_limit
        )

    def _erm_hybrid_power_output_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        """Constrains the hybrid storage's power output to be less than or equal to the interconnection limit."""
        if not self.hybrid_linkage.paired_charging_constraint_active_in_year.data.at[modeled_year]:
            return pyo.Constraint.Skip

        return (
            self.formulation_block.erm_power_output[modeled_year, weather_period, weather_timestamp]
            + self.paired_variable_resource.formulation_block.operational_capacity[modeled_year]
            * self.hybrid_erm_policy_linkage.multiplier.data.at[weather_timestamp]
            <= self.paired_variable_resource.formulation_block.operational_capacity[modeled_year]
        )

    def _erm_hybrid_power_output_interconnection_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        """Constrains the hybrid storage's power output to be less than or equal to the paired variable resource's operational capacity."""
        if not self.hybrid_linkage.paired_charging_constraint_active_in_year.data.at[modeled_year]:
            return pyo.Constraint.Skip
        if self.hybrid_linkage.interconnection_limit_mw is None:
            return pyo.Constraint.Skip

        return (
            self.formulation_block.erm_power_output[modeled_year, weather_period, weather_timestamp]
            + self.paired_variable_resource.formulation_block.operational_capacity[modeled_year]
            * self.hybrid_erm_policy_linkage.multiplier.data.at[weather_timestamp]
            <= self.hybrid_linkage.interconnection_limit_mw.data.at[modeled_year]
        )

    def _erm_hybrid_power_input_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        """Constrains the hybrid storage's power input to be less than or equal to the paired variable resource's
        power output plus its operational capacity times the ERM multiplier.
        """
        if not self.hybrid_linkage.paired_charging_constraint_active_in_year.data.at[modeled_year]:

            return pyo.Constraint.Skip

        # If grid charging is allowed, power input cannot exceed paired resource output
        if not self.hybrid_linkage.grid_charging_allowed:
            power_input_limit = 0
        else:
            power_input_limit = self.paired_variable_resource.formulation_block.operational_capacity[modeled_year]

        return (
            self.formulation_block.erm_power_input[modeled_year, weather_period, weather_timestamp]
            - self.paired_variable_resource.formulation_block.operational_capacity[modeled_year]
            * self.hybrid_erm_policy_linkage.multiplier.data.at[weather_timestamp]
            <= power_input_limit
        )

    def _erm_hybrid_power_input_interconnection_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        """Constrains the hybrid storage's power input to be less than or equal to the interconnection limit."""
        if not self.hybrid_linkage.paired_charging_constraint_active_in_year.data.at[modeled_year]:
            return pyo.Constraint.Skip

        # If grid charging is not allowed, power input cannot exceed paired resource output
        if not self.hybrid_linkage.grid_charging_allowed:
            power_input_limit = 0
        # If grid charging is allowed and there's no interconnection limit, then constraint can be skipped
        elif self.hybrid_linkage.interconnection_limit_mw is None:
            return pyo.Constraint.Skip
        else:
            power_input_limit = self.hybrid_linkage.interconnection_limit_mw.data.at[modeled_year]

        return (
            self.formulation_block.erm_power_input[modeled_year, weather_period, weather_timestamp]
            - self.paired_variable_resource.formulation_block.operational_capacity[modeled_year]
            * self.hybrid_erm_policy_linkage.multiplier.data.at[weather_timestamp]
            <= power_input_limit
        )

    def _hybrid_pairing_ratio_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """If user defines pairing_ratio on the hybrid_linkage, force operational capacities of
        storage and paired variable resources to be fixed ratio."""
        return (
            self.paired_variable_resource.formulation_block.operational_capacity[modeled_year]
        ) == self.hybrid_linkage.pairing_ratio * self.formulation_block.operational_capacity[modeled_year]


class HybridVariableResourceGroup(VariableResourceGroup, HybridVariableResource):
    SAVE_PATH: ClassVar[str] = "resources/hybrid_variable/groups"
    _NAME_PREFIX: ClassVar[str] = "hybrid_variable_resource_group"
    _GROUPING_CLASS = HybridVariableResource


class HybridSolarResourceGroup(HybridVariableResourceGroup, SolarResourceGroup, HybridSolarResource):
    SAVE_PATH: ClassVar[str] = "resources/hybrid_solar/groups"
    _NAME_PREFIX: ClassVar[str] = "hybrid_solar_resource_group"
    _GROUPING_CLASS = HybridSolarResource


class HybridWindResourceGroup(HybridVariableResourceGroup, WindResourceGroup, HybridWindResource):
    SAVE_PATH: ClassVar[str] = "resources/hybrid_wind/groups"
    _NAME_PREFIX: ClassVar[str] = "hybrid_wind_resource_group"
    _GROUPING_CLASS = HybridWindResource


class HybridStorageResourceGroup(StorageResourceGroup, HybridStorageResource):
    SAVE_PATH: ClassVar[str] = "resources/hybrid_storage/groups"
    _NAME_PREFIX: ClassVar[str] = "hybrid_storage_resource_group"
    _GROUPING_CLASS = HybridStorageResource

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)

        # investment rules specific to HybridStorageResource must be re-defined here because method resolution order
        # dictates that investment rules will inherit from StorageResourceGroup
        if self.hybrid_linkage.pairing_ratio is not None:
            pyomo_components.update(
                hybrid_pairing_ratio_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    rule=self._hybrid_pairing_ratio_constraint,
                )
            )

        if self.erm_policies:
            pyomo_components.update(
                erm_hybrid_power_output_interconnection_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_hybrid_power_output_interconnection_constraint,
                ),
                erm_hybrid_power_output_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_hybrid_power_output_constraint,
                ),
                erm_hybrid_power_input_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_hybrid_power_input_constraint,
                ),
                erm_hybrid_power_input_interconnection_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_hybrid_power_input_interconnection_constraint,
                ),
            )

        return pyomo_components
