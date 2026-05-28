"""
Tests for notebooks/data-utils/profile_adapter.py
This module contains unit tests for the profile adapter functions that
transform EV profile data from data_utils catalog format to RESOLVE-compatible
CSV profile format.
To run these tests:
    # Run all tests in this file
    pytest tests/test_profile_adapter.py -v
    # Run a specific test class
    pytest tests/test_profile_adapter.py::TestGetChoices -v
    # Run a specific test
    pytest tests/test_profile_adapter.py::TestGetChoices::test_single_column_low_cardinality -v
    # Run with coverage (requires pytest-cov)
    pytest tests/test_profile_adapter.py --cov=profile_adapter --cov-report=html
Test Coverage:
- get_choices(): Tests column filtering by cardinality
- get_ev_profile(): Tests dynamic filter building with prefixes
- put_ev_profile(): Tests CSV export with column handling
- pull_ev_profiles_to_local(): Tests grouping and batch export
- get_filterable_columns(): Tests column identification and validation
"""

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

import pandas as pd
import pytest

# Import the functions to test
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks" / "data-utils"))

import profile_adapter as pa


class TestGetChoices:
    """Tests for the get_choices function."""

    def test_single_column_low_cardinality(self):
        """Test with a single column having few unique values."""
        df = pd.DataFrame({"year": [2020, 2020, 2030, 2030, 2040]})
        result = pa.get_choices(df)
        assert result == {"year": [2020, 2030, 2040]}

    def test_multiple_columns_mixed_cardinality(self):
        """Test with columns of varying cardinality."""
        df = pd.DataFrame(
            {
                "year": [2020, 2020, 2030] * 10,
                "region": ["CAISO", "CAISO", "CAISO"] * 10,
                "value": [1, 2, 3] * 10,  # Low cardinality
                "timestamp": pd.date_range("2020-01-01", periods=30, freq="h"),  # High cardinality
            }
        )
        result = pa.get_choices(df)
        # Should only include columns with < 10 unique values
        assert "year" in result
        assert "region" in result
        assert "value" in result
        assert "timestamp" not in result  # Has 3 unique values, but checking the logic

    def test_exactly_10_unique_values(self):
        """Test boundary condition with exactly 10 unique values."""
        df = pd.DataFrame({"col": list(range(10))})
        result = pa.get_choices(df)
        # Should not include column with exactly 10 unique values
        assert "col" not in result

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        df = pd.DataFrame()
        result = pa.get_choices(df)
        assert result == {}

    def test_single_unique_value(self):
        """Test column with only one unique value."""
        df = pd.DataFrame({"constant": [5, 5, 5, 5]})
        result = pa.get_choices(df)
        assert result == {"constant": [5]}


