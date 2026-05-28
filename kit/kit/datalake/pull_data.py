from pathlib import Path
from typing import Union

import data_utils as du
from loguru import logger
from pyiceberg.exceptions import NoSuchTableError

from kit.core.utils.util import BaseDirStructure
from kit.datalake.project_name_cache import ProjectNameCache


def pull_data(
    project_name: str | None,
    project_category: du.ProjectCategories | None,
    data_folder: str = "data",
    start_dir: str | None = None,
    sync_folders: Union[None, list[str]] = None,
    overwrite: bool = False,
    no_cache: bool = False,
) -> None:
    """Pull data from the datalake to local directories.

    Downloads project data from the datalake (DVC storage) to local directories
    organized by subdirectory (raw, interim, processed, profiles, settings).
    Skips any data that doesn't exist in the datalake.

    Args:
        project_name: Name of the project to pull data for.
        project_category: Category of the project (du.ProjectCategories).
        data_folder: Name of the local data folder relative to the project root.
            Defaults to "data".
        start_dir: Optional path to the project root directory. If not provided,
            defaults to the current working directory (Path.cwd()).
        sync_folders: List of subdirectories to pull. If not provided, defaults to
            ["raw", "interim", "processed", "profiles", "settings"].
        overwrite: If True, overwrite existing local data. Defaults to False.
        no_cache: flag to skip any cacheing logic. this suppresses any follow up user prompts

    Returns:
        None

    Raises:
        NoSuchTableError: Caught and logged; skips pulling that specific subdirectory.

    Example:
        >>> pull_data("my_project", du.ProjectCategories.RECAP)
        >>> pull_data("my_project", du.ProjectCategories.RESOLVE,
        ...           start_dir="/path/to/project",
        ...           sync_folders=["raw", "interim"], overwrite=True)
    """
    if project_name is not None:
        assert (
            project_category is not None
        ), "If project_name is provided, project_category must also be provided."

    if project_category is not None:
        assert (
            project_name is not None
        ), "If project_category is provided, project_name must also be provided."

    default_folder_list = ["raw", "interim", "processed", "profiles", "settings"]
    folders_to_pull = sync_folders if sync_folders is not None else default_folder_list

    data_dirpath = BaseDirStructure(
        start_dir=start_dir if start_dir is not None else Path.cwd(),
        data_folder=data_folder,
    ).data_dir

    project_name_cache = ProjectNameCache(data_dir=data_dirpath)

    if not no_cache:
        project_name_parsed, project_category_parsed = (
            project_name_cache.get_or_set_attributes(
                project_name=project_name, project_category=project_category
            )
        )
    else:
        assert (
            project_name is not None and project_category is not None
        ), "If no_cache is True, project_name and project_category must be provided."
        project_name_parsed, project_category_parsed = project_name, project_category

    project_catalog = du.Catalog.project(
        project_name=project_name_parsed,
        project_category=project_category_parsed,
    )

    def _pull(subdir: str) -> None:
        try:
            logger.info(
                f"Pulling {subdir} data from datalake to {data_dirpath / subdir}..."
            )
            project_catalog.dvc_manager.pull(
                target_id=f"data-{subdir}",
                dest_path=data_dirpath / subdir,
                force=overwrite,
            )
            logger.success(f"{subdir} data pulled successfully.")
        except NoSuchTableError:
            logger.info(
                f"No DVC data found for target ID 'data-{subdir}'. Skipping pull for {subdir} data."
            )

    logger.info(f"Starting data pull process for project '{project_name}'...")
    logger.info(f"Folders to pull: {folders_to_pull}")
    for folder in folders_to_pull:
        _pull(folder)

    logger.success("Data pull process completed.")
