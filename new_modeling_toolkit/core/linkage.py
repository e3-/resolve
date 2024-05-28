import enum
import os
import pathlib
import typing
from typing import List
from typing import Optional

import pandas as pd
import pydantic
from loguru import logger
from tqdm import tqdm

from new_modeling_toolkit import get_units
from new_modeling_toolkit.core import component
from new_modeling_toolkit.core.custom_model import convert_str_float_to_int
from new_modeling_toolkit.core.temporal import timeseries as ts


@enum.unique
class LinkageRelationshipType(enum.Enum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class Linkage(component.Component):
    # TODO: Specific attributes needs to be define for linkages that carries doubled-indexed information
    """
    A generalized representation of all sorts of connection between either different component instances, or different
    instances of the same class.
    By definition and for convenience, the linkage has to be one-directional, even in reality this directionality might not mean much
    """
    # TODO (5/3): Could use class attributes like the ones below to validate whether linkages should be 1-to-1, 1-to-many, etc. in announce_linkage_to_instances method as it is updating the dicts
    # TODO (5/3): Make it so that some linkages don't have to be dicts (related to above)
    # is_exclusive_in_input = False
    # is_exclusive_in_output = False
    # is_complete_in_input = False
    # is_complete_in_output = False

    ####################
    # CLASS ATTRIBUTES #
    ####################

    _RELATIONSHIP_TYPE: LinkageRelationshipType

    _instances: typing.ClassVar = {}
    _component_type_from: typing.ClassVar = None
    _component_type_to: typing.ClassVar = None
    _class_descriptor: typing.ClassVar = ""  # This is the name for printing the info message
    _instance_from: component.Component
    _instance_to: component.Component
    # Filename attributes
    _attribute_file: typing.ClassVar = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Append new instance to the `_instances` class attribute
        if self.__class__.__name__ not in Linkage._instances.keys():
            Linkage._instances.update({self.__class__.__name__: [self]})
        else:
            Linkage._instances[self.__class__.__name__].append(self)

    def dict(self, **kwargs):
        """Need to exclude `_instance_from`, `_instance_to` attributes to avoid recursion error when saving to JSON."""
        attrs_to_exclude = {"attr_path", "_instance_from", "_instance_to", "_component_type_from", "_component_type_to"}

        dct = super(Linkage, self).dict(exclude=attrs_to_exclude, exclude_defaults=True, exclude_none=True)

        return dct

    @classmethod
    def _filter_scenarios(cls, linkages_df: pd.DataFrame, scenarios: List[str], filepath: pathlib.Path) -> pd.DataFrame:
        if cls._RELATIONSHIP_TYPE == LinkageRelationshipType.MANY_TO_ONE:
            group_columns = ["component_from"]
        elif (
            cls._RELATIONSHIP_TYPE == LinkageRelationshipType.MANY_TO_MANY
            or cls._RELATIONSHIP_TYPE == LinkageRelationshipType.ONE_TO_ONE
        ):
            group_columns = ["component_from", "component_to"]
        elif cls._RELATIONSHIP_TYPE == LinkageRelationshipType.ONE_TO_MANY:
            group_columns = ["component_to"]
        else:
            raise NotImplementedError(
                f"Linkage._filter_scenarios() method does not have logic implemented for the `{cls._RELATIONSHIP_TYPE}`"
                f" relationship type"
            )
        grouped_linkages_df = linkages_df.groupby(group_columns, as_index=False, group_keys=False)
        if "attribute" in linkages_df.columns:
            filtered_linkages_df = grouped_linkages_df.apply(
                lambda frame: cls._filter_highest_scenario(
                    filename=filepath, input_df=frame.set_index(["attribute", "timestamp"]), scenarios=scenarios
                ).reset_index(drop=False)
            )
        else:
            filtered_linkages_df = grouped_linkages_df.apply(
                lambda frame: cls._filter_highest_scenario(
                    filename=filepath, input_df=frame.set_index(group_columns), scenarios=scenarios
                ).reset_index(drop=False)
            )

        return filtered_linkages_df

    @classmethod
    def from_dir(
        cls,
        dir_path: os.PathLike,
        linkages_df: pd.DataFrame,
        components_dict: dict,
        linkages_csv_path: pathlib.Path,
        scenarios: list = [],
    ):
        """Create Linkage instances based on prescribed CSV files.

        This method relies on one class attribute:
            _attribute_file: Optional filename for static & dynamic attributes of the Linkage instance

        Args:
            dir_path: Path to CSV file
            instances_from: Dict of Component instances to reference in linkage.
            instances_to: Dict of Component instances to reference in linkage.

        """
        filtered_linkages_df = cls._filter_scenarios(
            linkages_df=linkages_df, scenarios=scenarios, filepath=linkages_csv_path
        )
        linkage_pairs = list(
            filtered_linkages_df.loc[:, ["component_from", "component_to"]].itertuples(index=False, name=None)
        )

        # TODO (5/13): from_csv shares similarities with Component.from_csv...maybe want to generalize both later
        # Read in _attribute_file data as needed
        linkage_attributes = None
        if cls._attribute_file is not None:  # Read in CSV attributes file if it exists
            input_df = pd.read_csv(pathlib.Path(dir_path) / cls._attribute_file)
            linkage_attributes = cls._filter_scenarios(
                linkages_df=input_df, scenarios=scenarios, filepath=pathlib.Path(dir_path) / cls._attribute_file
            )
            linkage_attributes = linkage_attributes.groupby(["component_from", "component_to"])

        # Construct linkage instances
        unmatched_linkages = []
        for name_from, name_to in tqdm(
            linkage_pairs,
            desc=f"Loading {cls.__name__}".rjust(32),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            # For `AllToPolicy` class the component_type from is an input, for all the other classes it is a class
            # level static attrs
            if cls == AllToPolicy:
                component_type_from = find_component_type(components_dict, name_from)
            else:
                component_type_from = cls._component_type_from
            component_type_to = cls._component_type_to

            # obtain the linked inst from and to from the components dictionary
            instance_from = (
                components_dict[component_type_from].get(name_from, None) if component_type_from is not None else None
            )
            instance_to = components_dict[component_type_to].get(name_to, None)

            if instance_from is None or instance_to is None:
                unmatched_linkages += [f"{cls.__name__}({name_from}, {name_to})"]
            else:
                if linkage_attributes is None or (name_from, name_to) not in linkage_attributes.groups:
                    linkage_instance = cls(
                        name=(name_from, name_to), _instance_from=instance_from, _instance_to=instance_to
                    )
                else:
                    _, linkage_instance = cls._parse_vintages(
                        filename=pathlib.Path(dir_path) / cls._attribute_file,
                        input_df=linkage_attributes.get_group((name_from, name_to)).drop(
                            columns=["component_from", "component_to"]
                        ),
                        separate_vintages=False,
                        scenarios=scenarios,
                        data={"_instance_from": instance_from, "_instance_to": instance_to},
                        name=(name_from, name_to),
                    ).popitem()

                # This ensures _component_type_from is correct.
                if cls.__name__ == "AllToPolicy" and component_type_from == "assets":
                    linkage_instance._component_type_from = "assets_"
                else:
                    linkage_instance._component_type_from = component_type_from

        if len(unmatched_linkages) > 0:
            logger.warning(
                f"The following linkages were not loaded (could not find corresponding components in system): \n{unmatched_linkages}"
            )

    @classmethod
    def announce_linkage_to_instances(cls):
        """Iterate through all linkages in Linkages._instances to append instances as attributes to mapped instances.

        In other words, if we have:
            r = Resource(name="CCGT", ...)
            f = Fuel(name="natural_gas", ...)
            l = Linkage(instance_from=r, instance_to=f)

        This method will:
            - Append r.fuels = {"natural_gas": f}
            - Append f.resource = {"CCGT": r}

        So that it's easy to find the necessary attributes from linked instances
        (e.g., fuel burn associated with a fuel being burned in a certain resource)
        """
        for linkage_type, linkage_instances in cls._instances.items():
            for linkage in tqdm(
                linkage_instances,
                desc=f"Loading {cls.__name__}".rjust(32),
                bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
            ):
                logger.debug(
                    f"Announcing linkage between '{linkage._instance_from.name}', '{linkage._instance_to.name}'"
                )
                # Unpack the tuple
                name_from, name_to = linkage.name
                # instance to look at, attribute to look at & append opposing component instance, name of opposing component instance
                linkage_tuple = [
                    (linkage._instance_to, linkage._component_type_from, name_from),
                    (linkage._instance_from, linkage._component_type_to, name_to),
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
            .dropna(subset="value")
            .rename(
                columns={
                    "level_0": "component_from",
                    "level_1": "component_to",
                    "level_2": "scenario",
                }
            )
        )[["component_from", "component_to", "timestamp", "attribute", "value", "scenario"]]

        wb.app.status_bar = f"Writing {cls.__name__}"

        save_path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(save_path, index=False)


class HybridStorageResourceToHybridVariableResource(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.ONE_TO_ONE
    _class_descriptor = "hybrid_storage_resources → hybrid_variable_resources"
    _component_type_from = "hybrid_storage_resources"
    _component_type_to = "hybrid_variable_resources"
    _attribute_file = "hybrid_resources.csv"

    interconnection_limit_mw: ts.NumericTimeseries = pydantic.Field(
        default_freq="YS",
        up_method="ffill",
        down_method="average",
    )

    grid_charging_allowed: bool = False


class CandidateFuelToResource(Linkage):
    """Linkage between new_modeling_toolkit.common.fuel.CandidateFuel and new_modeling_toolkit.common.resource.Resource.

    Houses the data related to both resources & candidate fuels (e.g., fuel burn coefficients).
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "candidate fuels → resources"
    _component_type_from = "candidate_fuels"
    _component_type_to = "resources"

    ###################
    # INSTANCE FIELDS #
    ###################
    # TODO (6/8): Need to think about fuel burn formulation. As a stopgap measure, moving fuel burn coefficients
    # to be only on the resource (i.e., a resource's fuel burn slope/intercept are the same for all candidate fuels)


@enum.unique
class IncrementalReserveType(enum.Enum):
    OPERATIONAL_CAPACITY = "operational capacity"
    HOURLY_PROFILE = "hourly profile"


class ResourceToReserve(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "resources → operating reserves"
    _component_type_from = "resources"
    _component_type_to = "reserves"
    _attribute_file = "resources_to_reserves.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    exclusive: bool = True
    dependent_on: str = pydantic.Field(
        "setpoint",
        description="Operating reserves are usually related to a resource's setpoint (i.e., online head/footroom). "
        "Certain resources (e.g., inertia) are only related to online/committed capacity."
        "**Note: RESOLVE cannot currently represent non-spinning reserves.**",
    )
    # TODO (2022-02-21): Non-spinning reserves cannot be represented with these options, since they can also include offline capacity.

    max_fraction_of_capacity: pydantic.condecimal(ge=0, le=1) = pydantic.Field(
        1,
        description="Max % of a resource's online capacity (e.g., committed capacity for unit commitment resources) "
        "that can be used to provide operating reserve.",
    )
    incremental_requirement_annual_scalar: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="first",
        units=get_units("requirement"),
    )
    scalar_type: IncrementalReserveType = IncrementalReserveType.OPERATIONAL_CAPACITY

    incremental_requirement_hourly_scalar: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        None,
        default_freq="H",
        up_method="interpolate",
        down_method="first",
        units=get_units("requirement"),
        alias="incremental_requirement",
    )
    incremental_requirement_hourly_scalar__type: ts.TimeseriesType = ts.TimeseriesType.MODELED_YEAR

    @pydantic.validator("dependent_on")
    def validate_reserve_dependence(cls, dependent_on, values):
        dependent_list = ["setpoint", "commitment"]
        if dependent_on not in dependent_list:
            raise ValueError(
                f"For {cls.__name__} linkage \"{values['name']}\", attribute (`dependent_on`) must be in {dependent_list}"
            )
        return dependent_on


class LoadToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "loads → zones"
    _component_type_from = "loads"
    _component_type_to = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class LoadToReserve(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.ONE_TO_MANY
    _class_descriptor = "loads → reserves"
    _component_type_from = "loads"
    _component_type_to = "reserves"
    _attribute_file = "loads_to_reserves.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    incremental_requirement_hourly_scalar: Optional[ts.FractionalTimeseries] = pydantic.Field(
        default=None,
        default_freq="H",
        up_method="ffill",
        down_method="average",
    )
    incremental_requirement_hourly_scalar__type: ts.TimeseriesType = ts.TimeseriesType.MODELED_YEAR


class ReserveToZone(Linkage):
    """TODO: 2023-08-22: I want to deprecate this class in favor of `LoadToReserve`, but for now keeping for backward compatibility."""

    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "reserves → zones"
    _component_type_from = "reserves"
    _component_type_to = "zones"
    _attribute_file = "reserves_to_zones.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    incremental_requirement_hourly_scalar: Optional[ts.FractionalTimeseries] = pydantic.Field(
        default=None,
        default_freq="H",
        up_method="ffill",
        down_method="average",
        alias="requirement_fraction_of_gross_load",
    )
    incremental_requirement_hourly_scalar__type: ts.TimeseriesType = ts.TimeseriesType.MODELED_YEAR


class ResourceToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "resources → zones"
    _component_type_from = "resources"
    _component_type_to = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class AssetToAssetGroup(Linkage):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _component_type_from = "assets"
    _component_type_to = "asset_groups"


class TrancheToAsset(Linkage):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _component_type_from = "tranches"
    _component_type_to = "assets"


class ResourceToResourceGroup(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "resources → resource groups"
    _component_type_from = "resources"
    _component_type_to = "resource_groups"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class ResourceToOutageDistribution(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "resources → outage distributions"
    _component_type_from = "resources"
    _component_type_to = "outage_distributions"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class ResourceToFuelZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "resources → zones"
    _component_type_from = "resources"
    _component_type_to = "fuel_zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class AssetToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "assets → zones"
    _component_type_from = "assets"
    _component_type_to = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class CandidateFuelToFinalFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "candidate fuels → final fuels"
    _component_type_from = "candidate_fuels"
    _component_type_to = "final_fuels"
    _attribute_file = "candidate_fuels_to_final_fuels.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    blend_limit_fraction: Optional[ts.FractionalTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
    )


class CandidateFuelToPollutant(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "candidate fuels → pollutants"
    _component_type_from = "candidate_fuels"
    _component_type_to = "pollutants"
    _attribute_file = "candidate_fuels_to_pollutants.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    net_emission_factor: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("emission_factor"),
    )

    gross_emission_factor: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("emission_factor"),
    )

    upstream_emission_factor: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("emission_factor"),
    )

    gross_emissions_trajectory_override: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )

    net_emissions_trajectory_override: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )

    upstream_emissions_trajectory_override: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )


class BiomassResourceToCandidateFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "biomass resources → candidate fuels"
    _component_type_from = "biomass_resources"
    _component_type_to = "candidate_fuels"
    _attribute_file = "biomass_resources_to_candidate_fuels.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    conversion_efficiency: ts.NumericTimeseries = pydantic.Field(
        default_freq="YS", up_method="ffill", down_method="annual", units=get_units("conversion_efficiency")
    )
    # note this is the full cost per mmbtu of this fuel pathway
    conversion_cost: ts.NumericTimeseries = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("conversion_cost")
    )


class ElectrolyzerToCandidateFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "electrolyzers → candidate fuels"
    _component_type_from = "electrolyzers"
    _component_type_to = "candidate_fuels"


class FuelZoneToCandidateFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "fuel zones → candidate fuels"
    _component_type_from = "fuel_zones"
    _component_type_to = "candidate_fuels"

    ###################
    # INSTANCE FIELDS #
    ###################


class ElectrolyzerToFuelZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "electrolyzers → fuel zones"
    _component_type_from = "electrolyzers"
    _component_type_to = "fuel_zones"


class ElectrolyzerToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "electrolyzers → zones"
    _component_type_from = "electrolyzers"
    _component_type_to = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class FuelStorageToFuelZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "fuel storages → fuel zones"
    _component_type_from = "fuel_storages"
    _component_type_to = "fuel_zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class FuelStorageToCandidateFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "fuel storages → candidate fuels"
    _component_type_from = "fuel_storages"
    _component_type_to = "candidate_fuels"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class FuelStorageToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "fuel storages → zones"
    _component_type_from = "fuel_storages"
    _component_type_to = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class FuelConversionPlantToFuelZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "fuel conversion plants → fuel zones"
    _component_type_from = "fuel_conversion_plants"
    _component_type_to = "fuel_zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class FuelConversionPlantToCandidateFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "fuel conversion plants → candidate fuels"
    _component_type_from = "fuel_conversion_plants"
    _component_type_to = "candidate_fuels"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class FuelConversionPlantToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "fuel conversion plants → zones"
    _component_type_from = "fuel_conversion_plants"
    _component_type_to = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class FinalFuelToFuelZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "final fuels → fuel zones"
    _component_type_from = "final_fuels"
    _component_type_to = "fuel_zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class ZoneToTransmissionPath(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "zones → transmission paths"
    _component_type_from = "zones"
    _component_type_to = "tx_paths"
    _attribute_file = "zones_to_tx_paths.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    # user should specify the from and to zone of each tx path
    # TODO: do we need a validation so that there are only two zones linked to the same line?
    # TODO: validation to make sure there is only one from_zone for each tx_path etc.
    from_zone: bool = False
    to_zone: bool = False

    @pydantic.root_validator
    def linkage_is_from_zone_xor_to_zone(cls, values):
        """Validate that exactly one of `from_zone` and `to_zone` is set to True."""
        if not values["from_zone"] and not values["to_zone"]:
            raise ValueError(
                f"{cls.__name__} linkage for {values['name']} must have either 'from_zone' or 'to_zone' set to True."
            )
        elif values["from_zone"] and values["to_zone"]:
            raise ValueError(
                f"{cls.__name__} linkage for {values['name']} must have either 'from_zone' or 'to_zone' set to True, but not both."
            )
        else:
            return values


class FuelZoneToFuelTransportation(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "fuel zones → fuel transportations"
    _component_type_from = "fuel_zones"
    _component_type_to = "fuel_transportations"
    _attribute_file = "fuel_zones_to_fuel_transportations.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    # user should specify the from and to zone of each fuel transportation
    # TODO: do we need a validation so that there are only two zones linked to the same line?
    # TODO: validation to make sure there is only one from_zone for each tx_path etc.
    from_zone: bool = False
    to_zone: bool = False

    @pydantic.root_validator
    def linkage_is_from_zone_xor_to_zone(cls, values):
        """Validate that exactly one of `from_zone` and `to_zone` is set to True."""
        if not values["from_zone"] and not values["to_zone"]:
            raise ValueError(
                f"{cls.__name__} linkage for {values['name']} must have either 'from_zone' or 'to_zone' set to True."
            )
        elif values["from_zone"] and values["to_zone"]:
            raise ValueError(
                f"{cls.__name__} linkage for {values['name']} must have either 'from_zone' or 'to_zone' set to True, but not both."
            )
        else:
            return values


class ZoneToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "zones → zones"
    _component_type_to = "subzones"
    _component_type_from = "parent_zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class FuelZoneToElectricZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "fuel zones → electric zones"
    _component_type_to = "fuel_zones"
    _component_type_from = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class FuelTransportationToCandidateFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "fuel transportations → candidate fuels"
    _component_type_from = "fuel_transportations"
    _component_type_to = "candidate_fuels"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


# TODO: Not sure I need to create _instances class attribute every time... In general, there's a lot of boilerplate here.
# TODO: Need to get the "from" and "to" direction consistent


@enum.unique
class DeliverabilityStatus(enum.Enum):
    FULLY_DELIVERABLE = "FCDS"
    ENERGY_ONLY = "EO"
    BOTH = "Both"


class AllToPolicy(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ###################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "anything → policies"
    _component_type_from = ""  # this will be overridden in get_dir
    _component_type_to = "policies"
    # _map_file = "all_to_policies/mapping.csv"
    _attribute_file = "all_to_policies.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    multiplier: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="annual", alias="nqc"
    )
    # TODO: should be pint.Unit but don't know how to do it
    multiplier_unit: typing.Optional[str] = None
    attribute: typing.Optional[str] = None  # attribute in the RESOLVE model
    forward_dir_multiplier: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="annual"
    )  # used when Transmission Path to Policy linkage
    reverse_dir_multiplier: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="annual"
    )  # used when Transmission Path to Policy linkage

    deliverability_status: DeliverabilityStatus = DeliverabilityStatus.BOTH

    # Used when Transmission Path to Policy Linkage
    @pydantic.root_validator
    def validate_single_xor_bidirectional_multiplier(cls, values):
        """Validate that the linkage either has both 'forward_dir_multiplier' & 'reverse_dir_multiplier' defined,
        xor only has 'multiplier' defined. The two types of multipliers shouldn't exist at the same time."""
        # TODO (6/8): This validation could be made easier to meet by defaulting one of the bidirectional multipliers to 0 if not defined.

        if (values["multiplier"] is not None) and (
            values["forward_dir_multiplier"] is not None or values["reverse_dir_multiplier"] is not None
        ):
            raise ValueError(
                f"{cls.__name__} linkage for {values['name']} already has a uniform multiplier defined. "
                f"Forward/Reverse direction multipliers are not allowed when a uniform multiplier has been defined."
            )
        else:
            return values


class FinelFuelToAnnualEmissionsPolicy(AllToPolicy):
    """Temporary subclass only so that final fuels are correctly linked to annual emissions policies."""

    ####################
    # CLASS ATTRIBUTES #
    ###################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "final fuel → annual emissions policy"
    _component_type_from = "final_fuels"
    _component_type_to = "policies"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class AssetToELCC(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "assets → ELCC"
    _component_type_from = "assets"
    _component_type_to = "elcc_surfaces"
    _attribute_file = "assets_to_elcc.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    multiplier: typing.Optional[float] = None
    multiplier_unit: typing.Optional[str] = None
    attribute: typing.Literal["power", "energy"] = "power"
    elcc_axis_index: typing.Optional[int] = None
    elcc_axis_multiplier: typing.Optional[float] = None

    # Convert strings that look like floats to integers for integer fields
    _convert_int = pydantic.validator("elcc_axis_index", allow_reuse=True, pre=True)(convert_str_float_to_int)

    @pydantic.root_validator
    def has_axis_index_if_multiplier(cls, values):
        if values["elcc_axis_multiplier"] is not None:
            assert values["elcc_axis_index"] is not None, (
                "`elcc_axis_multiplier` was specified but `elcc_axis_index` was not. You must specify an "
                "`elcc_axis_index` in order to use an `elcc_axis_multiplier`."
            )

        return values


def find_component_type(components_dict: dict[str, dict[str, component.Component]], instance_name: str):
    """Try to find the component with the given instance_name.

    Args:
        components_dict: Nested dictionary of all System instance components.
            First level of the dict is the name of the component type (class name),
            while dict nested inside holds the various instances of that component type.
        inst_name: The name of the current instance being queried.

    Returns:
        The name of the component type of the current instance under query.

    """
    matching_component_types = [
        component_type
        for component_type, component_dict_one_type in components_dict.items()
        if instance_name in component_dict_one_type.keys()
    ]

    # Warn if no components found or multiple components found (i.e., components with the same name but different types)
    if not matching_component_types:
        err = f"{instance_name} not found in System components"
        logger.exception(err)
        return None
    elif (
        len(matching_component_types) > 1
        and set(matching_component_types) != {"assets", "resources", "plants"}
        and set(matching_component_types) != {"assets", "generic_assets"}
    ):
        logger.debug(
            f"Multiple System components found with name '{instance_name}' in: {matching_component_types}. Using {matching_component_types[0]}"
        )

    # Hacky way to return `assets` as component type as a last resort
    if "resources" in matching_component_types:
        return "resources"
    if "plants" in matching_component_types:
        return "plants"
    if "tx_paths" in matching_component_types:
        return "tx_paths"
    if "assets" in matching_component_types:
        return "assets"
    else:
        return matching_component_types[0]


class DeviceToFinalFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "devices → final fuels"
    _component_type_from = "devices"
    _component_type_to = "final_fuels"
    _attribute_file = "devices_to_final_fuels.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    fuel_share_of_service_demand: typing.Optional[str] = None

    device_efficiency: ts.NumericTimeseries = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("device_efficiency")
    )

    # attributes that will be set during stock rollover calculations
    out_final_energy_demand: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("out_final_energy_demand")
    )


class StockRolloverSubsectorToDevice(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "stock rollover subsectors → devices"
    _component_type_from = "stock_rollover_subsectors"
    _component_type_to = "devices"
    _attribute_file = "stock_rollover_subsectors_to_devices.csv"

    ###################
    # INSTANCE FIELDS #
    ###################


class BuildingShellSubsectorToBuildingShellType(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "building shell subsectors → building shell types"
    _component_type_from = "building_shell_subsectors"
    _component_type_to = "building_shell_types"
    _attribute_file = "building_shell_subsectors_to_building_shell_types.csv"

    ###################
    # INSTANCE FIELDS #
    ###################


class BuildingShellSubsectorToSector(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "building shell subsectors → sectors"
    _component_type_from = "building_shell_subsectors"
    _component_type_to = "sectors"


class EnergyDemandSubsectorToFinalFuel(Linkage):
    """
    Defines the linkage betweeen energy demand subsectors and final fuels. It is used to define the assumed growth
    of fuel demands within a subsector and the extent and cost of efficiency by fuel within a subsector. Note efficiency
    is applied after fuel conversions.
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "energy demand subsectors → final fuels"
    _component_type_from = "energy_demand_subsectors"
    _component_type_to = "final_fuels"
    _attribute_file = "energy_demand_subsectors_to_final_fuels.csv"

    ###################
    # INSTANCE FIELDS #
    ###################

    default_energy_demand_trajectory: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("default_energy_demand_trajectory"),
    )
    efficiency_fraction: typing.Optional[ts.FractionalTimeseries] = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("efficiency_fraction")
    )
    efficiency_cost: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("efficiency_cost")
    )

    # attributes that will be set during stock rollover calculations
    out_final_energy_demand: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("out_final_energy_demand")
    )
    out_efficiency_cost: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("out_efficiency_cost")
    )


class NonEnergySubsectorToPollutant(Linkage):
    """
    Defines the linkage betweeen non energy subsectors and pollutants.
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "non-energy subsectors → pollutants"
    _component_type_from = "non_energy_subsectors"
    _component_type_to = "pollutants"
    _attribute_file = "non_energy_subsectors_to_pollutants.csv"

    ###################
    # INSTANCE FIELDS #
    ###################

    emissions: ts.NumericTimeseries = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("emissions")
    )
    cost: Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("cost")
    )


class NegativeEmissionsTechnologyToPollutant(Linkage):
    """Defines the linkage between NETs and pollutants."""

    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "negative emissions technologies → pollutants"
    _component_type_from = "negative_emissions_technologies"
    _component_type_to = "pollutants"


class ResourceToPollutant(Linkage):
    """
    Defines the linkage between resources and pollutants. Used if emission factors are set on the resource to
    pollutant level rather than the resource to fuel to pollutant level.
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "resources → pollutants"
    _component_type_from = "resources"
    _component_type_to = "pollutants"
    _attribute_file = "resources_to_pollutants.csv"

    emission_factor: ts.NumericTimeseries = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )


class TransmissionPathToPollutant(Linkage):
    """
    Defines the linkage between transmission paths and pollutants. Used to set emission factors for Tx lines.
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "transmission paths → pollutants"
    _component_type_from = "tx_paths"
    _component_type_to = "pollutants"
    _attribute_file = "tx_paths_to_pollutants.csv"

    forward_dir_multiplier: ts.NumericTimeseries = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )
    reverse_dir_multiplier: ts.NumericTimeseries = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )


class DeviceToLoad(Linkage):
    """
    Defines the mapping from a device to a load component. Used to populate load component annual energy with
    outputs of stock rollover.
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "devices → loads"
    _component_type_from = "devices"
    _component_type_to = "loads"
    _attribute_file = "devices_to_loads.csv"

    ###################
    # INSTANCE FIELDS #
    ###################

    # The multiplier is what energy demands from devices are multiplied by to add to the annual_energy_forecast in the
    # linked load component, if applicable. Used for unit conversion. Default value is conversion from MMBTU to MWh.
    multiplier: float = 0.293071


class EnergyDemandSubsectorToLoad(Linkage):
    """
    Defines the mapping from a energy demand subsector to a load component. Used to populate load component
    annual energy with outputs of energy demand calculations.
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "energy_demand_subsectors → loads"
    _component_type_from = "energy_demand_subsectors"
    _component_type_to = "loads"
    _attribute_file = "energy_demand_subsectors_to_loads.csv"

    ###################
    # INSTANCE FIELDS #
    ###################

    # The multiplier is what energy demands from energy demand subsectors are multiplied by to add to the
    # annual_energy_forecast in the linked load component, if applicable. Used for unit conversion.
    # Default value is conversion from MMBTU to MWh.
    multiplier: float = 0.293071


class StockRolloverSubsectorToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "stock rollover subsectors → zones"
    _component_type_from = "stock_rollover_subsectors"
    _component_type_to = "zones"


class EnergyDemandSubsectorToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "energy demand subsectors → zones"
    _component_type_from = "energy_demand_subsectors"
    _component_type_to = "zones"


class NonEnergySubsectorToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "non-energy subsectors → zones"
    _component_type_from = "non_energy_subsectors"
    _component_type_to = "zones"


class StockRolloverSubsectorToSector(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "stock rollover subsectors → sectors"
    _component_type_from = "stock_rollover_subsectors"
    _component_type_to = "sectors"


class EnergyDemandSubsectorToSector(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "energy demand subsectors → sectors"
    _component_type_from = "energy_demand_subsectors"
    _component_type_to = "sectors"


class NonEnergySubsectorToSector(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "non-energy subsectors → sectors"
    _component_type_from = "non_energy_subsectors"
    _component_type_to = "sectors"


class CCSPlantToFinalFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "ccs_plants → final_fuels"
    _component_type_from = "ccs_plants"
    _component_type_to = "final_fuels"
    _attribute_file = "ccs_plants_to_final_fuels.csv"

    ###################
    # INSTANCE FIELDS #
    ###################

    ccs_energy_demand: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        description="Energy demand required to run CCS (in units of MMBtu per metric ton)",
    )

    # attributes that will be set during calculations
    out_final_energy_demand: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("out_final_energy_demand")
    )


class NegativeEmissionsTechnologyToFinalFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "negative_emissions_technologies → final_fuels"
    _component_type_from = "negative_emissions_technologies"
    _component_type_to = "final_fuels"
    _attribute_file = "negative_emissions_technologies_to_final_fuels.csv"

    ###################
    # INSTANCE FIELDS #
    ###################

    energy_demand: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        description="Energy demand required to run NET (in units of MMBtu per metric ton)",
    )

    # attributes that will be set during calculations
    out_final_energy_demand: typing.Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("out_final_energy_demand")
    )