class TestGetEvProfile:
    """Tests for the get_ev_profile function."""

    def test_equality_filter(self):
        """Test basic equality filtering."""
        mock_table = Mock()
        mock_table.region = Mock()

        # Mock the comparison operation
        mock_condition = Mock()
        mock_table.region.__eq__ = Mock(return_value=mock_condition)
        mock_table.region.__ge__ = Mock(return_value=mock_condition)
        mock_table.region.__le__ = Mock(return_value=mock_condition)

        # Mock the to_pandas call
        expected_df = pd.DataFrame({"region": ["CAISO"], "value": [10]})
        mock_table.to_pandas = Mock(return_value=expected_df)

        filter_config = {"region": "CAISO"}
        mock_catalog = Mock()
        mock_catalog.get_table = Mock(return_value=mock_table)

        with patch("profile_adapter.logger"):
            result = pa.get_ev_profile(mock_catalog, "test_table", filter_config)

        assert result.equals(expected_df)
        mock_table.to_pandas.assert_called_once()

    def test_range_filter_start_prefix(self):
        """Test range filtering with start_ prefix."""
        mock_table = Mock()
        mock_table.year = Mock()

        mock_condition = Mock()
        mock_table.year.__eq__ = Mock(return_value=mock_condition)
        mock_table.year.__ge__ = Mock(return_value=mock_condition)
        mock_table.year.__le__ = Mock(return_value=mock_condition)

        expected_df = pd.DataFrame({"year": [2020, 2030], "value": [1, 2]})
        mock_table.to_pandas = Mock(return_value=expected_df)

        filter_config = {"start_year": 2020}
        mock_catalog = Mock()
        mock_catalog.get_table = Mock(return_value=mock_table)

        with patch("profile_adapter.logger"):
            result = pa.get_ev_profile(mock_catalog, "test_table", filter_config)

        assert result.equals(expected_df)

    def test_range_filter_end_prefix(self):
        """Test range filtering with end_ prefix."""
        mock_table = Mock()
        mock_table.year = Mock()

        mock_condition = Mock()
        mock_table.year.__le__ = Mock(return_value=mock_condition)
        mock_table.year.__eq__ = Mock(return_value=mock_condition)
        mock_table.year.__ge__ = Mock(return_value=mock_condition)

        expected_df = pd.DataFrame({"year": [2020, 2030], "value": [1, 2]})
        mock_table.to_pandas = Mock(return_value=expected_df)

        filter_config = {"end_year": 2040}
        mock_catalog = Mock()
        mock_catalog.get_table = Mock(return_value=mock_table)

        with patch("profile_adapter.logger"):
            result = pa.get_ev_profile(mock_catalog, "test_table", filter_config)

        assert result.equals(expected_df)

    def test_combined_filters(self):
        """Test multiple filters combined with AND logic."""
        mock_table = Mock()
        mock_table.year = Mock()
        mock_table.region = Mock()

        # Create mock conditions
        year_cond = Mock()
        region_cond = Mock()
        combined_cond = Mock()

        mock_table.year.__ge__ = Mock(return_value=year_cond)
        mock_table.year.__le__ = Mock(return_value=year_cond)
        mock_table.year.__eq__ = Mock(return_value=year_cond)
        mock_table.region.__eq__ = Mock(return_value=region_cond)
        mock_table.region.__ge__ = Mock(return_value=region_cond)
        mock_table.region.__le__ = Mock(return_value=region_cond)
        year_cond.__and__ = Mock(return_value=combined_cond)

        expected_df = pd.DataFrame({"year": [2020], "region": ["CAISO"]})
        mock_table.to_pandas = Mock(return_value=expected_df)

        filter_config = {"start_year": 2020, "region": "CAISO"}
        mock_catalog = Mock()
        mock_catalog.get_table = Mock(return_value=mock_table)

        with patch("profile_adapter.logger"):
            result = pa.get_ev_profile(mock_catalog, "test_table", filter_config)

        assert result.equals(expected_df)

    def test_invalid_column_raises_error(self):
        """Test that invalid column name raises AttributeError."""
        mock_table = Mock()
        # Configure mock to raise AttributeError when accessing non-existent columns
        mock_table.configure_mock(**{})

        # Set up side_effect to raise AttributeError for any attribute access
        type(mock_table).__getattr__ = Mock(
            side_effect=AttributeError("'Mock' object has no attribute 'invalid_column'")
        )

        filter_config = {"invalid_column": "value"}
        mock_catalog = Mock()
        mock_catalog.get_table = Mock(return_value=mock_table)

        with pytest.raises(AttributeError):
            with patch("profile_adapter.logger"):
                pa.get_ev_profile(mock_catalog, "test_table", filter_config)


