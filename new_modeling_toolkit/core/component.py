from __future__ import annotations

import copy
import json
import os
import pathlib
import textwrap
import types
from collections import OrderedDict
from typing import Annotated
from typing import Any
from typing import ClassVar
from typing import Dict
from typing import List
from typing import Optional
from typing import TYPE_CHECKING
from typing import TypeVar
from typing import Union

import pandas as pd
import pint
import pydantic
import pyomo.environ as pyo
from loguru import logger
from pydantic import ConfigDict
from pydantic import Field
from tqdm.notebook import tqdm

from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.from_csv_mix_in import FromCSVMixIn
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.core.temporal.timeseries import TimeseriesType
from new_modeling_toolkit.core.utils.core_utils import filter_not_none
from new_modeling_toolkit.core.utils.core_utils import map_dict
from new_modeling_toolkit.core.utils.pandas_utils import compare_dataframes
from new_modeling_toolkit.core.utils.pyomo_utils import convert_pyomo_object_to_dataframe
from new_modeling_toolkit.core.utils.xlwings import ExcelApiCalls

if TYPE_CHECKING:
    from new_modeling_toolkit.core.model import ModelTemplate

# Create an alias Component class type annotation (see return value in `from_csv` method)
C = TypeVar("Component")
# TODO: This doesn't seem to work as-expected for return type annotation


class LastUpdatedOrderedDict(OrderedDict):
    "Store items in the order the keys were last added"

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)


class VarContainer(FromCSVMixIn, arbitrary_types_allowed=True, populate_by_name=True):
    min: None | float | ts.NumericTimeseries = pydantic.Field(default=None, union_mode="left_to_right")
    max: None | float | ts.NumericTimeseries = pydantic.Field(default=None, union_mode="left_to_right")
    value: None | float | ts.NumericTimeseries = pydantic.Field(default=None, union_mode="left_to_right")

    @classmethod
    def default_factory(cls, name: Union[str, tuple[str]]):
        def factory(*args, **kwargs):
            return cls(name=name, *args, **kwargs)

        return factory

    @classmethod
    def _get_flexible_timeseries_attribute_names(cls) -> list[str]:
        flexible_timeseries_attributes = []
        for attr_name, field_info in cls.model_fields.items():
            attr_field_types = cls.get_field_type(field_info=field_info)
            if cls.field_is_timeseries(field_info=field_info) and (
                len(set(attr_field_types) - set(ts.Timeseries.__subclasses__() + [ts.Timeseries, type(None)])) > 0
            ):
                flexible_timeseries_attributes.append(attr_name)

        return flexible_timeseries_attributes

    @classmethod
    def _parse_flexible_timeseries_attributes(
        cls, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: list[str]
    ):
        flexible_ts_attribute_names = cls._get_flexible_timeseries_attribute_names()

        flexible_ts_attrs = {}
        for attr in flexible_ts_attribute_names:
            input_df_slice = input_df.loc[input_df["attribute"] == attr].set_index(["timestamp"])
            if len(input_df_slice) > 0:
                input_df_slice = cls._filter_highest_scenario(
                    filename=filename, input_df=input_df_slice, scenarios=scenarios
                )
                if len(input_df_slice) == 1:
                    flexible_ts_attrs[attr] = input_df_slice.squeeze()
                else:
                    flexible_ts_attrs[attr] = {"name": attr, "data": input_df_slice.squeeze(axis=1).rename(attr)}

        return flexible_ts_attrs

    @classmethod
    def _parse_attributes(cls, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: list[str]) -> dict[str, Any]:
        flexible_ts_attrs = cls._parse_flexible_timeseries_attributes(
            filename=filename, input_df=input_df, scenarios=scenarios
        )

        attrs = {
            **flexible_ts_attrs,
            **super(VarContainer, cls)._parse_attributes(
                filename=filename,
                input_df=input_df.loc[~input_df["attribute"].isin(flexible_ts_attrs.keys())],
                scenarios=scenarios,
            ),
        }

        return attrs


class ExpressionContainer(VarContainer):
    """"""


