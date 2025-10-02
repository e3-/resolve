import enum
import itertools
import pprint
from typing import Any
from typing import ClassVar
from typing import Optional
from typing import Type
from typing import TypeVar

import numpy as np
import pandas as pd
import pydantic
import pyomo.environ as pyo
from loguru import logger
from pydantic import BeforeValidator
from pydantic import computed_field
from pydantic import Field
from typing_extensions import Annotated

from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import ModelType
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.three_way_linkage import CustomConstraintLinkage
from new_modeling_toolkit.core.utils.pyomo_utils import get_index_labels

_ASSET_POTENTIAL_SLACK_PENALTY = 50_000_000


@enum.unique
class AssetCategory(enum.Enum):
    THERMAL = "thermal"
    FIRM = "firm"
    VARIABLE = "variable"
    HYDRO = "hydro"
    STORAGE = "storage"
    DEMAND_RESPONSE = "dr"
    HYBRID_STORAGE = "hybrid_storage"
    FLEXIBLE_LOAD = "flexible_load"


class Asset(Component):
    """An Asset is anything with a cost & quantity."""

    _DOCS_URL: ClassVar[str] = (
        "https://docs.ethree.com/projects/kit/en/resolve-refactor-test-case-v4/system/index.html#new_modeling_toolkit.system.asset.Asset."
    )
    SAVE_PATH: ClassVar[str] = "assets"

    ############
    # Linkages #
    ############
    asset_groups: Annotated[dict[str, linkage.AssetToAssetGroup], Metadata(linkage_order="to")] = {}
    caiso_tx_constraints: Annotated[dict[str, linkage.AssetToCaisoTxConstraint], Metadata(linkage_order="to")] = {}
    custom_constraints: Annotated[
        dict[str, CustomConstraintLinkage], Metadata(linkage_order=3, default_exclude=True)
    ] = {}
    elcc_surfaces: Annotated[dict[str, linkage.AssetToELCC], Metadata(linkage_order="to")] = {}
    emissions_policies: Annotated[
        dict[str, linkage.EmissionsContribution], Metadata(linkage_order="to", category=FieldCategory.OPERATIONS)
    ] = {}
    annual_energy_policies: Annotated[
        dict[str, linkage.AnnualEnergyStandardContribution],
        Metadata(linkage_order="to", category=FieldCategory.OPERATIONS),
    ] = {}
    hourly_energy_policies: Annotated[
        dict[str, linkage.HourlyEnergyStandardContribution],
        Metadata(linkage_order="to", category=FieldCategory.OPERATIONS),
    ] = {}
    prm_policies: Annotated[dict[str, linkage.ReliabilityContribution], Metadata(linkage_order="to")] = {}
    erm_policies: Annotated[dict[str, linkage.ERMContribution], Metadata(linkage_order="to")] = {}
    zones: Annotated[
        dict[str, linkage.AssetToZone], Metadata(linkage_order="to", category=FieldCategory.OPERATIONS)
    ] = {}

    #################################
    # Build & Retirement Attributes #
    #################################
    vintage_parent_group: Optional[str] = Field(None, title="Vintage Parent Group")
    build_year: Annotated[pd.Timestamp, Metadata(category=FieldCategory.BUILD)] = Field(
        pd.Timestamp("1/1/2000"),
        alias="commission_date",
    )

    integer_build_increment: Annotated[float | None, Metadata(category=FieldCategory.BUILD, units=units.megawatt)] = (
        Field(
            None,
            ge=0,
            description="If not None, consider integer (rather than linear) build decisions. If set equal to potential, this will force an all or nothing choice. Otherwise, this can be used to build certain increments of assets",
            title="Integer Build Unit Size (MW)",
        )
    )

    @pydantic.field_validator("build_year", mode="before")
    def convert_build_year(cls, value):
        converted = pd.Timestamp(value)
        return converted

    can_build_new: Annotated[bool, Metadata(category=FieldCategory.BUILD)] = Field(
        False,
        description="Whether resource can be expanded (for now only linear capacity expansion).",
    )
    can_retire: Annotated[bool, Metadata(category=FieldCategory.BUILD)] = Field(
        False,
        description="Whether resource can be retired. By default, resources cannot be retired.",
    )

    physical_lifetime: Annotated[int, Metadata(category=FieldCategory.BUILD, units=units.year)] = Field(
        100,
        description="Number of years after commission date that asset is operational.",
        ge=0,
    )

    potential: Annotated[float | None, Metadata(category=FieldCategory.BUILD, units=units.megawatt)] = Field(
        default=np.inf, ge=0, title="Potential (MW)"
    )
    planned_capacity: Annotated[ts.NumericTimeseries, Metadata(category=FieldCategory.BUILD, units=units.megawatt)] = (
        Field(
            default_factory=ts.NumericTimeseries.zero,
            title="Planned Capacity (MW)",
            default_freq="YS",
            up_method="ffill",
            down_method="mean",
            weather_year=False,
        )
    )
    min_operational_capacity: Annotated[ts.NumericTimeseries | None, Metadata(units=units.MW)] = Field(
        default=None,
        default_freq="YS",
        weather_year=False,
        up_method="interpolate",
        down_method="mean",
        description="Minimum required operational capacity (planned+selected) by model year for this asset",
        title="Minimum Operational Capacity (MW)",
    )

    ##################################################
    # Build and Retirement Outputs from Solved Model #
    ##################################################
    """These three attributes are outputs, not inputs. They are initialized to None and are updated to their chosen
    optimal values after the RESOLVE model is solved. The attributes are used to give build and retirement decisions to
    a model run in production simulation mode."""
    operational_capacity: ts.NumericTimeseries | None = Field(
        None, down_method="mean", up_method="ffill", default_freq="YS"
    )
    selected_capacity: float | None = None
    retired_capacity: ts.NumericTimeseries | None = Field(
        None, down_method="mean", up_method="ffill", default_freq="YS"
    )
    cumulative_retired_capacity: ts.NumericTimeseries | None = Field(
        None, down_method="mean", up_method="ffill", default_freq="YS"
    )

    ###################
    # Cost Attributes #
    ###################

    # TODO (skramer 2023-10-26): should these be floats or timeseries?
    #  Current thinking is that for build-related costs, these should be a single value, but operational costs should
    #  be Timeseries

    # TODO: Adjust warning bounds for Plants (these warning bounds are for resources)
    annualized_capital_cost: Annotated[
        float,
        Metadata(
            category=FieldCategory.BUILD,
            units=units.dollar / units.kW_year,
            excel_short_title="Capital Cost",
            warning_bounds=(0, 1_000),
        ),
    ] = Field(default=0)
    annualized_fixed_om_cost: Annotated[
        ts.NumericTimeseries,
        Metadata(
            category=FieldCategory.BUILD,
            units=units.dollar / units.kW_year,
            excel_short_title="Fixed O&M",
            warning_bounds=(0, 100),
        ),
    ] = Field(default_factory=ts.NumericTimeseries.zero, up_method="ffill", down_method="mean", default_freq="YS")

    # TODO 2023-04-30: Maybe timeseries fields should have a "assume_timestamp_is" attribute for now to retain backward compatibility for whether the timestamp column is weather year, model year, or vintage

    ##########################
    # Reliability Attributes #
    ##########################

    stochastic_outage_rate: Annotated[float | None, Metadata(category=FieldCategory.RELIABILITY)] = Field(
        None,
        description="Stochastic forced outage rate",
    )

    mean_time_to_repair: Annotated[float | None, Metadata(category=FieldCategory.RELIABILITY, units=units.hour)] = (
        Field(
            None,
            description="Mean time to repair",
        )
    )

    random_seed: Annotated[int | None, Metadata(category=FieldCategory.RELIABILITY)] = Field(
        None,
        description="Random seed",
    )

    ###########
    # Methods #
    ###########

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def revalidate(self):
        # Check that the Asset is not linked to more than 1 zone
        if self.operational_group is None and len(self.zones) == 0:
            # Only display warning if it doesn't have input/output_zones attrs
            if not getattr(self, "input_zones", None):
                logger.warning(
                    f"`{self.__class__.__name__}` instance `{self.name}` is not linked to a Zone. The Asset may not "
                    f"contribute to dispatch properly if it is not linked to a Zone."
                )
        if len(self.zones) > 1:
            raise AssertionError(
                f"`{self.__class__.__name__}` instance `{self.name}` is linked to more than 1 Zone: "
                f"`{self.zones.keys()}`. Linkage to more than 1 Zone is prohibited."
            )
        if len(self.custom_constraints) > 0 and self.operational_group is not None:
            raise ValueError(
                f"`{self.__class__.__name__}` instance `{self.name}` is assigned to both an operational group and a "
                f"custom constraint. Custom constraints cannot be enforced correctly if the Asset is linked to an "
                f"operational group. Either remove the custom constraint linkage or apply the custom constraint to the "
                f"entire operational group."
            )

        if self.potential is None:
            self.potential = np.inf

        if self.integer_build_increment:
            if self.integer_build_increment > self.potential:
                raise ValueError(f"{self.name}: potential must be greater than integer_build_increment.")
            if ~np.isinf(self.potential) & (self.potential % self.integer_build_increment != 0):
                potential_modeled = (
                    np.floor(self.potential / self.integer_build_increment) * self.integer_build_increment
                )
                logger.warning(
                    f"{self.name}: potential not divisible by integer_build_increment. Input potential {self.potential} cannot be reached; maximum potential due to integer_build_limit is {potential_modeled})"
                )

        for year in self.planned_capacity.data.index:
            if self.planned_capacity.data.loc[year] > self.potential:
                raise ValueError(
                    f"`{self.__class__.__name__}` instance `{self.name}` has a potential of {self.potential}, "
                    f"which is less than the planned capacity of {self.planned_capacity.data.loc[year]} in {year.year}."
                )

        # Check that asset belongs to at most one operational group
        operational_groups = [
            group_linkage.instance_to
            for group_linkage in self.asset_groups.values()
            if group_linkage.instance_to.aggregate_operations
        ]
        if len(operational_groups) > 1:
            raise ValueError(
                f"`{self.__class__.__name__}` instance `{self.name}` is linked to more than 1 operational group"
            )

    @property
    def operational_attributes(self):
        return [
            attr_name
            for attr_name, field_info in self.model_fields.items()
            if self.get_metadata(field_name=attr_name).category in [FieldCategory.OPERATIONS, FieldCategory.RELIABILITY]
            and attr_name not in self.linkage_attributes
            and attr_name not in self.three_way_linkage_attributes
        ]

    @property
    def operational_linkages(self):
        return [
            attr_name
            for attr_name, field_info in self.model_fields.items()
            if self.get_metadata(field_name=attr_name).category in [FieldCategory.OPERATIONS, FieldCategory.RELIABILITY]
            and attr_name in self.linkage_attributes
        ]

    @property
    def non_operational_linkages(self):
        return [
            attr_name
            for attr_name, field_info in self.model_fields.items()
            if self.get_metadata(field_name=attr_name).category
            not in [FieldCategory.OPERATIONS, FieldCategory.RELIABILITY]
            and attr_name in self.linkage_attributes
        ]

    @property
    def operational_three_way_linkages(self):
        return [
            attr_name
            for attr_name, field_info in self.model_fields.items()
            if self.get_metadata(field_name=attr_name).category in [FieldCategory.OPERATIONS, FieldCategory.RELIABILITY]
            and attr_name in self.three_way_linkage_attributes
        ]

    @property
    def policies(self):
        return (
            self.emissions_policies
            | self.annual_energy_policies
            | self.hourly_energy_policies
            | self.prm_policies
            | self.erm_policies
        )

    @property
    def outage_distribution(self):
        if self.outage_distributions is None or len(self.outage_distributions) == 0:
            outage_distribution = None
        else:
            outage_dist_name = list(self.outage_distributions.keys())[0]
            outage_distribution = self.outage_distributions[outage_dist_name].instance_to

        return outage_distribution

    @property
    def operational_group(self) -> Optional["AssetGroup"]:
        operational_groups = [
            group_linkage.instance_to
            for group_linkage in self.asset_groups.values()
            if group_linkage.instance_to.aggregate_operations
        ]
        if len(operational_groups) == 0:
            operational_group = None
        elif len(operational_groups) == 1:
            operational_group = operational_groups[0]
        else:
            raise ValueError(
                f"`{self.__class__.__name__}` instance `{self.name}` is linked to more than 1 operational group"
            )

        return operational_group

    @property
    def has_operational_rules(self) -> bool:
        """Property for whether this asset has operational rules (i.e., it is not a part of an operational group)"""
        if self.operational_group is None:
            return True
        else:
            return False

    @computed_field(title="Operational Group")
    def operational_group_name(self) -> str:
        if self.operational_group is None:
            return "None"
        else:
            return self.operational_group.name

    @computed_field(title="Zone(s)")
    @property
    def zone_names_string(self) -> str:
        """This property concatenates the keys in the zones dictionary for results reporting."""
        if len(self.zones) == 0:
            return "None"
        else:
            return ",".join(map(str, self.zones.keys()))

    @property
    def annual_results_column_order(self):
        """This property defines the ordering of columns in the Asset annual results summary out of Resolve.
        The name of the model field or formulation_block pyomo component can be used.
        """
        return [
            # Topology and grouping
            "zone_names_string",
            "vintage_parent_group",
            "operational_group_name",
            # Investment data
            "selected_capacity",
            "operational_capacity",
            "retired_capacity",
            "planned_capacity",
            "potential",
            # Costs
            "annual_capital_cost",
            "annual_fixed_om_cost",
            "annual_total_investment_cost",
            "annual_total_operational_cost",
            "asset_potential_slack",
            "asset_potential_slack_cost",
            "annual_total_slack_investment_cost",
            "annual_total_slack_operational_cost",
            # Integer Build
            "integer_build",
            "integer_build_increment",
        ]

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict()

        pyomo_components.update(
            # Selected amount of new-build capacity
            selected_capacity=pyo.Var(
                within=pyo.NonNegativeReals,
                doc="Selected Capacity (MW)",
                initialize=0,
            ),
            # Amount of selected capacity that is retired in each year (non-cumulative)
            retired_capacity=pyo.Var(
                model.MODELED_YEARS,
                within=pyo.NonNegativeReals,
                doc="Retired Capacity (MW)",
                initialize=0,
            ),
            asset_potential_slack=pyo.Var(within=pyo.NonNegativeReals, initialize=0, doc="Asset Potential Slack"),
            operational_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._operational_capacity,
                doc="Operational Capacity (MW)",
            ),
            # Force the selected new-build capacity variable to be 0 if the Asset cannot be built new
            # Note: doing `self.formulation_block.selected_capacity.fix(0)` does not work because the value on the decision
            #  variable cannot be fixed before the block is fully constructed, which does not happen until after this
            #  function is called
            can_build_new_constraint=pyo.Constraint(rule=self._can_build_new_constraint),
            potential_constraint=pyo.Constraint(model.MODELED_YEARS, rule=self._potential_constraint),
            retired_capacity_max_constraint=pyo.Constraint(
                model.MODELED_YEARS, rule=self._retired_capacity_max_constraint
            ),
        )

        if self.integer_build_increment:
            pyomo_components.update(
                integer_build=pyo.Var(
                    within=pyo.NonNegativeIntegers,
                    doc="Integer Build Units Selected",
                    initialize=0,
                ),
                integer_build_constraint=pyo.Constraint(rule=self._integer_build_constraint),
            )

        if self.physical_lifetime != 100:
            pyomo_components.update(
                physical_lifetime_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._physical_lifetime_constraint
                )
            )

        if len(self.prm_policies) > 0 or len(self.elcc_surfaces) > 0:
            ##########################
            # PRM Policy Constraints #
            ##########################
            PRM_POLICIES = pyo.Set(initialize=self.prm_policies.keys())
            pyomo_components.update(
                PRM_POLICIES=PRM_POLICIES,
                reliability_capacity=pyo.Var(
                    PRM_POLICIES, model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="Reliability Capacity (MW)"
                ),
                NQC=pyo.Expression(PRM_POLICIES, model.MODELED_YEARS, rule=self._NQC, doc="NQC (MW)"),
                max_reliability_capacity_constraint=pyo.Constraint(
                    PRM_POLICIES, model.MODELED_YEARS, rule=self._max_reliability_capacity_constraint
                ),
                maintain_reliability_capacity_constraint=pyo.Constraint(
                    PRM_POLICIES, model.MODELED_YEARS, rule=self._maintain_reliability_capacity_constraint
                ),
            )

        if self.min_operational_capacity is not None:
            pyomo_components.update(
                min_operational_capacity_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._min_operational_capacity_constraint
                )
            )

        ##########################################
        # Production Simulation Mode Constraints #
        ##########################################
        if model.TYPE == ModelType.RESOLVE and model.production_simulation_mode:
            self.formulation_block.chosen_selected_capacity = pyo.Param(initialize=self.selected_capacity)
            # Chosen retired capacity should include cumulative retired capacity through first modeled year
            # For example, if capacity is retired in 2030 and modeling PCM in 2045, need to count retired capacity to
            #   avoid infeasibilities
            self.formulation_block.chosen_retired_capacity = pyo.Param(
                model.MODELED_YEARS,
                initialize=lambda m, y: (
                    self.cumulative_retired_capacity.data.at[y]
                    if y == min(model.MODELED_YEARS)
                    else self.retired_capacity.data.at[y]
                ),
            )
            self.formulation_block.chosen_operational_capacity = pyo.Param(
                model.MODELED_YEARS, initialize=self.operational_capacity.data.loc[list(model.MODELED_YEARS)]
            )
            pyomo_components.update(
                prod_sim_selected_capacity_constraint=pyo.Constraint(rule=self._prod_sim_selected_capacity_constraint),
                prod_sim_retired_capacity_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._prod_sim_retired_capacity_constraint
                ),
                prod_sim_operational_capacity_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._prod_sim_operational_capacity_constraint
                ),
            )

        if construct_costs:
            pyomo_components.update(
                asset_potential_slack_cost=pyo.Expression(
                    rule=self._asset_potential_slack_cost, doc="Asset Potential Slack Cost ($)"
                ),
                annual_total_slack_investment_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_slack_investment_cost,
                    doc="Annual Total Slack Investment Cost ($)",
                ),
                annual_capital_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._annual_capital_cost, doc="Annual Capital Cost ($)"
                ),
                annual_fixed_om_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._annual_fixed_om_cost, doc="Annual Fixed O&M Cost ($)"
                ),
                annual_total_investment_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._annual_total_investment_cost, doc="Annual Total Investment Cost ($)"
                ),
            )

        return pyomo_components

    def _operational_capacity(self, block, modeled_year: pd.Timestamp):
        """The amount of operational new-build capacity in each year"""
        if modeled_year >= self.build_year:
            operational_capacity = (
                self.planned_capacity.data[modeled_year]
                + self.formulation_block.selected_capacity
                - pyo.quicksum(
                    self.formulation_block.retired_capacity[year]
                    for year in self.formulation_block.model().MODELED_YEARS
                    if year <= modeled_year
                )
            )
        else:
            operational_capacity = 0.0

        return operational_capacity

    def _can_build_new_constraint(self, block: pyo.Block):
        if block.model().TYPE == ModelType.RESOLVE and block.model().production_simulation_mode:
            return pyo.Constraint.Skip
        if not self.can_build_new:
            # selected_capacity and asset_potential_slack are both >= 0, so setting their sum equal to zero
            # constrains both to be equal to zero
            constraint = block.selected_capacity + block.asset_potential_slack == 0
        # Don't allow new capacity if build year is not one of the modeled years
        elif self.build_year not in block.model().MODELED_YEARS:
            constraint = block.selected_capacity + block.asset_potential_slack == 0
        else:
            constraint = pyo.Constraint.Skip

        return constraint

    def _potential_constraint(self, block: pyo.Block, modeled_year):
        """The total amount of planned and new-build capacity cannot exceed the available potential"""
        if self.potential == np.inf:
            constraint = pyo.Constraint.Skip
        else:
            constraint = (
                self.planned_capacity.data[modeled_year]
                + self.formulation_block.selected_capacity
                - self.formulation_block.asset_potential_slack
                <= self.potential
            )

        return constraint

    def _retired_capacity_max_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Upper bound on the amount of retired capacity in each year. Retired capacity in a given year cannot
        exceed the operational capacity in the previous year, and capacity cannot be retired before the build year
        of the Asset."""

        # If the modeled year is earlier than the build year, no capacity can be retired in that year
        if modeled_year < self.build_year:
            constraint = self.formulation_block.retired_capacity[modeled_year] == 0

        # If the resource can't be retired, but it has a physical lifetime, don't allow the Asset to retire until the
        #  end of its physical lifetime
        elif (
            not self.can_retire
            and self.physical_lifetime != 100
            and modeled_year < self.build_year.replace(year=self.build_year.year + self.physical_lifetime)
        ):
            constraint = self.formulation_block.retired_capacity[modeled_year] == 0

        # If the resource can't be retired, and it has no specified physical lifetime, don't allow it to retire ever
        elif not self.can_retire and self.physical_lifetime == 100:
            constraint = self.formulation_block.retired_capacity[modeled_year] == 0

        # If the resource exists before the first modeled year, only the planned capacity can be retired
        elif (modeled_year == self.formulation_block.model().MODELED_YEARS.first()) or (
            modeled_year == self.build_year
        ):
            constraint = (
                self.formulation_block.retired_capacity[modeled_year] <= self.planned_capacity.data[modeled_year]
            )

        # Otherwise, the Asset cannot retire more capacity than was online in the previous modeled year
        else:
            constraint = (
                self.formulation_block.retired_capacity[modeled_year]
                <= self.formulation_block.operational_capacity[
                    self.formulation_block.model().MODELED_YEARS.prev(modeled_year)
                ]
            )

        return constraint

    def _physical_lifetime_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """The Asset must be retired after the end of its physical lifetime"""
        if (
            self.physical_lifetime != 100
            and self.build_year.replace(year=self.build_year.year + self.physical_lifetime) <= modeled_year
        ):
            constraint = self.formulation_block.operational_capacity[modeled_year] == 0
        else:
            constraint = pyo.Constraint.Skip

        return constraint

    def _integer_build_constraint(self, block: pyo.Block):
        """
        If `integer_build_increment` is not None, only allow selected capacity to be selected in that increment.
        For example, if `integer_build_increment` is 5, the model will only select this asset in increments of
        5,10,15, etc. If you want to force an "all or nothing" decision, set the `integer_build_increment`
        equal to `potential`
        """
        return block.selected_capacity == block.integer_build * self.integer_build_increment

    def _annual_capital_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Capital costs for the Asset in each year. Capital costs are only incurred for selected new-build
        capacity, not for planned capacity. Capital Costs are not incurred overnight in the build year of the
        Asset, but are incurred annually over the course of its financial lifetime. This term represents the
        costs incurred in a single year, and it is not discounted (i.e. it is not multiplied by the discount
        factor for the relevant model year)."""
        if (
            self.build_year
            <= modeled_year
            < self.build_year.replace(year=self.build_year.year + self.physical_lifetime)
        ):
            # TODO (skramer): should planned capacity incur a capital cost or no?
            investment_cost = self.annualized_capital_cost * 1e3 * self.formulation_block.selected_capacity
        else:
            investment_cost = 0.0

        return investment_cost

    def _annual_fixed_om_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Fixed O&M costs of capacity for the Asset in each year. Fixed O&M costs are incurred for both selected
        new-build capacity and for planned capacity. This term represents the costs incurred in a single year, and
        it is not discounted (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        fixed_om_cost = (
            self.annualized_fixed_om_cost.data.at[modeled_year]
            * 1e3
            * self.formulation_block.operational_capacity[modeled_year]
        )

        return fixed_om_cost

    def _asset_potential_slack_cost(self, block: pyo.Block):
        return self.formulation_block.asset_potential_slack * _ASSET_POTENTIAL_SLACK_PENALTY

    def _annual_total_slack_investment_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        if modeled_year == self.build_year:
            return self.formulation_block.asset_potential_slack_cost
        else:
            return 0

    def _annual_total_investment_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Total investment costs (capital and fixed O&M) for the Asset in each year. This term represents the costs
        incurred in a single year, and it is not discounted (i.e. it is not multiplied by the discount factor for
        the relevant model year)."""
        total_investment_cost = (
            block.annual_capital_cost[modeled_year]
            + block.annual_fixed_om_cost[modeled_year]
            + block.annual_total_slack_investment_cost[modeled_year]
        )

        return total_investment_cost

    def _max_reliability_capacity_constraint(self, block: pyo.Block, _policy: str, modeled_year: pd.Timestamp):
        """The maximum amount of capacity value (in MW) that an asset can provide"""
        if not self.prm_policies[_policy].fully_deliverable:
            return block.reliability_capacity[_policy, modeled_year] <= block.operational_capacity[modeled_year]
        else:
            return block.reliability_capacity[_policy, modeled_year] == block.operational_capacity[modeled_year]

    def _maintain_reliability_capacity_constraint(self, block: pyo.Block, _policy: str, modeled_year: pd.Timestamp):
        """The reliability capacity should not change year-on-year, other than if capacity is retired, or more is planned."""
        if (
            self.prm_policies[_policy].fully_deliverable
            or modeled_year == block.model().MODELED_YEARS.last()
            or self.build_year > modeled_year
        ):
            return pyo.Constraint.Skip
        else:
            return (
                block.reliability_capacity[_policy, modeled_year]
                == block.reliability_capacity[_policy, block.model().MODELED_YEARS.next(modeled_year)]
                - block.retired_capacity[modeled_year]
                - self.planned_capacity.data.at[block.model().MODELED_YEARS.next(modeled_year)]
                + self.planned_capacity.data.at[modeled_year]
            )

    def _NQC(self, block: pyo.Block, _policy: str, modeled_year: pd.Timestamp):
        if (
            _policy not in self.prm_policies or self.prm_policies[_policy].multiplier is None
        ):  # Return zero if this asset uses an ELCC
            return 0
        else:
            return (
                self.prm_policies[_policy].multiplier.data.at[modeled_year]
                * block.reliability_capacity[_policy, modeled_year]
            )

    def _min_operational_capacity_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """The total amount of operational capacity must exceed the minimum operational capacity"""

        constraint = (
            self.formulation_block.operational_capacity[modeled_year]
            >= self.min_operational_capacity.data.at[modeled_year]
        )

        return constraint

    def _prod_sim_selected_capacity_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """In production simulation mode, selected capacity is constrained to the capacity selected in the
        original capacity expansion problem."""
        return block.selected_capacity == block.chosen_selected_capacity

    def _prod_sim_retired_capacity_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """In production simulation mode, retirement decisions are constrained to the retirement decisions of the
        original capacity expansion problem."""
        return block.retired_capacity[modeled_year] == block.chosen_retired_capacity[modeled_year]

    def _prod_sim_operational_capacity_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """In production simulation mode, operational capacities are constrained to those of the original
        capacity expansion problem."""
        return block.operational_capacity[modeled_year] == block.chosen_operational_capacity[modeled_year]

    def check_operational_linkages_are_equal(self, other: "Asset") -> bool:
        """Checks whether two Assets have equivalent "operational linkages."

        In order for two Assets to be "operationally equivalent," one condition is that any linkages which may impact
         the operational decisions of the resource must also be equal. For example, if a Resource is linked to an
        AnnualEmissionsStandard, then its dispatch will be partially influenced by this emissions target, so the other
        Resource must also be linked to that policy.

        Args:
            other: the other Asset to compare against

        Returns:
            equal: whether or not the two components have equivalent operational linkages
        """
        # If the two resources do not have equivalent sets of operational linkage fields, they cannot be equal
        if set(self.operational_linkages) != set(other.operational_linkages) or set(
            self.operational_three_way_linkages
        ) != set(other.operational_three_way_linkages):
            equal = False
        else:
            # Set value temporarily to True, and if any linkages are not equal, it will be changed to False
            equal = True

            for linkage_attr_name in self.operational_linkages:
                # Check that there are no linkages that are present on one Asset but not the other
                equal = getattr(self, linkage_attr_name).keys() == getattr(other, linkage_attr_name).keys()
                if not equal:
                    return equal
                # Check that both `self` and `other` are linked to the same object
                for linkage_name, linkage_instance in getattr(self, linkage_attr_name).items():
                    if linkage_instance.instance_from is self:
                        self_linked_component = linkage_instance.instance_to
                        other_linked_component = getattr(other, linkage_attr_name)[linkage_name].instance_to
                    elif linkage_instance.instance_to is self:
                        self_linked_component = linkage_instance.instance_from
                        other_linked_component = getattr(other, linkage_attr_name)[linkage_name].instance_from
                    else:
                        raise ValueError(
                            f"When checking linkage equality, instance `{self.name}` was not found in linkage `{linkage_instance.name}`"
                        )
                    equal = self_linked_component is other_linked_component
                    if not equal:
                        return equal
            for three_way_linkage_attr_name in self.operational_three_way_linkages:
                # Check that there are no linkages that are present on one Resource but not the other
                equal = (
                    getattr(self, three_way_linkage_attr_name).keys()
                    == getattr(other, three_way_linkage_attr_name).keys()
                )
                if not equal:
                    return equal
                # Check that both `self` and `other` are linked to the same objects
                for three_way_linkage_name, three_way_linkage_instance in getattr(
                    self, three_way_linkage_attr_name
                ).items():
                    if three_way_linkage_instance.instance_1 is self:
                        self_linked_component_1 = three_way_linkage_instance.instance_2
                        other_linked_component_1 = getattr(other, three_way_linkage_attr_name)[
                            three_way_linkage_name
                        ].instance_2
                        self_linked_component_2 = three_way_linkage_instance.instance_3
                        other_linked_component_2 = getattr(other, three_way_linkage_attr_name)[
                            three_way_linkage_name
                        ].instance_3
                    elif three_way_linkage_instance.instance_2 is self:
                        self_linked_component_1 = three_way_linkage_instance.instance_1
                        other_linked_component_1 = getattr(other, three_way_linkage_attr_name)[
                            three_way_linkage_name
                        ].instance_1
                        self_linked_component_2 = three_way_linkage_instance.instance_3
                        other_linked_component_2 = getattr(other, three_way_linkage_attr_name)[
                            three_way_linkage_name
                        ].instance_3
                    elif three_way_linkage_instance.instance_3 is self:
                        self_linked_component_1 = three_way_linkage_instance.instance_1
                        other_linked_component_1 = getattr(other, three_way_linkage_attr_name)[
                            three_way_linkage_name
                        ].instance_1
                        self_linked_component_2 = three_way_linkage_instance.instance_2
                        other_linked_component_2 = getattr(other, three_way_linkage_attr_name)[
                            three_way_linkage_name
                        ].instance_2
                    else:
                        raise ValueError(
                            f"When checking linkage equality, instance `{self.name}` was not found in linkage `{three_way_linkage_instance.name}`"
                        )
                    equal = (
                        self_linked_component_1 is other_linked_component_1
                        and self_linked_component_2 is other_linked_component_2
                    )
                    if not equal:
                        return equal

        return equal

    def check_if_operationally_equal(
        self, other: "Asset", check_linkages: bool = True, fields_to_check: Optional[list[str]] = None
    ) -> bool:
        """Check is this Asset is "operationally equivalent" to another Asset.

        This check is used when automatically grouping resources together in RESOLVE for the construction of operational
        constraints. See `AssetGroup` for more information.

        Operational equivalence is defined by two categories. First, all the "operational attributes" of the Assets
        (which are defined in a class variable) must be equal. Any attribute whose value may impact the optimal
        operational decisions for the assets have to be equal. For example, they must have equal `power_output_max`
        profiles, among other things. Second, they must have equivalent "operational linkages" - see
        `check_operational_linkages_are_equal` for more information.

        Args:
            other: the Resource to compare to
            check_linkages: whether linkages should be considered in determining operational equality
            fields_to_check: an optional list of a subset of fields to check

        Returns:
            bool: whether the two Resources are operationally equal
        """
        if fields_to_check is not None:
            equal = set(fields_to_check).issubset(set(self.operational_attributes)) and set(fields_to_check).issubset(
                other.operational_attributes
            )
        else:
            equal = set(self.operational_attributes) == set(other.operational_attributes)

        if equal:
            # Check that all operational attributes are equal - if any are not equal, then the assets are not equal
            if fields_to_check is None:
                fields_to_check = self.operational_attributes
            for attr in fields_to_check:
                if getattr(self, attr) != getattr(other, attr):
                    equal = False
                    break

        # check that all operational linkages are equal
        if equal:
            equal = equal and self.check_operational_linkages_are_equal(other)

        return equal

    def save_operational_capacity(self):
        """Save the resulting operational capacity after the RESOLVE model has been solved."""
        model_years = self.formulation_block.operational_capacity.extract_values().keys()
        capacities = self.formulation_block.operational_capacity[:].expr()
        self.operational_capacity = ts.NumericTimeseries(
            name="operational_capacity", data=pd.Series(index=model_years, data=capacities)
        )

    def save_selected_capacity(self):
        """Save the resulting selected capacity after the RESOLVE model has been solved."""
        self.selected_capacity = self.formulation_block.selected_capacity.value

    def save_retired_capacity(self):
        """Save the resulting retired capacity after the RESOLVE model has been solved."""
        model_years = self.formulation_block.retired_capacity.extract_values().keys()
        retirements = list(self.formulation_block.retired_capacity.extract_values().values())
        self.retired_capacity = ts.NumericTimeseries(
            name="retired_capacity", data=pd.Series(index=model_years, data=retirements)
        )

    def save_cumulative_retired_capacity(self):
        """Save the resulting retired capacity after the RESOLVE model has been solved."""
        model_years = self.formulation_block.retired_capacity.extract_values().keys()
        cumulative_retirements = list(
            itertools.accumulate(self.formulation_block.retired_capacity.extract_values().values())
        )
        self.cumulative_retired_capacity = ts.NumericTimeseries(
            name="cumulative_retired_capacity", data=pd.Series(index=model_years, data=cumulative_retirements)
        )

    def save_capacity_expansion_results(self):
        self.save_operational_capacity()
        self.save_selected_capacity()
        self.save_retired_capacity()
        self.save_cumulative_retired_capacity()


AnyOperationalGroup = TypeVar("AnyOperationalGroup", bound="GenericResourceOperationalGroup")
AnyResource = TypeVar("AnyResource", bound="GenericResource")


def _set_to_none(v: Any):
    """TODO: Improve this inheritance structure. Shouldn't have to use this method for build_year."""
    return None


class AssetGroup(Asset):
    """AssetGroup combines multiple vintages of Assets, since Resolve and Recap treat these differently.

    For Resolve, separate vintages
    For Recap, combine vintages
    """

    SAVE_PATH: ClassVar[str] = "assets/groups"

    # Naming prefix used to name instances when operational groups are created automatically
    _NAME_PREFIX: ClassVar[str] = "asset_group"

    _GROUPING_CLASS: ClassVar[Type[Component]] = Asset

    ############
    # Linkages #
    ############
    assets: Annotated[dict[str, linkage.AssetToAssetGroup], Metadata(linkage_order="from")] = Field(
        default_factory=dict
    )

    #################################
    # Build & Retirement Attributes #
    #################################

    # Force certain build attributes that are inherited from parent class but not applicable to groups to be None
    # TODO: will these still show up in auto-generated docs? if so, figure out another solution to this issue. Probably
    #  involves a more complicated inheritance pattern
    build_year: Annotated[None, BeforeValidator(_set_to_none)] = None
    annualized_capital_cost: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero, up_method="ffill", down_method="mean", default_freq="YS"
    )
    annualized_fixed_om_cost: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero, up_method="ffill", down_method="mean", default_freq="YS"
    )
    vintages_to_construct: ts.BooleanTimeseries = pydantic.Field(
        default_factory=lambda: ts.BooleanTimeseries.default_factory(value=False),
        up_method="ffill",
        down_method="first",
        default_freq="YS",
    )
    potential: Annotated[ts.NumericTimeseries | None, Metadata(units=units.MW, show_year_headers=False)] = Field(
        default=None,
        default_freq="YS",
        weather_year=False,
        up_method="interpolate",
        down_method="mean",
        description="Build potential for planned and selected capacity by model year across all assets in the group",
        title="Potential (MW)",
    )
    cumulative_potential: Annotated[ts.NumericTimeseries | None, Metadata(units=units.MW, show_year_headers=False)] = (
        Field(
            default=None,
            default_freq="YS",
            weather_year=False,
            up_method="interpolate",
            down_method="mean",
            description="Cumulative build potential for planned and selected capacity by model year across all assets in the group",
            title="Cumulative Build Potential (MW)",
        )
    )
    min_cumulative_new_build: Annotated[ts.NumericTimeseries | None, Metadata(units=units.MW)] = Field(
        default=None,
        default_freq="YS",
        weather_year=False,
        up_method="interpolate",
        down_method="mean",
        description="Cumulative minimum required selected capacity by model year across all assets in the group",
        title="Cumulative Min New Build (MW)",
    )

    ##########################
    # Operational Attributes #
    ##########################
    aggregate_operations: bool = Field(
        default=False,
        description=(
            "Whether to enforce operational constraints across all assets in the group as if they were a single asset. "
            "This is only possible if all assets in the group are operationally equivalent to one another."
        ),
        title="Aggregate Operations",
    )

    @property
    def has_operational_rules(self) -> bool:
        """Redefine has_operational_rules property based on aggregate_options attribute"""
        return self.aggregate_operations

    @property
    def asset_instances(self) -> dict[str, Asset]:
        """Returns a dictionary of all Asset instances linked to the group. These can be Assets or other AssetGroups."""
        return {asset_linkage.instance_from.name: asset_linkage.instance_from for asset_linkage in self.assets.values()}

    @property
    def operational_assets(self):
        """For operational decisions, whether we use an Asset or AssetGroup depends on whether AssetGroup has `aggregate_operations==True`."""
        # TODO: Check this property
        assets_in_operational_groups = set()
        for v in self.asset_instances.values():
            if isinstance(v, AssetGroup) and v.aggregate_operations:
                assets_in_operational_groups |= set(v.assets)

        assets_for_operations = {
            k: v
            for k, v in self.asset_instances.items()
            if not isinstance(v, AssetGroup) and v not in assets_in_operational_groups
        }

        return assets_for_operations

    @property
    def build_assets(self):
        """For build decisions, always use the individual asset instances. This is a recursive property that gets the
        Assets directly linked to this AssetGroup plus any Assets linked to AssetGroups linked to this AssetGroup."""
        # TODO: This recursion breaks if a group contains only itself as a member asset (with the same name)
        build_assets = self.directly_linked_build_assets
        for k, v in self.asset_instances.items():
            if isinstance(v, AssetGroup):
                build_assets |= v.build_assets

        return build_assets

    @property
    def directly_linked_build_assets(self):
        """For build decisions, always use the individual asset instances."""
        return {k: v for k, v in self.asset_instances.items() if not isinstance(v, AssetGroup)}

    @property
    def earliest_build_year(self):
        return min(asset.build_year for asset in self.build_assets.values())

    @property
    def annual_results_column_order(self):
        return [
            "zone_names_string",
            "aggregate_operations",
            "selected_capacity",
            "cumulative_selected_capacity",
            "operational_capacity",
            "cumulative_retired_capacity",
            "cumulative_potential",
            "planned_capacity",
            "aggregate_operations",
            "annual_total_operational_cost",
        ]


    @classmethod
    def _construct_operational_group_from_asset_list(cls, name: str, assets: list[Asset]):
        """Constructs an AssetGroup instance based on a list of Assets.

        This method is intended to be used when creating operational groups automatically for a System, and the resulting
        AssetGroup instance will inherit some of its attributes from the Assets that are being used to create it. This
        behavior would not be appropriate for a group that is used only for aggregate investment decisions.

        Args:
            name: name to assign to the resulting AssetGroup instance
            assets: the list of assets to use in construction

        Returns:

        """
        # Copy the attributes of one of the assets in the group as a placeholder and give it a new name
        init_kwargs = assets[0].model_dump()
        init_kwargs["name"] = name

        # Remove all attributes from the placeholder resource that should be None, based on the definition of the group
        # Note: Pydantic does not allow overriding a non-optional attribute from a parent class and forcing it to None.
        #  It will instead try to coerce the value to whatever type is required by the parent. Instead, passing no
        #  init argument results in the default value being used, which does successfully override the parent.
        for attr_name, field_info in cls.model_fields.items():
            if field_info.annotation is type(None) or attr_name in assets[0].non_operational_linkages:
                init_kwargs.pop(attr_name)
            # Remove potential and annualized costs (these are not timeseries on grouops and not needed for operational decisions)
            if attr_name == "potential" or attr_name.startswith("annualized_"):
                init_kwargs.pop(attr_name)

        # Create the group instance
        inst = cls(aggregate_operations=True, **init_kwargs)

        # Create linkages to link the Asset instances to the group
        for asset in assets:
            curr_linkage = linkage.AssetToAssetGroup(name=(asset.name, name), instance_from=asset, instance_to=inst)
            curr_linkage.announce_linkage_to_instances()

        # Create operational linkages for the group instance based on the placeholder
        for linkage_attr_name in assets[0].operational_linkages:
            for linkage_instance in getattr(assets[0], linkage_attr_name).values():
                if linkage_instance.instance_from is assets[0]:
                    instance_type = "instance_from"
                else:
                    instance_type = "instance_to"
                curr_linkage = linkage_instance.copy()
                curr_linkage.name = (
                    (name, linkage_instance.instance_to.name)
                    if instance_type == "instance_from"
                    else (linkage_instance.instance_from.name, name)
                )

                # Assign the instance from and instance to for the linkage.
                # Note: similar to the problem described above, the required type for `instance_from` and `instance_to`
                #  is Component, so if these arguments are passed to the __init__ method of the linkage, they are
                #  coerced to Components, and not their appropriate subclasses. Assigning them after instantiation
                #  avoids this issue.
                curr_linkage.instance_from = (
                    inst if instance_type == "instance_from" else linkage_instance.instance_from
                )
                curr_linkage.instance_to = inst if instance_type == "instance_to" else linkage_instance.instance_to
                curr_linkage.announce_linkage_to_instances()

        # Create operational linkages for the group instance based on the placeholder
        for three_way_linkage_attr_name in assets[0].operational_three_way_linkages:
            for three_way_linkage_instance in getattr(assets[0], three_way_linkage_attr_name).values():
                curr_three_way_linkage = three_way_linkage_instance.copy()
                if three_way_linkage_instance.instance_1 is assets[0]:
                    curr_three_way_linkage.name[0] = name
                    curr_three_way_linkage.instance_1 = inst
                elif three_way_linkage_instance.instance_2 is assets[0]:
                    curr_three_way_linkage.name[1] = name
                    curr_three_way_linkage.instance_2 = inst
                elif three_way_linkage_instance.instance_3 is assets[0]:
                    curr_three_way_linkage.name[2] = name
                    curr_three_way_linkage.instance_3 = inst
                else:
                    raise ValueError("Could not create linkage for operational group automatically")

                curr_three_way_linkage.announce_linkage_to_instances()

        inst.revalidate()

        return inst

    @classmethod
    def construct_operational_groups(
        cls, assets: list[Asset], skip_single_member_groups: bool = False
    ) -> tuple[dict[str, AnyOperationalGroup], dict[str, AnyResource]]:
        """Takes a list of resources of the same type and returns a list of OperationalGroup objects containing the
        assets which are operationally equivalent to one another.

        If `skip_single_member_groups` is True, any group that would have only one Asset in it is not created, and
        a dictionary of these resources will be returned along with a dictionary of OperationalGroup objects. If
        `skip_single_member_groups` is False, an empty dictionary will be returned along with the OperationalGroups.

        Args:
            assets: the list of Resources to create the groups from
            skip_single_member_groups: whether to skip the creation of groups that would only have a single member

        Returns:
            asset_groups: a dictionary of constructed AssetGroup instances
            single_member_assets: if `skip_single_member_groups` is True, a dictionary of all Assets that were not
                assigned to a group
        """
        # Create the first group containing the first instance in the list
        groups = [[assets[0]]]

        # For each asset, check if it is operationally equivalent to any of the existing groups. If so, add it to
        #  the group that it matches, and if not, create a new group for it.
        for curr_asset in assets[1:]:
            added_to_group = False
            for group in groups:
                if curr_asset.check_if_operationally_equal(group[0]):
                    group.append(curr_asset)
                    added_to_group = True
                    break
            if not added_to_group:
                groups.append([curr_asset])

        # Create the OperationalGroup object for each group of assets
        if skip_single_member_groups:
            single_member_assets = {
                resource.name: resource for group in groups for resource in group if len(group) == 1
            }
            asset_groups = {
                f"{cls._NAME_PREFIX}_{i}": cls._construct_operational_group_from_asset_list(
                    name=f"{cls._NAME_PREFIX}_{i}", assets=group
                )
                for i, group in enumerate(groups)
                if len(group) > 1
            }
        else:
            single_member_assets = dict()
            asset_groups = {
                f"{cls._NAME_PREFIX}_{i}": cls._construct_operational_group_from_asset_list(
                    name=f"{cls._NAME_PREFIX}_{i}", assets=group
                )
                for i, group in enumerate(groups)
            }

        return asset_groups, single_member_assets

    def revalidate(self):
        # Ensure that all linked Assets are of the expected type (e.g. a StorageResourceGroup should only contain
        #  StorageResources)
        linked_assets_incorrect_type = [
            asset for asset in self.asset_instances.values() if not isinstance(asset, self._GROUPING_CLASS)
        ]
        if len(linked_assets_incorrect_type) > 0:
            raise ValueError(
                f"The following Components that were linked to the `{self.__class__.__name__}` instance `{self.name}` "
                f"were not instances of the allowed type `{self._GROUPING_CLASS}`: `{linked_assets_incorrect_type}`"
            )

        # Raise a warning if there are no assets in the group
        if len(self.assets) == 0:
            logger.warning(f"`{self.__class__.__name__}` instance `{self.name}` has no linked Assets")

        # Validate that all linked Assets can be safely aggregated for operations
        if self.aggregate_operations:
            operational_attributes_set_by_user = {}
            operational_linkages_set_by_user = {}

            for asset in self.asset_instances.values():
                # Check that the Asset has the same set of operational attributes and linkages as the group
                for operational_set in [
                    "operational_attributes",
                    "operational_linkages",
                    "operational_three_way_linkages",
                ]:
                    if set(getattr(asset, operational_set)) != set(getattr(self, operational_set)):
                        raise ValueError(
                            f" {asset.__class__.__name__} instance `{asset.name}` has `{operational_set}` that are "
                            f"different from its assigned operational group `{self.name}`"
                        )

                # Validate that all assets in the group do not have their own operational attributes defined
                curr_asset_op_attr_set = [
                    attr
                    for attr in asset.operational_attributes
                    if attr in asset.model_fields_set and getattr(self, attr) != getattr(asset, attr)
                ]
                # Append detected errors to a dictionary and so they can be raised at once for all linked assets
                if len(curr_asset_op_attr_set) > 0:
                    operational_attributes_set_by_user[asset.name] = curr_asset_op_attr_set

                # Validate that all assets in the group do not have their own operational linkages defined
                if not self.check_operational_linkages_are_equal(asset):
                    curr_asset_op_linkages_set = [
                        linkage_attr
                        for linkage_attr in asset.operational_linkages + asset.operational_three_way_linkages
                        if len(getattr(asset, linkage_attr)) > 0
                    ]
                    if len(curr_asset_op_linkages_set) > 0:
                        operational_linkages_set_by_user[asset.name] = {
                            linkage_attr: list(getattr(asset, linkage_attr).keys())
                            for linkage_attr in sorted(
                                set(asset.operational_linkages + asset.operational_three_way_linkages)
                            )
                        }

            if len(operational_attributes_set_by_user) > 0:
                raise ValueError(
                    f"Assets assigned to operational group `{self.name}` were instantiated with data for their "
                    f"operational attributes that do not match the group. Remove input data for the following fields:\n"
                    f"`{pprint.pformat(operational_attributes_set_by_user)}`"
                )

            if len(operational_linkages_set_by_user) > 0:
                self_linkages = {
                    linkage_attr: list(getattr(self, linkage_attr).keys())
                    for linkage_attr in sorted(set(self.operational_linkages + self.operational_three_way_linkages))
                }
                raise ValueError(
                    f"Assets assigned to operational group `{self.name}` were instantiated with linkages that impact "
                    f"their operational decision which did not match its assigned group. Remove input data for the "
                    f"following linkage fields: \n`{pprint.pformat(operational_linkages_set_by_user)}`"
                    f"\n The operational group had the following linkages assigned: \n `{pprint.pformat(self_linkages)}`"
                )

            # TODO: After it's been confirmed that all operational linkages are identical, remove the linkages from the underlying assets

        # Check that the AssetGroup is not linked to more than 1 zone
        if self.aggregate_operations and len(self.zones) == 0:
            logger.warning(
                f"`{self.__class__.__name__}` instance `{self.name}` is not linked to a Zone. The Asset may not "
                f"contribute to dispatch properly if it is not linked to a Zone."
            )
        if len(self.zones) > 1 and self.__class__.__name__ != "TxPathGroup":
            raise AssertionError(
                f"`{self.__class__.__name__}` instance `{self.name}` is linked to more than 1 Zone: "
                f"`{self.zones.keys()}`. Linkage to more than 1 Zone is prohibited."
            )

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict()
        ASSETS = pyo.Set(initialize=list(self.asset_instances.keys()))  # TODO: Does this set do anything?
        pyomo_components.update(
            ASSETS=ASSETS,
            # Operational Capacity of AssetGroups are defined as variables to avoid
            # the writing on member asset build decisions within operational constraints
            operational_capacity=pyo.Var(
                model.MODELED_YEARS,
                doc="Operational Capacity (MW)",
            ),
            group_operational_capacity_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                rule=self._operational_capacity,
            ),
            cumulative_selected_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._cumulative_selected_capacity,
                doc="Cumulative Selected Capacity (MW)",
            ),
            selected_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._selected_capacity,
                doc="Selected Capacity (MW)",
            ),
            retired_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._retired_capacity,
                doc="Retired Capacity (MW)",
            ),
            cumulative_retired_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._cumulative_retired_capacity,
                doc="Cumulative Retired Capacity (MW)",
            ),
        )

        # TODO: single-year "potential" on AssetGroup currently does not do anything. Only cumulative potential constrains.
        if self.cumulative_potential is not None:
            pyomo_components.update(
                potential_constraint=pyo.Constraint(model.MODELED_YEARS, rule=self._potential_constraint)
            )
        if self.min_cumulative_new_build is not None:
            pyomo_components.update(
                min_cumulative_new_build_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._min_cumulative_new_build_constraint
                )
            )
        if self.min_operational_capacity is not None:
            pyomo_components.update(
                min_operational_capacity_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._min_operational_capacity_constraint
                )
            )

        if construct_costs:
            pyomo_components.update(
                annual_total_investment_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=0, doc="Annual Total Investment Cost ($)"
                )
            )

        return pyomo_components

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        if self.aggregate_operations:
            if construct_costs:
                # Set the operational costs for each individual asset to be 0
                # Note: this is done because the operational decisions, and associated costs, are modeled for the block
                #  as a whole, and we don't want to double-count operational costs. After the model is solved, the
                #  resources will be updated with their respective fractions of the dispatch and costs.
                for asset in self.asset_instances.values():
                    asset.formulation_block.annual_total_operational_cost = pyo.Expression(
                        model.MODELED_YEARS, rule=0, doc="Annual Total Operational Cost ($)"
                    )

            pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)
        else:
            pyomo_components = LastUpdatedOrderedDict(
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=0, doc="Annual Total Operational Cost ($)"
                )
            )

        return pyomo_components

    def _operational_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the operational capacity of the group in each year as the sum of operational capacity of all linked
        Assets."""
        return (
            pyo.quicksum(
                asset.formulation_block.operational_capacity[modeled_year] for asset in self.build_assets.values()
            )
            == block.operational_capacity[modeled_year]
        )

    def _cumulative_selected_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the cumulative capacity built in the current and previous modeled year(s) for all linked Assets."""
        return pyo.quicksum(
            +asset.formulation_block.selected_capacity
            for asset in self.build_assets.values()
            if asset.build_year <= modeled_year
        )

    def _selected_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the capacity built in each modeled year for all linked Assets."""
        model = block.model()
        sorted_years = sorted(model.MODELED_YEARS)
        year_index = sorted_years.index(modeled_year)
        if year_index == 0:
            return self.formulation_block.cumulative_selected_capacity[modeled_year]
        else:
            prev_modeled_year = sorted_years[year_index - 1]
            return (
                self.formulation_block.cumulative_selected_capacity[modeled_year]
                - self.formulation_block.cumulative_selected_capacity[prev_modeled_year]
            )

    def _retired_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the retired capacity of the group in each year as the sum of retired capacities of all linked
        Assets."""
        return pyo.quicksum(
            asset.formulation_block.retired_capacity[modeled_year] for asset in self.build_assets.values()
        )

    def _cumulative_retired_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the cumulative retired capacity in the current and previous modeled year(s) for all linked Assets."""
        model = block.model()
        sorted_years = sorted(model.MODELED_YEARS)
        year_index = sorted_years.index(modeled_year)
        if year_index == 0:
            return self.formulation_block.retired_capacity[modeled_year]
        else:
            prev_modeled_year = sorted_years[year_index - 1]
            return (
                self.formulation_block.retired_capacity[modeled_year]
                + self.formulation_block.cumulative_retired_capacity[prev_modeled_year]
            )

    def _potential_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """The total amount of planned and new-build capacity cannot exceed the available potential"""
        if len([asset for asset in self.build_assets.values() if asset.build_year <= modeled_year]) == 0:
            return pyo.Constraint.Skip

        return (
            pyo.quicksum(
                asset.planned_capacity.data[modeled_year]
                + asset.formulation_block.selected_capacity
                - asset.formulation_block.asset_potential_slack
                for asset in self.build_assets.values()
                if asset.build_year <= modeled_year
            )
            <= self.cumulative_potential.data.at[modeled_year]
        )

    def _min_cumulative_new_build_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """The total amount of selected capacity must exceed the minimum cumulative new build required"""
        if self.min_cumulative_new_build.data.at[modeled_year] == 0:
            return pyo.Constraint.Skip
        else:
            constraint = (
                pyo.quicksum(
                    asset.formulation_block.selected_capacity
                    for asset in self.build_assets.values()
                    if asset.build_year <= modeled_year
                )
                >= self.min_cumulative_new_build.data.at[modeled_year]
            )
            return constraint

    def _update_assets_with_operational_attributes_and_linkages(self):
        """Assign values to operational attributes and construct linkages that govern operational decisions on all
        Resources that are linked to the group.

        This method is only used if the group is set to perform aggregated operational decisions.
        """
        for asset in self.asset_instances.values():
            # Update resource's operational attributes to match the group
            for attr in self.operational_attributes:
                setattr(asset, attr, getattr(self, attr))

            # Update resource's operational linkages to match the group
            for linkage_attr in self.operational_linkages:
                for linkage_instance in getattr(self, linkage_attr).values():
                    linkage_copy = linkage_instance.copy()
                    if linkage_copy.instance_from is self:
                        linkage_copy.instance_from = asset
                        linkage_copy.name = (asset.name, linkage_copy.instance_to.name)
                    elif linkage_copy.instance_to is self:
                        linkage_copy.instance_to = asset
                        linkage_copy.name = (linkage_copy.instance_from.name, asset.name)
                    else:
                        raise ValueError(
                            f"When copying Linkage `{linkage_instance}` in resource group `{self.name}`, the resource "
                            f"group was not found in `instance_from` or `instance_to` of the linkage."
                        )
                    linkage_copy.announce_linkage_to_instances()

    def update_assets_with_results(self):
        # TODO: Check if this should sum over asset_instances or build_assets
        """Allocates optimization model results to the linked Assets based on the fraction of total operational capacity
        in each modeled year that is represented by each asset.
        """

        if self.aggregate_operations:
            # Construct linkages and assign values to operations-related attributes on the linked Resources
            # Note: these attributes and linkages will be used in the construction of decision variables, expressions,
            #  and constraints below
            self._update_assets_with_operational_attributes_and_linkages()

            for asset in self.asset_instances.values():
                # Construct the operational decision variables, expressions, and constraints
                # Note: because operations were aggregated, the pyomo components for each individual resource were never
                #  constructed, so in order to calculate resource-level results properly, the pyomo components must be
                #  constructed first.
                asset.formulation_block.del_component("annual_total_operational_cost")
                asset.construct_operational_rules(
                    model=self.formulation_block.model(), construct_costs=self.formulation_block.model().construct_costs
                )

        # TODO: are there any decision variables on the group if it's not an operational group?
        # Iterate over all decision variables on the group instance
        for self_variable in self.formulation_block.component_objects(ctype=pyo.Var):
            # Iterate over all linked assets
            for asset in self.asset_instances.values():
                # Fix the values of the corresponding decision variables on the asset based on the proportion of the
                #  total operational capacity of the group in that year
                child_variable = getattr(asset.formulation_block, self_variable.local_name)
                for index in self_variable.keys():
                    modeled_year = index[get_index_labels(self_variable).index("MODELED_YEARS")]
                    if pyo.value(self.formulation_block.operational_capacity[modeled_year]) == 0:
                        child_variable[index].fix(0)
                    else:
                        child_variable[index].fix(
                            pyo.value(self_variable[index])
                            / self.formulation_block.operational_capacity[modeled_year]
                            * asset.formulation_block.operational_capacity[modeled_year]
                        )
