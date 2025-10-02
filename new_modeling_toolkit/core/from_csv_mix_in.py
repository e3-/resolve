from __future__ import annotations

import pathlib
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import pandas as pd
from loguru import logger

from new_modeling_toolkit.core.custom_model import CustomModel
from new_modeling_toolkit.core.temporal import timeseries as ts


class FromCSVMixIn(CustomModel):
    """Base class to implement a standard `from_csv` class method to read from `interim` data folder."""

    @classmethod
    def model_fields_with_aliases(cls):
        return cls.model_fields | {
            field_info.alias: field_info for field_info in cls.model_fields.values() if field_info.alias
        }

    @classmethod
    def field_is_timeseries(cls, *, field_info) -> bool:
        types = cls.get_field_type(field_info=field_info)
        return any(ts_subclass in types for ts_subclass in ts.Timeseries.__subclasses__())

    @classmethod
    def get_timeseries_attribute_names(cls, include_aliases: bool = False):
        attribute_names = [
            attr
            for attr, field_settings in cls.model_fields.items()
            if cls.field_is_timeseries(field_info=field_settings)
        ]

        if include_aliases:
            attribute_names += [
                field_settings.alias
                for attr, field_settings in cls.model_fields.items()
                if cls.field_is_timeseries(field_info=field_settings) and field_settings.alias is not None
            ]

        return attribute_names

    @classmethod
    def get_timeseries_default_freqs(cls):
        ts_attrs = cls.get_timeseries_attribute_names()  # Do not include aliases
        ts_attr_default_freqs = {}
        for attr in ts_attrs:
            field_settings = cls.model_fields[attr]
            if field_settings.json_schema_extra and "default_freq" in field_settings.json_schema_extra:
                default_freq = field_settings.json_schema_extra["default_freq"]
            else:
                default_freq = None
            ts_attr_default_freqs[attr] = default_freq
            if field_settings.alias is not None:
                ts_attr_default_freqs[field_settings.alias] = default_freq
        return ts_attr_default_freqs

    @classmethod
    def _filter_highest_scenario(
        cls, *, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: Optional[list[str]] = None
    ) -> pd.DataFrame:
        """Filter for the highest priority data based on scenario tags.

        scenarios_unknown: Scenario tags that aren't known to the Categorical
        scenarios_overridden: Scenario tags that were overridden
        scenarios_used: Scenario tags that made it to the final attribute
        """

        # Create/fill a dummy (base) scenario tag that has the lowest priority order
        if "scenario" not in input_df.columns:
            input_df["scenario"] = "__base__"
        # Create a dummy (base) scenario tag that has the lowest priority order
        input_df["scenario"] = input_df["scenario"].fillna("__base__")

        scenarios_unique = set(input_df["scenario"].fillna("__base__").unique())

        # Create a categorical data type in the order of the scenario priority order (lowest to highest)
        if scenarios is None:
            scenarios = []
        input_df["scenario"] = pd.Categorical(input_df["scenario"], ["__base__"] + scenarios)

        scenarios_known = set(input_df["scenario"].dropna().unique())
        scenarios_unknown = scenarios_unique - scenarios_known

        # Drop any scenarios that weren't provided in the scenario list (or the default `__base__` tag)
        len_input_df_unfiltered = len(input_df)
        input_df = input_df.sort_values("scenario").dropna(subset="scenario")

        # Log error if scenarios filtered out all data
        if len_input_df_unfiltered != 0 and len(input_df) == 0:
            logger.warning(f"{filename.stem} has no data for active scenario(s): {scenarios}")

        # Timeseries slices may have a "mixed index" (i.e., some `None` and some timestamps)
        if input_df.index.name != "attribute":
            # This isn't the most robust check, but should work for now
            unique_index = input_df.index.unique().tolist()
            if "None" in unique_index and len(unique_index) > 1:
                msg = f"For {filename.stem}, {input_df['attribute'].iloc[0]}"
                # If `None`-indexed timeseries data is the highest priority, drop all timestamped data
                if unique_index[-1] == "None":
                    logger.debug(
                        f"{msg}, CSV reference overrides other timeseries data because it is the highest scenario priority."
                    )
                    input_df = input_df.loc[input_df.index == "None"]
                # If `None`-indexed timeseries data is **not** the highest priority, drop it
                else:
                    logger.debug(f"{msg}, CSV file reference ignored because it is **not** highest scenario priority.")
                    input_df = input_df.loc[input_df.index != "None"]

        # Keep only highest priority scenario data
        input_df = input_df.groupby(input_df.index.names).last()

        # TODO FINISH THIS
        scenarios_used = set(input_df["scenario"].unique())
        scenarios_overridden = scenarios_known - scenarios_used

        scenario_stats = {
            "known": scenarios_known,
            "unknown": scenarios_unknown,
            "used": scenarios_used,
            "overridden": scenarios_overridden,
        }

        # Drop unneeded columns
        return input_df.drop(columns=["scenario", "attribute"], errors="ignore")

    @classmethod
    def _parse_nodate_timeseries_attributes(
        cls, *, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: Optional[list[str]] = None
    ) -> dict[str, ts.NoDateTimeseries]:
        """Temporarily reimplement nodate_timeseries."""

        # Find names of timeseries attributes based on class definition
        attribute_names = [
            attr
            for attr, field_settings in cls.model_fields.items()
            if ts.NoDateTimeseries in cls.get_field_type(field_info=field_settings)
        ]

        attribute_names += [
            field_settings.alias
            for attr, field_settings in cls.model_fields.items()
            if ts.NoDateTimeseries in cls.get_field_type(field_info=field_settings) and field_settings.alias is not None
        ]

        # TODO: Need to figure out a way to initialize the `timezone` and `DST` attribute
        # Deep copy used to avoid pandas "SettingWithCopyWarning"
        ts_df = input_df.loc[input_df["attribute"].isin(attribute_names), :]

        nodate_ts_df = input_df.loc[input_df["attribute"].isin(attribute_names), :].copy(deep=True)
        nodate_ts_attrs = {}
        for attr in nodate_ts_df["attribute"].unique():
            ts_slice = nodate_ts_df.loc[nodate_ts_df["attribute"] == attr, ["timestamp", "value"]].set_index(
                ["timestamp"]
            )

            # Get last instance of any duplicate values (for scenario tagging)
            ts_slice = ts_slice.groupby(ts_slice.index).last()

            if len(ts_slice) == 1:
                ts_data = ts_slice.to_dict()["value"]
            else:
                ts_data = ts_slice.squeeze()
            ts_data.index = ts_data.index.astype(float).astype(int)
            ts_data = ts_data.sort_index()
            nodate_ts_attrs[attr] = ts.NoDateTimeseries(
                name=f"{filename.stem}:{attr}",
                data=ts_data,
                data_dir=pathlib.Path(str(filename).split("interim")[0]).parent,
            )

        return nodate_ts_attrs

    @classmethod
    def _parse_timeseries_attributes(
        cls, *, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: Optional[list[str]] = None
    ) -> dict[str, ts.Timeseries]:
        """Create `Timeseries` instances for timeseries data."""
        # Find names of timeseries attributes based on class definition
        attribute_names = cls.get_timeseries_attribute_names(include_aliases=True)
        attribute_freqs = cls.get_timeseries_default_freqs()

        # TODO: Need to figure out a way to initialize the `timezone` and `DST` attribute
        # Deep copy used to avoid pandas "SettingWithCopyWarning"
        ts_df = input_df.loc[input_df["attribute"].isin(attribute_names), :]

        # Need to loop through each timeseries attribute separately and fill dict of ts.Timeseries instances
        ts_attrs = {}
        for attr in ts_df["attribute"].unique():
            ts_slice = ts_df.loc[ts_df["attribute"] == attr, :].set_index(["timestamp"])

            ts_slice = cls._filter_highest_scenario(filename=filename, input_df=ts_slice, scenarios=scenarios)

            # Try to parse index as datetime (if index is not "None")
            if "None" not in ts_slice.index:
                ts_slice.index = pd.to_datetime(ts_slice.index, infer_datetime_format=True)

            # If timeseries is a filepath reference, ts_data should be a string to be parsed by `Timeseries.validate_or_convert_to_series`
            if ts_slice.index.values.tolist() == ["None"]:
                ts_data = ts_slice.loc["None", "value"]
            else:
                ts_data = ts_slice.squeeze(axis=1)

            # Construct Timeseries object for attribute (otherwise silently default to None/empty attribute)
            if len(ts_data) > 0 and (
                (isinstance(ts_data, str))
                or (isinstance(ts_data, (pd.Series, dict)) and not ts_data.isin({None, "None"}).any())
            ):
                ts_cls = cls.get_field_type(field_info=cls.model_fields_with_aliases()[attr])[0]
                ts_attrs[attr] = ts_cls(
                    name=f"{filename.stem}:{attr}",
                    data=ts_data,
                    data_dir=pathlib.Path(str(filename).split("interim")[0]),
                    _freq=attribute_freqs[attr],
                )

        return ts_attrs

    @classmethod
    def _parse_scalar_attributes(
        cls, *, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: Optional[list[str]] = None
    ) -> dict[str, Any]:
        ts_attribute_names = cls.get_timeseries_attribute_names(include_aliases=True)

        # Find names of scalar attributes based on class definition
        attribute_names = [attr for attr in cls.model_fields if attr not in ts_attribute_names]

        attribute_names += [
            attr
            for attr in input_df["attribute"].unique()
            if attr not in attribute_names and attr not in ts_attribute_names
        ]

        scalar_slice = (
            input_df.loc[input_df["attribute"].isin(attribute_names), :]
            .drop(columns=["timestamp"])
            .set_index(["attribute"])
        )

        scalar_slice = cls._filter_highest_scenario(filename=filename, input_df=scalar_slice, scenarios=scenarios)

        # Squeeze the DataFrame into a Series, then convert to a dict
        return scalar_slice.squeeze(axis=1).to_dict()

    @classmethod
    def _parse_attributes(
        cls, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: Optional[list[str]] = None
    ) -> dict[str, Any]:
        input_df["timestamp"] = input_df["timestamp"].fillna("None")
        scalar_attrs = cls._parse_scalar_attributes(filename=filename, input_df=input_df, scenarios=scenarios)
        ts_attrs = cls._parse_timeseries_attributes(filename=filename, input_df=input_df, scenarios=scenarios)
        nodate_ts_attrs = cls._parse_nodate_timeseries_attributes(
            filename=filename, input_df=input_df, scenarios=scenarios
        )

        attrs = {
            **scalar_attrs,
            **ts_attrs,
            **nodate_ts_attrs,
        }

        return attrs

    @classmethod
    def from_dataframe(
        cls,
        *,
        input_df: pd.DataFrame,
        attr_path: Optional[pathlib.Path] = None,
        scenarios: Optional[list[str]] = None,
        data: Optional[dict] = None,
        name: Optional[str] = None,
    ):
        """Create an instance of the class from an input DataFrame.

        The input DataFrame will optionally be filtered by a list of scenarios ordered from lowest to highest priority.
        At least one of `attr_path` or `name` must be specified in order to name the newly created object.

        Args:
            input_df: the input DataFrame to use to instantiate the class
            attr_path: optional path to the CSV from which the input DataFrame was loaded
            scenarios: optional list of scenarios used to filter the input DataFrame
            data: optional dictionary of attribute data used to override data parsed from the input DataFrame
            name: name for the new object

        Returns:
            inst: instance of the class
        """
        attrs = {
            **{"name": name if name is not None else attr_path.stem, "attr_path": attr_path},
            **cls._parse_attributes(filename=attr_path, input_df=input_df, scenarios=scenarios),
        }
        if data is not None:
            attrs.update(data)

        inst = cls(**attrs)

        return inst

    @classmethod
    def from_csv(
        cls,
        filename: pathlib.Path,
        scenarios: Optional[List] = None,
        data: Optional[Dict] = None,
        name: Optional[str] = None,
    ) -> FromCSVMixIn:
        """Create Component instance from CSV input file.

        The CSV input file must have the following mandatory three-column format, with two optional columns
        (column order does not matter; however, **column header names do matter**):

        +--------------------------------------+------------------+---------+-----------------+---------------------+
        | timestamp                            | attribute        | value   | unit (optional) | scenario (optional) |
        +======================================+==================+=========+=================+=====================+
        | [None or timestamp (hour beginning)] | [attribute name] | [value] | [unit name]     | [scenario name]     |
        +--------------------------------------+------------------+---------+-----------------+---------------------+

        **Units**

        Unit conversion is handled by the ``pint`` Python package. Expected attribute units are hard-coded in the Python
        implementation. If the `pint` package can find an appropiate conversion between the user-specified input of the
        attribute and the expected unit, it will convert data automatically to the expected unit.

        For example, if the expected unit is MMBtu (named as `million_Btu` or `MBtu` in `pint`), a user can easily
        enter data in `Btu`, and the code will automatically divide the input value by 1e6.

        **Scenarios**

        Scenarios are handled via an optional `scenario` column. Scenario handling is done via some clever pandas
        DataFrame sorting. In detail:

        #. The ``scenario`` column is converted to a `pd.Categorical`_, which is an ordered list.
        #. The ``scenario`` columns is sorted based on the Categorical ordering,
           where values with no scenario tag (``None``/``NaN``) are lowest-priority.
        #. The method ``df.groupby.last()`` is used to take the last (highest-priority) value
           (since the dataframe should be sorted from lowest to highest priority scenario tag).
        #. Scenario tags that are not listed in scenarios.csv will be ignored completely (dropped from the dataframe).

        **Duplicate Values**

        If an attribute is defined multiple times (and for a timeseries, multiple times for the same timestamp),
        the last value entered in the CSV (i.e., furthest down the CSV rows) will be used.

        Args:
            filename: Name of CSV input file. Defaults to ``attributes.csv``.
            scenarios: List of optional scenario tags to filter input data in file. Defaults to [].
            data: Additional data to add to the instance as named attributes. Defaults to {}.

        **Referencing Other CSVs for Timeseries Data**

        To keep the ``attributes.csv`` shorter, user can optionally enter the value of a timeseries as a file path to
        another CSV file instead of entering each timestamped data value in ``attributes.csv``.
        This is done by using the ``None`` timestamp and entering a string filepath for the value.
        Absolute paths are preferred for the sake of being explicit, though relative paths will be parsed
        relative to the top-level ``new-modeling-toolkit`` folder.

        There are two limitations of this functionality:

        #. It is not currently possible to "mix-and-match" timeseries data specified in the attributes.csv file
           and from other referenced CSV files. You must either (a) input timeseries data in ``attributes.csv`` with
           timestamps or (b) use the ``None`` timestamp and reference a different file.
        #. Timeseries data read from another CSV file does not currently benefit scenario-tagging capabilities.
           The filepath references themselves in ``attributes.csv`` can be scenario-tagged; however, the other CSV file
           is just read in as if it were a ``pd.Series`` with a DateTimeIndex.

        Returns:
            (C): Instance of Component class.

        .. _pd.Categorical:
            https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Categorical.html
        """
        # Setting mutable [] or {} as default argument is dangerous, so this is the workaround
        if not scenarios:
            scenarios = []
        if not data:
            data = {}
        logger.debug(f"Reading from {filename}")

        input_df = pd.read_csv(filename).sort_index()

        inst = cls.from_dataframe(
            input_df=input_df,
            attr_path=filename,
            scenarios=scenarios,
            data=data,
            name=name,
        )

        return inst