class CCSPlantToPollutant(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "ccs_plants → pollutants"
    _component_type_from = "ccs_plants"
    _component_type_to = "pollutants"


class NonEnergySubsectorToCCSPlant(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "non_energy_subsectors → ccs_plants"
    _component_type_from = "non_energy_subsectors"
    _component_type_to = "ccs_plants"
    _attribute_file = "non_energy_subsectors_to_ccs_plants.csv"

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


class NonEnergySubsectorToEnergyDemandSubsector(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "non_energy_subsectors → energy_demand_subsectors"
    _component_type_from = "non_energy_subsectors"
    _component_type_to = "energy_demand_subsectors"
    _attribute_file = "non_energy_subsectors_to_energy_demand_subsectors.csv"


if __name__ == "__main__":
    from new_modeling_toolkit.core import dir_str, energy_demand_subsector, fuel

    energy_demand_subsectors = energy_demand_subsector.EnergyDemandSubsector.from_dir(
        dir_str.data_interim_dir / "energy_demand_subsectors"
    )
    fuels = fuel.FinalFuel.from_dir(dir_str.data_interim_dir / "final_fuels")

    eds = energy_demand_subsectors["CA_Industry_Agriculture"]
    f = fuels["Diesel"]

    linkage = EnergyDemandSubsectorToFinalFuel(name="test linkage", _instance_from=eds, _instance_to=f)
