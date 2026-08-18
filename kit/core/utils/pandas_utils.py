import pandas as pd


def _round_floats(row: pd.Series, decimals: int) -> str:
    """Helper function to round floats in a row to a specified number of decimals.
    Note that the return type is a string.
    """
    try:
        return row.astype(float, errors="ignore").round(decimals).astype(str)
    except (ValueError, TypeError):
        return row.astype(str)


def compare_dataframes(
    *,
    previous: pd.DataFrame,
    new: pd.DataFrame,
    indices: list[str],
    column_to_compare: str,
):
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
    comparison[["previous", "new"]] = comparison[["previous", "new"]].apply(
        lambda row: _round_floats(row, 4), axis=1
    )
    comparison = comparison.loc[comparison["previous"] != comparison["new"], :]

    return comparison
