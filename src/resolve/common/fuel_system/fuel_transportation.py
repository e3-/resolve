from typing import Optional

import pandas as pd
from pydantic import Field

from resolve.common import asset
from resolve.core import linkage
from resolve.core.temporal import timeseries as ts


class FuelTransportation(asset.Asset):
    ######################
    # Mapping Attributes #
    ######################
    policies: dict[str, linkage.Linkage] = {}
    pollutants: dict[str, linkage.Linkage] = {}
    candidate_fuels: dict[str, linkage.Linkage] = {}

    ##############
    # Attributes #
    ##############

    forward_flow_profile: ts.FractionalTimeseries = Field(
        None,
        description="Normalized fixed shape of ElectrofuelTransportaition potential forward flow rating",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
    )

    reverse_flow_profile: ts.FractionalTimeseries = Field(
        None,
        description="Normalized fixed shape of ElectrofuelTransportaition potential reverse flow rating",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
    )

    hurdle_rate_forward_flow_direction: ts.NumericTimeseries = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
    )

    hurdle_rate_reverse_flow_direction: ts.NumericTimeseries = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
    )

    def revalidate(self):
        if self.fuel_zones is None or len(self.fuel_zones) == 0:
            raise ValueError(
                f"FuelTransportation component `{self.name}` must be linked to a FuelZone in order to "
                f"function properly. Please add an FuelTransportationToFuelZone linkage to your linkages.csv file."
            )

        from_zones = [
            fuel_zone_linkage._instance_from.name
            for fuel_zone_linkage in self.fuel_zones.values()
            if fuel_zone_linkage.from_zone
        ]
        if len(from_zones) > 1:
            raise ValueError(
                f"Multiple zones `{from_zones}` are marked as being on the 'from' side of path `{self.name}`."
            )
        elif len(from_zones) == 0:
            raise ValueError(f"No zones assigned as 'from' zone of path `{self.name}`.")

        to_zones = [
            fuel_zone_linkage._instance_from.name
            for fuel_zone_linkage in self.fuel_zones.values()
            if fuel_zone_linkage.to_zone
        ]
        if len(to_zones) > 1:
            raise ValueError(f"Multiple zones `{to_zones}` are marked as being on the 'to' side of path `{self.name}`.")
        elif len(to_zones) == 0:
            raise ValueError(f"No zones assigned as 'tp' zone of path `{self.name}`.")

    ########################################
    # Optimization Constraints/Expressions #
    ########################################

    def Fuel_Transportation_Min_Flow_Constraint(self, model, temporal_settings, model_year, rep_period, hour):
        return model.Transmit_Candidate_Fuel_MMBTU_H[self.name, model_year, rep_period, hour] >= (
            model.Operational_Capacity_In_Model_Year[self.name, model_year]
            * -1
            * self.reverse_flow_profile.slice_by_timepoint(temporal_settings, model_year, rep_period, hour)
        )

    def Fuel_Transportation_Max_Flow_Constraint(self, model, temporal_settings, model_year, rep_period, hour):
        return model.Transmit_Candidate_Fuel_MMBTU_H[self.name, model_year, rep_period, hour] <= (
            model.Operational_Capacity_In_Model_Year[self.name, model_year]
            * self.forward_flow_profile.slice_by_timepoint(temporal_settings, model_year, rep_period, hour)
        )

    def Fuel_Transportation_Transmit_Candidate_Fuel_Rule_Forward(self, model, model_year, rep_period, hour):
        return (
            model.Transmit_Candidate_Fuel_Forward_MMBTU_H[self.name, model_year, rep_period, hour]
            >= model.Transmit_Candidate_Fuel_MMBTU_H[self.name, model_year, rep_period, hour]
        )

    def Fuel_Transportation_Transmit_Candidate_Fuel_Rule_Reverse(self, model, model_year, rep_period, hour):
        return (
            model.Transmit_Candidate_Fuel_Reverse_MMBTU_H[self.name, model_year, rep_period, hour]
            >= -model.Transmit_Candidate_Fuel_MMBTU_H[self.name, model_year, rep_period, hour]
        )

    def Fuel_Transportation_Hurdle_Cost_In_Timepoint_Forward(self, model, model_year, rep_period, hour):
        return model.Transmit_Candidate_Fuel_Forward_MMBTU_H[self.name, model_year, rep_period, hour] * (
            self.hurdle_rate_forward_flow_direction.slice_by_year(model_year) + 0.001
        )

    def Fuel_Transportation_Hurdle_Cost_In_Timepoint_Reverse(self, model, model_year, rep_period, hour):
        return model.Transmit_Candidate_Fuel_Reverse_MMBTU_H[self.name, model_year, rep_period, hour] * (
            self.hurdle_rate_reverse_flow_direction.slice_by_year(model_year) + 0.001
        )

    ########################
    # Optimization Results #
    ########################
    opt_flow_forward_mmbtu_h: Optional[pd.Series] = Field(
        None,
        description="Optimized transmission of power in the forward direction by timepoint, in MMBTU/hr.",
    )
    opt_flow_reverse_mmbtu_h: Optional[pd.Series] = Field(
        None,
        description="Optimized transmission of power in the reverse direction by timepoint, in MMBTU/hr.",
    )
    opt_annual_hurdle_cost_forward_dollars: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized hurdle costs of the transmission line in the forward direction, in dollars.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_hurdle_cost_reverse_dollars: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized hurdle costs of the transmission line in the reverse direction, in dollars.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_flow_forward_mmbtu: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual transmitted power in the forward direction, in MMBTU.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_flow_reverse_mmbtu: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual transmitted power in the reverse direction, in MMBTU.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    # TODO (5/13): These properties only validate the # of linkages when called.
    #  Think whether we can validate # of linkages earlier (during `announce_linkage_to_components`)
    # TODO (2/07/2023): Need to determine if `from_zone` and `to_zone` are correct.
    @property
    def from_zone(self):
        if self.fuel_zones:
            zone = [z for z in self.fuel_zones.values() if z.from_zone][0]
        else:
            zone = None

        return zone

    @property
    def to_zone(self):
        if self.fuel_zones:
            zone = [z for z in self.fuel_zones.values() if z.to_zone][0]
        else:
            zone = None

        return zone

    @property
    def unique_candidate_fuel(self):
        if self.candidate_fuels:
            candidate_fuels = list(self.candidate_fuels.keys())
            if len(candidate_fuels) > 1:
                raise ValueError(
                    f"Multiple candidate fuels ({candidate_fuels}) assigned to FuelTransportation '{self.name}'"
                )
            elif len(candidate_fuels) == 0:
                raise ValueError(f"No candidate fuels assigned to FuelTransportation '{self.name}'")
            else:
                return candidate_fuels[0]
        else:
            raise ValueError(f"No candidate fuels assigned to FuelTransportation '{self.name}'")
