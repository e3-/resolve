from __future__ import annotations

import functools
import importlib
import os
import pathlib
import textwrap
from collections import defaultdict
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import xlwings as xw
import yaml
from loguru import logger
from pydantic import Field
from tqdm.notebook import tqdm
from upath import UPath

from new_modeling_toolkit.core.custom_model import CustomModel
from new_modeling_toolkit.core.custom_model import ModelType
from new_modeling_toolkit.core.utils.pandas_utils import compare_dataframes
from new_modeling_toolkit.core.utils.util import DirStructure
from new_modeling_toolkit.core.utils.xlwings import ExcelApiCalls
from new_modeling_toolkit.system.generics.generic_linkages import *

excel_api = ExcelApiCalls()


class LinkageFieldsToWrite(CustomModel):
    instances: list[str] = []
    linkage_class: Any | None = None


class ComponentToWrite(CustomModel):
    linkages_to_write: list[LinkageFieldsToWrite] = []
    include: None | list[str] = None
    exclude: None | list[str] = None
    num_rows: int = 30

    def construct(
        self,
        *,
        anchor_range: xw.Range,
        modeled_years_range: list[Any],
        modeled_years_visible: list,
        component_tables: list[str],
        add_doc_hyperlinks: bool,
        row_offset: int,
        column_offset: int,
    ):
        module_name, class_name = self.name.rsplit(".", 1)
        component = getattr(importlib.import_module(f"new_modeling_toolkit.{module_name}"), class_name)

        rows_to_add, columns_to_add, table_name = component.to_excel(
            anchor_range=anchor_range.offset(row_offset=row_offset, column_offset=column_offset),
            excel_api=excel_api,
            modeled_years_range=modeled_years_range,
            modeled_years_visible=modeled_years_visible,
            add_doc_hyperlinks=add_doc_hyperlinks,
            linkages_to_write=self.linkages_to_write,
            table_name=f"{module_name}.{class_name}",
            include=self.include,
            exclude=self.exclude,
            num_rows=self.num_rows,
        )
        row_offset += rows_to_add
        column_offset += columns_to_add
        component_tables += [table_name]

        return row_offset, column_offset, component_tables


class SectionToWrite(CustomModel):
    """Sheets are sub-divided into sections separated by Header-formatted rows."""

    level: int = 1
    sections: list[SectionToWrite] = []
    components: list[ComponentToWrite] = []

    def construct(
        self,
        *,
        sheet: xw.Sheet,
        anchor_range: xw.Range,
        modeled_years_range: list[Any],
        modeled_years_visible: list | None = None,
        component_tables: list[str],
        add_doc_hyperlinks: bool,
    ) -> tuple[int, int]:
        logger.debug(f"----Constructing section: {self.name}")

        section_header = sheet.range(anchor_range, anchor_range.end("right"))
        excel_api.set_cell_style(section_header, excel_api.styles(sheet.book, f"Heading {self.level}"))
        section_header.resize(1, 1).value = self.name

        column_offset = 0
        row_offset = 4
        for section in self.sections:
            rows_to_add, columns_to_add = section.construct(
                sheet=sheet,
                anchor_range=anchor_range.offset(row_offset=row_offset, column_offset=column_offset),
                modeled_years_range=modeled_years_range,
                modeled_years_visible=modeled_years_visible,
            )
            row_offset += 0
            column_offset += 0

        row_offset += 4
        for component in self.components:
            row_offset, column_offset, component_tables = component.construct(
                component_tables=component_tables,
                anchor_range=anchor_range,
                modeled_years_range=modeled_years_range,
                modeled_years_visible=modeled_years_visible,
                add_doc_hyperlinks=add_doc_hyperlinks,
                row_offset=row_offset,
                column_offset=column_offset,
            )

        return 0, column_offset, component_tables


