from pathlib import Path
from typing import Union

import data_utils as du
from loguru import logger

from kit.core.utils.util import BaseDirStructure
from kit.datalake.project_name_cache import ProjectNameCache


def push_data(
    project_name: Union[str, None],
    project_category: Union[du.ProjectCategories, None],
    data_folder: str = "data",
    start_dir: str | None = None,
    sync_folders: Union[None, list[str]] = None,
    no_cache: bool = False,
) -> None:
    """Push data from local directories to the datalake.

    Uploads project data from local directories to the datalake (DVC storage)
    organized by subdirectory (raw, interim, processed, profiles, settings).
    Skips any subdirectories that don't exist locally.

    Args:
        project_name: Name of the project to push data for.
        project_category: Category of the project (du.ProjectCategories).
        data_folder: Name of the local data folder relative to the project root.
            Defaults to "data".
        start_dir: Optional path to the project root directory. If not provided,
            defaults to the current working directory (Path.cwd()).
        sync_folders: List of subdirectories to push. If not provided, defaults to
            ["raw", "interim", "processed", "profiles", "settings"].
        no_cache: flag to skip any cacheing logic. this suppresses any follow up user prompts

    Returns:
        None

    Raises:
        Warning: Logged if the data directory does not exist or if specific
            subdirectories cannot be found (function returns early without pushing).

    Example:
        >>> push_data("my_project", du.ProjectCategories.RECAP)
        >>> push_data("my_project", du.ProjectCategories.RESOLVE,
        ...           start_dir="/path/to/project",
        ...           sync_folders=["raw", "interim"])
    """

    default_folder_list = ["raw", "interim", "processed", "profiles", "settings"]
    folders_to_push = sync_folders if sync_folders is not None else default_folder_list

    data_dirpath = BaseDirStructure(
        start_dir=start_dir if start_dir is not None else Path.cwd(),  # type: ignore
        data_folder=data_folder,
        mkdirs=False,
    ).data_dir

    if not (data_dirpath.exists() and data_dirpath.is_dir()):
        logger.warning(
            f"Data directory not found at {data_dirpath}. Please ensure the data directory exists before pushing."
        )
        return

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

    def _push(subdir: str) -> None:
        if (data_dirpath / subdir).exists():
            logger.info(
                f"Pushing {subdir} data from {data_dirpath / subdir} to datalake..."
            )
            project_catalog.dvc_manager.push(
                data_dirpath / subdir,
                target_id=f"data-{subdir}",
            )
            logger.success(f"{subdir} data pushed successfully.")
        else:
            logger.warning(
                f"{subdir} data directory not found at {data_dirpath / subdir}. Skipping push for {subdir} data."
            )

    logger.info(f"Starting data push process for project '{project_name}'...")
    logger.info(f"Folders to push: {folders_to_push}")
    for folder in folders_to_push:
        _push(folder)

    logger.info("Data push process completed.")