class Component(FromCSVMixIn):
    __TABLE_COUNTER: ClassVar[int] = 1
    model_config = ConfigDict(protected_namespaces=())

    attr_path: Optional[Union[str, pathlib.Path]] = Field(
        pathlib.Path.cwd(), description="the path to the attributes file"
    )
    include: Annotated[bool, Metadata(category=FieldCategory.BUILD)] = Field(
        True, description="Include component in system."
    )
    class_name: str | None = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._formulation_block = None

        # Save class name to be saved in json files after run, to be read in production simulation mode
        if not self.class_name:
            self.class_name = self.__class__.__name__

    def __repr__(self):
        """WORKAROUND because default pydantic model __repr__ causing trouble with error handling."""

        return f"{self.__class__.__name__}: {str(self.name)}"

    # TODO: Use method chaining to make this cleaner: https://stackoverflow.com/questions/49112201/python-class-methods-chaining

    def _expose_linkage_component(self, linkage_name: str, linkage_key: str) -> "Component":
        """
        Return the linkage component

        Args:
            linkage_name: str of linkage name defined on System. Ex: "pollutants"
            linkage_key: str. Name of specific linkage key in linkage dictionary. Ex: "Connecticut_Residential Single Family Space Heating"

        Returns: linked component

        """
        linkage = getattr(self, linkage_name)[linkage_key].instance_to
        # handle the case where the linkage_to returns the self object, and you actually want linkage_from
        if linkage == self:
            linkage = getattr(self, linkage_name)[linkage_key].instance_from
        return linkage

    def _return_linked_component(self, linkage_name: str) -> "Component":
        """
        For a 1:1 linkage, return the linked component.

        Args:
            linkage_name: str of linkage name. Ex: "sector"

        Returns: linked component for 1:1 linkage

        """
        if getattr(self, linkage_name) is None or len(getattr(self, linkage_name)) == 0:
            linkage = None
        elif len(getattr(self, linkage_name)) > 1:
            raise ValueError(f"Expecting only one linkage, multiple are present for {linkage_name}")
        else:
            linkage_key = list(getattr(self, linkage_name).keys())[0]
            linkage = self._expose_linkage_component(linkage_name, linkage_key)

        return linkage

    def _return_linkage_list(self, linkage_name: str) -> list | None:
        """
        Loop through a dictionary of linkages and return a list of the linked component only.

        Args:
            linkage_name: str of name of the linkage on the component. Ex: "pollutants"

        Returns: list of components

        """
        if getattr(self, linkage_name) is None or len(getattr(self, linkage_name)) == 0:
            return None
        else:
            return [
                self._expose_linkage_component(linkage_name, linkage_key) for linkage_key in getattr(self, linkage_name)
            ]

    def _return_linkage_dict(self, linkage_name: str) -> dict | None:
        """
        Loop through a dictionary of linkages and return a dict of the linked component only.

        Args:
            linkage_name: str of name of the linkage on the component. Ex: "pollutants"

        Returns: dictionary of components. Key is the name of the linkage, value is the linked `to` or `from` component {str: component}

        """
        if getattr(self, linkage_name) is None or len(getattr(self, linkage_name)) == 0:
            return None
        else:
            return {
                linkage_key: self._expose_linkage_component(linkage_name, linkage_key)
                for linkage_key in getattr(self, linkage_name)
            }

    @property
    def results_reporting_category(self):
        return f"{self.__class__.__name__}"

    @property
    def results_reporting_folder(self):
        return self.results_reporting_category

    @classmethod
    def model_fields_by_category(cls) -> dict:
        """Create a nested dictionary of model fields by category for  UI (if specified in `Metadata` annotation)."""
        fields = {}
        # Put linkages in their own category
        fields["Linkages"] = [
            name for name in cls._linkage_attributes() if not cls.get_metadata(field_name=name).default_exclude
        ]
        # Append rest of the attributes
        for name, field in cls.model_fields.items():
            excluded_fields = (
                name in ["attr_path", "name"]
                or name.startswith("opt_")
                or name in fields["Linkages"]
                or cls.get_field_type(field_info=field) is None
                or cls.get_metadata(field_name=name).default_exclude
            )
            if excluded_fields:
                continue

            metadata = cls.get_metadata(field_name=name)
            if metadata.category is not None:
                category = metadata.category.value
            else:
                category = None

            if category not in fields:
                fields[category] = []

            fields[category] += [name]

        # Sort the fields alphabetically
        for category in fields.keys():
            fields[category] = sorted(fields[category])

        return fields

    @classmethod
    def _get_table_headers(
        cls, field_name, year, instance_name_prefix: str = "", include_class_name_prefix: bool = False
    ) -> tuple | list[tuple]:
        """Convert metadata for all component fields into a list of tuples.

        Used by `Component.to_excel()` to create header rows, in this order:
        - Field category
        - Field attribute (i.e., the name in the code)
        - Defined units
        - Lower bound warning
        - Upper bound warning
        - Field title (i.e., nicely formatted name), if timeseries
        - The only actual Excel `Table` header row: Field title (if scalar) **OR** year + short title (if timeseries)
            - Excel `Table` headers must be unique, which is why for timeseries fields, I prepend a year
        """
        # Get metadata annotation
        metadata = cls.get_metadata(field_name)

        # This prefix is used for the "field" wrote (the name of the attribute), and is the instance name + the class name
        attr_prefix = (f"{instance_name_prefix}") + (f".{cls.__name__}." if include_class_name_prefix else "")

        # Get linkage fields, which will all be put at the beginning of the table
        linkage_attribute_names = {
            name: attr
            for name, attr in cls.model_fields.items()
            if "linkage" in cls.get_field_type(field_info=attr)[-1].__module__
            and cls.get_field_type(field_info=attr)[-1].__name__ not in ["DeliverabilityStatus"]
        }
        # TODO 2024-08-02: This won't work for linkages not written in `linkage.py` or `three_way_linkage.py`, so need to generalize

        # TODO 2024-04-30: For now, using this as a band-aid
        # TODO 2024-05-17: Some of this if/else overlaps with `model_fields_by_category`
        # Get category, attribute name & units from metadata
        modified_field_name = field_name
        if instance_name_prefix != "":
            category = f"{instance_name_prefix} Parameters"
        elif field_name in linkage_attribute_names:
            category = "Linkages"
            linkage_order = f".{metadata.linkage_order}"
            modified_field_name = (
                f"{cls.get_field_type(field_info=cls.model_fields[field_name])[-1].__name__}{linkage_order}"
            )
        elif metadata.category is not None:
            category = metadata.category.value
        else:
            category = None

        # Get units (either a pint unit or a string, e.g., for bools, %)
        if isinstance(metadata.units, pint.Unit) or isinstance(metadata.units, pint.Quantity):
            units = f"{metadata.units:e3}"
        else:
            units = metadata.units

        # Get timeseries short title with years
        header_with_years = (
            field_name in cls.get_timeseries_attribute_names(include_aliases=True)
            and metadata.show_year_headers
            and (
                cls.model_fields[field_name].json_schema_extra["default_freq"] == "YS"
                if cls.model_fields[field_name].json_schema_extra is not None
                else False
            )
        )
        modified_instance_name_prefix = f"{instance_name_prefix} " if instance_name_prefix != "" else ""
        if header_with_years:
            ts_title = (
                modified_instance_name_prefix + modified_field_name.replace("_", " ").title()
                if cls.model_fields[field_name].title is None
                else cls.model_fields[field_name].title
            )
            return (
                category,
                f"{attr_prefix}{modified_field_name}",
                units,
                *metadata.warning_bounds,
                ts_title,
                f"{year} "
                + modified_instance_name_prefix
                + f"{metadata.excel_short_title if metadata.excel_short_title != '' else ts_title}",
            )
        else:
            ts_title = "-"
            title = (
                modified_instance_name_prefix + field_name.replace("_", " ").title()
                if cls.model_fields[field_name].title is None
                else cls.model_fields[field_name].title
            )
            return (
                category,
                f"{attr_prefix}{modified_field_name}",
                units,
                *metadata.warning_bounds,
                ts_title,
                title,
            )

    @classmethod
    def get_metadata(cls, field_name: str):
        """Get field's `Metadata()` from annotation (or return an default `Metadata()` instance."""
        if not cls.model_fields[field_name].metadata or not any(
            isinstance(metadata, Metadata) for metadata in cls.model_fields[field_name].metadata
        ):
            metadata = Metadata()
        else:
            metadata = [mtd for mtd in cls.model_fields[field_name].metadata if isinstance(mtd, Metadata)][0]
        return metadata

    @classmethod
    def to_excel(
        cls,
        *,
        anchor_range: "Range",
        excel_api: ExcelApiCalls,
        modeled_years_range: list[int] = range(2020, 2051),
        modeled_years_visible: list | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        num_rows: int = 20,
        add_doc_hyperlinks: bool = True,
        linkages_to_write: list["LinkageFieldsToWrite"] | None = None,
        table_name: str,
    ):
        """Create a new user inputs tab in an Excel UI, using `E3 Model Template.xlsm`."""
        # Initialize empty lists
        if linkages_to_write is None:
            linkages_to_write = []

        if modeled_years_visible is None:
            modeled_years_visible = modeled_years_range

        if include is None:
            include = cls.model_fields.keys()

        # Always include `instance_from`, `instance_to`, etc. for linkages
        include = list(set(include).union(set(k for k in cls.model_fields.keys() if k.startswith("instance_"))))

        if exclude is not None:
            include = list(set(include) - set(exclude))

        # The attribute name row & units rows should be in "Explanatory Text" format
        rng = anchor_range.sheet.range(
            f"{anchor_range.offset(row_offset=-6).row}:{anchor_range.offset(row_offset=-3).row}"
        )
        excel_api.set_cell_style(rng, excel_api.styles(rng.sheet.book, "Explanatory Text"))

        column_offset = 0

        # 2. Create `name` column
        rng = anchor_range.offset(column_offset=column_offset)
        rng.offset(row_offset=-6).resize(row_size=5).options(transpose=True).value = [
            "",
            "name",
            "",
            "",
            "",
            "",
            "Name",
        ]
        rng = anchor_range.resize(row_size=num_rows)
        column_offset += 1

        # 3. Create `scenarios` column
        rng = anchor_range.offset(column_offset=column_offset)
        rng.offset(row_offset=-6).resize(row_size=5).options(transpose=True).value = [
            "",
            "scenarios",
            "Units",
            "Reasonable Lower Bound",
            "Reasonable Upper Bound",
            "",
            "Data Scenario Tag",
        ]
        rng = rng.resize(row_size=num_rows)
        column_offset += 1

        # 5. Create field columns
        logger.debug("Getting field headers...")
        df = (
            pd.MultiIndex.from_tuples(
                [
                    cls._get_table_headers(field_name, year)
                    for field_category, fields in cls.model_fields_by_category().items()
                    for field_name in fields
                    if field_name in include
                    for year in modeled_years_range
                ]
            )
            .unique()
            .to_frame(index=False)
            .fillna(value="-")
        )
        # Optionally append linkage attributes
        df = cls._append_linkage_fields_to_table(df, include, linkages_to_write, modeled_years_range)

        # Various neatness
        df[0].loc[df[0].duplicated()] = ""
        df[3].loc[df[3] == "-"] = ""
        df[4].loc[df[4] == "-"] = ""
        df[5].loc[(df[5].duplicated()) & (df[5] != "-")] = ""

        # Format headers
        rng = anchor_range.offset(row_offset=-6, column_offset=column_offset).resize(column_size=df.shape[0])
        rng.options(chunksize=250, index=False, header=False).value = df.T

        excel_api.set_cell_style(rng, excel_api.styles(rng.sheet.book, "Table Header"))
        excel_api.set_cell_style(
            anchor_range.offset(row_offset=-1, column_offset=column_offset).resize(column_size=df.shape[0]),
            excel_api.styles(rng.sheet.book, "Table Sub-Header"),
        )

        # 6. Add docs hyperlinks
        if add_doc_hyperlinks:
            logger.debug("Adding links to docs...")
            for i, (_, attr, ts_title, unit, lb, ub, title) in df.iterrows():
                if getattr(cls, "_DOCS_URL", None) is not None:
                    if anchor_range.offset(row_offset=-1, column_offset=column_offset + i).value is not None:
                        if anchor_range.offset(row_offset=-1, column_offset=column_offset + i).value == "-":
                            rng = anchor_range.offset(column_offset=column_offset + i)
                        else:
                            rng = anchor_range.offset(row_offset=-1, column_offset=column_offset + i)
                        rng.add_hyperlink(f"{cls._DOCS_URL}{attr}", rng.value)

        column_offset += df.shape[0]

        # 7. Add a `Notes` column
        rng = anchor_range.offset(column_offset=column_offset)
        rng.offset(row_offset=-6).resize(row_size=5).options(transpose=True).value = [
            "",
            "",
            "",
            "",
            "",
            "",
            "Notes",
        ]
        column_offset += 1

        # 8. Make entire field table a table
        rng = anchor_range.resize(column_size=column_offset, row_size=num_rows)

        # 9. Hide modeled years that are not in `modeled_years_visible`
        logger.debug("Grouping columns...")
        modeled_years_to_hide = list(set(modeled_years_range) - set(modeled_years_visible))
        for col in rng.columns:
            header_to_check = str(col[0].value)
            if any(header_to_check.startswith(f"{year} ") for year in modeled_years_to_hide):
                excel_api.group(col, by="column")

        # Table name format is always _[kit sub-module name].[class name].[counter]
        logger.debug("Converting range to table...")
        table_name = f"{table_name}.__{cls.__TABLE_COUNTER}"
        cls.__TABLE_COUNTER += 1
        rng.sheet.tables.add(rng, name=table_name, table_style_name="TableStyleExtraLight9")

        # Excel tables work better if they're placed side-by-side
        return (0, column_offset + 2, table_name)

    @classmethod
    def _append_linkage_fields_to_table(cls, df, include, linkages_to_write, modeled_years_range):
        # Match list of linkages we want to include in table with linkage classes (so that we can introspect the fields)e
        if cls.model_fields_by_category()["Linkages"]:
            linkage_fields = [
                (cls.model_fields[name], l)
                for l in linkages_to_write
                for name in cls.model_fields_by_category()["Linkages"]
                if name in include and l.name == cls.get_field_type(field_info=cls.model_fields[name])[-1].__name__
            ]
        else:
            # For some reason if cls.model_fields_by_category()["Linkages"] is empty, the above clause doesn't quite work
            linkage_fields = []

        for linkage_field, linkage_to_write in linkage_fields:
            linkage_class = cls.get_field_type(field_info=linkage_field)[-1]
            df = df.T
            linkage_column = (
                df.pop(df.loc[:, df.iloc[1, :].str.contains(linkage_class.__name__)].columns[0]).to_frame().T
            )
            df = df.T
            # Pop out the column with the linkage attribute (e.g., ReliabilityConstribution.to)
            for instance in linkage_to_write.instances:
                # Customize the linkage column for this specific instance of the linkage
                linkage_instance_column = linkage_column.copy()
                linkage_instance_column.loc[:, 0] = "-"
                linkage_instance_column.iloc[:, 1] = f"{instance}.{linkage_instance_column.iloc[:, 1].values[0]}"
                linkage_instance_column.iloc[:, -1] = f"{instance}"
                dfs_to_concat = [
                    df,
                    linkage_instance_column,
                ]
                # Append any linkage attributes
                columns = [
                    linkage_class._get_table_headers(
                        field_name, year, instance_name_prefix=instance, include_class_name_prefix=True
                    )
                    for field_category, fields in linkage_class.model_fields_by_category().items()
                    for field_name in fields
                    if "instance_" not in field_name and field_name != "include"
                    for year in modeled_years_range
                ]
                if columns:
                    dfs_to_concat.append(
                        pd.MultiIndex.from_tuples(columns).unique().to_frame(index=False).fillna(value="-")
                    )

                # Update df with new columns
                df = pd.concat(dfs_to_concat, ignore_index=True)
        return df

    # CURRENTLY UNUSED!!
    @classmethod
    def _get_pyomo_container_attributes(cls) -> dict[str, Union[VarContainer, ExpressionContainer]]:
        """Returns a list of attributes of the Component that are of type VarContainer or ExpressionContainer.

        Returns:
            container_attributes: a list of attribute names of type VarContainer or ExpressionContainer
        """
        container_attributes = {}
        for attr_name, field_info in cls.model_fields.items():
            attr_field_types = cls.get_field_type(field_info=field_info)
            if len({VarContainer, ExpressionContainer}.intersection(set(attr_field_types))) > 0:
                assert (
                    len(attr_field_types) == 1
                ), "Union types using VarContainer or ExpressionContainer are not supported"
                container_attributes[attr_name] = attr_field_types[0]

        return container_attributes

    # CURRENTLY UNUSED!!
    @classmethod
    def _parse_pyomo_container_attributes(
        cls, *, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: list
    ) -> dict[str, Any]:
        """Parses input data used to initialize attributes of type VarContainer or ExpressionContainer when creating a
        Component from a CSV.

        Args:
            filename: path to the input CSV file
            input_df: DataFrame representation of the input CSV file
            scenarios: list of scenarios to filter

        Returns:
            container_attrs: dictionary of parsed container attributes
        """
        container_attribute_names_and_classes = cls._get_pyomo_container_attributes()

        container_attrs = {}
        for attr_name, container_class in container_attribute_names_and_classes.items():
            input_df_container_subset = input_df.loc[
                input_df.loc[:, "attribute"].isin([attr_name, f"{attr_name}_min", f"{attr_name}_max"]), :
            ].copy()
            input_df_container_subset.loc[:, "attribute"] = (
                input_df_container_subset.loc[:, "attribute"]
                .replace(f"{attr_name}_max", "max")
                .replace(f"{attr_name}_min", "min")
                .replace(attr_name, "value")
            )

            container_attrs[attr_name] = container_class.from_dataframe(
                input_df=input_df_container_subset, attr_path=filename, scenarios=scenarios, data={}, name=attr_name
            ).popitem()[1]

        return container_attrs

    @pydantic.model_validator(mode="before")
    def annual_input_validator(cls, values):
        """
        Checks that all timeseries data with down_method == 'annual' only has one input per year
        and sets the datetime index to be January 1st at midnight
        """
        if not isinstance(values, dict):
            return values

        aliases = {field_settings.alias: attr for attr, field_settings in cls.model_fields.items()}
        aliases.update({attr: attr for attr, field_settings in cls.model_fields.items()})

        for value in values:
            # In this situation, all the ts attributes are still the base ts (and not a subclass) when first initialized
            if (
                isinstance(values[value], ts.Timeseries)
                and cls.model_fields[aliases[value]].json_schema_extra["down_method"] == "annual"
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

    @pydantic.model_validator(mode="after")
    def warn_value_bounds(self):
        """Raise a warning (instead of an error) for values that are out of a "reasonable" value range but not explicitly "wrong"."""
        for field in self.model_fields_set:
            metadata = self.get_metadata(field_name=field)
            attr = getattr(self, field)
            lb, ub = metadata.warning_bounds

            # Don't really know how else to implement this switch ¯\_(ツ)_/¯
            if lb is None:
                lb = float("-inf")
            if ub is None:
                ub = float("inf")

            if isinstance(attr, ts.NumericTimeseries):
                out_of_bounds = attr.data.loc[(attr.data < lb) | (attr.data > ub)]
                if not out_of_bounds.empty:
                    logger.warning(
                        f"For {self.name}.{field}: values may be unreasonable: reasonable bounds are {lb, ub}:\n{out_of_bounds.to_string()}"
                    )
            if isinstance(attr, float) or isinstance(attr, int):
                if attr < lb or attr > ub:
                    logger.warning(
                        f"For {self.name}.{field}: {getattr(self, field):.4f} may be unreasonable: reasonable bounds are {lb, ub}"
                    )
        return self

    @classmethod
    def _parse_attributes(cls, filename: pathlib.Path, input_df: pd.DataFrame, scenarios: list[str]):
        attrs = super(Component, cls)._parse_attributes(filename=filename, input_df=input_df, scenarios=scenarios)
        attrs.update(**cls._parse_pyomo_container_attributes(filename=filename, input_df=input_df, scenarios=scenarios))

        return attrs

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
    def dfs_to_csv(
        cls,
        *,
        instances: pd.DataFrame,
        wb: "Book",
        dir_str: "DirStructure",
        compare_files: bool = True,
        dry_run: bool = False,
        save_path_override: pathlib.Path | None = None,
    ) -> None:
        """Save DataFrame into (separate) component CSV files."""
        # Remove `include` attribute (if it exists)
        instances = instances.loc[~(instances["attribute"] == "include"), :]

        instances = instances.groupby(instances["name"])
        progress_bar = tqdm(total=len(instances), display=False, smoothing=None)

        if save_path_override is not None:
            save_path = save_path_override
        else:
            save_path = dir_str.data_interim_dir / cls.SAVE_PATH
        save_path.mkdir(parents=True, exist_ok=True)

        for name, df in instances:
            progress_bar.update()
            excel_progress_bar = str(progress_bar)
            if (
                (save_path / f"{name}.csv").exists()
                and os.stat(save_path / f"{name}.csv").st_size > 0
                and compare_files
            ):
                try:
                    previous_df = pd.read_csv(
                        save_path / f"{name}.csv", parse_dates=["timestamp"], infer_datetime_format=True
                    )
                    comparison = compare_dataframes(
                        previous=previous_df,
                        new=df.iloc[:, 1:],
                        indices=["attribute", "timestamp", "scenario"],
                        column_to_compare="value",
                    )

                    if not comparison.empty:
                        comparison = textwrap.indent(comparison.to_string(), " > ")
                        logger.debug(f'│ ├─ Differences in {save_path / f"{name}.csv"}:\n{comparison}')
                except:
                    logger.error(f"Could not compare CSV files: {save_path / name}.csv")

            if not dry_run:
                df.iloc[:, 1:].to_csv(save_path / f"{name}.csv", index=False)
                wb.app.status_bar = f"Writing {cls.__name__}: {excel_progress_bar} {name}"

        progress_bar.close()

    def revalidate(self):
        """Abstract method to run additional validations after `Linkage.announce_linkage_to_instances`."""

    @property
    def timeseries_attrs(self):
        # find all timeseries attributes in instance
        return [
            attr
            for attr, field_settings in self.model_fields.items()
            if self.field_is_timeseries(field_info=field_settings)
        ]

    @classmethod
    def _linkage_attributes(cls) -> list[str]:
        from new_modeling_toolkit.core.linkage import Linkage

        linkage_attrs = []
        for field_name, field_info in cls.model_fields.items():
            if type(field_info.annotation) == types.GenericAlias and any(
                t in Linkage.get_subclasses() or t == Linkage for t in field_info.annotation.__args__
            ):
                linkage_attrs.append(field_name)

        return linkage_attrs

    @property
    def linkage_attributes(self) -> list[str]:
        return self._linkage_attributes()

    @classmethod
    def _three_way_linkage_attributes(cls) -> list[str]:
        from new_modeling_toolkit.core.three_way_linkage import ThreeWayLinkage

        linkage_attrs = []
        for field_name, field_info in cls.model_fields.items():
            if type(field_info.annotation) == types.GenericAlias and any(
                t in ThreeWayLinkage.get_subclasses() or t == ThreeWayLinkage for t in field_info.annotation.__args__
            ):
                linkage_attrs.append(field_name)

        return linkage_attrs

    @property
    def three_way_linkage_attributes(self) -> list[str]:
        return self._three_way_linkage_attributes()

    @property
    def non_linkage_attributes(self) -> list[str]:
        return list(set(self.model_fields.keys()) - set(self.linkage_attributes + self.three_way_linkage_attributes))

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
        extrapolated = set()
        for attr in self.timeseries_attrs:
            # Don't try resampling empty ts data
            temp = getattr(self, attr)
            if temp is None:
                continue

            # Get the resampling settings from the pydantic.Field definition
            field_settings = self.model_fields[attr].json_schema_extra

            # There are now TWO ways to identify toggle timeseries types (hard-coded or via an attribute called `[attr]__type`)
            is_weather_year = ("weather_year" in field_settings and field_settings["weather_year"]) or (
                getattr(self, f"{attr}__type", None) == TimeseriesType.WEATHER_YEAR
            )
            temp.weather_year = is_weather_year  # TODO: This is a bandaid that sets the Timeseries instance attribute to True if the Field in the System is also True

            # TODO 2023-07-17: These are sort of goofy...
            do_not_resample_weather_year = is_weather_year and not resample_weather_year_attributes
            do_not_resample_modeled_year = not is_weather_year and not resample_non_weather_year_attributes

            # Skip this attribute if we're not resampling
            if do_not_resample_modeled_year or do_not_resample_weather_year:
                continue

            # Get correct index: Resample data by comparing against a "correct index" with the correct default_freq
            # if data is input in weather year, only resample to weather year boundaries
            if is_weather_year:
                year_start = weather_year_start
                year_end = weather_year_end
            else:
                year_start = model_year_start
                year_end = model_year_end
            # Date range from correct start and end, at defined default frequency
            correct_index = pd.date_range(
                str(year_start), str(year_end + 1), freq=field_settings["default_freq"], inclusive="left"
            )

            # Change index year if the data has default year
            if list(temp.data.index.year.unique()) == [
                1900
            ]:  # TODO: This doesn't seem like a good way to check if data is default
                # default data, update index to be resampled
                temp.data.index += pd.DateOffset(years=year_start - 1900)

            # if all timestamp of the correct index are contained in the existing series, just need to resample down
            overlapping_index = correct_index.isin(temp.data.index)
            if (~overlapping_index).sum() == 0:
                new_profile = temp.data.reindex(correct_index)
                new_profile = ts.Timeseries.resample_down(
                    new_profile,
                    field_settings["default_freq"],
                    field_settings["down_method"],
                )
                temp.data = new_profile.fillna(method="ffill")
            # If the indexes do not overlap at all, throw an error
            elif overlapping_index.sum() == 0:
                raise ValueError(
                    f"{self.name}: {temp.name} index does not overlap with target years: {year_start}: {year_end}"
                )
            # Resample up: Check if timeseries type is monthly, month-hour, or season-hour
            # TODO: Is there a smart way for us to infer the timeseries __type to avoid a user input?
            elif (
                getattr(self, f"{attr}__type", None) == TimeseriesType.MONTH_HOUR
                or getattr(self, f"{attr}__type", None) == TimeseriesType.SEASON_HOUR
                or getattr(self, f"{attr}__type", None) == TimeseriesType.MONTHLY
            ):
                # TODO: Figure out a way to use the resample_up method on monthly or seasonal data?
                temp.type = getattr(self, f"{attr}__type")  # Set timeseries attribute type
                if field_settings["up_method"] != "ffill":
                    logger.warning(
                        "Monthly data upsampling is only supported for forward filling, not back filling or interpolation. "
                        "All timestamps within a given month will be assigned the value given in that month."
                    )
                temp.resample_month_or_season_hour_to_hourly(correct_index=correct_index)
            # Resample up: Data is not monthly, month-hour, or season-hour
            else:
                new_profile = temp.data.reindex(correct_index)
                new_profile = ts.Timeseries.resample_up(
                    new_profile,
                    field_settings["up_method"],
                )

                # Because we have `validate_assignment` as True, every time we do ts.data = something,
                # it will get re-validated, including if we're mid-operation (in this case, we've extended the indices
                # but have yet to fill in the NaNs)
                temp.data = new_profile.fillna(method="ffill")

        # TODO: `extrapolated` doesn't seem to be updated anywhere
        # If the `extrapolated` set of attrs is not empty, return them to `System` for warning
        if extrapolated:
            return {self.name: extrapolated}

    @classmethod
    def map_units(cls, row):
        """Return original units for named attribute."""
        try:
            unit = cls.model_fields[row["attribute"]].json_schema_extra["units"]
        except KeyError:
            # Catch exception if unit is not defined for an attribute
            logger.debug(
                f"Unit for {row['attribute']} ({row['timestamp']}) not defined in code (see documentation for more details on units). Assuming dimensionless."
            )
            unit = 1 * units.dimensionless
        return unit

    @classmethod
    def parse_user_unit(cls, row):
        """Convert user-defined unit to pint `Unit` instance."""
        try:
            unit = units.Quantity(row["unit"])
        except pint.UndefinedUnitError as e:
            logger.warning(
                f"Unit for {row['attribute']} ({row['timestamp']}) could not be parsed (see documentation for more details on units): {e}"
            )
            unit = units.Quantity("1 dimensionless")
        return unit

    @classmethod
    def convert_units(cls, row):
        """Convert units from user-defined `unit` to `defined_unit`."""
        if row["unit"].units == units("dimensionless"):
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

    def copy(
        self,
        exclude: Optional[list[str]] = None,
        include_linkages: bool = False,
        update: Optional[dict[str, Any]] = None,
        new_class: Type | None = None,
    ):
        """Copy a component instance (and optionally convert it to a new component class type)."""
        attrs_to_excl = self.linkage_attributes + self.three_way_linkage_attributes
        if exclude is not None:
            attrs_to_excl += exclude
        attrs_to_excl = set(attrs_to_excl)
        data = self.model_dump(exclude=set(attrs_to_excl))
        if update is not None:
            data.update(**update)
        data = copy.deepcopy(data)
        class_to_use = self.__class__ if new_class is None else new_class
        copied = class_to_use.model_validate(data)

        if update is not None and self.formulation_block is not None:
            logger.warning(
                f"Cannot duplicate formulation block for `{self.name}` because fields have been updated in the `copy()` "
                f"method. Setting `formulation_block` to None on the copy."
            )
        elif self._formulation_block is not None:
            copied._formulation_block = self.formulation_block.clone()

        if include_linkages:
            for linkage_attribute in copied._linkage_attributes():
                curr_linkages = getattr(self, linkage_attribute)
                for linkage in curr_linkages.values():
                    # Warning: this creates a shallow copy of the linkage, meaning updating a linkage attribute on
                    # the copied version will change the original attribute, and vice versa.
                    linkage_copy = linkage.copy()
                    if linkage_copy.instance_from is self:
                        linkage_copy.instance_from = copied
                        linkage_copy.name = (copied.name, linkage_copy.instance_to.name)
                    elif linkage_copy.instance_to is self:
                        linkage_copy.instance_to = copied
                        linkage_copy.name = (linkage_copy.instance_from.name, copied.name)
                    else:
                        raise ValueError(
                            f"When copying Component `{self.name} with linkages, the Component was not found in "
                            f"`instance_from` or `instance_to` of the connected Linkage `{linkage.name}`"
                        )
                    linkage_copy.announce_linkage_to_instances()

            for linkage_attribute in self.three_way_linkage_attributes:
                curr_linkages = getattr(self, linkage_attribute)
                for linkage in curr_linkages.values():
                    linkage_copy = linkage.copy()
                    if linkage_copy.instance_1 is self:
                        linkage_copy.instance_1 = copied
                        linkage_copy.name = (copied.name, linkage_copy.instance_2.name, linkage_copy.instance_3.name)
                    elif linkage_copy.instance_2 is self:
                        linkage_copy.instance_2 = copied
                        linkage_copy.name = (linkage_copy.instance_1.name, copied.name, linkage_copy.instance_3.name)
                    elif linkage_copy.instance_3 is self:
                        linkage_copy.instance_3 = copied
                        linkage_copy.name = (linkage_copy.instance_1.name, linkage_copy.instance_2.name, copied.name)
                    else:
                        raise ValueError(
                            f"When copying Component `{self.name} with linkages, the Component was not found in "
                            f"`instance_from` or `instance_to` of the connected Linkage `{linkage.name}`"
                        )
                    linkage_copy.announce_linkage_to_instances()

        return copied

    @property
    def formulation_block(self) -> Optional[pyo.Block]:
        """The Pyomo Block for the Component"""
        return self._formulation_block

    def construct_modeling_block(
        self,
        model: "ModelTemplate",
        construct_investment_rules: bool = True,
        construct_operational_rules: bool = True,
        construct_costs: bool = True,
    ) -> pyo.Block:
        """Constructs a Pyomo Block containing all decision variables, expressions, parameters, constraints, and sets
        required for representing this Component as a member of an energy system.

        This method assumes that the `model` argument is an instance of an E3 `ModelTemplate` which contains some
        universal time-indexing sets that are used in the construction of decision variables, constraints, etc.

        Args:
            model: the Model to which the created Block should be attached
            construct_investment_rules: whether rules related to investment decisions should be constructed
            construct_operational_rules: whether rules related to operational decisions should be constructed
            construct_costs: whether cost terms should be constructed

        Returns:
            self.formulation_block: the constructed Pyomo Block
        """
        self._formulation_block = pyo.Block()
        if construct_investment_rules:
            self.construct_investment_rules(model=model, construct_costs=construct_costs)
        if construct_operational_rules:
            self.construct_operational_rules(model=model, construct_costs=construct_costs)

        return self.formulation_block

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        """Defines the investment-related optimization formulation components (decision variables, expressions,
        constraints, etc.) for the Component. This method should be overridden by subclasses to define additional terms,
        but make sure to call super()._construct_investment_rules (unless you are sure you don't need to).

        Args:
            model: the Model containing the necessary temporal settings information needed to construct the rules
            construct_costs: whether cost-related investment terms should be constructed

        Returns:
            pyomo_components: ordered dictionary containing optimization model terms
        """
        pyomo_components = LastUpdatedOrderedDict()
        if construct_costs:
            pyomo_components.update(
                annual_total_slack_investment_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=0,
                    doc="Annual Total Slack Investment Cost ($)",
                ),
                annual_total_investment_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=0, doc="Annual Total Investment Cost ($)"
                ),
            )

        return pyomo_components

    def construct_investment_rules(self, model: "ModelTemplate", construct_costs: bool):
        """Constructs the investment-related optimization formulation (decision variables, expressions, constraints,
        etc.) for the Component.

        Args:
            model: the Model containing the necessary temporal settings information needed to construct the rules
            construct_costs: whether cost-related investment terms should be constructed
        """
        pyomo_components = self._construct_investment_rules(model=model, construct_costs=construct_costs)
        for name, component in pyomo_components.items():
            setattr(self._formulation_block, name, component)

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        """Defines the operations-related optimization formulation components (decision variables, expressions,
        constraints, etc.) for the Component. This method should be overridden by subclasses to define additional terms,
        but make sure to call super()._construct_investment_rules (unless you are sure you don't need to).

        Args:
            model: the Model containing the necessary temporal settings information needed to construct the rules
            construct_costs: whether cost-related operations terms should be constructed

        Returns:
            pyomo_components: ordered dictionary containing optimization model terms
        """
        pyomo_components = LastUpdatedOrderedDict()
        if construct_costs:
            pyomo_components.update(
                annual_total_slack_operational_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=0, doc="Annual Total Slack Operational Cost ($)"
                ),
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=0, doc="Annual Total Operational Cost ($)"
                ),
            )

        return pyomo_components

    def construct_operational_rules(self, model: "ModelTemplate", construct_costs: bool):
        """Constructs the operations-related optimization formulation (decision variables, expressions, constraints,
        etc.) for the Component.

        Args:
            model: the Model containing the necessary temporal settings information needed to construct the rules
            construct_costs: whether cost-related operational terms should be constructed
        """
        pyomo_components = self._construct_operational_rules(model=model, construct_costs=construct_costs)
        for name, component in pyomo_components.items():
            setattr(self._formulation_block, name, component)

    def _construct_output_expressions(self, construct_costs: bool):
        """Constructs Pyomo expressions used for results reporting that are not required for model construction/solving,
         or cannot be constructed before the model is solved. For example, results reporting expressions that rely on
         dual values of constraints can only be constructed after the model is solved.

        Args:
            construct_costs: whether to construct cost-related terms
        """

    def _order_annual_results_columns(self, column_order: list, annual_results: pd.DataFrame) -> list:
        """The desired order of columns in the component's annual results summary

        Args:
            column_order: hard-coded order of annual result summary columns
        """
        if hasattr(self, "annual_results_column_order"):
            ordered_columns = []
            field_dict = self.model_fields | self.model_computed_fields
            for column in column_order:
                # Check if column refers to a pyomo component
                if (
                    hasattr(self.formulation_block, column)
                    and getattr(self.formulation_block, column).doc in annual_results.columns
                ):
                    ordered_columns.append(getattr(self.formulation_block, column).doc)
                # Check if column refers to an attribute
                elif column in field_dict.keys() and field_dict[column].title in annual_results.columns:
                    ordered_columns.append(field_dict[column].title)
            return ordered_columns
        else:
            return annual_results.columns

    def _build_year_based_annual_index(self) -> list:
        """Helper method to get the model year index of a component with a build_year (Assets)
        or earliest_build_year (AssetGroups)"""
        # If the Component does not have a build year, repeat the value for all modeled years
        if getattr(self, "build_year", None) is None:
            # If the Component is a group, it could have an earliest_build_year. Check for that
            if getattr(self, "earliest_build_year", None) is None:
                index = list(self.formulation_block.model().MODELED_YEARS)
            elif getattr(self, "earliest_build_year") > max(self.formulation_block.model().MODELED_YEARS):
                index = [max(self.formulation_block.model().MODELED_YEARS)]
            else:
                index = [
                    year
                    for year in self.formulation_block.model().MODELED_YEARS
                    if year >= getattr(self, "earliest_build_year")
                ]
        # If the build year is greater than the max modeled year, assign the value to the max modeled year
        elif getattr(self, "build_year") > max(self.formulation_block.model().MODELED_YEARS):
            index = [max(self.formulation_block.model().MODELED_YEARS)]
        # Otherwise, find the modeled year that is closest to but later than the build year
        else:
            index = [
                year for year in self.formulation_block.model().MODELED_YEARS if year >= getattr(self, "build_year")
            ]
        return index

    @staticmethod
    def _pivot_result_df(data_frame: pd.DataFrame, index: list) -> pd.DataFrame:
        """Helper method to reformat a data frame holding Pyomo component data"""
        pivoted_df = data_frame.reset_index().pivot(
            index=index, columns=[x for x in data_frame.index.names if x not in index]
        )

        return pivoted_df

    def export_formulation_block_raw_results(self, output_dir: pathlib.Path):
        """
        Save raw pyomo components to csv.

        Args:
            output_dir: raw results directory

        """
        output_dir = output_dir.joinpath(self.results_reporting_folder, self.name)
        output_dir.mkdir(exist_ok=True, parents=True)
        for component_type in [
            pyo.Set,
            pyo.Var,
            pyo.Expression,
            pyo.Constraint,
            pyo.Param,
        ]:
            components_to_print = list(self.formulation_block.component_objects(component_type, active=True))
            for component in components_to_print:
                component_df = convert_pyomo_object_to_dataframe(component)
                if component_df is not None:
                    # if additional non-timseries index, pivot for easier comparison
                    timeseries_index = [
                        x
                        for x in component_df.index.names
                        if isinstance(component_df.index.get_level_values(level=x), pd.DatetimeIndex)
                    ]
                    if len(timeseries_index) > 0:
                        if component_df.index.names != timeseries_index:
                            component_df = self._pivot_result_df(component_df, timeseries_index)
                    component_df.dropna(axis=0, how="all").round(3).sort_index().to_csv(
                        output_dir / f"{component.local_name}.csv", index=True
                    )

    def _create_results_from_non_indexed_attributes(self) -> list[pd.DataFrame]:
        """Loop through all numerical attributes on the object. If a `title` is defined in the attribute Field
        definition, Return the attribute value as a dataframe with all MODELED_YEARS as the index.

        Returns: list of pd.DataFrames with ["MODELED_YEARS""] as index and attribute 'title' as column header
        """
        annual_attributes = []

        # Loop over all attributes that are not Timeseries data that have a title defined for results reporting
        field_dict = self.model_fields | self.model_computed_fields
        for att in [
            x for x in field_dict if field_dict[x].title is not None and x not in self.get_timeseries_attribute_names()
        ]:
            column_name = field_dict[att].title
            start_year = min(self._build_year_based_annual_index())
            years = [year for year in self.formulation_block.model().MODELED_YEARS if year >= start_year]
            df = pd.DataFrame(
                index=pd.Index(name=self.formulation_block.model().MODELED_YEARS.name, data=years),
                data=str(getattr(self, att)),
                columns=[column_name],
            )
            annual_attributes.append(df)

        return annual_attributes

    def _create_hourly_timeseries_attribute_results(self) -> list[pd.DataFrame]:
        """Create a list of DataFrames of hourly-frequency Timeseries attributes of the Component that are flagged for
        export (i.e. they have a `title` argument defined in their pydantic Field() definition).

        Returns: list of pd.DataFrames with ["MODELED_YEARS", "DISPATCH_WINDOWS", "TIMESTAMPS"] as index and attribute
            'title' as column header
        """

        def _create_timeseries_results_from_attributes(att_name: str, by_weight=False) -> pd.DataFrame:
            """Helper method for converting hourly Timeseries data to an appropriately indexed DataFrame.

            Map hourly inputs to ["MODELED_YEARS", "DISPATCH_WINDOWS", "TIMESTAMPS"] of model temporal settings
            Note: this would only work for weather year indexed attributes

            Args:
                att_name: name of the timeseries attribute
                by_weight: bool. If true, multiply each timestamp by the dispatch_window_weight

            Returns: pd.DataFrame of hourly inputs used in the model

            """
            temporal_settings = self.formulation_block.model().temporal_settings
            modeled_years = temporal_settings.modeled_years.data.loc[temporal_settings.modeled_years.data.values].index
            df = pd.concat(
                [
                    temporal_settings.subset_timeseries_by_dispatch_windows(
                        getattr(self, att_name).data, modeled_year, apply_dispatch_window_weights=by_weight
                    )
                    for modeled_year in modeled_years
                ]
            )
            df.index.names = ["MODELED_YEARS", "DISPATCH_WINDOWS", "TIMESTAMPS"]
            df.columns = [self.model_fields[att_name].title]
            return df

        hourly_attributes = []
        for attr_name, field_info in self.model_fields.items():
            if (
                attr_name in self.get_timeseries_attribute_names()
                and field_info.title is not None
                and field_info.json_schema_extra["default_freq"] == "H"
                and attr_name not in ["profile_model_years"]
            ):
                if getattr(self, attr_name, None) is not None:
                    hourly_attributes.append(
                        _create_timeseries_results_from_attributes(
                            attr_name, by_weight=field_info.json_schema_extra.get("export_weighted_results", False)
                        )
                    )

        return hourly_attributes

    def _create_annual_timeseries_attribute_results(self) -> list[pd.DataFrame]:
        """Create a list of DataFrames of annual-frequency Timeseries attributes of the Component that are flagged for
        export (i.e. they have a `title` argument defined in their pydantic Field() definition).

        Returns: list of pd.DataFrames with ["MODELED_YEARS", "DISPATCH_WINDOWS", "TIMESTAMPS"] as index and attribute
            'title' as column header
        """

        def _create_timeseries_results_from_attributes(att_name: str, by_weight=False) -> pd.DataFrame:
            """
            Map hourly inputs to "MODELED_YEARS" of model temporal settings
            Note: this would only work for modeled year indexed attributes

            Args:
                att_name: name of the timeseries attribute

            Returns: pd.DataFrame of annual inputs used in the model

            """
            index = self._build_year_based_annual_index()
            df = pd.DataFrame.from_dict(
                {modeled_year: [getattr(self, att_name).data.at[modeled_year]] for modeled_year in index}
            ).T
            df.index.name = "MODELED_YEARS"
            df.columns = [self.model_fields[att_name].title]
            return df

        annual_attributes = []
        for attr_name, field_info in self.model_fields.items():
            if (
                attr_name in self.get_timeseries_attribute_names()
                and field_info.title is not None
                and field_info.json_schema_extra["default_freq"] == "YS"
                and not field_info.json_schema_extra.get("weather_year", False)
            ):
                if getattr(self, attr_name, None) is not None:
                    annual_attributes.append(
                        _create_timeseries_results_from_attributes(
                            attr_name, by_weight=field_info.json_schema_extra.get("export_weighted_results", False)
                        )
                    )

        return annual_attributes

    def _create_pyomo_component_results(
        self,
        report_hourly: bool,
        report_chrono: bool,
        disagg_group: bool,
    ) -> tuple[list[pd.DataFrame], list[pd.DataFrame], list[pd.DataFrame], list[pd.DataFrame]]:
        """Create lists of DataFrames of Pyomo data from the Component's formulation block

        Args:
            report_hourly: if False, skips hourly results reporting code
            report_chrono: if False, skips chrono results reporting code
            disagg_group: if False, hourly results are not reported for resources within operational groups

        Returns:
            annual_results: list of DataFrames of annual-indexed results
            hourly_results: list of DataFrames of dispatch window/timestamp-indexed results
            chrono_results: list of DataFrames of chrono-indexed results
            product_annual_results: list of DataFrames of product- and annual-indexed results
            product_hourly_results: list of DataFrames of product- and hourly-indexed results
            product_chrono_results: list of DataFrames of product- and chrono-indexed results
            unknown_index_results: list of DataFrames of results that are not indexed by any of the above
        """

        def _create_non_indexed_component_df(
            pyomo_component: Union[pyo.Param, pyo.Var, pyo.Expression, pyo.Set],
        ) -> pd.DataFrame:
            """Helper method for creating a DataFrame from a non-indexed Pyomo component

            Args:
                pyomo_component: non-indexed pyomo object. Example: "potential"

            Returns: pd.DataFrame of non indexed component object assuming `build_year` as MODELED_YEARS index

            """
            year = min(self._build_year_based_annual_index())
            component_df = pd.DataFrame(
                index=pd.Index(name=self.formulation_block.model().MODELED_YEARS.name, data=[year]),
                data=[pyo.value(pyomo_component)],
                columns=[pyomo_component.doc],
            )

            return component_df

        # Construct additional output expressions
        self._construct_output_expressions(construct_costs=True)

        model = self.formulation_block.model()
        annual_index = [model.MODELED_YEARS.name]
        hourly_index = [model.MODELED_YEARS.name, model.DISPATCH_WINDOWS.name, model.TIMESTAMPS.name]
        chrono_index = [model.MODELED_YEARS.name, model.CHRONO_PERIODS.name, model.TIMESTAMPS.name]
        weather_timestamp_index = [model.MODELED_YEARS.name, model.WEATHER_PERIODS.name, model.WEATHER_TIMESTAMPS.name]
        product_annual_index = [model.PRODUCTS.name] + annual_index
        product_hourly_index = [model.PRODUCTS.name] + hourly_index
        product_chrono_index = [model.PRODUCTS.name] + chrono_index

        annual_results = []
        hourly_results = []
        chrono_results = []
        weather_timestamp_results = []
        product_annual_results = []
        product_hourly_results = []
        product_chrono_results = []
        multi_index_weather_timestamp_results = []
        unknown_index_results = []
        # todo: add product_weather_timestamp_results here if necessary

        # Collect model components with their index sets if labeled with 'doc'
        for component in self.formulation_block.component_objects(descend_into=True):
            if component.doc is not None and not component.is_indexed():
                annual_results.append(_create_non_indexed_component_df(component))
            if component.is_indexed() and component.doc is not None:
                df = convert_pyomo_object_to_dataframe(component, use_doc_as_column_name=True, dual_only=True)
                first_year = min(
                    self._build_year_based_annual_index()
                )  # first year to print out, based on build year (if one exists)
                if isinstance(df.index, pd.MultiIndex):
                    name = df.index.names
                else:
                    name = [df.index.name]

                if hourly_index == name:
                    if (
                        report_hourly
                        and (
                            not (hasattr(self, "operational_group") and self.operational_group is not None)
                            or disagg_group  # Skip resources which belong to operational groups
                        )
                        and (
                            not (
                                hasattr(self, "aggregate_operations") and not self.aggregate_operations
                            )  # Skip resource groups which don't aggregate operations
                        )
                    ):
                        df = df.loc[df.index.get_level_values(model.MODELED_YEARS.name) >= first_year]
                        hourly_results.append(df)
                    else:
                        continue
                elif chrono_index == name:
                    if (
                        report_chrono
                        and model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
                        and self.allow_inter_period_sharing
                        and (
                            not (hasattr(self, "operational_group") and self.operational_group is not None)
                            or disagg_group
                            # Skip resources which belong to operational groups
                        )
                        and (
                            not (hasattr(self, "aggregate_operations") and not self.aggregate_operations)
                            # Skip resource groups which don't aggregate operations
                        )
                    ):
                        df = df.loc[df.index.get_level_values(model.MODELED_YEARS.name) >= first_year]
                        chrono_results.append(df)
                    else:
                        continue
                elif weather_timestamp_index == name and report_chrono:
                    df = df.loc[df.index.get_level_values(model.MODELED_YEARS.name) >= first_year]
                    weather_timestamp_results.append(df)
                elif annual_index == name:
                    df = df.loc[df.index >= first_year]
                    annual_results.append(df)
                elif len(name) > 3 and weather_timestamp_index == name[-3:]:
                    # This is for pyomo components that are indexed on something, *then* MODELED_YEARS and
                    # WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS:
                    MODELED_YEAR_INDEX_LEVEL = 1
                    df = df[df.index.get_level_values(MODELED_YEAR_INDEX_LEVEL) >= first_year]
                    multi_index_weather_timestamp_results.append(df)
                elif len(model.PRODUCTS) > 0:
                    # rename any index with products to model.PRODUCTS.name
                    for index_name in df.index.names:
                        index_values = set(df.index.get_level_values(index_name))
                        if index_values.issubset(set(model.PRODUCTS)):
                            df = df.rename_axis(index={index_name: model.PRODUCTS.name})
                    name = df.index.names

                    if product_hourly_index == name:
                        if (
                            report_hourly
                            and (
                                not (hasattr(self, "operational_group") and self.operational_group is not None)
                                or disagg_group  # Skip resources which belong to operational groups
                            )
                            and (
                                not (
                                    hasattr(self, "aggregate_operations") and not self.aggregate_operations
                                )  # Skip resource groups which don't aggregate operations
                            )
                        ):
                            df = df.loc[df.index.get_level_values(model.MODELED_YEARS.name) >= first_year]
                            product_hourly_results.append(df)
                        else:
                            continue
                    elif product_chrono_index == name:
                        if (
                            report_chrono
                            and model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
                            and self.allow_inter_period_sharing
                            and (
                                not (hasattr(self, "operational_group") and self.operational_group is not None)
                                or disagg_group
                                # Skip resources which belong to operational groups
                            )
                            and (
                                not (hasattr(self, "aggregate_operations") and not self.aggregate_operations)
                                # Skip resource groups which don't aggregate operations
                            )
                        ):
                            df = df.loc[df.index.get_level_values(model.MODELED_YEARS.name) >= first_year]
                            product_chrono_results.append(df)
                        else:
                            continue
                    elif product_annual_index == name:
                        df = df.loc[df.index.get_level_values(model.MODELED_YEARS.name) >= first_year]
                        product_annual_results.append(df)
                    else:  # Unknown index
                        if model.MODELED_YEARS.name in name:
                            df = df.loc[df.index.get_level_values(model.MODELED_YEARS.name) >= first_year]
                        unknown_index_results.append(df)
                else:  # Unknown index
                    if model.MODELED_YEARS.name in name:
                        df = df.loc[df.index.get_level_values(model.MODELED_YEARS.name) >= first_year]
                    unknown_index_results.append(df)

        return (
            annual_results,
            hourly_results,
            chrono_results,
            weather_timestamp_results,
            product_annual_results,
            product_hourly_results,
            product_chrono_results,
            unknown_index_results,
            multi_index_weather_timestamp_results,
        )

    def _add_zones_to_results_summary(self, results_df: pd.DataFrame) -> pd.DataFrame:
        """Method for adding a Zone(s) column on annual, hourly, and chrono-indexed results"""
        if hasattr(self, "zones"):  # Only add the column if this component is linked to at least one zone
            zones = ",".join(map(str, self.zones.keys()))
            results_df.insert(0, "Zone(s)", zones)
        return results_df

    def _add_operational_group_to_results_summary(self, results_df: pd.DataFrame) -> pd.DataFrame:
        """Method for adding a column that shows an asset's operational group on annual, hourly, and chrono-indexed results"""
        if (
            hasattr(self, "operational_group") and self.operational_group is not None
        ):  # Only add the column if this component is linked to at least one operational_group
            results_df.insert(0, "Operational Group", self.operational_group.name)
        return results_df

    def _add_fuels_to_results_summary(self, results_df: pd.DataFrame) -> pd.DataFrame:
        """Method for adding a Fuel(s) column as the first column on annual results"""
        if hasattr(self, "candidate_fuels"):  # Only add the column if this component is linked to at least one fuel
            fuels = ",".join(map(str, self.candidate_fuels.keys()))
            results_df.insert(0, "Fuel(s)", fuels)
        return results_df

    def _append_dispatch_window_weights(self, df: pd.DataFrame):
        # Append dispatch window weights to hourly results df
        df = df.merge(
            self.formulation_block.model().temporal_settings.dispatch_window_weights,
            left_on=self.formulation_block.model().DISPATCH_WINDOWS.name,
            right_index=True,
            how="left",
        )
        df.set_index("weight", inplace=True, append=True)
        return df

    def export_component_result_summary(self, output_dir: pathlib.Path, results_settings: dict) -> pd.DataFrame:
        """
        Loop through all pyomo objects on the formulation block and return all results objects with a labeled `doc` argument.
        Loop through all the input attributes on the class object and return all inputs with a `title` argument in the Field definition.

        Concatenate all inputs and results by frequency of index and save to csv.
        Currently only implemented for non-indexed, annual, hourly, and chrono periods.

        Args:
            output_dir: path to save summary results as csv
            results_settings: dictionary indicating which sets of results to report

        Returns: pd.DataFrame of annual results

        """
        output_dir = output_dir.joinpath(self.results_reporting_folder, self.name)
        output_dir.mkdir(exist_ok=True, parents=True)

        report_hourly = results_settings["report_hourly"]
        report_chrono = results_settings["report_chrono"]
        disagg_group = results_settings["disagg_group"]

        # Convert all the Pyomo components from the formulation block to DataFrames
        (
            annual_results,
            hourly_results,
            chrono_results,
            weather_timestamp_results,
            product_annual_results,
            product_hourly_results,
            product_chrono_results,
            unknown_index_results,
            multi_index_weather_timestamp_results,
        ) = self._create_pyomo_component_results(
            report_hourly=report_hourly,
            report_chrono=report_chrono,
            disagg_group=disagg_group,
        )

        # Append hourly-indexed Component attributes to list of hourly results
        if (
            report_hourly
            and (
                not (hasattr(self, "operational_group") and self.operational_group is not None) or disagg_group
            )  # Skip resources which belong to operational groups
            and (not (hasattr(self, "aggregate_operations") and not self.aggregate_operations))
        ):  # Skip resource groups which don't aggregate operations
            hourly_results = hourly_results + self._create_hourly_timeseries_attribute_results()
            if len(hourly_results) > 0:
                hourly_results = pd.concat(hourly_results, axis=1)
                hourly_results = self._append_dispatch_window_weights(hourly_results)

                # Insert a column for operational group, zone, and fuel if this component has them
                hourly_results = self._add_zones_to_results_summary(hourly_results)
                hourly_results = self._add_operational_group_to_results_summary(hourly_results)
                hourly_results = self._add_fuels_to_results_summary(hourly_results)

                # Export to csv
                hourly_results.to_csv(output_dir.joinpath(f"{self.name}_hourly_results.csv"), index=True)

        # Append annual-indexed Component attributes to list of annual results
        annual_results = (
            annual_results
            + self._create_annual_timeseries_attribute_results()
            + self._create_results_from_non_indexed_attributes()
        )
        if len(annual_results) > 0:
            annual_results = pd.concat(annual_results, axis=1)

            # Reorder columns
            if hasattr(self, "annual_results_column_order"):
                annual_results = annual_results[
                    self._order_annual_results_columns(self.annual_results_column_order, annual_results)
                ]

            # Export to csv
            annual_results.to_csv(output_dir.joinpath(f"{self.name}_annual_results.csv"), index=True)

            # Add additional index columns for easy filtering in concatenated results (annual results summaries)
            annual_results.loc[:, "Component Name"] = self.name
            annual_results.loc[:, "Component Type"] = self.__class__.__name__
            annual_results.loc[:, "Category"] = self.results_reporting_category
            annual_results.set_index(
                ["Component Name", "Component Type", "Category", annual_results.index], inplace=True
            )
            annual_results.rename_axis(
                index=("Component Name", "Component Type", "Category", "Modeled Year"), inplace=True
            )

        if len(chrono_results) > 0 and report_chrono:
            chrono_results = pd.concat(chrono_results, axis=1)

            # Insert a column for operational group and zone if this component has them
            chrono_results = self._add_zones_to_results_summary(chrono_results)
            chrono_results = self._add_operational_group_to_results_summary(chrono_results)
            chrono_results = self._add_fuels_to_results_summary(chrono_results)

            chrono_results.to_csv(output_dir.joinpath(f"{self.name}_chrono_results.csv"), index=True)

        if len(weather_timestamp_results) > 0 and report_chrono:
            weather_timestamp_results = pd.concat(weather_timestamp_results, axis=1)
            weather_timestamp_results.to_csv(
                output_dir.joinpath(f"{self.name}_weather_timestamp_results.csv"), index=True
            )

        if (
            report_hourly
            and (
                not (hasattr(self, "operational_group") and self.operational_group is not None) or disagg_group
            )  # Skip assets which belong to operational groups
            and (not (hasattr(self, "aggregate_operations") and not self.aggregate_operations))
        ):  # Skip asset groups which don't aggregate operations
            if len(product_hourly_results) > 0:
                product_hourly_results = pd.concat(product_hourly_results, axis=1)
                product_hourly_results = self._append_dispatch_window_weights(product_hourly_results)
                product_hourly_results = self._add_zones_to_results_summary(product_hourly_results)
                product_hourly_results = self._add_operational_group_to_results_summary(product_hourly_results)
                product_hourly_results.to_csv(
                    output_dir.joinpath(f"{self.name}_hourly_results_by_product.csv"), index=True
                )

        if len(product_annual_results) > 0:
            product_annual_results = pd.concat(product_annual_results, axis=1)
            product_annual_results = self._add_zones_to_results_summary(product_annual_results)
            product_annual_results = self._add_operational_group_to_results_summary(product_annual_results)
            product_annual_results.to_csv(output_dir.joinpath(f"{self.name}_annual_results_by_product.csv"), index=True)

            # add additional index columns for easy filtering in concatenated results
            product_annual_results.loc[:, "Component Name"] = str(self.name)
            product_annual_results.loc[:, "Component Type"] = self.__class__.__name__
            product_annual_results.loc[:, "Category"] = self.results_reporting_category
            product_annual_results.reset_index(inplace=True)
            product_annual_results.set_index(
                ["Component Name", "Component Type", "Category", "PRODUCTS", "MODELED_YEARS"], inplace=True
            )
            product_annual_results.rename_axis(
                index=("Component Name", "Component Type", "Category", "Product", "Modeled Year"), inplace=True
            )

        if len(product_chrono_results) > 0 and report_chrono:
            product_chrono_results = pd.concat(product_chrono_results, axis=1)
            product_chrono_results = self._add_zones_to_results_summary(product_chrono_results)
            product_chrono_results = self._add_operational_group_to_results_summary(product_chrono_results)
            product_chrono_results.to_csv(output_dir.joinpath(f"{self.name}_chrono_results_by_product.csv"), index=True)

        if len(unknown_index_results) > 0:
            # Special treatment of policy results by asset (not yet implemented for HourlyEnergyStandard policies)
            if hasattr(self, "_create_component_indexed_policy_results"):
                component_indexed_policy_results = self._create_component_indexed_policy_results(unknown_index_results)
                if component_indexed_policy_results is not None:
                    policy_name = self.name
                    component_indexed_policy_results.to_csv(
                        output_dir.joinpath(f"{policy_name}_annual_results_by_component.csv"), index=True
                    )

            # combine unknown_index_results if they all have the same index
            elif all(df.index.equals(unknown_index_results[0].index) for df in unknown_index_results):
                # Concatenate the dataframes
                all_unknown_index_results = pd.concat(unknown_index_results, axis=1)
                df_name = "_".join(map(str, all_unknown_index_results.columns))
                df_name = df_name.replace("/", "_")  # Replace '/' with '_' for columns with names like "$/MWh"
                all_unknown_index_results.to_csv(output_dir.joinpath(f"{df_name}.csv"), index=True)

            else:
                for df in unknown_index_results:
                    df_name = df.columns[0]
                    df_name = df_name.replace("/", "_")  # Replace '/' with '_' for columns with names like "$/MWh"
                    df.to_csv(output_dir.joinpath(f"{df_name}.csv"), index=True)

        if len(multi_index_weather_timestamp_results) > 0:
            multi_index_weather_timestamp_results = pd.concat(multi_index_weather_timestamp_results, axis=1)
            multi_index_weather_timestamp_results.to_csv(
                output_dir.joinpath(f"{self.name}_multi_index_weather_timestamp_results.csv"), index=True
            )
        # Return annual_results for concatenation into annual_results_summaries
        return annual_results, product_annual_results
