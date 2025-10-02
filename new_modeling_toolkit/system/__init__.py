from __future__ import annotations

import copy
import gc
import inspect
import json
import os
import pathlib
import pprint
import sys
import typing
from collections import Counter
from collections import defaultdict
from json import dumps
from types import UnionType
from typing import Any
from typing import ClassVar
from typing import Optional
from typing import Union

import pandas as pd
import pydantic
import pydantic_core
from joblib import delayed
from joblib import Parallel
from loguru import logger
from pydantic import Field
from pydantic import ValidationError
from tqdm import tqdm

from new_modeling_toolkit.core import custom_constraint
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core import three_way_linkage
from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.linkage import AssetToAssetGroup
from new_modeling_toolkit.core.linkage import IncrementalReserveType
from new_modeling_toolkit.core.linkage import Linkage
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.three_way_linkage import CustomConstraintLinkage
from new_modeling_toolkit.core.three_way_linkage import ThreeWayLinkage
from new_modeling_toolkit.core.utils.core_utils import timer
from new_modeling_toolkit.core.utils.util import DirStructure
from new_modeling_toolkit.system.asset import Asset
from new_modeling_toolkit.system.asset import AssetGroup
from new_modeling_toolkit.system.electric.caiso_tx_constraint import CaisoTxConstraint
from new_modeling_toolkit.system.electric.elcc import ELCCFacet
from new_modeling_toolkit.system.electric.elcc import ELCCSurface
from new_modeling_toolkit.system.electric.load_component import Load
from new_modeling_toolkit.system.electric.reserve import Reserve
from new_modeling_toolkit.system.electric.resource_group import ResourceGroup
from new_modeling_toolkit.system.electric.resources import ElectricResource
from new_modeling_toolkit.system.electric.resources import FlexLoadResource
from new_modeling_toolkit.system.electric.resources import GenericResource
from new_modeling_toolkit.system.electric.resources import HybridStorageResource
from new_modeling_toolkit.system.electric.resources import HybridVariableResource
from new_modeling_toolkit.system.electric.resources import HydroResource
from new_modeling_toolkit.system.electric.resources import ShedDrResource
from new_modeling_toolkit.system.electric.resources import StorageResource
from new_modeling_toolkit.system.electric.resources import ThermalResource
from new_modeling_toolkit.system.electric.resources import ThermalUnitCommitmentResource
from new_modeling_toolkit.system.electric.resources import UnitCommitmentResource
from new_modeling_toolkit.system.electric.resources import VariableResource
from new_modeling_toolkit.system.electric.resources.generic import GenericResourceGroup
from new_modeling_toolkit.system.electric.resources.hybrid import HybridSolarResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridSolarResourceGroup
from new_modeling_toolkit.system.electric.resources.hybrid import HybridStorageResourceGroup
from new_modeling_toolkit.system.electric.resources.hybrid import HybridVariableResourceGroup
from new_modeling_toolkit.system.electric.resources.hybrid import HybridWindResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridWindResourceGroup
from new_modeling_toolkit.system.electric.resources.hydro import HydroResourceGroup
from new_modeling_toolkit.system.electric.resources.storage import StorageResourceGroup
from new_modeling_toolkit.system.electric.resources.thermal import ThermalResourceGroup
from new_modeling_toolkit.system.electric.resources.thermal import ThermalUnitCommitmentResourceGroup
from new_modeling_toolkit.system.electric.resources.variable.solar import SolarResource
from new_modeling_toolkit.system.electric.resources.variable.solar import SolarResourceGroup
from new_modeling_toolkit.system.electric.resources.variable.variable import VariableResourceGroup
from new_modeling_toolkit.system.electric.resources.variable.wind import WindResource
from new_modeling_toolkit.system.electric.resources.variable.wind import WindResourceGroup
from new_modeling_toolkit.system.electric.tx_path import TxPath
from new_modeling_toolkit.system.electric.tx_path import TxPathGroup
from new_modeling_toolkit.system.electric.zone import Zone
from new_modeling_toolkit.system.fuel.candidate_fuel import CandidateFuel
from new_modeling_toolkit.system.fuel.electrolyzer import Electrolyzer
from new_modeling_toolkit.system.fuel.electrolyzer import ElectrolyzerGroup
from new_modeling_toolkit.system.fuel.final_fuel import FinalFuel
from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlant
from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlantGroup
from new_modeling_toolkit.system.fuel.fuel_storage import FuelStorage
from new_modeling_toolkit.system.fuel.fuel_storage import FuelStorageGroup
from new_modeling_toolkit.system.generics.demand import Demand
from new_modeling_toolkit.system.generics.energy import _EnergyCarrier
from new_modeling_toolkit.system.generics.energy import Electricity
from new_modeling_toolkit.system.generics.energy import EnergyDemand
from new_modeling_toolkit.system.generics.generic_linkages import DemandToProduct
from new_modeling_toolkit.system.generics.generic_linkages import ZoneToDemand
from new_modeling_toolkit.system.generics.generic_linkages import ZoneToPlant
from new_modeling_toolkit.system.generics.generic_linkages import ZoneToProduct
from new_modeling_toolkit.system.generics.plant import Plant
from new_modeling_toolkit.system.generics.plant import PlantGroup
from new_modeling_toolkit.system.generics.process import ChargeProcess
from new_modeling_toolkit.system.generics.process import Process
from new_modeling_toolkit.system.generics.product import Product
from new_modeling_toolkit.system.generics.transportation import Transportation
from new_modeling_toolkit.system.outage_distribution import OutageDistribution
from new_modeling_toolkit.system.policy import AnnualEmissionsPolicy
from new_modeling_toolkit.system.policy import AnnualEnergyStandard
from new_modeling_toolkit.system.policy import EnergyReserveMargin
from new_modeling_toolkit.system.policy import HourlyEnergyStandard
from new_modeling_toolkit.system.policy import PlanningReserveMargin
from new_modeling_toolkit.system.pollution.negative_emissions_technology import NegativeEmissionsTechnology
from new_modeling_toolkit.system.pollution.negative_emissions_technology import NegativeEmissionsTechnologyGroup
from new_modeling_toolkit.system.pollution.pollutant import Pollutant
from new_modeling_toolkit.system.pollution.sequestration import Sequestration
from new_modeling_toolkit.system.pollution.sequestration import SequestrationGroup
from new_modeling_toolkit.system.sector import Sector

# Mapping between `System` attribute name and component class to construct.

__all__ = [
    "Asset",
    "AssetGroup",
    "TxPath",
    "ELCCSurface",
    "Load",
    "Reserve",
    "ResourceGroup",
    "FlexLoadResource",
    "GenericResource",
    "HybridStorageResource",
    "HybridVariableResource",
    "HydroResource",
    "ShedDrResource",
    "StorageResource",
    "ThermalResource",
    "ThermalUnitCommitmentResource",
    "VariableResource",
    "SolarResource",
    "WindResource",
    "GenericResourceGroup",
    "HydroResourceGroup",
    "StorageResourceGroup",
    "ThermalResourceGroup",
    "VariableResourceGroup",
    "WindResourceGroup",
    "SolarResourceGroup",
    "HybridVariableResourceGroup",
    "HybridStorageResourceGroup",
    "Zone",
    "CandidateFuel",
    "FinalFuel",
    "OutageDistribution",
    "AnnualEmissionsPolicy",
    "AnnualEnergyStandard",
    "PlanningReserveMargin",
    "Pollutant",
    "Sector",
    "Demand",
    "EnergyDemand",
    "_EnergyCarrier",
    "FuelStorage",
    "FuelProductionPlant",
    "Electricity",
    "NegativeEmissionsTechnology",
    "Sequestration",
]


NON_COMPONENT_FIELDS = [
    "attr_path",
    "class_name",
    "include",
    "custom_constraints",
    "dir_str",
    "linkages",
    "name",
    "scenarios",
    "three_way_linkages",
    "year_end",
    "year_start",
    "base_year",
]


# Create a list of components to construct
ASSET_GROUP_TYPES = [AssetGroup] + list(AssetGroup.get_subclasses())
ASSET_TYPES = [Asset] + [x for x in Asset.get_subclasses() if x not in ASSET_GROUP_TYPES]
PRODUCT_TYPES = [Product] + list(Product.get_subclasses())
DEMAND_TYPES = [Demand] + list(Demand.get_subclasses())

COMPONENT_TYPES_TO_RECONSTRUCT_DICT = {
    "assets": {asset_class.__name__: asset_class for asset_class in ASSET_TYPES},
    "asset_groups": {asset_group_class.__name__: asset_group_class for asset_group_class in ASSET_GROUP_TYPES},
    "products": {product_class.__name__: product_class for product_class in PRODUCT_TYPES},
    "demands": {demand_class.__name__: demand_class for demand_class in DEMAND_TYPES},
}

