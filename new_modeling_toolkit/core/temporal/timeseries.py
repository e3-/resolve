# 3rd party packages
import calendar
import datetime
import enum
import glob
import json
import pathlib
from typing import Dict
from typing import Optional
from typing import Union

import numpy as np
import pandas as pd
import pytz
from loguru import logger
from pydantic import field_serializer
from pydantic import field_validator
from pydantic import model_validator
from pydantic import PrivateAttr

from new_modeling_toolkit.core import custom_model
from new_modeling_toolkit.core import dir_str

# TODO: is copy and csv really necessary here? Feels like a vestige
# Python pre-installed package
# Import variable representing directory structure

# Constants
INIT_SEED = 2021
STEPS_MAX = 100


@enum.unique
class TimeseriesType(enum.Enum):
    MODELED_YEAR = "modeled year", "Modeled Year"
    WEATHER_YEAR = "weather year", "Weather Year"
    # Month-hour & season-hour profiles are converted to modeled-year hourly profiles
    MONTH_HOUR = "month-hour", "Month-Hour"
    SEASON_HOUR = "season-hour", "Season-Hour"
    MONTHLY = "monthly", "Monthly"

    def __new__(cls, _, *values):
        obj = object.__new__(cls)
        # first value is canonical value
        obj._value_ = values[0]
        for other_value in values[1:]:
            cls._value2member_map_[other_value] = obj
        obj._all_values = values
        return obj

    def __repr__(self):
        return f"<{self.__class__.__name__}.{self._name_}: {', '.join([repr(v) for v in self._all_values])}>"

class NoDateTimeseries(custom_model.CustomModel):
    #################
    # HIDDEN FIELDS #
    #################
    _date_created: datetime.datetime = PrivateAttr(datetime.datetime.now())
    _as_dict: Optional[dict] = None

    ###################
    # REQUIRED FIELDS #
    ###################
    data: pd.Series

    ###################
    # OPTIONAL FIELDS #
    ###################
    type: Optional[TimeseriesType] = None
    data_dir: Optional[pathlib.Path] = None


