# TODO: Factor class for creating fuel conversion plants from single table in the UI
# import enum
# import pathlib
# from typing import Annotated
#
# import pandas as pd
#
# from new_modeling_toolkit.core.custom_model import FieldCategory
# from new_modeling_toolkit.core.custom_model import Metadata
# from new_modeling_toolkit.system.fuel import candidate_fuel
# from new_modeling_toolkit.system.fuel import final_fuel
# from new_modeling_toolkit.system.fuel.electrolyzer import Electrolyzer
# from new_modeling_toolkit.system.fuel.electrolyzer import ElectrolyzerGroup
# from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlant
# from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlantGroup
# from new_modeling_toolkit.system.fuel.fuel_storage import FuelStorage
# from new_modeling_toolkit.system.fuel.fuel_storage import FuelStorageGroup
# from new_modeling_toolkit.system.generics.plant import Plant
# from new_modeling_toolkit.system.generics.plant import PlantGroup
# from new_modeling_toolkit.system.pollution.negative_emissions_technology import NegativeEmissionsTechnology
# from new_modeling_toolkit.system.pollution.negative_emissions_technology import NegativeEmissionsTechnologyGroup
#
# __all__ = ["Plant", "FuelProductionPlant", "Electrolyzer", "FuelStorage", "NegativeEmissionsTechnology"]
#
#
# @enum.unique
# class PlantType(enum.Enum):
#     GENERIC = "Plant"
#     FPP = "FuelProductionPlant"
#     ELECTROLYZER = "Electrolyzer"
#     FUEL_STORAGE = "FuelStorage"
#     NET = "NegativeEmissionsTechnology"
#
#
# class FuelConversionPlant(Plant, FuelProductionPlant, Electrolyzer, FuelStorage, NegativeEmissionsTechnology):
#     """A "factory" class that creates the appropriate type of fuel sector plant based on the defined `type`."""
#
#     SAVE_PATH = "fuel_conversion_plants"
#     plant_type: Annotated[PlantType, Metadata(category=FieldCategory.BUILD)]
#
#     @classmethod
#     def from_dataframe(
#         cls,
#         *,
#         input_df: pd.DataFrame,
#         attr_path: pathlib.Path | None = None,
#         scenarios: list[str] | None = None,
#         data: dict | None = None,
#         name: str | None = None,
#     ):
#         attrs = {
#             **{"name": name if name is not None else attr_path.stem, "attr_path": attr_path},
#             **cls._parse_attributes(filename=attr_path, input_df=input_df, scenarios=scenarios),
#         }
#         if data is not None:
#             attrs.update(data)
#
#         plant_type = PlantType(attrs.pop("resource_type"))
#
#         match plant_type:
#             case PlantType.GENERIC:
#                 subclass = Plant
#             case PlantType.FPP:
#                 subclass = FuelProductionPlant
#             case PlantType.ELECTROLYZER:
#                 subclass = Electrolyzer
#             case PlantType.FUEL_STORAGE:
#                 subclass = FuelStorage
#             case PlantType.NET:
#                 subclass = NegativeEmissionsTechnology
#
#         attrs = {
#             **{"name": name if name is not None else attr_path.stem, "attr_path": attr_path},
#             **subclass._parse_attributes(filename=attr_path, input_df=input_df, scenarios=scenarios),
#         }
#         if data is not None:
#             attrs.update(data)
#
#         return subclass(**attrs)
#
#
# class FuelConversionPlantGroup(
#     PlantGroup, FuelProductionPlantGroup, ElectrolyzerGroup, FuelStorageGroup, NegativeEmissionsTechnologyGroup
# ):
#     """A "factory" class that creates the appropriate type of electric sector resource based on the defined `type`."""
#
#     SAVE_PATH = "fuel_conversion_plants/groups"
#     resource_type: Annotated[PlantType, Metadata(category=FieldCategory.BUILD)]
#
#     @classmethod
#     def dfs_to_csv(
#         cls,
#         *,
#         instances: pd.DataFrame,
#         wb: "Book",
#         dir_str: "DirStructure",
#         compare_files: bool = True,
#         dry_run: bool = False,
#         save_path_override: pathlib.Path | None = None,
#     ) -> None:
#         """If `vintages_to_construct` exists in the dataframe to be saved, create individual instances/vintages in addition to the group."""
#         # Save the group CSV
#         super().dfs_to_csv(instances=instances, wb=wb, dir_str=dir_str, compare_files=compare_files, dry_run=dry_run)
#
#     @classmethod
#     def from_dataframe(
#         cls,
#         *,
#         input_df: pd.DataFrame,
#         attr_path: pathlib.Path | None = None,
#         scenarios: list[str] | None = None,
#         data: dict | None = None,
#         name: str | None = None,
#     ):
#         attrs = {
#             **{"name": name if name is not None else attr_path.stem, "attr_path": attr_path},
#             **cls._parse_attributes(filename=attr_path, input_df=input_df, scenarios=scenarios),
#         }
#         if data is not None:
#             attrs.update(data)
#
#         plant_type = PlantType(attrs.pop("resource_type"))
#
#         match plant_type:
#             case PlantType.GENERIC:
#                 subclass = PlantGroup
#             case PlantType.FPP:
#                 subclass = FuelProductionPlantGroup
#             case PlantType.ELECTROLYZER:
#                 subclass = ElectrolyzerGroup
#             case PlantType.FUEL_STORAGE:
#                 subclass = FuelStorageGroup
#             case PlantType.NET:
#                 subclass = NegativeEmissionsTechnologyGroup
#
#         attrs = {
#             **{"name": name if name is not None else attr_path.stem, "attr_path": attr_path},
#             **subclass._parse_attributes(filename=attr_path, input_df=input_df, scenarios=scenarios),
#         }
#         if data is not None:
#             attrs.update(data)
#
#         return subclass(**attrs)
