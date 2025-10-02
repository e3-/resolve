from __future__ import annotations

import enum
import os
import pathlib
import textwrap
from typing import ClassVar
from typing import List
from typing import Literal
from typing import Optional

import numpy as np
import pandas as pd
import pydantic
from loguru import logger
from pydantic import Field
from tqdm import tqdm
from typing_extensions import Annotated

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core.custom_model import get_units
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.utils.pandas_utils import compare_dataframes
from new_modeling_toolkit.core.utils.xlwings import ExcelApiCalls


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

    _RELATIONSHIP_TYPE: ClassVar[LinkageRelationshipType]

    component_type_from_: str
    component_type_to_: str
    instance_from: component.Component | None = (
        None  # Not ideal, since a linkage should only exist if there are linked instances
    )
    instance_to: component.Component | None = None
    # Filename attributes
    SAVE_PATH: ClassVar[str | None] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __eq__(self, other):
        if not isinstance(other, Linkage):
            equals = False
        else:
            equals = (
                type(self) == type(other)
                and self.name == other.name
                and self.component_type_to_ == other.component_type_to_
                and self.component_type_from_ == other.component_type_from_
                and id(self.instance_from) == id(other.instance_from)
                and id(self.instance_to) == id(other.instance_from)
            )

        return equals

    def dict(self, **kwargs):
        """Need to exclude `instance_from`, `instance_to` attributes to avoid recursion error when saving to JSON."""
        attrs_to_exclude = {"attr_path", "instance_from", "instance_to", "component_type_from_", "component_type_to_"}

        dct = super(Linkage, self).model_dump(exclude=attrs_to_exclude, exclude_defaults=True, exclude_none=True)

        return dct

    @pydantic.field_validator("name")
    def _validate_name_tuple(cls, name):
        if not all([type(name) is tuple, len(name) == 2, all(type(s) is str for s in name)]):
            raise AssertionError("Linkage names must be a tuple of 2 strings")

        return name

    @property
    def name_from(self):
        return self.name[0]

    @property
    def name_to(self):
        return self.name[1]

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
    def to_excel(cls, *, anchor_range, excel_api: ExcelApiCalls, **kwargs):
        """Small wrapper around Component.to_excel() because for now linkages need a formula to construct their name."""
        rows_to_add, columns_to_add, table_name = super().to_excel(
            anchor_range=anchor_range, excel_api=excel_api, **kwargs
        )

        # Add formula for linkage name
        name_column = anchor_range.sheet.range(f"{table_name}[Name]")
        excel_api.set_cell_style(name_column, excel_api.styles(name_column.sheet.book, "Calculation"))
        name_column.value = f'=TEXTJOIN(", ", TRUE, {table_name}[@[Instance From]:[Instance To]])'

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
        save_path = dir_str.data_interim_dir / "linkages"
        save_path.mkdir(parents=True, exist_ok=True)

        # Split the name into `component_from`, `component_to` (assumes that the name column is a formula)
        instances = instances.loc[~instances["attribute"].isin(["instance_from", "instance_to", "to", "from"]), :]
        if instances.empty:
            return None

        id = instances["name"].str.split(", ", expand=True)
        id.columns = ["component_from", "component_to"]
        instances = pd.concat([instances.drop("name", axis=1), id], axis=1, ignore_index=True)

        # Reorder columns
        instances.columns = ["attribute", "timestamp", "value", "scenario", "component_from", "component_to"]
        instances = instances[["component_from", "component_to", "attribute", "timestamp", "value", "scenario"]]

        if (
            (save_path / f"{cls.SAVE_PATH}").exists()
            and os.stat(save_path / f"{cls.SAVE_PATH}").st_size > 0
            and compare_files
        ):
            try:
                previous_df = pd.read_csv(
                    save_path / f"{cls.SAVE_PATH}", parse_dates=["timestamp"], infer_datetime_format=True
                )
                comparison = compare_dataframes(
                    previous=previous_df,
                    new=instances,
                    indices=["component_from", "component_to", "attribute", "timestamp", "scenario"],
                    column_to_compare="value",
                )

                if not comparison.empty:
                    comparison = textwrap.indent(comparison.to_string(), " > ")
                    logger.debug(f'│ ├─ Differences in {save_path / f"{cls.SAVE_PATH}"}:\n{comparison}')
            except:
                logger.error(f'Could not compare CSV files: {save_path / f"{cls.SAVE_PATH}"}.csv')

        if not dry_run:
            instances.to_csv(save_path / f"{cls.SAVE_PATH}", index=False)
            wb.app.status_bar = f"Writing {cls.__name__}"

    @classmethod
    def from_dir(
        cls,
        dir_path: os.PathLike,
        linkages_df: pd.DataFrame,
        components_dict: dict[str, component.Component],
        linkages_csv_path: pathlib.Path,
        scenarios: list = [],
    ):
        """Create Linkage instances based on prescribed CSV files.

        This method relies on one class attribute:
            SAVE_PATH: Optional filename for static & dynamic attributes of the Linkage instance

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
        # Read in SAVE_PATH data as needed
        linkage_attributes = None
        if (
            cls.SAVE_PATH is not None and (pathlib.Path(dir_path) / cls.SAVE_PATH).exists()
        ):  # Read in CSV attributes file if it exists
            input_df = pd.read_csv(pathlib.Path(dir_path) / cls.SAVE_PATH)
            input_df["timestamp"] = input_df["timestamp"].fillna(value="None")
            linkage_attributes = cls._filter_scenarios(
                linkages_df=input_df, scenarios=scenarios, filepath=pathlib.Path(dir_path) / cls.SAVE_PATH
            )
            if len(linkage_attributes) == 0:
                linkage_attributes = None
            else:
                linkage_attributes = linkage_attributes.groupby(["component_from", "component_to"])

        # Construct linkage instances
        constructed_linkages = []
        unmatched_linkages = []
        for name_from, name_to in tqdm(
            linkage_pairs,
            desc=f"Loading {cls.__name__}".rjust(50),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):

            # obtain the linked inst from and to from the components dictionary
            instance_from = components_dict.get(name_from, None)
            instance_to = components_dict.get(name_to, None)

            if instance_from is None or instance_to is None:
                missing_linkage = f"{cls.__name__}({name_from}, {name_to}): missing {name_from if instance_from is None else ' '} {name_to if instance_to is None else ' '}"
                unmatched_linkages += [missing_linkage]

            else:
                if linkage_attributes is None or (name_from, name_to) not in linkage_attributes.groups:
                    linkage_instance = cls(
                        name=(name_from, name_to), instance_from=instance_from, instance_to=instance_to
                    )
                else:
                    linkage_instance = cls.from_dataframe(
                        input_df=linkage_attributes.get_group((name_from, name_to)).drop(
                            columns=["component_from", "component_to"]
                        ),
                        attr_path=pathlib.Path(dir_path) / cls.SAVE_PATH,
                        scenarios=scenarios,
                        data={"instance_from": instance_from, "instance_to": instance_to},
                        name=(name_from, name_to),
                    )

                constructed_linkages.append(linkage_instance)

        if len(unmatched_linkages) > 0:
            formatted_list = "\n\t".join(unmatched_linkages)
            logger.debug(
                f"The following linkages were not loaded (could not find corresponding components in system): \n\t{formatted_list}"
            )

        return constructed_linkages

    def announce_linkage_to_instances(self):
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
        # Unpack the tuple
        # instance to look at, attribute to look at & append opposing component instance, name of opposing component instance
        linkage_tuple = [
            (self.instance_to, self.component_type_from_, self.name_from),
            (self.instance_from, self.component_type_to_, self.name_to),
        ]
        # TODO (2021-11-16): Related to #380, can simplify this (if default linkage attribute is {} instead of None)
        for instance, attr, name in linkage_tuple:
            if attr is not None and attr != "":
                if getattr(instance, attr) is None:
                    # Create a new dict
                    instance.__dict__[attr] = {name: self}
                else:
                    # Update the dict with additional values
                    if attr in instance.__dict__.keys():
                        instance.__dict__[attr].update({name: self})
                    else:
                        instance.__dict__[attr] = {}
                        instance.__dict__[attr].update({name: self})

    def copy(self):
        return self.model_copy()


class HybridStorageResourceToHybridVariableResource(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.ONE_TO_ONE
    _class_descriptor = "hybrid_storage_resources → hybrid_variable_resources"
    component_type_from_: str = "hybrid_storage_resources"
    component_type_to_: str = "hybrid_variable_resources"
    SAVE_PATH = "hybrid_resources.csv"

    interconnection_limit_mw: ts.NumericTimeseries | None = pydantic.Field(
        default=None, default_freq="YS", up_method="ffill", down_method="mean"
    )

    grid_charging_allowed: Optional[bool] = Field(
        False,
        description="If True, hybrid_storage's power_input must not exceed hybrid_variable's power_output.",
    )

    pairing_ratio: Optional[float] = Field(
        None,
        description="If specified, ratio of operational capacity of hybrid_variable to that of hybrid_storage resources. Usually set to 1.",
        ge=0,
    )

    paired_charging_constraint_active_in_year: ts.NumericTimeseries = pydantic.Field(
        description="If 1, the charging constraint is active in the year. If 0, the charging constraint is not active in the year.",
        default_factory=ts.Timeseries.one,
        default_freq="YS",
        up_method="ffill",
        down_method="mean",
    )

    def revalidate(self):
        if any(~self.paired_charging_constraint_active_in_year.data.isin([0, 1])):
            return ValueError(
                f"Values in `paired_charging_constraint_active_in_year` attribute for `{self.__class__.__name__}` "
                f"instance `{self.name}` can only be either 1 (constraint active) or 0 (constraint inactive)."
            )


class CandidateFuelToResource(Linkage):
    """Linkage between new_modeling_toolkit.common.fuel.CandidateFuel and new_modeling_toolkit.common.resource.Resource.

    Houses the data related to both resources & candidate fuels (e.g., fuel burn coefficients).
    """

    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "candidate fuels → resources"
    component_type_from_: str = "candidate_fuels"
    component_type_to_: str = "resources"

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
    component_type_from_: str = "resources"
    component_type_to_: str = "reserves"
    SAVE_PATH = "resources_to_reserves.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    # TODO: Are `exclusive` and `dependent_on` being used?
    exclusive: Annotated[bool, Metadata(default_exclude=True)] = True
    dependent_on: Annotated[str, Metadata(default_exclude=True)] = pydantic.Field(
        "setpoint",
        description="Operating reserves are usually related to a resource's setpoint (i.e., online head/footroom). "
        "Certain resources (e.g., inertia) are only related to online/committed capacity."
        "**Note: RESOLVE cannot currently represent non-spinning reserves.**",
    )
    # TODO (2022-02-21): Non-spinning reserves cannot be represented with these options, since they can also include offline capacity.

    max_fraction_of_capacity: Annotated[float, Field(ge=0, le=1)] = pydantic.Field(
        0,
        description="Max % of a resource's online capacity (e.g., committed capacity for unit commitment resources) "
        "that can be used to provide operating reserve.",
    )
    scalar_type: IncrementalReserveType = IncrementalReserveType.OPERATIONAL_CAPACITY

    incremental_requirement_hourly_scalar: ts.NumericTimeseries = pydantic.Field(
        default_freq="H",
        up_method="interpolate",
        down_method="first",
        alias="incremental_requirement",
        default_factory=ts.NumericTimeseries.zero,
    )
    incremental_requirement_hourly_scalar__type: ts.TimeseriesType = ts.TimeseriesType.MODELED_YEAR

    # TODO: incremental requirement annual scalar is currently not used
    incremental_requirement_annual_scalar: ts.NumericTimeseries = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="first",
        default_factory=ts.NumericTimeseries.zero,
    )

    # @pydantic.validator("dependent_on")
    # def validate_reserve_dependence(cls, dependent_on, values):
    #     dependent_list = ["setpoint", "commitment"]
    #     if dependent_on not in dependent_list:
    #         raise ValueError(
    #             f"For {cls.__name__} linkage \"{values['name']}\", attribute (`dependent_on`) must be in {dependent_list}"
    #         )
    #     return dependent_on


class LoadToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "loads → zones"
    component_type_from_: str = "loads"
    component_type_to_: str = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class LoadToReserve(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "loads → reserves"
    component_type_from_: str = "loads"
    component_type_to_: str = "reserves"
    SAVE_PATH = "loads_to_reserves.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    incremental_requirement_hourly_scalar: ts.FractionalTimeseries = pydantic.Field(
        default_factory=ts.NumericTimeseries.zero,
        default_freq="H",
        up_method="ffill",
        down_method="average",
    )
    incremental_requirement_hourly_scalar__type: ts.TimeseriesType = ts.TimeseriesType.MODELED_YEAR


class ReserveToZone(Linkage):

    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "reserves → zones"
    component_type_from_: str = "reserves"
    component_type_to_: str = "zones"
    SAVE_PATH = "reserves_to_zones.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    incremental_requirement_hourly_scalar: ts.FractionalTimeseries = pydantic.Field(
        default_factory=ts.NumericTimeseries.zero,
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
    component_type_from_: str = "resources"
    component_type_to_: str = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class AssetToAssetGroup(Linkage):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    component_type_from_: str = "assets"
    component_type_to_: str = "asset_groups"


class TrancheToAsset(Linkage):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    component_type_from_: str = "tranches"
    component_type_to_: str = "assets"


class ResourceToResourceGroup(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "resources → resource groups"
    component_type_from_: str = "resources"
    component_type_to_: str = "resource_groups"

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
    component_type_from_: str = "resources"
    component_type_to_: str = "outage_distributions"

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
    component_type_from_: str = "resources"
    component_type_to_: str = "fuel_zones"

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
    component_type_from_: str = "assets"
    component_type_to_: str = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class AssetToCaisoTxConstraint(Linkage):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "assets → CAISO tx constraint"
    component_type_from_: str = "assets"
    component_type_to_: str = "caiso_tx_constraints"
    SAVE_PATH = "assets_to_caiso_tx_constraints.csv"

    hsn_factor: float
    ssn_factor: float
    eods_factor: float

class CandidateFuelToPollutant(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "candidate fuels → pollutants"
    component_type_from_: str = "candidate_fuels"
    component_type_to_: str = "pollutants"
    SAVE_PATH = "candidate_fuels_to_pollutants.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    net_emission_factor: Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("emission_factor"),
    )

    gross_emission_factor: Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("emission_factor"),
    )

    upstream_emission_factor: Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("emission_factor"),
    )

    gross_emissions_trajectory_override: Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )

    net_emissions_trajectory_override: Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )

    upstream_emissions_trajectory_override: Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )

    # attributes that will be set during stock rollover calculations
    out_net_emissions: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        weather_year=False,
    )

    out_gross_emissions: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        weather_year=False,
    )

    out_upstream_emissions: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        weather_year=False,
    )

    out_net_emissions_CO2e: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        weather_year=False,
    )

    out_gross_emissions_CO2e: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        weather_year=False,
    )

    out_upstream_emissions_CO2e: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        weather_year=False,
    )


class BiomassResourceToCandidateFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "biomass resources → candidate fuels"
    component_type_from_: str = "biomass_resources"
    component_type_to_: str = "candidate_fuels"
    SAVE_PATH = "biomass_resources_to_candidate_fuels.csv"

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
    component_type_from_: str = "electrolyzers"
    component_type_to_: str = "candidate_fuels"


class FuelZoneToCandidateFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "fuel zones → candidate fuels"
    component_type_from_: str = "fuel_zones"
    component_type_to_: str = "candidate_fuels"

    ###################
    # INSTANCE FIELDS #
    ###################

    @property
    def candidate_fuel(self):
        return self.instance_to

    @property
    def fuel_zone(self):
        return self.instance_from


class ElectrolyzerToFuelZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "electrolyzers → fuel zones"
    component_type_from_: str = "electrolyzers"
    component_type_to_: str = "fuel_zones"


class ElectrolyzerToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    _class_descriptor = "electrolyzers → zones"
    component_type_from_: str = "electrolyzers"
    component_type_to_: str = "zones"

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
    component_type_from_: str = "fuel_storages"
    component_type_to_: str = "fuel_zones"

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
    component_type_from_: str = "fuel_storages"
    component_type_to_: str = "candidate_fuels"

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
    component_type_from_: str = "fuel_storages"
    component_type_to_: str = "zones"

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
    component_type_from_: str = "fuel_conversion_plants"
    component_type_to_: str = "fuel_zones"

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
    component_type_from_: str = "fuel_conversion_plants"
    component_type_to_: str = "candidate_fuels"

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
    component_type_from_: str = "fuel_conversion_plants"
    component_type_to_: str = "zones"

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
    component_type_from_: str = "final_fuels"
    component_type_to_: str = "fuel_zones"

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
    component_type_from_: str = "zones"
    component_type_to_: str = "tx_paths"
    SAVE_PATH = "zones_to_tx_paths.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    # user should specify the from and to zone of each tx path
    # TODO: do we need a validation so that there are only two zones linked to the same line?
    # TODO: validation to make sure there is only one from_zone for each tx_path etc.
    from_zone: bool = False
    to_zone: bool = False

    @pydantic.root_validator(skip_on_failure=True)
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


class FromZoneToPath(ZoneToTransmissionPath):
    SAVE_PATH = None
    from_zone: bool = True


class ToZoneToPath(ZoneToTransmissionPath):
    SAVE_PATH = None
    to_zone: bool = True


# class FuelZoneToFuelTransportation(Linkage):
#     ####################
#     # CLASS ATTRIBUTES #
#     ####################
#     _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
#     _class_descriptor = "fuel zones → fuel transportations"
#     _component_type_from = "fuel_zones"
#     _component_type_to = "fuel_transportations"
#     SAVE_PATH = "fuel_zones_to_fuel_transportations.csv"
#
#     ###################
#     # INSTANCE FIELDS #
#     ###################
#     # user should specify the from and to zone of each fuel transportation
#     # TODO: do we need a validation so that there are only two zones linked to the same line?
#     # TODO: validation to make sure there is only one from_zone for each tx_path etc.
#     from_zone: bool = False
#     to_zone: bool = False
#
#     @pydantic.root_validator(skip_on_failure=True)
#     def linkage_is_from_zone_xor_to_zone(cls, values):
#         """Validate that exactly one of `from_zone` and `to_zone` is set to True."""
#         if not values["from_zone"] and not values["to_zone"]:
#             raise ValueError(
#                 f"{cls.__name__} linkage for {values['name']} must have either 'from_zone' or 'to_zone' set to True."
#             )
#         elif values["from_zone"] and values["to_zone"]:
#             raise ValueError(
#                 f"{cls.__name__} linkage for {values['name']} must have either 'from_zone' or 'to_zone' set to True, but not both."
#             )
#         else:
#             return values


class ZoneToZone(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "zones → zones"
    component_type_to_: str = "subzones"
    component_type_from_: str = "parent_zones"

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
    component_type_to_: str = "fuel_zones"
    component_type_from_: str = "zones"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


# class FuelTransportationToCandidateFuel(Linkage):
#     ####################
#     # CLASS ATTRIBUTES #
#     ####################
#     _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
#     _class_descriptor = "fuel transportations → candidate fuels"
#     _component_type_from = "fuel_transportations"
#     _component_type_to = "candidate_fuels"
#
#     ###################
#     # INSTANCE FIELDS #
#     ###################
#     # None


# TODO: Not sure I need to create _instances class attribute every time... In general, there's a lot of boilerplate here.
# TODO: Need to get the "from" and "to" direction consistent



class _AllToPolicy(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ###################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "anything → policies"
    component_type_from_: str = ""  # this will be overridden in get_dir
    component_type_to_: str = "policies"
    # _map_file = "all_to_policies/mapping.csv"
    SAVE_PATH = "all_to_policies.csv"

    multiplier: Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="sum", alias="nqc"
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Check if "component_type_from_" and "component_type_to_" exist if reading from json files in PCM
        if "component_type_from_" not in kwargs:
            self.component_type_from_: str = self._get_component_type_from_()
        if "component_type_to_" not in kwargs:
            self.component_type_to_: str = self._get_component_type_to_()

    def _get_component_type_from_(self):
        from new_modeling_toolkit import system

        if isinstance(self.instance_from, system.electric.load_component.Load):
            component_type_from = "loads"
        elif isinstance(self.instance_from, system.electric.elcc.ELCCSurface):
            component_type_from = "elcc_surfaces"
        elif isinstance(self.instance_from, system.fuel.candidate_fuel.CandidateFuel):
            component_type_from = "candidate_fuels"
        elif isinstance(self.instance_from, system.fuel.final_fuel.FinalFuel):
            component_type_from = "final_fuels"
        elif isinstance(self.instance_from, system.electric.reserve.Reserve):
            component_type_from = "reserves"
        elif isinstance(self.instance_from, system.electric.zone.Zone):
            component_type_from = "zones"
        elif isinstance(self.instance_from, system.electric.resources.generic.GenericResource):
            component_type_from = "resources"
        elif isinstance(self.instance_from, system.electric.tx_path.TxPath):
            component_type_from = "tx_paths"
        elif isinstance(self.instance_from, system.pollution.negative_emissions_technology.NegativeEmissionsTechnology):
            component_type_from = "negative_emissions_technologies"
        elif isinstance(self.instance_from, system.generics.plant.Plant):
            component_type_from = "plants"
        elif isinstance(self.instance_from, system.generics.demand.Demand):
            component_type_from = "demands"
        elif isinstance(self.instance_from, system.generics.transportation.Transportation):
            component_type_from = "transportations"
        elif isinstance(self.instance_from, system.pollution.pollutant.Pollutant):
            component_type_from = "pollutants"
        elif isinstance(self.instance_from, system.electric.CaisoTxConstraint):
            component_type_from = "caiso_tx_constraints"
        elif isinstance(self.instance_from, system.asset.Asset):
            if isinstance(self.instance_to, system.policy.PlanningReserveMargin) or isinstance(
                self.instance_to, system.policy.EnergyReserveMargin
            ):
                component_type_from = "assets_"
            else:
                component_type_from = "assets"
        else:
            raise ValueError(
                f"Unrecognized type for `instance_from` in AllToPolicy linkage `{self.name}`: `{type(self.instance_from)}`"
            )

        return component_type_from

    def _get_component_type_to_(self):
        from new_modeling_toolkit.system import policy

        if isinstance(self.instance_to, policy.AnnualEmissionsPolicy):
            component_type_to = "emissions_policies"
        elif isinstance(self.instance_to, policy.AnnualEnergyStandard):
            component_type_to = "annual_energy_policies"
        elif isinstance(self.instance_to, policy.HourlyEnergyStandard):
            component_type_to = "hourly_energy_policies"
        elif isinstance(self.instance_to, policy.PlanningReserveMargin):
            component_type_to = "prm_policies"
        elif isinstance(self.instance_to, policy.EnergyReserveMargin):
            component_type_to = "erm_policies"
            if not isinstance(self, ERMContribution):
                raise ValueError(
                    f"ERM policy linkages must be explicitly modeled as ERMContribution linkages."
                    f"Change the AllToPolicy linkage `{self.name}` to an ERMContribution linkage."
                )
        else:
            raise ValueError(
                f"Unrecognized type for `instance_to` in AllToPolicy linkage `{self.name}`: `{type(self.instance_to)}`"
            )

        return component_type_to


class AllToPolicy(_AllToPolicy):
    ###################
    # INSTANCE FIELDS #
    ###################
    attribute: Annotated[str | None, Metadata(default_exclude=True)] = None  # attribute in the RESOLVE model
    forward_dir_multiplier: Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="sum"
    )  # used when Transmission Path to Policy linkage
    reverse_dir_multiplier: Optional[ts.NumericTimeseries] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="sum"
    )  # used when Transmission Path to Policy linkage

    fully_deliverable: bool = True

    # Used when Transmission Path to Policy Linkage
    @pydantic.root_validator(skip_on_failure=True)
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


# Creating aliases for convenience
class EmissionsContribution(_AllToPolicy):
    SAVE_PATH = "resource_fuel_emissions_contributions.csv"
    multiplier: Annotated[
        ts.NumericTimeseries | None, Metadata(excel_short_title="tonne/MWh", units=units.tonne / units.MWh)
    ] = pydantic.Field(None, default_freq="YS", up_method="ffill", down_method="mean", title="Emissions Rate")


class TxEmissionsContribution(EmissionsContribution):
    SAVE_PATH = "tx_emissions_contributions.csv"
    forward_dir_multiplier: Annotated[
        ts.NumericTimeseries | None, Metadata(excel_short_title="Rate", units=units.tonne / units.MWh)
    ] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="sum", title="Forward Emissions Rate (per-MWh)"
    )
    reverse_dir_multiplier: Annotated[
        ts.NumericTimeseries | None, Metadata(excel_short_title="Rate", units=units.tonne / units.MWh)
    ] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="sum", title="Reverse Emissions Rate (per-MWh)"
    )


# TODO: Add TransportationEmissionsContribution


class AnnualEnergyStandardContribution(_AllToPolicy):
    SAVE_PATH = "annual_energy_standard_contributions.csv"
    multiplier: Annotated[ts.NumericTimeseries | None, Metadata(excel_short_title="%")] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="annual", title="Qualifying Generation (%)"
    )


class HourlyEnergyStandardContribution(_AllToPolicy):
    SAVE_PATH = "hourly_energy_standard_contributions.csv"
    multiplier: Annotated[ts.NumericTimeseries | None, Metadata(excel_short_title="%")] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="annual", title="Qualifying Generation (%)"
    )


class ERMContribution(_AllToPolicy):
    SAVE_PATH = "erm_contributions.csv"
    multiplier: Annotated[ts.NumericTimeseries | None, Metadata(excel_short_title="%")] = pydantic.Field(
        default_factory=ts.Timeseries.one,
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
        title="ERM Hourly Fraction",
    )

class ReliabilityContribution(_AllToPolicy):
    SAVE_PATH = "reliability_contributions.csv"
    attribute: Annotated[str | None, Metadata(default_exclude=True)] = None  # attribute in the RESOLVE model
    fully_deliverable: bool = True
    multiplier: Annotated[ts.NumericTimeseries | None, Metadata(excel_short_title="%")] = pydantic.Field(
        None, default_freq="YS", up_method="ffill", down_method="annual", title="Qualifying Capacity"
    )

class ELCCReliabilityContribution(_AllToPolicy):
    SAVE_PATH = "elcc_reliability_contributions.csv"

class FinalFuelToAnnualEmissionsPolicy(AllToPolicy):
    """Temporary subclass only so that final fuels are correctly linked to annual emissions policies."""

    ####################
    # CLASS ATTRIBUTES #
    ###################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "final fuel → annual emissions policy"
    component_type_from_: str = "final_fuels"
    component_type_to_: str = "policies"

    ###################
    # INSTANCE FIELDS #
    ###################
    # None


class ELCCFacetToSurface(Linkage):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_ONE
    component_type_from_: str = "facets"
    component_type_to_: str = "surface"


class AssetToELCC(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "assets → ELCC"
    component_type_from_: str = "assets"
    component_type_to_: str = "elcc_surfaces"
    SAVE_PATH = "assets_to_elcc.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    # TODO 2024-08-15: As far as I can tell, `multiplier` and `multiplier_unit` don't do anything?
    multiplier: Annotated[float | None, Metadata(default_exclude=True)] = None
    multiplier_unit: Annotated[str | None, Metadata(default_exclude=True)] = None
    attribute: Annotated[Literal["power", "energy"], Metadata(default_exclude=True)] = "power"
    elcc_axis_index: int = 1
    elcc_axis_multiplier: float = 1

    @pydantic.root_validator(skip_on_failure=True)
    def has_axis_index_if_multiplier(cls, values):
        if values["elcc_axis_multiplier"] is not None:
            assert values["elcc_axis_index"] is not None, (
                "`elcc_axis_multiplier` was specified but `elcc_axis_index` was not. You must specify an "
                "`elcc_axis_index` in order to use an `elcc_axis_multiplier`."
            )

        return values


class XToFinalFuel(Linkage):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.ONE_TO_MANY

    _class_descriptor = "component → final fuels"
    component_type_from_: str = "component"
    component_type_to_: str = "final_fuels"
    SAVE_PATH = "component_to_final_fuels.csv"

    # attributes that will be set during stock rollover calculations
    out_energy_demand: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        default_freq="YS",
        up_method="interpolate",
        down_method="first",
        weather_year=True,
    )


class CandidateFuelToFinalFuel(XToFinalFuel):
    ####################
    # CLASS ATTRIBUTES #
    ####################
    _RELATIONSHIP_TYPE = LinkageRelationshipType.ONE_TO_ONE
    _class_descriptor = "candidate fuels → final fuels"
    component_type_from_: str = "candidate_fuels"
    component_type_to_: str = "final_fuels"
    SAVE_PATH = "candidate_fuels_to_final_fuels.csv"

    ###################
    # INSTANCE FIELDS #
    ###################
    blend_limit_fraction: Optional[ts.NumericTimeseries] = pydantic.Field(
        default_freq="YS", up_method="interpolate", down_method="annual", weather_year=False
    )

    ######################
    # Calculated Outputs #
    ######################
    out_fuel_cost: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        default_freq="YS",
        up_method="interpolate",
        down_method="first",
        weather_year=True,
    )

    out_net_emissions: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        up_method="ffill",
        down_method="annual",
        default_freq="YS",
        weather_year=True,
    )

    out_gross_emissions: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        up_method="ffill",
        down_method="annual",
        default_freq="YS",
        weather_year=True,
    )

    out_upstream_emissions: ts.NumericTimeseries = pydantic.Field(
        default_factory=lambda: ts.NumericTimeseries.default_factory(value=np.nan),
        up_method="ffill",
        down_method="annual",
        default_freq="YS",
        weather_year=True,
    )


class ResourceToPollutant(Linkage):
    """
    Defines the linkage between resources and pollutants. Used if emission factors are set on the resource to
    pollutant level rather than the resource to fuel to pollutant level.
    """

    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY

    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "resources → pollutants"
    component_type_from_: str = "resources"
    component_type_to_: str = "pollutants"
    SAVE_PATH = "resources_to_pollutants.csv"

    emission_factor: ts.NumericTimeseries = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )


class TransmissionPathToPollutant(Linkage):
    """
    Defines the linkage between transmission paths and pollutants. Used to set emission factors for Tx lines.
    """

    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY

    ####################
    # CLASS ATTRIBUTES #
    ####################

    _class_descriptor = "transmission paths → pollutants"
    component_type_from_: str = "tx_paths"
    component_type_to_: str = "pollutants"
    SAVE_PATH = "tx_paths_to_pollutants.csv"

    forward_dir_multiplier: ts.NumericTimeseries = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )
    reverse_dir_multiplier: ts.NumericTimeseries = pydantic.Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )
