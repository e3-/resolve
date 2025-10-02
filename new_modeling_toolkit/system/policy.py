import enum
from typing import Annotated
from typing import ClassVar
from typing import Literal
from typing import Optional

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pydantic import Field
from pydantic import model_validator

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.model import ConstraintOperator
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.three_way_linkage import CustomConstraintLinkage
from new_modeling_toolkit.system import GenericResourceGroup
from new_modeling_toolkit.system.electric.resources.shed_dr import ShedDrResource
from new_modeling_toolkit.system.electric.resources.storage import StorageResource


@enum.unique
class TargetBasis(enum.Enum):
    SALES = "sales"
    SYSTEM_LOAD = "system load"
    HOURS = "hours"


@enum.unique
class TargetUnits(enum.Enum):
    RELATIVE = "relative"
    ABSOLUTE = "absolute"


class Policy(component.Component):
    """Parent class for specific types of policy sub-classes.

    This is a pseudo-abstract base class.
    """

    SAVE_PATH: ClassVar[str] = "policies"

    @property
    def results_reporting_category(self):
        return "Policy"

    @property
    def results_reporting_folder(self):
        return f"{self.results_reporting_category}/{self.__class__.__name__}"

    @property
    def annual_results_column_order(self):
        """This property defines the ordering of columns in the component's annual results summary out of Resolve.
        The name of the model field or formulation_block pyomo component can be used.
        """
        return [
            "NQC_lhs",
            "ELCC_lhs",
            "target",
            "target_adjustment",
            "policy_lhs",  # Achieved
            "policy_shadow_price",
            "policy_slack_up",
            "policy_slack_down",
            "annual_total_investment_cost",
            "annual_total_operational_cost",
            "policy_slack_cost",
            "policy_cost_without_slack",
            "annual_total_slack_investment_cost",
            "annual_total_slack_operational_cost",
        ]

    ######################
    # MAPPING ATTRIBUTES #
    ######################
    # The parent Policy class has no defined linkages

    ####################
    # ATTRIBUTES       #
    ####################
    constraint_operator: ConstraintOperator
    loads: Annotated[dict[str, linkage.AllToPolicy], Metadata(linkage_order="from")] = {}
    custom_constraints: Annotated[
        dict[str, CustomConstraintLinkage], Metadata(linkage_order=3, default_exclude=True)
    ] = {}
    slack_penalty: float = Field(default=1_000_000, description=("Cost to model of relaxing policy ($) "))
    type: Literal["emissions", "energy", "prm", "erm"] = Field(
        description=("Type of policy. Can be related to energy, emissions, prm, erm")
    )

    target: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="sum", title="Annual Target (Units)"
    )
    # TODO 2023-06-02: Funky that this is None or the ts

    target_basis: TargetBasis = Field(
        description=(
            "Basis of the target. Can be 'sales' or 'system demand'. Sales-based policies, like California's RPS, "
            "are based on the sales (before T&D losses). "
            "System-based policies consider total system load (i.e., sales * T&D losses)."
        )
    )
    target_units: TargetUnits = Field(
        description=(
            "Units of the target. Can be percentage or absolute. For example, policy targets for an GHG policy are"
            "likely absolute while an RPS policy is a percentage of sales."
        )
    )
    target_adjustment: Optional[ts.NumericTimeseries] = Field(
        default_factory=ts.NumericTimeseries.zero,
        default_freq="YS",
        up_method="interpolate",
        down_method="sum",
        description=(
            "Adjustment to the target. A **positive** adjustment would add the target, while a **negative** adjustment "
            "would be subtracted from the target."
        ),
        title="Annual Target Adjustment (Units)",
    )
    price: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", up_method="interpolate", down_method="sum")

    # Price and target cannot both be defined
    @model_validator(mode="after")
    def price_or_target(self):
        if self.price is not None and self.target is not None:
            raise ValueError(
                f"Check {self.name}: for a given policy, either a price or a target can be defined (but not both)."
            )

        return self

    def update_targets_from_loads(self):
        """Update policy targets if loads are linked to policies"""
        # TODO 2023-05-18: This could be simplified if we didn't pre-multiply the load component by "T&D losses"
        #  and did that at a later step
        if self.loads and self.target_units == TargetUnits.RELATIVE:
            # only do this if we've linked to loads to policies and want to recalc
            for year in self.target.data.index:
                total_load = pd.concat(
                    [
                        link.instance_from.model_year_profiles[year.year].data
                        * (link.multiplier.data.loc[year] if link.multiplier else 1.0)
                        / (
                            link.instance_from.td_losses_adjustment.data.loc[year]
                            if self.target_basis == TargetBasis.SALES
                            else 1
                        )  # put back into sales if needed
                        for link in self.loads.values()
                    ],
                    axis=1,
                ).sum(axis=1)

                total_load = total_load.multiply(self.target.data.loc[year])

                if self.type.lower() == "prm":  # find median peak
                    self.target._data_dict = None
                    self.target.data.loc[year] = total_load.groupby(total_load.index.year).max().median()
                elif self.type.lower() == "energy":  # find annual energy
                    self.target._data_dict = None
                    self.target.data.loc[year] = total_load.groupby(total_load.index.year).sum().mean()

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        pyomo_components.update(
            policy_slack_up=pyo.Var(model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="Policy Slack Up (Units)"),
            policy_slack_down=pyo.Var(
                model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="Policy Slack Down (Units)"
            ),
            policy_slack_cost=pyo.Expression(
                model.MODELED_YEARS, rule=self._policy_slack_cost, doc="Policy Slack Cost ($)"
            ),
            policy_lhs=pyo.Expression(model.MODELED_YEARS, rule=self._policy_lhs, doc="Achieved (Units)"),
            policy_constraint=pyo.Constraint(model.MODELED_YEARS, rule=self._policy_constraint),
        )

        if construct_costs:
            pyomo_components.update(
                annual_total_slack_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_slack_operational_cost,
                    doc="Annual Total Slack Operational Cost ($)",
                ),
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._total_policy_cost_in_modeled_year,
                    doc="Annual Total Operational Cost ($)",
                ),
            )

        return pyomo_components

    def _construct_output_expressions(self, construct_costs: bool):
        self.formulation_block.policy_shadow_price = pyo.Expression(
            self.formulation_block.model().MODELED_YEARS,
            rule=self._policy_constraint_dual,
            doc="Unweighted Dual Value ($/Unit)",
        )

    def _policy_constraint_dual(self, block: pyo.Block, modeled_year: pd.Timestamp):
        if modeled_year not in block.policy_constraint:
            return None
        policy_constraint_dual = block.policy_constraint[modeled_year].get_suffix_value("dual", default=np.nan)
        annual_discount_factor = block.model().temporal_settings.modeled_year_discount_factors.data.at[modeled_year]

        return policy_constraint_dual / annual_discount_factor

    def _total_policy_cost_in_modeled_year(self, block, modeled_year):
        if self.price is None:
            return self.formulation_block.policy_slack_cost[modeled_year]
        return (
            self.price.data.at[modeled_year] * self.formulation_block.policy_lhs[modeled_year]
            + self.formulation_block.policy_slack_cost[modeled_year]
        )

    def _policy_slack_cost(self, block, modeled_year):
        return self.slack_penalty * (
            self.formulation_block.policy_slack_up[modeled_year]
            + self.formulation_block.policy_slack_down[modeled_year]
        )

    def _annual_total_slack_operational_cost(self, block, modeled_year):
        return self.formulation_block.policy_slack_cost[modeled_year]

    def _policy_lhs(self, block, modeled_year):
        raise NotImplementedError

    def _policy_constraint(self, block, modeled_year):
        if self.target is None or np.isnan(self.target.data.at[modeled_year]):
            return pyo.Constraint.Skip

        policy_target_adjusted = self.target.data.at[modeled_year] + self.target_adjustment.data.at[modeled_year]

        # Construct >=, ==, or <= constraints, as defined by user.
        return self.constraint_operator.operator(
            self.formulation_block.policy_lhs[modeled_year]
            - self.formulation_block.policy_slack_up[modeled_year]
            + self.formulation_block.policy_slack_down[modeled_year],
            policy_target_adjusted,
        )

    def _create_component_indexed_policy_results(self, unknown_index_results: list):
        component_indexed_dfs = []
        if self.__class__.__name__ in ["AnnualEnergyStandard", "AnnualEmissionsPolicy", "PlanningReserveMargin"]:
            for df in unknown_index_results:
                # Add additional index columns
                df.loc[:, "Policy Name"] = self.name
                df.loc[:, "Policy Type"] = self.__class__.__name__
                df.loc[:, "Component Type"] = df.apply(
                    lambda row: self.governed_items[row.name[0]].instance_from.__class__.__name__, axis=1
                )
                df.loc[:, "Zone"] = df.apply(
                    lambda row: (
                        list(self.governed_items[row.name[0]].instance_from.zones.keys())[0]
                        if hasattr(self.governed_items[row.name[0]].instance_from, "zones")
                        and len(list(self.governed_items[row.name[0]].instance_from.zones.keys())) == 1
                        else ""
                    ),
                    axis=1,
                )
                component_columns_added = ["Component Type", "Zone"]
                if self.__class__.__name__ == "PlanningReserveMargin":
                    df.loc[:, "Vintage Parent Group"] = df.apply(
                        lambda row: (
                            self.governed_items[row.name[0]].instance_from.vintage_parent_group
                            if hasattr(self.governed_items[row.name[0]].instance_from, "vintage_parent_group")
                            and self.governed_items[row.name[0]].instance_from.vintage_parent_group is not None
                            else ""
                        ),
                        axis=1,
                    )
                    component_columns_added.append("Vintage Parent Group")
                if hasattr(self, "tx_paths") and len(self.tx_paths) > 0:
                    df.loc[:, "From Zone"] = df.apply(
                        lambda row: (
                            self.governed_items[row.name[0]].instance_from.from_zone.instance_from.name
                            if hasattr(self.governed_items[row.name[0]].instance_from, "from_zone")
                            else ""
                        ),
                        axis=1,
                    )
                    component_columns_added.append("From Zone")
                    df.loc[:, "To Zone"] = df.apply(
                        lambda row: (
                            self.governed_items[row.name[0]].instance_from.to_zone.instance_from.name
                            if hasattr(self.governed_items[row.name[0]].instance_from, "to_zone")
                            else ""
                        ),
                        axis=1,
                    )
                    component_columns_added.append("To Zone")
                component_index_header, modeled_year_header = df.index.names
                df.reset_index(inplace=True)
                df.set_index(
                    ["Policy Name", "Policy Type", component_index_header]
                    + component_columns_added
                    + [modeled_year_header],
                    inplace=True,
                )
                df.rename_axis(
                    index=["Policy Name", "Policy Type", "Asset"] + component_columns_added + ["Modeled Year"],
                    inplace=True,
                )

                component_indexed_dfs.append(df)
        else:
            logger.warning(f"{self.__class__.__name__} results are not reported by asset in a single report.")
            return None
        df_concat = pd.concat(component_indexed_dfs, axis=1)
        df_concat = df_concat.loc[:, ~df_concat.columns.duplicated()]
        return df_concat


