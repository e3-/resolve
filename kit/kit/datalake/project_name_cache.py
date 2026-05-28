from dataclasses import dataclass
from pathlib import Path
from typing import cast
from typing import Union

import data_utils as du
import yaml
from loguru import logger


@dataclass
class ProjectNameCache:

    data_dir: Path

    FILENAME: str = "datalake_project_name.yaml"
    CACHE_KEY_NAME: str = "project_name"
    CACHE_KEY_CATEGORY: str = "project_category"

    @property
    def cache_path(self) -> Path:
        return self.data_dir / self.FILENAME

    def set_project_attributes(
        self, project_name: str, project_category: du.ProjectCategories
    ) -> None:
        dump_dict = {
            self.CACHE_KEY_NAME: project_name,
            self.CACHE_KEY_CATEGORY: project_category.value,
        }
        with open(self.cache_path, "w") as f:
            yaml.safe_dump(dump_dict, f)

    def get_project_attributes(
        self,
    ) -> Union[tuple[None, None], tuple[str, du.ProjectCategories]]:
        if not self.cache_path.exists():
            return None, None
        try:
            with open(self.cache_path, "r") as f:
                cache_dict = yaml.safe_load(f)

        except (IOError, OSError) as e:
            logger.warning(f"Failed to read cache file {self.cache_path}: {e}")
            return None, None

        if (
            self.CACHE_KEY_NAME not in cache_dict
            or self.CACHE_KEY_CATEGORY not in cache_dict
        ):
            logger.warning(
                f"Cache file {self.cache_path} is missing required keys. Expected keys: {self.CACHE_KEY_NAME}, {self.CACHE_KEY_CATEGORY}. Returning (None, None)."
            )
            return None, None

        return cache_dict[self.CACHE_KEY_NAME], du.ProjectCategories(
            cache_dict[self.CACHE_KEY_CATEGORY]
        )

    def get_or_set_attributes(
        self,
        project_name: str | None,
        project_category: du.ProjectCategories | None,
    ) -> tuple[str, du.ProjectCategories]:

        if project_name is not None:
            assert (
                project_category is not None
            ), "If project_name is provided, project_category must also be provided."

        if project_category is not None:
            assert (
                project_name is not None
            ), "If project_category is provided, project_name must also be provided."

        if project_name is None:
            project_name, project_category = self.get_project_attributes()

            resp = input(
                f"Project name and category not provided. Found cached values: {project_name} - {project_category}. "
                "Use these values? (y/n): "
            )

            if resp.lower() != "y":
                raise ValueError(
                    "Project name and category are required. Please provide them as "
                    "arguments or confirm use of cached values."
                )

            if project_name is None:
                raise ValueError(
                    "No project name provided and no cached project name found. Please provide a project name."
                )
            logger.debug(
                f"Using cached project specification: {project_name} - {project_category}"
            )

        else:

            existing_project_name, existing_project_category = (
                self.get_project_attributes()
            )

            if (existing_project_name == project_name) and (
                existing_project_category == project_category
            ):
                logger.debug(
                    f"Provided project specification matches cached values: {project_name} - {project_category}. "
                    "No update needed."
                )

            else:
                resp = input(
                    f"Project name and category provided as arguments: {project_name} - {project_category}. "
                    "Cache these values for future use? (y/n): "
                )
                if resp.lower() == "y":
                    self.set_project_attributes(
                        project_name=project_name,
                        project_category=cast(du.ProjectCategories, project_category),
                    )
                elif resp.lower() != "n":
                    logger.warning(
                        "Invalid response. Not caching project name and category. "
                        "Please respond with 'y' or 'n' if you run this function again."
                    )

        return project_name, cast(du.ProjectCategories, project_category)
