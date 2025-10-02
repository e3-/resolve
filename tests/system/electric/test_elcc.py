import pandas as pd

from new_modeling_toolkit.system.electric.elcc import ELCCSurface
from tests.system.component_test_template import ComponentTestTemplate


class TestELCCSurface(ComponentTestTemplate):
    _COMPONENT_CLASS = ELCCSurface
    _COMPONENT_NAME = "TestELCCSurface"
    _SYSTEM_COMPONENT_DICT_NAME = "elcc_surfaces"

    def test_ELCC_MW_constraint(self, make_component_with_block_copy, first_index):
        elcc_surface = make_component_with_block_copy()
        block = elcc_surface.formulation_block
        first_year = first_index[0]

        block.ELCC_facet_value["test_elcc_facet", "TestPRM", first_year] = 100.0

        # ELCC_MW = ELCC_facet_value
        block.ELCC_MW[first_year].fix(100.0)
        assert block.ELCC_MW_constraint["test_elcc_facet", "TestPRM", first_year].upper() == 0
        assert block.ELCC_MW_constraint["test_elcc_facet", "TestPRM", first_year].body() == 0
        assert block.ELCC_MW_constraint["test_elcc_facet", "TestPRM", first_year].expr()

        # ELCC_MW < ELCC_facet_value
        block.ELCC_MW[first_year].fix(90.0)
        assert block.ELCC_MW_constraint["test_elcc_facet", "TestPRM", first_year].upper() == 0.0
        assert block.ELCC_MW_constraint["test_elcc_facet", "TestPRM", first_year].body() == -10.0
        assert block.ELCC_MW_constraint["test_elcc_facet", "TestPRM", first_year].expr()

        # ELCC_MW > ELCC_facet_value
        block.ELCC_MW[first_year].fix(110.0)
        assert block.ELCC_MW_constraint["test_elcc_facet", "TestPRM", first_year].upper() == 0.0
        assert block.ELCC_MW_constraint["test_elcc_facet", "TestPRM", first_year].body() == 10.0
        assert not block.ELCC_MW_constraint["test_elcc_facet", "TestPRM", first_year].expr()

    def test_ELCC_facet_value(self, make_component_with_block_copy):
        elcc_surface = make_component_with_block_copy()
        facet = elcc_surface.facets["test_elcc_facet"].instance_from
        block = elcc_surface.formulation_block

        for year, b_expected, facet_value_expected in [
            (pd.Timestamp("2025-01-01 00:00"), 0.0, (100.0 * 0.25 * 20.0) + (100.0 * 0.15 * 20.0)),
            (pd.Timestamp("2030-01-01 00:00"), 0.0, (100.0 * 0.25 * 15.0) + (100.0 * 0.15 * 15.0)),
            (pd.Timestamp("2035-01-01 00:00"), 5.0, 5.0 + (100.0 * 0.25 * 10.0) + (100.0 * 0.15 * 10.0)),
            (pd.Timestamp("2045-01-01 00:00"), 5.0, 5.0 + (100.0 * 0.25 * 5.0) + (100.0 * 0.15 * 5.0)),
        ]:
            intercept_value = facet.axis_0.data.at[year]
            assert intercept_value == b_expected
            axis_1_value = 0
            for _resource, link in elcc_surface.assets.items():
                resource = link.instance_from
                axis_multiplier = link.elcc_axis_multiplier
                resource.formulation_block.reliability_capacity["TestPRM", year].fix(100.0)
                axis_1_value += axis_multiplier * 100.0

            assert block.ELCC_facet_value["test_elcc_facet", "TestPRM", year].expr() == facet_value_expected

    def test_results_reporting(self, make_component_with_block_copy):
        elcc_surface = make_component_with_block_copy()
        elcc_surface._construct_output_expressions(construct_costs=True)
        block = elcc_surface.formulation_block

        assert block.ELCC_MW.doc == "ELCC Surface Total Reliability Capacity (MW)"
        assert block.ELCC_facet_value.doc == "ELCC Facet Value for Policy"
