import os
import pathlib
import textwrap
import typing
from typing import Tuple

import pandas as pd
import pydantic
from loguru import logger

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.utils.pandas_utils import compare_dataframes
from new_modeling_toolkit.core.utils.pyomo_utils import get_index_labels
from new_modeling_toolkit.core.utils.xlwings import ExcelApiCalls


class ThreeWayLinkage(component.Component):
    """
    A generalized representation of all sorts of connection between either three component instances component instances,
    or three different instances of the same class.
    By definition and for convenience, the linkage has to be one-directional, even in reality this directionality might not mean much.

    Note that this linkage type should only be used when chained Linkages do not suffice. A specific use case for this
    linkage type is controlling fuel switching within a given EnergyDemandSubsector instance. Such fuel switching is
    likely to be idiosyncratic to the instance. An example would be natural gas to hydrogen fuel switching within two
    industrial subsectors. One subsector may switch to entirely to hydrogen, while one might switch only 5% of
    natural gas demand. Such a linkage enables control of fuel switching extent within each subsector without a need
    for extensive preprocessing.
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################
    _instances: typing.ClassVar = {}
    _component_type_1: typing.ClassVar = None
    _component_type_2: typing.ClassVar = None
    _component_type_3: typing.ClassVar = None
    _attribute_to_announce: typing.ClassVar = (
        None  # This is the component to which the linkage is announced in host components
    )
    _class_descriptor: typing.ClassVar = ""  # This is the name for printing the info message

    instance_1: component.Component | None
    instance_2: component.Component | None
    instance_3: component.Component | None

    # Filename attributes
    SAVE_PATH: typing.ClassVar = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __eq__(self, other):
        if not isinstance(other, ThreeWayLinkage):
            equals = False
        else:
            equals = (
                type(self) == type(other)
                and self.name == other.name
                and self._component_type_1 == other._component_type_1
                and self._component_type_2 == other._component_type_2
                and self._component_type_3 == other._component_type_3
                and id(self.instance_1) == id(other.instance_1)
                and id(self.instance_2) == id(other.instance_2)
                and id(self.instance_3) == id(other.instance_3)
            )

        return equals

    @classmethod
    def from_dir(
        cls,
        dir_path: os.PathLike,
        linkage_pairs: list[tuple[str, str, str]],
        components_dict: dict[str, component.Component],
        scenarios: list = [],
    ):
        """Create Linkage instances based on prescribed CSV files.

        This method relies on one class attribute:
            SAVE_PATH: Optional filename for static & dynamic attributes of the Linkage instance

        Args:
            dir_path: Path to CSV file
            instances_1: Dict of Component instances to reference in linkage.
            instances_2: Dict of Component instances to reference in linkage.
            instances_3: Dict of Component instances to reference in linkage.

        """
        # TODO (5/13): from_csv shares similarities with Component.from_csv...maybe want to generalize both later
        # Read in SAVE_PATH data as needed

        data = {}
        if cls.SAVE_PATH is not None:
            # Find all time series type attributes
            timeseries_attrs = {
                attr: cls.get_field_type(field_info=field_settings)[0]
                for attr, field_settings in cls.model_fields.items()
                if cls.field_is_timeseries(field_info=field_settings)
            }

            # Read in CSV file
            input_df = pd.read_csv(pathlib.Path(dir_path) / cls.SAVE_PATH)
            if "scenario" in input_df.columns:
                input_df["scenario"] = input_df["scenario"].fillna("__base__")
                input_df["scenario"] = pd.Categorical(input_df["scenario"], ["__base__"] + scenarios)
                input_df = input_df.sort_values("scenario").dropna(subset=["scenario"])
            linkage_attributes = input_df.groupby(["component_1", "component_2", "component_3"])

            # TODO (6/8): Check for duplicate/nonunique inputs
            # Populate nested dict
            for name, group in linkage_attributes:
                # Parse "static" attributes
                static_attrs = group.loc[
                    group["attribute"].isin(timeseries_attrs) == False,  # noqa
                    ["attribute", "value"],
                ].set_index(["attribute"])
                # get highest priority scenario
                static_attrs = static_attrs.groupby(static_attrs.index).last()
                if len(static_attrs) == 1:
                    static_attrs = static_attrs.to_dict()["value"]
                else:
                    static_attrs = static_attrs.squeeze().to_dict()
                data.update({name: static_attrs})

                # Parse "dynamic" attributes
                ts_df = group.loc[group["attribute"].isin(timeseries_attrs), :].copy(deep=True)
                ts_df.loc[:, "timestamp"] = pd.to_datetime(ts_df["timestamp"], infer_datetime_format=True)

                ts_attrs = {}
                for attr in ts_df["attribute"].unique():
                    ts_slice = ts_df.loc[ts_df["attribute"] == attr, ["timestamp", "value"]].set_index(["timestamp"])
                    # Get last instance of any duplicate values (for scenario tagging)
                    ts_slice = ts_slice.groupby(ts_slice.index).last()
                    if len(ts_slice) == 1:
                        ts_data = ts_slice.to_dict()["value"]
                    else:
                        ts_data = ts_slice.squeeze()
                    ts_attrs.update({attr: timeseries_attrs[attr](name=f"{name}:{attr}", data=ts_data)})
                data[name].update(ts_attrs)

        constructed_linkages = []
        unmatched_linkages = []
        for _, name_1, name_2, name_3 in linkage_pairs[["component_1", "component_2", "component_3"]].itertuples():
            # obtain the linked inst from and to from the components dictionary
            instance_1 = components_dict.get(name_1, None)
            instance_2 = components_dict.get(name_2, None)
            instance_3 = components_dict.get(name_3, None)
            if instance_1 is None or instance_2 is None or instance_3 is None:
                unmatched_linkages += [f"{cls.__name__}({name_1}, {name_2}, {name_3})"]
            else:
                attributes = data.get((name_1, name_2, name_3), {})

                # instantiating the linkage instance based on linked instances and attributes.
                linkage_inst = cls(
                    name=(name_1, name_2, name_3),
                    instance_1=instance_1,
                    instance_2=instance_2,
                    instance_3=instance_3,
                    **attributes,
                )
                constructed_linkages.append(linkage_inst)

        if len(unmatched_linkages) > 0:
            logger.debug(
                f"The following three-way linkages were not loaded (could not find corresponding components in system):"
                f"\n{unmatched_linkages}"
            )

        return constructed_linkages

    def announce_linkage_to_instances(self):
        """Iterate through all linkages in ThreeWayLinkages._instances to append instances as attributes to mapped instances.

        In other words, if we have:
            s = EnergyDemandSubsector()
            f1 = Fuel()
            f2 = Fuel()
            three_way_linkage = ThreeWayLinkage(instance_1=s, instance_2=f1, instance_3=f2)

        This method will:
            - Append s.three_way_linkage_attribute = {(f1.name,f2.name):three_way_linkage}
            - Append f1.three_way_linkage_attribute = {(s.name,f2.name):three_way_linkage}
            - Append f2.three_way_linkage_attribute = {(s.name,f1.name):three_way_linkage}

        So that it's easy to find the necessary attributes from linked instances
        (e.g., fuel switching from one final fuel to another within and energy-only subsector in PATHWAYS)

        Note that three-way linkages as attributes under the components they are linking are denoted by a tuple of
        strings. Further, the attribute name itself cannot be cleanly mapped back to a single instance of a Component
        subclass because linked components may not be of the same class.
        """

        # print(linkage_type, linkage)
        # Unpack the tuple
        name_1, name_2, name_3 = self.name
        # instance to look at, attribute to look at & append opposing component instance, name of opposing component instance
        linkage_tuple = [
            (
                self.instance_3,
                self._attribute_to_announce,
                (name_1, name_2),
            ),
            (
                self.instance_2,
                self._attribute_to_announce,
                (name_1, name_3),
            ),
            (
                self.instance_1,
                self._attribute_to_announce,
                (name_2, name_3),
            ),
        ]
        # TODO (2021-11-16): Related to #380, can simplify this (if default linkage attribute is {} instead of None)
        for instance, attr, name in linkage_tuple:
            if attr is not None:
                if getattr(instance, attr) is None:
                    # Create a new dict
                    instance.__dict__[attr] = {name: self}
                else:
                    # Remove any string keys from json load, will be replaced by .update below
                    instance.__dict__[attr] = {
                        k: v for k, v in instance.__dict__[attr].items() if not isinstance(k, str)
                    }
                    # Update the dict with additional values
                    instance.__dict__[attr].update({name: self})

    def copy(self):
        return self.model_copy()

    @classmethod
    def to_excel(cls, *, anchor_range, excel_api: ExcelApiCalls, **kwargs):
        """Small wrapper around Component.to_excel() because for now linkages need a formula to construct their name."""
        rows_to_add, columns_to_add, table_name = super().to_excel(
            anchor_range=anchor_range, excel_api=excel_api, **kwargs
        )

        # Add formula for linkage name
        name_column = anchor_range.sheet.range(f"{table_name}[Name]")
        excel_api.set_cell_style(name_column, excel_api.styles(name_column.sheet.book, "Calculation"))
        name_column.value = f'=TEXTJOIN(", ", TRUE, {table_name}[@[Instance 1]:[Instance 3]])'

        return rows_to_add, columns_to_add, table_name

    @classmethod
    def dfs_to_csv(
        cls,
        *,
        instances: pd.DataFrame,
        wb: "Book",
        dir_str: "DirStructure",
        compare_files: bool = True,
        dry_run: bool = False,
    ) -> None:
        """Save DataFrame into (separate) component CSV files."""
        save_path = dir_str.data_interim_dir / "three_way_linkages"
        save_path.mkdir(parents=True, exist_ok=True)

        # Split the name into "instance_1", "instance_2", "instance_3" (assumes that the name column is a formula)
        instances = instances.loc[~instances["attribute"].isin(["instance_1", "instance_2", "instance_3"]), :]
        if instances.empty:
            return
        id = instances["name"].str.split(", ", expand=True)
        id.columns = ["instance_1", "instance_2", "instance_3"]
        instances = pd.concat([instances.drop("name", axis=1), id], axis=1)

        # Reorder columns
        instances.columns = ["attribute", "timestamp", "value", "scenario", "component_1", "component_2", "component_3"]
        instances = instances[
            ["component_1", "component_2", "component_3", "attribute", "timestamp", "value", "scenario"]
        ]

        if (
            (save_path / f"{cls.SAVE_PATH}").exists()
            and os.stat(save_path / f"{cls.SAVE_PATH}").st_size > 0
            and compare_files
        ):
            previous_df = pd.read_csv(
                save_path / f"{cls.SAVE_PATH}", parse_dates=["timestamp"], infer_datetime_format=True
            )
            try:
                comparison = compare_dataframes(
                    previous=previous_df,
                    new=instances,
                    indices=["component_1", "component_2", "component_3", "attribute", "timestamp", "scenario"],
                    column_to_compare="value",
                )

                if not comparison.empty:
                    comparison = textwrap.indent(comparison.to_string(), " > ")
                    logger.debug(f'│ ├─ Differences in {save_path / f"{cls.SAVE_PATH}"}:\n{comparison}')
            except ValueError:
                logger.error(f'Could not compare CSV files: {save_path / f"{cls.SAVE_PATH}"}.csv')

        if not dry_run:
            instances.to_csv(save_path / f"{cls.SAVE_PATH}", index=False)
            wb.app.status_bar = f"Writing {cls.__name__}"

##### Subclasses #####
class SectorCandidateFuelBlending(ThreeWayLinkage):
    """
    Three-way linkage used to set candidate fuel to final fuel blending by sector.
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################
    _class_descriptor = "sector-specific candidate fuel to final fuel linkage"
    _attribute_to_announce = "sector_candidate_fuel_blending"
    _component_type_1 = "sectors"
    _component_type_2 = "candidate_fuels"
    _component_type_3 = "final_fuels"
    SAVE_PATH = "sector_candidate_fuel_blending.csv"

    ###################
    # INSTANCE FIELDS #
    ###################

    blend_override: typing.Optional[ts.FractionalTimeseries] = pydantic.Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
    )



