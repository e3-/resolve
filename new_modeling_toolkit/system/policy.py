import enum
import operator
from typing import Literal
from typing import Optional

import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pydantic import Field
from pydantic import root_validator

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import dir_str
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.utils.core_utils import timer


@enum.unique
class TargetBasis(enum.Enum):
    SALES = "sales"
    SYSTEM_LOAD = "system load"


@enum.unique
class TargetUnits(enum.Enum):
    RELATIVE = "relative"
    ABSOLUTE = "absolute"


class ConstraintOperator(enum.Enum):
    GREATER_THAN_OR_EQUAL_TO = operator.ge, ">=", "ge"
    LESS_THAN_OR_EQUAL_TO = operator.le, "<=", "le"
    EQUAL_TO = operator.eq, "==", "eq"

    def __new__(cls, _, *values):
        obj = object.__new__(cls)
        # first value is canonical value
        obj._value_ = values[0]
        for other_value in values[1:]:
            cls._value2member_map_[other_value] = obj
        obj._all_values = values
        return obj

    def __init__(self, operator, *args):
        self.operator = operator

    def __repr__(self):
        return f"<{self.__class__.__name__}.{self._name_}: {', '.join([repr(v) for v in self._all_values])}>"


class Policy(component.Component):
    """Parent class for specific types of policy sub-classes.

    This is a pseudo-abstract base class.
    """

    ######################
    # MAPPING ATTRIBUTES #
    ######################
    # The parent Policy class has no defined linkages

    ####################
    # ATTRIBUTES       #
    ####################
    constraint_operator: ConstraintOperator
    loads: dict[str, linkage.Linkage] = {}
    type: Literal["emissions", "energy", "prm"] = Field(
        description=("Type of policy. Can be related to energy, emissions, prm")
    )

    target: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual"
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
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        description=(
            "Adjustment to the target. A **positive** adjustment would add the target, while a **negative** adjustment "
            "would be subtracted from the target."
        ),
    )
    price: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual"
    )
    opt_policy_lhs: Optional[ts.NumericTimeseries] = Field(None, description="Total RHS achieved")

    # Price and target cannot both be defined
    @root_validator
    def price_or_target(cls, values):
        if sum(values[i] is not None for i in ["price", "target"]) != 1:
            raise ValueError(
                f"Check {values['name']}: for a given policy, either a price or a target can be defined (but not both)."
            )

        return values

    ############################
    # Optimization Constraints #
    ############################
    def _construct(self, model: pyo.ConcreteModel, temporal_settings: "TemporalSettings"):
        pass

    def construct_constraints(self, model: pyo.ConcreteModel, temporal_settings: "TemporalSettings"):
        self._construct(model, temporal_settings)

    ########################
    # Optimization Results #
    ########################
    opt_dual_value_unweighted: Optional[ts.NumericTimeseries] = Field(
        None,
        description=(
            "Optimized dual value for the policy constraint, without discount factors or weightings applied, in "
            "dollars per unit."
        ),
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    def get_total_load(self, year: int):
        """Update policy targets if loads are linked to policies"""
        # TODO 2023-05-18: This could be simplified if we didn't pre-multiply the load component by "T&D losses"
        #  and did that at a later step
        total_load = pd.concat(
            [
                link._instance_from.scaled_profile_by_modeled_year[year].data
                * link.multiplier.data.loc[f"{year}-01-01"]
                / (
                    link._instance_from.td_losses_adjustment.data.loc[f"{year}-01-01"]
                    if self.target_basis == TargetBasis.SALES
                    else 1
                )  # put back into sales if needed
                for link in self.loads.values()
            ],
            axis=1,
        ).sum(axis=1)

        total_load = total_load.multiply(self.target.data.loc[f"{year}-01-01"])

        return total_load

    def update_targets_from_loads(self):
        pass


class AnnualEnergyStandard(Policy):
    """Policy class for Renewable Portfolio Standard (RPS) or Clean Energy Standard (CES) type policies."""

    ######################
    # MAPPING ATTRIBUTES #
    ######################
    resources: dict[str, linkage.AllToPolicy] = {}
    candidate_fuels: dict[str, linkage.Linkage] = {}
    type: str = "energy"
    constraint_operator: ConstraintOperator = ConstraintOperator.GREATER_THAN_OR_EQUAL_TO

    ########################
    # Optimization Results #
    ########################
    opt_annual_contribution_by_resource_mwh: Optional[pd.Series] = Field(
        None,
        description="Annual contributions to the policy by resource, in MWh.",
    )

    def update_targets_from_loads(self):
        if self.loads and self.target_units == TargetUnits.RELATIVE:
            for year in self.target.data.index:
                total_load = self.get_total_load(year.year)
                self.target._data_dict = None
                self.target.data.loc[year.year] = total_load.groupby(total_load.index.year).sum().mean()


class HourlyEnergyStandard(Policy):
    """Ideally this would be merged with `AnnualEnergyStandard`, but to preserve backward compatibility for now, keeping separate."""

    slack_penalty: ts.NumericTimeseries = Field(
        default_factory=ts.Timeseries.default_penalty,
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
    )

    ######################
    # MAPPING ATTRIBUTES #
    ######################
    resources: dict[str, linkage.AllToPolicy] = {}
    candidate_fuels: dict[str, linkage.Linkage] = {}
    type: str = "energy"
    constraint_operator: ConstraintOperator = ConstraintOperator.GREATER_THAN_OR_EQUAL_TO
    _target_by_model_year: dict[int, ts.NumericTimeseries] = {}

    ########################
    # Optimization Results #
    ########################
    opt_annual_contribution_by_resource_mwh: Optional[pd.Series] = Field(
        None,
        description="Annual contributions to the policy by resource, in MWh.",
    )

    ############################
    # Optimization Constraints #
    ############################
    def _construct(self, model: pyo.ConcreteModel, temporal_settings: "TemporalSettings"):
        # fmt: off
        model.blocks[self.name].slack_up = pyo.Var(model.TIMEPOINTS, within=pyo.NonNegativeReals)
        @model.blocks[self.name].Expression(model.TIMEPOINTS)
        def target(block, model_year, rep_period, hour):
            return (
                self._target_by_model_year[model_year].slice_by_timepoint(temporal_settings, model_year, rep_period, hour) +
                self.target_adjustment.slice_by_year(model_year)
            )

        _policy_resources = pyo.Set(initialize=sorted(self.resources.keys()))

        @model.blocks[self.name].Expression(_policy_resources, model.TIMEPOINTS)
        def resource_contribution(block, resource, model_year, rep_period, hour):
            return (
                self.resources[resource].multiplier.slice_by_year(model_year) *
                block.model().Provide_Power_MW[resource, model_year, rep_period, hour]
            )

        @model.blocks[self.name].Constraint(model.TIMEPOINTS)
        def constraint(block, model_year, rep_period, hour):
            return self.constraint_operator.operator(
                sum(
                    block.resource_contribution[resource, model_year, rep_period, hour]
                    for resource in _policy_resources
                ) +
                block.slack_up[model_year, rep_period, hour],
                block.target[model_year, rep_period, hour],
            )

        @model.blocks[self.name].Expression(model.MODEL_YEARS)
        def slack_penalty(block, model_year):
            return sum(
                self.slack_penalty.slice_by_timepoint(temporal_settings, model_year, rep_period, hour) *
                block.slack_up[model_year, rep_period, hour] *
                block.model().rep_period_weight[rep_period] *
                block.model().rep_periods_per_model_year[model_year] *
                temporal_settings.timesteps.at[hour]
                for hour in block.model().HOURS
                for rep_period in block.model().REP_PERIODS
            )
        # fmt: on

    def check_constraint_violations(self, model: pyo.ConcreteModel):
        if pyo.value(sum(model.blocks[self.name].slack_up[idx] for idx in model.blocks[self.name].slack_up)) > 0:
            logger.warning(f"Constraint violation (non-zero slack) for {self.name}")

    def update_targets_from_loads(self):
        if self.loads and self.target_units == TargetUnits.RELATIVE:
            for year in self.target.data.index:
                total_load = self.get_total_load(year.year)
                self._target_by_model_year[year.year] = ts.NumericTimeseries(
                    name=f"Scaled {self.name} hourly energy policy target",
                    data=self.target.slice_by_year(year.year) * total_load,
                    weather_year=True,
                )


class AnnualEmissionsPolicy(Policy):
    """Policy class for annual system emissions targets.

    Depending on scope of governed items, this could be an electric sector-only or multi-sector emissions target.

    """

    ######################
    # MAPPING ATTRIBUTES #
    ######################
    candidate_fuels: dict[str, linkage.Linkage] = {}
    final_fuels: dict[str, linkage.Linkage] = {}
    resources: dict[str, linkage.Linkage] = {}
    tx_paths: dict[str, linkage.Linkage] = {}
    negative_emissions_technologies: dict[str, linkage.Linkage] = {}
    pollutants: dict[str, linkage.Linkage] = {}
    non_energy_subsectors: dict[str, linkage.Linkage] = {}

    @property
    def assets(self):
        return self.resources | self.tx_paths

    @property
    def governed_items(self):
        return self.candidate_fuels | self.final_fuels_demands | self.resources | self.tx_paths

    ########################
    # Optimization Results #
    ########################
    type: str = "emissions"
    target_basis: TargetBasis = TargetBasis.SYSTEM_LOAD
    target_units: TargetUnits = TargetUnits.ABSOLUTE
    constraint_operator: ConstraintOperator = ConstraintOperator.LESS_THAN_OR_EQUAL_TO
    # TODO 2023-05-20: Could make target relative to some baseline, but currently absolute

    opt_annual_contribution_by_resource: Optional[pd.Series] = Field(
        None,
        description="Annual contributions to the policy by resource.",
    )
    opt_annual_contribution_by_tx_path: Optional[pd.Series] = Field(
        None,
        description="Annual contributions to the policy by resource.",
    )

    def revalidate(self):
        """Validate Resource → Candidate Fuel → Emissions Policy criteria are met.

        1. Resource → Policy linkage or Candidate Fuel → Policy linkage must have a multiplier for every resource linked.
        2. Cannot have a multiplier defined on both a Resource → Policy and Candidate Fuel → Policy
        """
        num_errors = 0

        # 1. Resource → Policy linkage or Candidate Fuel → Policy linkage must have a multiplier for every resource linked.
        candidate_fuels_without_multiplier = {
            name
            for name, fuel in self.candidate_fuels.items()
            if fuel._instance_from.policies[self.name].multiplier is None
        }

        resources_linked_to_candidate_fuels_without_multiplier = {
            name
            for name, r in self.resources.items()
            if [fuel for fuel in r._instance_from.candidate_fuels.keys() if fuel in candidate_fuels_without_multiplier]
        }

        resources_without_multiplier = {
            name for name, r in self.resources.items() if r._instance_from.policies[self.name].multiplier is None
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
            if fuel._instance_from.policies[self.name].multiplier is not None
        }

        resources_linked_to_candidate_fuels_with_multiplier = {
            name
            for name, r in self.resources.items()
            if [fuel for fuel in r._instance_from.candidate_fuels.keys() if fuel in candidate_fuels_with_multiplier]
        }

        resources_with_multiplier = {
            name for name, r in self.resources.items() if r._instance_from.policies[self.name].multiplier is not None
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

    ####################
    # ATTRIBUTES       #
    ####################


class PlanningReserveMargin(Policy):
    """Policy class for Planning Reserve Margin (PRM) type policies.

    Assets can be assigned Effective Load Carrying Capability (ELCC) linkages or Net Qualifying Capacity (NQC)
    attributes to contribute toward PRM polices.

    """

    ######################
    # MAPPING ATTRIBUTES #
    ######################
    assets_: dict[str, linkage.Linkage] = {}
    elcc_surfaces: dict[str, linkage.Linkage] = {}
    resources: dict[str, linkage.Linkage] = {}
    tx_paths: dict[str, linkage.Linkage] = {}

    @property
    def assets(self):
        return self.resources | self.tx_paths | self.assets_

    @property
    def governed_items(self):
        return self.elcc_surfaces | self.loads | self.resources | self.tx_paths | self.assets

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
        down_method="annual",
    )

    opt_resource_reliability_capacity: Optional[pd.Series] = Field(
        None,
        description="Annual resource capacity counted toward PRM constraint (i.e., delivered).",
    )
    opt_resource_energy_only_capacity: Optional[pd.Series] = Field(
        None,
        description="Annual resource capacity **not** counted toward PRM constraint (i.e., energy-only).",
    )

    opt_resource_nqc: Optional[pd.Series] = Field(
        None,
        description="Annual resource NQC.",
    )

    def update_targets_from_loads(self):
        if self.loads and self.target_units == TargetUnits.RELATIVE:
            for year in self.target.data.index:
                total_load = self.get_total_load(year.year)
                self.target._data_dict = None
                self.target.data.loc[year.year] = total_load.groupby(total_load.index.year).max().median()

    @timer
    def revalidate(self):
        """Validate Resource → ELCC → PRM linkage criteria are met.

        1. Check that every resource linked to the reliability policy has at least an NQC or ELCC assigned
        2. There cannot be more than one ELCC surface for a resource-policy pair
        3. There cannot be both an ELCC and NQC for the same resource
        """
        num_errors = 0
        # 1. Check that every resource linked to the reliability policy has at least an NQC or ELCC assigned
        resources_without_elcc_linked_to_policy = {
            name
            for name, r in self.resources.items()
            if not [e for e in r._instance_from.elcc_surfaces.values() if self.name in e._instance_to.policies]
        }
        resources_without_nqc = {
            name for name, r in self.resources.items() if r._instance_from.policies[self.name].multiplier is None
        }

        resources_without_elcc_or_nqc = resources_without_elcc_linked_to_policy & resources_without_nqc

        if resources_without_elcc_or_nqc:
            num_errors += len(resources_without_elcc_or_nqc)
            logger.exception(
                f"For policy {self.name}, the following resources do not have an ELCC surface or NQC assigned:\n{resources_without_elcc_or_nqc}"
            )

        if self.elcc_surfaces:
            # Get set of ELCCs assigned to reliability policy
            policy_elccs = set(self.elcc_surfaces.keys())

            # 2. There cannot be more than one ELCC surface for a resource-policy pair
            resources_with_multiple_elccs = {}
            for r in self.resources.values():
                if r._instance_from.elcc_surfaces:
                    # Get set of ELCCs assigned to resource
                    resource_elccs = set(r._instance_from.elcc_surfaces.keys())
                    # Check set intersection
                    elcc_intersection = resource_elccs.intersection(policy_elccs)
                    if len(elcc_intersection) > 1:
                        resources_with_multiple_elccs[r._instance_from.name] = elcc_intersection

            if resources_with_multiple_elccs:
                num_errors += len(resources_with_multiple_elccs)
                logger.exception(
                    f"For policy {self.name}, the following resources have multiple ELCC surfaces assigned:\n{resources_with_multiple_elccs}"
                    f"\nFor a given reliability policy, resources may only contribute once."
                )

            # 3. There cannot be both an ELCC and NQC for the same resource
            resources_with_both_elcc_nqc = [
                r._instance_from.name
                for r in self.resources.values()
                if r._instance_from.elcc_surfaces
                and set(r._instance_from.elcc_surfaces.keys()).intersection(policy_elccs)
                and r.multiplier is not None
            ]

            if resources_with_both_elcc_nqc:
                num_errors += len(resources_with_both_elcc_nqc)
                logger.exception(
                    f"For policy {self.name}, the following resources have both ELCC and NQC assigned:\n{resources_with_both_elcc_nqc}"
                    f"\nTo assign a derate to ELCC resources, use ResourceToELCC 'elcc_axis_multiplier' attribute."
                )
        if num_errors > 0:
            raise ValueError(
                f"{num_errors} issues with Resource → ELCC → Reliability Policy linkages. See log messages above."
            )


if __name__ == "__main__":
    # data_path = dir_str.data_dir / "interim" / "policies"
    # policies = Policy.from_dir(data_path)
    # print(policies)
    p = PlanningReserveMargin.from_csv(
        dir_str.data_interim_dir / "policies" / "System RA.csv", scenarios=["base", "PRM - High Imports"]
    )
    print()
