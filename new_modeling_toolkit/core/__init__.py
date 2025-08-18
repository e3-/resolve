import json

from pydantic import BaseModel
from pydantic import conlist

from new_modeling_toolkit.core.utils import util

# Initialize common directory structure
dir_str = util.DirStructure()

# Initialize class to intercept print statements from Pyomo
stream = util.StreamToLogger(level="INFO")

#
# import pandas as pd
# import pint
#
# def df_encoder(df, date_format="iso"):
#     """Convert pandas dataframe to JSON.
#
#     Need to do json.loads because df.to_json() returns a string in JSON format.
#     """
#     # if "pint" in df.dtypes:
#     #     df = df.pint.dequantify()
#     # except AttributeError:
#     #     # If the dataframe doesn't have pint units
#
#     # Dropping repeated values (if we ever reload a JSON file, will need to `ffill`)
#     df = df[(df.shift(1) != df)]
#     return json.loads(df.to_json(date_format="iso", date_unit="s"))
#
#
# class BaseModel(BaseModel, arbitrary_types_allowed=True, extra="allow", populate_by_name=True):
#     # Consider whether `validate_assignment` should be enabled for all models
#     name: str
#
#     # TODO 2024-01-04: Think about serialization:
#     # - https://docs.pydantic.dev/latest/concepts/serialization/#custom-serializers
#     # - https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.json_encoders
#     json_encoders = {
#         pd.DataFrame: lambda df: df_encoder(df),
#         pd.Series: lambda df: df_encoder(df),
#         pint.Unit: lambda unit: str(unit),
#         # pint.Quantity: lambda quantity: str(quantity),
#     }
#
# class Component(BaseModel):
#     pass
#
#
# class Linkage(Component):
#     components: Annotated[tuple[Component, min_length=2, unique_items=True]]
#     @property
#     def name(self):
#         return tuple(component.name for component in self.components)

__all__ = [
    "linkage",
    "component",
    "three_way_linkage",
]