class TestPutEvProfile:
    """Tests for the put_ev_profile function."""

    def setup_method(self):
        """Create a temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_basic_csv_export(self):
        """Test basic CSV export functionality."""
        df = pd.DataFrame(
            {"timestamp": pd.date_range("2020-01-01", periods=3, freq="h"), "kw_per_vehicle": [1.0, 2.0, 3.0]}
        )

        filename = "test_profile.csv"

        with patch("profile_adapter.logger"):
            pa.put_ev_profile(df, self.temp_dir, filename, timestamp_col="timestamp", value_col="kw_per_vehicle")

        # Check file was created
        output_file = Path(self.temp_dir) / filename
        assert output_file.exists()

        # Check file contents
        result_df = pd.read_csv(output_file)
        assert "timestamp" in result_df.columns
        assert "test_profile_kw_per_vehicle" in result_df.columns
        assert len(result_df) == 3

    def test_drops_constant_columns(self):
        """Test that columns with single unique value are dropped."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2020-01-01", periods=3, freq="h"),
                "kw_per_vehicle": [1.0, 2.0, 3.0],
                "year": [2020, 2020, 2020],  # Constant column
                "region": ["CAISO", "CAISO", "CAISO"],  # Constant column
            }
        )

        filename = "test_profile.csv"

        with patch("profile_adapter.logger"):
            pa.put_ev_profile(df, self.temp_dir, filename, timestamp_col="timestamp", value_col="kw_per_vehicle")

        # Check file contents
        output_file = Path(self.temp_dir) / filename
        result_df = pd.read_csv(output_file)

        # Constant columns should be dropped
        assert "year" not in result_df.columns
        assert "region" not in result_df.columns

    def test_warns_on_extra_columns(self):
        """Test warning is logged when extra non-constant columns exist."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2020-01-01", periods=3, freq="h"),
                "kw_per_vehicle": [1.0, 2.0, 3.0],
                "scenario": ["managed", "unmanaged", "managed"],  # Variable column
            }
        )

        filename = "test_profile.csv"

        with patch("profile_adapter.logger") as mock_logger:
            pa.put_ev_profile(df, self.temp_dir, filename, timestamp_col="timestamp", value_col="kw_per_vehicle")

            # Check that warning was logged
            mock_logger.warning.assert_called()

    def test_missing_required_column_raises_error(self):
        """Test that missing required columns raise AssertionError."""
        df = pd.DataFrame({"timestamp": [1, 2, 3]})

        with pytest.raises(AssertionError, match="must contain columns"):
            pa.put_ev_profile(df, self.temp_dir, "test.csv", timestamp_col="timestamp", value_col="missing_column")

    def test_column_renaming(self):
        """Test that columns are renamed correctly."""
        df = pd.DataFrame({"ts": pd.date_range("2020-01-01", periods=2, freq="h"), "power": [1.0, 2.0]})

        filename = "ev_2040.csv"

        with patch("profile_adapter.logger"):
            pa.put_ev_profile(df, self.temp_dir, filename, timestamp_col="ts", value_col="power")

        output_file = Path(self.temp_dir) / filename
        result_df = pd.read_csv(output_file)

        assert "timestamp" in result_df.columns
        assert "ev_2040_power" in result_df.columns


class TestPullEvProfilesToLocal:
    """Tests for the pull_ev_profiles_to_local function."""

    def setup_method(self):
        """Create temporary directory for test outputs."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_single_group_export(self):
        """Test exporting a single group."""
        # Create mock catalog and table
        mock_catalog = Mock()
        mock_table = Mock()
        mock_catalog.get_table = Mock(return_value=mock_table)

        # Create test data with single group
        test_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2020-01-01", periods=24, freq="h"),
                "kw_per_vehicle": [1.0] * 24,
                "year": [2020] * 24,
                "region": ["CAISO"] * 24,
            }
        )

        filterable_columns_dict = {
            "filterable_columns": [
                "year",
                "region",
            ]
        }
        with (
            patch("profile_adapter.get_ev_profile", return_value=test_df),
            patch("profile_adapter.put_ev_profile") as mock_put,
            patch("profile_adapter.logger"),
            patch("profile_adapter.get_filterable_columns", return_value=filterable_columns_dict),
        ):

            tbl_cfg = {
                "table_name": "test_table",
                "profile_name_stem": "ev_profile",
                "timestamp_col": "timestamp",
                "value_col": "kw_per_vehicle",
                "filterable_columns": ["year", "region"],
            }

            filter_cfg = {"region": "CAISO"}

            pa.pull_ev_profiles_to_local(mock_catalog, self.temp_dir, tbl_cfg, filter_cfg)

            # Check that put_ev_profile was called once
            assert mock_put.call_count == 1

            # Check the filename contains group values
            call_args = mock_put.call_args
            filename = call_args[0][2]
            assert "2020" in filename
            assert "CAISO" in filename

    def test_multiple_groups_export(self):
        """Test exporting multiple groups."""
        mock_catalog = Mock()
        mock_table = Mock()
        mock_catalog.get_table = Mock(return_value=mock_table)

        # Create test data with multiple groups (2 years × 2 scenarios = 4 groups)
        test_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2020-01-01", periods=4, freq="h").tolist() * 4,
                "kw_per_vehicle": [1.0] * 16,
                "year": [2020, 2020, 2020, 2020, 2030, 2030, 2030, 2030] * 2,
                "scenario": ["managed"] * 8 + ["unmanaged"] * 8,
            }
        )

        filterable_columns_dict = {"filterable_columns": ["year", "scenario"]}
        with (
            patch("profile_adapter.get_ev_profile", return_value=test_df),
            patch("profile_adapter.put_ev_profile") as mock_put,
            patch("profile_adapter.logger"),
            patch("profile_adapter.get_filterable_columns", return_value=filterable_columns_dict),
        ):

            tbl_cfg = {
                "table_name": "test_table",
                "profile_name_stem": "ev_profile",
                "timestamp_col": "timestamp",
                "value_col": "kw_per_vehicle",
                "filterable_columns": ["year", "scenario"],
            }

            filter_cfg = {}

            pa.pull_ev_profiles_to_local(mock_catalog, self.temp_dir, tbl_cfg, filter_cfg)

            # Should create 4 files (2 years × 2 scenarios)
            assert mock_put.call_count == 4

    def test_empty_data_raises_error(self):
        """Test that empty data raises ValueError."""
        mock_catalog = Mock()
        mock_table = Mock()
        mock_catalog.get_table = Mock(return_value=mock_table)

        empty_df = pd.DataFrame()

        filterable_columns_dict = {"filterable_columns": []}
        with (
            patch("profile_adapter.get_ev_profile", return_value=empty_df),
            patch("profile_adapter.logger"),
            patch("profile_adapter.get_filterable_columns", return_value=filterable_columns_dict),
        ):

            tbl_cfg = {
                "table_name": "test_table",
                "profile_name_stem": "ev_profile",
                "timestamp_col": "timestamp",
                "value_col": "kw_per_vehicle",
                "filterable_columns": [],
            }

            filter_cfg = {}

            with pytest.raises(ValueError, match="No data found"):
                pa.pull_ev_profiles_to_local(mock_catalog, self.temp_dir, tbl_cfg, filter_cfg)

    def test_default_tbl_cfg_used(self):
        """Test calling without tbl_cfg uses internal defaults."""
        mock_catalog = Mock()
        mock_table = Mock()
        mock_catalog.get_table = Mock(return_value=mock_table)

        test_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2020-01-01", periods=8, freq="h"),
                "kw_per_vehicle": [1.0] * 8,
                "year": [2020] * 4 + [2030] * 4,
                "region": ["CAISO"] * 8,
                "scenario": ["managed"] * 8,
            }
        )

        filterable_columns_dict = {"filterable_columns": ["year", "region", "scenario"]}
        with (
            patch("profile_adapter.get_ev_profile", return_value=test_df),
            patch("profile_adapter.put_ev_profile") as mock_put,
            patch("profile_adapter.logger"),
            patch("profile_adapter.get_filterable_columns", return_value=filterable_columns_dict),
        ):
            pa.pull_ev_profiles_to_local(mock_catalog, self.temp_dir)
            # filterable columns = year, region, scenario -> 2 groups (years differ)
            assert mock_put.call_count == 2