class SheetToWrite(CustomModel):
    title: str
    sections: list[SectionToWrite] = []
    name: str = Field(max_length=31)

    def __init__(self, **kwargs):
        """I don't know how to create the recursive heading level, so I'm manually assigning the level (which affects the heading text formatting)"""
        super().__init__(**kwargs)

        if self.title is None:
            self.title = self.name

        for section in self.sections:
            for subsection in section.sections:
                subsection.level = 2
                for subsubsection in subsection.sections:
                    subsubsection.level = 3

    def construct(
        self,
        *,
        wb: xw.Book,
        modeled_years_range: list[Any],
        modeled_years_visible: list | None,
        component_tables: list[str],
        add_doc_hyperlinks: bool,
    ):

        if self.name in [sheet.name for sheet in wb.sheets]:
            new_name = f"{self.name} ({datetime.now():%H-%M-%S})"
            logger.info(f"Renaming existing sheet: {new_name}")
            wb.sheets[self.name].name = new_name
        logger.info(f"Constructing new sheet: {self.title}")
        wb.sheets.add(self.name)
        excel_api.set_gridlines(wb.app, False)

        excel_api.set_cell_style(wb.sheets[self.name].range("1:1"), excel_api.styles(wb, "Title"))

        wb.sheets[self.name].range("A1").value = self.title

        # Hide parameter row (hard-coding for now...)
        excel_api.group(wb.sheets[self.name].range("A6"), by="row")

        column_offset = 0
        row_offset = 0
        for section in self.sections:
            rows_to_add, columns_to_add, table_names = section.construct(
                sheet=wb.sheets[self.name],
                anchor_range=wb.sheets[self.name]
                .range("E3")
                .offset(row_offset=row_offset, column_offset=column_offset),
                modeled_years_range=modeled_years_range,
                modeled_years_visible=modeled_years_visible,
                component_tables=component_tables,
                add_doc_hyperlinks=add_doc_hyperlinks,
            )
            row_offset += rows_to_add
            column_offset += columns_to_add

        # Hide details only once per sheet, or else you end up with many nested groups
        excel_api.hide_details(wb.sheets[self.name])

        return component_tables