# TODO: Consider adding attribute-based validation constraints (e.g., value bounds provided by user, or subclasses?)
class Timeseries(custom_model.CustomModel):
    #################
    # HIDDEN FIELDS #
    #################
    _date_created: datetime.datetime = PrivateAttr(datetime.datetime.now())

    ###################
    # REQUIRED FIELDS #
    ###################
    data: pd.Series
    _data_dict: Optional[Dict] = None

    ###################
    # OPTIONAL FIELDS #
    ###################
    timezone: Optional[str] = None
    DST: Optional[bool] = None
    weather_year: bool = False
    type: Optional[TimeseriesType] = None
    data_dir: Optional[pathlib.Path] = None
    freq_: Optional[str] = None

    def __eq__(self, other):
        if not isinstance(other, Timeseries):
            equals = False
        else:
            equals = (
                self.weather_year == other.weather_year
                and self.timezone == other.timezone
                and self.DST == other.DST
                and self.type == other.type
            )
            if equals:
                try:
                    pd.testing.assert_series_equal(left=self.data, right=other.data, check_names=True, check_freq=True)
                except AssertionError:
                    equals = False

        return equals

    def dict(self, **kwargs):
        """Need to exclude `_data_dict` attributes to avoid recursion error when saving to JSON."""
        attrs_to_exclude = {
            "DST",
            "_data_dict",
            "data_dir",
            "name",
            "timezone",
            "type",
        }
        return super(Timeseries, self).dict(exclude=attrs_to_exclude, exclude_defaults=True, exclude_none=True)

    @field_serializer("data", when_used="json")
    def serialize_pd_series(data: pd.Series):
        """
        This is needed for loading system from json. Without this, the default is to shrink timeseries with repeated values to a single timestamp,
        which does not translate correctly when resampling the timeseries attributes again because depending on the `up_method' it might try
         to interpolate for example instead of forward fill
        """
        return {str(key): value for key, value in data.items()}

    ###################################################################################################################
    # CLASS METHODS
    ###################################################################################################################

    @classmethod
    def default_factory(cls, value: float = 0):
        """Migrate all the other defaults to this one."""
        return cls(name="default", data=pd.Series({pd.to_datetime("1/1/1900"): value}))

    @classmethod
    def zero(cls):
        return cls(name="zeroes", data=pd.Series({pd.to_datetime("1/1/1900"): 0}))

    @classmethod
    def one(cls):
        return cls(name="ones", data=pd.Series({pd.to_datetime("1/1/1900"): 1}))

    @classmethod
    def infinity(cls):
        return cls(name="infinities", data=pd.Series({pd.to_datetime("1/1/1900"): np.inf}))

    @classmethod
    def from_csv(cls, name: str, filepath: Union[str, pathlib.Path], **kwargs):
        """
        Lightweight wrapper around pandas.read_csv() method
        """
        data = pd.read_csv(
            filepath,
            index_col=0,
            parse_dates=True,
            infer_datetime_format=True,
            **kwargs,
        )
        data = data.squeeze(axis=1)  # convert to series
        logger.debug(f"Read CSV '{name}': {filepath}")
        return cls(name=name, data=data)

    @model_validator(mode="before")
    @classmethod
    def validate_or_convert_to_series(cls, values):
        """Validate that data passed to Timeseries constructor is a pd.Series.

        Alternatively:
        - Convert a dictionary to a pd.Series (assumes that the keys are already datetimes, as done in `Component.from_csv`)
        - Parse a string as a file path referencing another CSV file that can be read in as a pd.Series
        """
        # Very hacky :(
        if values is None:
            return values
        # Transform it into the right kind of subclass
        elif isinstance(values, Timeseries) or issubclass(values.__class__, Timeseries):
            return cls(**values.model_dump())

        if len(values["data"]) == 0:
            values["data"] = 0
        elif isinstance(values["data"], str):
            try:  # See if the data is a float
                values["data"] = pd.Series({pd.Timestamp("1/1/1900"): float(values["data"])})
            except ValueError:  # If it seems like a string, then try to parse as a filepath
                # Deal with users using "\" instead of "/" as filepath separator
                if "\\" in values["data"]:
                    regularized_filepath = values["data_dir"] / pathlib.Path(pathlib.PureWindowsPath(values["data"]))
                else:
                    regularized_filepath = values["data_dir"] / pathlib.Path(values["data"])

                if regularized_filepath.exists():
                    path = pathlib.Path(regularized_filepath)
                elif (dir_str.proj_dir / regularized_filepath).exists():
                    path = dir_str.proj_dir / regularized_filepath
                else:
                    raise FileNotFoundError(f"Cannot find filepath to {values['data']}. Try using an absolute path.")
                values["data"] = (
                    pd.read_csv(path, index_col=0, parse_dates=True, infer_datetime_format=True)
                    .dropna(axis=1)
                    .squeeze(axis=1)
                )
        else:  # Assume it's a dict that can be turned into a Series
            values["data"] = pd.Series(values["data"])

        return values

    @classmethod
    def from_annual_series(cls, name: str, data: pd.Series, **kwargs):
        """Try to convert a pd.Series with year (e.g., 2020) indices into a Timeseries (with DateTimeIndex)."""
        if not (data.index.astype(int) >= 1000).all():
            raise ValueError("Series does not have valid index values for conversion (integers >= 1000).")
        series_dt = data.copy()
        series_dt.index = pd.DatetimeIndex(
            [pd.Timestamp(year=year, month=1, day=1) for year in series_dt.index.astype(int)], name=data.index.name
        )

        instance = cls(name=name, data=series_dt, **kwargs)

        return instance

    @classmethod
    def from_dir(cls, directory, filetype="csv") -> Dict[str, "Timeseries"]:
        # TODO: This is sort of obsolete now that the base `from_csv` method already reads from a directory
        """Reads all files in specified directory to Timeseries objects and returns dictionary of Timeseries objects

        Args:
            directory (str or pathlib.Path object): directory containing files to be read to timeseries objects
            filetype (str): either 'csv' or 'json'; specifies type of file being read to Timeseries objects

        Returns:
            ts_dict (dict): dictionary containing Timeseries objects with Timeseries names as keys
        """

        # Validate file_types
        if filetype not in ["csv", "json"]:
            raise Exception(f"Argument 'filetype' = {filetype} not valid; file_types must be either 'csv' or 'json'")

        # Grab all files of type file_types in directory
        files = glob.glob(str(directory / f"*.{filetype}"))

        # Check if files is empty
        if not files:
            raise Exception(
                f"No {filetype} files found in directory; check that directory is valid or that file_types is correct"
            )

        # Initialize empty list to hold timeseries objects
        ts_dict = {}
        for i, f in enumerate(files):
            # Read in timeseries object from file
            if filetype == "csv":
                name = pathlib.Path(f).stem  # Get name based on filename
                ts = cls.from_csv(name=name, filepath=f)
            elif filetype == "json":
                ts = cls.from_json(pathlib.Path(f))
            else:
                raise ValueError(f"File type must be [csv, json]. File type provided was '{filetype}'")
            # Enter object in ts_dict
            ts_dict[ts.name] = ts

        return ts_dict

    ###################################################################################################################
    # VALIDATION METHODS
    ###################################################################################################################

    def validate_timezone(self):
        """
        Validate timezone passed to timeseries object
        """
        ret = True
        # If timezone specified
        if self.timezone:
            # Check if timezone is valid (if it is in list of accepted timezones)
            if self.timezone not in pytz.all_timezones:
                ret = False
        return ret

    def validate_data(self):
        """
        Validate data passed to timeseries object
        """
        # Check if index is valid datetime index, etc.
        return True

    @field_validator("data")
    def validate_and_convert_series(cls, value: any) -> pd.Series:
        """Validate that timeseries data index is a DatetimeIndex"""
        if isinstance(value, pd.Series):
            value.index = pd.to_datetime(value.index)

        return value

    ###################################################################################################################
    # PROPERTIES
    ###################################################################################################################

    @property
    def processed_dir(self):
        return self.data_dir / "processed" / self.type

    @property
    def freq(self):
        if self.freq_ is None:
            if self.data.index.freq:
                self.freq_ = self.data.index.freq
            else:
                self.freq_ = pd.infer_freq(self.data.index)
        return self.freq_

    @property
    def data_dict(self):
        """Accessing data as a dictionary is faster than using .iloc/.loc.

        Should only use this once, because this will only crease the _as_dict hidden field once.
        For this to be more robust, need a way to update _as_dict every time `data` field gets updated

        https://github.com/e3-/new-modeling-toolkit/issues/597
        """
        if not self._data_dict:
            self._data_dict = self.data.to_dict()

        return self._data_dict

    @property
    def days_in_year(self) -> pd.Series:
        """Returns the number of days in each year of a timeseries"""
        is_leap_year = [calendar.isleap(year) for year in self.data.index.year]
        days_in_year = pd.Series(data=[366 if leap_year else 365 for leap_year in is_leap_year], index=self.data.index)
        return days_in_year

    ###################################################################################################################
    # METHODS
    ###################################################################################################################

    def to_json(self):
        """Save Timeseries object to specified path."""

        self.processed_dir.mkdir(parents=True, exist_ok=True)  # Will create processed directory if it does not exist

        with open(self.processed_dir / f"{self.name}.json", "w") as json_file:
            json.dump(json.loads(self.json()), json_file, indent=4)

    def slice_by_year(self, year):
        return self.data.at[pd.Timestamp(f"{year}-01-01")]

    def slice_by_timepoint(self, temporal_settings, model_year, period, hour):
        """
        Given model_year, period, and hour, find the correct value for this time series at those times.
        The ts_type determines the behavior of the tp slicing. For renewable profiles, we use only the period and hour
        to slice the correct value. For load components, we find the correct load through load profiles that are scaled
        to a future year, which is not incorporated into this function right now. For all others, we directly query the
        corresponding datetime.

        Args:
            system: System object that contains the power system component and linkages
            model_year: The year we are trying to model. Doesn't make an impact for renewable profiles
            period: The index of the representative period we're looking for
            hour: The hour within the representative period

        Returns: Value of the current TS at the queried (model year, period, hour)

        """
        # If the timeseries is already a weather year type, we use rep periods directly
        if self.weather_year:
            chrono_dt = temporal_settings.rep_periods.loc[period, hour]
        else:  # For model year based data, we only obtain month and date from the period info.
            chrono_dt = temporal_settings.rep_periods.loc[period, hour]

            # There's a small chance that the rep hour is a leap day hour, which is not guaranteed to exist for all
            # model years. In that case just find the same value from a day prior
            if (chrono_dt.month == 2) and (chrono_dt.day == 29):
                chrono_dt = chrono_dt - pd.Timedelta("1D")

            # Replace the weather year with the model year we are looking for
            chrono_dt = pd.Timestamp(f"{model_year}-{chrono_dt.month}-{chrono_dt.day} {chrono_dt.hour}:00:00")

        # If timeseries type is month-hour or season-hour, do some more hacky mapping
        if self.type == TimeseriesType.MONTHLY:
            chrono_dt = f"{chrono_dt.month:02d}-01 00:00:00"
        elif self.type == TimeseriesType.MONTH_HOUR:
            chrono_dt = f"{chrono_dt.month:02d}-01 {chrono_dt.hour:02d}:00:00"
        elif self.type == TimeseriesType.SEASON_HOUR:
            # Hard-code seasons-month mapping
            month_to_season = {
                1: "01",
                2: "01",
                3: "03",
                4: "03",
                5: "03",
                6: "06",
                7: "06",
                8: "06",
                9: "09",
                10: "09",
                11: "09",
                12: "01",
            }
            chrono_dt = f"{month_to_season[chrono_dt.month]}-01 {chrono_dt.hour:02d}:00:00"
        return self.data_dict[chrono_dt]

    def add_leap_day(self, year, interval):
        """
        Args:
            interval: Interval of timeseries in minutes. Ex: 60
        Only valid when original timeseries do not contain leap day.
        """
        # if it's not a leap year
        if not len(self.data.loc[year]) > (365 * 24 * 60 / interval):
            profile_start = self.data.loc[year][: int((31 + 28) * 24 * 60 / interval)]
            profile_add_day = self.data.loc[year][
                int((31 + 27) * 24 * 60 / interval) : int((31 + 28) * 24 * 60 / interval)
            ]
            profile_end = self.data.loc[year][int((31 + 28) * 24 * 60 / interval) :]
            df_concat = pd.concat([profile_start, profile_add_day, profile_end])
            return df_concat
        # if it's already a leap year
        else:
            return self.data.loc[year]

    def remove_leap_day(self, year, interval):
        """
        Args:
            interval: Interval of timeseries in minutes. Ex: 60
        Only valid when original timeseries do contain leap day.
        """
        # if it's a leap year
        if len(self.data.loc[year]) > (365 * 24 * 60 / interval):
            profile_start = self.data.loc[year][: int((31 + 28) * 24 * 60 / interval)]
            profile_end = self.data.loc[year][int((31 + 29) * 24 * 60 / interval) :]
            df_concat = pd.concat([profile_start, profile_end])
            return df_concat
        # if not:
        else:
            return self.data.loc[year]

    def add_index(self, year, interval, remove_leap_day=False):
        """Add datetime index to dataframe"""
        dates = pd.date_range(
            start=pd.Timestamp(year, 1, 1, 0),
            end=pd.Timestamp(year, 12, 31, 23),
            freq=str(interval) + "Min",
        )
        if remove_leap_day:
            logger.info("remove leap days")
            dates = dates[~((dates.month == 2) & (dates.day == 29))]  # remove leap days
        self.data.columns = [self.units]
        self.data.index = dates
        self.data.index.name = "date (tz = " + str(self.timezone) + ")"

    @staticmethod
    def resample_up(df, method):
        """Resample timeseries by increasing the timestamps.

        Args:
            frequency: New freqency of timestamps. Ex: 'H' for hourly
            method: Method for upsampling data into more frequent timestamps.
                - 'interpolate' to interpolate between existing values
                - 'ffill' to forward fill value until next timestamp
                - 'bfill' to back fill value until previous timestamp
        """
        if method == "interpolate":
            df = df.interpolate()
        elif method == "ffill":
            df = df.ffill()
        elif method == "bfill":
            df = df.bfill()
        elif method is None:
            df = df
        else:
            raise ValueError(f"Unsupported argument for resample_up(): method=`{method}`")

        return df

    @staticmethod
    def resample_down(df, frequency, method):
        """Resample timeseries by reducing the timestamps.

        Args:
            frequency: New frequency of timestamps. Ex: 'H' for hourly
            method: Method for combining data into less frequent timestamps.
                - 'sum' to add all existing values that fall into new timestamp range
                - 'mean' to average all existing values that fall into new timestamp range
                - 'first' to take the first existing value within the new timestamp range
        """
        if method == "sum":
            df = df.resample(rule=frequency).sum()
        elif method == "mean" or method == "average" or method == "annual":
            # Try to do time-weighted mean
            if frequency == "YS":
                complete_freq = "1D"
            else:
                complete_freq = "H"
            df = df.resample(rule=complete_freq).ffill()
            df = df.resample(rule=frequency).mean()
        elif method == "max":
            df = df.resample(rule=frequency).max()
        elif method == "first":
            new_index = df.resample(rule=frequency).sum().index
            df = df.reindex(index=new_index)
        elif method is None:
            df = df
        else:
            raise ValueError(f"Unsupported argument for resample_down(): method=`{method}`")

        return df

    def resample_month_or_season_hour_to_hourly(self, correct_index: pd.DatetimeIndex):
        """This is a method called by resample_ts_attributes in the Component Class which resamples monthly, month-hour,
        or season-hour data to the correct frequency and start and end date for a specific attribute."""

        if self.type == TimeseriesType.MONTH_HOUR:
            return self.resample_month_hour_to_hourly(correct_index=correct_index)
        elif self.type == TimeseriesType.SEASON_HOUR:
            return self.resample_season_hour_to_hourly(correct_index=correct_index)
        else:
            # Data with MONTHLY TimeseriesType are expected to have 12 values
            assert (
                len(self.data) == 12
            ), f"Month-hour data for {self.name} is the wrong size. Should be exactly 12 values."

            # Upsample monthly data to every index value with that month (this assumes forward fill up_method)
            new_profile = pd.Series(name=self.data.name, index=correct_index, data=np.nan)
            for month_index, value in self.data.items():
                month = month_index.month
                new_profile.loc[new_profile.index.month == month] = value
            self.data = new_profile

            return self

    def resample_month_hour_to_hourly(self, correct_index: pd.DatetimeIndex):

        raise NotImplementedError("Month-hour resampling is not yet implemented.")

        # Data with MONTH_HOUR TimeseriesType are expected to have 288 values
        # if getattr(self, attr).type == TimeseriesType.MONTH_HOUR:
        #     assert (
        #             len(getattr(self, attr).data) == 12 * 24
        #     ), f"Month-hour data for {self.name} is the wrong size. Should be exactly 288 values."

    def resample_season_hour_to_hourly(self, correct_index: pd.DatetimeIndex):

        raise NotImplementedError("Season-hour resampling is not yet implemented.")

        # Data with SEASON_HOUR TimeseriesType are expected to have 96 values
        # if getattr(self, attr).type == TimeseriesType.SEASON_HOUR:
        #     assert (
        #             len(getattr(self, attr).data) == 4 * 24
        #     ), f"Season-hour data for {self.name} is the wrong size. Should be exactly 96 values."

    def resample_simple_extend_years(self, weather_years: tuple[int, int]):
        """
        Copies a year of data for the range of weather years. For leap years, wraps the first day of the year around
        for last day of leap year

        Args:
            weather_years: tuple of beginning and end of weather year range

        Returns:

        """

        first_weather_year, last_weather_year = weather_years

        drange = pd.date_range(
            f"01/01/{first_weather_year} 00:00", f"12/31/{last_weather_year} 23:00", freq=pd.infer_freq(self.data.index)
        )
        # Because we have `validate_assignment` as True, every time we do ts.data = something,
        # it will get re-validated, including if we're mid-operation (in this case, we've extended the indices
        # but have yet to fill in the NaNs)

        raw = self.data.copy()
        new = self.data.copy()
        new = new.reindex(drange)
        for year in range(first_weather_year, last_weather_year + 1):
            year_index = new.loc[new.index.year == year].index

            if len(year_index) == len(raw):  # if both normal years
                new.loc[year_index] = raw.values
            elif len(year_index) > len(raw):  # if weather year is a leap year and model year isn't
                new.loc[year_index[: len(raw)]] = raw.values  # put the values in for first 8760
                new.loc[year_index[len(raw) :]] = raw.values[: len(year_index) - len(raw)]  # fill in from beginning
            else:  # if model year is a leap year and weather is no
                new.loc[year_index] = raw.values[: len(year_index)]

        self.data = new
        self.weather_year = True

    def repeat_ts(self, repeat_year_dict):
        """Replicate the timeseries for certain times.

        Args:
            repeat_year_dict: a dictionary between weather/load year and data year.
            e.g., for DR profiles, the dictionary can be {extended load year : one year of raw DR data};
            e.g., for Hydro profiles, the dictionary can be {extended load year : shuffled hydro year}

        """
        years = list(repeat_year_dict.keys())
        new_index = pd.date_range(
            start=pd.Timestamp(min(years), 1, 1, 0),
            end=pd.Timestamp(max(years), 12, 31, 23),
            freq=self.freq,
            name=self.data.index.name,
        )
        data_by_year = self.data.groupby(self.data.index.year)
        data_repeated = pd.Series()
        for year in years:
            data_repeated_year = data_by_year.get_group(repeat_year_dict[year])
            if self.freq in ["H", "D"]:
                if calendar.isleap(year) and not calendar.isleap(repeat_year_dict[year]):
                    # Add leap day
                    data_repeated_year_by_dayofyear = data_repeated_year.groupby(data_repeated_year.index.dayofyear)
                    dayofyear_order = list(range(1, 366))
                    dayofyear_order.insert(59, 59)  # Add leap day (repeat Feb 28)
                    data_repeated_year = pd.concat(
                        [data_repeated_year_by_dayofyear.get_group(dayofyear) for dayofyear in dayofyear_order], axis=0
                    )
                elif not calendar.isleap(year) and calendar.isleap(repeat_year_dict[year]):
                    # Remove leap day
                    data_repeated_year_by_dayofyear = data_repeated_year.groupby(data_repeated_year.index.dayofyear)
                    dayofyear_order = list(range(1, 367))
                    dayofyear_order.remove(60)  # Remove leap day (remove Feb 29)
                    data_repeated_year = pd.concat(
                        [data_repeated_year_by_dayofyear.get_group(dayofyear) for dayofyear in dayofyear_order], axis=0
                    )
            data_repeated = pd.concat([data_repeated, data_repeated_year], axis=0, ignore_index=True)
        data_repeated.index = new_index
        self.data = data_repeated


