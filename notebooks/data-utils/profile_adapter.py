"""
Profile Adapter Script

This module transforms EV (Electric Vehicle) profile data from the data_utils catalog format
to RESOLVE-compatible CSV profile format. It provides utilities to filter, retrieve, and
export EV charging profiles for use in RESOLVE capacity expansion modeling.

Main functionality:
- Retrieve EV profiles from data_utils tables with configurable filters
- Export profiles in RESOLVE-compatible format (timestamp, value columns)
- Handle multiple years and filter configurations

Example usage:
    python profile_adapter.py

EV Off-The-Shelf Library Docs:
- https://ethreesf.sharepoint.com/:w:/s/Models/EYyglX0MO0xIuoYEWLIrOnUBc8iuxdfMjHC_f6AiaK9aBw?e=y6geJS

"""

import typing
from pathlib import Path

import data_utils as du
import pandas as pd
from loguru import logger


def get_choices(df: pd.DataFrame) -> dict[str, list]:
    """
    Extract unique values from DataFrame columns with low cardinality.

    This function identifies columns with fewer than 10 unique values and
    returns their distinct values. Useful for understanding filtering options
    and validating data quality.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame to analyze

    Returns
    -------
    dict[str, list]
        Dictionary mapping column names to lists of unique values,
        only for columns with < 10 unique values

    Example
    -------
    >>> df = pd.DataFrame({'year': [2020, 2020, 2030], 'value': [1, 2, 3]})
    >>> get_choices(df)
    {'year': [2020, 2030]}
    """
    choices = {}
    for column in df.columns:
        if df[column].nunique() < 10:
            choices[column] = df[column].unique().tolist()
    return choices


def get_ev_profile(
    catalog: du.Catalog, table_id: str, filter_config: typing.Dict[str, typing.Any] = None
) -> pd.DataFrame:
    """
    Retrieve an EV profile from a data_utils Table with configurable filtering.

    Builds a filter expression dynamically from the configuration dictionary and
    retrieves matching rows from the table. Supports equality filters and range
    filters using 'start_' and 'end_' prefixes.

    Parameters
    ----------
    catalog : du.Catalog
        Data_utils Catalog object to query
    table_id : str
        Identifier for the table within the catalog
    filter_config : dict[str, Any], optional
        Dictionary mapping column names to desired filter values.
        - Standard columns use equality: {'region': 'CAISO'}
        - Range filters use prefixes:
          * 'start_<column>': >= comparison
          * 'end_<column>': <= comparison
        Example: {'start_year': 2020, 'end_year': 2040, 'region': 'CAISO'}

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame containing the EV profile data

    Raises
    ------
    AttributeError
        If a column specified in filter_config does not exist in the table

    Example
    -------
    >>> tbl = catalog.get_table('evlst_library_regional')
    >>> df = get_ev_profile(tbl, {'year': 2040, 'region': 'CAISO'})
    """

    tbl = catalog.get_table(table_id)

    # Build the filter expression dynamically from the configuration mapping.
    filt = None
    for col, val in filter_config.items():
        # Extract base attribute name by removing start_/end_ prefixes
        base_attr = col.removeprefix("start_").removeprefix("end_")
        # Determine which prefix was used (if any)
        binop = col.removesuffix(base_attr)

        try:
            col_attr = getattr(tbl, base_attr)
        except AttributeError:
            raise AttributeError(f"Table does not have column/attribute '{col}' required by filter_config")

        # Apply appropriate comparison operator based on prefix
        cond = {
            "start_": col_attr >= val,  # Greater than or equal for start_ prefix
            "end_": col_attr <= val,  # Less than or equal for end_ prefix
            "": col_attr == val,  # Equality for no prefix
        }[binop]

        # Combine conditions with AND logic
        filt = cond if filt is None else (filt & cond)

    pull_df = tbl.to_pandas(filter=filt)
    logger.info(
        f"Retrieved EV profile with {len(pull_df)} rows using filter: {filt}\n" f"Choices: {get_choices(pull_df)}"
    )
    return pull_df


