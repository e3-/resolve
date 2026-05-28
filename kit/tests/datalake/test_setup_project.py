from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def patch_du():
    """Patch data_utils in the setup_project module."""
    with patch("kit.datalake.setup_project.du") as mock_du:
        mock_du.ProjectCategories = MagicMock()
        mock_du.ProjectCategories.RECAP = MagicMock(value="recap")
        mock_du.ProjectCategories.RESOLVE = MagicMock(value="resolve")
        yield mock_du


# ── create_project ─────────────────────────────────────────────────────


def test_create_project_calls_new_project(patch_du):
    """Should call du.Catalog.new_project with the correct arguments."""
    category = patch_du.ProjectCategories.RECAP
    mock_catalog = MagicMock()
    patch_du.Catalog.new_project.return_value = mock_catalog

    from kit.datalake.setup_project import create_project

    result = create_project("my_project", category)

    patch_du.Catalog.new_project.assert_called_once_with(
        project_name="my_project",
        project_category=category,
    )


def test_create_project_returns_catalog(patch_du):
    """Should return the catalog object from du.Catalog.new_project."""
    category = patch_du.ProjectCategories.RECAP
    mock_catalog = MagicMock()
    patch_du.Catalog.new_project.return_value = mock_catalog

    from kit.datalake.setup_project import create_project

    result = create_project("my_project", category)

    assert result is mock_catalog


def test_create_project_prints_success_message(patch_du, capsys):
    """Should print a success message with the project name."""
    category = patch_du.ProjectCategories.RECAP
    patch_du.Catalog.new_project.return_value = MagicMock()

    from kit.datalake.setup_project import create_project

    create_project("my_project", category)

    captured = capsys.readouterr()
    assert "my_project" in captured.out
    assert "created successfully" in captured.out


def test_create_project_with_different_categories(patch_du):
    """Should pass through whichever category enum is provided."""
    for category in [
        patch_du.ProjectCategories.RECAP,
        patch_du.ProjectCategories.RESOLVE,
    ]:
        patch_du.Catalog.new_project.return_value = MagicMock()

        from kit.datalake.setup_project import create_project

        create_project("test_project", category)

        patch_du.Catalog.new_project.assert_called_with(
            project_name="test_project",
            project_category=category,
        )