class ExcelTemplate(CustomModel):
    template_path: str | None = None
    modeled_years_range: list[Any] = list(range(2023, 2051))
    modeled_years_visible: list | None = None
    sheets: list[SheetToWrite] = []
    component_tables: list[str] = []
    add_doc_hyperlinks: bool = True
    log_file_path: UPath = (
        UPath(__file__).parents[2].absolute()
        / "reports"
        / "ui"
        / f"scenario-tool-{datetime.now():%Y-%m-%d-%H-%M-%S}.log"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log_file_path.parent.mkdir(exist_ok=True, parents=True)
        # xlwings passes stderr log messages as modal popups, which is annoying. Removing the default loggers avoids this.
        logger.remove()
        logger.add(self.log_file_path, level="INFO")

    def construct(self):
        """Construct a Scenario Tool"""
        with xw.App(visible=True) as app:
            app.calculation = "manual"
            app.screen_updating = False

            wb = xw.Book(self.template_path)
            wb.save(pathlib.Path(self.template_path).parent.absolute() / f"{self.name}")

            wb.sheets["Cover"].range("A1").value = self.name

            for sheet in self.sheets:
                self.component_tables = sheet.construct(
                    wb=wb,
                    modeled_years_range=self.modeled_years_range,
                    modeled_years_visible=self.modeled_years_visible,
                    component_tables=self.component_tables,
                    add_doc_hyperlinks=self.add_doc_hyperlinks,
                )

            wb.save()

        logger.info("Done!")


def load_log_to_excel(func, *args, **kwargs):
    """Load log messages into corresponding "Log" tab in ScenarioTool, even if wrapped method fails.

    Assumes the decorated method is an instance method of ScenarioTool.
    """

    # Run decorated method
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # Clear (or create) Log sheet
        if "Log" not in [name.name for name in self.book.sheets]:
            self.book.sheets.add("Log")
        self.book.sheets["Log"].clear_contents()

        # Run the decorated function
        try:
            value = func(self, *args, **kwargs)
        except Exception as e:
            logger.error(e)
            raise e

        # Copy log into associated ScenarioTool instance
        with open(self.log_file_path, "r") as f:
            lines = f.readlines()
            self.book.sheets["Log"].range("A1").options(transpose=True).value = lines

        self.book.sheets["Log"].range("A1").expand("table").wrap_text = False
        self.book.sheets["Log"].activate()

        return value

    return wrapper


class ScenarioTool(ExcelTemplate):
    book: xw.Book

    def __init__(self, *, book: str):
        book = xw.Book(UPath(book))
        name = book.name
        super().__init__(name=name, book=book)
        logger.info(f"Reading {name}")

    @classmethod
    def from_template(cls, *, schema_file: UPath | None = None, add_doc_hyperlinks: bool):
        if schema_file is None:
            schema_file = UPath(__file__).parent / "ui-config.yml"

        with open(schema_file, "r") as config_file:
            yml_dict = yaml.safe_load(config_file)

            st = ExcelTemplate(**yml_dict, add_doc_hyperlinks=add_doc_hyperlinks)
            st.construct()

            return st

    @load_log_to_excel
    def export_system(
        self, model: ModelType, compare_files: bool = False, dry_run: bool = False, sheet_names: list[str] | None = None
    ):
        # TODO 2024-04-29: Add a version restriction and deprecation warning
        sheet = self.book.sheets[f"{model.value} Case Setup"]
        dir_str = DirStructure(
            start_dir=UPath(self.book.fullname).parent, data_folder=sheet.range(f"{model.value}.__DATAFOLDER__").value
        )
        self.book.sheets["xlwings.conf"].range("B3:B8").value = str(UPath(self.book.fullname).parent)
        system_save_path = dir_str.data_interim_dir / "systems" / sheet.range(f"{model.value}.system").value
        system_save_path.mkdir(exist_ok=True, parents=True)
        # Assume that table name format is always [kit sub-module name].[class name].__[counter] (see Component.to_excel())
        component_tables, three_way_linkage_tables = self._convert_tables_to_dataframes(sheet_names=sheet_names)

        self._save_system_three_way_linkages_csv(system_save_path, three_way_linkage_tables)

        linkages_for_linkages_csv = []
        linkage_attributes_to_print: dict[str, list] = {}
        components_for_components_csv = []
        for (module_name, class_name), tables in sorted(component_tables.items(), key=lambda item: item[0][1]):
            # If there are no tables, skip. Not exactly sure when this would ever happen, but just in case
            if not tables:
                continue

            logger.info(f"Exporting: {class_name}")
            data = pd.concat(tables, axis=0, ignore_index=True).dropna(how="all")
            data = self._format_attributes_dataframe(data)

            if data.empty:
                continue

            # Collect linkages & components for `components.csv` and `linkages.csv`
            try:
                component_class = getattr(importlib.import_module(f"new_modeling_toolkit.{module_name}"), class_name)
            except ModuleNotFoundError:
                logger.error(
                    f"Tried to save table with name starting with ({module_name}.{class_name}), but module '{module_name}' could not be found"
                )
            except AttributeError:
                logger.error(
                    f"Tried to save table with name starting with ({module_name}.{class_name}), but class '{class_name}' could not be found"
                )

            linkages_for_linkages_csv, data = self._collect_linkages_to_include(
                linkages_for_linkages_csv, ["from", "to"], component_class, data
            )
            components_for_components_csv, data = self._collect_components_to_include(
                components_for_components_csv, component_class, data
            )

            # Remove `include`
            data = data.loc[data["attribute"] != "include", :]
            if data.empty:
                continue

            # Save individual component attribute CSVs
            component_class.dfs_to_csv(
                instances=data, wb=self.book, dir_str=dir_str, compare_files=compare_files, dry_run=dry_run
            )
            logger.debug(f" └─ Success!")

        # Print out system `components.csv` and `linkages.csv` (only if the entire workbook is exported,
        # since the components & linkages are collected by reading through all the `Include` flags in all the tables)
        # if sheet_names is None:
        logger.info("Exporting: System component & linkage configuration files")
        self._save_system_components_csv(components_for_components_csv, compare_files, dry_run, system_save_path)
        self._save_system_linkages_csv(
            linkages_for_linkages_csv,
            ["linkage", "component_from", "component_to", "scenario"],
            compare_files,
            dry_run,
            system_save_path,
            "linkages",
        )

        logger.debug(f" └─ Success!")
        self.book.app.status_bar = "Done."

    def _save_system_three_way_linkages_csv(self, system_save_path, three_way_linkage_tables):
        # Write three_way_linkages.csv
        if three_way_linkage_tables:
            # Specify boolean nature of all bool columns (e.g., Include column).
            # Pandas does not allow concatenation of dfs with columns of type object that include only boolean values
            for df in three_way_linkage_tables:
                for col in df.select_dtypes(include=["object"]):
                    if df[col].dropna().isin([True, False]).all():
                        df[col] = df[col].astype(bool)
            custom_constraints_tables = [
                df for df in three_way_linkage_tables if df["linkage"].iloc[0] == "CustomConstraintLinkage"
            ]
            custom_constraints = (
                pd.concat(custom_constraints_tables) if len(custom_constraints_tables) > 0 else pd.DataFrame()
            )
            processes_tables = [df for df in three_way_linkage_tables if "Process" in df["linkage"].iloc[0]]
            processes = pd.concat(processes_tables) if len(processes_tables) > 0 else pd.DataFrame()

            def _twl_filter_columns(twl_df: pd.DataFrame) -> pd.DataFrame:
                twl_df = twl_df.iloc[:, [0, 1, 2, -1]]
                split_names = twl_df.iloc[:, 0].str.split(", ", expand=True)
                twl_df = pd.concat(
                    [twl_df["linkage"], split_names, twl_df["Data Scenario Tag"]],
                    axis=1,
                    ignore_index=True,
                )
                twl_df.columns = ["linkage", "component_1", "component_2", "component_3", "scenario"]
                return twl_df

            if not custom_constraints.empty:
                custom_constraints = _twl_filter_columns(custom_constraints)

            if not processes.empty:
                processes = _twl_filter_columns(processes)

            # Combine custom_constraints and processes
            if not (custom_constraints.empty and processes.empty):
                three_way_linkages = pd.concat([custom_constraints, processes], ignore_index=True)
                three_way_linkages.to_csv(system_save_path / "three_way_linkages.csv", index=False)

    def _convert_tables_to_dataframes(self, sheet_names: list[str] | None = None):
        three_way_linkage_tables = []
        component_tables = defaultdict(list)

        # If no sheets provided, loop through all sheets in the workbook
        if sheet_names is None:
            sheets = self.book.sheets
        else:
            sheets = [sheet for sheet in self.book.sheets if sheet.name in sheet_names]

        tables_to_load = [
            tbl
            for sheet in sheets
            for tbl in sheet.tables
            if ".__" in tbl.name and (tbl.name.startswith("core.") or tbl.name.startswith("system."))
        ]

        progress_bar = tqdm(total=len(tables_to_load), display=False, smoothing=None)
        for table in tables_to_load:
            logger.debug(f"Reading {table.name}")

            progress_bar.update()
            excel_progress_bar = str(progress_bar)
            self.book.app.status_bar = f"Reading tables: {excel_progress_bar} ({table.name})"

            # 1. The primary way to find component tables is based on the table's name (always ending in `.__[#]`
            module_name, class_name, _ = table.name.rsplit(".", 2)

            # Guard clause: Three-way linkages can be immediately concatenated into three_way_linkages.csv
            if module_name == "core.three_way_linkage":
                if class_name == "CustomConstraintLinkage":
                    df = table.range.options(pd.DataFrame, index=0).value.dropna(how="all")
                    df["linkage"] = class_name
                    # drop all rows without an appropriate name (value of False from empty row)
                    df = df[(df["Name"] != False) & (df["Name"].notna())]
                    if not df.empty:
                        three_way_linkage_tables += [df]
                else:
                    raise NotImplementedError(f"Three-way linkage saving for {class_name} is not implemented")
            elif module_name == "system.generics.process":
                df = table.range.options(pd.DataFrame, index=0).value.dropna(how="all")
                df["linkage"] = class_name
                # drop all rows without an appropriate name (value of False from empty row)
                df = df[(df["Name"] != False) & (df["Name"].notna())]
                if not df.empty:
                    three_way_linkage_tables += [df]


            # 2. Linkage attributes can also be appended to component tables (via `linkages_to_write` option),
            # which need to be written out to the corresponding linkage attributes CSV file.
            # Identify these by looking at the attribute row for names separated by 2 periods (`.`)
            start_cell = table.range[0, 0]
            row_offset = -1  # Dynamically find the number of non-blank rows above the table
            check_cell = start_cell.offset(row_offset, 0)
            while check_cell.value is None:
                row_offset -= 1
                check_cell = start_cell.offset(row_offset, 0)
            df = (
                table.range.offset(row_offset=row_offset)
                .resize(row_size=table.range.shape[0] - row_offset)
                .options(pd.DataFrame, chunksize=250, index=0, header=-row_offset + 1)
                .value
            ).dropna(how="all")

            # Remove the header rows that don't matter
            df.columns = pd.MultiIndex.from_tuples([(col[0], col[-row_offset]) for col in df.columns])

            # Split table into pieces
            parsed_headers = (
                df.columns.get_level_values(0)
                .to_series()
                .fillna(value="")
                .str.split(".", expand=True)
                .reset_index(drop=True)
            )
            parsed_headers = parsed_headers.loc[~parsed_headers[0].isin(["name", "scenarios", "include"]), :]

            # If there are no linkages appended to this component table, the entire table is for the original component
            if parsed_headers.shape[1] == 1:
                component_tables.setdefault((module_name, class_name), []).append(df)
            else:
                assert (
                    len(parsed_headers.columns) > 1 and len(parsed_headers.columns) < 4
                ), "Attribute names don't seem to match the naming scheme (names should have no more than three parts separated by periods)."

                # Get just the original Component table, which should have None in the last column
                id_columns = [col for col in df.columns if col[0] in ["name", "scenarios", "include"]]

                # Ensure is_attr_condition is a boolean Series, even when column 2 is missing
                if 2 in parsed_headers.columns:  # Check if column 2 exists
                    is_attr_condition = parsed_headers[2].isnull()
                else:
                    # Create a Series of True for all rows if column 2 doesn't exist
                    is_attr_condition = pd.Series([True] * len(parsed_headers), index=parsed_headers.index)

                # Build the list of columns based on the condition
                attr_columns = [
                    col for i, col in enumerate(df.columns) if i in parsed_headers.loc[is_attr_condition, :].index
                ]

                df_slice = df.loc[:, id_columns + attr_columns].copy()

                component_tables.setdefault((module_name, class_name), []).append(df_slice)

                # Loop through unique linkage instances in the table
                linkages_in_table = list(parsed_headers.dropna().groupby([0, 1]).first().index)
                linkages_in_table = [
                    (c.__module__.split(".", 1)[1], l, i)
                    for i, l in linkages_in_table
                    for c in Linkage.get_subclasses()
                    if c.__name__ == l
                ]
                # module, linkage, instance name
                for m, l, i in linkages_in_table:
                    logger.info(f"Reading {table.name} ({i})")
                    columns_for_this_linkage = parsed_headers.loc[
                        (parsed_headers[0] == i) & (parsed_headers[1] == l), :
                    ].index
                    linkage_attr_columns = [col for i, col in enumerate(df.columns) if i in columns_for_this_linkage]
                    df_slice = df.loc[:, id_columns + linkage_attr_columns].copy()

                    # Update `name` column to be the name of the linkage
                    if f"{i}.{l}.to" in df_slice.columns.get_level_values(0):
                        df_slice = df_slice.loc[
                            (df_slice.loc[:, pd.IndexSlice[f"{i}.{l}.to", :]] == True).squeeze(axis=1), :
                        ]
                        df_slice.iloc[:, 0] = df_slice.iloc[:, 0] + f", {i}"
                    elif f"{i}.{l}.from" in df_slice.columns.get_level_values(0):
                        df_slice = df_slice.loc[
                            (df_slice.loc[:, pd.IndexSlice[f"{i}.{l}.from", :]] == True).squeeze(axis=1), :
                        ]
                        df_slice.iloc[:, 0] = f"{i}, " + df_slice.iloc[:, 0]
                    # Check if the linkage was defined within this table directly
                    elif f"{l}.to" in {col[0] for col in attr_columns}:
                        # Filter rows where the column is not None or NaN
                        df_slice = df_slice[df_slice.loc[:, linkage_attr_columns].notna().any(axis=1)]
                        df_slice_index = df_slice.index
                        # Append the value from the column to the `name` column
                        df_slice.iloc[:, 0] = (
                            df_slice.iloc[:, 0] + ", " + df.loc[df_slice_index, pd.IndexSlice[f"{l}.to", :]].iloc[:, 0]
                        )
                    elif f"{l}.from" in {col[0] for col in attr_columns}:
                        # Filter rows where the column is not None or NaN
                        df_slice = df_slice[df_slice.loc[:, linkage_attr_columns].notna().any(axis=1)]
                        df_slice_index = df_slice.index
                        # Append the value from the column to the `name` column
                        df_slice.iloc[:, 0] = (
                            df.loc[df_slice_index, pd.IndexSlice[f"{l}.to", :]].iloc[:, 0] + ", " + df_slice.iloc[:, 0]
                        )

                    # Remove the instance & linkage class names
                    df_slice.columns = pd.MultiIndex.from_tuples(
                        [(str(attr).split(".")[-1], *rest) for attr, *rest in df_slice.columns.tolist()]
                    )

                    component_tables.setdefault((m, l), []).append(df_slice)

        return component_tables, three_way_linkage_tables

    def _save_system_linkages_csv(
        self, linkages_for_linkages_csv, indices, compare_files, dry_run, system_save_path, filename
    ):
        if linkages_for_linkages_csv:
            linkages_df = pd.concat(linkages_for_linkages_csv, axis=0, ignore_index=True)
            if (
                (system_save_path / f"{filename}.csv").exists()
                and os.stat(system_save_path / f"{filename}.csv").st_size > 0
                and compare_files
            ):
                linkages_df["include"] = True
                previous = pd.read_csv(system_save_path / f"{filename}.csv")
                # Linkages have no column to compare on, so need to manually add one
                previous["include"] = True
                try:
                    comparison = compare_dataframes(
                        previous=previous,
                        new=linkages_df,
                        indices=indices,
                        column_to_compare="include",
                    )
                    if not comparison.empty:
                        comparison = textwrap.indent(comparison.to_string(), " > ")
                        logger.warning(f'├─ Differences in {system_save_path / f"{filename}.csv"}:\n{comparison}')
                except ValueError:
                    logger.error(f'Could not compare CSV files: {system_save_path / f"{filename}.csv"}')
                linkages_df.drop(["include"], axis=1)

            if not dry_run:
                linkages_df.to_csv(system_save_path / f"{filename}.csv", index=False)

    def _save_system_components_csv(self, components_for_components_csv, compare_files, dry_run, system_save_path):
        if components_for_components_csv:
            components_df = pd.concat(components_for_components_csv, axis=0, ignore_index=True)
            if (
                (system_save_path / "components.csv").exists()
                and os.stat(system_save_path / "components.csv").st_size > 0
                and compare_files
            ):
                try:
                    comparison = compare_dataframes(
                        previous=pd.read_csv(system_save_path / "components.csv"),
                        new=components_df,
                        indices=["component", "instance", "scenario"],
                        column_to_compare="include",
                    )
                    if not comparison.empty:
                        comparison = textwrap.indent(comparison.to_string(), " > ")
                        logger.warning(f'├─ Differences in {system_save_path / "components.csv"}:\n{comparison}')
                except ValueError:
                    logger.error(f'Could not compare CSV files: {system_save_path / "components.csv"}')
            if not dry_run:
                components_df.to_csv(system_save_path / "components.csv", index=False)

    def _collect_components_to_include(self, components_for_components_csv, component_class, data):
        # If this table & component is a linkage, we don't put them into the components.csv file
        if component_class in Linkage.get_subclasses():
            return components_for_components_csv, data

        # Add components to include to components.csv
        components_to_include = data.loc[data["attribute"] == "include", ["name", "scenario", "value"]].copy()

        components_to_include.columns = ["instance", "scenario", "include"]
        components_to_include["component"] = component_class.__name__
        components_to_include = components_to_include[["component", "instance", "scenario", "include"]]

        components_for_components_csv.append(components_to_include)

        return components_for_components_csv, data

    def _collect_linkages_to_include(
        self, linkages_for_linkages_csv: list, suffixes: list, component_class, data: pd.DataFrame
    ):
        """Collect all linkages for the component so that they can be put into `linkages.csv`."""
        # TODO 2024-04-30: This is a pretty weak implementation (since it assumes that linkages have these suffixes), but should work for now until `Linkage` is replaced.
        # If we're looking at a table that's already a linkage component (i.e., this is a linkage that's been sliced out of a component table
        if component_class in Linkage.get_subclasses():
            linkages_in_dataframe = suffixes
            linkages = data.drop_duplicates(subset=["name", "scenario"]).copy()
            linkages["linkage"] = component_class.__name__
            linkages[["component_from", "component_to"]] = linkages["name"].str.split(", ", expand=True)
            linkages = linkages[["linkage", "component_from", "component_to", "scenario"]]
            linkages_for_linkages_csv.append(linkages)
        else:
            linkages_in_dataframe = data.loc[
                data["attribute"].str.contains(r"|".join([rf"\.{suffix}" for suffix in suffixes]), regex=True),
                "attribute",
            ].unique()

            linkages = data.loc[data["attribute"].isin(linkages_in_dataframe), :].copy()

            if not linkages.empty:
                linkage_keys = linkages["attribute"].str.split(".", expand=True)
                linkages["linkage"] = linkage_keys.iloc[:, 0]

                for suffix in suffixes:
                    linkages[f"component_{suffix}"] = np.where(
                        linkage_keys.iloc[:, 1] == suffix, linkages["value"], linkages["name"]
                    )

                linkages = linkages[["linkage", "component_from", "component_to", "scenario"]]
                linkages_for_linkages_csv.append(linkages)

            # Remove linkage attributes from dataframe
            data = data.loc[~data["attribute"].isin(linkages_in_dataframe), :]

        return linkages_for_linkages_csv, data

    def _format_attributes_dataframe(self, data):
        data = data.dropna(how="all").melt(
            id_vars=[col for col in data.columns if col[0] in ["name", "scenarios"]],
            ignore_index=True,
        )
        data.columns = ["name", "scenario", "attribute", "timestamp", "value"]
        data = data.loc[~data["attribute"].isin(["to", "from"]), :]
        data = data[["name", "attribute", "timestamp", "value", "scenario"]]
        data = data.dropna(subset=["name", "scenario"], how="all")

        # Coerce the timestamps to months or modeled year, and make the rest None
        data["timestamp"] = data["timestamp"].apply(lambda cell: _timestamp_column_maker(cell))

        # Drop empty data
        data = data.dropna(subset=["attribute", "value"])
        return data


def _timestamp_column_maker(cell):
    """Convert table headers that have a month (in %b format) or modeled year (in %YS format) to timestamp."""
    months = tuple(pd.date_range(start="1/1/2000", periods=12, freq="MS").strftime("%b").values)
    years = tuple(f"{year}" for year in range(2000, 2051))

    if cell.startswith(months):
        return pd.to_datetime(cell.split(" ")[0], format="%b", errors="coerce").replace(year=1900)
    elif cell.startswith(years):
        return pd.to_datetime(cell.split(" ")[0], format="%Y", errors="coerce")
    else:
        return None


if __name__ == "__main__":
    ScenarioTool.from_template(
        schema_file=UPath(__file__).parents[2] / "unified-test-case.yml", add_doc_hyperlinks=False
    )