def put_ev_profile(pull_df: pd.DataFrame, folder: str, filename: str, timestamp_col: str, value_col: str) -> None:
    """
    Export EV profile DataFrame to CSV in RESOLVE-compatible format.

    Transforms the DataFrame to have a 'timestamp' column and a renamed value
    column, then writes to CSV. The value column is renamed to include the
    filename stem as a prefix for better identification.

    Loose filter choice may lead to potential multi-index in the output profile.

    Parameters
    ----------
    pull_df : pd.DataFrame
        Source DataFrame containing the profile data
    folder : str
        Directory path where the CSV file will be written
    filename : str
        Name of the output CSV file (should end in .csv)
    timestamp_col : str
        Name of the column containing timestamp data
    value_col : str
        Name of the column containing the profile values

    Raises
    ------
    AssertionError
        If required columns are not present in the DataFrame

    Notes
    -----
    - Output format: timestamp, <filename_stem>_<value_col> [, optional_columns]
    - Columns with only one unique value (constants) are automatically dropped
    - Errors during file write are logged but do not raise exceptions

    Example
    -------
    >>> put_ev_profile(df, './profiles', 'ev_2040.csv', 'timestamp', 'kw_per_vehicle')
    Creates file: ./profiles/ev_2040.csv with columns: timestamp, ev_2040_kw_per_vehicle
    """
    write_columns = [timestamp_col, value_col]
    assert all(col in pull_df.columns for col in write_columns), f"DataFrame must contain columns: {write_columns}"

    # Create a copy with only the required columns
    drop_cols = [c for c in pull_df.columns if pull_df[c].nunique() == 1 and c not in write_columns]
    keep_columns = [c for c in pull_df.columns if c not in drop_cols]
    df = pull_df[keep_columns].copy()
    if df.shape[1] > len(write_columns):
        logger.warning(f"DataFrame has extra columns beyond {write_columns}. Treat profile with multi-index.")

    # Rename columns for RESOLVE compatibility
    df = df.rename(columns={timestamp_col: "timestamp", value_col: filename.removesuffix(".csv") + "_" + value_col})

    try:
        df.to_csv(Path(folder) / filename, index=False)
        logger.info(f"Successfully wrote profile to {Path(folder) / filename}")
    except (IOError, PermissionError) as e:  # file existence, permission, etc.
        logger.error(f"Failed to write profile to {filename}: {e}")


