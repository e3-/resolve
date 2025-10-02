import calendar
import enum
import pathlib
from typing import Optional

import numpy as np
import pandas as pd
import pydantic
from loguru import logger
from pandas.errors import ParserError
from pydantic import Field
from pydantic import field_validator
from pydantic_core.core_schema import ValidationInfo

import new_modeling_toolkit.core.temporal.timeseries as ts
from new_modeling_toolkit.core.from_csv_mix_in import FromCSVMixIn


@enum.unique
class DispatchWindowEdgeEffects(enum.Enum):
    LOOPBACK = "loopback"
    INTER_PERIOD_SHARING = "inter-period sharing"
    FIXED_INITIAL_CONDITION = "fixed initial condition"


class TemporalSettings(FromCSVMixIn):
    timeseries_cluster_name: str | None = None
    dispatch_window_edge_effects: DispatchWindowEdgeEffects
    include_leap_day: bool = True

    # Eventually use pandera to enforce schema
    # | Timestamp | Window Label | Include
    # Recall that DataFrame.loc is slow, so switching to a dict https://github.com/tum-ens/rivus/issues/26
    dispatch_windows_map: pd.DataFrame

    dispatch_window_weights: Optional[pd.Series] = Field(
        default=None, description="Manually-specified weights for each dispatch window."
    )

    # TODO (skramer): clean this up
    chrono_periods_map: Optional[pd.Series] = Field(
        default=None,
        description="Specification of chrono periods to be used in modeling and the mapping to their respective dispatch windows.",
    )

    modeled_years: ts.BooleanTimeseries = Field(..., default_freq="YS", up_method=None, down_method=None)
    modeled_year_discount_factors: Optional[ts.NumericTimeseries] = Field(
        default=None, default_freq="YS", up_method=None, down_method=None
    )
    weather_years_to_use: Optional[ts.BooleanTimeseries] = Field(
        default=None, default_freq="YS", up_method=None, down_method=None
    )
    dollar_year: int | None = Field(default=None)
    discount_rate: float | None = Field(default=None, ge=0, le=1)
    end_effect_years: int | None = Field(default=None, ge=1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.modeled_year_discount_factors = self._calculate_discount_factors()

        if self.dispatch_window_weights is None:
            self._calculate_dispatch_window_weights()

    @field_validator("dispatch_windows_map")
    @classmethod
    def _validate_dispatch_windows_map(cls, df: pd.DataFrame):
        if set(df.index.names) != {"dispatch_window", "timestamp"}:
            raise ValueError(
                "dispatch_windows_map must have exactly two index levels, named 'dispatch_window' and 'timestamp'. "
            )
        df = df.reorder_levels(["dispatch_window", "timestamp"], axis=0)

        if set(df.columns) != {"include"}:
            raise ValueError("dispatch_windows_map must have exactly one column, named 'include'.")

        assert df["include"].isin([0.0, 1.0]).all()

        assert len(df.index) == len(
            df.index.drop_duplicates()
        ), f"Dispatch_window_map has a duplicate value: {df[df.index.duplicated()].index.values}"

        return df

    @property
    def first_modeled_year(self):
        return self.modeled_years.data.index.year.min()

    @property
    def last_modeled_year(self):
        return self.modeled_years.data.index.year.max()

    @property
    def first_weather_year(self):
        return min(self.dispatch_windows_map.index.get_level_values("timestamp").year)

    @property
    def last_weather_year(self):
        return max(self.dispatch_windows_map.index.get_level_values("timestamp").year)

    @property
    def dispatch_windows_and_timestamps(self):
        return self.dispatch_windows_map.index.values

    @property
    def dispatch_windows(self):
        return self.dispatch_windows_map.index.get_level_values("dispatch_window").unique()

    @property
    def timestamps(self):
        return self.dispatch_windows_map.index.get_level_values("timestamp")

    @property
    def dispatch_window_groups(self):
        return self.dispatch_windows_map.groupby(level=["dispatch_window"])

    @pydantic.field_validator("dispatch_window_weights")
    def _validate_dispatch_window_weights(cls, dispatch_window_weights: Optional[pd.Series], info: ValidationInfo):
        dispatch_windows_map = info.data["dispatch_windows_map"]
        assert len(dispatch_windows_map.index) == len(
            dispatch_windows_map.index.drop_duplicates()
        ), "Dispatch_window_map has a duplicate index"

        if set(dispatch_window_weights.index) != set(dispatch_windows_map.index.get_level_values("dispatch_window")):
            raise ValueError(
                "The set of dispatch windows specified in 'dispatch_window_weights.csv' does not match the set of "
                "dispatch windows specified in 'dispatch_windows_map.csv'"
            )

        if dispatch_window_weights is not None:
            if np.round(dispatch_window_weights.sum(), 6) != 1:
                raise ValueError("User-specified `dispatch_window_weights` must sum to 1.0.")

        return dispatch_window_weights

    @pydantic.model_validator(mode="after")
    def validate_chrono_to_rep_mapping(self):
        # Extract the dispatch_windows_map from the validation info
        dispatch_windows_map = self.dispatch_windows_map

        # Check if the set of dispatch windows listed in chrono_periods_map matches the set
        #  listed in dispatch_windows_map
        # Note: because of how pandas stores datetime info, the dispatch windows from
        #  chrono_periods_map may be of type np.datetime64, while the dispatch windows from
        #  dispatch_windows_map may be of type pd.Timestamp, so using sets to determine equality is not possible - hence
        #  the sorting of unique values instead. Dispatch windows can also be integers, so coercion to a single datetime
        #  type is also not possible.
        if self.chrono_periods_map is None:
            return self
        if sorted(np.unique(self.chrono_periods_map.values)) != sorted(
            dispatch_windows_map.index.unique(level="dispatch_window")
        ):
            extra_dates_in_chrono = set(self.chrono_periods_map.values) - set(
                dispatch_windows_map.index.get_level_values("dispatch_window")
            )
            extra_dates_in_df = set(dispatch_windows_map.index.get_level_values("dispatch_window")) - set(
                self.chrono_periods_map.values
            )
            raise ValueError(
                f"The set of dispatch windows specified in 'chrono_periods_map.csv' does not match"
                f" the set of dispatch windows specified in 'dispatch_windows_map.csv'. "
                f"\n\n"
                f"Extra dates in 'chrono_periods_map.csv': {extra_dates_in_chrono}"
                f"\n"
                f"Extra dates in 'dispatch_windows_map.csv': {extra_dates_in_df}"
            )

        return self

    @classmethod
    def from_dir(cls, temporal_settings_dir: pathlib.Path) -> "TemporalSettings":

        df = pd.read_csv(temporal_settings_dir / "attributes.csv")
        timeseries_cluster_name = df.loc[df["attribute"] == "timeseries_cluster_name", "value"].squeeze()

        def _convert_column_to_datetime(df: pd.DataFrame, column_name: str, df_name: str):
            try:
                # Attempt to convert the column to timestamps
                #  Note: We first convert the column to a string because if it is an integer, pandas will assume by
                #  default that it is the number of nanoseconds after 1970-01-01 00:00, even if a parsing format is
                #  specified.
                df.loc[:, column_name] = pd.to_datetime(df.loc[:, column_name].astype(str))
            except (ValueError, ParserError) as e:
                logger.warning(
                    f"`{column_name}` column of `{df_name}` could not be converted to timestamps and will be "
                    f"interpreted as `{df[column_name].dtype}` - error message below:"
                )
                logger.warning(str(e))

        dispatch_windows_map = pd.read_csv(
            temporal_settings_dir.parents[2] / "timeseries" / timeseries_cluster_name / "dispatch_windows_map.csv",
            parse_dates=["timestamp"],
        )
        # Try to convert the "dispatch_window" column to a timestamp.
        # Note: the column does not have to be specified as a timestamp, but it is allowed.
        _convert_column_to_datetime(dispatch_windows_map, column_name="dispatch_window", df_name="dispatch_windows_map")

        dispatch_windows_map = dispatch_windows_map.set_index(
            ["dispatch_window", "timestamp"],
        )

        data = {"dispatch_windows_map": dispatch_windows_map}

        # Read in the chrono period to dispatch window mapping, if it exists
        chrono_period_file = (
            temporal_settings_dir.parents[2] / "timeseries" / timeseries_cluster_name / "chrono_periods_map.csv"
        )
        dw_weights_path = (
            temporal_settings_dir.parents[2] / "timeseries" / timeseries_cluster_name / "dispatch_window_weights.csv"
        )
        if chrono_period_file.exists():
            if dw_weights_path.exists():
                logger.warning(
                    f"Both a chrono period to dispatch window mapping and dispatch window weights were "
                    f"passed as inputs. Ignoring the dispatch window weights and calculating them "
                    f"endogenously with the chrono period mapping."
                )
            chrono_periods_map = pd.read_csv(chrono_period_file, index_col=False)

            # Attempt to convert the "chrono_period" and "dispatch_window" columns to timestamps
            #  Note: similar to above, the "chrono_period" and "dispatch_window columns do not have to be specified as
            #  a timestamps, but it is allowed.
            for column_name in ["chrono_period", "dispatch_window"]:
                _convert_column_to_datetime(
                    chrono_periods_map,
                    column_name=column_name,
                    df_name="chrono_periods_map",
                )

            chrono_periods_map = chrono_periods_map.set_index("chrono_period").squeeze()

            data["chrono_periods_map"] = chrono_periods_map

        elif dw_weights_path.exists():
            dispatch_window_weights = pd.read_csv(dw_weights_path)
            _convert_column_to_datetime(
                dispatch_window_weights, column_name="dispatch_window", df_name="dispatch_window_weights"
            )
            dispatch_window_weights = dispatch_window_weights.set_index("dispatch_window").squeeze()
            data["dispatch_window_weights"] = dispatch_window_weights

        else:
            raise ValueError(f"Either dispatch window weights or a chrono period mapping must be specified.")

        temporal_settings = cls.from_csv(
            filename=temporal_settings_dir.joinpath("attributes.csv"),
            scenarios=None,
            data=data,
            name="temporal_settings",
        )

        return temporal_settings

    @property
    def rep_periods(self) -> list:
        return list(self.dispatch_windows_map.index.unique(level="dispatch_window"))

    @property
    def timestamp_durations(self):
        # Calculate the duration of each timestamp within the dispatch windows
        # Note: Because the timestamps in each dispatch window do not necessarily wrap around
        #  a single day, we assume that the last timestamp in each dispatch window is the same length as the
        #  timestamp that preceded it.
        durations = (
            self.dispatch_windows_map.index.to_frame()
            .loc[:, "timestamp"]
            .rename("duration")
            .groupby("dispatch_window")
            .diff(1)
            .shift(-1)
            .fillna(method="ffill", limit=1)
        )

        return durations

    @property
    def timestamp_duration_hours(self):
        """

        Returns: pd.Series of how many hours in each timestamp

        """
        if getattr(self, "_timestamp_duration_hours", None) is None:
            self._timestamp_duration_hours = self.timestamp_durations.div(pd.Timedelta(hours=1))
        return self._timestamp_duration_hours

    @property
    def num_days_in_modeled_year(self) -> pd.Series:
        """Returns number of days in each modeled year as a repeating series, with option to ignore leap days (in which case modeled years are always 365 days)."""
        if self.include_leap_day:
            data = [366 if calendar.isleap(x.year) else 365 for x in self.modeled_years.data.index]
        else:
            data = [365 for x in self.modeled_years.data.index]

        return pd.Series(index=self.modeled_years.data.index, data=data)

    @property
    def modeled_year_list(self) -> list:
        """
        Return list of model years
        """
        return self.modeled_years.data.loc[self.modeled_years.data.values].index

    def subset_timeseries_by_dispatch_windows(
        self, profile: pd.Series, modeled_year: pd.Timestamp, apply_dispatch_window_weights: bool = True
    ) -> pd.DataFrame:
        """
        Inputs full weather year series, and returns a dataframe of only the timestamps of the dispatch windows used in the model.

        Args:
            profile: weather year pd.Series
            modeled_year: modeled year as pd.Timestamp
            apply_dispatch_window_weights: bool. True if dispatch windows should be multiplied by weights

        Returns: pd.DataFrame. index=[MODELED_YEAR,DISPATCH_WINDOW,TIMESTAMP], data=dispatch_window data from profile

        """
        return pd.DataFrame.from_dict(
            {
                (modeled_year, dispatch_window, timestamp): [
                    profile.at[timestamp]
                    * (
                        self.dispatch_window_weights[dispatch_window]
                        * self.num_days_in_modeled_year[modeled_year]
                        * self.timestamp_duration_hours[dispatch_window, timestamp]
                        if apply_dispatch_window_weights
                        else 1
                    )
                ]
                for dispatch_window, timestamp in self.dispatch_windows_and_timestamps
            }
        ).T

    def _calculate_dispatch_window_weights(self):
        """Calculates the weighting factor for each window, if no weights are specified by the user. The dispatch window
        weights will always sum to 1.

        If a chrono-to-dispatch-window mapping are specified, then the weights for each dispatch window are calculated
        as the number of occurrences of that dispatch window in the mapping divided by the total number of chrono
        periods.

        If there are no chrono periods specified, then the dispatch window weights will be calculated as the sum of the
        timestamp-weights for all timestamps in each dispatch window that are marked for inclusion, divided by the
        total sum of the timestamp-weights across all dispatch windows.

        Returns:

        """
        # todo: this assumes there are 24 hours in a day. Add validator?
        if self.chrono_periods_map is not None:
            dispatch_window_weights = (
                self.chrono_periods_map.value_counts().rename_axis(index="dispatch_window").rename("weight")
            )
            # need to update the hourly timestamp weights here in dispatch_windows_map? Flows into the sum_timepoint_to_annual calc
        else:
            dispatch_window_weights = (
                self.dispatch_windows_map.loc[self.dispatch_windows_map["include"].astype(bool)]
                .groupby("dispatch_window")["weight"]
                .sum()
            )

        dispatch_window_weights = dispatch_window_weights / dispatch_window_weights.sum()

        self.dispatch_window_weights = dispatch_window_weights

    def _calculate_discount_factors(self) -> ts.NumericTimeseries:
        # 1. Set up DataFrame for calculations spanning from ``cost_dollar_year`` through (``modeled_year_end`` + ``end_effect_years``)
        modeled_years = self.modeled_years.data.loc[self.modeled_years.data.values].index.to_list()
        modeled_year_start = min(modeled_years)
        modeled_year_end = max(modeled_years)
        df = pd.DataFrame(
            index=pd.date_range(
                start=f"1/1/{self.dollar_year}",
                end=f"1/1/{modeled_year_end.year + self.end_effect_years - 1}",
                freq="YS",
            )
        )

        # 2. Drop any years before first ``modeled_year_start``
        df = df[df.index >= min(modeled_year_start, pd.Timestamp(f"1/1/{self.dollar_year}"))]

        # 3. Convert annual discount rate to compounding discount rate for full modeling horizon, with 100% being ``cost_dollar_year``
        df["compounding_discount_rate"] = (1.0 + self.discount_rate) ** -1
        df["compounding_discount_rate"] = df["compounding_discount_rate"].fillna(method="ffill")
        df.loc[f"1/1/{self.dollar_year}", "compounding_discount_rate"] = 1
        df["compounding_discount_rate"] = df["compounding_discount_rate"].cumprod()
        df = df[df.index >= modeled_year_start]

        # 4. Add modeled years
        df["modeled_years"] = df.index.isin(modeled_years)
        # df["modeled_years"] = df["modeled_years"].fillna(False)

        # 5. Sum up end effect years
        df.loc[modeled_year_end, "compounding_discount_rate"] = df.loc[
            df.index >= modeled_year_end, "compounding_discount_rate"
        ].sum()
        df = df[df.index <= modeled_year_end]

        # 6. Count years between modeled years
        counter = 0
        start_year = modeled_year_start
        for index, row in df.iterrows():
            if row["modeled_years"]:
                counter = 0
                start_year = index
            df.loc[index, "end_year_weight"] = counter
            df.loc[index, "start_year"] = start_year
            # Increment counter
            counter += 1

        counter = 1
        end_year = pd.to_datetime(f"1/1/{modeled_year_end.year + 1}")
        for index, row in df[::-1].iterrows():
            df.loc[index, "start_year_weight"] = counter
            df.loc[index, "end_year"] = end_year
            # Increment counter
            counter += 1
            if row["modeled_years"]:
                end_year = index
                counter = 1

        df["num_years_between_modeled"] = df["end_year"].dt.year - df["start_year"].dt.year

        # 7. Weight compounding discount rate by ``start_year_weight`` and ``end_year_weight``

        df["end_year_weight"] = (
            df["end_year_weight"] / df["num_years_between_modeled"] * df["compounding_discount_rate"]
        )
        df["start_year_weight"] = (
            df["start_year_weight"] / df["num_years_between_modeled"] * df["compounding_discount_rate"]
        )

        # 8. Sum ``start_year_weight`` and ``end_year_weight`` for each modeled year using ``df.groupby``
        discount_factor = (
            pd.concat(
                [
                    df.groupby("start_year")["start_year_weight"].sum(),
                    df.groupby("end_year")["end_year_weight"].sum(),
                ],
                axis=1,
            )
            .fillna(0)
            .sum(axis=1)
        )
        discount_factor = discount_factor[df.loc[df["modeled_years"]].index]

        # 9. Convert to Timeseries object
        discount_factor = ts.NumericTimeseries(name="modeled_year_discount_factor", data=discount_factor)

        return discount_factor
