import pandas as pd
import pint
import pytest
from pydantic import ValidationError

from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.system import Demand
from new_modeling_toolkit.system import Electricity
from new_modeling_toolkit.system import Plant
from new_modeling_toolkit.system.generics.product import Product
from new_modeling_toolkit.system.pollution.pollutant import Pollutant
from tests.system.component_test_template import ComponentTestTemplate


class TestProduct(ComponentTestTemplate):
    _COMPONENT_CLASS = Product
    _COMPONENT_NAME = "Product_1"
    _SYSTEM_COMPONENT_DICT_NAME = "products"

    def test_convert_unit_string(self, make_component_copy):
        product = make_component_copy()
        assert isinstance(product.unit, pint.Unit)

    def test_total_consumption(self, make_component_with_block_copy, first_index, last_index):
        product = make_component_with_block_copy()
        block = product.formulation_block
        resources = block.model().system.resources

        for consumer in product.consumers.keys():
            if isinstance(product.consumers[consumer], Plant) or isinstance(product.consumers[consumer], Demand):
                product.consumers[consumer].formulation_block.consumption[self._COMPONENT_NAME, first_index] = 0
            else:  # consumer is a resource
                product.consumers[consumer].formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                    self._COMPONENT_NAME, first_index
                ] = 0

        input_resources = 0
        for resource in resources.values():
            if hasattr(resource.formulation_block, "power_input"):
                resource.formulation_block.power_input[first_index].fix(0)
                input_resources += 1

        assert not block.total_consumption[first_index].expr() == 100
        assert block.total_consumption[first_index].expr() == 0

        for consumer in product.consumers.keys():
            if isinstance(product.consumers[consumer], Plant) or isinstance(product.consumers[consumer], Demand):
                product.consumers[consumer].formulation_block.consumption[self._COMPONENT_NAME, last_index] = 100
            else:  # consumer is a resource
                product.consumers[consumer].formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                    self._COMPONENT_NAME, last_index
                ] = 100

        for resource in resources.values():
            if hasattr(resource.formulation_block, "power_input"):
                resource.formulation_block.power_input[last_index].fix(100)

        assert block.total_consumption[last_index].expr() == (
            100 * len(product.consumers) + 100 * 1e3 * input_resources * isinstance(product, Electricity)
        )

    def test_total_production(self, make_component_with_block_copy, first_index, last_index):
        product = make_component_with_block_copy()
        block = product.formulation_block
        resources = block.model().system.resources

        for producer in product.producers.keys():
            product.producers[producer].formulation_block.production[self._COMPONENT_NAME, first_index] = 0

        for resource in resources.values():
            resource.formulation_block.power_output[first_index].fix(0)

        assert not block.total_production[first_index].expr() == 100
        assert block.total_production[first_index].expr() == 0

        for producer in product.producers.keys():
            product.producers[producer].formulation_block.production[self._COMPONENT_NAME, last_index] = 10

        for resource in resources.values():
            resource.formulation_block.power_output[last_index].fix(100)

        assert block.total_production[last_index].expr() == (
            10 * len(product.producers) + 100 * 1e3 * len(resources) * isinstance(product, Electricity)
        )


