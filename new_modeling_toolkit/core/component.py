import json
import os
import pathlib
import re
from typing import Dict
from typing import List
from typing import Optional
from typing import TypeVar
from typing import Union

import pandas as pd
import pint
import pydantic
from loguru import logger
from pydantic import Field
from tqdm.notebook import tqdm

from new_modeling_toolkit import ureg
from new_modeling_toolkit.core import custom_model
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.timeseries import TimeseriesType
from new_modeling_toolkit.core.utils.core_utils import filter_not_none
from new_modeling_toolkit.core.utils.core_utils import map_dict

# Create an alias Component class type annotation (see return value in `from_csv` method)
C = TypeVar("Component")
# TODO: This doesn't seem to work as-expected for return type annotation


class Component(custom_model.CustomModel):
    attr_path: Optional[Union[str, pathlib.Path]] = Field(
        pathlib.Path.cwd(), description="the path to the attributes file"
    )
    """Based class to implement a standard `from_csv` class method to read from `interim` data folder."""

    def __repr__(self):
        """WORKAROUND because default pydantic model __repr__ causing trouble with error handling."""

        return str(self.name)

    @classmethod
    def get_timeseries_attribute_names(cls, include_aliases: bool = False):
        attribute_names = [
            attr
            for attr, field_settings in cls.__fields__.items()
            if field_settings.type_ in ts.Timeseries.__subclasses__()
        ]

        if include_aliases:
            attribute_names += [
                field_settings.alias
                for attr, field_settings in cls.__fields__.items()
                if field_settings.type_ in ts.Timeseries.__subclasses__() and field_settings.alias is not None
            ]

        return attribute_names

    @classmethod
    def get_timeseries_default_freqs(cls):
        ts_attrs = cls.get_timeseries_attribute_names()  # Do not include aliases
        ts_attr_default_freqs = {}
        for attr in ts_attrs:
            field_settings = cls.__fields__[attr]
            if "default_freq" in field_settings.field_info.extra:
                default_freq = field_settings.field_info.extra["default_freq"]
            else:
                default_freq = None
            ts_attr_default_freqs[attr] = default_freq
            if field_settings.alias is not None:
                ts_attr_default_freqs[field_settings.alias] = default_freq
        return ts_attr_default_freqs

    @pydantic.root_validator(pre=True)
    def annual_input_validator(cls, values):
        """
        Checks that all timeseries data with down_method == 'annual' only has one input per year
        and sets the datetime index to be January 1st at midnight
        """
        aliases = {field_settings.alias: attr for attr, field_settings in cls.__fields__.items()}
        aliases.update({attr: attr for attr, field_settings in cls.__fields__.items()})

        for value in values:
            # In this situation, all the ts attributes are still the base ts (and not a subclass) when first initialized
            if (
                isinstance(values[value], ts.Timeseries)
                and cls.__fields__[aliases[value]].field_info.extra["down_method"] == "annual"
            ):
                year_list = values[value].data.index.year.to_list()
                if len(year_list) > len(set(year_list)):
                    raise ValueError(f"{values['name']} '{value}' input data must be annual inputs")
                elif any((idx.month != 1 or idx.day != 1 or idx.hour != 0) for idx in values[value].data.index):
                    # If any indices are not 1/1 0:00, force to 1/1 0:00
                    logger.warning(f"{values['name']} annual attribute {value} reindexed to annual level")
                    new_index = [str(year) + "-01-01 00:00:00" for year in year_list]
                    new_index = pd.to_datetime(new_index)
                    values[value].data.index = new_index
        return values

    @property
    def timeseries_attrs(self):
        # find all timeseries attributes in instance
        return [
            attr
            for attr, field_settings in self.__fields__.items()
            if field_settings.type_ in ts.Timeseries.__subclasses__()
        ]

    @classmethod
    def _parse_units(cls):
        pass

    @classmethod
    def _filter_highest_scenario(cls, *, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: list):
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
    def _parse_nodate_timeseries_attributes(cls, *, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: list):
        """Temporarily reimplement nodate_timeseries."""

        # Find names of timeseries attributes based on class definition
        attribute_names = [
            attr for attr, field_settings in cls.__fields__.items() if field_settings.type_ == ts.NoDateTimeseries
        ]

        attribute_names += [
            field_settings.alias
            for attr, field_settings in cls.__fields__.items()
            if field_settings.type_ == ts.NoDateTimeseries and field_settings.alias is not None
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
    def _parse_timeseries_attributes(cls, *, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: list):
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
                try:
                    ts_attrs[attr] = ts.Timeseries(
                        name=f"{filename.stem}:{attr}",
                        data=ts_data,
                        data_dir=pathlib.Path(str(filename).split("interim")[0]).parent,
                        _freq=attribute_freqs[attr],
                    )
                except Exception as e:
                    raise ValueError(
                        f"Could not create timeseries `{attr}` for Component `{cls.__name__}` `{filename.stem}`"
                    ) from e

        return ts_attrs

    @classmethod
    def _parse_scalar_attributes(cls, *, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: list):
        ts_attribute_names = cls.get_timeseries_attribute_names(include_aliases=True)

        # Find names of scalar attributes based on class definition
        attribute_names = [attr for attr, field_settings in cls.__fields__.items() if attr not in ts_attribute_names]

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
    def _parse_vintages(
        cls,
        *,
        filename: pathlib.Path,
        input_df: pd.DataFrame,
        separate_vintages: bool,
        scenarios: list,
        data: dict,
        name: Optional[str] = None,
    ):
        # TODO 2023-04-23: Seems like vintages would be based on MODELED_YEARS + "planned", so need to have NewTemporalSettings happen before component reading?
        vintages = {}

        # Get list of vintages to construct (if separate_vintages == False, the list has just one vintage)
        if separate_vintages:
            if "vintage" in input_df.columns:
                vintages_to_construct = input_df["vintages"].unique()  # TODO: intersect with MODELED_YEARS
            # If no "vintage" column in attributes CSV, need to infer based on "old" (Resolve) assumptions
            else:
                # Add vintage attribute
                # Create list of vintages to loop through and slice the input_df by
                vintages_to_construct = [1]
        else:
            # Create placeholder vintage, string "None" because checking for None-type in DataFrame is funky
            input_df["vintages"] = "None"
            vintages_to_construct = ["None"]

        # Construct each vintage
        for vintage in vintages_to_construct:
            vintage_slice = input_df.loc[input_df["vintages"] == vintage, :].drop(columns=["vintages"])
            scalar_attrs = cls._parse_scalar_attributes(filename=filename, input_df=vintage_slice, scenarios=scenarios)
            ts_attrs = cls._parse_timeseries_attributes(filename=filename, input_df=vintage_slice, scenarios=scenarios)
            nodate_ts_attrs = cls._parse_nodate_timeseries_attributes(
                filename=filename, input_df=vintage_slice, scenarios=scenarios
            )
            attrs = {
                **{"name": (name if name is not None else filename.stem), "attr_path": filename},
                **scalar_attrs,
                **ts_attrs,
                **nodate_ts_attrs,
                **data,
            }
            vintages[attrs["name"]] = cls(**attrs)

        return vintages

    @classmethod
    def from_csv(
        cls,
        filename: pathlib.Path,
        separate_vintages: bool = False,
        scenarios: Optional[List] = None,
        data: Optional[Dict] = None,
        return_type=dict,
        name: Optional[str] = None,
    ) -> Union[dict[str, "Component"], tuple[str, "Component"]]:
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

        if return_type == dict:
            return cls._parse_vintages(
                filename=filename,
                input_df=input_df,
                separate_vintages=separate_vintages,
                scenarios=scenarios,
                data=data,
                name=name,
            )
        elif return_type == tuple:
            return cls._parse_vintages(
                filename=filename,
                input_df=input_df,
                separate_vintages=separate_vintages,
                scenarios=scenarios,
                data=data,
                name=name,
            ).popitem()

    @classmethod
    def from_dir(cls, data_path: os.PathLike, scenarios: Optional[list] = None) -> dict[str, C]:
        """Read instances from directory of instances with attribute.csv files.

        Args:
            data_path:

        Returns:

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
    def from_json(cls, filepath: os.PathLike) -> C:
        """Reads JSON file back to Component object."""

        with open(filepath, "r") as json_file:
            data = json.load(json_file)
        return cls(**data)

    @classmethod
    def get_data_from_xlwings(
        cls, wb: "Book", sheet_name: str, fully_specified: bool = False, new_style: bool = False
    ) -> pd.DataFrame:
        """Collect all attribute data from a specified Excel workbook using ``xlwings``.

        Searches the specified worksheet for named ranges that match attribute (or alias) names.
        Assumes all data for a given Component is stored in one sheet.

        Args:
            wb: An ``xlwings`` workbook, assuming a standard tabular format for data layout.
            sheet_name: Name of worksheet.

        Returns:
            data: Combined, "long" DataFrame, where the data is indexed by instance names & scenarios.
        """
        sheet = wb.sheets[sheet_name]

        # Clear filters applied to sheet
        sheet.api.AutoFilterMode = False

        # Add single quotes around sheet names with spaces (to match Excel naming convention)
        if " " in sheet_name:
            sheet_name = f"'{sheet_name}'"

        # Get all named ranges that refer to the current sheet
        # 2024-04-15: Workaround due to `wb.names` timing out on macOS because it's slow
        all_names = wb.sheets["__names__"].range("A1").expand().options(pd.DataFrame, index=False, header=False).value
        all_names.columns = ["name", "address"]
        named_ranges: set = set(all_names.loc[all_names["address"].str.contains(sheet_name), "name"].tolist())
        wb.app.status_bar = f"Found {len(named_ranges)} attribute tables for {cls.__name__} on {sheet_name}"

        # By default, the component as a named range must exist at least once on a sheet
        tables = [cls.__name__]

        # Sometimes, component can be split across multiple tables (see Emissions Target AllToPolicy and AllToPolicy.__2)
        tables += filter(lambda n: re.match(f"(.*?){cls.__name__}.\__[0-9]+$", n), named_ranges)

        data_combined = None
        for table in tables:
            if "!" in table:
                table = table.split("!")[1]

            # Get index as two long lists (assumes range is "tall" and not "wide")
            # We force xlwings to return the range as 2-dimensional and transpose is to ensure that we always get a list of "long" lists
            index: list = sheet.range(table).options(ndim=2, transpose=True).value

            # Get all scenario tags (or return a index-length list of None)
            # TODO 2023-06-13: This is messier than it needs to be...but works for now
            scenario: list = []
            if f"{table}.scenario" in named_ranges:
                scenario += [sheet.range(f"{table}.scenario").options(ndim=1).value]
            if f"{sheet_name}!{table}.scenario" in named_ranges:
                scenario += [sheet.range(f"{sheet_name}!{table}.scenario").options(ndim=1).value]
            if not scenario:
                scenario += [[None] * len(index[0])]

            # Get name of all possible attributes (including aliases) and putting the sheet name (for named ranges that refer only to Worksheet)
            attribute_names: set = set(cls.__fields__.keys()) | {f.alias for f in cls.__fields__.values()}
            # If `fully_specified` is true, named range must have the class name (instead of the code trying to find both `scenario` and `Policy.scenario` for example)
            if fully_specified:
                attribute_names = {f"{table}.{name}" for name in attribute_names}
            else:
                attribute_names |= {f"{table}.{name}" for name in attribute_names}
            attribute_names |= {f"{sheet_name}!{attribute}" for attribute in attribute_names}

            # Find all attribute names that correspond to named ranges on this sheet
            ranges_to_search: list = sorted(named_ranges.intersection(attribute_names))

            if ranges_to_search:
                # Create one large dataframe of all instances & attributes from this sheet
                if new_style:
                    dfs = {}
                    for attribute in ranges_to_search:
                        dfs[attribute] = (
                            sheet.range(attribute)
                            .offset(row_offset=-1)
                            .resize(sheet.range(attribute).shape[0] + 1, sheet.range(attribute).shape[1])
                            .options(pd.DataFrame, header=1, index=0)
                            .value
                        )
                        dfs[attribute].columns = pd.MultiIndex.from_product(
                            [[attribute.split(".")[-1]], dfs[attribute].columns]
                        )
                    data = pd.concat(dfs.values(), axis=1)

                else:
                    data = pd.concat(
                        [
                            sheet.range(attribute).options(pd.DataFrame, header=2, index=0).value
                            for attribute in ranges_to_search
                        ],
                        axis=1,
                    )
                data.index = index + scenario

                # Unpivot dataframe
                data = data.melt(ignore_index=False).rename(
                    columns={
                        "variable_0": "attribute",
                        "variable_1": "timestamp",
                    }
                )

                # TODO 2022-09-28: Pathways branch had an in/else to create an empty dataframe if there were no attributes; however,
                #                  I was unclear whether that was an issue we needed to catch

                # Clean up `timestamp` column (fill None and convert to dates, assuming header timestamp is just a year number)
                data["timestamp"] = pd.to_datetime(data["timestamp"], errors="ignore").fillna("None")

                # Replace any empty strings with `None`
                data["value"] = data["value"].replace("", None)
            else:
                data = pd.DataFrame(index=index + scenario, columns=["attribute", "timestamp", "value"])

            if data_combined is None:
                data_combined = data
            else:
                data_combined = pd.concat([data_combined, data], axis=0)

        return data_combined

    @classmethod
    def save_instance_attributes_csvs(
        cls, wb: "Book", data: pd.DataFrame, save_path: pathlib.Path, overwrite: bool = True
    ):
        """Save DataFrame in ``attributes.csv`` format, splitting DataFrame into separate CSVs for each instance.

        This method assumes the following (where ``n`` is the number of rows in the data tables in the corresponding sheet):
            - An ``n``-length named range (named as the name of the class) for the "index" (instance or component_from/_to names) of the data.
            - An ``n``-length named range (named as `{classname}.scenario`) for the scenario tags of the data
            - Separate ``n+2``-length named ranges for each attribute (named as the attribute name) with **two header rows above the data** (attribute name, timestamp)

        Args:
            wb: An ``xlwings`` workbook (only used to method prints a progress message)
            df: Combined DataFrame in "long" ``attributes.csv`` format (see ``cls.get_data_from_xlwings``).
            save_folder: Path to folder that will hold CSV files.
            overwrite: Whether this method should overwrite an existing attributes.csv file. Otherwise, will append unique values to existing file.
                # TODO 2022-05-05: Add this overwrite feature

        Returns:

        """
        data = data.reset_index().rename(
            columns={
                "level_0": "instance",
                "level_1": "scenario",
            }
        )
        # Print out CSVs for each instance, throwing away any empty values
        progress_bar = tqdm(total=len(sorted(data["instance"].dropna().unique())), display=False, smoothing=None)
        for instance in sorted(data["instance"].dropna().unique()):
            progress_bar.update()
            excel_progress_bar = str(progress_bar)

            # Join all attribute tables into one large DataFrame
            wb.app.status_bar = f"Writing {cls.__name__}: {excel_progress_bar} {instance}"

            df = (
                data.loc[data["instance"] == instance, ["timestamp", "attribute", "value", "scenario"]]
                .dropna(subset="value")
                .sort_values(["attribute", "scenario"])
            )
            file_path = save_path / f"{instance}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(file_path, index=False)
        progress_bar.close()

    def revalidate(self):
        """Abstract method to run additional validations after `Linkage.announce_linkage_to_instances`."""

    def resample_ts_attributes(
        self,
        modeled_years: tuple[int, int],
        weather_years: tuple[int, int],
        resample_weather_year_attributes=True,
        resample_non_weather_year_attributes=True,
    ):
        """Resample timeseries attributes to the default frequencies to make querying via `slice_by_timepoint` and
        `slice_by_year` more consistent later.

        1. Downsample data by comparing against a "correct index" with the correct default_freq
        2. If data start year > modeled start year, fill timeseries backward
        3. Create a temporary timestamp for the first hour of the year **after** the modeled end year
           to make sure we have all the hours, minutes (e.g., 23:59:59) filled in in step (4)
        4. Resample to fill in any data (particularly at end of timeseries) and drop temporary timestamp from (3)

        """
        model_year_start, model_year_end = modeled_years
        weather_year_start, weather_year_end = weather_years

        # find all timeseries attributes in instance
        timeseries_attrs = [
            attr
            for attr, field_settings in self.__fields__.items()
            if field_settings.type_ in ts.Timeseries.__subclasses__()
        ]

        extrapolated = set()
        for attr in timeseries_attrs:
            # Don't try resampling empty ts data
            if getattr(self, attr) is None:
                continue

            # Get the resampling settings from the pydantic.Field definition
            field_settings = self.__fields__[attr].field_info.extra

            # There are now TWO ways to identify toggle timeseries types (hard-coded or via an attribute called `[attr]__type`)
            is_weather_year = ("weather_year" in field_settings and field_settings["weather_year"]) or (
                getattr(self, f"{attr}__type", None) == TimeseriesType.WEATHER_YEAR
            )
            # More hackiness for month-/season-hour profiles
            if month_or_season_hour := (
                getattr(self, f"{attr}__type", None) == TimeseriesType.MONTH_HOUR
                or getattr(self, f"{attr}__type", None) == TimeseriesType.SEASON_HOUR
                or getattr(self, f"{attr}__type", None) == TimeseriesType.MONTHLY
            ):
                getattr(self, attr).type = getattr(self, f"{attr}__type", None)

                # Drop year, since we only care about month/season and hour for month-/season-hour data
                if isinstance(getattr(self, attr).data.index, pd.DatetimeIndex):
                    getattr(self, attr).data.index = getattr(self, attr).data.index.strftime("%m-01 %H:00:00")

                # Warnings, since we're not doing any resampling for month-/season-hour timeseries
                if getattr(self, attr).type == TimeseriesType.MONTHLY:
                    assert (
                        len(getattr(self, attr).data) == 12
                    ), f"Month-hour data for {self.name} {attr} is the wrong size. Should be exactly 12 values."
                elif getattr(self, attr).type == TimeseriesType.MONTH_HOUR:
                    assert (
                        len(getattr(self, attr).data) == 12 * 24
                    ), f"Month-hour data for {self.name} {attr} is the wrong size. Should be exactly 288 values."
                elif getattr(self, attr).type == TimeseriesType.SEASON_HOUR:
                    assert (
                        len(getattr(self, attr).data) == 4 * 24
                    ), f"Season-hour data for {self.name} {attr} is the wrong size. Should be exactly 96 values."
            else:
                month_or_season_hour = False

            # TODO 2023-07-17: These are sort of goofy...
            do_not_resample_weather_year = is_weather_year and not resample_weather_year_attributes
            do_not_resample_modeled_year = not is_weather_year and not resample_non_weather_year_attributes

            # Skip this attribute if we're not resampling
            if do_not_resample_modeled_year or do_not_resample_weather_year or month_or_season_hour:
                continue

            temp = getattr(self, attr)

            if temp is not None:
                # if data is input in weather year, only resample to weather year boundaries
                if is_weather_year:
                    year_start = weather_year_start
                    year_end = weather_year_end
                    # TODO: This is a bandaid that sets the Timeseries instance attribute to True if the Field in the System is also True
                    temp.weather_year = True
                else:
                    year_start = model_year_start
                    year_end = model_year_end
                    temp.weather_year = False
                # 1. Downsample data by comparing against a "correct index" with the correct default_freq
                correct_index = pd.date_range(
                    f"{temp.data.index.year[0]}-01-01 00:00:00",
                    f"{temp.data.index.year[-1]}-12-31 23:59:59",
                    freq=field_settings["default_freq"],
                )
                if len(correct_index) < len(temp.data.index):
                    logger.debug(f"Downsampling {attr}")
                    temp.data = ts.Timeseries.resample_down(
                        temp.data,
                        field_settings["default_freq"],
                        field_settings["down_method"],
                    )

                # 2. If data start year > modeled start year or timeseries does not start on January 1st, fill timeseries backward
                # Create a temporary timestamp for the year ** before ** the modeled start year
                #    to make sure we have all the hours, minutes (e.g., 23:59:59) filled in in step (4)
                if temp.data.index[0].year == year_start:
                    add_index = temp.data.index[0] - pd.offsets.YearEnd()
                    temp.data.loc[add_index] = temp.data.loc[temp.data.index[0]]
                    # TODO (8/4): This section is a band—aid so that we don't accidentally drop weather year-indexed data before the modeled years
                    #             We need to address issue #223 to fix this more completely
                    temp.data.sort_index(inplace=True)
                    temp.data = ts.Timeseries.resample_up(
                        temp.data,
                        field_settings["default_freq"],
                        field_settings["up_method"],
                    )
                    temp.data = temp.data[temp.data.index.year >= year_start]
                    ############################################################################################
                elif temp.data.index[0].year > year_start:
                    extrapolated.add(attr)
                    add_index = pd.to_datetime(f"1/1/{year_start}", infer_datetime_format=True)
                    temp.data.loc[add_index] = temp.data.loc[temp.data.index[0]]
                    temp.data.sort_index(inplace=True)

                # 3. Create a temporary timestamp for the year **after** the modeled end year
                #    to make sure we have all the hours, minutes (e.g., 23:59:59) filled in in step (4)
                # TODO 2023-07-17: I think there is an arg for pd.date_range() that tells it whether to be inclusive of the right end of the horizon
                if temp.data.index[-1].year == year_end:
                    add_index = temp.data.index[-1] + pd.offsets.YearBegin()
                    temp.data.loc[add_index] = temp.data.loc[temp.data.index[-1]]
                elif temp.data.index[-1].year < year_end:
                    extrapolated.add(attr)
                    add_index = pd.to_datetime(f"1/1/{int(year_end) + 1}", infer_datetime_format=True)
                    temp.data.loc[add_index] = temp.data.loc[temp.data.index[-1]]

                # 4. Resample to fill in any data (particularly at end of timeseries) and drop temporary timestamp from (3)
                temp.data.sort_index(inplace=True)
                temp.data = ts.Timeseries.resample_up(
                    temp.data,
                    field_settings["default_freq"],
                    field_settings["up_method"],
                )
                # drop excess data
                temp.data = temp.data[(temp.data.index.year <= year_end) & (temp.data.index.year >= year_start)]

        # If the `extrapolated` set of attrs is not empty, return them to `System` for warning
        if extrapolated:
            return extrapolated

    @classmethod
    def map_units(cls, row):
        """Return original units for named attribute."""
        try:
            unit = cls.__fields__[row["attribute"]].field_info.extra["units"]
        except KeyError:
            # Catch exception if unit is not defined for an attribute
            logger.debug(
                f"Unit for {row['attribute']} ({row['timestamp']}) not defined in code (see documentation for more details on units). Assuming dimensionless."
            )
            unit = 1 * ureg.dimensionless
        return unit

    @classmethod
    def parse_user_unit(cls, row):
        """Convert user-defined unit to pint `Unit` instance."""
        try:
            unit = ureg.Quantity(row["unit"])
        except pint.UndefinedUnitError as e:
            logger.warning(
                f"Unit for {row['attribute']} ({row['timestamp']}) could not be parsed (see documentation for more details on units): {e}"
            )
            unit = ureg.Quantity("1 dimensionless")
        return unit

    @classmethod
    def convert_units(cls, row):
        """Convert units from user-defined `unit` to `defined_unit`."""
        if row["unit"].units == ureg("dimensionless"):
            return 1
        else:
            return (row["unit"] * row["defined_unit"]).magnitude

    def extract_attribute_from_components(self, component_dict: Union[None, Dict[str, "Component"]], attribute: str):
        """Takes a dictionary with Components as the values and returns the dictionary with the same keys, but with
        the desired attribute extracted from the Components.

        Args:
            component_dict: dictionary of Components
            attribute: attribute to extract from each Component

        Returns:
            component_attributes: dictionary containing the extracted attributes
        """
        if component_dict is None:
            return None
        else:
            component_attributes = map_dict(dict_=component_dict, func=lambda component: getattr(component, attribute))

            return component_attributes

    def sum_attribute_from_components(
        self,
        component_dict: Union[None, Dict[str, "Component"]],
        attribute: str,
        timeseries: bool = False,
        skip_none: bool = False,
    ):
        """Extracts an attribute from all Components in `component_dict` and sums them. If the attributes are
        `Timeseries` objects, use `timeseries=True`. The `skip_none` argument will skip any Components for which the
        desired attribute has no value.

        Args:
            component_dict: dictionary containing the Components (e.g. `System.resources`)
            attribute: the desired attribute to sum
            timeseries: whether or not the attribute is a timeseries
            skip_none: whether or not to skip Components for which the attribute is None

        Returns:
            aggregate: the aggregated value across all Components
        """

        if component_dict is None:
            return None
        else:
            component_attributes = self.extract_attribute_from_components(
                component_dict=component_dict, attribute=attribute
            )
            if skip_none:
                component_attributes = {key: value for key, value in component_attributes.items() if value is not None}
                if len(component_attributes) == 0:
                    return None

            if timeseries:
                component_attributes = map_dict(dict_=component_attributes, func=lambda x: x.data)
                aggregate = ts.NumericTimeseries(name=attribute, data=sum(component_attributes.values()))
            else:
                aggregate = sum(component_attributes.values())

            return aggregate

    def sum_timeseries_attributes(
        self, attributes: List[str], name: str, skip_none: bool = False
    ) -> Union[None, ts.NumericTimeseries]:
        """Sums multiple attributes of the instance which are `Timeseries` objects.

        Args:
            attributes: list of attributes to sum
            name: name for the resulting `Timeseries`
            skip_none: whether or not to skip attributes if they are `None`

        Returns:
            result: a `Timeseries` that is the sum of the input attributes
        """
        timeseries_attributes = [getattr(self, attribute) for attribute in attributes]

        if skip_none:
            timeseries_attributes = filter_not_none(timeseries_attributes)
            if len(timeseries_attributes) == 0:
                return None

        result = ts.NumericTimeseries(name=name, data=sum([ts_.data for ts_ in timeseries_attributes]))

        return result
