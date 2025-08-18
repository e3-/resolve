from typing import Annotated
from typing import ClassVar
from typing import Dict
from typing import Optional
from typing import Tuple
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pydantic import computed_field
from pydantic import Field
from pydantic import model_validator
from pyomo.environ import RangeSet
from typing_extensions import Annotated

from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import ModelType
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.core.temporal.timeseries import TimeseriesType
from new_modeling_toolkit.system.asset import Asset
from new_modeling_toolkit.system.asset import AssetGroup
from new_modeling_toolkit.system.electric.reserve import ReserveDirection
from new_modeling_toolkit.system.electric.resource_group import ResourceGroup
from new_modeling_toolkit.system.outage_distribution import OutageDistribution


if TYPE_CHECKING:
    from new_modeling_toolkit.core.model import ModelTemplate


# Hard-code tolerance for budget/other checks (for numerical issues that create infeasible dispatch problems)
_PYOMO_BUDGET_TOLERANCE = 1  # MWh


class GenericResource(Asset):
    _DOCS_URL: ClassVar[str] = (
        "https://docs.ethree.com/projects/kit/en/main/system/electric/resources/generic.html#new_modeling_toolkit.system.generic.GenericResource."
    )
    SAVE_PATH: ClassVar[str] = "resources/generic"

    @property
    def results_reporting_category(self):
        return "Resource"

    @property
    def results_reporting_folder(self):
        return f"{self.results_reporting_category}/{self.__class__.__name__}"

    @property
    def annual_results_column_order(self):
        """This property defines the ordering of columns in the Asset annual results summary out of Resolve."""
        return [
            "zone_names_string",
            "vintage_parent_group",
            "operational_group_name",
            # Investment-related data
            "selected_capacity",
            "operational_capacity",
            "retired_capacity",
            "planned_capacity",
            "potential",
            "selected_storage_capacity",
            "operational_storage_capacity",
            "retired_storage_capacity",
            "planned_storage_capacity",
            # Investment-related costs
            "annual_capital_cost",
            "annual_fixed_om_cost",
            "annual_storage_capital_cost",
            "annual_storage_fixed_om_cost",
            "annual_total_investment_cost",
            # Operations-related data
            "power_output_annual",
            "power_input_annual",
            "net_power_output_annual",
            "annual_total_scheduled_curtailment",  # Defines both Curtailed Energy and Spilled Hydro columns
            "fuel_names_string",
            "annual_total_resource_fuel_consumption_mmbtu",
            "fuel_burn_slope",  # Defines both Average and Marginal heat rate columns
            # Operations-related costs
            "annual_power_output_variable_cost",
            "annual_power_input_variable_cost",
            "annual_production_tax_credit",
            "annual_variable_cost",
            "annual_total_curtailment_cost",
            "annual_total_resource_fuel_cost",
            "annual_start_cost",
            "annual_shutdown_cost",
            "annual_total_operational_cost",
            # Slacks
            "asset_potential_slack",
            "asset_potential_slack_cost",
            "annual_total_slack_investment_cost",
            "annual_total_slack_operational_cost",
            # Other
            "integer_build",
            "integer_build_increment",
        ]

    ############
    # Linkages #
    ############
    reserves: Annotated[
        dict[str, linkage.ResourceToReserve], Metadata(linkage_order="to", category=FieldCategory.OPERATIONS)
    ] = Field(
        default_factory=dict,
        description="This input links the resource to a specific reserve type that it can contribute to. For example, Storage can provide both regulation up and down, but might not provide non-spin reserves.",
    )
    resource_groups: Annotated[dict[str, linkage.ResourceToResourceGroup], Metadata(linkage_order="to")] = Field(
        default_factory=dict,
        description="This gives each resource a group for RECAP. Depending on the Resource class, the upsampling method could change. For example, with Solar and Wind, these will be upsampled using a day draw methodology.",
    )

    outage_distributions: Annotated[dict[str, linkage.ResourceToOutageDistribution], Metadata(linkage_order="to")] = (
        Field(
            default_factory=dict,
            description="This input links resources to a specific OutageDistribution component. When a random or planned outage occurs, the outage distribution dictates what the possible outage state are for each resource. For example, if a unit is either on or offline, then it's outage distribution is 0,1.",
        )
    )

    # Override linkage field so that the type requirement is for ResourceToZone
    zones: Annotated[
        dict[str, linkage.ResourceToZone], Metadata(linkage_order="to", category=FieldCategory.OPERATIONS)
    ] = {}

    #################################
    # Build & Retirement Attributes #
    #################################

    ###################
    # Cost Attributes #
    ###################

    # TODO 2023-04-30: Think about whether variable costs should vary by modeled year or weather year, or both. Currently assumes by weather year
    variable_cost_power_output: Annotated[
        ts.NumericTimeseries,
        Metadata(
            category=FieldCategory.OPERATIONS,
            units=units.dollar / units.MWh,
            excel_short_title="VO&M Out",
        ),
    ] = Field(
        default_factory=ts.NumericTimeseries.zero,
        description="Variable O&M cost per MWh charged.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        alias="variable_cost_provide_power",
        weather_year=True,
        title=f"Variable O&M Cost",
    )
    production_tax_credit: Annotated[
        float | None,
        Metadata(units=units.dollar / units.MWh, excel_short_title="PTC"),
    ] = Field(
        None,
        title=f"Production Tax Credit",
    )
    ptc_term: Annotated[
        int | None,
        Metadata(units=units.years, excel_short_title="PTC Term"),
    ] = Field(
        None,
        title=f"PTC Term",
    )

    @model_validator(mode="after")
    def check_ptc_term(self):
        """If PTC is defined, it needs a PTC term."""
        if self.production_tax_credit is not None and self.production_tax_credit != 0:
            assert self.ptc_term is not None, "PTC term (years) is missing"
        if self.ptc_term is not None:
            assert self.production_tax_credit is not None, "PTC ($/MWh) is missing"

        return self

    @property
    def production_tax_credit_ts(self) -> ts.NumericTimeseries:
        if self.production_tax_credit is None:
            return ts.NumericTimeseries.zero()
        return ts.NumericTimeseries(
            name="PTC timeseries",
            data=pd.Series(
                self.production_tax_credit, index=pd.date_range(start=self.build_year, freq="YS", periods=self.ptc_term)
            ),
            weather_year=False,
            default_freq="YS",
        )

    ##########################
    # Operational Attributes #
    ##########################
    power_output_min: Annotated[
        ts.FractionalTimeseries, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Min Output Profile")
    ] = Field(
        default_factory=ts.FractionalTimeseries.zero,
        description="Fixed shape of resource's potential power output (e.g., solar or wind shape or flat shape"
        "for firm resources or storage resources). Used in conjunction with "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.curtailable`.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
        alias="provide_power_min_profile",
        title=f"Min Power Output Profile",
    )
    power_output_min__type: Annotated[TimeseriesType | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description=f"Whether the power_output_min profile data is of type 'weather year', 'modeled year', 'month-hour',"
        f" 'season-hour', or 'monthly'",
    )
    power_output_max: Annotated[
        ts.FractionalTimeseries, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Max Output Profile")
    ] = Field(
        default_factory=ts.FractionalTimeseries.one,
        description="Fixed shape of resource's potential power output (e.g., solar or wind shape or flat shape"
        "for firm resources or storage resources). Used in conjunction with "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.curtailable`.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
        alias="provide_power_potential_profile",
        export_weighted_results=False,
        title=f"Max Power Output Profile",
    )
    power_output_max__type: Annotated[TimeseriesType | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description=f"Whether the power_output_max profile data is of type 'weather year', 'modeled year', 'month-hour',"
        f" 'season-hour', or 'monthly'",
    )  # TODO: Could we figure out a smart way to infer the __type based on the data?
    outage_profile: Annotated[
        ts.FractionalTimeseries,
        Metadata(
            category=FieldCategory.OPERATIONS, units=units.unitless, excel_short_title="Outage", default_exclude=True
        ),
    ] = Field(
        default_factory=ts.FractionalTimeseries.one,
        description="Fixed profile of simulated outages, where a value of 1.0 represents availability of full nameplate "
        "capacity and a value less than 1.0 represents a partial outage.",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
    )
    outage_profile__type: Annotated[TimeseriesType | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description=f"Whether the outage_profile data is of type 'weather year', 'modeled year', 'month-hour',"
        f" 'season-hour', or 'monthly'",
    )

    energy_budget_daily: Annotated[
        ts.FractionalTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, units=1 / units.day, excel_short_title="Daily"),
    ] = Field(
        None,
        description="Daily fraction of energy capacity allowed for daily dispatch.",
        default_freq="D",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
        title="Daily Energy Budget",
    )

    energy_budget_monthly: Annotated[
        ts.FractionalTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, units=1 / units.month, excel_short_title="Monthly"),
    ] = Field(
        None,
        description="Monthly fraction of energy capacity allowed for monthly dispatch]",
        default_freq="MS",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
        title=f"Monthly Energy Budget",
    )

    energy_budget_annual: Annotated[
        ts.FractionalTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, units=1 / units.year, excel_short_title="Annual"),
    ] = Field(
        None,
        description="Annual fraction of energy capacity allowed for annual dispatch.",
        default_freq="YS",
        up_method="ffill",
        down_method="mean",
        weather_year=True,  # TODO: Should this be model year data? Constraint may be over-constraining
        title=f"Annual Energy Budget",
    )

    ramp_rate_1_hour: Annotated[float | None, Metadata(category=FieldCategory.OPERATIONS, units=1 / units.hour)] = (
        Field(
            None,
            description="Single-hour ramp rate. When used in conjunction with the other ramp rate limits (1-4 hour), a resource's dispatch will be constrained by all applicable ramp rate limits on a rolling basis.",
            down_method="none",
            title=f"Max 1-Hour Ramp Rate",
        )
    )
    ramp_rate_2_hour: Annotated[float | None, Metadata(category=FieldCategory.OPERATIONS, units=1 / units.hour / 2)] = (
        Field(
            None,
            description="Two-hour ramp rate. When used in conjunction with the other ramp rate limits (1-4 hour), a resource's dispatch will be constrained by all applicable ramp rate limits on a rolling basis.",
            title=f"Max 2-Hour Ramp Rate",
        )
    )
    ramp_rate_3_hour: Annotated[float | None, Metadata(category=FieldCategory.OPERATIONS, units=1 / units.hour / 3)] = (
        Field(
            None,
            description="Three-hour ramp rate. When used in conjunction with the other ramp rate limits (1-4 hour), a resource's dispatch will be constrained by all applicable ramp rate limits on a rolling basis.",
            title=f"Max 3-Hour Ramp Rate",
        )
    )
    ramp_rate_4_hour: Annotated[float | None, Metadata(category=FieldCategory.OPERATIONS, units=1 / units.hour / 4)] = (
        Field(
            None,
            description="Four-hour ramp rate. When used in conjunction with the other ramp rate limits (1-4 hour), a resource's dispatch will be constrained by all applicable ramp rate limits on a rolling basis.",
            title=f"Max 4-Hour Ramp Rate",
        )
    )

    allow_inter_period_sharing: Annotated[bool, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        False,
        description="For resources & fuel storage resources that have chronological energy storage capability, "
        "enable inter-period energy/state-of-charge tracking. For resources with ramp rates, enable inter-period tracking of ramp constraints.",
        title=f"Inter-Period SoC & Ramps",
    )

    ###########
    # Methods #
    ###########

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._imax_profile = None
        self._imin_profile = None
        self._pmax_profile = None
        self._pmin_profile = None

    def revalidate(self):
        super().revalidate()

        # Check that the Asset is not in more than 1 operational group
        operational_groups = [
            group_linkage.instance_to.name
            for group_linkage in self.asset_groups.values()
            if group_linkage.instance_to.aggregate_operations
        ]
        if len(operational_groups) > 1:
            raise AssertionError(
                f"`{self.__class__.__name__}` instance `{self.name}` is assigned to more than 1 operational AssetGroup: "
                f"`{operational_groups}`. Assign the instance to no more than 1 operational group."
            )

        # Check that power output min is never greater than power output max
        if any(self.power_output_max.data.lt(self.power_output_min.data)):
            raise ValueError(
                f"{self.__class__.__name__} instance {self.name} has a power output max less than its power"
                f" output min. This will cause infeasibilities. Check your Pmax and Pmin data."
            )

        # Check that energy budgets and power output min are feasible
        if self.energy_budget_daily is not None:
            if any(
                self.energy_budget_daily.data.lt(
                    self.power_output_min.data.groupby(self.power_output_min.data.index.date).mean()
                )
            ):
                raise ValueError(
                    f"{self.__class__.__name__} instance {self.name} has a daily energy budget that is "
                    f"rendered infeasible by its power output min. Check your Pmin and daily budget inputs."
                )
        if self.energy_budget_annual is not None:
            if any(
                self.energy_budget_annual.data.lt(
                    self.power_output_min.data.groupby(self.power_output_min.data.index.year).mean()
                )
            ):
                raise ValueError(
                    f"{self.__class__.__name__} instance {self.name} has an annual energy budget that is "
                    f"rendered infeasible by its power output min. Check your Pmin and annual budget inputs."
                )

    @property
    def outage_distribution(self) -> Optional[OutageDistribution]:
        if self.outage_distributions is None or len(self.outage_distributions) == 0:
            outage_distribution = None
        else:
            outage_distribution_name = list(self.outage_distributions.keys())[0]
            outage_distribution = self.outage_distributions[outage_distribution_name].instance_to

        return outage_distribution

    @property
    def resource_group(self) -> Optional[ResourceGroup]:
        if self.resource_groups is None or len(self.resource_groups) == 0:
            resource_group = None
        else:
            resource_group_name = list(self.resource_groups.keys())[0]
            resource_group = self.resource_groups[resource_group_name].instance_to

        return resource_group

    @property
    def has_energy_budget(self) -> bool:
        return (
            (self.energy_budget_daily is not None)
            or (self.energy_budget_monthly is not None)
            or (self.energy_budget_annual is not None)
        )

    @property
    def pmax_profile(self) -> pd.Series:
        if getattr(self, "_pmax_profile", None) is None:
            self._pmax_profile = self.power_output_max.data

        return self._pmax_profile

    @property
    def pmin_profile(self) -> pd.Series:
        if getattr(self, "_pmin_profile", None) is None:
            self._pmin_profile = self.power_output_min.data

        return self._pmin_profile

    @property
    def scaled_pmax_profile(self) -> Dict[int, pd.Series]:
        return {
            modeled_year: self.planned_capacity.data.at[f"01-01-{modeled_year}"] * self.pmax_profile
            for modeled_year in self.planned_capacity.data.index.year
        }

    @property
    def scaled_pmin_profile(self):
        return {
            modeled_year: self.planned_capacity.data.at[f"01-01-{modeled_year}"] * self.pmin_profile
            for modeled_year in self.planned_capacity.data.index.year
        }

    @property
    def scaled_daily_energy_budget(self):
        if self.energy_budget_daily is None:
            self._scaled_daily_energy_budget = None
        elif getattr(self, "_scaled_daily_energy_budget", None) is None:
            self._scaled_daily_energy_budget = {
                modeled_year: self.planned_capacity.data.at[f"01-01-{modeled_year}"]
                * self.energy_budget_daily.data
                * 24
                for modeled_year in self.planned_capacity.data.index.year
            }
        return self._scaled_daily_energy_budget

    @property
    def scaled_monthly_energy_budget(self):
        if self.energy_budget_monthly is None:
            self._scaled_monthly_energy_budget = None
        elif getattr(self, "_scaled_monthly_energy_budget", None) is None:
            self._scaled_monthly_energy_budget = {
                modeled_year: (
                    self.planned_capacity.data.at[f"01-01-{modeled_year}"]
                    * self.energy_budget_monthly.data
                    * 24
                    * self.energy_budget_monthly.data.index.days_in_month
                )
                for modeled_year in self.planned_capacity.data.index.year
            }
        return self._scaled_monthly_energy_budget

    @property
    def scaled_annual_energy_budget(self):
        if self.energy_budget_annual is None:
            self._scaled_annual_energy_budget = None
        elif getattr(self, "_scaled_annual_energy_budget", None) is None:
            self._scaled_annual_energy_budget = {
                modeled_year: (
                    self.planned_capacity.data.at[f"01-01-{modeled_year}"]
                    * self.energy_budget_annual.data
                    * 24
                    * self.energy_budget_annual.days_in_year
                )
                for modeled_year in self.planned_capacity.data.index.year
            }
        return self._scaled_annual_energy_budget

    def clear_calculated_properties(self):
        """
        Clear the property cache so scaled profiles are recalculated after rescaling
        """
        self._pmax_profile = None
        self._pmin_profile = None
        self._scaled_daily_energy_budget = None
        self._scaled_monthly_energy_budget = None
        self._scaled_annual_energy_budget = None

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        pyomo_components.update(
            # Amount of power discharged into the grid in each modeled timepoint
            power_output=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                doc="Power Output (MW)",
                initialize=0,
            ),
            net_power_output=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._net_power_output,
                doc="Net Power Output (MW)",
            ),
            power_output_max=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._power_output_max,
                doc="Power Output Upper Bound (MW)",
            ),
            power_output_min=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._power_output_min,
                doc="Power Output Lower Bound (MW)",
            ),
            power_output_max_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._power_output_max_constraint,
                doc="Power Output Max Dual",
            ),
            power_output_annual=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._power_output_annual,
                doc="Annual Power Output (MWh)",
            ),
            net_power_output_annual=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._net_power_output_annual,
                doc="Net Annual Power Output (MWh)",
            ),
        )

        """Set of reserve products that the Resource is eligible to provide"""
        if len(self.reserves) > 0:
            reserves = pyo.Set(initialize=list(self.reserves.keys()))
            pyomo_components.update(
                RESERVES=reserves,
                # Amount of reserve provided by the Resource for each eligible reserve product in each modeled timepoint
                provide_reserve=pyo.Var(
                    reserves,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    initialize=0,
                    doc="Provide Reserve (MW)",
                ),
                total_up_reserves_by_timepoint=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._total_up_reserves_by_timepoint,
                    doc="Total Up Reserves (MW)",
                ),
                total_down_reserves_by_timepoint=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._total_down_reserves_by_timepoint,
                    doc="Total Down Reserves (MW)",
                ),
                total_provide_reserve=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._total_provide_reserve,
                    doc="Total Provide Reserve (MW)",
                ),
                total_up_reserves_max_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._total_up_reserves_max_constraint,
                ),
                total_down_reserves_max_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._total_down_reserves_max_constraint,
                ),
                _reserves_max_constraint=pyo.Constraint(
                    reserves,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._reserves_max_constraint,
                ),
            )

        if not (self.power_output_min.data == 0).all():
            pyomo_components.update(
                power_output_min_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._power_output_min_constraint,
                )
            )

        if getattr(self, "energy_budget_annual", None) is not None:
            pyomo_components.update(
                annual_energy_budget_MWh=pyo.Expression(
                    model.MODELED_YEARS,
                    model.WEATHER_YEARS,
                    rule=self._energy_budget_annual_MWh,
                ),
                annual_energy_budget_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_YEARS,
                    rule=self._annual_energy_budget_constraint,
                ),
            )

        if getattr(self, "energy_budget_monthly", None) is not None:
            if model.TYPE == ModelType.RESOLVE:
                logger.warning("Monthly energy budgets are not supported in RESOLVE and will be ignored.")
            else:
                pyomo_components.update(
                    monthly_energy_budget_MWh=pyo.Expression(
                        model.MODELED_YEARS,
                        model.MONTHS,
                        rule=self._energy_budget_monthly_MWh,
                    ),
                    # TODO (skramer): figure out how to make this align with how timepoint-indexed terms are aggregated elsewhere
                    monthly_energy_budget_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.MONTHS,
                        rule=self._monthly_energy_budget_constraint,
                    ),
                )

        if getattr(self, "energy_budget_daily", None) is not None:
            pyomo_components.update(
                daily_energy_budget_MWh=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DAYS,
                    rule=self._energy_budget_daily_MWh,
                ),
                daily_energy_budget_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DAYS,
                    rule=self._daily_energy_budget_constraint,
                ),
            )

        if any(
            ramp_rate is not None
            for ramp_rate in [
                self.ramp_rate_1_hour,
                self.ramp_rate_2_hour,
                self.ramp_rate_3_hour,
                self.ramp_rate_4_hour,
            ]
        ):
            pyomo_components.update(
                ramp_rate_intra_period_up_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    model.RAMP_DURATIONS,
                    rule=self._ramp_rate_intra_period_up_constraint,
                ),
                ramp_rate_intra_period_down_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    model.RAMP_DURATIONS,
                    rule=self._ramp_rate_intra_period_down_constraint,
                ),
            )

            if (
                model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
                and self.allow_inter_period_sharing
            ):
                pyomo_components.update(
                    ramp_rate_inter_period_up_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.CHRONO_PERIODS,
                        model.RAMP_DURATIONS,
                        RangeSet(0, model.RAMP_DURATIONS.last() - 1),
                        rule=self._ramp_rate_inter_period_up_constraint,
                    ),
                    ramp_rate_inter_period_down_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.CHRONO_PERIODS,
                        model.RAMP_DURATIONS,
                        RangeSet(0, model.RAMP_DURATIONS.last() - 1),
                        rule=self._ramp_rate_inter_period_down_constraint,
                    ),
                )

        if construct_costs:
            pyomo_components.update(
                power_output_variable_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._power_output_variable_cost,
                    doc="Power Output Variable Cost ($)",
                ),
                production_tax_credit=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._production_tax_credit,
                    doc="Production Tax Credit ($)",
                ),
                annual_power_output_variable_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_power_output_variable_cost,
                    doc="Annual Power Output Variable Cost ($)",
                ),
                annual_production_tax_credit=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_production_tax_credit,
                    doc="Annual Production Tax Credit ($)",
                ),
                # Overwrite the annual total operational cost inherited from Asset
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                ),
            )

        return pyomo_components

    def _net_power_output(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        return self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]

    def _net_power_output_annual(self, block, modeled_year):
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.net_power_output[modeled_year, :, :]
        )

    def _power_output_max(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        return self.formulation_block.operational_capacity[modeled_year] * self.pmax_profile.at[timestamp]

    def _power_output_min(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        return self.formulation_block.operational_capacity[modeled_year] * self.pmin_profile.at[timestamp]

    def _total_provide_reserve(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """Total amount of reserves provided across all eligible products in each modeled timepoint"""
        return sum(
            self.formulation_block.provide_reserve[reserve, modeled_year, dispatch_window, timestamp]
            for reserve in self.formulation_block.RESERVES
        )

    def _energy_budget_annual_MWh(self, block: pyo.Block, modeled_year: pd.Timestamp, weather_year: pd.Timestamp):
        """Fractional annual energy budget scaled to model year's capacity, giving budget in MWh"""
        return (
            block.operational_capacity[modeled_year]
            * self.energy_budget_annual.data.at[weather_year]
            * 24
            * self.energy_budget_annual.days_in_year.at[weather_year]
        )

    def _energy_budget_monthly_MWh(self, block: pyo.Block, modeled_year: pd.Timestamp, month: pd.Timestamp):
        """Fractional monthly energy budget scaled to model year's capacity, giving budget in MWh"""
        return (
            block.operational_capacity[modeled_year]
            * self.energy_budget_monthly.data.at[month]
            * 24
            * month.days_in_month
        )

    def _energy_budget_daily_MWh(self, block: pyo.Block, modeled_year: pd.Timestamp, day: pd.Timestamp):
        """Fractional daily energy budget scaled to model year's capacity, giving budget in MWh"""
        return block.operational_capacity[modeled_year] * self.energy_budget_daily.data.at[day] * 24

    def _power_output_max_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """The sum of the Resource's power output and provided reserves cannot exceed its Pmax profile in a given
        timepoint"""
        return (
            self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            <= self.formulation_block.power_output_max[modeled_year, dispatch_window, timestamp]
        )

    def _reserves_max_constraint(
        self, block: pyo.Block, reserve, modeled_year: pd.Timestamp, dispatch_window, timestamp
    ):
        """The provided reserves cannot exceed the operational capacity * its max_fraction_of_capacity in a given
        timepoint"""

        # Check if the field is using the default value
        def _is_using_default_value(instance, field_name):
            field_info = instance.__fields__[field_name]
            return getattr(instance, field_name) == field_info.default

        if _is_using_default_value(self.reserves[reserve], "max_fraction_of_capacity"):
            return pyo.Constraint.Skip
        return (
            self.formulation_block.provide_reserve[reserve, modeled_year, dispatch_window, timestamp]
            <= self.reserves[reserve].max_fraction_of_capacity
            * self.formulation_block.operational_capacity[modeled_year]
        )

    def _reserves_max_constraint(
        self, block: pyo.Block, reserve, modeled_year: pd.Timestamp, dispatch_window, timestamp
    ):
        """The provided reserves cannot exceed the operational capacity * its max_fraction_of_capacity in a given
        timepoint"""

        # Check if the constraint is necessary
        if self.reserves[reserve].max_fraction_of_capacity == 1.0:
            return pyo.Constraint.Skip
        return (
            self.formulation_block.provide_reserve[reserve, modeled_year, dispatch_window, timestamp]
            <= self.reserves[reserve].max_fraction_of_capacity
            * self.formulation_block.operational_capacity[modeled_year]
        )

    # TODO: This and _power_output_max_constraint are redundant?
    def _total_up_reserves_max_constraint(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp
    ):
        """The sum of the Resource's power output and provided reserves cannot exceed its Pmax profile in a given
        timepoint"""
        return (
            self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            + self.formulation_block.total_up_reserves_by_timepoint[modeled_year, dispatch_window, timestamp]
            <= self.formulation_block.power_output_max[modeled_year, dispatch_window, timestamp]
        )

    def _power_output_min_constraint(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """The power output of the Resource must be greater than or equal to its required Pmin in a given
        timepoint"""
        return (
            self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            >= self.formulation_block.power_output_min[modeled_year, dispatch_window, timestamp]
        )

    def _total_down_reserves_max_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp
    ):
        """The power input of the Resource must be less than or equal to its specified Imax profile in a given
        timepoint"""
        return (
            self.formulation_block.total_down_reserves_by_timepoint[modeled_year, dispatch_window, timestamp]
            <= self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
        )

    def _power_output_annual(self, block, modeled_year):
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.power_output[modeled_year, :, :]
        )

    # TODO: Should annual budgets be model year data? Constraint may be over-constraining
    def _annual_energy_budget_constraint(self, block, modeled_year: pd.Timestamp, weather_year: pd.Timestamp):
        """The annual power output of the Resource must not exceed its specified annual budget. Note: a
        tolerance of 1 unit is added to the budget to ensure that floating point errors do not create an
        infeasible model."""
        if self.energy_budget_annual is None or np.isinf(self.energy_budget_annual.data.at[weather_year]):
            constraint = pyo.Constraint.Skip
        else:
            constraint = (
                block.model().sum_timepoint_component_slice_to_annual(block.power_output[modeled_year, :, :])
                <= block.annual_energy_budget_MWh[modeled_year, weather_year] + _PYOMO_BUDGET_TOLERANCE
            )

        return constraint

    def _monthly_energy_budget_constraint(self, block, modeled_year, month):
        """The monthly power output of the Resource must not exceed its specified monthly budget. Note: a
        tolerance of 1 unit is added to the budget to ensure that floating point errors do not create an
        infeasible model."""
        if self.energy_budget_monthly is None or np.isinf(self.energy_budget_monthly.data.at[month]):
            constraint = pyo.Constraint.Skip
        else:
            # TODO: figure out how to add this up appropriately using chrono to rep mapping for RESOLVE
            raise NotImplementedError("Monthly energy budgets are not yet implemented in Resolve.")
            # constraint = (
            #     sum(
            #         block.power_output[modeled_year, dispatch_window, timestamp]
            #         for dispatch_window, timestamp in block.model().MONTH_TO_TIMESTAMPS_MAPPING[month]
            #     )
            #     <= block.monthly_energy_budget_MWh[modeled_year, month] + _PYOMO_BUDGET_TOLERANCE
            # )

        return constraint

    def _daily_energy_budget_constraint(self, block, modeled_year, day):
        """The daily power output of the Resource must not exceed its specified daily budget. Note: a
        tolerance of 1 unit is added to the budget to ensure that floating point errors do not create an
        infeasible model."""
        if self.energy_budget_daily is None or np.isinf(self.energy_budget_daily.data.at[day]):
            constraint = pyo.Constraint.Skip
        else:
            constraint = (
                sum(
                    block.power_output[modeled_year, dispatch_window, timestamp]
                    for dispatch_window, timestamp in block.model().DAY_TO_TIMESTAMPS_MAPPING[day]
                )
                <= block.daily_energy_budget_MWh[modeled_year, day] + _PYOMO_BUDGET_TOLERANCE
            )

        return constraint

    def _power_output_variable_cost(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """The variable cost incurred by the Resource of providing power to the grid in a given timepoint. This
        term is not discounted (i.e. it is not multiplied by the discount factor for the relevant model year).
        """
        return self.formulation_block.power_output[modeled_year, dispatch_window, timestamp] * (
            self.variable_cost_power_output.data.at[timestamp]
        )

    def _production_tax_credit(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """The production tax credit earned by the Resource in a given timepoint. This term is not discounted
        (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        if (
            self.production_tax_credit is None
            or modeled_year < self.build_year
            or modeled_year
            >= self.build_year.replace(year=self.build_year.year + (self.ptc_term if self.ptc_term is not None else 0))
        ):
            return 0
        return (
            self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            * self.production_tax_credit_ts.data.at[modeled_year]
        )

    def _annual_power_output_variable_cost(self, block, modeled_year: pd.Timestamp):
        """The variable cost incurred by the Resource of providing power to the grid in a given timepoint. This
        term is not discounted (i.e. it is not multiplied by the discount factor for the relevant model year).
        """
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.power_output_variable_cost[modeled_year, :, :]
        )

    def _annual_production_tax_credit(self, block, modeled_year: pd.Timestamp):
        """The production tax credit earned by the Resource in a given timepoint. This term is not discounted
        (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.production_tax_credit[modeled_year, :, :]
        )

    def _annual_total_operational_cost(self, block, modeled_year: pd.Timestamp):
        """The total annual operational costs of the Resource. This term is not discounted (i.e. it is not
        multiplied by the discount factor for the relevant model year)."""
        total_operational_cost = (
            self.formulation_block.annual_power_output_variable_cost[modeled_year]
            - self.formulation_block.annual_production_tax_credit[modeled_year]
        )

        return total_operational_cost

    def _total_up_reserves_by_timepoint(self, block, modeled_year, dispatch_window, timestamp):
        """Total amount of up reserves"""
        return sum(
            self.formulation_block.provide_reserve[reserve, modeled_year, dispatch_window, timestamp]
            for reserve in self.formulation_block.RESERVES
            if self.reserves[reserve].instance_to.direction == ReserveDirection.UP
        )

    def _total_down_reserves_by_timepoint(self, block, modeled_year, dispatch_window, timestamp):
        """Total amount of down reserves"""
        return sum(
            self.formulation_block.provide_reserve[reserve, modeled_year, dispatch_window, timestamp]
            for reserve in self.formulation_block.RESERVES
            if self.reserves[reserve].instance_to.direction == ReserveDirection.DOWN
        )

    def get_ramp_MW(
        self,
        modeled_year: pd.Timestamp,
        timepoint_1: Tuple[pd.Timestamp, pd.Timestamp],
        timepoint_2: Tuple[pd.Timestamp, pd.Timestamp],
    ):
        """
        Change in output MW between two timepoints
        """
        dispatch_window_1, hour_1 = timepoint_1[0], timepoint_1[1]
        dispatch_window_2, hour_2 = timepoint_2[0], timepoint_2[1]
        return (
            self.formulation_block.net_power_output[modeled_year, dispatch_window_2, hour_2]
            - self.formulation_block.net_power_output[modeled_year, dispatch_window_1, hour_1]
        )

    # note: these functions are overwritten in UnitCommitment ramp rate constraint formulation
    def _ramp_down_ub(
        self, rr: float, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        return rr * self.formulation_block.operational_capacity[modeled_year]

    def _ramp_up_ub(
        self, rr: float, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        return rr * self.formulation_block.operational_capacity[modeled_year]

    def _ramp_rate_intra_period_up_constraint(
        self,
        block,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
        ramp_duration: float,
    ):
        """
        Ramping Limits capture limitations on how fast thermal units can adjust their output power up
        Example: if 3 hour ramp rate (ramp_duration =3), this will constrain the change in output power between hours (t) and (t+3)

        power_output(t+3) - power_output(t) <= ramp_rate * operational_capacity

        Parameters:
            - block: The block object.
            - modeled_year: A Pandas Timestamp representing the year being modeled.
            - dispatch_window: A Pandas Timestamp representing the dispatch window.
            - timestamp: A Pandas Timestamp representing the specific time within the dispatch window.
            - ramp_duration: An integer representing the duration of the ramp in hours.

        Returns:
            - Constraint object: If ramp rate for the given duration exists and the timepoints are within the dispatch window, returns a constraint object enforcing the ramping limits, otherwise returns Constraint.Skip.

        """
        rr = getattr(self, f"ramp_rate_{ramp_duration}_hour")

        if (
            block.model().dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ) and (
            timestamp + pd.Timedelta(hours=ramp_duration)
            > self.formulation_block.model().last_timepoint_in_dispatch_window[dispatch_window]
        ):
            return pyo.Constraint.Skip
        elif rr is None:
            return pyo.Constraint.Skip
        else:
            timepoint_1 = dispatch_window, timestamp
            timepoint_2 = dispatch_window, self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[
                dispatch_window
            ].nextw(timestamp, ramp_duration)
            ramp_MW = self.get_ramp_MW(modeled_year, timepoint_1, timepoint_2)

            UB = self._ramp_up_ub(rr, modeled_year, timepoint_2[0], timepoint_2[1])

            return ramp_MW <= UB

    def _ramp_rate_intra_period_down_constraint(
        self,
        block,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
        ramp_duration: int,
    ):
        """
        Ramping Limits capture limitations on how fast thermal units can adjust their output power down
        Example: if 3 hour ramp rate (ramp_duration =3), this will constrain the change in output power between hours (t) and (t+3)

        power_output(t) - power_output(t+3) <= ramp_rate * operational_capacity

        Parameters:
            - block: The block object.
            - modeled_year: A Pandas Timestamp representing the year being modeled.
            - dispatch_window: A Pandas Timestamp representing the dispatch window.
            - timestamp: A Pandas Timestamp representing the specific time within the dispatch window.
            - ramp_duration: An integer representing the duration of the ramp in hours.

        Returns:
            - Constraint object: If ramp rate for the given duration exists and the timepoints are within the dispatch window, returns a constraint object enforcing the ramping limits, otherwise returns Constraint.Skip.

        """
        rr = getattr(self, f"ramp_rate_{ramp_duration}_hour")
        if (
            block.model().dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ) and (
            timestamp + pd.Timedelta(hours=ramp_duration)
            > self.formulation_block.model().last_timepoint_in_dispatch_window[dispatch_window]
        ):
            return pyo.Constraint.Skip
        elif rr is None:
            return pyo.Constraint.Skip
        else:
            timepoint_1 = dispatch_window, timestamp
            timepoint_2 = dispatch_window, self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[
                dispatch_window
            ].nextw(timestamp, ramp_duration)
            # Note: Down ramp is purposely flipped (t1 - t2)
            ramp_MW = self.get_ramp_MW(modeled_year, timepoint_2, timepoint_1)
            UB = self._ramp_down_ub(rr, modeled_year, timepoint_2[0], timepoint_2[1])
            return ramp_MW <= UB

    def _get_ramp_rate_timepoints_inter(
        self,
        block,
        modeled_year: pd.Timestamp,
        chrono_period: pd.Timestamp,
        ramp_duration: int,
        ramp_duration_offset: int,
    ):
        """
        Identify the two timepoints to constrain the ramp rate between when the timepoints fall between multiple dispatch windows.
        This constrains the last max(ramp_duration) number of timepoints in a dispatch window.
        Ex. If ramp_duration = 4 then, we need to write a constraint for dispatch period_0[t-3] <-> dispatch_period[1][t], dispatch period_0[t-2] <-> dispatch_period[1][t+1] etc.

        Parameters:
        - block: The block object.
        - modeled_year: A Pandas Timestamp representing the year being modeled.
        - chrono_period: A Pandas Timestamp representing the chronological period.
        - ramp_duration: An integer representing the duration of the ramp in hours.
        - ramp_duration_offset: An integer representing the number of hours that will have ramp constraints that cross the dispatch window boundary.


        Returns:
        - timepoint_1: tuple(current_dispatch_window, last_timestamp of dispatch_window - ramp_duration_offset), timepoint_2: tuple(next_dispatch_window, first_timepoint_of_next_dispatch_window + ramp_duration - ramp_duration_offset -1)
        """
        chrono_period_1_index, chrono_period_2_index = block.model().return_timepoints_connecting_chrono_periods(
            modeled_year, chrono_period
        )
        _, dispatch_window, last_timestamp_chrono_period = chrono_period_1_index
        _, next_dispatch_window, first_timestamp_next_chrono_period = chrono_period_2_index

        timepoint_1 = dispatch_window, self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[
            dispatch_window
        ].prevw(last_timestamp_chrono_period, ramp_duration_offset)

        timepoint_2 = next_dispatch_window, self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[
            next_dispatch_window
        ].nextw(
            first_timestamp_next_chrono_period, ramp_duration - ramp_duration_offset - 1
        )  # this is ramp_duration - 1 because the first_timestamp_next_chrono_period is already 1 timestep away
        return timepoint_1, timepoint_2

    def _ramp_rate_inter_period_up_constraint(
        self,
        block,
        modeled_year: pd.Timestamp,
        chrono_period: pd.Timestamp,
        ramp_duration: int,
        ramp_duration_offset: int,
    ):
        """
        Constrains the ramping limits for the adjustment of thermal units' output power upwards between two timestamps connecting two dispatch windows.

        Example: if 3 hour ramp rate (ramp_duration =3), this will constrain the change in output power between hours (t) and (t+3)

        power_output(t+3) - power_output(t) <= ramp_rate * operational_capacity

        If the ramp_duration_offset is greater than or equal to the ramp_duration, skip the constraint because these timepoints are already accounted for in the intra_ramp_rate constraints

        Parameters:
        - block: The block object.
        - modeled_year: A Pandas Timestamp representing the year being modeled.
        - chrono_period: A Pandas Timestamp representing the chronological period.
        - ramp_duration: An integer representing the duration of the ramp in hours.
        - ramp_duration_offset: An integer representing the number of hours that will have ramp constraints that cross the dispatch window boundary. (see docstrings for `_ramp_rate_timepoints_inter`)

        Returns:
        - Constraint object: If ramp rate for the given duration exists, returns a constraint object enforcing the ramping limits, otherwise returns Constraint.Skip.
        """
        rr = getattr(self, f"ramp_rate_{ramp_duration}_hour")
        if rr is None:
            return pyo.Constraint.Skip
        elif ramp_duration - ramp_duration_offset <= 0:
            return pyo.Constraint.Skip
        else:
            timepoint_1, timepoint_2 = self._get_ramp_rate_timepoints_inter(
                block, modeled_year, chrono_period, ramp_duration, ramp_duration_offset
            )
            ramp_MW = self.get_ramp_MW(modeled_year, timepoint_1, timepoint_2)

            UB = self._ramp_up_ub(rr, modeled_year, timepoint_2[0], timepoint_2[1])

            return ramp_MW <= UB

    def _ramp_rate_inter_period_down_constraint(
        self,
        block,
        modeled_year: pd.Timestamp,
        chrono_period: pd.Timestamp,
        ramp_duration: int,
        ramp_duration_offset: int,
    ):
        """
        Ramping Limits capture limitations on how fast thermal units can adjust their output power down for timestamp that connect two dispatch windows

        Example: if 3 hour ramp rate (ramp_duration =3), this will constrain the change in output power between hours (t) and (t+3)

        If the ramp_duration_offset is greater than or equal to the ramp_duration, skip the constraint because these timepoints are already accounted for in the intra_ramp_rate constraints

        Parameters:
        - block: The block object.
        - modeled_year: A Pandas Timestamp representing the year being modeled.
        - chrono_period: A Pandas Timestamp representing the chronological period.
        - ramp_duration_offset: An integer representing the number of hours that will have ramp constraints that cross the dispatch window boundary. (see docstrings for `_ramp_rate_timepoints_inter`)

        Returns:
        - Constraint object: If ramp rate for the given duration exists, returns a constraint object enforcing the ramping limits, otherwise returns Constraint.Skip.
        """
        rr = getattr(self, f"ramp_rate_{ramp_duration}_hour")
        if rr is None:
            return pyo.Constraint.Skip
        elif ramp_duration - ramp_duration_offset <= 0:
            return pyo.Constraint.Skip  # these timestamps are already constrained in the ram
        else:
            timepoint_1, timepoint_2 = self._get_ramp_rate_timepoints_inter(
                block, modeled_year, chrono_period, ramp_duration, ramp_duration_offset
            )

            # Note: Down ramp is purposely flipped (t1 - t2)
            ramp_MW = self.get_ramp_MW(modeled_year, timepoint_2, timepoint_1)
            UB = self._ramp_down_ub(rr, modeled_year, timepoint_2[0], timepoint_2[1])
            return ramp_MW <= UB


class GenericResourceGroup(AssetGroup, GenericResource):
    SAVE_PATH: ClassVar[str] = "resources/generic/groups"
    _NAME_PREFIX: ClassVar[str] = "generic_resource_group"
    _GROUPING_CLASS = GenericResource

    # Override linkage field so that the type requirement is for ResourceToZone
    zones: Annotated[
        dict[str, linkage.ResourceToZone], Metadata(linkage_order="to", category=FieldCategory.OPERATIONS)
    ] = {}

    @computed_field(title="Resource List")
    @property
    def list_of_resource_names(self) -> list:
        return list(self.asset_instances.keys())

    @property
    def results_reporting_category(self):
        return "ResourceGroup"

    @property
    def production_tax_credit_ts(self) -> ts.NumericTimeseries:
        if self.production_tax_credit is None:
            return ts.NumericTimeseries.zero()
        else:
            return ts.NumericTimeseries(
                name="PTC timeseries",
                data=pd.Series(
                    self.production_tax_credit,
                    index=pd.date_range(start=self.earliest_build_year, freq="YS", periods=self.ptc_term),
                ),
                weather_year=False,
                default_freq="YS",
            )

    @property
    def annual_results_column_order(self):
        """This property defines the ordering of columns in the Asset annual results summary out of Resolve."""
        return [
            "zone_names_string",
            "aggregate_operations",
            # Investment-related data
            "cumulative_selected_capacity",
            "operational_capacity",
            "cumulative_retired_capacity",
            "planned_capacity",
            "cumulative_potential",
            "cumulative_selected_storage_capacity",
            "operational_storage_capacity",
            "cumulative_retired_storage_capacity",
            "planned_storage_capacity",
            # Operations-related data
            "power_output_annual",
            "power_input_annual",
            "net_power_output_annual",
            "annual_total_scheduled_curtailment",  # TODO: Defines both Curtailed Energy and Spilled Hydro columns
            "fuel_names_string",
            "annual_total_resource_fuel_consumption_mmbtu",
            "fuel_burn_slope",  # TODO: Defines both Average and Marginal heat rate columns. Need separate columns
            # Operations-related costs
            "annual_power_output_variable_cost",
            "annual_power_input_variable_cost",
            "annual_production_tax_credit",
            "annual_variable_cost",
            "annual_total_curtailment_cost",
            "annual_total_resource_fuel_cost",
            "annual_start_cost",
            "annual_shutdown_cost",
            "annual_total_operational_cost",
            # Investment-related costs -- not needed for groups
        ]

    def revalidate(self):
        super().revalidate()

        # Check that power output min is never greater than power output max
        if any(self.power_output_max.data.lt(self.power_output_min.data)):
            raise ValueError(
                f"{self.__class__.__name__} instance {self.name} has a power output max less than its power"
                f" output min. This will cause infeasibilities. Check your Pmax and Pmin data."
            )

        # Check that energy budgets and power output min are feasible
        if self.energy_budget_daily is not None:
            if any(
                self.energy_budget_daily.data.lt(
                    self.power_output_min.data.groupby(self.power_output_min.data.index.date).mean()
                )
            ):
                raise ValueError(
                    f"{self.__class__.__name__} instance {self.name} has a daily energy budget that is "
                    f"rendered infeasible by its power output min. Check your Pmin and daily budget inputs."
                )
        if self.energy_budget_annual is not None:
            if any(
                self.energy_budget_annual.data.lt(
                    self.power_output_min.data.groupby(self.power_output_min.data.index.year).mean()
                )
            ):
                raise ValueError(
                    f"{self.__class__.__name__} instance {self.name} has an annual energy budget that is "
                    f"rendered infeasible by its power output min. Check your Pmin and annual budget inputs."
                )

    def _production_tax_credit(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """The production tax credit earned by the Resource in a given timepoint. This term is not discounted
        (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        # TODO: PTC credit calculation on operational groups does not account for different start and end dates of
        #  PTC term for different build years within the group
        if (
            self.production_tax_credit is None
            or modeled_year < self.earliest_build_year
            or modeled_year
            >= self.earliest_build_year.replace(
                year=self.earliest_build_year.year + (self.ptc_term if self.ptc_term is not None else 0)
            )
        ):
            return 0
        return (
            self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            * self.production_tax_credit_ts.data.at[modeled_year]
        )

    def _production_tax_credit(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """The production tax credit earned by the Resource in a given timepoint. This term is not discounted
        (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        # TODO: Check with ROGO if production_tax_credit should be set to zero for operational groups
        if (
            self.production_tax_credit is None
            or modeled_year < self.earliest_build_year
            or modeled_year
            >= self.earliest_build_year.replace(
                year=self.earliest_build_year.year + (self.ptc_term if self.ptc_term is not None else 0)
            )
        ):
            return 0
        return (
            self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            * self.production_tax_credit_ts.data.at[modeled_year]
        )
