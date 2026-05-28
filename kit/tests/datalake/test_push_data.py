from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_catalog():
    """Create a mock project catalog with a DVC manager."""
    catalog = MagicMock()
    catalog.dvc_manager = MagicMock()
    return catalog


@pytest.fixture
def patch_deps(mock_catalog, tmp_path):
    """Patch data_utils and BaseDirStructure for push_data tests.

    Creates a real data directory at tmp_path/data so existence checks pass.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    with (
        patch("kit.datalake.push_data.du") as mock_du,
        patch("kit.datalake.push_data.BaseDirStructure") as mock_dir_structure,
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


def test_push_data_uses_default_folders(patch_deps):
    """Should attempt to push all default folders when sync_folders is not specified."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP
    data_dir = tmp_path / "data"

    # Create all default subdirectories
    for folder in ["raw", "interim", "processed", "profiles", "settings"]:
        (data_dir / folder).mkdir()

    from kit.datalake.push_data import push_data

    push_data("my_project", category, start_dir=str(tmp_path))

    assert mock_catalog.dvc_manager.push.call_count == 5

    pushed_target_ids = [
        c.kwargs["target_id"] for c in mock_catalog.dvc_manager.push.call_args_list
    ]
    for folder in ["raw", "interim", "processed", "profiles", "settings"]:
        assert f"data-{folder}" in pushed_target_ids


# ── Custom sync_folders ────────────────────────────────────────────────


def test_push_data_uses_custom_sync_folders(patch_deps):
    """Should only push the specified folders when sync_folders is provided."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP
    data_dir = tmp_path / "data"

    (data_dir / "raw").mkdir()
    (data_dir / "interim").mkdir()

    from kit.datalake.push_data import push_data

    push_data(
        "my_project", category, start_dir=str(tmp_path), sync_folders=["raw", "interim"]
    )

    assert mock_catalog.dvc_manager.push.call_count == 2

    pushed_target_ids = [
        c.kwargs["target_id"] for c in mock_catalog.dvc_manager.push.call_args_list
    ]
    assert "data-raw" in pushed_target_ids
    assert "data-interim" in pushed_target_ids


# ── Missing data directory ─────────────────────────────────────────────


def test_push_data_returns_early_if_data_dir_missing(mock_catalog, tmp_path):
    """Should return without pushing if the data directory does not exist."""
    nonexistent_data_dir = tmp_path / "nonexistent_data"

    with (
        patch("kit.datalake.push_data.du") as mock_du,
        patch("kit.datalake.push_data.BaseDirStructure") as mock_dir_structure,
    ):
        mock_du.ProjectCategories = MagicMock()
        mock_du.ProjectCategories.RECAP = MagicMock(value="recap")
        category = mock_du.ProjectCategories.RECAP

        mock_ds_instance = MagicMock()
        mock_ds_instance.data_dir = nonexistent_data_dir
        mock_dir_structure.return_value = mock_ds_instance

        from kit.datalake.push_data import push_data

        push_data("my_project", category, start_dir=str(tmp_path))

        mock_du.Catalog.project.assert_not_called()
        mock_catalog.dvc_manager.push.assert_not_called()


# ── Skipping missing subdirectories ───────────────────────────────────


def test_push_data_skips_missing_subdirectories(patch_deps):
    """Should skip subdirectories that don't exist locally."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP
    data_dir = tmp_path / "data"

    # Only create 'raw', not 'interim'
    (data_dir / "raw").mkdir()

    from kit.datalake.push_data import push_data

    push_data(
        "my_project", category, start_dir=str(tmp_path), sync_folders=["raw", "interim"]
    )

    assert mock_catalog.dvc_manager.push.call_count == 1

    pushed_target_ids = [
        c.kwargs["target_id"] for c in mock_catalog.dvc_manager.push.call_args_list
    ]
    assert "data-raw" in pushed_target_ids
    assert "data-interim" not in pushed_target_ids


# ── Correct dest_path ─────────────────────────────────────────────────


def test_push_data_passes_correct_source_path(patch_deps):
    """Should pass data_dir / subdir as the source path to dvc_manager.push."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP
    data_dir = tmp_path / "data"

    (data_dir / "raw").mkdir()

    from kit.datalake.push_data import push_data

    push_data("my_project", category, start_dir=str(tmp_path), sync_folders=["raw"])

    mock_catalog.dvc_manager.push.assert_called_once()
    call_args = mock_catalog.dvc_manager.push.call_args
    assert call_args.args[0] == data_dir / "raw"
    assert call_args.kwargs["target_id"] == "data-raw"


# ── Catalog creation ──────────────────────────────────────────────────


def test_push_data_creates_catalog_with_correct_args(patch_deps):
    """Should create a project catalog with the given name and category."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP

    from kit.datalake.push_data import push_data

    push_data("my_project", category, start_dir=str(tmp_path), sync_folders=[])

    mock_du.Catalog.project.assert_called_once_with(
        project_name="my_project",
        project_category=category,
    )


# ── Empty sync_folders ────────────────────────────────────────────────


def test_push_data_with_empty_sync_folders(patch_deps):
    """Should not call push at all when sync_folders is an empty list."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP

    from kit.datalake.push_data import push_data

    push_data("my_project", category, start_dir=str(tmp_path), sync_folders=[])

    mock_catalog.dvc_manager.push.assert_not_called()


# ── All subdirectories missing ────────────────────────────────────────


def test_push_data_no_push_when_all_subdirs_missing(patch_deps):
    """Should not push anything when none of the default subdirectories exist."""
    mock_du, mock_catalog, _, tmp_path = patch_deps
    category = mock_du.ProjectCategories.RECAP

    from kit.datalake.push_data import push_data

    push_data("my_project", category, start_dir=str(tmp_path))

    mock_catalog.dvc_manager.push.assert_not_called()
