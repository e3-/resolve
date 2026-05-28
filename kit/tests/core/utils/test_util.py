import pytest

from kit.core.utils.util import BaseDirStructure


@pytest.fixture
def tmp_dir_structure(tmp_path):
    """Create a BaseDirStructure rooted at a temporary directory."""
    return BaseDirStructure(start_dir=tmp_path, mkdirs=True)


# ── Initialization ──────────────────────────────────────────────────────


def test_default_proj_dir_is_code_dir_parent(tmp_path):
    """When start_dir is not provided, proj_dir should be code_dir.parent."""
    ds = BaseDirStructure(code_dir=tmp_path / "kit", mkdirs=False)
    assert ds.proj_dir == tmp_path


def test_start_dir_overrides_proj_dir(tmp_path):
    """When start_dir is provided, it should be used as proj_dir."""
    custom_root = tmp_path / "custom_root"
    ds = BaseDirStructure(start_dir=custom_root, mkdirs=False)
    assert ds.proj_dir == custom_root


def test_data_directories_use_data_folder(tmp_path):
    """Data directories should be based on the data_folder parameter."""
    ds = BaseDirStructure(start_dir=tmp_path, data_folder="data-test", mkdirs=False)
    assert ds.data_dir == tmp_path / "data-test"
    assert ds.data_raw_dir == tmp_path / "data-test" / "raw"
    assert ds.data_interim_dir == tmp_path / "data-test" / "interim"
    assert ds.data_settings_dir == tmp_path / "data-test" / "settings"
    assert ds.data_processed_dir == tmp_path / "data-test" / "processed"


def test_standard_directory_layout(tmp_path):
    """All standard directories should be correctly derived from proj_dir."""
    ds = BaseDirStructure(start_dir=tmp_path, mkdirs=False)
    assert ds.code_test_dir == tmp_path / "tests"
    assert ds.data_dir == tmp_path / "data"
    assert ds.results_dir == tmp_path / "reports"


def test_default_field_values():
    """Default field values should match expected defaults."""
    ds = BaseDirStructure(mkdirs=False)
    assert ds.data_folder == "data"
    assert ds.tool_name == "kit"
    assert ds.start_dir is None


# ── mkdirs ──────────────────────────────────────────────────────────────


def test_mkdirs_true_creates_directories(tmp_path):
    """When mkdirs=True, all Path-valued directories should be created."""
    ds = BaseDirStructure(start_dir=tmp_path, mkdirs=True)
    assert ds.data_dir.exists()
    assert ds.data_raw_dir.exists()
    assert ds.data_interim_dir.exists()
    assert ds.data_settings_dir.exists()
    assert ds.data_processed_dir.exists()
    assert ds.results_dir.exists()
    assert ds.code_test_dir.exists()


def test_mkdirs_false_does_not_create_directories(tmp_path):
    """When mkdirs=False, no directories should be created."""
    project_root = tmp_path / "empty_project"
    ds = BaseDirStructure(start_dir=project_root, mkdirs=False)
    assert not ds.data_dir.exists()
    assert not ds.results_dir.exists()


# ── make_directories ────────────────────────────────────────────────────


def test_make_directories_creates_missing_dirs(tmp_path):
    """Calling make_directories() should create any missing Path dirs."""
    ds = BaseDirStructure(start_dir=tmp_path, mkdirs=False)
    assert not ds.data_dir.exists()

    ds.make_directories()
    assert ds.data_dir.exists()
    assert ds.results_dir.exists()


def test_make_directories_is_idempotent(tmp_dir_structure):
    """Calling make_directories() multiple times should not raise errors."""
    tmp_dir_structure.make_directories()
    tmp_dir_structure.make_directories()
    assert tmp_dir_structure.data_dir.exists()


# ── get_valid_results_dirs ──────────────────────────────────────────────


def test_get_valid_results_dirs_empty(tmp_dir_structure):
    """Returns an empty list when no results folders exist."""
    assert tmp_dir_structure.get_valid_results_dirs("resolve") == []


def test_get_valid_results_dirs_finds_nonempty_results(tmp_dir_structure):
    """Returns paths for results folders that contain a non-empty results_summary."""
    # Create: reports/resolve/case_a/2024-01-01/results_summary/output.csv
    results_summary = (
        tmp_dir_structure.results_dir
        / "resolve"
        / "case_a"
        / "2024-01-01"
        / "results_summary"
    )
    results_summary.mkdir(parents=True)
    (results_summary / "output.csv").touch()

    paths = tmp_dir_structure.get_valid_results_dirs("resolve")
    assert len(paths) == 1
    assert "case_a/2024-01-01" in paths[0]


def test_get_valid_results_dirs_ignores_empty_results_summary(tmp_dir_structure):
    """Ignores results folders where results_summary is empty."""
    results_summary = (
        tmp_dir_structure.results_dir
        / "resolve"
        / "case_b"
        / "2024-02-01"
        / "results_summary"
    )
    results_summary.mkdir(parents=True)
    # No files inside results_summary

    paths = tmp_dir_structure.get_valid_results_dirs("resolve")
    assert paths == []


# ── copy ────────────────────────────────────────────────────────────────


def test_copy_returns_same_class(tmp_path):
    """copy() should return an instance of the same class."""
    ds = BaseDirStructure(start_dir=tmp_path, mkdirs=False)
    ds_copy = ds.copy()
    assert isinstance(ds_copy, BaseDirStructure)


def test_copy_preserves_fields(tmp_path):
    """copy() should preserve code_dir and data_folder."""
    ds = BaseDirStructure(
        code_dir=tmp_path / "kit",
        data_folder="data-test",
        start_dir=tmp_path,
        mkdirs=False,
    )
    ds_copy = ds.copy(mkdirs=False)
    assert ds_copy.code_dir == tmp_path / "kit"
    assert ds_copy.data_folder == "data-test"


def test_copy_with_overrides(tmp_path):
    """copy() should apply kwargs overrides."""
    ds = BaseDirStructure(start_dir=tmp_path, data_folder="data", mkdirs=False)
    ds_copy = ds.copy(data_folder="data-test", mkdirs=False)
    assert ds_copy.data_folder == "data-test"
    assert ds_copy.data_dir == ds_copy.proj_dir / "data-test"


def test_copy_subclass_returns_subclass(tmp_path):
    """copy() on a subclass should return the subclass type, not the base."""

    class ChildDirStructure(BaseDirStructure):
        pass

    ds = ChildDirStructure(start_dir=tmp_path, mkdirs=False)
    ds_copy = ds.copy(mkdirs=False)
    assert type(ds_copy) is ChildDirStructure
