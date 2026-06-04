import enum
import pathlib
from typing import Annotated

import pandas as pd
from kit.system.electric import BaseElectricResource
from kit.system.electric import BaseElectricResourceGroup
from loguru import logger

from resolve.core.custom_model import FieldCategory
from resolve.core.custom_model import Metadata
from resolve.system.electric.resources.flex_load import FlexLoadResource
from resolve.system.electric.resources.flex_load import FlexLoadResourceGroup
from resolve.system.electric.resources.generic import GenericResource
from resolve.system.electric.resources.generic import GenericResourceGroup
from resolve.system.electric.resources.hybrid import HybridSolarResource
from resolve.system.electric.resources.hybrid import HybridSolarResourceGroup
from resolve.system.electric.resources.hybrid import HybridStorageResource
from resolve.system.electric.resources.hybrid import HybridStorageResourceGroup
from resolve.system.electric.resources.hybrid import HybridVariableResource
from resolve.system.electric.resources.hybrid import HybridVariableResourceGroup
from resolve.system.electric.resources.hybrid import HybridWindResource
from resolve.system.electric.resources.hybrid import HybridWindResourceGroup
from resolve.system.electric.resources.hydro import HydroResource
from resolve.system.electric.resources.hydro import HydroResourceGroup
from resolve.system.electric.resources.shed_dr import ShedDrResource
from resolve.system.electric.resources.shed_dr import ShedDrResourceGroup
from resolve.system.electric.resources.storage import StorageResource
from resolve.system.electric.resources.storage import StorageResourceGroup
from resolve.system.electric.resources.thermal import ThermalResource
from resolve.system.electric.resources.thermal import ThermalResourceGroup
from resolve.system.electric.resources.thermal import ThermalUnitCommitmentResource
from resolve.system.electric.resources.thermal import ThermalUnitCommitmentResourceGroup
from resolve.system.electric.resources.unit_commitment import UnitCommitmentResource
from resolve.system.electric.resources.variable.solar import SolarResource
from resolve.system.electric.resources.variable.solar import SolarResourceGroup
from resolve.system.electric.resources.variable.variable import VariableResource
from resolve.system.electric.resources.variable.variable import VariableResourceGroup
from resolve.system.electric.resources.variable.wind import WindResource
from resolve.system.electric.resources.variable.wind import WindResourceGroup

__all__ = [
    "FlexLoadResource",
    "GenericResource",
    "HybridStorageResource",
    "HybridVariableResource",
    "HybridSolarResource",
    "HybridWindResource",
    "HydroResource",
    "ShedDrResource",
    "StorageResource",
    "ThermalResource",
    "ThermalUnitCommitmentResource",
    "UnitCommitmentResource",
    "VariableResource",
]


@enum.unique
class ResourceType(enum.Enum):
    GENERIC = "Generic"
    THERMAL = "Thermal"
    THERMAL_UC = "Thermal Unit Commitment"
    HYDRO = "Hydro"
    SHED = "Shed DR"
    SHIFT = "Shift DR"
    STORAGE = "Storage"
    VARIABLE = "Variable"
    SOLAR = "Solar"
    WIND = "Wind"
    HYBRID_STORAGE = "Hybrid Storage"
    HYBRID_VARIABLE = "Hybrid Variable"
    HYBRID_SOLAR = "Hybrid Solar"
    HYBRID_WIND = "Hybrid Wind"