class AnnualEnergyStandard(Policy):
    """Policy class for Renewable Portfolio Standard (RPS) or Clean Energy Standard (CES) type policies."""

    ######################
    # MAPPING ATTRIBUTES #
    ######################
    loads: dict[str, linkage.AnnualEnergyStandardContribution] = {}
    resources: dict[str, linkage.AnnualEnergyStandardContribution] = {}
    candidate_fuels: dict[str, linkage.AnnualEnergyStandardContribution] = {}
    target_basis: None | TargetBasis = None
    target_units: TargetUnits = TargetUnits.ABSOLUTE
    type: str = "energy"
    constraint_operator: ConstraintOperator = ConstraintOperator.GREATER_THAN_OR_EQUAL_TO

    @property
    def governed_items(self):
        return self.resources

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict()

        RPS_RESOURCES = pyo.Set(initialize=self.resources.keys())
        pyomo_components.update(RPS_RESOURCES=RPS_RESOURCES)

        pyomo_components.update(
            energy_policy_annual_contribution_by_resource=pyo.Expression(
                RPS_RESOURCES,
                model.MODELED_YEARS,
                rule=self._energy_policy_annual_contribution_by_resource,
                doc="Annual Policy Contribution (MWh)",
            )
        )

        """
        The policy constraint is constructed in the parent Policy class. Accordingly,
        super()._construct_operational_rules is called at the end of the child function to allow RPS-specific
        attributes to be accessed from the parent class.
        """
        pyomo_components.update(super()._construct_operational_rules(model, construct_costs=construct_costs))

        return pyomo_components

    def _energy_policy_annual_contribution_by_resource(self, block, resource, modeled_year):
        resource_instance = self.resources[resource].instance_from
        # Contributions from thermal resources (e.g., burning renewable biomass)
        if (
            hasattr(resource_instance.formulation_block, "annual_power_output_by_fuel")
            and len(set(resource_instance.candidate_fuels.keys()).intersection(set(self.candidate_fuels.keys()))) > 0
        ):
            thermal_contributions = 0
            for candidate_fuel in set(resource_instance.candidate_fuels.keys()).intersection(
                set(self.candidate_fuels.keys())
            ):
                thermal_contributions += self.resources[resource].multiplier.data.at[modeled_year] * (
                    resource_instance.formulation_block.annual_power_output_by_fuel[candidate_fuel, modeled_year]
                )
            return thermal_contributions
        # Contributions from other resources (e.g., solar, wind)
        elif hasattr(resource_instance.formulation_block, "power_output_annual"):
            return self.resources[resource].multiplier.data.at[modeled_year] * (
                resource_instance.formulation_block.power_output_annual[modeled_year]
            )
        # No operational rules
        else:
            return 0

    def _policy_lhs(self, block, modeled_year):
        return sum(
            self.formulation_block.energy_policy_annual_contribution_by_resource[resource, modeled_year]
            for resource in self.resources.keys()
        )


