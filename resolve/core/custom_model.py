from __future__ import annotations

import enum
import json
import typing
from dataclasses import dataclass
from typing import get_args
from typing import Union

import pandas as pd
import pint
import pydantic
from pydantic import ConfigDict
from pydantic.fields import FieldInfo


def df_encoder(df, date_format="iso"):
    """Convert pandas dataframe to JSON.

    Need to do json.loads because df.to_json() returns a string in JSON format.
    """
    # if "pint" in df.dtypes:
    #     df = df.pint.dequantify()
    # except AttributeError:
    #     # If the dataframe doesn't have pint units

    # Dropping repeated values (if we ever reload a JSON file, will need to `ffill`)
    df = df[(df.shift(1) != df)]
    return json.loads(df.to_json(date_format="iso", date_unit="s"))


class CustomModel(pydantic.BaseModel):
    """Standard pydantic BaseModel configuration."""

    name: Union[str, tuple]
    # TODO[pydantic]: The following keys were removed: `copy_on_model_validation`, `underscore_attrs_are_private`, `json_encoders`.
    # Check https://docs.pydantic.dev/dev-v2/migration/#changes-to-config for more information.
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        populate_by_name=True,
        loc_by_alias=True,
        json_encoders={
            pd.DataFrame: lambda df: df_encoder(df),
            pd.Series: lambda df: df_encoder(df),
            pint.Unit: lambda unit: str(unit),
            # pint.Quantity: lambda quantity: str(quantity),
        },
    )

    @classmethod
    def get_field_type(cls, *, field_info: FieldInfo) -> tuple:
        """Return a tuple of a field's type(s)."""
        if typing.get_origin(field_info.annotation) is typing.Literal:
            return (typing.Literal,)
        elif nested_types := get_args(field_info.annotation):
            return nested_types
        else:
            return tuple([field_info.annotation])

    @classmethod
    def get_subclasses(cls):
        """Get all subclasses recursively."""
        for subclass in cls.__subclasses__():
            yield from subclass.get_subclasses()
            yield subclass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __rich_repr__(self):
        """WORKAROUND for Rich Repr Protocol.

        [Rich Repr Protocol](https://rich.readthedocs.io/en/latest/pretty.html#rich-repr-protocol)
        doesn't seem to work right now due to highly recursive nature of NMT's `pydantic` model and/or some unknown
        interaction with `loguru` trying to also pretty print the error.
        """
        yield None


class FieldCategory(enum.Enum):
    BUILD = "Build Parameters"
    OPERATIONS = "Operational Parameters"
    RELIABILITY = "Reliability Parameters"
    PYOMO_VARS = "Decision Variables"


@enum.unique
class ModelType(enum.Enum):
    PATHWAYS = "Pathways"
    RECAP = "Recap"
    RESOLVE = "Resolve"
    TEMPLATE = "Template"


@dataclass
class Metadata:
    category: None | FieldCategory = None
    units: pint.Unit | str = ""
    excel_short_title: str = ""
    tools: None | set[ModelType] = None
    warning_bounds: tuple[float | int | None, float | int | None] = (None, None)
    show_year_headers: bool = True
    linkage_order: typing.Literal["from", "to", 1, 2, 3, None] = None
    default_exclude: bool = False