class ElectricResource(BaseElectricResource, ThermalUnitCommitmentResource, VariableResource, FlexLoadResource):
    """A "factory" class that creates the appropriate type of electric sector resource based on the defined `type`."""

    SAVE_PATH = "resources"
    resource_type: Annotated[ResourceType, Metadata(category=FieldCategory.BUILD)]

    @classmethod
    def from_dataframe(
        cls,
        *,
        input_df: pd.DataFrame,
        attr_path: pathlib.Path | None = None,
        scenarios: list[str] | None = None,
        data: dict | None = None,
        name: str | None = None,
    ):
        attrs = {
            **{"name": name if name is not None else attr_path.stem, "attr_path": attr_path},
            **cls._parse_attributes(filename=attr_path, input_df=input_df, scenarios=scenarios),
        }
        if data is not None:
            attrs.update(data)

        resource_type = ResourceType(attrs.pop("resource_type"))

        match resource_type:
            case ResourceType.HYDRO:
                subclass = HydroResource
            case ResourceType.SHED:
                subclass = ShedDrResource
            case ResourceType.SHIFT:
                subclass = FlexLoadResource
            case ResourceType.STORAGE:
                subclass = StorageResource
            case ResourceType.VARIABLE:
                subclass = VariableResource
            case ResourceType.SOLAR:
                subclass = SolarResource
            case ResourceType.WIND:
                subclass = WindResource
            case ResourceType.GENERIC:
                subclass = GenericResource
            case ResourceType.THERMAL:
                subclass = ThermalResource
            case ResourceType.THERMAL_UC:
                subclass = ThermalUnitCommitmentResource
            case ResourceType.HYBRID_STORAGE:
                subclass = HybridStorageResource
            case ResourceType.HYBRID_VARIABLE:
                subclass = HybridVariableResource
            case ResourceType.HYBRID_SOLAR:
                subclass = HybridSolarResource
            case ResourceType.HYBRID_WIND:
                subclass = HybridWindResource

        attrs = {
            **{"name": name if name is not None else attr_path.stem, "attr_path": attr_path},
            **subclass._parse_attributes(filename=attr_path, input_df=input_df, scenarios=scenarios),
        }
        if data is not None:
            attrs.update(data)

        return subclass(**attrs)


class ElectricResourceGroup(
    BaseElectricResourceGroup, ThermalResourceGroup, StorageResourceGroup, VariableResourceGroup
):
    """A "factory" class that creates the appropriate type of electric sector resource based on the defined `type`."""

    SAVE_PATH = "resources/groups"
    resource_type: Annotated[ResourceType, Metadata(category=FieldCategory.BUILD)]

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
        """If `vintages_to_construct` exists in the dataframe to be saved, create individual instances/vintages in addition to the group."""
        # Save the group CSV
        super().dfs_to_csv(instances=instances, wb=wb, dir_str=dir_str, compare_files=compare_files, dry_run=dry_run)

    @classmethod
    def from_dataframe(
        cls,
        *,
        input_df: pd.DataFrame,
        attr_path: pathlib.Path | None = None,
        scenarios: list[str] | None = None,
        data: dict | None = None,
        name: str | None = None,
    ):
        attrs = {
            **{"name": name if name is not None else attr_path.stem, "attr_path": attr_path},
            **cls._parse_attributes(filename=attr_path, input_df=input_df, scenarios=scenarios),
        }
        if data is not None:
            attrs.update(data)

        resource_type = ResourceType(attrs.pop("resource_type"))

        match resource_type:
            case ResourceType.HYDRO:
                subclass = HydroResourceGroup
            case ResourceType.SHED:
                subclass = ShedDrResourceGroup
            case ResourceType.SHIFT:
                subclass = FlexLoadResourceGroup
            case ResourceType.STORAGE:
                subclass = StorageResourceGroup
            case ResourceType.VARIABLE:
                subclass = VariableResourceGroup
            case ResourceType.SOLAR:
                subclass = SolarResourceGroup
            case ResourceType.WIND:
                subclass = WindResourceGroup
            case ResourceType.GENERIC:
                subclass = GenericResourceGroup
            case ResourceType.THERMAL:
                subclass = ThermalResourceGroup
            case ResourceType.THERMAL_UC:
                subclass = ThermalUnitCommitmentResourceGroup
            case ResourceType.HYBRID_STORAGE:
                subclass = HybridStorageResourceGroup
            case ResourceType.HYBRID_VARIABLE:
                subclass = HybridVariableResourceGroup
            case ResourceType.HYBRID_SOLAR:
                subclass = HybridSolarResourceGroup
            case ResourceType.HYBRID_WIND:
                subclass = HybridWindResourceGroup

        attrs = {
            **{"name": name if name is not None else attr_path.stem, "attr_path": attr_path},
            **subclass._parse_attributes(filename=attr_path, input_df=input_df, scenarios=scenarios),
        }
        if data is not None:
            attrs.update(data)

        return subclass(**attrs)
