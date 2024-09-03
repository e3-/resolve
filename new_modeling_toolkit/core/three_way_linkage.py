import os
import pathlib
import typing

import pandas as pd
import pydantic
from loguru import logger

from new_modeling_toolkit import get_units
from new_modeling_toolkit.core import component
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.utils.core_utils import timer


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
    __slots__ = (
        "_instance_1",
        "_instance_2",
        "_instance_3",
    )
    # Filename attributes
    _attribute_file: typing.ClassVar = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Add component instances to __slots__ attributes
        for k in ["_instance_1", "_instance_2", "_instance_3"]:
            object.__setattr__(self, k, kwargs[k])

        # Append new instance to the `_instances` class attribute
        if self.__class__.__name__ not in ThreeWayLinkage._instances.keys():
            ThreeWayLinkage._instances.update({self.__class__.__name__: [self]})
        else:
            ThreeWayLinkage._instances[self.__class__.__name__].append(self)

    @classmethod
    def from_dir(
        cls,
        dir_path: os.PathLike,
        linkage_pairs: list[tuple[str, str, str]],
        components_dict: dict,
        scenarios: list = [],
    ):
        """Create Linkage instances based on prescribed CSV files.

        This method relies on one class attribute:
            _attribute_file: Optional filename for static & dynamic attributes of the Linkage instance

        Args:
            dir_path: Path to CSV file
            instances_1: Dict of Component instances to reference in linkage.
            instances_2: Dict of Component instances to reference in linkage.
            instances_3: Dict of Component instances to reference in linkage.

        """
        # TODO (5/13): from_csv shares similarities with Component.from_csv...maybe want to generalize both later
        # Read in _attribute_file data as needed

        data = {}
        if cls._attribute_file is not None:
            # Find all time series type attributes
            timeseries_attrs = [
                attr
                for attr, field_settings in cls.__fields__.items()
                if field_settings.type_ in ts.Timeseries.__subclasses__()
            ]

            # Read in CSV file
            input_df = pd.read_csv(pathlib.Path(dir_path) / cls._attribute_file)
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
                    ts_attrs.update({attr: ts.Timeseries(name=f"{name}:{attr}", data=ts_data)})
                data[name].update(ts_attrs)

        for name_1, name_2, name_3 in linkage_pairs:
            # For All to policy class the component_type from is an input, for all the other classes it is a class
            # level static attrs
            component_type_1 = cls._component_type_1
            component_type_2 = cls._component_type_2
            component_type_3 = cls._component_type_3

            # obtain the linked inst from and to from the components dictionary
            instance_1 = components_dict[component_type_1][name_1]
            instance_2 = components_dict[component_type_2][name_2]
            instance_3 = components_dict[component_type_3][name_3]
            attributes = data.get((name_1, name_2, name_3), {})

            # instantiating the linkage instance based on linked instances and attributes.
            linkage_inst = cls(
                name=(name_1, name_2, name_3),
                _instance_1=instance_1,
                _instance_2=instance_2,
                _instance_3=instance_3,
                **attributes,
            )

            # This ensure _component_type_1 is correct.
            linkage_inst._component_type_1 = component_type_1

    @classmethod
    @timer
    def announce_linkage_to_instances(cls):
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
        for linkage_type, linkage_instances in cls._instances.items():
            for linkage in linkage_instances:
                logger.debug(
                    f"Announcing linkage between '{linkage._instance_1.name}', '{linkage._instance_2.name}', '{linkage._instance_3.name}'"
                )
                # print(linkage_type, linkage)
                # Unpack the tuple
                name_1, name_2, name_3 = linkage.name
                # instance to look at, attribute to look at & append opposing component instance, name of opposing component instance
                linkage_tuple = [
                    (
                        linkage._instance_3,
                        linkage._attribute_to_announce,
                        (name_1, name_2),
                    ),
                    (
                        linkage._instance_2,
                        linkage._attribute_to_announce,
                        (name_1, name_3),
                    ),
                    (
                        linkage._instance_1,
                        linkage._attribute_to_announce,
                        (name_2, name_3),
                    ),
                ]
                # TODO (2021-11-16): Related to #380, can simplify this (if default linkage attribute is {} instead of None)
                for instance, attr, name in linkage_tuple:
                    if attr is not None:
                        if getattr(instance, attr) is None:
                            # Create a new dict
                            instance.__dict__[attr] = {name: linkage}
                        else:
                            # Update the dict with additional values
                            instance.__dict__[attr].update({name: linkage})

    @classmethod
    def save_instance_attributes_csvs(cls, wb, data: pd.DataFrame, save_path: pathlib.Path, overwrite: bool = True):
        """Save DataFrame in ``attributes.csv`` format, splitting DataFrame into separate CSVs for each instance.
        This method is a variation on ``Component.save_instance_attributes_csvs`` because:
            1. ``Linkage`` instances are saved in the same CSV file; whereas ``Components`` have separate ``attributes.csv`` files for each instance.
            2. ``Linkage`` instances are indexed by the names of the components that are linked together.
        Args:
            wb: An ``xlwings`` workbook (only used to method prints a progress message)
            df: Combined DataFrame in "long" ``attributes.csv`` format (see ``cls.get_data_from_xlwings``).
            save_folder: Path to folder that will hold CSV files.
            overwrite: Whether this method should overwrite an existing attributes.csv file. Otherwise, will append unique values to existing file.
                # TODO 2022-05-05: Add this overwrite feature
        Returns:
        """
        data = (
            data.reset_index()
            .dropna(subset=["value"])
            .rename(
                columns={
                    "level_0": "component_1",
                    "level_1": "component_2",
                    "level_2": "component_3",
                    "level_3": "scenario",
                }
            )
        )[["component_1", "component_2", "component_3", "timestamp", "attribute", "value", "scenario"]]

        wb.app.status_bar = f"Writing {cls.__name__}"

        save_path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(save_path, index=False)


