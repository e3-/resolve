#!/usr/bin/env python
import os
import pathlib
from typing import Optional

import data_utils as du
import typer
from loguru import logger as log

app = typer.Typer()

DEFAULT_CONFIG_FILE = pathlib.Path(__file__).parents[2] / ".nmt.config.json"


@app.command(help="Push Data: Pushes local data folders to the datalake using DVC")
def push_data(
    project_name: Optional[str] = typer.Argument(
        default=None,
        help="Name of the project to push data for (env: ANYSCALE_PROJECT)",
    ),
    project_category: Optional[du.ProjectCategories] = typer.Argument(
        default=None,
        help="Category of the project (e.g. recap, resolve, isp) (env: KIT_MODEL)",
    ),
    data_folder: str = typer.Option(
        "data",
        help="Name of data folder, which is assumed to be in the same folder as `kit` folder.",
    ),
    start_dir: str = typer.Option(
        None,
        help="Path to the starting directory where the `kit` folder is located. "
        "By default, it is assumed to be the current working directory.",
    ),
    sync_folders: list[str] = typer.Option(
        None,
        help=(
            "List of specific data subfolders to push (e.g. --sync-folders raw interim). "
            "If not provided, all default folders (raw, interim, processed, profiles, settings) will be pushed."
        ),
    ),
    no_cache: bool = typer.Option(
        False,
        help=(
            "Whether to skip caching project name and category locally after push. "
            "This suppresses any follow up user prompts."
        ),
    ),
):
    """Push local data folders to the datalake using DVC.

    Signs into AWS, then uploads project data from local directories to the
    datalake organized by subdirectory (raw, interim, processed, profiles, settings).
    """
    from kit.datalake.push_data import push_data as sync_push_data

    project_name = project_name or os.environ.get("ANYSCALE_PROJECT")
    project_category = project_category or (
        du.ProjectCategories(os.environ.get("KIT_MODEL"))
        if os.environ.get("KIT_MODEL")
        else None
    )

    log.info(f"Pushing data for project '{project_name}' to datalake...")
    log.info("Sign in to AWS... (follow any popups or prompts that appear)")

    du.aws_sign_in()

    sync_push_data(
        project_name=project_name,
        project_category=project_category,
        data_folder=data_folder,
        start_dir=start_dir,
        sync_folders=sync_folders,
        no_cache=no_cache,
    )


@app.command(help="Pull Data: Pulls data from the datalake to local folders using DVC")
def pull_data(
    project_name: Optional[str] = typer.Argument(
        default=None,
        help="Name of the project to pull data for (env: ANYSCALE_PROJECT)",
    ),
    project_category: Optional[du.ProjectCategories] = typer.Argument(
        default=None,
        help="Category of the project (e.g. recap, resolve, isp) (env: KIT_MODEL)",
    ),
    data_folder: str = typer.Option(
        "data",
        help="Name of data folder, which is assumed to be in the same folder as `kit` folder.",
    ),
    start_dir: str = typer.Option(
        None,
        help="Path to the starting directory where the `kit` folder is located. "
        "By default, it is assumed to be the current working directory.",
    ),
    sync_folders: list[str] = typer.Option(
        None,
        help=(
            "List of specific data subfolders to pull (e.g. --sync-folders raw interim). "
            "If not provided, all default folders (raw, interim, processed, profiles, settings) will be pulled."
        ),
    ),
    overwrite: bool = typer.Option(
        False,
        help="Whether to overwrite existing local data when pulling from the datalake. If False, existing local files will be preserved and not overwritten.",
    ),
    no_cache: bool = typer.Option(
        False,
        help=(
            "Whether to skip caching project name and category locally after push. "
            "This suppresses any follow up user prompts."
        ),
    ),
):
    """Pull data from the datalake to local folders using DVC.

    Signs into AWS, then downloads project data from the datalake to local
    directories organized by subdirectory (raw, interim, processed, profiles, settings).
    """
    from kit.datalake.pull_data import pull_data as sync_pull_data

    project_name = project_name or os.environ.get("ANYSCALE_PROJECT")
    project_category = project_category or (
        du.ProjectCategories(os.environ.get("KIT_MODEL"))
        if os.environ.get("KIT_MODEL")
        else None
    )

    log.info(f"Pulling data for project '{project_name}' from datalake...")
    log.info("Sign in to AWS... (follow any popups or prompts that appear)")

    du.aws_sign_in()

    sync_pull_data(
        project_name=project_name,
        project_category=project_category,
        data_folder=data_folder,
        start_dir=start_dir,
        sync_folders=sync_folders,
        overwrite=overwrite,
        no_cache=no_cache,
    )


def main():
    app()


if __name__ == "__main__":
    main()
