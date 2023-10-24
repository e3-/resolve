import calendar
from typing import Optional
from typing import Union

import pandas as pd
from loguru import logger
from pydantic import Field
from pydantic import root_validator
from resolve import get_units
from resolve.core import component
from resolve.core import linkage
from resolve.core.temporal import timeseries as ts

NUM_LEAP_YEAR_HOURS = 366 * 24
NUM_NON_LEAP_YEAR_HOURS = 365 * 24


class Load(component.Component):
    ######################
    # Boolean Attributes #
    ######################
    scale_by_capacity: bool = False
    scale_by_energy: bool = False
    policies: dict[str, linkage.Linkage] = {}

    profile: Optional[ts.NumericTimeseries] = Field(default_freq="H", up_method="interpolate", down_method="mean")
    profile__type: ts.TimeseriesType = ts.TimeseriesType.WEATHER_YEAR

    profile_model_years: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="H", up_method="interpolate", down_method="mean"
    )

    # Will be filled later...update description
    scaled_profile_by_modeled_year: dict = {}

    annual_peak_forecast: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="max", units=get_units("annual_peak_forecast")
    )

    annual_energy_forecast: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="sum", units=get_units("annual_energy_forecast")
    )
    # TODO: I want this to default to 1 but that breaks with resampling
    td_losses_adjustment: Optional[ts.NumericTimeseries] = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="max",
        description="T&D loss adjustment to gross up to system-level loads. For example, a DER may be able to serve "
        "8% more load (i.e., 1.08) than an equivalent bulk system resource due to T&D losses. Adjustment factor is "
        "**directly multiplied** against load (as opposed to 1 / (1 + ``td_losses_adjustment``).",
    )

    zones: dict[str, linkage.Linkage] = {}
    devices: dict[str, linkage.Linkage] = {}
    energy_demand_subsectors: dict[str, linkage.Linkage] = {}
    reserves: dict[str, linkage.Linkage] = {}

    @root_validator()
    def validate_profile_weather_or_model_year(cls, values):
        """Ensure that users only provide one profile (either ``profile`` or ``profile_weather_years``."""
        if values["profile__type"] == ts.TimeseriesType.MODELED_YEAR:
            values["profile_model_years"] = values["profile"].copy(deep=True)
            values["profile"] = None

        if values["profile_model_years"]:
            assert (
                values["profile"] is None
            ), f"For {values['name']}: Both `profile` and `profile_model_years` provided. Only one can be defined at a time."

        if values["profile"]:
            assert (
                values["profile_model_years"] is None
            ), f"For {values['name']}: Both `profile` and `profile_model_years` provided. Only one can be defined at a time."

        if values["profile_model_years"] is None and values["profile"] is None:
            raise ValueError(f"For {values['name']}: Neither `profile` nor `profile_model_years` provided.")
        return values

    @root_validator()
    def validate_td_annual(cls, values):
        if values["td_losses_adjustment"] is None:
            if values["annual_energy_forecast"] is None and values["annual_peak_forecast"] is None:
                pass
            else:
                logger.warning(f"Setting T&D Losses for {values['name']} to 0%")
                index = (
                    values["annual_energy_forecast"].data.index
                    if values["annual_energy_forecast"]
                    else values["annual_peak_forecast"].data.index
                )
                values["td_losses_adjustment"] = ts.NumericTimeseries(
                    name=f"{values['name']}_td_losses_adjustment",
                    data=pd.Series(data=1.0, index=index),
                )
        return values

    def normalize_profile(self, normalize_by):
        """Normalize profile by capacity or by energy"""

        if normalize_by == "capacity":
            logger.info("Normalizing by capacity - setting profile maximum to 1.")
            self.profile.data /= self.profile.data.max()

        elif normalize_by == "energy":
            logger.info("Normalizing by energy - setting annual profile sum to 1.")
            self.profile.data *= (
                len(self.profile.data.index.year.unique()) / self.profile.data.sum()
            )  # Sets profile sum = number of years

    def forecast_load(
        self,
        *,
        modeled_years: tuple[int, int],
        weather_years: tuple[int, int],
        custom_scalars: Optional[pd.Series] = None,
    ):
        """
        Calculate the scaling coefficient and scaling offset for the load series in order to scale them to any future
        between the first model year and last model year. The coefficient and offset is determine by the future peak
        load series and energy series, and the load scaling method defined by the user.
        """
        first_model_year, last_model_year = modeled_years

        if custom_scalars is not None:
            model_years_to_scale = custom_scalars.index.year.unique()
        else:
            model_years_to_scale = range(first_model_year, last_model_year + 1)

        for model_year in model_years_to_scale:
            to_peak = (
                self.annual_peak_forecast.data[self.annual_peak_forecast.data.index.year == model_year].values[0]
                if self.scale_by_capacity
                else self.scale_by_capacity
            )
            to_energy = (
                self.annual_energy_forecast.data[self.annual_energy_forecast.data.index.year == model_year].values[0]
                if self.scale_by_energy
                else self.scale_by_energy
            )
            if custom_scalars is not None and self.name in custom_scalars.columns:
                to_energy *= custom_scalars.loc[custom_scalars.index.year == model_year, self.name].squeeze()

            leap_year = calendar.isleap(model_year)

            if self.profile:
                profile_to_scale = self.profile
            elif self.profile_model_years:
                profile_to_scale = self.profile_model_years.copy(deep=True)
                profile_to_scale.data = self.profile_model_years.data[
                    self.profile_model_years.data.index.year == model_year
                ]
                profile_to_scale.resample_simple_extend_years(weather_years)

            td_losses = self.td_losses_adjustment.data.loc[
                self.td_losses_adjustment.data.index.year == model_year
            ].values[
                0
            ]  # get TD losses

            # Scale profile & save to the ``scaled_profile_by_modeled_year`` dictionary
            new_profile = Load.scale_load(profile_to_scale, to_peak, to_energy, td_losses, leap_year)
            self.scaled_profile_by_modeled_year.update({model_year: new_profile})

    @staticmethod
    def scale_load(
        profile: ts.NumericTimeseries,
        to_peak: Union[bool, float],
        to_energy: Union[bool, float],
        td_losses_adjustment: float,
        leap_year: bool,
    ) -> ts.NumericTimeseries:
        """Scale timeseries by energy and/or median peak.

        Scaling to energy assumes ``to_energy`` forecast value will match whether it is/is not a leap year.
        In other words, the energy forecast for a leap day includes an extra day's worth of energy.

        Args:
            profile: Hourly timeseries to be scaled
            to_peak: Median annual peak to be scaled to
            to_energy: Mean annual energy to be scaled to
            td_losses_adjustment: T&D losses adjustment (simple scalar on load profile)
            leap_year: If year being scaled to is a leap year (affecting energy scaling)

        Returns:
            new_profile: Scaled hourly timeseries
        """

        profile_median_peak = profile.data.groupby(profile.data.index.year).max().median()
        profile_mean_annual_energy = profile.data.groupby(profile.data.index.year).sum().mean()

        # calculate the average annual energy of the provided weather years
        n_hours_in_forecast = NUM_LEAP_YEAR_HOURS if leap_year else NUM_NON_LEAP_YEAR_HOURS

        if to_energy is False and to_peak is False:
            scale_multiplier = td_losses_adjustment
            scale_offset = 0
        elif to_energy is False:
            if profile_median_peak == 0:
                logger.debug(
                    f"Attempting to scale load profile `{profile.name}` by peak when the existing median peak is 0. "
                    f"Scaling factor will be set to 0."
                )
                scale_multiplier = 0.0
            else:
                scale_multiplier = to_peak * td_losses_adjustment / profile_median_peak
            scale_offset = 0
            logger.debug(f"Scaling {profile.name} to median peak.")
        elif to_peak is False:
            if profile_median_peak == 0:
                logger.debug(
                    f"Attempting to scale load profile `{profile.name}` by energy when the existing mean annual energy "
                    f"is 0. Scaling factor will be set to 0"
                )
                scale_multiplier = 0.0
            else:
                scale_multiplier = to_energy * td_losses_adjustment / profile_mean_annual_energy
            scale_offset = 0
            logger.debug(f"Scaling {profile.name} to mean annual energy.")
        else:
            scale_multiplier = td_losses_adjustment * (
                (to_peak - (to_energy / n_hours_in_forecast))
                / (profile_median_peak - (profile_mean_annual_energy / n_hours_in_forecast))
            )
            scale_offset = to_peak - scale_multiplier * profile_median_peak
            logger.debug(f"Scaling {profile.name} to median peak & mean annual energy.")
            if to_peak < 0:
                logger.warning("Scaling to peak & energy with a negative peak may not work as intended.")

        new_profile = profile.copy(deep=True)
        new_profile.data = scale_multiplier * profile.data + scale_offset

        new_profile_median_peak = new_profile.data.groupby(profile.data.index.year).max().median()
        new_profile_mean_energy = new_profile.data.mean() * n_hours_in_forecast
        logger.debug("Scaled load profile median peak: {:.0f} MW".format(new_profile_median_peak))
        logger.debug("Scaled load profile mean annual energy: {:.0f} MW".format(new_profile_mean_energy))

        return new_profile

    def get_load(self, temporal_settings, model_year, period, hour):
        """
        Based on the model year, first find the future load series belonging to that model year. And based on the
        period and hour, query the specific hourly load for that hour in the model year.
        Args:
            system: System.system. current power system
            model_year: int. model year being queried
            period:  model period being queried
            hour: model hour being queried

        Returns:  int. load for the tp under query.

        """

        return self.scaled_profile_by_modeled_year[model_year].slice_by_timepoint(
            temporal_settings, model_year, period, hour
        )

    def revalidate(self):
        if (self.devices or self.energy_demand_subsectors) and self.annual_energy_forecast:
            raise ValueError(
                "Error in load component {}: annual energy forecast can not be specified if load component is linked "
                "to a device or energy demand subsector".format(self.name)
            )