def pull_ev_profiles_to_local(
    catalog: du.Catalog,
    profiles_directory: typing.Union[str, Path],
    tbl_cfg: typing.Optional[dict] = None,
    filter_cfg: typing.Optional[dict] = None,
) -> None:
    """
    Retrieve and export EV profiles to local directory, grouped by filterable columns.
    Main orchestration function that:
    1. Retrieves the table from the catalog
    2. Applies filters to get the desired profile data
    3. Groups data by all filterable columns (excluding timestamp and value)
    4. Exports each group as a separate CSV file

    The function automatically handles multiple combinations of filter values
    (e.g., multiple scenarios, vehicle types, years) by creating one CSV per
    unique combination.

    tbl_cfg is optional. If omitted, a default configuration is used:
        {
            "table_name": "evlst_library_regional",
            "timestamp_col": "timestamp",
            "value_col": "kw_per_vehicle",
            "profile_name_stem": "ev_profile",
        }
    get_filterable_columns() is called internally to populate 'filterable_columns'.

    Parameters
    ----------
    catalog : du.Catalog
        Data_utils catalog containing the EV profile tables
    profiles_directory : str or Path
        Local directory path where profile CSVs will be written
    tbl_cfg : dict | None, optional
        Table configuration with keys:
        - 'table_name': Name of the table in the catalog
        - 'profile_name_stem': Base name for output files
        - 'timestamp_col': Name of timestamp column
        - 'value_col': Name of value column
        - 'filterable_columns': List of columns to group by (set by get_filterable_columns)
    filter_cfg : dict | None, optional
        Filter configuration passed to get_ev_profile()
        Example: {'start_year': 2020, 'end_year': 2060, 'region': 'CAISO'}

    Raises
    ------
    ValueError
        If no data is found in the profile data

    Notes
    -----
    - Automatically identifies filterable columns
    - Grouping uses all non timestamp/value columns, Handles multiple groups automatically
    - Output filename format: {profile_name_stem}_{group_values}.csv
    - Group values are joined with underscores in the filename
    - Prints progress information to stdout

    Example
    -------
    >>> tbl_cfg = {
    ...     'table_name': 'evlst_library_regional',
    ...     'profile_name_stem': 'ev_profile',
    ...     'timestamp_col': 'timestamp',
    ...     'value_col': 'kw_per_vehicle',
    ...     'filterable_columns': ['year', 'region', 'scenario', 'vehicle_type']
    ... }
    >>> filter_cfg = {'start_year': 2020, 'end_year': 2040, 'region': 'CAISO'}
    >>> pull_ev_profiles_to_local(catalog, './profiles', tbl_cfg, filter_cfg)

    If data contains multiple scenarios, this will create separate files like:
    - ev_profile_2020_CAISO_managed_ldvs.csv
    - ev_profile_2020_CAISO_unmanaged_ldvs.csv
    - ev_profile_2030_CAISO_managed_ldvs.csv
    - etc.
    """

    if tbl_cfg is None:
        tbl_cfg = {
            "table_name": "evlst_library_regional",
            "timestamp_col": "timestamp",
            "value_col": "kw_per_vehicle",
            "profile_name_stem": "ev_profile",
        }
        tbl_cfg.update(get_filterable_columns(tbl_cfg, catalog))
        logger.info("Using default tbl_cfg parameter {}".format(tbl_cfg))
    elif "filterable_columns" not in tbl_cfg:
        logger.info("Added filterable columns to provided tbl_cfg parameter {}".format(tbl_cfg))
        tbl_cfg.update(get_filterable_columns(tbl_cfg, catalog))
    else:
        logger.info("Using provided tbl_cfg parameter {}".format(tbl_cfg))

    if filter_cfg is None:
        filter_cfg = {}

    # Ensure filterable_columns present (always refreshed)
    tbl_cfg.update(get_filterable_columns(tbl_cfg, catalog))

    profile_name_stem = tbl_cfg["profile_name_stem"]
    table_name = tbl_cfg["table_name"]

    df = get_ev_profile(catalog, table_name, filter_cfg)

    # Display available filter choices for validation
    choices = get_choices(df)
    logger.info(f"Data retrieved with choices: {choices}")

    # Check that we have data
    if len(df) == 0:
        raise ValueError("No data found in profile data after filtering.")

    groupby_cols = tbl_cfg["filterable_columns"]
    if not groupby_cols:
        logger.warning("No filterable columns found. Writing single file.")
        # Write single file with generic name
        profile_name = f"{profile_name_stem}.csv"
        put_ev_profile(
            df,
            profiles_directory,
            profile_name,
            timestamp_col=tbl_cfg["timestamp_col"],
            value_col=tbl_cfg["value_col"],
        )
        logger.info(f"Wrote profile to {profile_name}")
        return

    logger.info(f"Grouping by columns: {groupby_cols}")

    # Group by all filterable columns and export each group
    grouped = df.groupby(groupby_cols, dropna=False)
    total_groups = len(grouped)
    logger.info(f"Found {total_groups} unique group(s) to export")

    for group_values, group_df in grouped:
        # Convert single value to tuple for consistent handling
        if not isinstance(group_values, tuple):
            group_values = (group_values,)

        # Build filename from group values
        group_str = "_".join([str(val) for val in group_values])
        profile_name = f"{profile_name_stem}_{group_str}.csv"

        # Create a dict of group identifiers for logging
        group_dict = dict(zip(groupby_cols, group_values))

        put_ev_profile(
            group_df,
            profiles_directory,
            profile_name,
            timestamp_col=tbl_cfg["timestamp_col"],
            value_col=tbl_cfg["value_col"],
        )
        logger.info(f"Wrote profile for {group_dict} to {profile_name}")


