from typing import Optional

import pandas as pd
from pydantic import Field

from new_modeling_toolkit import get_units
from new_modeling_toolkit.common import asset
from new_modeling_toolkit.core import dir_str
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.temporal import timeseries as ts


class TXPath(asset.Asset):
    ######################
    # Mapping Attributes #
    ######################
    zones: Optional[dict[str, linkage.ZoneToTransmissionPath]] = None
    policies: dict[str, linkage.Linkage] = {}
    pollutants: dict[str, linkage.Linkage] = {}

    ##############
    # Attributes #
    ##############

    forward_rating_profile: ts.FractionalTimeseries = Field(
        None,
        description="Normalized fixed shape of TXPath's potential forward rating",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        units=get_units("forward_rating_profile"),
    )

    reverse_rating_profile: ts.FractionalTimeseries = Field(
        None,
        description="Normalized fixed shape of TXPath's potential reverse rating",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        units=get_units("reverse_rating_profile"),
    )

    hurdle_rate_forward_direction: ts.NumericTimeseries = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("hurdle_rate_forward_direction"),
    )
    hurdle_rate_reverse_direction: ts.NumericTimeseries = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("hurdle_rate_reverse_direction"),
    )

    ########################
    # Optimization Results #
    ########################
    opt_transmit_power_forward_mw: Optional[pd.Series] = Field(
        None,
        description="Optimized transmission of power in the forward direction by timepoint, in MW.",
    )
    opt_transmit_power_reverse_mw: Optional[pd.Series] = Field(
        None,
        description="Optimized transmission of power in the reverse direction by timepoint, in MW.",
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
    opt_forward_flow_to_zone_value: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized value of forward direction transmission flows, valued at 'to zone' energy price.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_forward_flow_from_zone_value: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized value of forward direction transmission flows, valued at 'from zone' energy price.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_reverse_flow_to_zone_value: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized value of reverse direction transmission flows, valued at 'to zone' energy price.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_reverse_flow_from_zone_value: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized value of reverse direction transmission flows, valued at 'from zone' energy price.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_transmit_power_forward_mwh: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual transmitted power in the forward direction, in MWh.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_transmit_power_reverse_mwh: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual transmitted power in the reverse direction, in MWh.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    # TODO (5/13): These properties only validate the # of linkages when called.
    #  Think whether we can validate # of linkages earlier (during `announce_linkage_to_components`)
    @property
    def from_zone(self):
        if self.zones:
            zones = [z for z in self.zones.values() if z.from_zone]
            if len(zones) > 1:
                raise ValueError(
                    f"Multiple zones ({zones}) are marked as being on the 'from' side of path '{self.name}'."
                )
            elif len(zones) == 0:
                raise ValueError("No zones assigned as 'from' zone of path '{self.name}'.")
            else:
                # Return first (only) zone in the list
                return zones[0]

    @property
    def to_zone(self):
        if self.zones:
            zones = [z for z in self.zones.values() if z.to_zone]
            if len(zones) > 1:
                raise ValueError(
                    f"Multiple zones ({zones}) are marked as being on the 'to' side of path '{self.name}'."
                )
            elif len(zones) == 0:
                raise ValueError("No zones assigned as 'to' zone of path '{self.name}'.")
            else:
                # Return first (only) zone in the list
                return zones[0]


if __name__ == "__main__":
    test_networks_csv = TXPath.from_dir(data_path=dir_str.data_dir / "interim" / "tx_paths")
    print(f"From csv file: {test_networks_csv}")
