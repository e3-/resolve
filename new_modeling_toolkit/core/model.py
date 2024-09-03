from abc import ABC
from abc import abstractmethod

import pyomo.environ as pyo

from new_modeling_toolkit.core.temporal.new_temporal import DispatchWindowEdgeEffects
from new_modeling_toolkit.core.temporal.new_temporal import NewTemporalSettings


class ModelTemplate(pyo.ConcreteModel, ABC):
    """Can't make a child class that inherits both from Pydantic and Pyomo, so seems like this is all I can do for now."""

    def __init__(self, temporal_settings: NewTemporalSettings, system: "System", **kwargs):
        super().__init__(**kwargs)

        self.system = system
        self.temporal_settings = temporal_settings
        self.dispatch_window_edge_effects = temporal_settings.dispatch_window_edge_effects

        assert self.dispatch_window_edge_effects in [
            DispatchWindowEdgeEffects.LOOPBACK,
            DispatchWindowEdgeEffects.CHRONOPERIOD,
            DispatchWindowEdgeEffects.FIXED_INITIAL_SOC,
        ], f"State-of-charge tracking for specified edge effect type `{self.dispatch_window_edge_effects}` is not implemented."

        # Speed up model construction by creating SOME sets.
        self.MODELED_YEARS = pyo.Set(initialize=self.temporal_settings.modeled_years)

        self.DISPATCH_WINDOWS_AND_TIMESTAMPS = pyo.Set(
            initialize=self.temporal_settings.dispatch_windows_df.index.values
        )
        self.DISPATCH_WINDOWS = pyo.Set(
            initialize=self.temporal_settings.dispatch_windows_df.index.get_level_values("window_label").unique()
        )

        dispatch_window_groups = self.temporal_settings.dispatch_windows_df.groupby(level=["window_label"])

        self.TIMESTAMPS_IN_DISPATCH_WINDOWS = pyo.Set(
            self.DISPATCH_WINDOWS,
            initialize=lambda m, window: dispatch_window_groups.get_group(window).index.get_level_values(1),
        )

        timestamps = self.temporal_settings.dispatch_windows_df.index.get_level_values("index")
        self.DAYS = pyo.Set(initialize=timestamps.to_period("D").to_timestamp().unique())
        self.DAYS_IN_DISPATCH_WINDOWS = pyo.Set(
            self.DISPATCH_WINDOWS,
            initialize=lambda m, window: dispatch_window_groups.get_group(window)
            .index.get_level_values(1)
            .to_period("D")
            .to_timestamp()
            .unique(),
        )
        self.DAY_TO_TIMESTAMPS_MAPPING = pyo.Set(
            self.DAYS,
            initialize=self.temporal_settings.dispatch_windows_df.index.to_series()
            .groupby(timestamps.to_period("D").to_timestamp())
            .groups,
        )
        self.MONTHS = pyo.Set(initialize=timestamps.to_period("M").to_timestamp().unique())
        self.MONTHS_IN_DISPATCH_WINDOWS = pyo.Set(
            self.DISPATCH_WINDOWS,
            initialize=lambda m, window: dispatch_window_groups.get_group(window)
            .index.get_level_values(1)
            .to_period("M")
            .to_timestamp()
            .unique(),
        )
        self.MONTH_TO_TIMESTAMPS_MAPPING = pyo.Set(
            self.MONTHS,
            initialize=self.temporal_settings.dispatch_windows_df.index.to_series()
            .groupby(timestamps.to_period("M").to_timestamp())
            .groups,
        )
        self.WEATHER_YEARS = pyo.Set(initialize=timestamps.to_period("Y").to_timestamp().unique())
        self.WEATHER_YEARS_IN_DISPATCH_WINDOWS = pyo.Set(
            self.DISPATCH_WINDOWS,
            initialize=lambda m, window: dispatch_window_groups.get_group(window)
            .index.get_level_values(1)
            .to_period("Y")
            .to_timestamp()
            .unique(),
        )
        self.WEATHER_YEAR_TO_TIMESTAMPS_MAPPING = pyo.Set(
            self.WEATHER_YEARS,
            initialize=self.temporal_settings.dispatch_windows_df.index.to_series()
            .groupby(timestamps.to_period("Y").to_timestamp())
            .groups,
        )

    @abstractmethod
    def solve(self):
        ...