##### Subclasses #####


class EnergyDemandSubsectorFuelSwitching(ThreeWayLinkage):
    """
    Three-way linkage used to control the extent, efficiency, and cost of fuel switching within an EnergyDemandSubsector
    instance. Fuel efficiency is applied after fuel switching
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################
    _class_descriptor = "energy-demand-subsector-specific final fuel to final fuel switching"
    _attribute_to_announce = "fuel_switchings"
    _component_type_1 = "energy_demand_subsectors"
    _component_type_2 = "final_fuels"
    _component_type_3 = "final_fuels"
    _attribute_file = "energy_demand_subsectors_fuel_switching.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    conversion_fraction: typing.Optional[ts.FractionalTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("conversion_fraction"),
    )
    conversion_efficiency: typing.Optional[ts.FractionalTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("conversion_efficiency"),
    )
    conversion_cost: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("conversion_cost"),
    )

    # attributes that will be set during pathways calculations
    out_fuel_switching_cost: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("out_fuel_switching_cost"),
    )


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
    _attribute_file = "sector_candidate_fuel_blending.csv"

    ###################
    # INSTANCE FIELDS #
    ###################

    blend_override: typing.Optional[ts.FractionalTimeseries] = pydantic.Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
    )


class EnergyDemandSubsectorToFinalFuelToCCSPlant(ThreeWayLinkage):
    """
    Three-way linkage used to set candidate fuel to final fuel blending by sector.
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################
    _class_descriptor = (
        "three way linkage from energy demand subsector to final fuel to ccs plant (used for industry ccs)"
    )
    _attribute_to_announce = "energy_demand_subsector_to_final_fuel_to_ccs_plant"
    _component_type_1 = "energy_demand_subsectors"
    _component_type_2 = "final_fuels"
    _component_type_3 = "ccs_plants"
    _attribute_file = "energy_demand_subsector_to_final_fuel_to_ccs_plant.csv"

    ###################
    # INSTANCE FIELDS #
    ###################

    ccs_application_percentage: typing.Optional[ts.FractionalTimeseries] = pydantic.Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        description="percentage of gross emissions to capture",
    )


if __name__ == "__main__":
    from new_modeling_toolkit.common import energy_demand_subsector
    from new_modeling_toolkit.common import fuel, dir_str

    final_fuels = fuel.FinalFuel.from_dir(dir_str.data_interim_dir / "final_fuels")
    energy_demand_subsectors = energy_demand_subsector.EnergyDemandSubsector.from_dir(
        dir_str.data_interim_dir / "energy_demand_subsectors"
    )

    eds = energy_demand_subsectors["CA_Industry_Agriculture"]
    f1 = final_fuels["Diesel"]
    f2 = final_fuels["Electricity"]

    three_way_linkage = EnergyDemandSubsectorFuelSwitching(
        name="test three-way linkage",
        _instance_1=eds,
        _instance_2=f1,
        _instance_3=f2,
    )