class TestGetFilterableColumns:
    """Tests for the get_filterable_columns function."""

    def test_basic_filterable_columns(self):
        """Test identification of filterable columns."""
        mock_catalog = Mock()
        mock_table = Mock()
        mock_table.columns = ["timestamp", "kw_per_vehicle", "year", "region", "scenario"]
        mock_catalog.get_table = Mock(return_value=mock_table)

        tbl_cfg = {"table_name": "test_table", "timestamp_col": "timestamp", "value_col": "kw_per_vehicle"}

        with patch("profile_adapter.logger"):
            result = pa.get_filterable_columns(tbl_cfg, mock_catalog)

        assert "filterable_columns" in result
        assert "year" in result["filterable_columns"]
        assert "region" in result["filterable_columns"]
        assert "scenario" in result["filterable_columns"]
        assert "timestamp" not in result["filterable_columns"]
        assert "kw_per_vehicle" not in result["filterable_columns"]

    def test_missing_timestamp_column_raises_error(self):
        """Test that missing timestamp column raises AssertionError."""
        mock_catalog = Mock()
        mock_table = Mock()
        mock_table.columns = ["kw_per_vehicle", "year"]
        mock_catalog.get_table = Mock(return_value=mock_table)

        tbl_cfg = {"table_name": "test_table", "timestamp_col": "missing_timestamp", "value_col": "kw_per_vehicle"}

        with pytest.raises(AssertionError, match="Timestamp column"):
            pa.get_filterable_columns(tbl_cfg, mock_catalog)

    def test_missing_value_column_raises_error(self):
        """Test that missing value column raises AssertionError."""
        mock_catalog = Mock()
        mock_table = Mock()
        mock_table.columns = ["timestamp", "year"]
        mock_catalog.get_table = Mock(return_value=mock_table)

        tbl_cfg = {"table_name": "test_table", "timestamp_col": "timestamp", "value_col": "missing_value"}

        with pytest.raises(AssertionError, match="Value column"):
            pa.get_filterable_columns(tbl_cfg, mock_catalog)

    def test_only_timestamp_and_value_columns(self):
        """Test table with only timestamp and value columns."""
        mock_catalog = Mock()
        mock_table = Mock()
        mock_table.columns = ["timestamp", "kw_per_vehicle"]
        mock_catalog.get_table = Mock(return_value=mock_table)

        tbl_cfg = {"table_name": "test_table", "timestamp_col": "timestamp", "value_col": "kw_per_vehicle"}

        with patch("profile_adapter.logger"):
            result = pa.get_filterable_columns(tbl_cfg, mock_catalog)

        assert result["filterable_columns"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
