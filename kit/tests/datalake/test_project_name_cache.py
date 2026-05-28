from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from kit.datalake.project_name_cache import ProjectNameCache

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_project_categories():
    """Create a mock ProjectCategories enum."""
    recap = MagicMock(value="recap")
    resolve = MagicMock(value="resolve")
    categories = MagicMock()
    categories.RECAP = recap
    categories.RESOLVE = resolve
    categories.side_effect = lambda v: {"recap": recap, "resolve": resolve}[v]
    return categories


@pytest.fixture
def cache(tmp_path):
    """Create a ProjectNameCache pointed at a temporary directory."""
    return ProjectNameCache(data_dir=tmp_path)


# ── cache_path ─────────────────────────────────────────────────────────


def test_cache_path_returns_expected_path(tmp_path):
    """Should return data_dir / datalake_project_name.yaml."""
    cache = ProjectNameCache(data_dir=tmp_path)
    assert cache.cache_path == tmp_path / "datalake_project_name.yaml"


# ── set_project_attributes ────────────────────────────────────────────


def test_set_project_attributes_writes_yaml(cache, mock_project_categories):
    """Should write project name and category to a YAML file."""
    category = mock_project_categories.RECAP

    cache.set_project_attributes("my_project", category)

    assert cache.cache_path.exists()
    content = cache.cache_path.read_text()
    assert "project_name: my_project" in content
    assert "project_category: recap" in content


def test_set_project_attributes_overwrites_existing(cache, mock_project_categories):
    """Should overwrite existing cache file with new values."""
    cache.set_project_attributes("old_project", mock_project_categories.RECAP)
    cache.set_project_attributes("new_project", mock_project_categories.RESOLVE)

    content = cache.cache_path.read_text()
    assert "project_name: new_project" in content
    assert "project_category: resolve" in content
    assert "old_project" not in content


# ── get_project_attributes ────────────────────────────────────────────


def test_get_project_attributes_returns_none_when_no_cache(cache):
    """Should return (None, None) when cache file does not exist."""
    result = cache.get_project_attributes()
    assert result == (None, None)


@patch("kit.datalake.project_name_cache.du")
def test_get_project_attributes_reads_cached_values(mock_du, cache):
    """Should return the cached project name and category."""
    mock_category = MagicMock(value="recap")
    mock_du.ProjectCategories.side_effect = lambda v: mock_category

    # Write a cache file manually
    cache.cache_path.write_text("project_name: my_project\nproject_category: recap\n")

    name, category = cache.get_project_attributes()

    assert name == "my_project"
    mock_du.ProjectCategories.assert_called_once_with("recap")
    assert category is mock_category


# ── get_or_set_attributes ─────────────────────────────────────────────


@patch("kit.datalake.project_name_cache.du")
def test_get_or_set_attributes_caches_when_user_confirms(mock_du, cache):
    """Should write attributes and return them when user confirms caching."""
    mock_category = MagicMock(value="recap")

    with patch("builtins.input", return_value="y"):
        name, category = cache.get_or_set_attributes("my_project", mock_category)

    assert name == "my_project"
    assert category is mock_category
    assert cache.cache_path.exists()


@patch("kit.datalake.project_name_cache.du")
def test_get_or_set_attributes_skips_cache_when_user_declines(mock_du, cache):
    """Should return attributes but not cache when user declines."""
    mock_category = MagicMock(value="recap")

    with patch("builtins.input", return_value="n"):
        name, category = cache.get_or_set_attributes("my_project", mock_category)

    assert name == "my_project"
    assert category is mock_category
    assert not cache.cache_path.exists()


@patch("kit.datalake.project_name_cache.du")
def test_get_or_set_attributes_warns_on_invalid_input(mock_du, cache):
    """Should log warning and not cache when user gives invalid response."""
    mock_category = MagicMock(value="recap")

    with patch("builtins.input", return_value="maybe"):
        name, category = cache.get_or_set_attributes("my_project", mock_category)

    assert name == "my_project"
    assert not cache.cache_path.exists()


@patch("kit.datalake.project_name_cache.du")
def test_get_or_set_attributes_reads_cache_when_name_is_none(mock_du, cache):
    """Should read from cache when project_name is None and user confirms."""
    mock_category = MagicMock(value="resolve")
    mock_du.ProjectCategories.side_effect = lambda v: mock_category

    # Pre-populate cache
    cache.cache_path.write_text(
        "project_name: cached_project\nproject_category: resolve\n"
    )

    with patch("builtins.input", return_value="y"):
        name, category = cache.get_or_set_attributes(None, None)

    assert name == "cached_project"
    assert category is mock_category


@patch("kit.datalake.project_name_cache.du")
def test_get_or_set_attributes_raises_when_user_declines_cached(mock_du, cache):
    """Should raise ValueError when user declines cached values."""
    mock_category = MagicMock(value="resolve")
    mock_du.ProjectCategories.side_effect = lambda v: mock_category

    cache.cache_path.write_text(
        "project_name: cached_project\nproject_category: resolve\n"
    )

    with patch("builtins.input", return_value="n"):
        with pytest.raises(ValueError, match="Project name and category are required"):
            cache.get_or_set_attributes(None, None)


def test_get_or_set_attributes_raises_when_no_name_and_no_cache(cache):
    """Should raise ValueError when no name provided and no cache exists."""
    with patch("builtins.input", return_value="y"):
        with pytest.raises(ValueError, match="No project name provided"):
            cache.get_or_set_attributes(None, None)


def test_get_or_set_attributes_raises_when_name_without_category(cache):
    """Should raise AssertionError when project_name is provided without category."""
    with pytest.raises(AssertionError, match="project_category must also be provided"):
        cache.get_or_set_attributes("my_project", None)


def test_get_or_set_attributes_raises_when_category_without_name(cache):
    """Should raise AssertionError when project_category is provided without name."""
    mock_category = MagicMock(value="recap")
    with pytest.raises(AssertionError, match="project_name must also be provided"):
        cache.get_or_set_attributes(None, mock_category)
