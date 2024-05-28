from typing import Sequence
from typing import Union

import pandas as pd


def convert_index_levels_to_datetime(
    pandas_object: Union[pd.Series, pd.DataFrame], levels: Union[int, str, Sequence[int], Sequence[str]], **kwargs
) -> Union[pd.Series, pd.DataFrame]:
    """Converts one or levels in a pandas Series or DataFrame with a MultiIndex to datetime type.

    Args:
        pandas_object: series or data frame to convert the levels of
        levels: level name(s) to convert (or integer positions, if unnamed)
        **kwargs: additional arguments to pd.to_datetime() (e.g. `format="%d/%m/%Y %H:%M"`)

    Returns:
        converted_object: pandas object with the converted levels
    """
    if isinstance(levels, (int, str)):
        levels = [levels]

    level_name_indexes = [
        list(pandas_object.index.names).index(level) if isinstance(level, str) else level for level in levels
    ]

    converted_object = pandas_object.copy(deep=True)
    converted_object.index = converted_object.index.set_levels(
        levels=[
            [pd.to_datetime(x, **kwargs) for x in converted_object.index.levels[level_name_index]]
            for level_name_index in level_name_indexes
        ],
        level=levels,
    )

    return converted_object
