from __future__ import annotations

import calendar
import copy
from typing import Annotated
from typing import ClassVar
from typing import Optional
from typing import Self
from typing import Union

import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pydantic import Field
from pydantic import model_validator

from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.settings import TemporalSettings
from new_modeling_toolkit.core.utils.core_utils import timer
from new_modeling_toolkit.system.generics.generic_linkages import DemandToProduct
from new_modeling_toolkit.system.generics.generic_linkages import FromZoneToDemand
from new_modeling_toolkit.system.generics.generic_linkages import ToZoneToDemand
from new_modeling_toolkit.system.generics.process import Process

NUM_LEAP_YEAR_HOURS = 366 * 24
NUM_NON_LEAP_YEAR_HOURS = 365 * 24


class Demand(Component):
    """
    Currently only works for a single input product via one DemandToProduct or Process linkage.
    Will need to be updated to accommodate multiple input products via multiple DemandToProduct or Process linkages
    and/or via ProductBlend.
    """

    SAVE_PATH: ClassVar[str] = "demands"

    demand_products: dict[str, DemandToProduct] = {}
    processes: dict[Union[tuple[str, str], str], Process] = {}
    # TODO: Refactor ZoneToDemand linkages to be DemandToZone (analogous to Load). create input_zones and output_zones properties from zones dict
    input_zones: dict[str, FromZoneToDemand] = {}
    output_zones: dict[str, ToZoneToDemand] = {}

    emissions_policies: Annotated[
        dict[str, linkage.EmissionsContribution], Metadata(linkage_order="to", category=FieldCategory.OPERATIONS)
    ] = {}

    ######################
    # Boolean Attributes #
    ######################
    scale_by_capacity: bool = Field(
        False,
        description="If true, calculate model year profiles by scaling profile to median annual peak",
        title="Scale by Median Peak",
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
        description="Weather year(s) demand profile to be scaled. Must have either weather year OR model year profile, but not both.",
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
        description="Model year(s) demand profile to be scaled. Datetime index should include modeled years. Must have either weather year OR model year profile, but not both.",
        title=f"Modeled Year-indexed Profile",
    )

    annual_peak_forecast: Annotated[
        ts.NumericTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Peak"),
    ] = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="max",
        title=f"Annual Median Peak Forecast",
    )
    annual_energy_forecast: Annotated[
        ts.NumericTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Forecast"),
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
        description="T&D loss adjustment to gross up to system-level demands. For example, a DER may be able to serve "
        "8% more demand (i.e., 1.08) than an equivalent bulk system resource due to T&D losses. Adjustment factor is "
        "**directly multiplied** against demand (as opposed to 1 / (1 + ``td_losses_adjustment``).",
    )

    model_year_profiles: dict[int, ts.NumericTimeseries] = Field(
        {}, description="Model year profiles scaled to annual peak and/or annual energy forecasts"
    )

    @property
    def primary_consumed_product(self) -> str:
        return list(self.consumed_products.keys())[0]

    @property
    def unit(self):
        return self.consumed_products[self.primary_consumed_product].unit

    @property
    def consumed_products(self):
        """Unique input products."""
        return {
            demand_product.product.name: demand_product.product for demand_product in self.demand_products.values()
        } | {process.consumed_product.name: process.consumed_product for process in self.processes.values()}

    @property
    def produced_products(self):
        """Unique output products."""
        return {process.produced_product.name: process.produced_product for process in self.processes.values()}

    @property
    def products(self):
        return self.consumed_products | self.produced_products

    @property
    def policies(self):
        return self.emissions_policies

    @property
    def timeseries_attrs(self):
        timeseries_attrs = super().timeseries_attrs
        timeseries_attrs.remove("model_year_profiles")

        return timeseries_attrs

    @model_validator(mode="after")
    def validate_profile_weather_or_model_year(self) -> Self:
        """Ensure that users only provide one profile (either ``profile`` or ``profile_model_years``)."""
        assert (self.profile and not self.profile_model_years) or (
            not self.profile and self.profile_model_years
        ), f"For {self.name}: Only one of either `profile` or `profile_model_years` can be defined."
        return self

    def revalidate(self):
        super().revalidate()

        if not self.demand_products and not self.processes:
            raise ValueError(
                f"`{self.__class__.__name__}` `{self.name}` has no `DemandToProduct` or `Process` linkages assigned. "
                f"Check your `linkages.csv` and `three_way_linkages.csv` files."
            )

        if len(self.consumed_products) > 1:
            raise ValueError(
                f"`{self.__class__.__name__}` `{self.name}` can only be linked to one `DemandToProduct` or `Process` "
                f"linkage."
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
            self.forecast_demand(modeled_years=modeled_years, weather_years=weather_years)
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

    def forecast_demand(
        self,
        modeled_years: tuple[int, int],
        weather_years: tuple[int, int],
        custom_scalars: Optional[pd.Series] = None,
    ):
        """
        Calculate the scaling coefficient and scaling offset for the demand series in order to scale them to any future
        between the first model year and last model year. The coefficient and offset is determine by the future peak
        demand series and energy series, and the demand scaling method defined by the user.

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
            new_profile = Demand.scale_demand(
                profile_to_scale, to_peak, to_energy, self.td_losses_adjustment.slice_by_year(model_year), leap_year
            )
            self.model_year_profiles.update({model_year: new_profile})

    @staticmethod
    def scale_demand(
        profile: ts.NumericTimeseries,
        to_peak: bool | float,
        to_energy: bool | float,
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
            td_losses_adjustment: T&D losses adjustment (simple scalar on demand profile)
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
        logger.debug("Scaled demand profile median peak: {:.0f} MW".format(new_profile_median_peak))
        logger.debug("Scaled demand profile mean annual energy: {:.0f} MWh".format(new_profile_mean_energy))

        return new_profile

    def get_demand(self, modeled_year: int, weather_year_timestamp: pd.Timestamp):
        """
        Based on the model year, first find the future demand series belonging to that model year. And based on the
        period and hour, query the specific hourly demand for that hour in the model year.
        Args:
            system: System.system. current power system
            modeled_year: int. model year being queried
            weather_year_timestamp: model hour being queried

        Returns:  int. demand for the tp under query.

        """

        return self.model_year_profiles[modeled_year].data.at[weather_year_timestamp]

    def _adjusted_hourly_demand(self, temporal_settings) -> pd.DataFrame:
        """

        Args:
            temporal_settings: TemporalSettings object with model year and dispatch window weights

        Returns: Weighted hourly demands within dispatch windows defined in temporal settings

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

    def _demand(self, block, input_product, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        return self.get_demand(modeled_year.year, timestamp)

    def _return_demand_scalars(self, temporal_settings) -> pd.Series:
        """
        Re-scale demands to make annual energy match

        Args:
            temporal_settings: TemporalSettings object with model year and dispatch window weights

        Returns: pd Series of annual_energy_forecast scalar

        """

        adjusted_hourly_demands = self._adjusted_hourly_demand(temporal_settings).groupby(level=0).sum().squeeze(axis=1)
        adjusted_hourly_demands.index = pd.to_datetime(adjusted_hourly_demands.index, format="%Y")

        demand_scalars = (
            self.annual_energy_forecast.data.loc[adjusted_hourly_demands.index] / adjusted_hourly_demands.values
        )

        return demand_scalars

    @timer
    def update_demand_components(self, temporal_settings: TemporalSettings) -> None:
        """
        The annual energy on the rep periods may not add up to 100% of the original 8760, so do a simple re-scaling.

        Args:
            temporal_settings: TemporalSettings object with model year and dispatch window weights

        """

        if self.scale_by_energy:
            demand_scalars = self._return_demand_scalars(temporal_settings)

            # Update demands
            logger.debug(f"Re-scaling {self.name} so that sampled rep period annual energy matches energy forecast")
            self.forecast_demand(
                modeled_years=(temporal_settings.first_modeled_year, temporal_settings.last_modeled_year),
                weather_years=(temporal_settings.first_weather_year, temporal_settings.last_weather_year),
                custom_scalars=demand_scalars,
            )

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:

        pyomo_components = super()._construct_operational_rules(model, construct_costs=construct_costs)

        INPUTS = pyo.Set(initialize=self.consumed_products.keys())

        pyomo_components.update(
            INPUTS=INPUTS,
            consumption=pyo.Var(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                doc=f"Hourly Consumption ({self.unit:e3} per hour)",
            ),
            demand=pyo.Expression(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._demand,
                doc=f"Hourly Demand ({self.unit:e3} per hour)",
            ),
            rep_annual_energy=pyo.Expression(
                model.MODELED_YEARS, rule=self._rep_annual_energy, doc=f"Representative Annual Energy ({self.unit:e3})"
            ),
            annual_energy=pyo.Expression(
                model.MODELED_YEARS, rule=self._annual_energy, doc=f"Average Annual Energy ({self.unit:e3})"
            ),
            rep_annual_peak=pyo.Expression(
                model.MODELED_YEARS, rule=self._rep_annual_peak, doc=f"Representative Annual Peak ({self.unit:e3})"
            ),
            annual_peak=pyo.Expression(
                model.MODELED_YEARS, rule=self._annual_peak, doc=f"Average Annual Peak ({self.unit:e3})"
            ),
            consumption_must_equal_demand=pyo.Constraint(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._consumption_must_equal_demand,
            ),
        )

        if self.processes:
            OUTPUTS = pyo.Set(initialize=self.produced_products.keys())
            pyomo_components.update(
                OUTPUTS=OUTPUTS,
                production=pyo.Expression(
                    OUTPUTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._production,
                    doc=f"Hourly Production (Product Units per hour)",
                ),
                produced_product_to_zone=pyo.Expression(
                    OUTPUTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._produced_product_to_zone,
                    doc=f"Hourly Produced Product To Zone (Product Units per hour)",
                ),
                produced_product_release=pyo.Expression(
                    OUTPUTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._produced_product_release,
                    doc=f"Hourly Produced Product Release (Product Units per hour)",
                ),
            )

        if construct_costs:
            pyomo_components.update(
                consumed_commodity_product_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._consumed_commodity_product_cost,
                    # TODO (MK): confirm no doc needed for this expr?
                ),
                annual_consumed_commodity_product_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_consumed_commodity_product_cost,
                    doc="Annual Total Consumed Commodity Product Cost ($)",
                ),
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                ),
            )

        return pyomo_components

    def _construct_output_expressions(self, construct_costs: bool):
        super()._construct_output_expressions(construct_costs)
        model: ModelTemplate = self.formulation_block.model()

        self.formulation_block.annual_consumption = pyo.Expression(
            self.formulation_block.INPUTS,
            model.MODELED_YEARS,
            rule=self._annual_consumption,
            doc=f"Annual Consumption ({self.unit:e3})",
        )
        self.formulation_block.annual_demand = pyo.Expression(
            self.formulation_block.INPUTS,
            model.MODELED_YEARS,
            rule=self._annual_demand,
            doc=f"Annual Demand ({self.unit:e3})",
        )
        if self.processes:
            self.formulation_block.annual_production = pyo.Expression(
                self.formulation_block.OUTPUTS,
                model.MODELED_YEARS,
                rule=self._annual_production,
                doc=f"Annual Production (Product Units)",
            )
            self.formulation_block.annual_produced_product_to_zone = pyo.Expression(
                self.formulation_block.OUTPUTS,
                model.MODELED_YEARS,
                rule=self._annual_produced_product_to_zone,
                doc=f"Annual Produced Product To Zone (Product Units)",
            )
            self.formulation_block.annual_produced_product_release = pyo.Expression(
                self.formulation_block.OUTPUTS,
                model.MODELED_YEARS,
                rule=self._annual_produced_product_release,
                doc=f"Annual Produced Product Release (Product Units)",
            )

    # TODO: INPUTS should probably be a Param, rather than a Set, since Demands typically only take one input.
    def _rep_annual_energy(self, block, modeled_year: pd.Timestamp):
        """
        Annual energy
        """
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.demand[block.INPUTS[1], modeled_year, :, :]
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
        Annual peak of the representative annual demand that the model sees
        """
        model = block.model()
        return max(
            self.model_year_profiles[modeled_year.year].data.at[timestamp]
            for dispatch_window, timestamp in model.DISPATCH_WINDOWS_AND_TIMESTAMPS
        )

    def _production(self, block, output, modeled_year, dispatch_window, timestamp):
        """Production out byproduct is the conversion rate for a given process times consumption of the corresponding
        input"""
        return sum(
            block.consumption[process.consumed_product.name, modeled_year, dispatch_window, timestamp]
            * process.conversion_rate
            for process in self.processes.values()
            if process.produced_product.name == output
        )

    def _produced_product_to_zone(self, block, output, modeled_year, dispatch_window, timestamp):
        """This represents capture of output product, i.e. injection of output product into the demand's linked zone.
        This typically will equal the value of the production expression, unless it is believed that the output
        product is instead a released atmospheric pollution"""
        return sum(
            block.consumption[process.consumed_product.name, modeled_year, dispatch_window, timestamp]
            * process.conversion_rate
            * process.output_capture_rate
            for process in self.processes.values()
            if process.produced_product.name == output
        )

    def _produced_product_release(self, block, output, modeled_year, dispatch_window, timestamp):
        """This represents release of output product **external** of the system. This will typically be 0,
        unless it is believed that the output product is instead a released atmospheric pollutant."""
        return (
            block.production[output, modeled_year, dispatch_window, timestamp]
            - block.produced_product_to_zone[output, modeled_year, dispatch_window, timestamp]
        )

    def _consumption_must_equal_demand(self, block, input_product, modeled_year, dispatch_window, timestamp):
        return (
            block.consumption[input_product, modeled_year, dispatch_window, timestamp]
            == block.demand[input_product, modeled_year, dispatch_window, timestamp]
        )

    def _consumed_commodity_product_cost(self, block, modeled_year, dispatch_window, timestamp):
        """Operational cost from consuming commodity product"""
        return sum(
            block.consumption[product_name, modeled_year, dispatch_window, timestamp]
            * product.price_per_unit.data.at[timestamp.replace(year=modeled_year.year)]
            for product_name, product in self.consumed_products.items()
            if product.commodity
        )

    def _annual_consumed_commodity_product_cost(self, block, modeled_year):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.consumed_commodity_product_cost[modeled_year, :, :]
        )

    def _annual_total_operational_cost(self, block, modeled_year):
        """The total annual operational costs of the Demand, including consumed product costs.
        This term is not discounted (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        return block.annual_consumed_commodity_product_cost[modeled_year]

    def _annual_consumption(self, block, product, modeled_year):
        return block.model().sum_timepoint_component_slice_to_annual(block.consumption[product, modeled_year, :, :])

    def _annual_demand(self, block, product, modeled_year):
        return block.model().sum_timepoint_component_slice_to_annual(block.demand[product, modeled_year, :, :])

    def _annual_production(self, block, product, modeled_year):
        return block.model().sum_timepoint_component_slice_to_annual(block.production[product, modeled_year, :, :])

    def _annual_produced_product_to_zone(self, block, product, modeled_year):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.produced_product_to_zone[product, modeled_year, :, :]
        )

    def _annual_produced_product_release(self, block, product, modeled_year):
        return (
            block.annual_production[product, modeled_year]
            - block.annual_produced_product_to_zone[product, modeled_year]
        )


# TODO: do we need this? errors in production sim mode
Demand.model_rebuild()
