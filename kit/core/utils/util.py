import inspect
import pathlib
from typing import Self

import pydantic
from loguru import logger
from pydantic import ConfigDict


class StreamToLogger:
    """Class to help loguru capture all print() from stdout.

    The use-case for this in Pyomo is the `tee=True` feed from the solver.
    Because of this, the logging level is assumed to be DEBUG.
    """

    def __init__(self, level="DEBUG"):
        self._level = level

    def write(self, buffer):
        for line in buffer.rstrip().splitlines():
            logger.opt(depth=1).log(self._level, line.rstrip())

    def flush(self):
        pass


class BaseDirStructure(pydantic.BaseModel):
    """Base directory and file structure shared across all E3 modeling tools.

    Provides the common directory layout (data, settings, results, etc.) that
    is inherited by tool-specific DirStructure subclasses in resolve and recap.

    Naming convention: directory attributes use a ``_dir`` suffix;
    file attributes do not.

    Attributes:
        code_dir: Path to the package's code directory.
        data_folder: Name of the data folder relative to the project root.
        tool_name: Name of the modeling tool.
        start_dir: If provided, overrides the default project root directory.
        proj_dir: Resolved project root (computed from start_dir or code_dir).
        mkdirs: If True, create all directories on initialization.
    """

    model_config = ConfigDict(extra="allow")

    code_dir: pathlib.Path = None
    data_folder: str = "data"
    tool_name: str = "kit"
    start_dir: pathlib.Path | None = None
    mkdirs: bool = True

    _data_folder: str = pydantic.PrivateAttr()

    # Derived path fields (computed in model_post_init)
    proj_dir: pathlib.Path = None
    code_test_dir: pathlib.Path = None
    data_dir: pathlib.Path = None
    data_raw_dir: pathlib.Path = None
    data_interim_dir: pathlib.Path = None
    data_settings_dir: pathlib.Path = None
    data_processed_dir: pathlib.Path = None
    results_dir: pathlib.Path = None

    def model_post_init(self, __context) -> None:
        """Compute derived directory paths after field validation.

        Sets up the standard directory layout (data, settings, results, etc.)
        relative to the project root. If ``start_dir`` is provided, it is used
        as the project root; otherwise, the parent of ``code_dir`` is used.

        If ``code_dir`` is not explicitly provided, it is resolved from the
        module file of the actual (sub)class, so that subclasses in other
        packages (e.g. recap, resolve) get a path relative to their own
        package rather than kit.
        """
        if self.code_dir is None:
            self.code_dir = (
                pathlib.Path(inspect.getfile(type(self))).resolve().parent.parent.parent
            )

        self._data_folder = self.data_folder

        # Project directory / Root directory
        if self.start_dir is not None:
            self.proj_dir = self.start_dir
        else:
            self.proj_dir = self.code_dir.parent

        # Testing code base location
        self.code_test_dir = self.proj_dir / "tests"

        # Data directories
        self.data_dir = self.proj_dir / self.data_folder
        self.data_raw_dir = self.data_dir / "raw"
        self.data_interim_dir = self.data_dir / "interim"
        self.data_settings_dir = self.data_dir / "settings"
        self.data_processed_dir = self.data_dir / "processed"

        # Results directory
        self.results_dir = self.proj_dir / "reports"

        # Make these directories if they do not already exist
        if self.mkdirs:
            self.make_directories()

    def make_directories(self):
        """Create directories for all Path-valued attributes on this instance."""
        for path in vars(self).values():
            if isinstance(path, pathlib.Path):
                path.mkdir(parents=True, exist_ok=True)

    def get_valid_results_dirs(self, model: str):
        """Return a list of non-empty results folders for the specified model.

        Args:
            model: Name of the model to filter results for
                (e.g. "resolve", "reclaim", "recap").

        Returns:
            List of path strings in "case_name/timestamp" format.
        """
        results_path = self.results_dir / model

        # Get all RESOLVE results folder names (nested list to make it "tall" instead of "wide"
        paths = [
            "/".join(p.parts[-3:-1])
            for p in results_path.glob("**/results_summary")
            if any(p.iterdir())
        ]

        return paths

    def copy(self, **kwargs) -> Self:
        """Create a copy of this directory structure with optional overrides.

        Args:
            **kwargs: Field values to override in the new instance.

        Returns:
            A new instance of the same (sub)class with the specified overrides.
        """
        copy_kwargs = dict(
            code_dir=self.code_dir,
            data_folder=self._data_folder,
            tool_name=self.tool_name,
        )
        copy_kwargs.update(kwargs)
        return self.__class__(**copy_kwargs)
