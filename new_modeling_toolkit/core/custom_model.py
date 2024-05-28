import json
from typing import Union

import pandas as pd
import pint
import pydantic
from loguru import logger


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

    class Config:
        arbitrary_types_allowed = True
        copy_on_model_validation = False
        underscore_attrs_are_private = False
        extra = "allow"
        allow_population_by_field_name = True

        json_encoders = {
            pd.DataFrame: lambda df: df_encoder(df),
            pd.Series: lambda df: df_encoder(df),
            pint.Unit: lambda unit: str(unit),
            # pint.Quantity: lambda quantity: str(quantity),
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __rich_repr__(self):
        """WORKAROUND for Rich Repr Protocol.

        [Rich Repr Protocol](https://rich.readthedocs.io/en/latest/pretty.html#rich-repr-protocol)
        doesn't seem to work right now due to highly recursive nature of NMT's `pydantic` model and/or some unknown
        interaction with `loguru` trying to also pretty print the error.
        """
        yield None


def convert_str_float_to_int(value: str) -> int:
    """Convert float strings to integers. For example, '16.0' will become 16.

    Pydantic doesn't seem to be able to handle this internally, so explicitly defining this heper validator.
    """
    if value is None:
        return None
    else:
        logger.debug(f"Converting {value} to {int(float(value))}")
        return int(float(value))
