from typing import Optional

import pandas as pd
from pydantic import Field
from pydantic import validator

from new_modeling_toolkit import get_units
from new_modeling_toolkit.common.asset import Asset
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.timeseries import TimeseriesType


class Plant(Asset):
    """
    Define a plant component, defined as something that converts energy from one form into another.
    """

    ######################
    # Mapping Attributes #
    ######################
    candidate_fuels: dict[str, linkage.Linkage] = {}
    reserves: dict[str, linkage.Linkage] = {}

    ###################################
    # Operational Dispatch Attributes #
    ###################################

    allow_inter_period_sharing: bool = Field(
        False,
        description="For resources & fuel storage resources that have chronological energy storage capability, "
        "enable inter-period energy/state-of-charge tracking.",
    )

    provide_power_potential_profile: ts.FractionalTimeseries = Field(
        None,
        description="Fixed shape of resource's potential power output (e.g., solar or wind shape or flat shape"
        "for firm resources or storage resources). Used in conjunction with "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.curtailable`.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        units=get_units("provide_power_potential_profile"),
    )
    provide_power_potential_profile__type: TimeseriesType = TimeseriesType.WEATHER_YEAR
    @validator("provide_power_potential_profile")
    def floor_small_values(cls, provide_power_potential_profile):
        """Remove any ``provide_power_potential_profile`` values below 1e-4."""
        if provide_power_potential_profile is not None:
            provide_power_potential_profile.data = provide_power_potential_profile.data.apply(
                lambda x: 0 if x < 1e-4 else x
            )
        return provide_power_potential_profile

    provide_power_min_profile: ts.FractionalTimeseries = Field(
        None,
        description="Fixed shape of resource's minimum power output (e.g., hydro minimum generation)",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        units=get_units("provide_power_min_profile"),
    )
    provide_power_min_profile__type: TimeseriesType = TimeseriesType.WEATHER_YEAR

    increase_load_potential_profile: ts.FractionalTimeseries = Field(
        None,
        description="Fixed shape of resource's potential power draw (e.g. flat shape for storage resources)."
        " Used in conjunction with "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.curtailable`.",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        units=get_units("increase_load_potential_profile"),
    )
    increase_load_potential_profile__type: TimeseriesType = TimeseriesType.WEATHER_YEAR

    ###################
    # Cost Attributes #
    ###################

    variable_cost_provide_power: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Variable O&M cost per MWh charged ($/MWh).",
        default_freq="H",
        up_method="ffill",
        down_method=None,
        units=get_units("variable_cost_provide_power"),
    )

    variable_cost_increase_load: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Variable O&M cost per MWh generated ($/MWh).",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
        units=get_units("variable_cost_increase_load"),
    )

    ########################
    # Optimization Results #
    ########################
    opt_provide_power_mw: Optional[pd.Series] = Field(
        None, description="Optimized gross generation by timepoint, in MW."
    )
    opt_increase_load_mw: Optional[pd.Series] = Field(
        None, description="Optimized gross consumption by timepoint, in MW."
    )
    opt_annual_provide_power_mwh: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual gross generation, in MWh.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_increase_load_mwh: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual gross consumption, in MWh.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_provide_reserve_mwh: Optional[pd.Series] = Field(
        None,
        description="Optimized reserves provided by reserve product and timepoint, in MW.",
    )
    opt_annual_variable_cost_dollars: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized total annual variable costs, in $.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    @property
    def _variable_cost_provide_power(self):
        return self._map_proforma_data_to_property(
            resource_attr="variable_cost_provide_power",
            proforma_attr="cost_variable_om",
            attr_descriptor="variable O&M cost to provide power ($/MWh)",
            energy_component=True,
        )

    @property
    def _variable_cost_increase_load(self):
        return self._map_proforma_data_to_property(
            resource_attr="variable_cost_increase_load",
            proforma_attr="cost_variable_om",
            attr_descriptor="variable O&M cost to increase load ($/MWh)",
        )

    @property
    def _opt_net_generation_mw(self):
        if self.opt_provide_power_mw is None and self.opt_increase_load_mw is None:
            net_generation_data = None
        else:
            if self.opt_increase_load_mw is None:
                net_generation_data = self.opt_provide_power_mw
            elif self.opt_provide_power_mw is None:
                net_generation_data = self.opt_increase_load_mw
            else:
                net_generation_data = self.opt_provide_power_mw - self.opt_increase_load_mw

            net_generation_data = net_generation_data.rename("_opt_net_generation_mw")

        return net_generation_data

    @property
    def opt_annual_net_generation_mwh(self):
        if self.opt_annual_provide_power_mwh is None and self.opt_annual_increase_load_mwh is None:
            net_generation = None
        else:
            if self.opt_annual_increase_load_mwh is None:
                net_generation_data = self.opt_annual_provide_power_mwh.data
            elif self.opt_annual_provide_power_mwh is None:
                net_generation_data = self.opt_annual_increase_load_mwh.data
            else:
                net_generation_data = self.opt_annual_provide_power_mwh.data - self.opt_annual_increase_load_mwh.data

            net_generation = ts.NumericTimeseries(name="_opt_annual_net_generation_mwh", data=net_generation_data)

        return net_generation

    def revalidate(self):
        assert len(self.zones) > 0
