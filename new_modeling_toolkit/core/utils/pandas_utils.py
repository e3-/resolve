from functools import reduce
from typing import Iterable
from typing import List
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


def reindex_by_intersection(
    pandas_objects: Iterable[Union[pd.Series, pd.DataFrame]]
) -> List[Union[pd.Series, pd.DataFrame]]:
    """Reindexes a list of frames using the set intersection of the row indices of all frames.

    Args:
        pandas_objects: list of series or data frames

    Returns:
        reindexed_frames: list of reindexed data frames
    """
    new_index = reduce(pd.Index.intersection, [frame_.index for frame_ in pandas_objects])
    reindexed_frames = [frame.reindex(new_index) for frame in pandas_objects]

    return reindexed_frames


def reindex_by_union(pandas_objects: Iterable[Union[pd.Series, pd.DataFrame]]) -> List[Union[pd.Series, pd.DataFrame]]:
    """Reindexes a list of frames using the set union of the row indices of all frames.

    Args:
        pandas_objects: list of series or data frames

    Returns:
        reindexed_frames: list of reindexed data frames
    """
    new_index = reduce(pd.Index.union, [frame_.index for frame_ in pandas_objects])
    reindexed_frames = [frame.reindex(new_index) for frame in pandas_objects]

    return reindexed_frames


def _round_floats(row, decimals):
    try:
        return row.astype(float, errors="ignore").round(decimals).astype(str)
    except (ValueError, TypeError):
        return row.astype(str)


def compare_dataframes(*, previous: pd.DataFrame, new: pd.DataFrame, indices: list[str], column_to_compare: str):
    """A more flexible comparison method for two dataframes.

    The existing .compare() and .equal() methods from pandas don't quite fit our needs. This method allows you to compare
    any two dataframes by:
     - Concatenating the two DataFrames
     - Doing a string comparison of the "previous" and "new" column
     - Returning a DataFrame with any deltas
    """
    comparison = pd.concat(
        [
            previous.set_index(indices)[column_to_compare],
            new.set_index(indices)[column_to_compare],
        ],
        axis=1,
    )

    comparison.columns = ["previous", "new"]
    comparison[["previous", "new"]] = comparison[["previous", "new"]].apply(lambda row: _round_floats(row, 4), axis=1)
    comparison = comparison.loc[comparison["previous"] != comparison["new"], :]

    return comparison
