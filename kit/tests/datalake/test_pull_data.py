from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from pyiceberg.exceptions import NoSuchTableError

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_catalog():
    """Create a mock project catalog with a DVC manager."""
    catalog = MagicMock()
    catalog.dvc_manager = MagicMock()
    return catalog


@pytest.fixture
def patch_deps(mock_catalog, tmp_path):
    """Patch data_utils and BaseDirStructure for pull_data tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    with (
        patch("kit.datalake.pull_data.du") as mock_du,
        patch("kit.datalake.pull_data.BaseDirStructure") as mock_dir_structure,
        patch("builtins.input", return_value="y"),
    ):
        mock_du.ProjectCategories = MagicMock()
        mock_du.ProjectCategories.RECAP = MagicMock(value="recap")
        mock_du.Catalog.project.return_value = mock_catalog

        mock_ds_instance = MagicMock()
        mock_ds_instance.data_dir = data_dir
        mock_dir_structure.return_value = mock_ds_instance

        yield mock_du, mock_catalog, mock_dir_structure, tmp_path


# ── Default folders ────────────────────────────────────────────────────


def test_pull_data_uses_default_folders(patch_deps):
    """Should pull all default folders when sync_folders is not specified."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP

    from kit.datalake.pull_data import pull_data

    pull_data("my_project", category, start_dir=str(tmp_path))

    expected_folders = ["raw", "interim", "processed", "profiles", "settings"]
    assert mock_catalog.dvc_manager.pull.call_count == len(expected_folders)

    pulled_target_ids = [
        c.kwargs["target_id"] for c in mock_catalog.dvc_manager.pull.call_args_list
    ]
    for folder in expected_folders:
        assert f"data-{folder}" in pulled_target_ids


# ── Custom sync_folders ────────────────────────────────────────────────


def test_pull_data_uses_custom_sync_folders(patch_deps):
    """Should only pull the specified folders when sync_folders is provided."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP

    from kit.datalake.pull_data import pull_data

    pull_data(
        "my_project", category, start_dir=str(tmp_path), sync_folders=["raw", "interim"]
    )

    assert mock_catalog.dvc_manager.pull.call_count == 2

    pulled_target_ids = [
        c.kwargs["target_id"] for c in mock_catalog.dvc_manager.pull.call_args_list
    ]
    assert "data-raw" in pulled_target_ids
    assert "data-interim" in pulled_target_ids


# ── Overwrite / force ──────────────────────────────────────────────────


def test_pull_data_passes_overwrite_as_force(patch_deps):
    """Should pass overwrite value as the 'force' parameter to dvc_manager.pull."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP

    from kit.datalake.pull_data import pull_data

    pull_data(
        "my_project",
        category,
        start_dir=str(tmp_path),
        sync_folders=["raw"],
        overwrite=True,
    )

    mock_catalog.dvc_manager.pull.assert_called_once()
    assert mock_catalog.dvc_manager.pull.call_args.kwargs["force"] is True


def test_pull_data_force_defaults_to_false(patch_deps):
    """Should default force to False when overwrite is not specified."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP

    from kit.datalake.pull_data import pull_data

    pull_data("my_project", category, start_dir=str(tmp_path), sync_folders=["raw"])

    assert mock_catalog.dvc_manager.pull.call_args.kwargs["force"] is False


# ── NoSuchTableError handling ──────────────────────────────────────────


def test_pull_data_skips_folder_on_no_such_table_error(patch_deps):
    """Should skip folders that raise NoSuchTableError without stopping."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP

    # First call raises, second succeeds
    mock_catalog.dvc_manager.pull.side_effect = [
        NoSuchTableError("not found"),
        None,
    ]

    from kit.datalake.pull_data import pull_data

    # Should not raise
    pull_data(
        "my_project", category, start_dir=str(tmp_path), sync_folders=["raw", "interim"]
    )

    assert mock_catalog.dvc_manager.pull.call_count == 2


# ── dest_path ──────────────────────────────────────────────────────────


def test_pull_data_uses_correct_dest_path(patch_deps):
    """Should pass data_dir / subdir as dest_path to dvc_manager.pull."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP
    data_dir = tmp_path / "data"

    from kit.datalake.pull_data import pull_data

    pull_data("my_project", category, start_dir=str(tmp_path), sync_folders=["raw"])

    assert (
        mock_catalog.dvc_manager.pull.call_args.kwargs["dest_path"] == data_dir / "raw"
    )


# ── Catalog creation ──────────────────────────────────────────────────


def test_pull_data_creates_catalog_with_correct_args(patch_deps):
    """Should create a project catalog with the given name and category."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP

    from kit.datalake.pull_data import pull_data

    pull_data("my_project", category, start_dir=str(tmp_path), sync_folders=[])

    mock_du.Catalog.project.assert_called_once_with(
        project_name="my_project",
        project_category=category,
    )


# ── Empty sync_folders ────────────────────────────────────────────────


def test_pull_data_with_empty_sync_folders(patch_deps):
    """Should not call pull at all when sync_folders is an empty list."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP

    from kit.datalake.pull_data import pull_data

    pull_data("my_project", category, start_dir=str(tmp_path), sync_folders=[])

    mock_catalog.dvc_manager.pull.assert_not_called()