########################################################################################################################
# SUB-CLASSES
########################################################################################################################


class BooleanTimeseries(Timeseries):
    @field_validator("data")
    def validate_data_is_boolean(cls, data, values):
        if data.dtype != bool:
            # Try to convert to Boolean
            data = data.replace([1, 1.0, "1", "1.0", True, "TRUE", "True", "true", "T", "t"], True)
            data = data.replace([0, 0.0, "0", "0.0", False, "FALSE", "False", "false", "F", "f"], False)
            # Fillna as necessary
            data = data.fillna(method="ffill")
        # If after replacing values, the Series is still not Boolean, raise error
        assert data.dtype == bool, f"Timeseries data for {values.data['name']} should be boolean (True/False)"
        return data


class NumericTimeseries(Timeseries):
    @field_validator("data")
    def validate_data_is_numeric(cls, data):
        """Try to coerce data to be numeric."""
        return pd.to_numeric(data)

    @model_validator(mode="after")
    def validate_data_is_not_nan(self):
        if self.name != "default" and any(self.data.isna()):
            raise ValueError(f"Values for {self.name} are non-numeric: \n{self.data}")
        return self

class FractionalTimeseries(Timeseries):
    @field_validator("data")
    @classmethod
    def validate_data_is_fractional(cls, data, values):
        data = pd.to_numeric(data)
        if (data < 0 - 1e-5).any() or (data > 1 + 1e-5).any():
            df_slice = data[(data < 0) | (data > 1)]
            raise ValueError(
                f"Values for timeseries '{values.data['name']}' not all fractional, see values: \n{df_slice}"
            )
        return data
