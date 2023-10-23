from typing import Optional

import pandas as pd
import pyomo.environ as pyo
from pydantic import confloat
from pydantic import Field
from pydantic import PositiveFloat
from pydantic import root_validator

from resolve.common.asset import plant
from resolve.core import linkage
from resolve.core.temporal import timeseries as ts


class FuelStorage(plant.Plant):
    ######################
    # Mapping Attributes #
    ######################

    # Candidate fuels represent input energy sources for compressing hydrogen.
    candidate_fuels: dict[str, linkage.Linkage] = {}

    ##########################
    # Operational Attributes #
    ##########################
    fuel_storage_duration: Optional[PositiveFloat] = Field(
        None,
        description="For resource with storage capacity, the rated duration relative to the nameplate capacity. "
        "Exclusive of "
        ":py:attr:`resolve.fuel_system.fuel_storage.FuelStorage.planned_storage_capacity`.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )
    planned_storage_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Nameplate MMBTU capacity of the resource. "
        "Exclusive of "
        ":py:attr:`resolve.fuel_system.fuel_storage.FuelStorage.duration`.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )

    @root_validator
    def validate_storage_duration(cls, values):
        if values["fuel_storage_duration"] is not None and values["planned_storage_capacity"] is not None:
            raise ValueError(
                f"'{values['name']}': Resource attributes 'fuel_duration' and 'planned_storage_capacity' cannot both be defined simultaneously."
            )
        return values

    fuel_storage_charging_efficiency_mwh_per_mmbtu: float = Field(
        ..., description="Candidate fuel stored per unit of electricity consumed"
    )

    fuel_storage_discharging_efficiency_mwh_per_mmbtu: float = Field(
        ..., description="Candidate fuel produced per unit of electricity consumed"
    )

    """
    Initially included these attributes in order to model storage resources that might need non-electricity fuel to operate.
    I (BKW) am keeping them, but commented out, in the off-chance that we may want to model this.
    """
    # fuel_storage_charging_efficiency_mmbtu_per_mmbtu: Optional[confloat(ge=0, le=1)] = Field(
    #    None,
    #    description="Candidate fuel stored per unit of candidate fuel consumed, unitless",
    #    units=get_units("fuel_storage_charging_efficiency_mmbtu_per_mmbtu"),
    # )

    # fuel_storage_discharging_efficiency_mmbtu_per_mmbtu: Optional[confloat(ge=0, le=1)] = Field(
    #    None,
    #    description="Candidate fuel produced per unit candidate fuel consumed, unitless",
    #    units=get_units("fuel_storage_charging_efficiency_mmbtu_per_mmbtu"),
    # )

    """
    Unnecessary, since we have one required efficiency for charging and discharging
    """
    # @root_validator
    # def validate_charging_efficiencies(cls, values):
    #    if (
    #        values["fuel_storage_charging_efficiency_mmbtu_per_mwh"] is None
    #        and values["fuel_storage_charging_efficiency_mmbtu_per_mmbtu"] is None
    #    ):
    #        raise ValueError(
    #            f"'{values['name']}': At least one of 'fuel_storage_charging_efficiency_mmbtu_per_mwh' or"
    #            f"'fuel_storage_charging_efficiency_mmbtu_per_mmbtu' must be defined."
    #        )

    # @root_validator
    # def validate_discharging_efficiencies(cls, values):
    #    if (
    #        values["fuel_storage_discharging_efficiency_mmbtu_per_mwh"] is None
    #        and values["fuel_storage_discharging_efficiency_mmbtu_per_mmbtu"] is None
    #    ):
    #        raise ValueError(
    #            f"'{values['name']}': At least one of 'fuel_storage_discharging_efficiency_mmbtu_per_mwh' or"
    #            f"'fuel_storage_discharging_efficiency_mmbtu_per_mmbtu' must be defined."
    #        )

    fuel_storage_parasitic_loss: confloat(ge=0, le=1) = Field(
        0.0,
        description="Hourly state of charge losses",
    )

    ###################
    # Cost Attributes #
    ###################
    planned_fuel_storage_capacity_fixed_om_by_model_year: Optional[ts.NumericTimeseries] = Field(
        None,
        description="For the planned portion of the fuel storage capacity, the"
        "ongoing fixed O&M cost ($/MMBTU-year).",
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
    )
    new_fuel_storage_capacity_fixed_cost_dollars_per_mmbtu_yr_by_vintage: Optional[ts.NumericTimeseries] = Field(
        None,
        description="For new fuel storage capacity, the annualized fixed cost of investment. This is an "
        "annualized version of an overnight cost that could include financing costs ($/MMBTU-year).",
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
    )
    new_fuel_storage_fixed_om_by_vintage: Optional[ts.NumericTimeseries] = Field(
        None,
        description="For new fuel storage, the ongoing fixed O&M of each vintage ($/MMBTU-year). Depending on "
        "how fixed costs are calculated user may choose to use an 'all-in' cost via "
        ":py:attr:`resolve.common.fuel_system.fuel_storage.FuelStorage.new_fuel_storage_capacity_fixed_cost_dollars_per_mmbtu_yr_by_vintage`",
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
    )

    def revalidate(self):
        if self.fuel_zones is None or len(self.fuel_zones) == 0:
            raise ValueError(
                f"FuelStorage component `{self.name}` must be linked to a FuelZone in order to "
                f"function properly. Please add an FuelStorageToFuelZone linkage to your linkages.csv file."
            )

    ####################
    # Helper Functions #
    ####################

    def _apply_parasitic_loss(self, SOC, parasitic_loss, period_hrs):
        return SOC * (1 - parasitic_loss) ** period_hrs

    ############################
    # Optimization Expressions #
    ############################
    def Increase_Load_For_Charging_Fuel_Storage_MW(self, model, model_year, rep_period, hour):
        return (
            model.Fuel_Storage_Charging_MMBtu_per_Hr[self.name, model_year, rep_period, hour]
            * self.fuel_storage_charging_efficiency_mwh_per_mmbtu
        )

    def Increase_Load_For_Discharging_Fuel_Storage_MW(self, model, model_year, rep_period, hour):
        return (
            model.Fuel_Storage_Discharging_MMBtu_per_Hr[self.name, model_year, rep_period, hour]
            * self.fuel_storage_charging_efficiency_mwh_per_mmbtu
        )

    def Fuel_Storage_Consumption_Increase_Load_Capacity_In_Timepoint_MW(
        self, model, temporal_settings, model_year, rep_period, hour
    ):
        if self.fuel_storage_charging_efficiency_mwh_per_mmbtu is not None:
            return (
                model.Operational_Capacity_In_Model_Year[self.name, model_year]
                * self.increase_load_potential_profile.slice_by_timepoint(
                    temporal_settings, model_year, rep_period, hour
                )
                * self.fuel_storage_charging_efficiency_mwh_per_mmbtu
            )
        else:
            return model.Operational_Capacity_In_Model_Year[self.name, model, model_year, rep_period, hour] * 0.0

    def Fuel_Storage_Production_Increase_Load_Capacity_In_Timepoint_MW(
        self, model, temporal_settings, model_year, rep_period, hour
    ):
        if self.fuel_storage_discharging_efficiency_mwh_per_mmbtu is not None:
            return (
                model.Operational_Capacity_In_Model_Year[self.name, model_year]
                * self.increase_load_potential_profile.slice_by_timepoint(
                    temporal_settings, model_year, rep_period, hour
                )
                * self.fuel_storage_discharging_efficiency_mwh_per_mmbtu
            )
        else:
            return (
                model.Operational_Fuel_Storage_Volume_In_Model_Year[self.name, model, model_year, rep_period, hour]
                * 0.0
            )

    def Fuel_Storage_SOC_Inter_Intra_Joint(self, model, model_year, chrono_period, hour, rep_period):
        """
        Track SOC in fuel storage resources in all timepoints.
        """
        return (
            model.Fuel_Storage_SOC_Intra_Period[self.name, model_year, rep_period, hour]
            + model.Fuel_Storage_SOC_Inter_Period[self.name, model_year, chrono_period]
        )

    ############################
    # Optimization Constraints #
    ############################
    def Fuel_Storage_Charging_Max_Constraint(self, model, model_year, rep_period, hour):
        return (
            model.Fuel_Storage_Charging_MMBtu_per_Hr[self.name, model_year, rep_period, hour]
            <= model.Operational_Capacity_In_Model_Year[self.name, model_year]
        )

    def Fuel_Storage_Discharging_Max_Constraint(self, model, model_year, rep_period, hour):
        return (
            model.Fuel_Storage_Discharging_MMBtu_per_Hr[self.name, model_year, rep_period, hour]
            <= model.Operational_Capacity_In_Model_Year[self.name, model_year]
        )

    def Fuel_Storage_Duration_Constraint(self, model, model_year):
        if self.fuel_storage_duration is None:
            return pyo.Constraint.Skip
        else:
            return (
                model.Operational_Fuel_Storage_Volume_In_Model_Year[self.name, model_year]
                == model.Operational_Capacity_In_Model_Year[self.name, model_year] * self.fuel_storage_duration
            )

    def Fuel_Storage_Increase_Load_Constraint(self, model, model_year, rep_period, hour):
        return (
            model.Increase_Load_MW[self.name, model_year, rep_period, hour]
            == model.Fuel_Storage_Production_Increase_Load_Capacity_In_Timepoint_MW[
                self.name, model_year, rep_period, hour
            ]
            + model.Fuel_Storage_Consumption_Increase_Load_Capacity_In_Timepoint_MW[
                self.name, model_year, rep_period, hour
            ]
        )

    # ALL ENERGY UNITS ARE MMBTU!!!
    def Fuel_Storage_SOC_Inter_Intra_Max_Constraint(self, model, model_year, chrono_period, hour):
        """
        SOC cannot exceed fuel storage's total MMBTU capacity
        This would be divided by discharging efficiency if the discharging efficiency was MMBTU per MMBTU.
        """
        return (
            model.Fuel_Storage_SOC_Inter_Intra_Joint[self.name, model_year, chrono_period, hour]
            <= model.Operational_Fuel_Storage_Volume_In_Model_Year[self.name, model_year]
        )

    def Fuel_Storage_SOC_Inter_Intra_Min_Constraint(self, model, model_year, chrono_period, hour):
        """
        SOC cannot be less than zero
        """
        return model.Fuel_Storage_SOC_Inter_Intra_Joint[self.name, model_year, chrono_period, hour] >= 0

    def Fuel_Storage_SOC_Intra_Anchoring_Constraint(self, model, model_year, rep_period, hour):
        if (
            self.allow_inter_period_sharing
            and (model_year, rep_period, hour) == model.first_timepoint_of_period[model_year, rep_period]
        ):
            return model.Fuel_Storage_SOC_Intra_Period[self.name, model_year, rep_period, hour] == 0
        else:
            return pyo.Constraint.Skip

    def Fuel_Storage_SOC_Intra_Tracking_Constraint(
        self, model, model_year, rep_period, hour, temporal_settings, next_rep_timepoint
    ):
        if (model_year, rep_period, hour) == model.last_timepoint_of_period[model_year, rep_period]:
            constraint = pyo.Constraint.Skip
        else:
            charged_mmbtu = model.Fuel_Storage_Charging_MMBtu_per_Hr[self.name, model_year, rep_period, hour]

            discharged_mmbtu = model.Fuel_Storage_Discharging_MMBtu_per_Hr[self.name, model_year, rep_period, hour]

            constraint = (
                model.Fuel_Storage_SOC_Intra_Period[
                    self.name,
                    next_rep_timepoint,
                ]
                == self._apply_parasitic_loss(
                    model.Fuel_Storage_SOC_Intra_Period[self.name, model_year, rep_period, hour],
                    self.fuel_storage_parasitic_loss,
                    temporal_settings.timesteps[hour],
                )
                + charged_mmbtu
                - discharged_mmbtu
            )

        return constraint

    # Commenting this out since we're not modeling fuel combustion for fuel storage operation
    # def Fuel_Storage_Electricity_Input_And_Candidate_Fuel_Consumption_Constraint(
    #    self, model, temporal_settings, model_year, rep_period, hour
    # ):
    #    """
    #    Ensure that fuel consumed by storage resource using candidate fuel efficiency is the same as fuel consumed
    #    by storage using electricity.
    #    """
    #    if (
    #        self.fuel_storage_charging_efficiency_mmbtu_per_mmbtu is not None
    #        and self.fuel_storage_charging_efficiency_mmbtu_per_mwh is not None
    #    ):
    #        charged_mmbtu_1 = (
    #            model.Fuel_Storage_Candidate_Fuel_Consumption_In_Timepoint[
    #                self.name, model_year, rep_period, hour
    #            ]
    #            * temporal_settings.timesteps[hour]
    #            * self.fuel_storage_charging_efficiency_mmbtu_per_mmbtu
    #        )

    #        charged_mmbtu_2 = (
    #            model.Increase_Load_For_Charging_Fuel_Storage_MW[self.name, model_year, rep_period, hour]
    #            * temporal_settings.timesteps[hour]
    #            * self.fuel_storage_charging_efficiency_mmbtu_per_mwh
    #        )
    #        return charged_mmbtu_2 == charged_mmbtu_1
    #    else:
    #        return pyo.Constraint.Skip

    # Commenting this out since we're not modeling fuel combustion for fuel storage operation
    # def Fuel_Storage_Electricity_Input_And_Candidate_Fuel_Production_Constraint(
    #    self, model, temporal_settings, model_year, rep_period, hour
    # ):
    #    """
    #    Ensure that fuel produced by storage resource using candidate fuel efficiency is the same as fuel produced
    #    by storage using electricity.
    #    """
    #    if (
    #        self.fuel_storage_discharging_efficiency_mmbtu_per_mmbtu is not None
    #        and self.fuel_storage_discharging_efficiency_mmbtu_per_mwh is not None
    #    ):
    #        discharged_mmbtu_1 = (
    #            model.Fuel_Storage_Candidate_Fuel_Consumption_In_Timepoint[
    #                self.name, model_year, rep_period, hour
    #            ]
    #            * temporal_settings.timesteps[hour]
    #            * self.fuel_storage_discharging_efficiency_mmbtu_per_mmbtu
    #        )

    #        discharged_mmbtu_2 = (
    #            model.Increase_Load_For_Discharging_Fuel_Storage_MW[self.name, model_year, rep_period, hour]
    #            * temporal_settings.timesteps[hour]
    #            * self.fuel_storage_discharging_efficiency_mmbtu_per_mwh
    #        )
    #        return discharged_mmbtu_2 == discharged_mmbtu_1
    #    else:
    #        return pyo.Constraint.Skip

    def Fuel_Storage_SOC_Inter_Tracking_Constraint(
        self, model, model_year, chrono_period, next_chrono_period, rep_period
    ):
        final_hour = max(model.HOURS)
        first_hour = min(model.HOURS)

        charged_mmbtu = model.Fuel_Storage_Charging_MMBtu_per_Hr[self.name, model_year, rep_period, final_hour]
        # Commenting this out, since we're not assuming fuel combustion for storage operation
        # else:
        #    charged_mmbtu = (
        #        model.Fuel_Storage_Candidate_Fuel_Consumption_In_Timepoint[
        #            self.name, model_year, rep_period, final_hour
        #        ]
        #        * self.fuel_storage_charging_efficiency_mmbtu_per_mmbtu
        #    )

        discharged_mmbtu = model.Fuel_Storage_Discharging_MMBtu_per_Hr[self.name, model_year, rep_period, final_hour]
        # Commenting this out, since we're not assuming fuel combustion for storage operation
        # else:
        #    discharged_mmbtu = (
        #        model.Fuel_Storage_Candidate_Fuel_Production_In_Timepoint[
        #            self.name, model_year, rep_period, final_hour
        #        ]
        #        * self.fuel_storage_discharging_efficiency_mmbtu_per_mmbtu
        #    )

        constraint = (
            model.Fuel_Storage_SOC_Inter_Period[self.name, model_year, next_chrono_period]
            == self._apply_parasitic_loss(
                model.Fuel_Storage_SOC_Inter_Period[self.name, model_year, chrono_period],
                self.fuel_storage_parasitic_loss,
                model.timepoints_per_period,
            )
            + self._apply_parasitic_loss(
                model.Fuel_Storage_SOC_Intra_Period[self.name, model_year, rep_period, final_hour],
                self.fuel_storage_parasitic_loss,
                1.0,
            )
            + charged_mmbtu
            - discharged_mmbtu
            - model.Fuel_Storage_SOC_Intra_Period[self.name, model_year, rep_period, first_hour]
        )

        return constraint

    def Fuel_Storage_SOC_Inter_Zero_Constraint(self, model, model_year, chrono_period):
        if self.allow_inter_period_sharing:
            return pyo.Constraint.Skip
        else:
            return model.Fuel_Storage_SOC_Inter_Period[self.name, model_year, chrono_period] == 0

    def Fuel_Storage_Simultaneous_Charging_Constraint(self, model, model_year, rep_period, hour):
        """
        Limit simultaneous charging & discharging for fuel storage resources.
        Split 50-50 in a given hour.
        """
        # TODO: Add the appropriate set of reserves for this resource
        return (
            model.Increase_Load_For_Charging_Fuel_Storage_MW[self.name, model_year, rep_period, hour]
            + model.Increase_Load_For_Discharging_Fuel_Storage_MW[self.name, model_year, rep_period, hour]
            <= model.Plant_Increase_Load_Capacity_In_Timepoint_MW[self.name, model_year, rep_period, hour]
        )

    # TODO: Do we need a constraint that ensures that we don't charge+discharge together more than what is possible? Something like flow_in+flow_out<=max_flow?

    ########################
    # Optimization Results #
    ########################
    # TODO: Do we need to account for electricity (or other fuel) consumption for storage resources?
    opt_increase_load_charging_mw: Optional[pd.Series] = Field(
        None, description="Optimized gross consumption by timepoint for charging storage reservoir, in MW."
    )
    opt_increase_load_discharging_mw: Optional[pd.Series] = Field(
        None, description="Optimized gross consumption by timepoint for discharging storage reservoir, in MW."
    )
    opt_annual_increase_load_charging_mwh: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual gross consumption for charging storage reservoir, in MWh.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_increase_load_discharging_mwh: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual gross consumption for discharging storage reservoir, in MWh.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_soc_intra_period: Optional[pd.Series] = Field(
        None, description="Optimized intra-period SOC by timepoint, in MMBTU."
    )
    opt_soc_inter_period: Optional[pd.Series] = Field(
        None, description="Optimized inter-period SOC by timepoint, in MMBTU."
    )
    opt_soc_inter_intra_joint: Optional[pd.Series] = Field(
        None, description="Optimized inter-intra-period SOC by timepoint, in MMBTU."
    )
    opt_operational_new_storage_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized operational fuel energy capacity of new build storage by model year, in MMBTU.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_operational_planned_storage_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized operational fuel energy capacity of planned build storage by model year, in MMBTU.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    @property
    def opt_total_operational_storage_capacity(self):
        total_operational_capacity = self.sum_timeseries_attributes(
            attributes=["opt_operational_planned_storage_capacity", "opt_operational_new_storage_capacity"],
            name="opt_total_operational_storage_capacity",
            skip_none=True,
        )

        return total_operational_capacity

    @property
    def opt_retired_storage_capacity(self):
        if self.planned_storage_capacity is None:
            return None
        else:
            return ts.NumericTimeseries(
                name="opt_retired_storage_capacity",
                data=self.planned_storage_capacity.data - self.opt_operational_planned_storage_capacity.data,
            )
