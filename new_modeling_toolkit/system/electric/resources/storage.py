import enum
import itertools
from typing import ClassVar
from typing import Dict

import pandas as pd
import pyomo.environ as pyo
from pydantic import Field
from typing_extensions import Annotated

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import ModelType
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.core.temporal.timeseries import TimeseriesType
from new_modeling_toolkit.system.electric.resources.generic import GenericResource
from new_modeling_toolkit.system.electric.resources.generic import GenericResourceGroup


@enum.unique
class StorageDurationConstraint(enum.Enum):
    FIXED = "fixed"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"


class StorageResource(GenericResource):
    """Resource with storage capacity.

    Adds state-of-charge tracking.

    It feels like BatteryResource could be composed of a GenericResource + Asset (that represents the storage costs),
    but need to think about this more before implementing.
    """

    _DOCS_URL: ClassVar[str] = (
        "https://docs.ethree.com/projects/kit/en/main/system/electric/resources/storage.html#new_modeling_toolkit.system.storage.StorageResource."
    )
    SAVE_PATH: ClassVar[str] = "resources/storage"

    #################################
    # Build & Retirement Attributes #
    #################################
    duration: Annotated[
        float, Metadata(category=FieldCategory.OPERATIONS, show_year_headers=False, units=units.hour)
    ] = Field(
        description="[RESOLVE, RECAP]. Hours of operational time the battery can operate at a specified power level "
        "before it runs out of energy. Required when resource is an operational group or does not belong to"
        " one.",
        alias="storage_duration",
        title=f"Duration",
        ge=0,
    )

    duration_constraint: Annotated[StorageDurationConstraint, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        default=StorageDurationConstraint.FIXED,
    )

    ##################################################
    # Build and Retirement Outputs from Solved Model #
    ##################################################
    """These three attributes are outputs, not inputs. They are initialized to None and are updated to their chosen
    optimal values after the RESOLVE model is solved. The attributes are used to give build and retirement decisions to
    a model run in production simulation mode."""
    operational_storage_capacity: ts.NumericTimeseries | None = Field(
        None, down_method="mean", up_method="ffill", default_freq="YS"
    )
    selected_storage_capacity: float | None = None
    retired_storage_capacity: ts.NumericTimeseries | None = Field(
        None, down_method="mean", up_method="ffill", default_freq="YS"
    )
    cumulative_retired_storage_capacity: ts.NumericTimeseries | None = Field(
        None, down_method="mean", up_method="ffill", default_freq="YS"
    )

    ###################
    # Cost Attributes #
    ###################
    annualized_storage_capital_cost: Annotated[float, Metadata(units=units.dollar / units.kWh_year)] = Field(
        default=0.0,
        description="$/kWh-yr. For new storage capacity, the annualized fixed cost of investment. "
        "This is an annualized version of an overnight cost that could include financing costs ($/kWh-year).",
        alias="new_storage_annual_fixed_cost_dollars_per_kwh_yr_by_vintage",
        title=f"Storage Levelized Fixed Cost",
    )
    annualized_storage_fixed_om_cost: Annotated[ts.NumericTimeseries, Metadata(units=units.dollar / units.kWh_year)] = (
        Field(
            default_factory=ts.NumericTimeseries.zero,
            description="$/kWh-yr. For the planned portion of the resource's storage capacity, "
            "the ongoing fixed O&M cost",
            default_freq="YS",
            up_method="interpolate",
            down_method="mean",
            alias="new_storage_capacity_fixed_om_by_vintage",
            title=f"Storage Fixed O&M Cost",
        )
    )

    variable_cost_power_input: Annotated[
        ts.NumericTimeseries,
        Metadata(
            category=FieldCategory.OPERATIONS,
            units=units.dollar / units.MWh,
            excel_short_title="VO&M In",
        ),
    ] = Field(
        default_factory=ts.NumericTimeseries.zero,
        description="Variable O&M cost per MWh generated.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        alias="variable_cost_increase_load",
        weather_year=True,
        title=f"Variable O&M Cost",
    )

    ##########################
    # Operational Attributes #
    ##########################
    power_input_min: Annotated[
        ts.FractionalTimeseries,
        Metadata(category=FieldCategory.OPERATIONS, units=units.unitless, excel_short_title="Min Input Profile"),
    ] = Field(
        default_factory=ts.FractionalTimeseries.zero,
        description="Fixed shape of resource's potential power draw (e.g. flat shape for storage resources)."
        " Used in conjunction with "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.curtailable`.",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        title=f"Min Power Input Profile",
    )
    power_input_min__type: Annotated[TimeseriesType | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description=f"Whether the power_input_min profile data is of type 'weather year', 'modeled year', 'month-hour',"
        f" 'season-hour', or 'monthly'",
    )
    power_input_max: Annotated[
        ts.FractionalTimeseries,
        Metadata(category=FieldCategory.OPERATIONS, units=units.unitless, excel_short_title="Max Input Profile"),
    ] = Field(
        default_factory=ts.FractionalTimeseries.one,
        description="Fixed shape of resource's potential power draw (e.g. flat shape for storage resources)."
        " Used in conjunction with "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.curtailable`.",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        alias="increase_load_potential_profile",
        title=f"Max Power Input Profile",
    )
    power_input_max__type: Annotated[TimeseriesType | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description=f"Whether the power_input_max profile data is of type 'weather year', 'modeled year', 'month-hour',"
        f" 'season-hour', or 'monthly'",
    )

    charging_efficiency: Annotated[ts.FractionalTimeseries, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        default_factory=ts.FractionalTimeseries.one,
        description="[RESOLVE, RECAP]. % of Charging MW. Efficiency losses associated with charging (increasing load), typically expressed as a % of nameplate unless charging power specified "
        'to increase storage "state of charge".',
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
        title=f"Charging Efficiency",
    )
    charging_efficiency__type: Annotated[TimeseriesType | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description=f"Whether the charging_efficiency profile data is of type 'weather year', 'modeled year', 'month-hour',"
        f" 'season-hour', or 'monthly'",
    )
    discharging_efficiency: Annotated[ts.FractionalTimeseries, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        default_factory=ts.FractionalTimeseries.one,
        description="[RESOLVE, RECAP]. % of Discharging MW, Efficiency losses associated with discharging (providing power), typically expressed as a % of nameplate unless charging power specified, "
        'taking energy out of storage "state of charge".',
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
        title=f"Discharging Efficiency",
    )
    discharging_efficiency__type: Annotated[TimeseriesType | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description=f"Whether the discharging_efficiency profile data is of type 'weather year', 'modeled year', 'month-hour',"
        f" 'season-hour', or 'monthly'",
    )
    parasitic_loss: Annotated[float, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        0, description="[Storage] Hourly state of charge losses.", title=f"Parasitic Losses", ge=0, le=1
    )

    state_of_charge_min: Annotated[float, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        0,
        description="[Storage] Minimum state-of-charge at any given time.",
        title=f"Min State-of-Charge",
    )

    ###########
    # Methods #
    ###########

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def revalidate(self):
        super().revalidate()
        if len(self.erm_policies) > 1:
            raise ValueError(
                f"The `StorageResource` {self.name} is linked to more than one ERM policy, which is not "
                f"allowed. Check your linkages.csv file"
            )

    @property
    def planned_storage_capacity(self) -> pd.Series:
        """
        This property is for storage only now.
        """

        return self.planned_capacity.data * self.duration

    @property
    def imax_profile(self) -> pd.Series:
        if getattr(self, "_imax_profile", None) is None:
            self._imax_profile = self.power_input_max.data

        return self._imax_profile

    @property
    def imin_profile(self) -> pd.Series:
        if getattr(self, "_imin_profile", None) is None:
            self._imin_profile = self.power_input_min.data

        return self._imin_profile

    @property
    def scaled_imax_profile(self) -> Dict[int, pd.Series]:
        return {
            modeled_year: self.capacity_planned.data.at[f"01-01-{modeled_year}"] * self.imax_profile
            for modeled_year in self.capacity_planned.data.index.year
        }

    @property
    def scaled_imin_profile(self) -> Dict[int, pd.Series]:
        return {
            modeled_year: self.capacity_planned.data.at[f"01-01-{modeled_year}"] * self.imin_profile
            for modeled_year in self.capacity_planned.data.index.year
        }

    @property
    def scaled_SOC_max_profile(self) -> Dict[int, pd.Series]:
        """
        This property is for storage only now.
        """
        if getattr(self, "_scaled_SOC_max_profile", None) is None:
            self._scaled_SOC_max_profile = {
                modeled_year: pd.Series(
                    index=self.scaled_pmax_profile[modeled_year].index,
                    data=self.planned_storage_capacity.at[f"01-01-{modeled_year}"],
                )
                for modeled_year in self.planned_storage_capacity.index.year
            }
        return self._scaled_SOC_max_profile

    def clear_calculated_properties(self):
        """
        Clear the property cache so scaled profiles are recalculated after rescaling
        """
        super().clear_calculated_properties()
        self._imax_profile = None
        self._imin_profile = None

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)

        self.formulation_block.planned_storage_capacity = pyo.Param(
            model.MODELED_YEARS,
            initialize=lambda b, year: self.planned_storage_capacity[year],
            doc="Planned Storage Capacity (MWh)",
        )
        pyomo_components.update(
            selected_storage_capacity=pyo.Var(
                within=pyo.NonNegativeReals,
                doc="Selected Storage Capacity (MWh)",
            ),
            retired_storage_capacity=pyo.Var(
                model.MODELED_YEARS,
                within=pyo.NonNegativeReals,
                doc="Retired Storage Capacity (MWh)",
            ),
            operational_storage_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._operational_storage_capacity,
                doc="Operational Storage Capacity (MWh)",
            ),
            storage_capacity_duration_constraint=pyo.Constraint(
                model.MODELED_YEARS, rule=self._storage_capacity_duration_constraint
            ),
            retired_storage_capacity_max_constraint=pyo.Constraint(
                model.MODELED_YEARS, rule=self._retired_storage_capacity_max_constraint
            ),
            storage_physical_lifetime_constraint=pyo.Constraint(
                model.MODELED_YEARS, rule=self._storage_physical_lifetime_constraint
            ),
        )

        ##########################################
        # Production Simulation Mode Constraints #
        ##########################################
        if model.TYPE == ModelType.RESOLVE and model.production_simulation_mode:
            self.formulation_block.chosen_selected_storage_capacity = pyo.Param(
                initialize=self.selected_storage_capacity
            )
            self.formulation_block.chosen_retired_storage_capacity = pyo.Param(
                model.MODELED_YEARS, initialize=self.retired_storage_capacity.data.loc[list(model.MODELED_YEARS)]
            )
            self.formulation_block.chosen_operational_storage_capacity = pyo.Param(
                model.MODELED_YEARS, initialize=self.operational_storage_capacity.data.loc[list(model.MODELED_YEARS)]
            )
            pyomo_components.update(
                prod_sim_selected_storage_capacity_constraint=pyo.Constraint(
                    rule=self._prod_sim_selected_storage_capacity_constraint
                ),
                prod_sim_retired_storage_capacity_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._prod_sim_retired_storage_capacity_constraint
                ),
                prod_sim_operational_storage_capacity_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._prod_sim_operational_storage_capacity_constraint
                ),
            )

        if construct_costs:
            pyomo_components.update(
                annual_storage_capital_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_storage_capital_cost,
                    doc="Annual Storage Capacity Capital Cost ($)",
                ),
                annual_storage_fixed_om_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_storage_fixed_om_cost,
                    doc="Annual Storage Capacity Fixed O&M Cost ($)",
                ),
                annual_total_investment_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_investment_cost,
                    doc="Annual Total Investment Cost ($)",
                ),
            )

        if self.erm_policies:
            pyomo_components.update(
                erm_dispatch_cost_per_MWh=pyo.Param(within=pyo.Reals, initialize=-0.001),
                erm_charging_efficiency=pyo.Expression(model.WEATHER_TIMESTAMPS, rule=self._erm_charging_efficiency),
                erm_discharging_efficiency=pyo.Expression(
                    model.WEATHER_TIMESTAMPS, rule=self._erm_discharging_efficiency
                ),
                erm_power_input=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="ERM Power Input (MW)",
                    initialize=0,
                ),
                erm_power_output=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="ERM Power Output (MW)",
                    initialize=0,
                ),
                erm_net_power_output=pyo.Expression(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_net_power_output,
                    doc="ERM Net Power Output (MW)",
                ),
                erm_power_output_max_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_power_output_max_constraint,
                ),
                erm_power_input_max_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_power_input_max_constraint,
                ),
                erm_state_of_charge=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="ERM SOC (MWh)",
                    initialize=0,
                ),
                erm_soc_tracking_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_soc_tracking_constraint,
                ),
                erm_dispatch_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_dispatch_cost,
                    doc="ERM Storage Dispatch Cost ($)",
                ),
                erm_annual_dispatch_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._erm_annual_dispatch_cost, doc="ERM Annual Storage Dispatch Cost ($)"
                ),
            )

        return pyomo_components

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict(
            # Amount of power consumed from the grid in each modeled timepoint
            power_input=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                doc="Power Input (MW)",
                initialize=0,
            ),
        )

        pyomo_components.update(super()._construct_operational_rules(model, construct_costs))

        pyomo_components.update(
            power_input_max=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._power_input_max,
                doc="Power Input Upper Bound (MW)",
            ),
            power_input_min=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._power_input_min,
                doc="Power Input Lower Bound (MW)",
            ),
            power_input_annual=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._power_input_annual,
                doc="Annual Power Input (MWh)",
            ),
            power_input_max_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._power_input_max_constraint,
            ),
            mileage_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._mileage_constraint,
            ),
        )

        # If the minimum power input (Imin) of the Resource is not 0 in all timepoints, constrain the power input to be
        #  greater than the Imin
        if (self.power_input_min.data > 0).any():
            pyomo_components.update(
                power_input_min_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._power_input_min_constraint,
                )
            )

        pyomo_components.update(
            soc_intra_period=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.Reals,
                initialize=0,
                doc="SOC Intra Period (MWh)",
            ),
            soc_inter_period=pyo.Var(
                model.MODELED_YEARS,
                model.CHRONO_PERIODS,
                within=pyo.NonNegativeReals,
                initialize=0,
            ),
            soc_inter_intra_joint=pyo.Expression(
                model.MODELED_YEARS,
                model.CHRONO_PERIODS_AND_TIMESTAMPS,
                rule=self._soc_inter_intra_joint,
                doc="SOC Inter-Intra Joint (MWh)",
            ),
            simultaneous_charging_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._simultaneous_charging_constraint,
            ),
            soc_inter_intra_max_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.CHRONO_PERIODS_AND_TIMESTAMPS,
                rule=self._soc_inter_intra_max_constraint,
            ),
            soc_inter_intra_min_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.CHRONO_PERIODS_AND_TIMESTAMPS,
                rule=self._soc_inter_intra_min_constraint,
            ),
            soc_intra_tracking_constraint=pyo.Constraint(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._soc_intra_tracking_constraint
            ),
            soc_intra_anchoring_constraint=pyo.Constraint(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS, rule=self._soc_intra_anchoring_constraint
            ),
            soc_inter_tracking_constraint=pyo.Constraint(
                model.MODELED_YEARS, model.CHRONO_PERIODS, rule=self._soc_inter_tracking_constraint
            ),
        )

        if len(self.reserves) > 0:
            pyomo_components.update(
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
                soc_intra_operating_reserve_up_max=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._soc_intra_operating_reserve_up_max,
                ),
            )

        if construct_costs:
            pyomo_components.update(
                power_input_variable_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._power_input_variable_cost,
                    doc="Power Input Variable Cost ($)",
                ),
                annual_power_input_variable_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_power_input_variable_cost,
                    doc="Annual Power Input Variable Cost ($)",
                ),
                annual_variable_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._annual_variable_cost, doc="Annual Total Variable Cost ($)"
                ),
                # Overwrite the annual total operational cost inherited from GenericResource
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                ),
            )

        return pyomo_components

    def _operational_storage_capacity(self, block, modeled_year: pd.Timestamp):
        if modeled_year >= self.build_year:
            operational_storage_capacity = (
                self.planned_storage_capacity[modeled_year]
                + self.formulation_block.selected_storage_capacity
                - pyo.quicksum(
                    self.formulation_block.retired_storage_capacity[year]
                    for year in self.formulation_block.model().MODELED_YEARS
                    if year <= modeled_year
                )
            )
        else:
            operational_storage_capacity = 0.0

        return operational_storage_capacity

    def _storage_capacity_duration_constraint(self, block, modeled_year):
        """
        Constrains operational storage capacity based on duration:
        If user-defined duration is fixed, power capacity * duration is equal to energy capacity
        If user-defined duration is the minimum allowed, power capacity * duration is less than or equal to energy capacity
        If user-defined duration is the maximum allowed, power capacity * duration is greater than or equal to energy capacity

        """
        duration_requirement = self.formulation_block.operational_capacity[modeled_year] * self.duration
        operational_storage_capacity = self.formulation_block.operational_storage_capacity[modeled_year]
        if self.duration_constraint == StorageDurationConstraint.FIXED:
            return duration_requirement == operational_storage_capacity
        elif self.duration_constraint == StorageDurationConstraint.MINIMUM:
            return duration_requirement <= operational_storage_capacity
        elif self.duration_constraint == StorageDurationConstraint.MAXIMUM:
            return duration_requirement >= operational_storage_capacity
        else:
            raise NotImplementedError(
                f"Duration specification ({self.duration_constraint}) for {self.name} has not been implemented yet."
            )

    def _retired_storage_capacity_max_constraint(self, block, modeled_year):
        """Upper bound on the amount of retired capacity in each year. Retired capacity in a given year cannot
        exceed the operational capacity in the previous year, and capacity cannot be retired before the build year
        of the storage resource."""

        # If the modeled year is earlier than the build year, no capacity can be retired in that year
        if self.build_year > modeled_year:
            return self.formulation_block.retired_storage_capacity[modeled_year] == 0

        # If the resource can't be retired, but it has a physical lifetime, don't allow retirement until the
        #  end of its physical lifetime
        elif (
            not self.can_retire
            and self.physical_lifetime != 100
            and modeled_year < self.build_year.replace(year=self.build_year.year + self.physical_lifetime)
        ):
            constraint = self.formulation_block.retired_storage_capacity[modeled_year] == 0

        # If the resource can't be retired, and it has no specified physical lifetime, don't allow it to retire ever
        elif not self.can_retire and self.physical_lifetime == 100:
            constraint = self.formulation_block.retired_storage_capacity[modeled_year] == 0

        # If the resource exists before the first modeled year, only the planned capacity can be retired
        elif (modeled_year == self.formulation_block.model().MODELED_YEARS.first()) or (
            modeled_year == self.build_year
        ):
            constraint = (
                self.formulation_block.retired_storage_capacity[modeled_year]
                <= self.planned_storage_capacity[modeled_year]
            )

        # Otherwise, the resource cannot retire more capacity than was online in the previous modeled year
        else:
            constraint = (
                self.formulation_block.retired_storage_capacity[modeled_year]
                <= self.formulation_block.operational_storage_capacity[
                    self.formulation_block.model().MODELED_YEARS.prev(modeled_year)
                ]
            )

        return constraint

    def _storage_physical_lifetime_constraint(self, block, modeled_year):
        """The storage resource energy capacity must be retired after the end of its physical lifetime"""
        if (
            self.physical_lifetime != 100
            and self.build_year.replace(year=self.build_year.year + self.physical_lifetime) <= modeled_year
        ):
            constraint = self.formulation_block.operational_storage_capacity[modeled_year] == 0
        else:
            constraint = pyo.Constraint.Skip

        return constraint

    def _annual_storage_capital_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Capital costs of storage for the Asset in each year. Capital costs are only incurred for selected new-build
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
            storage_investment_cost = (
                self.annualized_storage_capital_cost * 1e3 * self.formulation_block.selected_storage_capacity
            )
        else:
            storage_investment_cost = 0.0

        return storage_investment_cost

    def _annual_storage_fixed_om_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Fixed O&M costs of capacity for the Asset in each year. Fixed O&M costs are incurred for both selected
        new-build capacity and for planned capacity. This term represents the costs incurred in a single year, and
        it is not discounted (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        storage_fixed_om_cost = (
            self.annualized_storage_fixed_om_cost.data.at[modeled_year]
            * 1e3
            * self.formulation_block.operational_storage_capacity[modeled_year]
        )

        return storage_fixed_om_cost

    def _annual_total_investment_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        total_investment_cost = super()._annual_total_investment_cost(block=block, modeled_year=modeled_year)
        total_investment_cost += (
            self.formulation_block.annual_storage_capital_cost[modeled_year]
            + self.formulation_block.annual_storage_fixed_om_cost[modeled_year]
        )

        return total_investment_cost

    ### Operational Constraints

    def _net_power_output(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        return (
            self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            - self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
        )

    def _power_input_max(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        return self.formulation_block.operational_capacity[modeled_year] * self.imax_profile.at[timestamp]

    def _power_input_min(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        return self.formulation_block.operational_capacity[modeled_year] * self.imin_profile.at[timestamp]

    def _total_up_reserves_max_constraint(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp
    ):
        """The sum of the Resource's power output and provided reserves cannot exceed its Pmax profile in a given
        timepoint"""
        return (
            self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            + self.formulation_block.total_up_reserves_by_timepoint[modeled_year, dispatch_window, timestamp]
            - self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
            <= self.formulation_block.power_output_max[modeled_year, dispatch_window, timestamp]
        )

    def _power_input_max_constraint(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """The power input of the Resource must be less than or equal to its specified Imax profile in a given
        timepoint"""
        return (
            self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
            <= self.formulation_block.power_input_max[modeled_year, dispatch_window, timestamp]
        )

    def _total_down_reserves_max_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp
    ):
        """The power input of the Resource must be less than or equal to its specified Imax profile in a given
        timepoint"""
        return (
            self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
            + self.formulation_block.total_down_reserves_by_timepoint[modeled_year, dispatch_window, timestamp]
            - self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            <= self.formulation_block.power_input_max[modeled_year, dispatch_window, timestamp]
        )

    def _power_input_min_constraint(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """The power input of the Resource must be less than or equal to its specified Imax profile in a given
        timepoint"""
        return (
            self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
            >= self.formulation_block.power_input_min[modeled_year, dispatch_window, timestamp]
        )

    def _power_input_annual(self, block, modeled_year):
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.power_input[modeled_year, :, :]
        )

    def _mileage_constraint(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """The Resource cannot both discharge and consume power for the entire duration of a single timepoint.
        Note: this constraint is somewhat imperfect unless the Pmax profile and Imax profile are equal in a
        given timepoint."""
        if len(self.reserves) > 0:
            return self.formulation_block.power_output[
                modeled_year, dispatch_window, timestamp
            ] + self.formulation_block.power_input[
                modeled_year, dispatch_window, timestamp
            ] + self.formulation_block.total_up_reserves_by_timepoint[
                modeled_year, dispatch_window, timestamp
            ] + self.formulation_block.total_down_reserves_by_timepoint[
                modeled_year, dispatch_window, timestamp
            ] <= self.formulation_block.operational_capacity[
                modeled_year
            ] * max(
                self.pmax_profile.at[timestamp], self.imax_profile.at[timestamp]
            )
        else:
            return self.formulation_block.power_output[
                modeled_year, dispatch_window, timestamp
            ] + self.formulation_block.power_input[
                modeled_year, dispatch_window, timestamp
            ] <= self.formulation_block.operational_capacity[
                modeled_year
            ] * max(
                self.pmax_profile.at[timestamp], self.imax_profile.at[timestamp]
            )

    def _soc_intra_operating_reserve_up_max(
        self, block, modeled_year: int, dispatch_window: int, timestamp: pd.Timestamp
    ):
        """Upward reserves are limited by storage state-of-charge "headroom"."""
        return (
            # charging efficiency not applied to power_input
            # because storage could provide full amount of MW charging as reserve by just stopping its charging
            # Ex: Battery w 100 MWh SOC (discharge_eff of 0.8), charging at 200 MW may provide 280 MW reserve
            # bc it could stop charging and then begin discharging
            self.formulation_block.total_up_reserves_by_timepoint[modeled_year, dispatch_window, timestamp]
            <= (
                self.formulation_block.soc_intra_period[modeled_year, dispatch_window, timestamp]
                * self.discharging_efficiency.data.at[timestamp]
            )
            + self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
            - self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
        )

    def _simultaneous_charging_constraint(self, block, modeled_year, dispatch_window, timestamp):
        """Limit simultaneous charging & discharging for storage resource to what could be possible within an hour.

        In other words, storage resources can simultaneously charge & discharge as long as they "split" the hour
        (e.g., charging for half the hour and discharging for half the hour).
        """
        if len(self.reserves) > 0:
            return (
                self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
                + self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
                + self.formulation_block.total_up_reserves_by_timepoint[modeled_year, dispatch_window, timestamp]
                + self.formulation_block.total_down_reserves_by_timepoint[modeled_year, dispatch_window, timestamp]
                <= self.formulation_block.operational_capacity[modeled_year]
            )
        else:
            return (
                self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
                + self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
                <= self.formulation_block.operational_capacity[modeled_year]
            )

    def _soc_inter_intra_joint(self, block, modeled_year, chrono_period, timestamp):
        """
        Sums inter- and intra-period SOC. Used to track SOC in resources with storage in all timepoints.
        """
        dispatch_window = self.formulation_block.model().chrono_periods_map[chrono_period]
        return (
            self.formulation_block.soc_intra_period[modeled_year, dispatch_window, timestamp]
            + self.formulation_block.soc_inter_period[modeled_year, chrono_period]
        )

    def _soc_inter_intra_max_constraint(self, block, modeled_year, chrono_period, timestamp):
        """
        SOC cannot exceed storage's total MWh capacity divided by discharging efficiency, i.e. the full tank size.
        """
        return (
            self.formulation_block.soc_inter_intra_joint[modeled_year, chrono_period, timestamp]
            <= self.formulation_block.operational_storage_capacity[modeled_year]
            / self.discharging_efficiency.data.at[timestamp]
        )

    def _soc_inter_intra_min_constraint(self, block, modeled_year, chrono_period, timestamp):
        """
        SOC must be non-negative or constrained by soc_min.
        """
        return (
            self.formulation_block.soc_inter_intra_joint[modeled_year, chrono_period, timestamp]
            >= self.formulation_block.operational_storage_capacity[modeled_year] * self.state_of_charge_min
        )

    def apply_parasitic_loss(self, state_of_charge, period_hrs):
        return state_of_charge * (1 - self.parasitic_loss) ** period_hrs

    # Currently this constraint does not loop, SK will consider if we should change this
    def _soc_intra_tracking_constraint(self, block, modeled_year, dispatch_window, timestamp):
        """
        Tracks intra period status of charging in resources with storage.
        SOC represents the status at the beginning of the current timepoint.
        Therefore SOC[next tp] = SOC[current tp] - provide power[current tp] + increase load[current tp]

        If we are using the default representative/chronological period representation,
        this constraint does not apply for the last timepoint of an intra period:
             1. Any energy left in the last tp is transferred to `Soc_Inter_Period` via `SOC_Inter_Tracking_Constraint`
             2. `Soc_Intra_Period` in the first timepoint of each representative period is anchored to 0 by
                `SOC_Intra_Anchoring_Constraint`

        If either of the following conditions is met, this constraint **does** create a SoC constraint to loop
        the last tp of a rep period to the first tp:
             1. A resource is set to :py:attr:`new_modeling_toolkit.common.resource.Resource.allow_inter_period_sharing`==False
             2. :py:attr:`new_modeling_toolkit.resolve.model_formulation.ResolveCase.rep_period_method`=="manual"

        Args:
            model:
            resource:
            timepoint:

        Returns:

        """

        if (modeled_year, dispatch_window, timestamp) == (
            modeled_year,
            dispatch_window,
            self.formulation_block.model().last_timepoint_in_dispatch_window[dispatch_window],
        ):
            return pyo.Constraint.Skip
        else:
            # TODO: add operating reserves & paired resource/EV energy taken offline related later
            charged_mwh = (
                self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
                * self.formulation_block.model().timestamp_durations_hours[dispatch_window, timestamp]
                * self.charging_efficiency.data.at[timestamp]
            )
            discharged_mwh = (
                self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
                * self.formulation_block.model().timestamp_durations_hours[dispatch_window, timestamp]
                / self.discharging_efficiency.data.at[timestamp]
            )
            return (
                self.formulation_block.soc_intra_period[
                    modeled_year,
                    self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.next((dispatch_window, timestamp)),
                ]
                == self.apply_parasitic_loss(
                    state_of_charge=self.formulation_block.soc_intra_period[modeled_year, dispatch_window, timestamp],
                    period_hrs=self.formulation_block.model().timestamp_durations_hours[dispatch_window, timestamp],
                )
                + charged_mwh
                - discharged_mwh
            )

    def _soc_intra_anchoring_constraint(self, block, modeled_year, dispatch_window):
        """
        Intra-period SOC is 0 in the first timestamp of every dispatch window when inter_period_sharing is allowed
        """
        # If the model is set to loop back around dispatch windows, or if inter-period sharing is enabled in the model
        #  but not for this specific resource, loop the SOC tracking around the boundary of a single dispatch window
        if self.formulation_block.model().dispatch_window_edge_effects == DispatchWindowEdgeEffects.LOOPBACK or (
            self.formulation_block.model().dispatch_window_edge_effects
            == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and not self.allow_inter_period_sharing
        ):
            first_timestamp = self.formulation_block.model().first_timepoint_in_dispatch_window[dispatch_window]
            last_timestamp = self.formulation_block.model().last_timepoint_in_dispatch_window[dispatch_window]
            charged_mwh = (
                self.formulation_block.power_input[modeled_year, dispatch_window, last_timestamp]
                * self.formulation_block.model().timestamp_durations_hours[dispatch_window, last_timestamp]
                * self.charging_efficiency.data.at[last_timestamp]
            )
            discharged_mwh = (
                self.formulation_block.power_output[modeled_year, dispatch_window, last_timestamp]
                * self.formulation_block.model().timestamp_durations_hours[dispatch_window, last_timestamp]
                / self.discharging_efficiency.data.at[last_timestamp]
            )
            constraint = (
                self.formulation_block.soc_intra_period[modeled_year, dispatch_window, first_timestamp]
                == self.apply_parasitic_loss(
                    state_of_charge=self.formulation_block.soc_intra_period[
                        modeled_year, dispatch_window, last_timestamp
                    ],
                    period_hrs=self.formulation_block.model().timestamp_durations_hours[
                        dispatch_window, last_timestamp
                    ],
                )
                + charged_mwh
                - discharged_mwh
            )
        # If the model is set to allow inter-period sharing and the StorageResource is set to allow inter-period
        #  sharing, force the initial intra-period SOC to be 0
        elif (
            self.formulation_block.model().dispatch_window_edge_effects
            == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ):
            constraint = (
                self.formulation_block.soc_intra_period[
                    modeled_year,
                    dispatch_window,
                    self.formulation_block.model().first_timepoint_in_dispatch_window[dispatch_window],
                ]
                == 0
            )

        elif (
            self.formulation_block.model().dispatch_window_edge_effects
            == DispatchWindowEdgeEffects.FIXED_INITIAL_CONDITION
        ):
            constraint = (
                self.formulation_block.state_of_charge[
                    modeled_year,
                    dispatch_window,
                    self.formulation_block.model().first_timepoint_in_dispatch_window[dispatch_window],
                ]
                == self.initial_storage_SOC.at[dispatch_window]
            )

        else:
            raise ValueError(
                f"Unsupported value for DispatchWindowEdgeEffects: {self.formulation_block.model().dispatch_window_edge_effects}"
            )

        return constraint

    def _soc_inter_tracking_constraint(self, block, modeled_year, chrono_period):
        """
        Inter-period SOC should change depending on final intra-period SOC of previous chronological period.

        NOTE: The definition of "get_next_chrono_period" provides that the inter-period SOC of the final
        chronological period is linked to the inter-period SOC of the first chronological period; hence,
        this constraint also enforces the "annual looping" constraint
        """
        if not (
            self.formulation_block.model().dispatch_window_edge_effects
            == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ):
            constraint = self.formulation_block.soc_inter_period[modeled_year, chrono_period] == 0
        else:

            # Get next chronological period, current representative period, and final hour
            next_chrono_period = self.formulation_block.model().CHRONO_PERIODS.nextw(chrono_period)
            dispatch_window = self.formulation_block.model().chrono_periods_map[chrono_period]
            final_hour = self.formulation_block.model().last_timepoint_in_dispatch_window[dispatch_window]
            first_hour = self.formulation_block.model().first_timepoint_in_dispatch_window[dispatch_window]

            # Get charging/discharging in final hour of the chronological period
            charged_mwh = (
                self.formulation_block.power_input[modeled_year, dispatch_window, final_hour]
                * self.charging_efficiency.data.at[final_hour]
            )
            discharged_mwh = (
                self.formulation_block.power_output[modeled_year, dispatch_window, final_hour]
                / self.discharging_efficiency.data.at[final_hour]
            )

            constraint = (
                self.formulation_block.soc_inter_period[modeled_year, next_chrono_period]
                == self.apply_parasitic_loss(
                    self.formulation_block.soc_inter_period[modeled_year, chrono_period],
                    period_hrs=self.formulation_block.model().dispatch_window_duration_hours[dispatch_window],
                )
                + self.apply_parasitic_loss(
                    self.formulation_block.soc_intra_period[modeled_year, dispatch_window, final_hour], period_hrs=1
                )
                + charged_mwh
                - discharged_mwh
                - self.formulation_block.soc_intra_period[modeled_year, dispatch_window, first_hour]
            )

        return constraint

    def _power_input_variable_cost(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """The variable cost incurred by the Resource of consuming power from the grid in a given timepoint.
        This term is not discounted (i.e. it is not multiplied by the discount factor for the relevant model
        year)."""
        return (
            self.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
            * self.variable_cost_power_input.data.at[timestamp]
        )

    def _annual_power_input_variable_cost(self, block, modeled_year: pd.Timestamp):
        """The variable cost incurred by the Resource of consuming power from the grid in a given timepoint.
        This term is not discounted (i.e. it is not multiplied by the discount factor for the relevant model
        year)."""
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.power_input_variable_cost[modeled_year, :, :]
        )

    def _annual_variable_cost(self, block, modeled_year: pd.Timestamp):
        """
        Power output variable cost + power input variable cost
        """
        return (
            block.annual_power_output_variable_cost[modeled_year] + block.annual_power_input_variable_cost[modeled_year]
        )

    def _annual_total_operational_cost(self, block, modeled_year: pd.Timestamp):
        """The total annual operational costs of the Resource. This term is not discounted (i.e. it is not
        multiplied by the discount factor for the relevant model year)."""
        total_operational_cost = (
            super()._annual_total_operational_cost(block=block, modeled_year=modeled_year)
            + self.formulation_block.annual_power_input_variable_cost[modeled_year]
        )

        return total_operational_cost

    # ERM-related expressions and constraints:
    def _erm_charging_efficiency(
        self,
        block: pyo.Block,
        weather_timestamp: pd.Timestamp,
    ):
        # Charging efficiency is redefined on StorageResourceGroup to take the average efficiency
        return self.charging_efficiency.data.at[weather_timestamp]

    def _erm_discharging_efficiency(
        self,
        block: pyo.Block,
        weather_timestamp: pd.Timestamp,
    ):
        # Discharging efficiency is redefined on StorageResourceGroup to take the average efficiency
        return self.discharging_efficiency.data.at[weather_timestamp]

    def _erm_net_power_output(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        return (
            block.erm_power_output[modeled_year, weather_period, weather_timestamp]
            - block.erm_power_input[modeled_year, weather_period, weather_timestamp]
        )

    def _erm_dispatch_cost(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        return (
            block.erm_dispatch_cost_per_MWh
            * block.erm_net_power_output[modeled_year, weather_period, weather_timestamp]
        )

    def _erm_annual_dispatch_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        annual_dispatch_cost = block.model().sum_weather_timestamp_component_slice_to_annual(
            block.erm_dispatch_cost[modeled_year, :, :]
        )
        return annual_dispatch_cost

    def _erm_power_output_max_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        """Constrains the power output for a storage resource to be less than the operational capacity
        scaled by self.pmax_profile.
        """
        return (
            block.erm_power_output[modeled_year, weather_period, weather_timestamp]
            <= block.operational_capacity[modeled_year] * self.pmax_profile.at[weather_timestamp]
        )

    def _erm_power_input_max_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        """Constrains the power input for a storage resource to be less than the operational capacity
        scaled by self.imax_profile."""
        return (
            block.erm_power_input[modeled_year, weather_period, weather_timestamp]
            <= block.operational_capacity[modeled_year] * self.imax_profile.at[weather_timestamp]
        )

    def _erm_soc_tracking_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        """Constrains the state of charge for a given hour to be a reasonable value given the SOC
        for the previous hour. This is based off the amount of charging and discharging, and the known
        efficiencies for charging and discharging for the timestamps in question.

        params:
        block: The Pyomo block to which this constraint applies
        modeled_year: index for the relevant Pyomo variables
        chrono_period: index for the relevant Pyomo variables
        chrono_timestamp: index for the relevant Pyomo variables
        """
        charging_mwh = block.erm_power_input[modeled_year, weather_period, weather_timestamp]
        discharging_mwh = block.erm_power_output[modeled_year, weather_period, weather_timestamp]
        next_hour = block.model().WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS.nextw((weather_period, weather_timestamp))
        return (
            block.erm_state_of_charge[modeled_year, next_hour]
            == block.erm_state_of_charge[modeled_year, weather_period, weather_timestamp]
            + charging_mwh * block.erm_charging_efficiency[weather_timestamp]
            - discharging_mwh / block.erm_discharging_efficiency[weather_timestamp]
        )

    def _erm_soc_max_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        return (
            block.erm_state_of_charge.data.at[modeled_year, weather_period, weather_timestamp]
            <= block.operational_storage_capacity[modeled_year] / block.erm_discharging_efficiency[weather_timestamp]
        )

    def _reliability_capacity_duration_constraint(self, block: pyo.Block, _policy: str, modeled_year: pd.Timestamp):
        """Derate resources with storage by their duration relative to the PRM policy's `reliability_event_length`."""
        policy = self.policies[_policy].instance_to  # self.assets[_asset] is a Linkage. asset is an Asset.
        return (
            block.reliability_capacity[_policy, modeled_year]
            <= block.operational_storage_capacity[modeled_year] / policy.reliability_event_length.data.at[modeled_year]
        )

    def _prod_sim_selected_storage_capacity_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """In production simulation mode, retirement decisions are constrained to the retirement decisions of the
        original capacity expansion problem."""
        return block.selected_storage_capacity == block.chosen_selected_storage_capacity

    def _prod_sim_retired_storage_capacity_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """In production simulation mode, retirement decisions are constrained to the retirement decisions of the
        original capacity expansion problem."""
        return block.retired_storage_capacity[modeled_year] == block.chosen_retired_storage_capacity[modeled_year]

    def _prod_sim_operational_storage_capacity_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """In production simulation mode, operational capacities are constrained to those of the original
        capacity expansion problem."""
        return (
            block.operational_storage_capacity[modeled_year] == block.chosen_operational_storage_capacity[modeled_year]
        )

    def check_if_operationally_equal(self, other):
        equal = (
            super().check_if_operationally_equal(other) and self.duration_constraint == StorageDurationConstraint.FIXED
        )

        return equal

    def save_operational_storage_capacity(self):
        """Save the resulting operational storage capacity after the RESOLVE model has been solved."""
        model_years = self.formulation_block.operational_storage_capacity.extract_values().keys()
        capacities = self.formulation_block.operational_storage_capacity[:].expr()
        self.operational_storage_capacity = ts.NumericTimeseries(
            name="operational_storage_capacity", data=pd.Series(index=model_years, data=capacities)
        )

    def save_selected_storage_capacity(self):
        """Save the resulting selected storage capacity after the RESOLVE model has been solved."""
        self.selected_storage_capacity = self.formulation_block.selected_storage_capacity.value

    def save_retired_storage_capacity(self):
        """Save the resulting retired storage capacity after the RESOLVE model has been solved."""
        model_years = self.formulation_block.retired_storage_capacity.extract_values().keys()
        retirements = list(self.formulation_block.retired_storage_capacity.extract_values().values())
        self.retired_storage_capacity = ts.NumericTimeseries(
            name="retired_storage_capacity", data=pd.Series(index=model_years, data=retirements)
        )

    def save_cumulative_retired_storage_capacity(self):
        """Save the resulting retired storage capacity after the RESOLVE model has been solved."""
        model_years = self.formulation_block.retired_storage_capacity.extract_values().keys()
        cumulative_retirements = list(
            itertools.accumulate(self.formulation_block.retired_storage_capacity.extract_values().values())
        )
        self.cumulative_retired_storage_capacity = ts.NumericTimeseries(
            name="cumulative_retired_storage_capacity", data=pd.Series(index=model_years, data=cumulative_retirements)
        )

    def save_capacity_expansion_results(self):
        super().save_capacity_expansion_results()
        self.save_operational_storage_capacity()
        self.save_selected_storage_capacity()
        self.save_retired_storage_capacity()
        self.save_cumulative_retired_storage_capacity()


class StorageResourceGroup(GenericResourceGroup, StorageResource):
    SAVE_PATH: ClassVar[str] = "resources/storage/groups"
    _NAME_PREFIX: ClassVar[str] = "storage_resource_group"
    _GROUPING_CLASS = StorageResource

    # Redefine duration attribute to allow non-operational groups to not have a defined duration
    duration: Annotated[
        float | None, Metadata(category=FieldCategory.OPERATIONS, show_year_headers=False, units=units.hour)
    ] = Field(
        default=None,
        description="[RESOLVE, RECAP]. Hours of operational time of the battery can operate at a specified power level "
        "before it runs out of energy. Required when resource is an operational group or does not belong "
        "to one.",
        alias="storage_duration",
        title=f"Duration",
        ge=0,
    )

    annualized_storage_capital_cost: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero, up_method="ffill", down_method="mean", default_freq="YS"
    )
    annualized_storage_fixed_om_cost: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero, up_method="ffill", down_method="mean", default_freq="YS"
    )

    power_input_max: Annotated[
        ts.FractionalTimeseries,
        Metadata(category=FieldCategory.OPERATIONS, units=units.unitless, excel_short_title="Max Input Profile"),
    ] = Field(
        default_factory=ts.FractionalTimeseries.one,
        description="Fixed shape of resource's potential power draw (e.g. flat shape for storage resources)."
        " Used in conjunction with "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.curtailable`.",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        alias="increase_load_potential_profile",
        title=f"Max Power Input Profile",
    )

    def revalidate(self):
        super().revalidate()
        if self.has_operational_rules and self.duration is None:
            raise ValueError(
                f"The `StorageResourceGroup` {self.name} is an operational group, so it requires a duration defined."
            )
        if len(self.erm_policies) > 1:
            raise ValueError(
                f"The `StorageResourceGroup` {self.name} is linked to more than one ERM policy, which is not "
                f"allowed. Check your linkages.csv file"
            )

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)
        pyomo_components.update(
            # Operational Storage Capacity of StorageResourceGroups are defined as variables to avoid
            # the writing on member asset build decisions within operational constraints
            operational_storage_capacity=pyo.Var(
                model.MODELED_YEARS,
                doc="Operational Storage Capacity (MWh)",
            ),
            group_operational_storage_capacity_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                rule=self._operational_storage_capacity,
            ),
            cumulative_selected_storage_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._cumulative_selected_storage_capacity,
                doc="Cumulative Selected Storage Capacity (MWh)",
            ),
            selected_storage_capacity=pyo.Expression(
                model.MODELED_YEARS, rule=self._selected_storage_capacity, doc="Selected Storage Capacity (MWh)"
            ),
            retired_storage_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._retired_storage_capacity,
                doc="Retired Storage Capacity (MWh)",
            ),
            cumulative_retired_storage_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._cumulative_retired_storage_capacity,
                doc="Cumulative Retired Storage Capacity (MWh)",
            ),
        )
        pyomo_components.update(
            annual_total_investment_cost=pyo.Expression(
                model.MODELED_YEARS,
                rule=0,
                doc="Annual Total Investment Cost ($)",
            )
        )

        # ERM policy investment rules need to be re-defined because method resolution order dictates that super() will
        # reference _construct_investment_rules() on GenericResourceGroup
        if self.erm_policies:
            pyomo_components.update(
                erm_dispatch_cost_per_MWh=pyo.Param(within=pyo.Reals, initialize=-0.001),
                erm_charging_efficiency=pyo.Expression(model.WEATHER_TIMESTAMPS, rule=self._erm_charging_efficiency),
                erm_discharging_efficiency=pyo.Expression(
                    model.WEATHER_TIMESTAMPS, rule=self._erm_discharging_efficiency
                ),
                erm_power_input=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="ERM Power Input (MW)",
                    initialize=0,
                ),
                erm_power_output=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="ERM Power Output (MW)",
                    initialize=0,
                ),
                erm_net_power_output=pyo.Expression(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_net_power_output,
                    doc="ERM Net Power Output (MW)",
                ),
                erm_power_output_max_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_power_output_max_constraint,
                ),
                erm_power_input_max_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_power_input_max_constraint,
                ),
                erm_state_of_charge=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="ERM SOC (MWh)",
                    initialize=0,
                ),
                erm_soc_tracking_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_soc_tracking_constraint,
                ),
                erm_dispatch_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_dispatch_cost,
                    doc="ERM Storage Dispatch Cost ($)",
                ),
                erm_annual_dispatch_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._erm_annual_dispatch_cost, doc="ERM Annual Storage Dispatch Cost ($)"
                ),
            )

        return pyomo_components

    def _operational_storage_capacity(self, block, modeled_year: pd.Timestamp):
        return (
            pyo.quicksum(
                resource.formulation_block.operational_storage_capacity[modeled_year]
                for resource in self.build_assets.values()
            )
            == block.operational_storage_capacity[modeled_year]
        )

    def _cumulative_selected_storage_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the cumulative capacity built in the current and previous modeled year(s) for all linked Assets."""
        return pyo.quicksum(
            +asset.formulation_block.selected_storage_capacity
            for asset in self.build_assets.values()
            if asset.build_year <= modeled_year
        )

    def _selected_storage_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the capacity built in each modeled year for all linked Assets."""
        model = block.model()
        sorted_years = sorted(model.MODELED_YEARS)
        year_index = sorted_years.index(modeled_year)
        if year_index == 0:
            return self.formulation_block.cumulative_selected_storage_capacity[modeled_year]
        else:
            prev_modeled_year = sorted_years[year_index - 1]
            return (
                self.formulation_block.cumulative_selected_storage_capacity[modeled_year]
                - self.formulation_block.cumulative_selected_storage_capacity[prev_modeled_year]
            )

    def _retired_storage_capacity(self, block, modeled_year: pd.Timestamp):
        return pyo.quicksum(
            resource.formulation_block.retired_storage_capacity[modeled_year] for resource in self.build_assets.values()
        )

    def _cumulative_retired_storage_capacity(self, block, modeled_year: pd.Timestamp):
        model = block.model()
        sorted_years = sorted(model.MODELED_YEARS)
        year_index = sorted_years.index(modeled_year)
        if year_index == 0:
            return self.formulation_block.retired_storage_capacity[modeled_year]
        else:
            prev_modeled_year = sorted_years[year_index - 1]
            return (
                self.formulation_block.retired_storage_capacity[modeled_year]
                + self.formulation_block.cumulative_retired_storage_capacity[prev_modeled_year]
            )

    def _erm_charging_efficiency(
        self,
        block: pyo.Block,
        weather_timestamp: pd.Timestamp,
    ):
        # Take the average efficiency over all member resources for purposes of ERM dispatch
        return sum(
            resource.charging_efficiency.data.at[weather_timestamp] for resource in self.build_assets.values()
        ) / len(
            self.build_assets
        )  # use build_assets to avoid double-counting

    def _erm_discharging_efficiency(
        self,
        block: pyo.Block,
        weather_timestamp: pd.Timestamp,
    ):
        # Take the average efficiency over all member resources for purposes of ERM dispatch
        return sum(
            resource.discharging_efficiency.data.at[weather_timestamp] for resource in self.build_assets.values()
        ) / len(
            self.build_assets
        )  # use build_assets to avoid double-counting