class HourlyEnergyStandard(Policy):
    """Ideally this would be merged with `AnnualEnergyStandard`, but to preserve backward compatibility for now, keeping separate."""

    # TODO: Fix this default slack_penalty
    slack_penalty: ts.NumericTimeseries = Field(
        default_factory=ts.Timeseries.one,
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
    )

    ######################
    # MAPPING ATTRIBUTES #
    ###############K#######
    resources: dict[str, linkage.HourlyEnergyStandardContribution] = {}
    candidate_fuels: dict[str, linkage.HourlyEnergyStandardContribution] = {}
    type: str = "energy"
    constraint_operator: ConstraintOperator = ConstraintOperator.GREATER_THAN_OR_EQUAL_TO
    _target_by_modeled_year: dict[int, ts.NumericTimeseries] = {}

    ############################
    # Optimization Constraints #
    ############################

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict()
        policy_resources = pyo.Set(initialize=self.resources.keys())
        pyomo_components.update(
            policy_slack=pyo.Var(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, within=pyo.NonNegativeReals, doc="Slack"
            ),
            policy_resources=policy_resources,
            target=pyo.Expression(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._target, doc="Target w Adjustment"
            ),
            resource_contribution=pyo.Expression(
                policy_resources,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._resource_contribution,
                doc="Hourly Policy Contribution (MWh)",
            ),
            policy_lhs=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._policy_lhs,
                doc="Achieved (Units)",
            ),
            policy_constraint=pyo.Constraint(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._policy_constraint
            ),
            policy_slack_cost=pyo.Expression(
                model.MODELED_YEARS, rule=self._policy_slack_cost, doc="Policy Slack Cost ($)"
            ),
        )

        if construct_costs:
            pyomo_components.update(
                annual_total_slack_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_slack_operational_cost,
                    doc="Annual Total Slack Operational Cost ($)",
                ),
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._total_policy_cost_in_modeled_year,
                    doc="Annual Total Operational Cost ($)",
                ),
            )

        return pyomo_components

    def _policy_lhs(self, block, modeled_year, dispatch_window, timestamp):
        return sum(
            self.formulation_block.resource_contribution[resource, modeled_year, dispatch_window, timestamp]
            for resource in self.formulation_block.policy_resources
        )

    def _policy_constraint(self, block, modeled_year, dispatch_window, timestamp):

        if self.target is None:
            return pyo.Constraint.Skip

        policy_target_adjusted = self.formulation_block.target[modeled_year, dispatch_window, timestamp]

        # Construct >= constraints
        if self.constraint_operator == ConstraintOperator.GREATER_THAN_OR_EQUAL_TO:
            return (
                self.formulation_block.policy_lhs[modeled_year, dispatch_window, timestamp]
                + self.formulation_block.policy_slack[modeled_year, dispatch_window, timestamp]
                >= policy_target_adjusted
            )
        else:
            raise ValueError(f"Policy operator {self.constraint_operator}")

    def _policy_slack_cost(self, block, modeled_year):
        slack_cost = self.slack_penalty.data.at[
            modeled_year
        ] * self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.policy_slack[modeled_year, :, :]
        )
        return slack_cost

    def _construct_output_expressions(self, construct_costs: bool):
        self.formulation_block.policy_shadow_price = pyo.Expression(
            self.formulation_block.model().MODELED_YEARS,
            self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS,
            rule=self._policy_constraint_dual,
            doc="Unweighted Dual Value ($/Unit)",
        )

    def _policy_constraint_dual(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        policy_constraint_dual = self.formulation_block.policy_constraint[
            modeled_year, dispatch_window, timestamp
        ].get_suffix_value("dual", default=np.nan)
        annual_discount_factor = block.model().temporal_settings.modeled_year_discount_factors.data.at[modeled_year]
        dispatch_window_weight = block.model().temporal_settings.dispatch_window_weights.at[dispatch_window]
        num_days_per_year = block.model().num_days_per_modeled_year[modeled_year]
        timestamp_duration = block.model().timestamp_durations_hours[dispatch_window, timestamp]

        return (
            policy_constraint_dual
            / annual_discount_factor
            / dispatch_window_weight
            / num_days_per_year
            / timestamp_duration
        )

    def _resource_contribution(self, block, resource, modeled_year, dispatch_window, timestamp):
        return self.resources[resource].multiplier.data.at[modeled_year] * (
            self.resources[resource].instance_from.formulation_block.power_output[
                modeled_year, dispatch_window, timestamp
            ]
            if hasattr(self.resources[resource].instance_from.formulation_block, "power_output")
            else 0
        )

    def _target(self, block, modeled_year, dispatch_window, timestamp):
        return (
            self._target_by_modeled_year[modeled_year.year].data.at[timestamp]
            + self.target_adjustment.data.at[modeled_year]
        )

    def _annual_total_slack_operational_cost(self, block, modeled_year):
        return self.formulation_block.policy_slack_cost[modeled_year]

    def _total_policy_cost_in_modeled_year(self, block, modeled_year):
        return self.formulation_block.policy_slack_cost[modeled_year]

    def check_constraint_violations(self, model: pyo.ConcreteModel):
        if (
            pyo.value(sum(model.blocks[self.name].policy_slack[idx] for idx in model.blocks[self.name].policy_slack))
            > 0
        ):
            logger.warning(f"Constraint violation (non-zero slack) for {self.name}")

    def update_targets_from_loads(self):
        if self.loads and self.target_units == TargetUnits.RELATIVE:
            for year in self.target.data.index:
                total_load = pd.concat(
                    [
                        link.instance_from.model_year_profiles[year.year].data
                        * link.multiplier.data.loc[year]
                        / (
                            link.instance_from.td_losses_adjustment.data.loc[year]
                            if self.target_basis == TargetBasis.SALES
                            else 1
                        )  # put back into sales if needed
                        for link in self.loads.values()
                    ],
                    axis=1,
                ).sum(axis=1)

                self._target_by_modeled_year[year.year] = ts.NumericTimeseries(
                    name=f"Scaled {self.name} hourly energy policy target",
                    data=self.target.slice_by_year(year.year) * total_load,
                    weather_year=True,
                )
        elif self.loads:
            raise NotImplementedError(
                f"update_targets_from_loads not implemented for `{self.__class__.__name__}` without loads and relative target units."
            )


class EnergyReserveMargin(Policy):
    """Policy class for Energy Reserve Margin (ERM) type policies."""

    ######################
    # MAPPING ATTRIBUTES #
    ######################
    resources: dict[str, linkage.ERMContribution] = {}
    tx_paths: dict[str, linkage.ERMContribution] = {}
    assets_: dict[str, linkage.ERMContribution] = {}

    ##############
    # ATTRIBUTES #
    ##############
    type: str = "erm"
    _target_adjusted_by_modeled_year: dict[int, ts.NumericTimeseries] = {}
    target: ts.NumericTimeseries = Field(
        None,
        default_freq="H",
        up_method="ffill",
        down_method="mean",
    )
    target_adjustment: Optional[ts.NumericTimeseries] = Field(
        default_factory=ts.NumericTimeseries.zero,
        default_freq="H",
        up_method="ffill",
        down_method="mean",
    )
    target_basis: None | TargetBasis = None
    target_units: TargetUnits = TargetUnits.ABSOLUTE
    constraint_operator: ConstraintOperator = ConstraintOperator.GREATER_THAN_OR_EQUAL_TO
    allow_inter_period_sharing: bool = True  # TODO: description

    @property
    def assets(self):
        return self.resources | self.tx_paths | self.assets_

    @property
    def governed_items(self):
        return self.assets

    @property
    def storage_resources(self):
        # Includes StorageResource and StorageResourceGroup instances
        return {k: v for k, v in self.resources.items() if isinstance(v.instance_from, StorageResource)}

    @property
    def shed_dr_resources(self):
        return {k: v for k, v in self.resources.items() if isinstance(v.instance_from, ShedDrResource)}

    @property
    def other_resources(self):
        # Includes all other Resource instances and ResourceGroup instances
        return {
            k: v
            for k, v in self.resources.items()
            if k not in self.storage_resources and k not in self.shed_dr_resources
        }

    @property
    def resource_groups(self):
        # Includes StorageResourceGroup and ShedDrResourceGroup instances
        return {k: v for k, v in self.resources.items() if isinstance(v.instance_from, GenericResourceGroup)}

    @property
    def resource_instances(self):
        return {k: v for k, v in self.resources.items() if k not in self.resource_groups}

    def revalidate(self):
        # Validate that no resources are linked as both a Resource instance and in a ResourceGroup.
        repeated_resources = []
        for resource_group_linkage in self.resource_groups.values():
            resource_group = resource_group_linkage.instance_from
            intersection = set(resource_group.build_assets.keys()) & set(self.resource_instances.keys())
            if intersection and resource_group.aggregate_operations:
                # Remove underlying asset linkages
                for resource in intersection:
                    del self.resources[resource].instance_from.erm_policies[self.name]
                    del self.resources[resource]
                    # TODO: delete from system.linkages as well?
            elif intersection:
                repeated_resources.append(intersection)

        if repeated_resources:
            repeated_resources_str = "\n" + "\n".join(map(str, repeated_resources))
            raise ValueError(
                f"`{self.__class__.__name__}` instance `{self.name}` is linked to resource instances that are also in "
                f"its linked resource groups: {repeated_resources_str}"
            )

        for resource_group_linkage in self.resource_groups.values():
            resource_group = resource_group_linkage.instance_from
            resources_are_storage = [
                isinstance(resource, StorageResource) for resource in resource_group.build_assets.values()
            ]
            if any(resources_are_storage) and not all(resources_are_storage):
                raise ValueError(
                    f"The resource group {resource_group} is linked to an ERM policy and contains some storage and "
                    f"some non-storage resources. This is not allowed."
                )

        if not self.constraint_operator == ConstraintOperator.GREATER_THAN_OR_EQUAL_TO:
            raise ValueError(
                f"Policy operator for `{self.__class__.__name__}` `{self.name}` should be set to greater than or equal to."
            )

        if self.target_units == TargetUnits.RELATIVE:
            raise NotImplementedError(
                f"`{self.__class__.__name__}` not implemented for `{self.name}` with relative target units.'"
            )

        # Target should be set, not price
        if self.price is not None:
            raise ValueError(f"For `{self.__class__.__name__}` `{self.name}`, a target should be defined, not a price.")

    ############################
    # Optimization Constraints #
    ############################

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:

        pyomo_components = LastUpdatedOrderedDict()
        storage_resources = pyo.Set(initialize=self.storage_resources.keys())
        other_resources = pyo.Set(initialize=self.other_resources.keys())
        shed_dr_resources = pyo.Set(initialize=self.shed_dr_resources.keys())
        tx_paths = pyo.Set(initialize=self.tx_paths.keys())
        generic_assets = pyo.Set(initialize=self.assets_.keys())
        pyomo_components.update(
            policy_slack=pyo.Var(
                model.MODELED_YEARS,
                model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                doc="Slack (MW)",
            ),
            storage_resource_contribution=pyo.Expression(
                storage_resources,
                model.MODELED_YEARS,
                model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                rule=self._storage_resource_contribution,
                doc="Hourly Storage Contribution (MW)",
            ),
            shed_dr_resource_contribution=pyo.Expression(
                shed_dr_resources,
                model.MODELED_YEARS,
                model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                rule=self._shed_dr_resource_contribution,
                doc="Hourly Shed DR Contribution (MW)",
            ),
            other_resource_contribution=pyo.Expression(
                other_resources,
                model.MODELED_YEARS,
                model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                rule=self._other_resource_contribution,
                doc="Hourly Contribution from other resources (MW)",
            ),
            tx_path_contribution=pyo.Expression(
                tx_paths,
                model.MODELED_YEARS,
                model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                rule=self._tx_path_contribution,
                doc="Hourly Tx Path Contribution (MW)",
            ),
            generic_asset_contribution=pyo.Expression(
                generic_assets,
                model.MODELED_YEARS,
                model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                rule=self._generic_asset_contribution,
                doc="Hourly Generic Asset Contribution (MW)",
            ),
            policy_lhs=pyo.Expression(
                model.MODELED_YEARS,
                model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                rule=self._policy_lhs,
                doc="Achieved (MW)",
            ),
            policy_target_adjusted=pyo.Param(
                model.MODELED_YEARS,
                model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                rule=self._policy_target_adjusted,
                doc="Target (MW)",
            ),
            policy_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                rule=self._policy_constraint,
            ),
        )

        if construct_costs:
            pyomo_components.update(
                policy_slack_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._policy_slack_cost,
                    doc="Policy Slack Cost ($)",
                ),
                annual_total_investment_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._total_policy_cost_in_modeled_year,
                    doc="Annual Total Investment Cost ($)",
                ),
                annual_total_slack_investment_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._policy_slack_cost,
                    doc="Annual Total Slack Investment Cost ($)",
                ),
            )
        return pyomo_components

    def _construct_operational_rules(self, model: "ModelTemplate", construct_costs: bool):
        """Operational rules which are defined in Policy class are moved to investment rules in the ERM class because
        an ERM policy and its costs are part of an investment decision."""
        pyomo_components = LastUpdatedOrderedDict()
        if construct_costs:
            pyomo_components.update(annual_total_operational_cost=pyo.Expression(model.MODELED_YEARS, rule=0))

        return pyomo_components

    def _construct_output_expressions(self, construct_costs: bool):
        model = self.formulation_block.model()
        self.formulation_block.policy_shadow_price = pyo.Expression(
            model.MODELED_YEARS,
            model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
            rule=self._policy_constraint_dual,
            doc="Unweighted Dual Value ($/Unit)",
        )

    def _policy_constraint_dual(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        policy_constraint_dual = block.policy_constraint[
            modeled_year, weather_period, weather_timestamp
        ].get_suffix_value("dual", default=np.nan)
        return policy_constraint_dual

    def _storage_resource_contribution(
        self,
        block,
        storage_resource_name: str,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        storage_linkage = self.storage_resources[storage_resource_name]
        storage = storage_linkage.instance_from

        available_capacity = (
            storage_linkage.multiplier.data.at[weather_timestamp]
            * storage.formulation_block.erm_net_power_output[modeled_year, weather_period, weather_timestamp]
        )
        return available_capacity

    def _shed_dr_resource_contribution(
        self,
        block,
        shed_dr_resource_name: str,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        shed_dr_linkage = self.shed_dr_resources[shed_dr_resource_name]
        shed_dr = shed_dr_linkage.instance_from

        available_capacity = (
            shed_dr_linkage.multiplier.data.at[weather_timestamp]
            * shed_dr.formulation_block.erm_power_output[modeled_year, weather_period, weather_timestamp]
        )

        return available_capacity

    def _other_resource_contribution(
        self,
        block,
        resource_name: str,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        resource_linkage = self.other_resources[resource_name]
        resource = resource_linkage.instance_from

        available_capacity = (
            resource_linkage.multiplier.data.at[weather_timestamp]
            * resource.formulation_block.operational_capacity[modeled_year]
        )

        return available_capacity

    def _tx_path_contribution(
        self,
        block: pyo.Block,
        tx_path_name: str,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        tx_path_linkage = self.tx_paths[tx_path_name]
        tx_path = tx_path_linkage.instance_from
        contribution = (
            tx_path_linkage.multiplier.data.at[weather_timestamp]
            * tx_path.formulation_block.operational_capacity[modeled_year]
        )
        return contribution

    def _generic_asset_contribution(
        self,
        block: pyo.Block,
        generic_asset_name: str,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        generic_asset_linkage = self.assets_[generic_asset_name]
        generic_asset = generic_asset_linkage.instance_from
        contribution = (
            generic_asset_linkage.multiplier.data.at[weather_timestamp]
            * generic_asset.formulation_block.operational_capacity[modeled_year]
        )
        return contribution

    def _policy_lhs(
        self, block, modeled_year: pd.Timestamp, weather_period: pd.Timestamp, weather_timestamp: pd.Timestamp
    ):
        total_storage_contribution = sum(
            block.storage_resource_contribution[storage_name, modeled_year, weather_period, weather_timestamp]
            for storage_name in self.storage_resources.keys()
        )
        total_shed_dr_contribution = sum(
            block.shed_dr_resource_contribution[shed_dr_name, modeled_year, weather_period, weather_timestamp]
            for shed_dr_name in self.shed_dr_resources.keys()
        )
        total_other_resource_contribution = sum(
            block.other_resource_contribution[resource_name, modeled_year, weather_period, weather_timestamp]
            for resource_name in self.other_resources.keys()
        )
        total_tx_path_contribution = sum(
            block.tx_path_contribution[tx_path_name, modeled_year, weather_period, weather_timestamp]
            for tx_path_name in self.tx_paths.keys()
        )
        total_generic_asset_contribution = sum(
            block.generic_asset_contribution[asset_name, modeled_year, weather_period, weather_timestamp]
            for asset_name in self.assets_.keys()
        )

        return (
            total_storage_contribution
            + total_shed_dr_contribution
            + total_other_resource_contribution
            + total_tx_path_contribution
            + total_generic_asset_contribution
        )

    def _policy_target_adjusted(
        self, block, modeled_year: pd.Timestamp, weather_period: pd.Timestamp, weather_timestamp: pd.Timestamp
    ):
        if self.target is None:
            return 0
        return self._target_adjusted_by_modeled_year[modeled_year.year].data.at[weather_timestamp]

    def _policy_constraint(
        self, block, modeled_year: pd.Timestamp, weather_period: pd.Timestamp, weather_timestamp: pd.Timestamp
    ):
        if self.target is None or self.target == 0:
            return pyo.Constraint.Skip

        return (
            self.formulation_block.policy_lhs[modeled_year, weather_period, weather_timestamp]
            + self.formulation_block.policy_slack[modeled_year, weather_period, weather_timestamp]
            >= self.formulation_block.policy_target_adjusted[modeled_year, weather_period, weather_timestamp]
        )

    def _policy_slack_cost(self, block, modeled_year):
        # Sum of weather_timestamp-indexed variable is the average value multiplied by number of hours in modeled year
        slack_cost = self.slack_penalty * block.model().sum_weather_timestamp_component_slice_to_annual(
            block.policy_slack[modeled_year, :, :]
        )
        return slack_cost

    def _total_policy_cost_in_modeled_year(self, block, modeled_year):
        return (
            self.formulation_block.policy_slack_cost[modeled_year]
            + sum(
                resource.instance_from.formulation_block.erm_annual_dispatch_cost[modeled_year]
                for resource in self.storage_resources.values()
            )
            + sum(
                resource.instance_from.formulation_block.erm_annual_dispatch_cost[modeled_year]
                for resource in self.shed_dr_resources.values()
            )
        )

    def update_targets_from_loads(self):
        pass

    def update_targets_to_weather_year_index(self, modeled_years: tuple[int, int], weather_years: tuple[int, int]):
        if self.target is not None:
            for year in range(modeled_years[0], modeled_years[1] + 1):
                target_adjusted_by_year = ts.NumericTimeseries(
                    name="Resampled hourly target",
                    data=(
                        self.target.data[self.target.data.index.year == year].add(
                            self.target_adjustment.data[self.target_adjustment.data.index.year == year], fill_value=0
                        )
                    ),
                )
                target_adjusted_by_year.resample_simple_extend_years(weather_years=weather_years)

                self._target_adjusted_by_modeled_year[year] = target_adjusted_by_year


class AnnualEmissionsPolicy(Policy):
    """Policy class for annual system emissions targets.

    Depending on scope of governed items, this could be an electric sector-only or multi-sector emissions target.

    """

    ######################
    # MAPPING ATTRIBUTES #
    ######################
    candidate_fuels: dict[str, linkage.EmissionsContribution] = {}
    final_fuels: dict[str, linkage.EmissionsContribution] = {}
    resources: dict[str, linkage.EmissionsContribution] = {}
    tx_paths: dict[str, linkage.TxEmissionsContribution] = {}
    # non_energy_subsectors: dict[str, linkage.Linkage] = {}
    pollutants: dict[str, linkage.AllToPolicy] = {}
    demands: dict[str, linkage.AllToPolicy] = {}
    negative_emissions_technologies: dict[str, linkage.AllToPolicy] = {}
    plants: dict[str, linkage.AllToPolicy] = {}
    transportations: dict[str, linkage.AllToPolicy] = {}

    @property
    def assets(self):
        return (
            self.resources | self.tx_paths | self.negative_emissions_technologies | self.plants | self.transportations
        )

    @property
    def governed_items(self):
        return (
            self.candidate_fuels
            | self.final_fuels
            | self.resources
            | self.tx_paths
            | self.demands
            | self.negative_emissions_technologies
            | self.plants
            | self.transportations
        )

    ########################
    # Optimization Results #
    ########################
    type: str = "emissions"
    target_basis: TargetBasis = TargetBasis.SYSTEM_LOAD
    target_units: TargetUnits = TargetUnits.ABSOLUTE
    constraint_operator: ConstraintOperator = ConstraintOperator.LESS_THAN_OR_EQUAL_TO
    # TODO 2023-05-20: Could make target relative to some baseline, but currently absolute

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict()

        if self.resources:
            RESOURCES = pyo.Set(initialize=self.resources.keys())
            pyomo_components.update(RESOURCES=RESOURCES)
            pyomo_components.update(
                annual_resource_emissions_in_policy=pyo.Expression(
                    RESOURCES,
                    model.MODELED_YEARS,
                    rule=self._annual_resource_emissions_in_policy,
                    doc="Annual Resource Policy Contribution (tonne)",
                )
            )

        if self.tx_paths:
            TRANSMISSION_LINES = pyo.Set(initialize=self.tx_paths.keys())
            pyomo_components.update(TRANSMISSION_LINES=TRANSMISSION_LINES)
            pyomo_components.update(
                annual_transmission_emissions_in_policy=pyo.Expression(
                    TRANSMISSION_LINES,
                    model.MODELED_YEARS,
                    rule=self._annual_transmission_emissions_in_policy,
                    doc="Annual Transmission Policy Contribution (tonne)",
                )
            )

        if self.negative_emissions_technologies:
            NEGATIVE_EMISSIONS_TECHNOLOGIES = pyo.Set(initialize=self.negative_emissions_technologies.keys())
            pyomo_components.update(NEGATIVE_EMISSIONS_TECHNOLOGIES=NEGATIVE_EMISSIONS_TECHNOLOGIES)
            pyomo_components.update(
                annual_negative_emissions_technology_emissions_in_policy=pyo.Expression(
                    NEGATIVE_EMISSIONS_TECHNOLOGIES,
                    model.MODELED_YEARS,
                    rule=self._annual_negative_emissions_technology_emissions_in_policy,
                    doc="Annual Negative Emissions Technology Policy Contribution (tonne)",
                )
            )

        if self.plants:
            PLANTS = pyo.Set(initialize=self.plants.keys())
            pyomo_components.update(PLANTS=PLANTS)
            pyomo_components.update(
                annual_plant_emissions_in_policy=pyo.Expression(
                    PLANTS,
                    model.MODELED_YEARS,
                    rule=self._annual_plant_emissions_in_policy,
                    doc="Annual Plant Policy Contribution (tonne)",
                )
            )

        if self.demands:
            DEMANDS = pyo.Set(initialize=self.demands.keys())
            pyomo_components.update(DEMANDS=DEMANDS)
            pyomo_components.update(
                annual_demand_emissions_in_policy=pyo.Expression(
                    DEMANDS,
                    model.MODELED_YEARS,
                    rule=self._annual_demand_emissions_in_policy,
                    doc="Annual Demand Policy Contribution (tonne)",
                )
            )

        if self.transportations:
            TRANSPORTATIONS = pyo.Set(initialize=self.transportations.keys())
            pyomo_components.update(TRANSPORTATIONS=TRANSPORTATIONS)
            pyomo_components.update(
                annual_transportation_emissions_in_policy=pyo.Expression(
                    TRANSPORTATIONS,
                    model.MODELED_YEARS,
                    rule=self._annual_transportation_emissions_in_policy,
                    doc="Annual Transportation Policy Contribution (tonne)",
                )
            )

        # call  super()._construct_operational_rules() at end of self._construct_operational_rules(),
        # parent function requires above attributes of formulation_block defined
        pyomo_components.update(super()._construct_operational_rules(model=model, construct_costs=construct_costs))

        return pyomo_components

    def _policy_lhs(
        self,
        block,
        modeled_year: pd.Timestamp,
    ):
        """Calculate emissions from final fuel demands, resources, unspecified transmission imports, plants, demands, transportations."""
        # todo (3/20/24): revisit final_fuel_demand_emissions

        resource_emissions = sum(
            self.formulation_block.annual_resource_emissions_in_policy[resource, modeled_year]
            for resource in self.resources.keys()
        )

        # get import & export emissions
        tx_emissions = sum(
            self.formulation_block.annual_transmission_emissions_in_policy[tx_path, modeled_year]
            for tx_path in self.tx_paths.keys()
        )

        plant_emissions = sum(
            self.formulation_block.annual_plant_emissions_in_policy[plant, modeled_year] for plant in self.plants.keys()
        )

        demand_emissions = sum(
            self.formulation_block.annual_demand_emissions_in_policy[demand, modeled_year]
            for demand in self.demands.keys()
        )

        transportation_emissions = sum(
            self.formulation_block.annual_transportation_emissions_in_policy[transportation, modeled_year]
            for transportation in self.transportations.keys()
        )

        negative_emissions_technology_emissions = sum(
            self.formulation_block.annual_negative_emissions_technology_emissions_in_policy[
                negative_emissions_technology, modeled_year
            ]
            for negative_emissions_technology in self.negative_emissions_technologies.keys()
        )

        lhs = (
            resource_emissions
            + tx_emissions
            + negative_emissions_technology_emissions
            + plant_emissions
            + demand_emissions
            + transportation_emissions
        )

        return lhs

    def _annual_resource_emissions_in_policy(
        self,
        block,
        resource_name: str,
        modeled_year: pd.Timestamp,
    ):
        resource_multiplier = self.resources[resource_name].multiplier
        resource = self.resources[resource_name].instance_from
        if resource_multiplier:
            resource_emissions = resource_multiplier.data.loc[modeled_year] * (
                self.formulation_block.model().sum_timepoint_component_slice_to_annual(
                    resource.formulation_block.power_output[modeled_year, :, :]
                )
                if hasattr(resource.formulation_block, "power_output")
                else 0
            )
        else:
            resource_emissions = sum(
                self.candidate_fuels[candidate_fuel_name].multiplier.data[modeled_year]
                * (
                    block.model().sum_timepoint_component_slice_to_annual(
                        resource.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                            candidate_fuel_name, modeled_year, :, :
                        ]
                    )
                    if hasattr(resource.formulation_block, "resource_fuel_consumption_in_timepoint_mmbtu")
                    and candidate_fuel_name in resource.candidate_fuels.keys()
                    else 0
                )
                for candidate_fuel_name in self.candidate_fuels.keys()
            )

        return resource_emissions

    def _annual_transmission_emissions_in_policy(
        self,
        block,
        tx_path_name: str,
        modeled_year: pd.Timestamp,
    ):
        tx_multiplier = self.tx_paths[tx_path_name].multiplier
        tx_path = self.tx_paths[tx_path_name].instance_from

        if not tx_path.has_operational_rules:
            return 0

        if tx_multiplier:
            tx_forward_rate = tx_multiplier.data.loc[modeled_year]
            tx_reverse_rate = tx_multiplier.data.loc[modeled_year]
        else:
            tx_forward_rate = self.tx_paths[tx_path_name].forward_dir_multiplier.data.loc[modeled_year]
            tx_reverse_rate = self.tx_paths[tx_path_name].reverse_dir_multiplier.data.loc[modeled_year]
        # TODO (2021-12-08): Clean this up. Seems like we should be able to consolidate resource/transmission emissions reporting...

        return (
            self.formulation_block.model().sum_timepoint_component_slice_to_annual(
                tx_path.formulation_block.transmit_power_forward[modeled_year, :, :]
            )
            * tx_forward_rate
            + self.formulation_block.model().sum_timepoint_component_slice_to_annual(
                tx_path.formulation_block.transmit_power_reverse[modeled_year, :, :]
            )
            * tx_reverse_rate
        )

    def _annual_plant_emissions_in_policy(
        self,
        block,
        plant_name: str,
        modeled_year: pd.Timestamp,
    ):
        plant = self.plants[plant_name].instance_from
        return self._annual_plant_or_negative_emissions_technology_emissions(block, plant, modeled_year)

    def _annual_negative_emissions_technology_emissions_in_policy(
        self,
        block,
        net_name: str,
        modeled_year: pd.Timestamp,
    ):
        net = self.negative_emissions_technologies[net_name].instance_from
        return self._annual_plant_or_negative_emissions_technology_emissions(block, net, modeled_year)

    def _annual_plant_or_negative_emissions_technology_emissions(
        self,
        block,
        plant_or_negative_emissions_technology,
        modeled_year,
    ):
        return pyo.quicksum(
            self.formulation_block.model().sum_timepoint_component_slice_to_annual(
                plant_or_negative_emissions_technology.formulation_block.produced_product_release[
                    product.name, modeled_year, :, :
                ]
            )
            * product.GWP
            for product in plant_or_negative_emissions_technology.produced_products.values()
            if product.name in self.pollutants.keys()
        ) - pyo.quicksum(
            self.formulation_block.model().sum_timepoint_component_slice_to_annual(
                plant_or_negative_emissions_technology.formulation_block.consumed_product_capture[
                    product.name, modeled_year, :, :
                ]
            )
            * product.GWP
            for product in plant_or_negative_emissions_technology.consumed_products.values()
            if product.name in self.pollutants.keys()
        )

    def _annual_demand_emissions_in_policy(
        self,
        block,
        demand_name: str,
        modeled_year: pd.Timestamp,
    ):
        demand = self.demands[demand_name].instance_from
        return pyo.quicksum(
            self.formulation_block.model().sum_timepoint_component_slice_to_annual(
                demand.formulation_block.produced_product_release[product.name, modeled_year, :, :]
            )
            * product.GWP
            for product in demand.produced_products.values()
            if product.name in self.pollutants.keys()
        )

    def _annual_transportation_emissions_in_policy(
        self,
        block,
        transportation_name: str,
        modeled_year: pd.Timestamp,
    ):
        # Multiplier based on operating the transportation (already accounts for GWP of all emissions)
        transportation_multiplier = self.transportations[transportation_name].multiplier
        transportation = self.transportations[transportation_name].instance_from

        if transportation_multiplier:
            forward_rate = transportation_multiplier.data.loc[modeled_year]
            reverse_rate = transportation_multiplier.data.loc[modeled_year]
        else:
            forward_rate = self.transportations[transportation_name].forward_dir_multiplier.data.loc[modeled_year]
            reverse_rate = self.transportations[transportation_name].reverse_dir_multiplier.data.loc[modeled_year]

        return pyo.quicksum(
            self.formulation_block.model().sum_timepoint_component_slice_to_annual(
                transportation.formulation_block.transmit_product_forward[
                    product.instance_from.name, modeled_year, :, :
                ]
            )
            * forward_rate
            + self.formulation_block.model().sum_timepoint_component_slice_to_annual(
                transportation.formulation_block.transmit_product_reverse[
                    product.instance_from.name, modeled_year, :, :
                ]
            )
            * reverse_rate
            for product in transportation.products.values()
            # TODO: add terms to account for emissions from upstream or biogenic emissions
            #  e.g., track emissions associated with bio feedstocks or out-of-bounds extraction/processing emissions.
        )

    def revalidate(self):
        """Validate Resource → Candidate Fuel → Emissions Policy criteria are met.

        1. Resource → Policy linkage or Candidate Fuel → Policy linkage must have a multiplier for every resource linked.
        2. Cannot have a multiplier defined on both a Resource → Policy and Candidate Fuel → Policy
        """
        if len(self.assets) == 0:
            logger.warning(
                f"`{self.__class__.__name__}` instance `{self.name}` is not linked to any Assets. If you "
                f"are expecting this Policy to be linked to other Components, please check your linkages.csv and "
                f"linkages/all_to_policies.csv files."
            )

        num_errors = 0

        # 1. Resource → Policy linkage or Candidate Fuel → Policy linkage must have a multiplier for every resource linked.
        candidate_fuels_without_multiplier = {
            name
            for name, fuel in self.candidate_fuels.items()
            if fuel.instance_from.emissions_policies[self.name].multiplier is None
        }

        resources_linked_to_candidate_fuels_without_multiplier = {
            name
            for name, r in self.resources.items()
            if [fuel for fuel in r.instance_from.candidate_fuels.keys() if fuel in candidate_fuels_without_multiplier]
        }

        resources_without_multiplier = {
            name
            for name, r in self.resources.items()
            if r.instance_from.emissions_policies[self.name].multiplier is None
        }

        invalid_resources = resources_without_multiplier & resources_linked_to_candidate_fuels_without_multiplier

        if invalid_resources:
            num_errors += len(invalid_resources)
            logger.exception(
                f"For policy {self.name}, the following resources do not have a defined emissions rate (either "
                "as a per-MWh multiplier or as a per-MMBtu multiplier on a linked candidate fuel):"
                f"\n{invalid_resources}"
            )

        # 2. Cannot have a multiplier defined on both a Resource → Policy and Candidate Fuel → Policy
        candidate_fuels_with_multiplier = {
            name
            for name, fuel in self.candidate_fuels.items()
            if fuel.instance_from.emissions_policies[self.name].multiplier is not None
        }

        resources_linked_to_candidate_fuels_with_multiplier = {
            name
            for name, r in self.resources.items()
            if [fuel for fuel in r.instance_from.candidate_fuels.keys() if fuel in candidate_fuels_with_multiplier]
        }

        resources_with_multiplier = {
            name
            for name, r in self.resources.items()
            if r.instance_from.emissions_policies[self.name].multiplier is not None
        }

        invalid_resources = resources_with_multiplier & resources_linked_to_candidate_fuels_with_multiplier

        if invalid_resources:
            logger.info(
                f"For policy {self.name}, the following resources have both a per-MWh and per-MMBtu (on a linked candidate fuel) "
                "emissions multiplier defined. The per-MWh multiplier will take precendence:"
                f"\n{invalid_resources}"
            )

        if num_errors > 0:
            raise ValueError(
                f"{num_errors} issues with Resource → Candidate Fuel → Emissions Policy linkages. See log messages above."
            )


class PlanningReserveMargin(Policy):
    """Policy class for Planning Reserve Margin (PRM) type policies.

    Assets can be assigned Effective Load Carrying Capability (ELCC) linkages or Net Qualifying Capacity (NQC)
    attributes to contribute toward PRM polices.

    """

    ######################
    # MAPPING ATTRIBUTES #
    ######################
    assets_: dict[str, linkage.ReliabilityContribution] = {}
    elcc_surfaces: dict[str, linkage.ELCCReliabilityContribution] = {}
    resources: dict[str, linkage.ReliabilityContribution] = {}
    tx_paths: dict[str, linkage.ReliabilityContribution] = {}
    caiso_tx_constraints: dict[str, linkage.ReliabilityContribution] = {}
    plants: dict[str, linkage.ReliabilityContribution] = {}

    @property
    def assets(self):
        return self.resources | self.tx_paths | self.assets_ | self.plants

    @property
    def governed_items(self):
        return self.assets

    ####################
    # ATTRIBUTES       #
    ####################
    type: str = "prm"
    target_basis: TargetBasis = TargetBasis.SYSTEM_LOAD
    constraint_operator: ConstraintOperator = ConstraintOperator.GREATER_THAN_OR_EQUAL_TO

    reliability_event_length: ts.NumericTimeseries = Field(
        default_factory=lambda: ts.NumericTimeseries(
            name="reliability_event_length",
            data=pd.Series(4, index=pd.date_range(start="1/1/2000", end="1/1/2100", freq="YS")),
        ),
        default_freq="YS",
        up_method="interpolate",
        down_method="sum",
    )

    def revalidate(self):
        """Validate Asset → ELCC → PRM linkage criteria are met.

        1. Check that every asset linked to the reliability policy has at least an NQC or ELCC assigned
        2. There cannot be more than one ELCC surface for an asset-policy pair
        3. There cannot be both an ELCC and NQC for the same asset
        """
        if len(self.assets) == 0:
            logger.warning(
                f"`{self.__class__.__name__}` instance `{self.name}` is not linked to any Assets. If you "
                f"are expecting this Policy to be linked to other Components, please check your linkages.csv and "
                f"linkages/all_to_policies.csv files."
            )

        num_errors = 0
        # 1. Check that every resource linked to the reliability policy has at least an NQC or ELCC assigned
        assets_without_elcc_linked_to_policy = {
            name
            for name, r in self.assets.items()
            if not [e for e in r.instance_from.elcc_surfaces.values() if self.name in e.instance_to.prm_policies]
        }
        assets_without_nqc = {
            name for name, r in self.assets.items() if r.instance_from.prm_policies[self.name].multiplier is None
        }
        assets_without_caiso_tx_constraint_linked_to_policy = {
            name
            for name, r in self.assets.items()
            if not [e for e in r.instance_from.caiso_tx_constraints.values() if self.name in e.instance_to.prm_policies]
        }

        assets_without_elcc_or_nqc_or_caiso_tx = (
            assets_without_elcc_linked_to_policy
            & assets_without_nqc
            & assets_without_caiso_tx_constraint_linked_to_policy
        )

        if assets_without_elcc_or_nqc_or_caiso_tx:
            num_errors += len(assets_without_elcc_or_nqc_or_caiso_tx)
            logger.exception(
                f"For policy {self.name}, the following assets do not have an ELCC surface or NQC or TxConstraint assigned:\n{assets_without_elcc_or_nqc_or_caiso_tx}"
            )

        if self.elcc_surfaces:
            # Get set of ELCCs assigned to reliability policy
            policy_elccs = set(self.elcc_surfaces.keys())

            # 2. There cannot be more than one ELCC surface for an asset-policy pair
            assets_with_multiple_elccs = {}
            for r in self.assets.values():
                if r.instance_from.elcc_surfaces:
                    # Get set of ELCCs assigned to resource
                    assets_elccs = set(r.instance_from.elcc_surfaces.keys())
                    # Check set intersection
                    elcc_intersection = assets_elccs.intersection(policy_elccs)
                    if len(elcc_intersection) > 1:
                        assets_with_multiple_elccs[r.instance_from.name] = elcc_intersection

            if assets_with_multiple_elccs:
                num_errors += len(assets_with_multiple_elccs)
                logger.exception(
                    f"For policy {self.name}, the following resources have multiple ELCC surfaces assigned:\n{assets_with_multiple_elccs}"
                    f"\nFor a given reliability policy, resources may only contribute once."
                )

            # 3. There cannot be both an ELCC and NQC for the same asset
            assets_with_both_elcc_nqc = [
                r.instance_from.name
                for r in self.assets.values()
                if r.instance_from.elcc_surfaces
                and set(r.instance_from.elcc_surfaces.keys()).intersection(policy_elccs)
                and r.multiplier is not None
            ]

            if assets_with_both_elcc_nqc:
                num_errors += len(assets_with_both_elcc_nqc)
                logger.exception(
                    f"For policy {self.name}, the following resources have both ELCC and NQC assigned:\n{assets_with_both_elcc_nqc}"
                    f"\nTo assign a derate to ELCC resources, use ResourceToELCC 'elcc_axis_multiplier' attribute."
                )
        if num_errors > 0:
            raise ValueError(
                f"{num_errors} issue(s) with Resource → ELCC → Reliability Policy linkages. See log messages above."
            )

    def _construct_investment_rules(self, model: "ModelTemplate", construct_costs: bool):
        pyomo_components = LastUpdatedOrderedDict()
        #############
        # Variables #
        #############

        pyomo_components.update(
            policy_slack_up=pyo.Var(model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="Policy Slack Up (Units)")
        )
        pyomo_components.update(
            policy_slack_down=pyo.Var(model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="Policy Slack Down (Units)")
        )

        ###############
        # Expressions #
        ###############

        pyomo_components.update(
            NQC_lhs=pyo.Expression(model.MODELED_YEARS, rule=self._NQC_lhs, doc="NQC Reliable Capacity (MW)")
        )

        pyomo_components.update(
            ELCC_lhs=pyo.Expression(model.MODELED_YEARS, rule=self._ELCC_lhs, doc="ELCC Reliable Capacity (MW)")
        )

        pyomo_components.update(
            policy_lhs=pyo.Expression(model.MODELED_YEARS, rule=self._policy_lhs, doc="Achieved (Units)")
        )

        ###############
        # Constraints #
        ###############

        pyomo_components.update(policy_constraint=pyo.Constraint(model.MODELED_YEARS, rule=self._policy_constraint))

        if construct_costs:
            pyomo_components.update(
                policy_slack_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._policy_slack_cost, doc="Policy Slack Cost ($)"
                ),
                annual_total_investment_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._total_policy_cost_in_modeled_year,
                    doc="Annual Total Investment Cost ($)",
                ),
                annual_total_slack_investment_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._policy_slack_cost,  # referece total_policy_slack_cost
                    doc="Annual Total Slack Investment Cost ($)",
                ),
            )

        return pyomo_components

    def _construct_operational_rules(self, model: "ModelTemplate", construct_costs: bool):
        """Operational rules which are defined in Policy class are moved to investment rules in the PRM class because
        a PRM policy and its costs are part of an investment decision."""
        pyomo_components = LastUpdatedOrderedDict()
        if construct_costs:
            pyomo_components.update(annual_total_operational_cost=pyo.Expression(model.MODELED_YEARS, rule=0))

        return pyomo_components

    def _construct_output_expressions(self, construct_costs: bool):
        if len(self.assets) > 0:
            self.formulation_block.PRM_ASSETS = pyo.Set(initialize=self.assets.keys())

            self.formulation_block.asset_specific_nqc_contributions = pyo.Expression(
                self.formulation_block.PRM_ASSETS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._asset_specific_nqc_contributions,
                doc="NQC (MW)",
            )
            self.formulation_block.asset_specific_reliability_contribution = pyo.Expression(
                self.formulation_block.PRM_ASSETS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._asset_specific_reliability_contributions,
                doc="Reliability Capacity (MW)",
            )

        if construct_costs:
            self.formulation_block.policy_cost_without_slack = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._policy_cost_without_slack,
                doc="Policy Cost Without Slack ($)",
            )

            self.formulation_block.policy_shadow_price = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._policy_constraint_dual,
                doc="Unweighted Dual Value ($/Unit)",
            )

    #########
    # Rules #
    #########

    def _NQC_lhs(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Calculate sum of resource NQCs for a given PRM policy."""
        NQC_lhs = 0
        for linkage in self.assets.values():
            asset = linkage.instance_from
            _policy = linkage.instance_to.name
            if hasattr(asset.formulation_block, "NQC"):
                NQC_lhs += asset.formulation_block.NQC[_policy, modeled_year]
        return NQC_lhs

    def _ELCC_lhs(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Calculate sum of linked ELCC surfaces."""
        ELCC_lhs = 0
        for linkage in self.elcc_surfaces.values():
            elcc_surface = linkage.instance_from
            ELCC_lhs += elcc_surface.formulation_block.ELCC_MW[modeled_year]
        return ELCC_lhs

    def _policy_lhs(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.NQC_lhs[modeled_year] + block.ELCC_lhs[modeled_year]

    def _policy_cost_without_slack(self, block: pyo.Block, modeled_year: pd.Timestamp):
        if self.price is None:
            return 0
        else:
            return self.price.data.at[modeled_year] * block.policy_lhs[modeled_year]

    def _asset_specific_nqc_contributions(self, block: pyo.Block, _asset: str, modeled_year: pd.Timestamp):
        return self.assets[_asset].instance_from.formulation_block.NQC[self.name, modeled_year]

    def _asset_specific_reliability_contributions(self, block: pyo.Block, _asset: str, modeled_year: pd.Timestamp):
        return self.assets[_asset].instance_from.formulation_block.reliability_capacity[self.name, modeled_year]

    def _annual_total_slack_investment_cost(self, block, modeled_year):
        return self.formulation_block.policy_slack_cost[modeled_year]