def get_filterable_columns(tbl_cfg: dict, catalog: du.Catalog) -> dict:
    """
    Identify and validate columns available for filtering in a table.

    Determines which columns can be used as filters by excluding the timestamp
    and value columns. Updates the table configuration with this information.

    Parameters
    ----------
    tbl_cfg : dict
        Table configuration dictionary containing:
        - 'table_name': Name of table in catalog
        - 'timestamp_col': Name of timestamp column to exclude
        - 'value_col': Name of value column to exclude
    catalog : du.Catalog
        Data_utils catalog to retrieve table from

    Returns
    -------
    dict
        Updated tbl_cfg with new 'filterable_columns' key containing
        list of column names available for filtering

    Raises
    ------
    AssertionError
        If timestamp_col or value_col is not found in table columns

    Example
    -------
    >>> tbl_cfg = {
    ...     'table_name': 'evlst_library_regional',
    ...     'timestamp_col': 'timestamp',
    ...     'value_col': 'kw_per_vehicle'
    ... }
    >>> updated_cfg = get_filterable_columns(tbl_cfg, catalog)
    >>> logger.info(updated_cfg['filterable_columns'])
    ['year', 'region', 'scenario', 'vehicle_type', 'charger_type']
    """
    table_name = tbl_cfg["table_name"]
    table = catalog.get_table(table_name)
    columns = table.columns
    timestamp_col = tbl_cfg["timestamp_col"]
    value_col = tbl_cfg["value_col"]

    # Validate required columns exist
    assert timestamp_col in columns, f"Timestamp column '{timestamp_col}' not found in table columns."
    assert value_col in columns, f"Value column '{value_col}' not found in table columns."

    # Identify filterable columns (all except timestamp and value)
    filterable_columns = [col for col in columns if col not in (timestamp_col, value_col)]

    col_filt_d = {"filterable_columns": filterable_columns}
    logger.info(f"Filterable columns for table '{table_name}': {col_filt_d}")
    return col_filt_d


if __name__ == "__main__":
    """
    Main execution block for EV profile extraction.

    This script:
    1. Connects to the E3 data library
    2. Configures table and filter parameters
    3. Retrieves and exports EV charging profiles

    Configuration can be modified by changing tbl_cfg and filter_cfg dictionaries.
    """
    import data_utils as du

    # Authenticate with AWS
    du.aws_sign_in()

    # Connect to the data catalog
    # catalog = du.Catalog.testing()  # Use for testing
    catalog = du.Catalog.library()  # Use for production data library

    # Define output directory using pathlib for cross-platform compatibility
    profiles_directory = Path(__file__).resolve().parent.parent.parent / "data-test" / "profiles"

    logger.info(f"Available tables in catalog: {catalog.list_tables()}")

    # Configure the table structure
    tbl_cfg = {
        "table_name": "evlst_library_regional",  # EV load shape table
        "timestamp_col": "timestamp",  # Column containing timestamps
        "value_col": "kw_per_vehicle",  # Column containing kW values
        "profile_name_stem": "ev_profile",  # Base name for output files
    }

    # Identify which columns can be used for filtering
    tbl_cfg.update(get_filterable_columns(tbl_cfg, catalog))

    # Configure the data filters
    filter_cfg = {
        "start_year": 2020,  # Include years >= 2020
        "end_year": 2060,  # Include years <= 2060
        "region": "CAISO",  # California ISO region
        # "scenario": "managed",        # Managed charging scenario
        "vehicle_type": "ldvs",  # Light-duty vehicles
        "charger_type": "home_l2",  # Home Level 2 chargers
    }

    # Execute the profile extraction
    pull_ev_profiles_to_local(catalog, profiles_directory, tbl_cfg, filter_cfg)

    logger.info("Profile extraction completed successfully")