# Create a list of linkages to construct
LINKAGE_TYPES = list(Linkage.get_subclasses())
LINKAGE_TYPE_DICT = {linkage_class.__name__: linkage_class for linkage_class in LINKAGE_TYPES}

THREE_WAY_LINKAGE_TYPES = list(ThreeWayLinkage.get_subclasses())
THREE_WAY_LINKAGE_TYPE_DICT = {linkage_class.__name__: linkage_class for linkage_class in THREE_WAY_LINKAGE_TYPES}

class System(Component):
    """Initializes Component and Linkage instances."""

    ####################
    # FIELDS FROM FILE #
    ####################
    # TODO: Tradeoff between using a Timeseries, which will be read automatically, and being able to constrain values.
    #  Think if there's a way to constrain data types--maybe only be subclassing timeseries?
    #  A silly way to do this would be to read them in as Timeseries but then use validators to convert them to dicts/lists

    """
    TODO (5/3):
    1. Make a list of timestamps we want to model (will eventually be more dynamic)
    2. Write methods for Timeseries that return a "view" of the timeseries that matches the timestamps we want to model


    1. Subclasses
    2. Should subclasses have different input folders?

    """
    SAVE_PATH: ClassVar[str] = "systems"
    dir_str: DirStructure

    ##############
    # Components #
    ##############
    # fmt: off
    # TODO 2023-05-05: Probably can come up with a default data_filepath to reduce repeating name of component (e.g., data_filepath="assets")

    # Assets
    assets: dict[str, Asset] = {}
    asset_groups: dict[str, AssetGroup] = {}

    # Products and Demands
    products: dict[str, Product] = {}
    demands: dict[str, Demand] = {}

    # Policy-related
    emissions_policies: dict[str, AnnualEmissionsPolicy] = {}
    annual_energy_policies: dict[str, AnnualEnergyStandard] = {}
    hourly_energy_policies: dict[str, HourlyEnergyStandard] = {}
    erm_policies: dict[str, EnergyReserveMargin] = {}
    prm_policies: dict[str, PlanningReserveMargin] = {}
    elcc_facets: dict[str, ELCCFacet] = {}
    elcc_surfaces: dict[str, ELCCSurface] = {}

    # Other component classes
    zones: dict[str, Zone] = {}
    loads: dict[str, Load] = {}
    reserves: dict[str, Reserve] = {}
    custom_constraints_lhs: dict[str, custom_constraint.CustomConstraintLHS] = {}
    custom_constraints_rhs: dict[str, custom_constraint.CustomConstraintRHS] = {}
    caiso_tx_constraints: dict[str, CaisoTxConstraint] = {}

    # TODO: Not yet implemented in Resolve 3.0:
    sectors: dict[str, Sector] = {}
    outage_distributions: dict[str, OutageDistribution] = {}
    final_fuels: dict[str, FinalFuel] = {}


    ############
    # Linkages #
    ############
    linkages: dict[str, list[linkage.Linkage]] = {}
    three_way_linkages: dict[str, list[three_way_linkage.ThreeWayLinkage]] = {}

    @property
    def _optimization_construction_order(self):
        """Order of components here is important because some component blocks reference others which have to be created.

        The order is referenced in reverse when results expressions are created.
        """
        construction_order = (
            list(self.assets.values()) +
            list(self.asset_groups.values()) +
            list(self.demands.values()) +
            list(self.loads.values()) +
            list(self.reserves.values()) +
            list(self.elcc_surfaces.values()) +
            list(self.policies.values()) +
            list(self.caiso_tx_constraints.values()) +
            list(self.custom_constraints_lhs.values()) +
            list(self.custom_constraints_rhs.values()) +
            list(self.products.values()) +
            list(self.zones.values())
        )

        # Reorder the list so that HybridVariableResources are always before HybridStorageResources
        def hybrid_sort_key(obj):
            if isinstance(obj, HybridVariableResource):
                return 0  # HybridVariableResources will move to the top
            elif isinstance(obj, HybridStorageResource):
                return 1  # HybridStorageResources will come next
            else:
                return 2  # Everything else stays in the same order
        construction_order = sorted(construction_order, key=hybrid_sort_key)

        # Check for repeating names
        construction_order_names = [component.name for component in construction_order]
        if len(construction_order_names) != len(set(construction_order_names)):
            # there are repeating components in construction_order list
            raise ValueError(f"There are repeating component(s) in System._optimization_construction_order.")
        else:
            return construction_order

    ##########
    # FIELDS #
    ##########
    scenarios: list = []

    @property
    def generic_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, GenericResource)}

    @property
    def flex_load_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, FlexLoadResource)}

    @property
    def hydro_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, HydroResource)}

    @property
    def shed_dr_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, ShedDrResource)}

    @property
    def storage_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, StorageResource)}

    @property
    def solar_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, SolarResource)}

    @property
    def wind_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, WindResource)}

    @property
    def thermal_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, ThermalResource)}

    @property
    def thermal_uc_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, ThermalUnitCommitmentResource)}

    @property
    def hybrid_storage_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, HybridStorageResource)}

    @property
    def hybrid_variable_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, HybridVariableResource)}

    @property
    def hybrid_solar_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, HybridSolarResource)}

    @property
    def hybrid_wind_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, HybridWindResource)}

    @property
    def hybrid_storage_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, HybridStorageResourceGroup)}

    @property
    def hybrid_variable_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, HybridVariableResourceGroup)}

    @property
    def hybrid_solar_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, HybridSolarResourceGroup)}

    @property
    def hybrid_wind_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, HybridWindResourceGroup)}

    @property
    def generic_assets(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, Asset)}

    @property
    def electric_resources(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, GenericResource)}

    @property
    def tx_paths(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, TxPath)}

    @property
    def wind_and_solar_resources(self) -> dict[str, VariableResource]:
        return (self.solar_resources | self.wind_resources)

    @property
    def transportations(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, Transportation)}

    @property
    def generic_plants(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, Plant)}

    @property
    def fuel_production_plants(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, FuelProductionPlant)}

    @property
    def electrolyzers(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, Electrolyzer)}

    @property
    def fuel_storage_plants(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, FuelStorage)}

    @property
    def negative_emissions_technologies(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, NegativeEmissionsTechnology)}

    @property
    def sequestration_plants(self):
        return {k: v for k, v in self.assets.items() if isinstance(v, Sequestration)}

    # TODO: make the properties more specific and the initialized dictionaries more general, like we have for Electric Sector
    @property
    def plants(self) -> dict[str, Plant]:
        """Superset of all `Plant` child classes."""
        return self.generic_plants | self.fuel_production_plants | self.electrolyzers | self.fuel_storage_plants | self.negative_emissions_technologies| self.sequestration_plants

    @property
    def energy_demands(self):
        return {k: v for k, v in self.demands.items() if isinstance(v, EnergyDemand)}

    @property
    def energy_carriers(self):
        return {k: v for k, v in self.products.items() if isinstance(v, _EnergyCarrier)}

    @property
    def electricity_products(self):
        return {k: v for k, v in self.products.items() if isinstance(v, Electricity)}

    @property
    def pollutants(self):
        return {k: v for k, v in self.products.items() if isinstance(v, Pollutant)}

    @property
    def candidate_fuels(self):
        return {k: v for k, v in self.products.items() if isinstance(v, CandidateFuel)}


    @property
    def variable_resources(self) -> dict[str, VariableResource]:
        return {k: v for k, v in self.assets.items() if isinstance(v, VariableResource)}

    @property
    def resources(self) -> dict[str, GenericResource]:
        """Superset of all `Resource` child classes (duplicative of electric_resources)."""
        return self.electric_resources

    @property
    def policies(self):
        """Superset of all `Policy` child classes."""
        return (
            self.emissions_policies
            | self.annual_energy_policies
            | self.hourly_energy_policies
            | self.prm_policies
            | self.erm_policies
        )


    @classmethod
    def _component_fields(cls):
        """Return list of component FIELDS in `System` (by manually excluding non-`Component` attributes)."""
        return {name: field for name, field in cls.model_fields.items() if name not in NON_COMPONENT_FIELDS}

    @property
    def components_by_type(self):
        return (
            {name: getattr(self, name) for name, field in self._component_fields().items()}
        )

    @property
    def components(self) -> dict[str, Component]:
        """Return dict of component ATTRIBUTES and "virtual" components (i.e., properties that are the union of other components)."""
        return {
            key: component
            for name in self._component_fields().keys()
            for key, component in getattr(self, name).items()
        }

    @property
    def tx_path_groups(self):
        return {k:v for k, v in self.asset_groups.items() if isinstance(v, TxPathGroup)}

    # TODO: these next two properties are the same thing. Which one can be removed?
    @property
    def resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, GenericResourceGroup)}

    @property
    def generic_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, GenericResourceGroup)}

    @property
    def hydro_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, HydroResourceGroup)}

    @property
    def wind_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, WindResourceGroup)}

    @property
    def solar_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, SolarResourceGroup)}

    @property
    def wind_and_solar_resource_groups(self):
        return (self.solar_resource_groups | self.wind_resource_groups)

    @property
    def variable_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, VariableResourceGroup)}

    @property
    def storage_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, StorageResourceGroup)}

    @property
    def thermal_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, ThermalResourceGroup)}

    @property
    def thermal_uc_resource_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, ThermalUnitCommitmentResourceGroup)}

    @property
    def plant_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, PlantGroup)}

    @property
    def fuel_production_plant_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, FuelProductionPlantGroup)}

    @property
    def electrolyzer_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, ElectrolyzerGroup)}

    @property
    def fuel_storage_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, FuelStorageGroup)}

    @property
    def negative_emissions_technology_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, NegativeEmissionsTechnologyGroup)}

    @property
    def sequestration_groups(self):
        return {k: v for k, v in self.asset_groups.items() if isinstance(v, SequestrationGroup)}

    def __init__(self, **data):
        """
        Initializes a electrical system based on csv inputs. The sequence of initialization can be found in the
        comments of the system class

        Args:
            graph_dict: the dictionary that determines the linkage between different components of the system
        """
        super().__init__(**data)

        # Announce linkages
        self.relink()
        self.announce_linkages_to_instances()
        self.announce_three_way_linkages_to_instances()

        ##########################
        # ADDITIONAL VALIDATIONS #
        ##########################
        self._validate_electricity_products_and_linkages()

    def revalidate(self):
        logger.info("Revalidating components...")
        for component in self.components.values():
            component.revalidate()

    # TODO: Add construct_vintages unit test
    def construct_vintages(self, modeled_years):
        """Create vintage components for asset groups that have any True `vintages_to_construct."""

        linkages_to_remove = defaultdict(list)
        for group in tqdm(
                self.asset_groups.values(),
                desc=f"Constructing vintages".rjust(50),
                bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            # Guard clause to skip groups that don't have defined `vintages_to_construct`
            if "vintages_to_construct" not in group.model_fields_set:
                continue

            # Only construct vintages that user specifies & for modeled years
            vintages_to_construct = (
                set(group.vintages_to_construct.data.loc[group.vintages_to_construct.data == True].index.year) &
                set(modeled_years.year)
            )
            logger.debug(f"Creating {group.name} vintages: {vintages_to_construct}")

            vintage_class = group.__class__.__bases__[-1]  # last base class should be vintage class

            for vintage in vintages_to_construct:
                # Turn timeseries values into scalars when necessary & get a new name
                fields_to_update = {"name": f"{group.name} ({vintage})", "build_year": f"1/1/{vintage}"}
                for field in group.model_fields:
                    # Make annualized_capital_cost, annualized_fixed_om_cost, and potential floats on each vintage
                    if field.startswith("annualized_capital_cost") or field.startswith("annualized_storage_capital_cost"):
                        fields_to_update[field] = getattr(group, field).data.loc[getattr(group, field).data.index.year == vintage].squeeze()
                    elif field == "potential" and getattr(group, field) is not None:
                        fields_to_update[field] = getattr(group, field).data.loc[getattr(group, field).data.index.year == vintage].squeeze()

                vintage_instance = group.copy(include_linkages=True, update=fields_to_update, new_class=vintage_class, exclude=["class_name"])
                setattr(vintage_instance, "vintage_parent_group", group.name)
                self.assets.update({vintage_instance.name: vintage_instance})

                # Add all linkages from the copy to self.linkages
                for linkage_attribute in vintage_instance.linkage_attributes:
                    linkage_key = vintage_instance.get_field_type(field_info=vintage_instance.model_fields[linkage_attribute])[-1].__name__
                    curr_linkage = getattr(vintage_instance, linkage_attribute).values()
                    if curr_linkage:
                        for linkage_instance in curr_linkage:
                            if linkage_key in self.linkages:
                                self.linkages[linkage_key].append(linkage_instance)
                            else:
                                self.linkages[linkage_key] = [linkage_instance]

                # Add all linkages from the copy to self.linkages
                for twl_attribute in vintage_instance.three_way_linkage_attributes:
                    twl_key = vintage_instance.get_field_type(
                        field_info=vintage_instance.model_fields[twl_attribute])[-1].__name__
                    curr_twl = getattr(vintage_instance, twl_attribute).values()
                    if curr_twl:
                        for twl_instance in curr_twl:
                            if twl_key in self.linkages:
                                self.three_way_linkages[twl_key].append(twl_instance)
                            else:
                                self.three_way_linkages[twl_key] = [twl_instance]


                # Create AssetToAssetGroup linkages & announce the linkages
                asset_linkage = AssetToAssetGroup(name=(vintage_instance.name, group.name), instance_from=vintage_instance,
                                      instance_to=group)
                if "AssetToAssetGroup" in self.linkages:
                    self.linkages["AssetToAssetGroup"].append(asset_linkage)
                else:
                    self.linkages["AssetToAssetGroup"] = [asset_linkage]
                asset_linkage.announce_linkage_to_instances()


            logger.debug("Cleaning up linkages")
            # I feel like other linkages should be removed, but I don't know what they are or how to do it efficiently
            # TODO: Make this faster
            # TODO: Create list of linkages to remove that can be added to.
            if "AssetToAssetGroup" in self.linkages:
                linkages_to_remove = []
                for linkage in self.linkages["AssetToAssetGroup"]:
                    if linkage.instance_from == group:
                        # Remove linkage from corresponding assets
                        del self.components[linkage.instance_from.name].asset_groups[linkage.instance_to.name]
                        del self.components[linkage.instance_to.name].assets[linkage.instance_from.name]

                        # Remove linkage from self.linkages
                        linkages_to_remove.append(linkage)

                self.linkages["AssetToAssetGroup"] = [l for l in self.linkages["AssetToAssetGroup"] if l not in linkages_to_remove]

            if "AssetToELCC" in self.linkages:
                linkages_to_remove = []
                for linkage in self.linkages["AssetToELCC"]:
                    if linkage.instance_from == group:
                        # Remove linkage from corresponding assets
                        del self.components[linkage.instance_from.name].elcc_surfaces[linkage.instance_to.name]
                        del self.components[linkage.instance_to.name].assets[linkage.instance_from.name]

                        # Remove linkage from self.linkages
                        linkages_to_remove.append(linkage)

                self.linkages["AssetToELCC"] = [l for l in self.linkages["AssetToELCC"] if
                                                      l not in linkages_to_remove]

            if "ResourceToReserve" in self.linkages:
                for linkage in self.linkages["ResourceToReserve"]:
                    if linkage.instance_from == group:
                        # If the incremental requirement hourly scalar depends on operational capacity, set that value
                        # to zero on the group to avoid double-counting
                        if linkage.scalar_type == IncrementalReserveType.OPERATIONAL_CAPACITY:
                            linkage.incremental_requirement_hourly_scalar = copy.deepcopy(
                                linkage.incremental_requirement_hourly_scalar
                            )
                            linkage.incremental_requirement_hourly_scalar.data[:] = 0

                        # Keep the linkages on both the member assets and the group to account for resource
                        # contributions to reserves. Only operational assets will have operational rules constructed
                        # and contribute to reserves.


            if "ReliabilityContribution" in self.linkages:
                linkages_to_remove = []
                for linkage in self.linkages["ReliabilityContribution"]:
                    if linkage.instance_from == group:
                        # Remove linkage from corresponding assets
                        del self.components[linkage.instance_from.name].prm_policies[linkage.instance_to.name]
                        if linkage.instance_from.name in self.components[linkage.instance_to.name].assets_:
                            del self.components[linkage.instance_to.name].assets_[linkage.instance_from.name]
                        if linkage.instance_from.name in self.components[linkage.instance_to.name].resources:
                            del self.components[linkage.instance_to.name].resources[linkage.instance_from.name]
                        if linkage.instance_from.name in self.components[linkage.instance_to.name].tx_paths:
                            del self.components[linkage.instance_to.name].tx_paths[linkage.instance_from.name]
                        if linkage.instance_from.name in self.components[linkage.instance_to.name].caiso_tx_constraints:
                            del self.components[linkage.instance_to.name].caiso_tx_constraints[linkage.instance_from.name]
                        if linkage.instance_from.name in self.components[linkage.instance_to.name].plants:
                            del self.components[linkage.instance_to.name].plants[linkage.instance_from.name]

                        # Remove linkage from self.linkages
                        linkages_to_remove.append(linkage)

                self.linkages["ReliabilityContribution"] = [l for l in self.linkages["ReliabilityContribution"] if
                                                l not in linkages_to_remove]

            if "ERMContribution" in self.linkages:
                linkages_to_remove = []
                for linkage in self.linkages["ERMContribution"]:
                    if linkage.instance_from == group:
                        if not group.aggregate_operations:
                            # Remove linkage from the group as operations will take place at the vintage level
                            del self.components[linkage.instance_from.name].erm_policies[linkage.instance_to.name]
                            if linkage.instance_from.name in self.components[linkage.instance_to.name].resources:
                                del self.components[linkage.instance_to.name].resources[linkage.instance_from.name]

                            # Remove linkage from self.linkages
                            linkages_to_remove.append(linkage)


                self.linkages["ERMContribution"] = [l for l in self.linkages["ERMContribution"] if
                                                l not in linkages_to_remove]

            if "AssetToCaisoTxConstraint" in self.linkages:
                linkages_to_remove = []
                for linkage in self.linkages["AssetToCaisoTxConstraint"]:
                    if linkage.instance_from == group:
                        # Remove linkage from corresponding assets
                        del self.components[linkage.instance_from.name].caiso_tx_constraints[linkage.instance_to.name]
                        del self.components[linkage.instance_to.name].assets[linkage.instance_from.name]

                        # Remove linkage from self.linkages
                        linkages_to_remove.append(linkage)

                self.linkages["AssetToCaisoTxConstraint"] = [l for l in self.linkages["AssetToCaisoTxConstraint"] if
                                                l not in linkages_to_remove]

            # For custom constraints, I think we want to **remove** the linkages to the groups so that we're not double-constraining
            if "CustomConstraintLinkage" in self.three_way_linkages:
                linkages_to_remove = []
                for linkage in self.three_way_linkages["CustomConstraintLinkage"]:
                    if linkage.linked_component == group:
                        # Remove linkage from corresponding components of the threeway linkage
                        del self.components[linkage.instance_1.name].custom_constraints[(linkage.instance_2.name, linkage.instance_3.name)]
                        del self.components[linkage.instance_2.name].custom_constraints[(linkage.instance_1.name, linkage.instance_3.name)]
                        del self.components[linkage.instance_3.name].custom_constraints[(linkage.instance_1.name, linkage.instance_2.name)]

                        # Remove linkage from self.linkages
                        linkages_to_remove.append(linkage)

                self.three_way_linkages["CustomConstraintLinkage"] = [l for l in self.three_way_linkages["CustomConstraintLinkage"] if l not in linkages_to_remove]

            # TODO: If group.aggregate_operations is TRUE, remove operations-related linkages from indvidual vintages (GHG, RPS, Reserves).
            #  Alternatively, remove asset-specific operational linkages on the asset class within the revalidate method.

        # For HybridStorageResourceToHybridVariableResource linkages, link the corresponding vintages constructed by each group
        if "HybridStorageResourceToHybridVariableResource" in self.linkages:
            for hybrid_storage_group in self.hybrid_storage_resource_groups.values():
                # Guard clause to skip this group if it didn't construct any vintages
                if "vintages_to_construct" not in hybrid_storage_group.model_fields_set:
                    continue
                # Find corresponding hybrid_variable_resource_group to which the storage group is linked
                linked_hybrid_variable_resource_group = [
                    r.instance_to for r in hybrid_storage_group.hybrid_variable_resources.values()
                    if isinstance(r.instance_to, HybridVariableResourceGroup)
                ]
                if len(linked_hybrid_variable_resource_group) > 1:
                    raise ValueError(f"A Hybrid Storage Resource Group can only have one Hybrid Variable Resource Group linked to it, "
                                     f"but {hybrid_storage_group.name} has multiple linked: {linked_hybrid_variable_resource_group}.")
                elif len(linked_hybrid_variable_resource_group) == 0:
                    raise ValueError(
                        f"A Hybrid Storage Resource Group must have exactly one Hybrid Variable Resource Group linked to it, "
                        f"but {hybrid_storage_group.name} has none linked.")
                else:
                    linked_hybrid_variable_resource_group = linked_hybrid_variable_resource_group[0]
                vintage_years = (
                        set(hybrid_storage_group.vintages_to_construct.data.loc[
                                hybrid_storage_group.vintages_to_construct.data == True].index.year) &
                        set(modeled_years.year)
                )
                vintages = []
                for name, vintage in self.hybrid_storage_resources.items():
                    for year in vintage_years:
                        if name == f"{hybrid_storage_group.name} ({year})":
                            vintages.append(vintage)
                if len(vintages) == 0:
                    continue

                linkages_to_remove = []
                for linkage in self.linkages["HybridStorageResourceToHybridVariableResource"]:
                    if linkage.instance_from == hybrid_storage_group and linkage.instance_to != linked_hybrid_variable_resource_group:
                        # Remove linkage from corresponding assets
                        del self.components[linkage.instance_from.name].hybrid_variable_resources[
                            linkage.instance_to.name]
                        del self.components[linkage.instance_to.name].hybrid_storage_resources[linkage.instance_from.name]

                        # Remove linkage from self.linkages
                        linkages_to_remove.append(linkage)

                    if linkage.instance_from in vintages:
                        # Remove all linkages except that of the one that links it to the hybrid variable resource vintage of the same year
                        vintage_year = [year for year in vintage_years if str(year) in linkage.instance_from.name][0]
                        if f"({vintage_year})" not in linkage.instance_to.name:
                            # Remove linkage from corresponding assets
                            del self.components[linkage.instance_from.name].hybrid_variable_resources[
                                linkage.instance_to.name]
                            del self.components[linkage.instance_to.name].hybrid_storage_resources[
                                linkage.instance_from.name]

                            # Remove linkage from self.linkages
                            linkages_to_remove.append(linkage)

                self.linkages["HybridStorageResourceToHybridVariableResource"] = [l for l in self.linkages["HybridStorageResourceToHybridVariableResource"] if
                                                             l not in linkages_to_remove]


    def announce_linkages_to_instances(self):
        for linkage_type, linkage_instances in self.linkages.items():
            if len(linkage_instances) == 0:
                continue
            for linkage_instance in tqdm(
                linkage_instances,
                desc=f"Connecting {linkage_type}".rjust(50),
                bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
            ):
                logger.debug(
                    f"Announcing linkage between '{linkage_instance.instance_from.name}', '{linkage_instance.instance_to.name}'"
                )
                linkage_instance.announce_linkage_to_instances()


    def announce_three_way_linkages_to_instances(self):
        for linkage_type, linkage_instances in self.three_way_linkages.items():
            for linkage_instance in tqdm(
                linkage_instances,
                desc=f"Loading {linkage_type}".rjust(50),
                bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
            ):
                logger.debug(
                    f"Announcing linkage between '{linkage_instance.instance_1.name}', '{linkage_instance.instance_2.name}', '{linkage_instance.instance_3.name}'"
                )
                linkage_instance.announce_linkage_to_instances()

    @classmethod
    @timer
    def _construct_component_fields(cls, dir_str: DirStructure, system_name: str, scenarios: list[str]):
        # Read the list of components in the system
        components_to_load = pd.read_csv(dir_str.data_interim_dir / "systems" / system_name / "components.csv")
        # Filter components using scenario tags
        components_to_load = _filter_highest_scenario(df=components_to_load, scenarios=scenarios)
        # Drop any components which are flagged as not included
        components_to_load = components_to_load.loc[components_to_load["include"], ["component", "instance"]]
        # Group by component class
        components_to_load = components_to_load.groupby("component")

        # Populate component attributes with data from instance CSV files
        # Get field class by introspecting the field info
        components_constructed = Parallel()(delayed(cls._construct_components_of_type)(component_dict_name, components_to_load, dir_str,
                                              field_info, scenarios) for component_dict_name, field_info in cls._component_fields().items())

        # Populate the component_fields dict
        component_fields = {}
        for component_type in components_constructed:
            component_fields.update(component_type)

        return component_fields

    @classmethod
    def _construct_components_of_type(cls, component_dict_name, components_to_load, dir_str,
                                      field_info, scenarios):
        dict = {}
        field_types = cls.get_field_type(field_info=field_info)[-1]
        if field_types == Asset:
            field_types = [field_types] + list({name for name in Asset.get_subclasses() if "Group" not in name.__name__})
        elif field_types == AssetGroup:
            field_types = [field_types] + list({name for name in AssetGroup.get_subclasses() if "Group" in name.__name__})
        elif field_types == Product:
            field_types = [field_types] + list(
                {name for name in Product.get_subclasses() if "Group" not in name.__name__})
        elif field_types == Demand:
            field_types = [field_types] + list(
                {name for name in Demand.get_subclasses() if "Group" not in name.__name__})
        else:
            field_types = [field_types]
        for field_type in field_types:
            field_data_filepath = field_type.SAVE_PATH

            if field_type.__name__ not in components_to_load.groups:
                logger.debug(f"Component type {field_type.__name__} not loaded because component type not recognized")
                # Escape this method
            else:
                dict.update(cls._update_component_attrs(
                    dir_str=dir_str,
                    field_type=field_type,
                    component_data_subfolder=field_data_filepath,
                    components_to_load=components_to_load.get_group(field_type.__name__)["instance"].values.tolist(),
                    scenarios=scenarios,
                ))

        return {component_dict_name: dict}

    @classmethod
    def _update_component_attrs(
        cls,
        *,
        dir_str: DirStructure,
        field_type: Component,
        component_data_subfolder: str,
        components_to_load: list[str],
        scenarios: list[str],
    ) -> dict | None:
        """Load all components of a certain type listed in `components_to_load`."""
        components = {}

        for component_name in tqdm(
            components_to_load,
            desc=f"Loading {field_type.__name__}:".rjust(50),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            # by convention, the dir name is the name of the component dictionary
            # the following line is just a way to get an attribute's (component_dict) name
            if (dir_str.data_interim_dir / component_data_subfolder / f"{component_name}.csv").exists():
                curr_component = field_type.from_csv(
                    dir_str.data_interim_dir / component_data_subfolder / f"{component_name}.csv", scenarios=scenarios)
            else:
                curr_component = field_type(name=component_name)
            if curr_component.name in components:
                raise ValueError(f"The following Component name is duplicated: {curr_component.name}")
            components[curr_component.name] = curr_component

        return components

    @classmethod
    @timer
    def _construct_linkages(
        cls,
        *,
        dir_str: DirStructure,
        system_name: str,
        linkage_subclasses_to_load: list,
        linkage_type: str,
        scenarios: list[str],
        component_by_type: dict[str, dict[str, Component]],
    ):
        # Flatten the nested dictionary of system components into a single dictionary
        all_components_dict = {
            component_name: component
            for subdict in component_by_type.values()
            for component_name, component in subdict.items()
        }
        constructed_linkages = {}
        """This function now can be used to initialize both two- and three-way linkages."""
        if (dir_str.data_interim_dir / "systems" / system_name / f"{linkage_type}.csv").exists():
            linkages_to_load = pd.read_csv(dir_str.data_interim_dir / "systems" / system_name / f"{linkage_type}.csv")
            linkages_to_load = cls._get_scenario_linkages(linkages=linkages_to_load, scenarios=scenarios)
            linkages_to_load = linkages_to_load.groupby("linkage")

            for linkage_class in linkage_subclasses_to_load:
                # If no linkages of this class type specified by user, skip this iteration of the loop (`continue` keyword)
                if linkage_class.__name__ not in linkages_to_load.groups:
                    logger.debug(
                        f"Linkage type {linkage_class.__name__} not loaded because linkage type not recognized"
                    )
                elif linkage_type == "linkages":
                    # Assume the data/interim folder has the same name as the file that lists the linkages
                    constructed_linkages[linkage_class.__name__] = linkage_class.from_dir(
                        dir_path=dir_str.data_interim_dir / f"{linkage_type}",
                        linkages_df=linkages_to_load.get_group(linkage_class.__name__),
                        components_dict=all_components_dict,
                        scenarios=scenarios,
                        linkages_csv_path=dir_str.data_interim_dir / "systems" / system_name / f"{linkage_type}.csv",
                    )
                elif linkage_type == "three_way_linkages":
                    constructed_linkages[linkage_class.__name__] = linkage_class.from_dir(
                        dir_path=dir_str.data_interim_dir / f"{linkage_type}",
                        linkage_pairs=linkages_to_load.get_group(linkage_class.__name__),
                        components_dict=all_components_dict,
                        scenarios=scenarios,
                    )

        return constructed_linkages

    @pydantic.model_validator(mode="before")
    def _validate_no_duplicated_component_names(cls, values: dict[str, Any]):
        component_names_by_field = {
            component_field: values[component_field].keys()
            for component_field in cls._component_fields().items()
            if component_field in values
        }

        component_name_counts = Counter()
        for component_names in component_names_by_field.values():
            component_name_counts.update(component_names)

        errors = {}
        for component_name, count in component_name_counts.items():
            if count > 1:
                errors[component_name] = [
                    component_type
                    for component_type in component_names_by_field
                    if component_name in component_names_by_field[component_type]
                ]

        if len(errors) > 0:
            raise ValueError(
                f"The following names were duplicated across different Component types: {pprint.pformat(errors)}"
            )

        return values

    def _validate_electricity_products_and_linkages(self):
        resource_flag = any(isinstance(component, GenericResource) for component in self.assets.values()
                         or any(isinstance(component, GenericResourceGroup) for component in self.asset_groups.values()))


        plant_flag = any(isinstance(component, Plant) for component in self.assets.values()
                         or any(isinstance(component, PlantGroup) for component in self.asset_groups.values()))

        if resource_flag and plant_flag:
            optimization_style = "mixed electric-fuels optimization"
        elif resource_flag:
            optimization_style = "pure electric-sector optimization"
        elif plant_flag:
            optimization_style = "pure fuels-sector optimization"
        else:
            raise NotImplementedError(
                "No supply-side resources or plants are specified. There is nothing to optimize"
            )

        if sum(isinstance(product, Electricity) for product in self.products.values()) > 1:
            raise ValidationError(
                "There can be no more than one `Electricity` product in the system."
            )
        elif sum(isinstance(product, Electricity) for product in self.products.values()) == 1:
            product = [product for product in self.products.values() if isinstance(product, Electricity)][0]
            if product.commodity and resource_flag:
                raise ValidationError(
                    f"For {optimization_style}, a non-commodity `Electricity` instance "
                    f"must be specified. Please update `Electricity` instance {product.name} or remove all `Resource` "
                    f"instances from the system."
                )

        if not any(isinstance(product, Electricity) for product in self.products.values()):
            if "electric" in optimization_style:
                logger.warning(
                    f"For {optimization_style}, one non-commodity `Electricity` product must be "
                    "specified. Instantiating one now..."
                )
                # Instantiate non-commodity electricity
                self.products["Electricity"] = Electricity(name="Electricity", commodity=False)

                # Create ZoneToProduct key in system.linkages if it doesn't exist
                if "ZoneToProduct" not in self.linkages:
                    self.linkages["ZoneToProduct"] = []

                # Link all zones to new Electricity product
                for zone in self.zones.values():
                    linkage_instance = ZoneToProduct(
                        name=(zone.name, "Electricity"),
                        instance_from=zone,
                        instance_to=self.products["Electricity"],
                    )
                    self.linkages["ZoneToProduct"].append(linkage_instance)
                    linkage_instance.announce_linkage_to_instances()

    @staticmethod
    def _get_scenario_linkages(*, linkages: pd.DataFrame, scenarios: list):
        """Filter for the highest priority data based on scenario tags."""

        # Create/fill a dummy (base) scenario tag that has the lowest priority order
        if "scenario" not in linkages.columns:
            linkages["scenario"] = "__base__"
        # Create a dummy (base) scenario tag that has the lowest priority order
        linkages["scenario"] = linkages["scenario"].fillna("__base__")

        # Create a categorical data type in the order of the scenario priority order (lowest to highest)
        linkages["scenario"] = pd.Categorical(linkages["scenario"], ["__base__"] + scenarios)

        # Drop any scenarios that weren't provided in the scenario list (or the default `__base__` tag)
        len_linkages_unfiltered = len(linkages)
        linkages = linkages.sort_values("scenario").dropna(subset="scenario")

        # Log error if scenarios filtered out all data
        if len_linkages_unfiltered != 0 and len(linkages) == 0:
            err = f"No linkages for active scenario(s): {scenarios}. "
            logger.error(err)

        # Keep only highest priority scenario data
        linkages = linkages.groupby([x for x in linkages.columns if x != "scenario"]).last().reset_index()

        return linkages

    def remove_component(self, component_name: str):
        """Deletes a Component from the system and deletes all linkages associated with it.

        Args:
            component_name: the name of the component to remove
        """
        # Iterate over all component_fields of the System to find the Component, so that it can be deleted
        for field in self._component_fields():
            curr_component_dict = getattr(self, field)
            if component_name in curr_component_dict:
                component_to_delete = curr_component_dict[component_name]

                # Iterate over all Linkages on the Component, delete them from the linkage attributes of the other
                #  components it was linked to, remove the Linkage from the system, and then delete the Linkage object
                for linkage_attr_name in component_to_delete.linkage_attributes:
                    for linkage_name, linkage_object in getattr(component_to_delete, linkage_attr_name).items():
                        if linkage_object.instance_from is component_to_delete:
                            linked_component = linkage_object.instance_to
                            linked_component_attr_to_edit = linkage_object.component_type_from_
                        elif linkage_object.instance_to is component_to_delete:
                            linked_component = linkage_object.instance_from
                            linked_component_attr_to_edit = linkage_object.component_type_to_
                        else:
                            raise ValueError(
                                f"Component to delete `{component_name}` not found in attached Linkage object `{linkage_name}`."
                            )

                        del getattr(linked_component, linked_component_attr_to_edit)[component_name]

                        self.linkages[linkage_object.__class__.__name__].remove(linkage_object)

                        del linkage_object

                # Iterate over all ThreeWayLinkages on the Component, delete them from the linkage attributes of the
                # other components it was linked to, remove the ThreeWayLinkage from the system, and then delete the
                #  ThreeWayLinkage object
                for three_way_linkage_attr_name in component_to_delete.three_way_linkage_attributes:
                    for three_way_linkage_name, three_way_linkage_object in getattr(component_to_delete, three_way_linkage_attr_name).items():
                        if three_way_linkage_object.instance_1 is component_to_delete:
                            linked_component_1 = three_way_linkage_object.instance_2
                            linked_component_2 = three_way_linkage_object.instance_3
                            name_to_delete_1 = (component_name, linked_component_2.name)
                            name_to_delete_2 = (component_name, linked_component_1.name)
                        elif three_way_linkage_object.instance_2 is component_to_delete:
                            linked_component_1 = three_way_linkage_object.instance_1
                            linked_component_2 = three_way_linkage_object.instance_3
                            name_to_delete_1 = (component_name, linked_component_2.name)
                            name_to_delete_2 = (linked_component_1.name, component_name)
                        elif three_way_linkage_object.instance_3 is component_to_delete:
                            linked_component_1 = three_way_linkage_object.instance_1
                            linked_component_2 = three_way_linkage_object.instance_2
                            name_to_delete_1 = (linked_component_2.name, component_name)
                            name_to_delete_2 = (linked_component_1.name, component_name)
                        else:
                            raise ValueError(
                                f"Component to delete `{component_name}` not found in attached Linkage object `{three_way_linkage_name}`."
                            )

                        del getattr(linked_component_1, three_way_linkage_object._attribute_to_announce)[name_to_delete_1]
                        del getattr(linked_component_2, three_way_linkage_object._attribute_to_announce)[name_to_delete_2]

                        self.three_way_linkages[three_way_linkage_object.__class__.__name__].remove(three_way_linkage_object)

                        del three_way_linkage_object

                del curr_component_dict[component_name]
                del component_to_delete

                gc.collect()

    def remove_unused_components(self, modeled_years: tuple[int, int]):
        """Remove Components from the System if they are unable to be modeled based on the set of desired modeled years.

        Currently, this method only does the following:
        * Removes Assets from the System if their build year is later than the max modeled year.
        * Removes AssetGroups from the System if they have no Assets linked to them (either due to an input data mistake
          or because all of its linked Assets were removed due to the above condition)

        Args:
            modeled_years: tuple of min and max modeled year
        """
        components_to_remove = []
        for asset_ in self.assets.values():
            if asset_.build_year > pd.Timestamp(year=max(modeled_years), month=1, day=1):
                components_to_remove.append(asset_.name)
        if len(components_to_remove) > 0:
            component_list_str = "\n · ".join(components_to_remove)
            logger.warning(
                f"{len(components_to_remove)} components were removed from the System  because their build years were set later than "
                f"the maximum modeled year for this case ({max(modeled_years)}):\n · {component_list_str}"
            )
        for component in components_to_remove:
            self.remove_component(component)

        components_to_remove = []
        for asset_group in self.asset_groups.values():
            no_vintages_within_modeled_year_range = not any(
                modeled_years[0] <= year <= modeled_years[1]
                for year in asset_group.vintages_to_construct.data[asset_group.vintages_to_construct.data].index.year
            )
            if len(asset_group.assets) == 0 and no_vintages_within_modeled_year_range:
                components_to_remove.append(asset_group.name)
        if len(components_to_remove) > 0:
            component_list_str = "\n · ".join(components_to_remove)
            logger.warning(
                f"{len(components_to_remove)} asset groups were removed from the System  because they were not linked to "
                f"any assets nor had any vintages to construct within the modeling horizon:\n · {component_list_str}"
            )
        for component in components_to_remove:
            self.remove_component(component)

    @timer
    def resample_ts_attributes(
        self,
        modeled_years: tuple[int, int],
        weather_years: tuple[int, int],
        resample_weather_year_attributes: bool = True,
        resample_non_weather_year_attributes: bool = True,
    ):
        """Interpolate/extrapolate timeseries attributes so that they're all defined for the range of modeled years.

        Args:
            modeled_years: tuple of min and max modeled year
            weather_years: tuple of min and max weather year
            resample_weather_year_attributes: whether to resample modeled-year-indexed attributes
            resample_non_weather_year_attributes: whether to resample weather-year-indexed attributes
        """

        # Dictionary of objects & their attributes that were extrapolated (i.e., start/end dates too short)
        extrapolated = {}
        extrapolated_attrs = Parallel()(delayed(instance.resample_ts_attributes)(
                modeled_years,
                weather_years,
                resample_weather_year_attributes=resample_weather_year_attributes,
                resample_non_weather_year_attributes=resample_non_weather_year_attributes,
            ) for instance in tqdm(
            self.components.values(),
            desc=f"Resampling timeseries attributes".rjust(50),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ))
        for attr in extrapolated_attrs:
            if isinstance(attr, dict):
                extrapolated.update(attr)

        # TODO: When load becomes a subclass of demand, we should eliminate this double loop
        # Demand treated differently: forecast future demand
        for instance in self.demands.keys():
            self.demands[instance].forecast_demand(modeled_years, weather_years)

        # Load treated differently: forecast future load
        Parallel()(delayed(self.loads[instance].forecast_load)(modeled_years, weather_years) for instance in tqdm(self.loads.keys(),
            desc=f"Forecasting load components".rjust(50),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",))

        # ELCC treated differently
        for inst in self.elcc_surfaces.keys():
            for facet in self.elcc_surfaces[inst].facets:
                extrapolated[inst] = (
                    self.elcc_surfaces[inst]
                    .facets[facet]
                    .resample_ts_attributes(
                        modeled_years,
                        weather_years,
                        resample_weather_year_attributes=resample_weather_year_attributes,
                        resample_non_weather_year_attributes=resample_non_weather_year_attributes,
                    )
                )

        # Regularize timeseries attributes, if any, in linkages (same as components above)
        for linkage_class in self.linkages:
            for linkage_inst in self.linkages[linkage_class]:
                extrapolated[", ".join(linkage_inst.name)] = linkage_inst.resample_ts_attributes(
                    modeled_years,
                    weather_years,
                    resample_weather_year_attributes=resample_weather_year_attributes,
                    resample_non_weather_year_attributes=resample_non_weather_year_attributes,
                )

        # Regularize timeseries attributes, if any, in three way linkages (same as components above)
        for three_way_linkage_class in self.three_way_linkages:
            for three_way_linkage_inst in self.three_way_linkages[three_way_linkage_class]:
                extrapolated[three_way_linkage_inst.name] = three_way_linkage_inst.resample_ts_attributes(
                    modeled_years,
                    weather_years,
                    resample_weather_year_attributes=resample_weather_year_attributes,
                    resample_non_weather_year_attributes=resample_non_weather_year_attributes,
                )

        # loads to policies
        for inst in self.policies.keys():
            self.policies[inst].update_targets_from_loads()
            if isinstance(self.policies[inst], EnergyReserveMargin):
                self.policies[inst].update_targets_to_weather_year_index(modeled_years=modeled_years, weather_years=weather_years)

        if extrapolated := {str(k): list(v) for k, v in extrapolated.items() if v is not None}:
            logger.debug(
                f"The following timeseries attributes were extrapolated to cover model years: \n{dumps(extrapolated, indent=4)}"
            )

    @property
    def linkage_attributes(self) -> list[str]:
        return ["linkages", "three_way_linkages"]

    @classmethod
    def from_csv(cls, filename: pathlib.Path, scenarios: list = [], data: dict = {}):
        ###########################################
        # READ IN COMPONENTS & LINKAGES FROM FILE #
        ###########################################
        component_fields = cls._construct_component_fields(
            dir_str=data["dir_str"], system_name=filename.parent.stem, scenarios=scenarios
        )
        cls._validate_no_duplicated_component_names(component_fields)

        linkages = cls._construct_linkages(
            dir_str=data["dir_str"],
            system_name=filename.parent.stem,
            linkage_subclasses_to_load=LINKAGE_TYPES,
            linkage_type="linkages",
            scenarios=scenarios,
            component_by_type=component_fields,
        )
        three_way_linkages = cls._construct_linkages(
            dir_str=data["dir_str"],
            system_name=filename.parent.stem,
            linkage_subclasses_to_load=THREE_WAY_LINKAGE_TYPES,
            linkage_type="three_way_linkages",
            scenarios=scenarios,
            component_by_type=component_fields,
        )

        # Construct System
        attrs = {
            **{"name": filename.parent.stem, "scenarios": scenarios},
            **component_fields,
            **{"linkages": linkages},
            **{"three_way_linkages": three_way_linkages},
            **data,
        }
        return attrs["name"], cls(**attrs)

    @classmethod
    def from_json(cls, filepath: pathlib.Path, data: dict = {}):
        json_system_data = json.load(open(filepath / "selected_system.json"))
        system_dict = pydantic_core.from_json(json_system_data)

        system_name = system_dict["name"]
        scenarios = system_dict["scenarios"]

        component_fields = cls._construct_component_fields_from_json(filepath)
        linkages = cls._construct_linkages_from_json(filepath, "linkages")
        three_way_linkages = cls._construct_linkages_from_json(filepath, "three_way_linkages")

        # Construct System
        attrs = {
            **{"name": system_name, "scenarios": scenarios},
            **component_fields,
            **{"linkages": linkages},
            **{"three_way_linkages": three_way_linkages},
            **data,
        }

        return cls(**attrs)

    @classmethod
    def _construct_component_fields_from_json(cls, filepath: pathlib.Path):

        # Get keys of non-empty component fields dicts
        component_types_to_construct = [
            component_type for component_type in cls._component_fields().keys()
            if os.path.isdir(filepath / component_type)
            and component_type not in ['erm_policies', 'prm_policies']  # remove policies related to inv decisions
        ]

        # Populate the component_fields dict
        component_fields = {}
        for component_type in component_types_to_construct:
            component_type_dict = {}
            for filename in tqdm(
                    os.listdir(filepath / component_type),
                    desc=f"Loading {component_type}".rjust(50),
                    bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
            ):
                component_name, _ = os.path.splitext(filename)
                constructed_component = cls._construct_component_from_json(
                    filepath,
                    component_type=component_type,
                    component_name=component_name,
                )
                component_type_dict[component_name] = constructed_component

            component_fields[component_type] = component_type_dict

        return component_fields

    @classmethod
    def _construct_linkages_from_json(cls, filepath: pathlib.Path, linkage_type: str):

        linkages_dict = {}

        if linkage_type == "linkages":
            linkage_type_dict = LINKAGE_TYPE_DICT
        else:
            linkage_type_dict = THREE_WAY_LINKAGE_TYPE_DICT

        linkage_keys_to_construct = [
            linkage_key for linkage_key in linkage_type_dict.keys()
            if os.path.isdir(filepath / linkage_type / linkage_key)
            and linkage_key not in ['ReliabilityContribution', 'ERMContribution'] # remove linkages related to inv decisions
        ]

        for linkage_key in tqdm(
            linkage_keys_to_construct,
            desc=f"Loading {linkage_type}".rjust(50),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            linkage_key_list = []
            for filename in os.listdir(filepath / linkage_type / linkage_key):
                component_name, _ = os.path.splitext(filename)
                constructed_component = cls._construct_component_from_json(
                    filepath,
                    component_type=linkage_type,
                    component_name=component_name,
                    linkage_key=linkage_key,
                )
                linkage_key_list.append(constructed_component)

            linkages_dict[linkage_key] = linkage_key_list

        return linkages_dict

    @classmethod
    def _construct_component_from_json(
            cls, filepath: pathlib.Path,
            component_type: str,
            component_name: str,
            linkage_key: str = "",
    ):
        """

        Args:
            filepath: example PosixPath('reports/resolve/{system_name}/{timestamp}/json')
            component_type: "assets", "asset_groups", "linkages", "three_way_linkages"
            linkage_key: if component_type is "linkages" or "three_way_linkages", example "ResourceToZone"; else empty
            component_name:

        Returns:

        """

        # Read json data as dict
        json_component_data = json.load(open((filepath / component_type / linkage_key / component_name).with_suffix(".json")))
        component_dict = pydantic_core.from_json(json_component_data)

        # Get original class of component instance
        if linkage_key:
            component_class = cls._get_component_class(linkage_key, class_name="", linkage_type=component_type)
        else:
            class_name = component_dict["class_name"]
            component_class = cls._get_component_class(component_type, class_name)

        constructed_component = component_class.model_validate_json(json_component_data)
        return constructed_component

    @classmethod
    def _get_component_class(cls, component_type: str, class_name: str, linkage_type: str = ""):
        if linkage_type == "linkages":
            return LINKAGE_TYPE_DICT[component_type]
        elif linkage_type == "three_way_linkages":
            return THREE_WAY_LINKAGE_TYPE_DICT[component_type]
        else:
            if component_type in COMPONENT_TYPES_TO_RECONSTRUCT_DICT.keys():
                return COMPONENT_TYPES_TO_RECONSTRUCT_DICT[component_type].get(class_name)
            else:
                return typing.get_args(cls._component_fields()[component_type].annotation)[1]

    def custom_model_dump_json(self, output_resolve_dir: pathlib.Path, exclude_from_all_components: set = set()):
        # TODO: exclude_from_components (e.g., selected_capacity) if not saving to run PCM with this system

        # Resolve system output json file location
        output_json_dir = output_resolve_dir / "json"
        os.makedirs(output_json_dir, exist_ok=True)

        # Save system to json file
        with open(output_json_dir / "selected_system.json", "w", encoding="utf-8") as f:
            json.dump(self.model_dump_json(include={"name", "scenarios"}), f, ensure_ascii=False, indent=4)

        # Save components to json files
        for component_type, component_type_dict in tqdm(
            self.components_by_type.items(),
            desc="Saving system components to json files".rjust(50),
        ):
            if component_type_dict:
                component_type_output_dir = output_json_dir / component_type
                os.makedirs(component_type_output_dir, exist_ok=True)

                for component_name, component in component_type_dict.items():
                    # Exclude linkage dict attributes in components - will be re-added to components when
                    # system.__init__ calls announce_linkages_to_instances()
                    exclude = exclude_from_all_components | set(component.linkage_attributes) | set(component.three_way_linkage_attributes)
                    # Don't save power_output_max profile for variable resources (don't want to re-use resampled profile in 8760 simulation)
                    if isinstance(component, VariableResource):
                        exclude = {"power_output_max"} | exclude
                    # Save component to json file
                    with open((component_type_output_dir / component.name).with_suffix(".json"), "w", encoding="utf-8") as f:
                        json.dump(component.model_dump_json(exclude=exclude), f, ensure_ascii=False, indent=4)

        # Save linkages to json files
        linkage_output_dir = output_json_dir / "linkages"
        for linkage_type, linkage_list in tqdm(
            self.linkages.items(),
            desc="Saving linkages to json files".rjust(50),
        ):
            linkage_type_output_dir = linkage_output_dir / linkage_type
            os.makedirs(linkage_type_output_dir, exist_ok=True)

            for linkage in linkage_list:
                # Save each linkage component to json file
                with open((linkage_type_output_dir / str(linkage.name)).with_suffix(".json"), "w", encoding="utf-8") as f:
                    json.dump(linkage.model_dump_json(), f, ensure_ascii=False, indent=4)

        # Save three-way-linkages to json files
        three_way_linkage_output_dir = output_json_dir / "three_way_linkages"
        for linkage_type, linkage_list in tqdm(
                self.three_way_linkages.items(),
                desc="Saving three-way-linkages to json files".rjust(50),
        ):
            linkage_type_output_dir = three_way_linkage_output_dir / linkage_type
            os.makedirs(linkage_type_output_dir, exist_ok=True)

            for linkage in linkage_list:
                # Save each three_way_linkage component to json file
                with open((linkage_type_output_dir / str(linkage.name)).with_suffix(".json"), "w", encoding="utf-8") as f:
                    json.dump(linkage.model_dump_json(), f, ensure_ascii=False, indent=4)

    def relink(self):
        """
        Re-link components so that system is equivalent after creating from json.
        Ensures linkages are references to a component, not copies
        """
        for linkage_type, linkage_instances in self.linkages.items():
            for x, linkage_instance in enumerate(linkage_instances):
                logger.debug(
                    f"Updating linkage between '{linkage_instance.instance_from.name}', '{linkage_instance.instance_to.name}'"
                )

                linkage_class = LINKAGE_TYPE_DICT.get(linkage_type)
                new_linkage = linkage_class.construct(**linkage_instance.__dict__)
                self.linkages[linkage_type][x] = new_linkage
                self.linkages[linkage_type][x].instance_to = self.components.get(new_linkage.instance_to.name)
                self.linkages[linkage_type][x].instance_from = self.components.get(new_linkage.instance_from.name)
                if linkage_type == "AllToPolicy":
                    self.linkages[linkage_type][x].component_type_from_ = self.linkages[linkage_type][x]._get_component_type_from_()
                    self.linkages[linkage_type][x].component_type_to_ = self.linkages[linkage_type][x]._get_component_type_to_()

        for linkage_type, linkage_instances in self.three_way_linkages.items():
            for x, linkage_instance in enumerate(linkage_instances):
                logger.debug(
                    f"Updating linkage between '{linkage_instance.instance_1.name}', '{linkage_instance.instance_2.name}', '{linkage_instance.instance_3.name}'"
                )
                linkage_class = THREE_WAY_LINKAGE_TYPE_DICT.get(linkage_type)
                new_linkage = linkage_class.construct(**linkage_instance.__dict__)
                self.three_way_linkages[linkage_type][x] = new_linkage
                self.three_way_linkages[linkage_type][x].instance_1 = self.components.get(
                    new_linkage.instance_1.name)
                self.three_way_linkages[linkage_type][x].instance_2 = self.components.get(
                    new_linkage.instance_2.name)
                self.three_way_linkages[linkage_type][x].instance_3 = self.components.get(
                    new_linkage.instance_3.name)

    def copy(self):
        components = {
            component_type: {component.name: component.copy() for component in getattr(self, component_type).values()}
            for component_type in self._component_fields()
        }

        linkages = {linkage_subclass: [] for linkage_subclass in self.linkages.keys()}
        for linkage_subclass, linkage_instances in self.linkages.items():
            for linkage_instance in linkage_instances:
                linkages[linkage_subclass].append(
                    linkage_instance.model_copy(
                        update={
                            "instance_from": [
                                component
                                for component_dict in components.values()
                                for component in component_dict.values()
                                if component.name == linkage_instance.name_from
                            ][0],
                            "instance_to": [
                                component
                                for component_dict in components.values()
                                for component in component_dict.values()
                                if component.name == linkage_instance.name_to
                            ][0],
                        }
                    )
                )

        three_way_linkages = {three_way_linkage_type: [] for three_way_linkage_type in self.three_way_linkages.keys()}
        for three_way_linkage_subclass, three_way_linkage_instances in self.three_way_linkages.items():
            for three_way_linkage_instance in three_way_linkage_instances:
                three_way_linkages[three_way_linkage_subclass].append(
                    three_way_linkage_instance.model_copy(
                        update={
                            "instance_1": [
                                component
                                for component_dict in components.values()
                                for component in component_dict.values()
                                if component.name == three_way_linkage_instance.instance_1.name
                            ][0],
                            "instance_2": [
                                component
                                for component_dict in components.values()
                                for component in component_dict.values()
                                if component.name == three_way_linkage_instance.instance_2.name
                            ][0],
                            "instance_3": [
                                component
                                for component_dict in components.values()
                                for component in component_dict.values()
                                if component.name == three_way_linkage_instance.instance_3.name
                            ][0],
                        }
                    )
                )

        return System(
            **components,
            linkages=linkages,
            three_way_linkages=three_way_linkages,
            name=copy.deepcopy(self.name),
            dir_str=self.dir_str.copy(),
        )

    def construct_operational_groups(self):
        # TODO (2024-12-18): This does not seem to be working properly. Investigation needed to correct this.
        #  Plant groups should also be added to this functionality once it's working properly.
        """Constructs instances of AssetGroup subclasses for groups of operationally equivalent Asset subclasses in the
        System (i.e., **automatically** identifying groups to construct.

        For each Asset subclass that has a corresponding Group class defined, unique groups of "operationally equivalent"
        Assets will be identified, a new instance of the Group class will be created, and the individual Assets will be
        linked to the Group.
        """
        # Iterate over the types of Assets with groups
        # Note: this loop must be expanded manually if new types of groups are defined
        for component_dict, group_class, group_dict in [
            # (self.generic_resources, GenericResourceGroup, self.generic_resource_groups),
            (self.solar_resources, SolarResourceGroup, self.solar_resource_groups),
            (self.wind_resources, WindResourceGroup, self.wind_resource_groups),
            (self.hydro_resources, HydroResourceGroup, self.hydro_resource_groups),
            (self.thermal_resources, ThermalResourceGroup, self.thermal_resource_groups),
            (self.storage_resources, StorageResourceGroup, self.storage_resource_groups),
        ]:
            # Skip if there are no resources of this type in the system
            if len(component_dict) == 0:
                continue

            # Check if UC resources are in component_dict
            # TODO: implement operational equality checks for UC resources
            if any(isinstance(v, UnitCommitmentResource) for v in component_dict.values()):
                logger.warning("Creating operational groups of UC resources is not implemented yet. "
                               "These resources will not be grouped.")

            # Remove components from list if they are UC resources or they already belong to an operational group
            component_list = list(component_dict.values())
            for comp in list(component_dict.values()):
                # TODO: Remove this first if-clause after above TODO is complete.
                if isinstance(comp, UnitCommitmentResource):
                    component_list.remove(comp)
                if comp.operational_group is not None:
                    component_list.remove(comp)

            # Skip if there are no resources of this type in the system
            if len(component_list) == 0:
                continue

            # Use the group's constructor method to identify and create groups
            operational_groups, _ = group_class.construct_operational_groups(
                component_list, skip_single_member_groups=True
            )

            # Check that none of the newly created groups have names that would override an existing group
            for new_group_instance in operational_groups.values():
                if new_group_instance.name in group_dict:
                    raise ValueError(
                        f"Automatically created operational group `{new_group_instance.name}` has a name that conflicts"
                        f" with an existing group instance. Please change the name of the asset group in your input data."
                    )
            group_dict.update(operational_groups)

            # TRYING TO SIMPLIFY THIS HARD-CODED LOGIC
            # for group_name, group in self.asset_groups.items():
            #     components_to_group = group.asset_instances.values()
            #     group_class = group.__class__
            #     # Use the group's constructor method to identify and create groups
            #     operational_groups, _ = group_class.construct_operational_groups(
            #         components_to_group, skip_single_member_groups=True
            #     )
            #     # Check that none of the newly created groups have names that would override an existing group
            #     for new_group_instance in operational_groups.values():
            #         if new_group_instance.name in self.asset_groups:
            #             raise ValueError(
            #                 f"Automatically created operational group `{new_group_instance.name}` has a name that conflicts"
            #                 f" with an existing group instance. Please change the name of the asset group in your input data."
            #             )
            #     self.asset_groups.update(operational_groups)


            # Add the linkages defined on each of the new Group instances to the list of linkages in the System
            for group_instance in operational_groups.values():
                for linkage_attr in group_instance.linkage_attributes:
                    for linkage_instance in getattr(group_instance, linkage_attr).values():
                        linkage_cls = linkage_instance.__class__.__name__
                        if linkage_cls not in self.linkages:
                            self.linkages[linkage_cls] = [linkage_instance]
                        else:
                            self.linkages[linkage_cls].append(linkage_instance)
                for three_way_linkage_attr in group_instance.three_way_linkage_attributes:
                    for three_way_linkage_instance in getattr(group_instance, three_way_linkage_attr).values():
                        linkage_cls = three_way_linkage_instance.__class__.__name__
                        if linkage_cls not in self.linkages:
                            self.linkages[linkage_cls] = [three_way_linkage_instance]
                        else:
                            self.linkages[linkage_cls].append(three_way_linkage_instance)

                # Append group to system
                logger.info(f"Appending AssetGroup {group_instance.name} to system.")
                self.asset_groups |= {group_instance.name: group_instance}


def _filter_highest_scenario(df: pd.DataFrame, scenarios: list):
    # Create/fill a dummy (base) scenario tag that has the lowest priority order
    if "scenario" not in df.columns:
        df["scenario"] = "__base__"
    # Create a dummy (base) scenario tag that has the lowest priority order
    df["scenario"] = df["scenario"].fillna("__base__")

    # Create a categorical data type in the order of the scenario priority order (lowest to highest)
    df["scenario"] = pd.Categorical(df["scenario"], ["__base__"] + scenarios)

    # Drop any scenarios that weren't provided in the scenario list (or the default `__base__` tag)
    len_input_df_unfiltered = len(df)
    df = df.sort_values("scenario").dropna(subset="scenario")

    # Log error if scenarios filtered out all data
    if len_input_df_unfiltered != 0 and len(df) == 0:
        logger.warning(f"No data for active scenario(s): {scenarios}")

    # Keep only highest priority scenario data
    df = df.groupby(["component", "instance"]).last()

    return df.reset_index()


if __name__ == "__main__":
    from new_modeling_toolkit.core.utils.util import DirStructure

    dir_str = DirStructure(data_folder="data-test")
    _, system = System.from_csv(
        filename=dir_str.data_interim_dir / "systems" / "unit-test-temporal-settings" / "attributes.csv",
        scenarios=[],
        data={"dir_str": dir_str, "tool_name": "resolve"},
    )
    copy = system.copy()
    print(system)
