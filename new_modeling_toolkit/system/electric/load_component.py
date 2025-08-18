import calendar
import copy
from typing import Annotated
from typing import ClassVar
from typing import Optional
from typing import Union

import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pydantic import computed_field
from pydantic import Field
from pydantic import model_validator

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.settings import TemporalSettings
from new_modeling_toolkit.core.utils.core_utils import timer

NUM_LEAP_YEAR_HOURS = 366 * 24
NUM_NON_LEAP_YEAR_HOURS = 365 * 24


class Load(component.Component):
    # TODO: Subclass Load from Demand
    SAVE_PATH: ClassVar[str] = "loads"

    ############
    # Linkages #
    ############

    # TODO: Remove duplicate linkages that already exist on Demand
    zones: Annotated[dict[str, linkage.LoadToZone], Metadata(linkage_order="to")] = {}
    reserves: Annotated[dict[str, linkage.LoadToReserve], Metadata(linkage_order="to")] = {}
    # TODO: should these all be AllToPolicy linkages or the subclasses?
    emissions_policies: dict[str, linkage.AllToPolicy] = Field(default_factory=dict)
    annual_energy_policies: dict[str, linkage.AllToPolicy] = Field(default_factory=dict)
    hourly_energy_policies: dict[str, linkage.AllToPolicy] = Field(default_factory=dict)
    prm_policies: Annotated[dict[str, linkage.AllToPolicy], Metadata(linkage_order="to")] = Field(default_factory=dict)
    erm_policies: dict[str, linkage.AllToPolicy] = Field(default_factory=dict)
    devices: dict[str, linkage.Linkage] = Field(default_factory=dict)
    energy_demand_subsectors: dict[str, linkage.Linkage] = Field(default_factory=dict)

    ######################
    # Boolean Attributes #
    ######################
    # TODO: Remove attributes that are on Demand
    scale_by_capacity: bool = Field(
        False,
        description="If true, calculate model year profiles by scaling profile to median annual peak",
        title="Scale by Median Peak",
        alias="scale_by_peak",
    )
    scale_by_energy: bool = Field(
        False,
        description="If true, calculate model year profiles by scaling profile to mean annual energy",
        title="Scale by Mean Annual Energy",
    )

    #########################
    # Timeseries Attributes #
    #########################
    profile: Annotated[
        ts.NumericTimeseries | None, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Profile")
    ] = Field(
        None,
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        description="Weather year(s) load profile to be scaled. Must have either weather year OR model year profile, but not both.",
        title=f"Weather Year-indexed Profile",
    )

    profile_model_years: Annotated[
        ts.NumericTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Modeled Year Profile"),
    ] = Field(
        None,
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        description="Model year(s) load profile to be scaled. Datetime index should include modeled years. Must have either weather year OR model year profile, but not both.",
        title=f"Modeled Year-indexed Profile",
    )

    annual_peak_forecast: Annotated[
        ts.NumericTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, units=units.megawatt, excel_short_title="Peak"),
    ] = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="max",
        title=f"Annual Median Peak Forecast",
    )
    annual_energy_forecast: Annotated[
        ts.NumericTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, units=units.megawatt * units.hour, excel_short_title="Forecast"),
    ] = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="sum",
        title=f"Annual Energy Forecast",
    )

    td_losses_adjustment: Annotated[
        ts.NumericTimeseries | None, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="T&D Factor")
    ] = Field(
        default_factory=ts.FractionalTimeseries.one,
        default_freq="YS",
        up_method="interpolate",
        down_method="max",
        description="T&D loss adjustment to gross up to system-level loads. For example, a DER may be able to serve "
        "8% more load (i.e., 1.08) than an equivalent bulk system resource due to T&D losses. Adjustment factor is "
        "**directly multiplied** against load (as opposed to 1 / (1 + ``td_losses_adjustment``).",
    )

    model_year_profiles: dict[int, ts.NumericTimeseries] = Field(
        {}, description="Model year profiles scaled to annual peak and/or annual energy forecasts"
    )

    @model_validator(mode="after")
    def validate_profile_weather_or_model_year(self) -> "Load":
        """Ensure that users only provide one profile (either ``profile`` or ``profile_model_years``)."""
        assert (self.profile and not self.profile_model_years) or (
            not self.profile and self.profile_model_years
        ), f"For {self.name}: Only one of either `profile` or `profile_model_years` can be defined."
        return self

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
    def timeseries_attrs(self):
        timeseries_attrs = super().timeseries_attrs
        timeseries_attrs.remove("model_year_profiles")

        return timeseries_attrs

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
        """This property defines the ordering of columns in the component's annual results summary out of Resolve.
        The name of the model field or formulation_block pyomo component can be used.
        """
        return [
            "zone_names_string",
            "rep_annual_energy",
            "annual_energy",
            "rep_annual_peak",
            "annual_peak",
        ]

    def revalidate(self):
        if ((len(self.devices) > 0) or (len(self.energy_demand_subsectors) > 0)) and (
            self.annual_energy_forecast is not None
        ):
            raise ValueError(
                "Error in load component {}: annual energy forecast can not be specified if load component is linked "
                "to a device or energy demand subsector".format(self.name)
            )

    def resample_ts_attributes(
        self,
        modeled_years: tuple[int, int],
        weather_years: tuple[int, int],
        resample_weather_year_attributes=True,
        resample_non_weather_year_attributes=True,
    ):
        super().resample_ts_attributes(
            modeled_years=modeled_years,
            weather_years=weather_years,
            resample_weather_year_attributes=resample_weather_year_attributes,
            resample_non_weather_year_attributes=resample_non_weather_year_attributes,
        )
        if len(self.model_year_profiles) > 0:
            self.model_year_profiles = {}
            self.forecast_load(modeled_years=modeled_years, weather_years=weather_years)
        else:
            self.model_year_profiles = {}

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

    # TODO: Refactor methods and attributes with "load" in their names to just be aliases of similar Demand methods.
    #  See commented example below
    # @property
    # def forecast_load(self):
    #     return self.forecast_demand

    def forecast_load(
        self,
        modeled_years: tuple[int, int],
        weather_years: tuple[int, int],
        custom_scalars: Optional[pd.Series] = None,
    ):
        """
        Calculate the scaling coefficient and scaling offset for the load series in order to scale them to any future
        between the first model year and last model year. The coefficient and offset is determine by the future peak
        load series and energy series, and the load scaling method defined by the user.

        Args:
            modeled_years: tuple first model year to last model year
            weather_years: tuple first weather year to last weather year (only used for profile_modeled_years)
            custom_scalars: Optional series of scalars to be applied to annual energy forecast. Only used if `scale_by_energy` is true. Intended to ensure annual energy forecast is still true when weighted dispatch windows are applied.

        Returns: Updated `modeled_year_profile` dict

        """
        first_model_year, last_model_year = modeled_years

        if custom_scalars is not None:
            modeled_years_to_scale = custom_scalars.index.year.unique()
        else:
            # todo: should this be just for the years we are running?
            modeled_years_to_scale = range(first_model_year, last_model_year + 1)

        for model_year in modeled_years_to_scale:
            to_peak = (
                self.annual_peak_forecast.slice_by_year(model_year)
                if self.scale_by_capacity
                else self.scale_by_capacity
            )
            to_energy = (
                self.annual_energy_forecast.slice_by_year(model_year) if self.scale_by_energy else self.scale_by_energy
            )

            if custom_scalars is not None and to_energy is not False:
                to_energy *= custom_scalars.at[f"{model_year}-01-01"]

            leap_year = calendar.isleap(model_year)

            if self.profile_model_years:
                profile_to_scale = copy.deepcopy(self.profile_model_years)
                profile_to_scale.data = self.profile_model_years.data.at[str(model_year)]
                if weather_years:
                    profile_to_scale.resample_simple_extend_years((min(weather_years), max(weather_years)))
            else:
                profile_to_scale = self.profile

            # Scale profile & save to the ``modeled_year_profiles`` dictionary
            new_profile = Load.scale_load(
                profile_to_scale, to_peak, to_energy, self.td_losses_adjustment.slice_by_year(model_year), leap_year
            )
            self.model_year_profiles.update({model_year: new_profile})

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
            scale_multiplier = to_peak * td_losses_adjustment / profile_median_peak
            scale_offset = 0
            logger.debug(f"Scaling {profile.name} to median peak.")
        elif to_peak is False:
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

        new_profile = copy.deepcopy(profile)
        new_profile.data = scale_multiplier * profile.data + scale_offset

        new_profile_median_peak = new_profile.data.groupby(profile.data.index.year).max().median()
        new_profile_mean_energy = new_profile.data.mean() * n_hours_in_forecast
        logger.debug("Scaled load profile median peak: {:.0f} MW".format(new_profile_median_peak))
        logger.debug("Scaled load profile mean annual energy: {:.0f} MWh".format(new_profile_mean_energy))

        return new_profile

    def get_load(self, modeled_year: int, weather_year_timestamp: pd.Timestamp):
        """
        Based on the model year, first find the future load series belonging to that model year. And based on the
        period and hour, query the specific hourly load for that hour in the model year.
        Args:
            system: System.system. current power system
            modeled_year: int. model year being queried
            weather_year_timestamp: model hour being queried

        Returns:  int. load for the tp under query.

        """

        return self.model_year_profiles[modeled_year].data.at[weather_year_timestamp]

    def _adjusted_hourly_load(self, temporal_settings) -> pd.DataFrame:
        """

        Args:
            temporal_settings: TemporalSettings object with model year and dispatch window weights

        Returns: Weighted hourly loads within dispatch windows defined in temporal settings

        """
        modeled_years = temporal_settings.modeled_years.data.loc[temporal_settings.modeled_years.data.values].index

        return pd.concat(
            [
                temporal_settings.subset_timeseries_by_dispatch_windows(
                    self.model_year_profiles[modeled_year.year].data, modeled_year
                )
                for modeled_year in modeled_years
            ]
        )

    def _return_load_scalars(self, temporal_settings) -> pd.Series:
        """
        Re-scale loads to make annual energy match

        Args:
            temporal_settings: TemporalSettings object with model year and dispatch window weights

        Returns: pd Series of annual_energy_forecast scalar

        """

        adjusted_hourly_loads = self._adjusted_hourly_load(temporal_settings).groupby(level=0).sum().squeeze(axis=1)
        adjusted_hourly_loads.index = pd.to_datetime(adjusted_hourly_loads.index, format="%Y")

        load_scalars = self.annual_energy_forecast.data.loc[adjusted_hourly_loads.index] / adjusted_hourly_loads.values

        return load_scalars

    def _rep_annual_energy(self, block, modeled_year: pd.Timestamp):
        """
        Annual energy
        """
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.load[modeled_year, :, :]
        )

    def _annual_energy(self, block, modeled_year: pd.Timestamp):
        """
        Average annual energy
        """
        df = self.model_year_profiles[modeled_year.year].data
        return df.groupby(df.index.year).sum().mean()

    def _annual_peak(self, block, modeled_year: pd.Timestamp):
        """
        Average annual peak
        """
        df = self.model_year_profiles[modeled_year.year].data
        return df.groupby(df.index.year).max().mean()

    def _rep_annual_peak(self, block, modeled_year: pd.Timestamp):
        """
        Annual peak of the representative annual load that the model sees
        """
        model = block.model()
        return max(
            self.model_year_profiles[modeled_year.year].data.at[timestamp]
            for dispatch_window, timestamp in model.DISPATCH_WINDOWS_AND_TIMESTAMPS
        )

    @timer
    def update_load_components(self, temporal_settings: TemporalSettings) -> None:
        """
        The annual energy on the rep periods may not add up to 100% of the original 8760, so do a simple re-scaling.

        Args:
            temporal_settings: TemporalSettings object with model year and dispatch window weights

        """

        if self.scale_by_energy:
            load_scalars = self._return_load_scalars(temporal_settings)

            # Update loads
            logger.debug(f"Re-scaling {self.name} so that sampled rep period annual energy matches energy forecast")
            self.forecast_load(
                modeled_years=(temporal_settings.first_modeled_year, temporal_settings.last_modeled_year),
                weather_years=(temporal_settings.first_weather_year, temporal_settings.last_weather_year),
                custom_scalars=load_scalars,
            )

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model, construct_costs=construct_costs)

        pyomo_components.update(
            load=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=lambda block, year, dispatch_window, timestamp: self.model_year_profiles[year.year].data.at[
                    timestamp
                ],
                doc="Hourly Load (MWh)",
            ),
            rep_annual_energy=pyo.Expression(
                model.MODELED_YEARS, rule=self._rep_annual_energy, doc="Representative Annual Energy (MWh)"
            ),
            annual_energy=pyo.Expression(
                model.MODELED_YEARS, rule=self._annual_energy, doc="Average Annual Energy (MWh)"
            ),
            rep_annual_peak=pyo.Expression(
                model.MODELED_YEARS, rule=self._rep_annual_peak, doc="Representative Annual Peak (MWh)"
            ),
            annual_peak=pyo.Expression(model.MODELED_YEARS, rule=self._annual_peak, doc="Average Annual Peak (MWh)"),
        )

        return pyomo_components