class TestCommodityProduct(TestProduct):
    _COMPONENT_CLASS = Product
    _COMPONENT_NAME = "CommodityProduct1"
    _SYSTEM_COMPONENT_DICT_NAME = "products"

    def _update_consumption(self, product: Product, modeled_year: pd.Timestamp, value: int | float):
        if len(product.consumers) > 0:
            for consumer in product.consumers.values():
                if isinstance(consumer, Demand) or isinstance(consumer, Plant):
                    consumer.formulation_block.consumption[product.name, modeled_year, :, :] = value
                else:  # consumer is a resource
                    consumer.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                        product.name, modeled_year, :, :
                    ] = value

    def _update_production(self, product: Product, modeled_year: pd.Timestamp, value: int | float):
        if len(product.producers) > 0:
            for producer in product.producers.values():
                producer.formulation_block.production[product.name, modeled_year, :, :] = value

    def test_annual_total_consumption(self, make_component_with_block_copy, first_index, last_index):
        product = make_component_with_block_copy()
        block = product.formulation_block

        modeled_year, dispatch_window, timestamp = first_index
        self._update_consumption(product, modeled_year, 100)
        if len(product.consumers) == 0:
            assert block.annual_total_consumption[modeled_year].expr() == 0
        else:
            assert block.annual_total_consumption[modeled_year].expr() == 365 * 100 * 3 * len(product.consumers)
            modeled_year, dispatch_window, timestamp = last_index
            self._update_consumption(product, modeled_year, 200)
            assert not block.annual_total_consumption[modeled_year].expr() == 365 * 100 * 3 * len(product.consumers)

    def test_annual_total_production(self, make_component_with_block_copy, first_index, last_index):
        product = make_component_with_block_copy()
        block = product.formulation_block

        modeled_year, dispatch_window, timestamp = first_index
        self._update_production(product, modeled_year, 100)
        if len(product.producers) == 0:
            assert block.annual_total_production[modeled_year].expr() == 0
        else:
            assert block.annual_total_production[modeled_year].expr() == 365 * 100 * 3 * len(product.producers)
            modeled_year, dispatch_window, timestamp = last_index
            self._update_production(product, modeled_year, 200)
            assert not block.annual_total_production[modeled_year].expr() == 365 * 100 * 3 * len(product.producers)

    def test_consumption_availability_constraint(self, make_component_with_block_copy, first_index, last_index):
        product = make_component_with_block_copy()
        block = product.formulation_block
        modeled_year, dispatch_window, timestamp = last_index

        if product.availability is None or len(product.consumers) == 0:
            pass
        else:
            self._update_consumption(product, modeled_year, 10)
            assert block.consumption_availability_constraint[modeled_year].expr()

            self._update_consumption(product, modeled_year, 100_000.0 / 365.0 / 3.0 / len(product.consumers))
            assert block.consumption_availability_constraint[modeled_year].expr()

            self._update_consumption(product, modeled_year, 200)
            assert not block.consumption_availability_constraint[modeled_year].expr()

    def test_validate_hourly_prices_and_availability(self, make_component_copy):
        original_product: Product = make_component_copy()
        init_kwargs = original_product.model_dump(
            include={
                "name",
                "SAVE_PATH",
                "unit",
                "commodity",
                "availability",
                "price_per_unit",
                "monthly_price_multiplier",
                "annual_price",
            }
        )

        # Test if commodity is False, price per unit, annual price, and availability set to None
        kwargs = init_kwargs.copy()
        kwargs.update(commodity=False)

        test_product = self._COMPONENT_CLASS(**kwargs)
        assert test_product.price_per_unit is None
        assert test_product.annual_price is None
        assert test_product.availability is None

        monthly_price_multiplier = ts.NumericTimeseries(
            name="monthly_price_multiplier",
            data=pd.Series(
                index=pd.date_range(
                    start="2025-01-01",
                    end="2025-12-01",
                    freq="MS",
                    name="timestamp",
                ),
                data=300.0,
                name="value",
            ),
        )
        annual_price = ts.NumericTimeseries(
            name="annual_price",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01",
                    ],
                    name="timestamp",
                ),
                data=300.0,
                name="value",
            ),
        )

        # Test if error is raised when prices are provided incompletely
        kwargs = init_kwargs.copy()
        del kwargs["price_per_unit"]
        kwargs.update(monthly_price_multiplier=monthly_price_multiplier)
        with pytest.raises(ValidationError) as e:
            self._COMPONENT_CLASS(**kwargs)
        assert "product price can be entered via `price_per_unit` or by providing both" in str(e.value)

        # Test if monthly_price_multiplier and annual_price are ignored when price_per_unit is provided
        kwargs = init_kwargs.copy()
        kwargs.update(
            annual_price=annual_price,
            monthly_price_multiplier=monthly_price_multiplier,
        )
        new_product = self._COMPONENT_CLASS(**kwargs)
        new_price_per_unit_data = new_product.price_per_unit.data
        old_price_per_unit_data = original_product.price_per_unit.data
        pd.testing.assert_series_equal(new_price_per_unit_data, old_price_per_unit_data)

        # Test that monthly_price_multiplier * annual_price works as expected
        expected_price_per_unit_in_all_hours = 300.0 * 300.0
        kwargs = init_kwargs.copy()
        del kwargs["price_per_unit"]
        kwargs.update(annual_price=annual_price, monthly_price_multiplier=monthly_price_multiplier)
        new_product = self._COMPONENT_CLASS(**kwargs)
        new_product_price = new_product.price_per_unit.data
        assert (new_product_price[new_product_price.index.year == 2025] == expected_price_per_unit_in_all_hours).all()
        assert (new_product_price[new_product_price.index.year != 2025] == 0).all()


class TestPollutant(TestProduct):
    _COMPONENT_CLASS = Pollutant
    _COMPONENT_NAME = "Pollutant1"
    _SYSTEM_COMPONENT_DICT_NAME = "pollutants"

    def test_total_sequestration(self, make_component_with_block_copy, first_index, last_index):
        product = make_component_with_block_copy()
        block = product.formulation_block

        product_name = "Pollutant1"
        seq_plant_1 = product.sequestration_plants["Sequestration1"]
        seq_plant_1.formulation_block.produced_product_sequestered[product_name, first_index] = 100

        seq_plant_2 = product.sequestration_plants["Sequestration2"]
        seq_plant_2.formulation_block.produced_product_sequestered[product_name, first_index] = 50

        assert block.total_sequestration[first_index].expr() == 150
