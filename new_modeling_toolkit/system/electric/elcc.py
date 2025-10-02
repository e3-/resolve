from typing import ClassVar
from typing import Optional

import pandas as pd
import pyomo.environ as pyo
from pydantic import Field

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts


class ELCCFacet(component.Component):
    """A single ELCC facet, representing a plane equation.

    axis_0 is the intercept
    axis_1 and axis_2 are the "slopes"
    """

    SAVE_PATH: ClassVar[str] = "elcc_surfaces/facets"
    surface: dict[str, linkage.ELCCFacetToSurface] = {}

    # TODO: Add more axis
    axis_0: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", up_method="ffill", down_method="first")
    axis_1: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", up_method="ffill", down_method="first")
    axis_2: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", up_method="ffill", down_method="first")
    axis_3: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", up_method="ffill", down_method="first")


class ELCCSurface(component.Component):
    SAVE_PATH: ClassVar[str] = "elcc_surfaces"
    facets: dict[str, linkage.ELCCFacetToSurface] = {}
    assets: dict[str, linkage.AssetToELCC] = {}
    prm_policies: dict[str, linkage.ELCCReliabilityContribution] = {}

    def revalidate(self):
        if len(self.assets) == 0:
            raise AttributeError(
                f"`ELCCSurface` {self.name} does not have any Assets linked to it. "
                f"The surface will not contribute to any PRM policies. Check your linkages.csv file."
            )

        if len(self.facets) == 0:
            raise AttributeError(
                f"`ELCCSurface` {self.name} does not have any ELCCFacets linked to it. "
                f"The surface will not contribute to any PRM policies. Check your linkages.csv file."
            )

        if len(self.prm_policies) == 0:
            raise AttributeError(
                f"`ELCCSurface` {self.name} does not have any `PlanningReserveMargin` policies linked to it."
                f"Check your linkages.csv file for an ELCCReliabilityContribution linkage."
            )

        for asset_linkage in self.assets.values():
            for prm_policy in self.prm_policies.keys():
                if prm_policy not in asset_linkage.instance_from.prm_policies.keys():
                    raise AttributeError(
                        f"`Asset` {asset_linkage.instance_from.name} is linked to `ELCCSurface` {self.name}, which is"
                        f"linked to `PlanningReserveMargin` policy {prm_policy}, but {asset_linkage.instance_from.name}"
                        f"itself must also be linked to {prm_policy} via a `ReliabilityContribution` linkage."
                        f"Check your linkages.csv file."
                    )

            if asset_linkage.elcc_axis_index is None:
                raise AttributeError(
                    f"`AssetToELCC` Linkage between Asset `{asset_linkage.instance_from.name}` and ELCCSurface "
                    f"`{self.name}` has no `elcc_axis_index` defined."
                )

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict()

        ########
        # Sets #
        ########

        """The set of all facets that exist for this ELCC Surface"""
        FACETS = pyo.Set(initialize=self.facets.keys())
        pyomo_components.update(FACETS=FACETS)

        """The set of all PRM policies that use this ELCC surface"""
        PRM_POLICIES = pyo.Set(initialize=self.prm_policies.keys())
        pyomo_components.update(PRM_POLICIES=PRM_POLICIES)

        #############
        # Variables #
        #############

        pyomo_components.update(
            ELCC_MW=pyo.Var(
                model.MODELED_YEARS,
                units=pyo.units.MW,
                within=pyo.NonNegativeReals,
                doc="ELCC Surface Total Reliability Capacity (MW)",
            )
        )

        ###############
        # Expressions #
        ###############

        pyomo_components.update(
            ELCC_facet_value=pyo.Expression(
                FACETS,
                PRM_POLICIES,
                model.MODELED_YEARS,
                rule=self._ELCC_facet_value,
                doc="ELCC Facet Value for Policy",
            )
        )

        if construct_costs:
            pyomo_components.update(
                annual_total_investment_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._annual_total_investment_cost
                )
            )

        ###############
        # Constraints #
        ###############

        pyomo_components.update(
            ELCC_MW_constraint=pyo.Constraint(
                FACETS,
                PRM_POLICIES,
                model.MODELED_YEARS,
                rule=self._ELCC_MW_constraint,
            )
        )

        return pyomo_components

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict()

        if construct_costs:
            pyomo_components.update(
                annual_total_operational_cost=pyo.Expression(model.MODELED_YEARS, rule=lambda block, year: 0)
            )

        return pyomo_components

    def _ELCC_MW_constraint(self, block: pyo.Block, _facet: str, _policy: str, modeled_year: pd.Timestamp):
        """Constrain `ELCC_MW` variable by each ELCC facet."""
        return block.ELCC_MW[modeled_year] <= block.ELCC_facet_value[_facet, _policy, modeled_year]

    def _ELCC_facet_value(self, block: pyo.Block, _facet: str, _policy: str, modeled_year: pd.Timestamp):

        # Warning is raised if no assets are linked. Return zero for facet value
        if len(self.assets) == 0:
            return 0

        facet = self.facets[_facet].instance_from

        # Get # of ELCC axes (currently limited to two in elcc.py)
        elcc_axes = range(1, max(r.elcc_axis_index for r in self.assets.values()) + 1)

        # Calculate facet value from slope-intercept
        facet_elcc_mw = (
            # Intercept
            facet.axis_0.data.at[modeled_year]
            +
            # Sum ``reliability_capacity`` of all resources assigned to this axis
            sum(
                getattr(facet, f"axis_{axis_num}").data.at[modeled_year]
                * sum(
                    asset_linkage.elcc_axis_multiplier
                    * (
                        asset_linkage.instance_from.formulation_block.reliability_capacity[_policy, modeled_year]
                    )
                    for _asset, asset_linkage in self.assets.items()
                    if asset_linkage.elcc_axis_index == axis_num
                )
                for axis_num in elcc_axes
            )
        )
        return facet_elcc_mw

    def _annual_total_investment_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        # Subtract a very small value from the total investment cost so that ELCC surface chooses smallest facet value when constraint is non-binding
        return -0.001 * block.ELCC_MW[modeled_year]
