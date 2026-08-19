from __future__ import annotations

import json
import os
import pathlib
import types
from typing import Any
from typing import Optional
from typing import Self

import pandas as pd
import pydantic
from loguru import logger
from pydantic.fields import FieldInfo

from kit.core.custom_model import BaseCustomModel
from kit.core.temporal import timeseries as ts


class BaseFromCSVMixIn(BaseCustomModel):
    """Base class to implement a standard `from_csv` class method to read from `interim` data folder."""

    @classmethod
    def _get_data_dir(cls, filename: pathlib.Path) -> pathlib.Path:
        """Return the project root directory by splitting on the ``interim`` path segment."""
        return pathlib.Path(str(filename).split("interim")[0])

    @classmethod
    def model_fields_with_aliases(cls) -> dict[str, FieldInfo]:
        """Return a merged mapping of canonical field names and their aliases to ``FieldInfo``.

        Fields without an alias appear only under their canonical name. Fields with an alias
        appear under both names, pointing to the same ``FieldInfo`` object.
        """
        return cls.model_fields | {
            field_info.alias: field_info
            for field_info in cls.model_fields.values()
            if field_info.alias
        }

    @classmethod
    def field_is_timeseries(cls, *, field_info: FieldInfo) -> bool:
        """Return ``True`` if the field's type is a ``Timeseries`` subclass."""
        types = cls.get_field_type(field_info=field_info)
        return any(
            ts_subclass in types for ts_subclass in ts.Timeseries.__subclasses__()
        )

    @classmethod
    def get_timeseries_attribute_names(cls, include_aliases: bool = False) -> list[str]:
        """Return the names of all ``Timeseries`` fields defined on this class.

        Args:
            include_aliases: if ``True``, aliases for timeseries fields are appended to the list.

        Returns:
            List of canonical attribute names (and optionally their aliases).
        """
        attribute_names = [
            attr
            for attr, field_settings in cls.model_fields.items()
            if cls.field_is_timeseries(field_info=field_settings)
        ]

        if include_aliases:
            attribute_names += [
                field_settings.alias
                for attr, field_settings in cls.model_fields.items()
                if cls.field_is_timeseries(field_info=field_settings)
                and field_settings.alias is not None
            ]

        return attribute_names

    @classmethod
    def get_timeseries_default_freqs(cls) -> dict[str, Optional[str]]:
        """Return a mapping of timeseries attribute name → ``default_freq`` string (or ``None``).

        Both canonical names and aliases are included so the dict can be keyed by whichever
        name appears in a CSV's ``attribute`` column.
        """
        ts_attrs = cls.get_timeseries_attribute_names()  # Do not include aliases
        ts_attr_default_freqs = {}
        for attr in ts_attrs:
            field_settings = cls.model_fields[attr]
            if (
                field_settings.json_schema_extra
                and "default_freq" in field_settings.json_schema_extra
            ):
                default_freq = field_settings.json_schema_extra["default_freq"]
            else:
                default_freq = None
            ts_attr_default_freqs[attr] = default_freq
            if field_settings.alias is not None:
                ts_attr_default_freqs[field_settings.alias] = default_freq
        return ts_attr_default_freqs

    @classmethod
    def _filter_highest_scenario(
        cls,
        *,
        filename: pathlib.Path,
        input_df: pd.DataFrame,
        scenarios: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Filter ``input_df`` down to the highest-priority scenario for each index value.

        Rows with no scenario tag (``None``/``NaN``) are treated as a baseline ``"__base__"``
        with the lowest priority. Rows whose scenario tag does not appear in ``scenarios`` are
        dropped entirely. When multiple rows remain for the same index value, the last one in
        priority order (highest in ``scenarios``) is kept via ``groupby().last()``.

        For timeseries slices that mix inline timestamps and file-path references (``None``
        index), the highest-priority entry wins: if the file-path reference is highest
        priority, all timestamped rows are dropped and vice versa.

        Args:
            filename: path to the source CSV, used only for log messages.
            input_df: slice of the attributes DataFrame, indexed by the relevant key column.
            scenarios: ordered list of scenario tags from lowest to highest priority.

        Returns:
            Filtered DataFrame with the ``scenario`` and ``attribute`` columns removed.
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
        input_df["scenario"] = pd.Categorical(
            input_df["scenario"], ["__base__"] + scenarios
        )

        scenarios_known = set(input_df["scenario"].dropna().unique())
        scenarios_unknown = scenarios_unique - scenarios_known

        # Drop any scenarios that weren't provided in the scenario list (or the default `__base__` tag)
        len_input_df_unfiltered = len(input_df)
        input_df = input_df.sort_values("scenario").dropna(subset="scenario")

        # Log error if scenarios filtered out all data
        if len_input_df_unfiltered != 0 and len(input_df) == 0:
            logger.warning(
                f"{filename.stem} has no data for active scenario(s): {scenarios}"
            )

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
                    logger.debug(
                        f"{msg}, CSV file reference ignored because it is **not** highest scenario priority."
                    )
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
        cls,
        *,
        filename: pathlib.Path,
        input_df: pd.DataFrame,
        scenarios: Optional[list[str]] = None,
    ) -> dict[str, ts.NoDateTimeseries]:
        """Parse ``NoDateTimeseries`` attributes from the flat attributes DataFrame.

        Identifies fields typed as ``NoDateTimeseries`` (including aliases), extracts the
        relevant rows, deduplicates by taking the last value per index, and returns a dict
        of constructed ``NoDateTimeseries`` instances keyed by attribute name.

        Args:
            filename: source CSV path; used to name each ``NoDateTimeseries`` and derive its ``data_dir``.
            input_df: full attributes DataFrame with columns ``timestamp``, ``attribute``, ``value``.
            scenarios: optional scenario priority list passed through to filtering logic.

        Returns:
            Mapping of attribute name → ``NoDateTimeseries`` instance.
        """

        # Find names of timeseries attributes based on class definition
        attribute_names = [
            attr
            for attr, field_settings in cls.model_fields.items()
            if ts.NoDateTimeseries in cls.get_field_type(field_info=field_settings)
        ]

        attribute_names += [
            field_settings.alias
            for attr, field_settings in cls.model_fields.items()
            if ts.NoDateTimeseries in cls.get_field_type(field_info=field_settings)
            and field_settings.alias is not None
        ]

        # TODO: Need to figure out a way to initialize the `timezone` and `DST` attribute
        # Deep copy used to avoid pandas "SettingWithCopyWarning"
        ts_df = input_df.loc[input_df["attribute"].isin(attribute_names), :]

        nodate_ts_df = input_df.loc[
            input_df["attribute"].isin(attribute_names), :
        ].copy(deep=True)
        nodate_ts_attrs = {}
        for attr in nodate_ts_df["attribute"].unique():
            ts_slice = nodate_ts_df.loc[
                nodate_ts_df["attribute"] == attr, ["timestamp", "value"]
            ].set_index(["timestamp"])

            # Get last instance of any duplicate values (for scenario tagging)
            ts_slice = ts_slice.groupby(ts_slice.index).last()

            ts_data = ts_slice.squeeze(axis=1)
            ts_data.index = ts_data.index.astype(float).astype(int)
            ts_data = ts_data.sort_index()
            nodate_ts_attrs[attr] = ts.NoDateTimeseries(
                name=f"{filename.stem}:{attr}",
                data=ts_data,
                data_dir=cls._get_data_dir(filename),
            )

        return nodate_ts_attrs

    @classmethod
    def _parse_timeseries_attributes(
        cls,
        *,
        filename: pathlib.Path,
        input_df: pd.DataFrame,
        scenarios: Optional[list[str]] = None,
    ) -> dict[str, ts.Timeseries]:
        """Parse ``Timeseries`` attributes from the flat attributes DataFrame.

        Identifies all ``Timeseries``-typed fields (including aliases), applies scenario
        filtering per attribute, parses datetime indices, and constructs the appropriate
        ``Timeseries`` subclass instance for each attribute. Attributes with no usable data
        (all-None values) are silently omitted from the result.

        A value of ``"None"`` in the timestamp column is treated as a file-path reference:
        the value string is passed directly to the ``Timeseries`` constructor to be resolved.

        Args:
            filename: source CSV path; used to name each ``Timeseries`` and derive its ``data_dir``.
            input_df: full attributes DataFrame with columns ``timestamp``, ``attribute``, ``value``.
            scenarios: optional scenario priority list.

        Returns:
            Mapping of attribute name → ``Timeseries`` subclass instance.
        """
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

            ts_slice = cls._filter_highest_scenario(
                filename=filename, input_df=ts_slice, scenarios=scenarios
            )

            # Try to parse index as datetime (if index is not "None")
            if "None" not in ts_slice.index:
                ts_slice.index = pd.to_datetime(ts_slice.index, format="mixed")

            # If timeseries is a filepath reference, ts_data should be a string to be parsed by `Timeseries.validate_or_convert_to_series`
            if ts_slice.index.values.tolist() == ["None"]:
                ts_data = ts_slice.loc["None", "value"]
            else:
                ts_data = ts_slice.squeeze(axis=1)

            # Construct Timeseries object for attribute (otherwise silently default to None/empty attribute)
            if len(ts_data) > 0 and (
                (isinstance(ts_data, str))
                or (
                    isinstance(ts_data, (pd.Series, dict))
                    and not ts_data.isin({None, "None"}).any()
                )
            ):
                ts_cls = cls.get_field_type(
                    field_info=cls.model_fields_with_aliases()[attr]
                )[0]
                ts_attrs[attr] = ts_cls(
                    name=f"{filename.stem}:{attr}",
                    data=ts_data,
                    data_dir=cls._get_data_dir(filename),
                    _freq=attribute_freqs[attr],
                )

        return ts_attrs

    @classmethod
    def _parse_scalar_attributes(
        cls,
        *,
        filename: pathlib.Path,
        input_df: pd.DataFrame,
        scenarios: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Parse non-timeseries (scalar) attributes from the flat attributes DataFrame.

        Collects all field names that are not typed as ``Timeseries``, plus any extra
        attribute names present in the CSV that are also not timeseries. Applies scenario
        filtering and returns the resulting attribute → value mapping.

        Args:
            filename: source CSV path; used for scenario-filter log messages.
            input_df: full attributes DataFrame with columns ``timestamp``, ``attribute``, ``value``.
            scenarios: optional scenario priority list.

        Returns:
            Mapping of attribute name → scalar value.
        """
        ts_attribute_names = cls.get_timeseries_attribute_names(include_aliases=True)

        # Find names of scalar attributes based on class definition
        attribute_names = [
            attr for attr in cls.model_fields if attr not in ts_attribute_names
        ]

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

        scalar_slice = cls._filter_highest_scenario(
            filename=filename, input_df=scalar_slice, scenarios=scenarios
        )

        # Squeeze the DataFrame into a Series, then convert to a dict
        return scalar_slice.squeeze(axis=1).to_dict()

    @classmethod
    def _parse_attributes(
        cls,
        filename: pathlib.Path,
        input_df: pd.DataFrame,
        scenarios: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Combine scalar, timeseries, and no-date-timeseries attributes into a single dict.

        Args:
            filename: source CSV path.
            input_df: full attributes DataFrame with columns ``timestamp``, ``attribute``, ``value``.
            scenarios: optional scenario priority list.

        Returns:
            Merged mapping of attribute name → parsed value, ready to pass to the class constructor.
        """
        input_df["timestamp"] = input_df["timestamp"].fillna("None")
        scalar_attrs = cls._parse_scalar_attributes(
            filename=filename, input_df=input_df, scenarios=scenarios
        )
        ts_attrs = cls._parse_timeseries_attributes(
            filename=filename, input_df=input_df, scenarios=scenarios
        )
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
    ) -> Self:
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
            **{
                "name": name if name is not None else attr_path.stem,
                "attr_path": attr_path,
            },
            **cls._parse_attributes(
                filename=attr_path, input_df=input_df, scenarios=scenarios
            ),
        }
        if data is not None:
            attrs.update(data)

        inst = cls(**attrs)

        return inst

    @classmethod
    def from_csv(
        cls,
        filename: pathlib.Path,
        scenarios: Optional[list[str]] = None,
        data: Optional[dict] = None,
        name: Optional[str] = None,
    ) -> Self:
        """Create an instance of this class from a CSV attributes file.

        The CSV must have three mandatory columns and two optional columns (order does not matter,
        but header names do):

        +--------------------------------------+------------------+---------+-----------------+---------------------+
        | timestamp                            | attribute        | value   | unit (optional) | scenario (optional) |
        +======================================+==================+=========+=================+=====================+
        | [None or timestamp (hour beginning)] | [attribute name] | [value] | [unit name]     | [scenario name]     |
        +--------------------------------------+------------------+---------+-----------------+---------------------+

        **Units**

        Units are used for documentation only. NO UNIT CONVERSION IS APPLIED! it is assumed that the
        data is in the correct units. Modified in kit ver 5.9.3 This is a departure from older
        versions of kit where units were converted.

        **Scenarios**

        Rows can carry an optional ``scenario`` tag. Tags are treated as an ordered ``pd.Categorical``
        (lowest to highest priority) and only the highest-priority value per attribute/timestamp is kept.
        Rows with no tag are treated as baseline (lowest priority); rows with unrecognised tags are dropped.

        **Duplicate Values**

        When an attribute (or timestamp) appears more than once, the last row in the CSV wins.

        **Referencing External CSVs for Timeseries Data**

        A timeseries value may be a file path instead of inline data. Use a ``None`` timestamp and set
        the value to an absolute path pointing to another CSV. That file is read as a ``pd.Series`` with
        a ``DateTimeIndex``. Mixing inline timestamps and file-path references for the same attribute is
        not supported. File-path references can themselves be scenario-tagged, but the referenced file
        is not subject to scenario filtering.

        Args:
            filename: path to the CSV attributes file.
            scenarios: scenario tags ordered from lowest to highest priority. Defaults to ``[]``.
            data: additional attribute overrides applied after CSV parsing. Defaults to ``{}``.
            name: name for the new instance; defaults to the CSV file stem.

        Returns:
            New instance of this class populated from the CSV.
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

    @classmethod
    def from_dir(
        cls, data_path: os.PathLike, scenarios: Optional[list[str]] = None
    ) -> dict[str, Self]:
        """Read all ``*.csv`` files in ``data_path`` and return a dict of instances.

        Args:
            data_path: directory containing one CSV file per instance.
            scenarios: scenario tags ordered from lowest to highest priority. Defaults to ``[]``.

        Returns:
            Mapping of instance name → instance, keyed by CSV file stem.
        """
        # TODO: Figure out how to read in selected subfolders and not just all subfolders...
        # TODO: Remove redundancy in component filepaths/names (i.e., [class]_inputs/[instance]/[class]_X_inputs.csv)
        instances = {}
        if not scenarios:
            scenarios = []

        for filename in sorted(pathlib.Path(data_path).glob("*.csv")):
            vintages = cls.from_csv(filename=filename, scenarios=scenarios)
            instances.update(vintages)

        return instances

    @classmethod
    def from_json(cls, filepath: os.PathLike) -> Self:
        """Deserialise a JSON file back into an instance of this class."""

        with open(filepath, "r") as json_file:
            data = json.load(json_file)
        return cls(**data)

    @classmethod
    def _linkage_base_classes(cls) -> tuple:
        """Return the base classes used to identify linkage fields on this class.

        Downstream repos override this to return their own ``Linkage`` base class(es).
        The default returns an empty tuple, meaning no fields are treated as linkages.
        """
        return ()

    @classmethod
    def get_linkage_attrs(cls) -> list[str]:
        """Return the names of fields whose type is a subclass of any ``_linkage_base_classes``."""
        linkage_attrs = []
        for field_name, field_info in cls.model_fields.items():
            if type(field_info.annotation) == types.GenericAlias and any(
                issubclass(t, cls._linkage_base_classes())
                for t in field_info.annotation.__args__
            ):
                linkage_attrs.append(field_name)
        return linkage_attrs

    @pydantic.root_validator(pre=True)
    @classmethod
    def annual_input_validator(cls, values: dict) -> dict:
        """Validate and normalise annual timeseries inputs.

        For any ``Timeseries`` field whose ``down_method`` is ``"annual"``:
        - Raises ``ValueError`` if more than one value is provided for the same year.
        - Reindexes timestamps to ``YYYY-01-01 00:00:00`` if they are not already at midnight on January 1st.
        """
        aliases = {
            field_settings.alias: attr
            for attr, field_settings in cls.model_fields.items()
        }
        aliases.update(
            {attr: attr for attr, field_settings in cls.model_fields.items()}
        )

        for value in values:
            # In this situation, all the ts attributes are still the base ts (and not a subclass) when first initialized
            if (
                isinstance(values[value], ts.Timeseries)
                and cls.model_fields[aliases[value]].json_schema_extra["down_method"]
                == "annual"
            ):
                year_list = values[value].data.index.year.to_list()
                if len(year_list) > len(set(year_list)):
                    raise ValueError(
                        f"{values['name']} '{value}' input data must be annual inputs"
                    )
                elif any(
                    (idx.month != 1 or idx.day != 1 or idx.hour != 0)
                    for idx in values[value].data.index
                ):
                    # If any indices are not 1/1 0:00, force to 1/1 0:00
                    logger.warning(
                        f"{values['name']} annual attribute {value} reindexed to annual level"
                    )
                    new_index = [str(year) + "-01-01 00:00:00" for year in year_list]
                    new_index = pd.to_datetime(new_index)
                    values[value].data.index = new_index
        return values