class CustomConstraintLinkage(ThreeWayLinkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "component → linkage"
    _component_type_1 = "custom_constraints_rhs"
    _component_type_2 = "custom_constraints_lhs"
    _component_type_3 = "component"
    _attribute_to_announce = "custom_constraints"

    instance_1: component.Component | None = pydantic.Field(..., title="Constraint RHS")
    instance_2: component.Component | None = pydantic.Field(..., title="Constraint LHS")
    instance_3: component.Component | None = pydantic.Field(..., title="Component to Constrain")

    @classmethod
    def to_excel(cls, *, anchor_range, excel_api: ExcelApiCalls, **kwargs):
        """Since instances 1-3 have different names in table headers, need a custom `to_excel` method for custom constraints."""
        rows_to_add, columns_to_add, table_name = super().to_excel(
            anchor_range=anchor_range, excel_api=excel_api, **kwargs
        )

        # Add formula for linkage name
        name_column = anchor_range.sheet.range(f"{table_name}[Name]")
        excel_api.set_cell_style(name_column, excel_api.styles(name_column.sheet.book, "Calculation"))
        name_column.value = f'=TEXTJOIN(", ", TRUE, {table_name}[@[Constraint RHS]:[Component to Constrain]])'

        return rows_to_add, columns_to_add, table_name

    @property
    def rhs(self):
        """

        Returns: Linked instance_1 as the RHS of the custom constraint

        """
        return self.instance_1

    @property
    def lhs_instance(self):
        """

        Returns: Linked instance 2 as a LHS component of the custom constraint

        """
        return self.instance_2

    @property
    def linked_component(self):
        """

        Returns: Linked instance 3 as the component to constraint of the custom constraint

        """
        return self.instance_3

    @property
    def pyomo_component(self):
        """

        Returns: pyomo variable from the component formulation block

        """
        return getattr(self.linked_component.formulation_block, self.lhs_instance.pyomo_component_name)

    @property
    def variable_index(self) -> list:
        """

        Returns: Index labels for the pyomo variable being constrained. Ex: if the variable is index hourly, this will return ["MODELED_YEARS", "DISPATCH_WINDOWS", "TIMESTAMPS"]

        """
        return get_index_labels(self.pyomo_component)

    @property
    def is_hourly(self):
        """
        Bool. Assumes a variable must be either hourly or annually indexed.
        Returns: True if index includes hourly timestamps.

        """
        return {"MODELED_YEARS", "DISPATCH_WINDOWS", "TIMESTAMPS"}.issubset(self.variable_index)

    @property
    def is_annual(self):
        """
        Bool. Assumes a variable must be either hourly or annually indexed.
        Returns: True if variable index does not include hourly timestamps.

        """
        return not self.is_hourly

    def return_valid_index(self, index: Tuple[pd.Timestamp]):
        """
        Return index of variable to constrain

        Args:
            index: [modeled_year] for annual only or [modeled_year, dispatch_window, timestamp] for hourly

        Returns: (additional index str, modeled year [,dispatch windows, timestamp if hourly constraint],)

        """
        if self.is_annual:
            # if constraint is annual only, use only model year to index the variable
            new_index = index[0]
        else:
            new_index = index

        if self.lhs_instance.additional_index is not None:
            # if an additional index is present for the LHS component, append this to the front of the index
            return (
                self.lhs_instance.additional_index,
                new_index,
            )
        else:
            return new_index

    def validate_custom_constraint_linkage(self):
        assert self.linked_component is not None
        assert (
            self.linked_component.formulation_block is not None
        ), f"Formulation block has not been constructed for {self.linked_component.name}"
        assert (
            getattr(self.linked_component.formulation_block, self.lhs_instance.pyomo_component_name, None) is not None
        ), f"{self.lhs_instance.pyomo_component_name} is not a valid variable name for {self.linked_component.name}"
        assert self.is_annual or self.is_hourly, f"Error constructing {self.name}"
