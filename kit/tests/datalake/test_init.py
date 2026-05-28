"""Tests for kit.datalake package exports."""


def test_exports_create_project():
    """create_project should be importable from kit.datalake."""
    from kit.datalake import create_project

    assert callable(create_project)


def test_exports_pull_data():
    """pull_data should be importable from kit.datalake."""
    from kit.datalake import pull_data

    assert callable(pull_data)


def test_exports_push_data():
    """push_data should be importable from kit.datalake."""
    from kit.datalake import push_data

    assert callable(push_data)


def test_all_contains_expected_names():
    """__all__ should list exactly the four public functions."""
    import kit.datalake

    expected = {"create_project", "pull_data", "push_data"}
    assert set(kit.datalake.__all__) == expected
