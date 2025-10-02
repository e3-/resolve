from __future__ import annotations

from typing import Annotated
from typing import ClassVar

import pandas as pd
import pyomo.environ as pyo
from pydantic import Field

from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.system.asset import AssetGroup


class CaisoTxConstraint(Component):
    """For the CPUC IRP, we model transmission constraints within the CAISO system.

    These constraints relate assumed resource impacts (by technology type & BA) to assumed "headroom" on the
    CAISO system during Highest System Need (HSN), Secondary System Need (SSN), and offpeak times.
    """

    SAVE_PATH: ClassVar[str] = "caiso_tx_constraints"
    assets: Annotated[dict[str, linkage.AssetToCaisoTxConstraint], Metadata(linkage_order="from")] = {}
    prm_policies: Annotated[dict[str, linkage.ReliabilityContribution], Metadata(linkage_order="to")] = {}

    enable_hsn_constraint: bool
    slack_penalty: Annotated[float, Metadata(units=units.dollar / units.megawatt)] = 10_000_000
    hsn_headroom: Annotated[ts.NumericTimeseries, Metadata(category=FieldCategory.BUILD, units=units.megawatt)] = Field(
        default_factory=ts.NumericTimeseries.zero,
        title="HSN Headroom (MW)",
        default_freq="YS",
        up_method="ffill",
        down_method="mean",
        weather_year=False,
    )
    enable_ssn_constraint: bool
    ssn_headroom: Annotated[ts.NumericTimeseries, Metadata(category=FieldCategory.BUILD, units=units.megawatt)] = Field(
        default_factory=ts.NumericTimeseries.zero,
        title="SSN Headroom (MW)",
        default_freq="YS",
        up_method="ffill",
        down_method="mean",
        weather_year=False,
    )
    enable_eods_constraint: bool
    eods_headroom: Annotated[ts.NumericTimeseries, Metadata(category=FieldCategory.BUILD, units=units.megawatt)] = (
        Field(
            default_factory=ts.NumericTimeseries.zero,
            title="EODS Off-Peak Headroom (MW)",
            default_freq="YS",
            up_method="ffill",
            down_method="mean",
            weather_year=False,
        )
    )

    @property
    def build_assets(self):
        """For build decisions, always use the individual asset instances. This is a recursive property that gets the
        Assets directly linked to this AssetGroup plus any Assets linked to AssetGroups linked to this AssetGroup."""
        build_assets = self.directly_linked_build_assets
        for k, v in self.assets.items():
            if isinstance(v.instance_from, AssetGroup):
                build_assets |= v.instance_to.build_assets

        return build_assets

    # TODO: Get rid of this property and just have recursive build_assets?
    @property
    def directly_linked_build_assets(self):
        """For build decisions, always use the individual asset instances."""
        return {k: v for k, v in self.assets.items() if not isinstance(v.instance_from, AssetGroup)}

    @property
    def annual_results_column_order(self):
        """This property defines the ordering of columns in the component's annual results summary out of Resolve.
        The name of the model field or formulation_block pyomo component can be used.
        """
        return [
            "hsn_headroom",
            "ssn_headroom",
            "eods_headroom",
            "hsn_lhs",
            "ssn_lhs",
            "eods_lhs",
            "hsn_slack",
            "ssn_slack",
            "eods_slack",
            "annual_total_investment_cost",
            "annual_total_slack_investment_cost",
        ]

    @property
    def prm_policy(self):
        """Returns PRM Policy instance"""
        linkage_name = list(self.prm_policies.keys())[0]
        prm_policy = self.prm_policies[linkage_name].instance_to

        return prm_policy

    def revalidate(self):
        # TODO: Redesign this revalidate() method to record all data mismatches and then return the error message.
        assert len(self.assets) > 0, f"At least one asset must be connected to CAISO transmission upgrade constraint {self.name}"

        assert (
            len(self.prm_policies) == 1
        ), f"Exactly one PRM policy must be linked to CAISO transmission upgrade constraint {self.name}"

        prm_policy = self.prm_policy
        for asset in self.build_assets.values():
            assert prm_policy.name in asset.instance_from.prm_policies, (
                f"Asset {asset.instance_from.name} must be linked to policy {prm_policy.name} in order for its CAISO "
                f"Tx Constraint {self.name} to be constructed. Add a ReliabilityContribution linkage between "
                f"{asset.instance_from.name} and {prm_policy.name}."
            )

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        return pyomo_components

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)

        prm_policies = pyo.Set(initialize=self.prm_policies.keys())
        if self.enable_hsn_constraint:
            pyomo_components.update(
                hsn_slack=pyo.Var(model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="HSN Slack"),
                hsn_lhs=pyo.Expression(model.MODELED_YEARS, rule=self._hsn_lhs, doc="HSN LHS (MW)"),
                hsn_constraint=pyo.Constraint(model.MODELED_YEARS, rule=self._hsn_constraint),
            )
        if self.enable_ssn_constraint:
            pyomo_components.update(
                ssn_slack=pyo.Var(model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="SSN Slack"),
                ssn_lhs=pyo.Expression(model.MODELED_YEARS, rule=self._ssn_lhs, doc="SSN LHS (MW)"),
                ssn_constraint=pyo.Constraint(model.MODELED_YEARS, rule=self._ssn_constraint),
            )
        if self.enable_eods_constraint:
            pyomo_components.update(
                eods_slack=pyo.Var(model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="EODS Slack"),
                eods_lhs=pyo.Expression(model.MODELED_YEARS, rule=self._eods_lhs, doc="EODS LHS (MW)"),
                eods_constraint=pyo.Constraint(model.MODELED_YEARS, rule=self._eods_constraint),
            )

        if construct_costs:
            pyomo_components.update(
                annual_total_slack_investment_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_slack_investment_cost,
                    doc="Annual Total Slack Investment Cost ($)",
                ),
                annual_total_investment_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._annual_total_investment_cost, doc="Annual Total Investment Cost ($)"
                ),
            )

        return pyomo_components

    def _hsn_lhs(self, block, modeled_year: pd.Timestamp):
        return sum(
            asset.hsn_factor
            * asset.instance_from.formulation_block.reliability_capacity[self.prm_policy.name, modeled_year]
            for asset in self.build_assets.values()
        )

    def _hsn_constraint(self, block, modeled_year: pd.Timestamp):
        return block.hsn_lhs[modeled_year] <= self.hsn_headroom.data[modeled_year] + block.hsn_slack[modeled_year]

    def _ssn_lhs(self, block, modeled_year: pd.Timestamp):
        return sum(
            asset.ssn_factor
            * asset.instance_from.formulation_block.reliability_capacity[self.prm_policy.name, modeled_year]
            for asset in self.build_assets.values()
        )

    def _ssn_constraint(self, block, modeled_year: pd.Timestamp):
        return block.ssn_lhs[modeled_year] <= self.ssn_headroom.data[modeled_year] + block.ssn_slack[modeled_year]

    def _eods_lhs(self, block, modeled_year: pd.Timestamp):
        return sum(
            asset.eods_factor * asset.instance_from.formulation_block.operational_capacity[modeled_year]
            for asset in self.build_assets.values()
        )

    def _eods_constraint(self, block, modeled_year: pd.Timestamp):
        """Energy-only deliverability status is determined purely on `operational_capacity` and not on the qualifying FCDS capacity (`reliability_capacity`)."""
        return block.eods_lhs[modeled_year] <= self.eods_headroom.data[modeled_year] + block.eods_slack[modeled_year]

    def _annual_total_slack_investment_cost(self, block, modeled_year: pd.Timestamp):
        slacks = 0
        if self.enable_hsn_constraint:
            slacks += block.hsn_slack[modeled_year]
        if self.enable_ssn_constraint:
            slacks += block.ssn_slack[modeled_year]
        if self.enable_eods_constraint:
            slacks += block.eods_slack[modeled_year]
        return self.slack_penalty * slacks

    def _annual_total_investment_cost(self, block, modeled_year: pd.Timestamp):
        return block.annual_total_slack_investment_cost[modeled_year]
