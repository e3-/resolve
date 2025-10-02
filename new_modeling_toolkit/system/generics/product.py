from __future__ import annotations

from typing import Annotated
from typing import Any
from typing import ClassVar
from typing import Union

import pandas as pd
import pint
import pyomo.environ as pyo
from loguru import logger
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.utils.core_utils import convert_to_bool
from new_modeling_toolkit.system import Asset
from new_modeling_toolkit.system.generics.demand import Demand
from new_modeling_toolkit.system.generics.generic_linkages import DemandToProduct
from new_modeling_toolkit.system.generics.generic_linkages import ProductToBlend
from new_modeling_toolkit.system.generics.generic_linkages import ProductToTransportation
from new_modeling_toolkit.system.generics.generic_linkages import ZoneToProduct
from new_modeling_toolkit.system.generics.plant import Plant
from new_modeling_toolkit.system.generics.process import ChargeProcess
from new_modeling_toolkit.system.generics.process import Process
from new_modeling_toolkit.system.generics.process import SequestrationProcess


class Product(Component):
    """A global product type (e.g., Hydrogen, Electricity) to be modeled in the system."""

    SAVE_PATH: ClassVar[str] = "products"

    # TODO: Use proper "Annotated" functionality for initializing dictionaries
    processes: Annotated[dict[Union[tuple[str, str], str], Process], Metadata(category=FieldCategory.OPERATIONS)] = (
        Field(
            default_factory=dict,
            description="These three-way linkages define the input-output relationships between products on a plant",
        )
    )
    charging_processes: dict[str, ChargeProcess] = {}
    zones: dict[str, ZoneToProduct] = {}
    transportations: dict[str, ProductToTransportation] = {}
    demands: dict[str, DemandToProduct] = {}
    product_blends: dict[str, ProductToBlend] = {}

    unit: pint.Unit

    commodity: Annotated[bool, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        False,
        description="Set to `False` if this fuel is endogenously produced; otherwise, it will be considered a "
        "'commodity' with a fixed price stream and potentially a fixed consumption limit.",
    )
    availability: Annotated[
        ts.NumericTimeseries | None, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Availability")
    ] = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="sum",
        description="This input sets the maximum potential for this commodity product. If the commodity product is "
        "used in RESOLVE, consumption of this product will never exceed the availability in a given year.",
    )

    price_per_unit: Annotated[
        ts.NumericTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Price"),
    ] = Field(None, default_freq="H", up_method="ffill", down_method="mean", weather_year=False)

    monthly_price_multiplier: Annotated[
        ts.NumericTimeseries | None,
        Metadata(units=units.unitless, category=FieldCategory.OPERATIONS, excel_short_title="Multiplier"),
    ] = Field(None, default_freq="MS", up_method="ffill", down_method="mean")

    annual_price: Annotated[
        ts.NumericTimeseries | None, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Annual Price")
    ] = Field(None, default_freq="YS", up_method="interpolate", down_method="sum")

    @property
    def consumers(self) -> dict[str, Demand | Plant]:
        return self._consumers()

    def _consumers(self) -> dict[str, Demand | Plant]:
        demands = {
            demand_product.instance_from.name: demand_product.instance_from for demand_product in self.demands.values()
        }
        plants = {
            process.plant.name: process.plant
            for process in self.processes.values()
            if (process.consumed_product.name == self.name) and isinstance(process.instance_1, Plant)
        }
        consumers = dict(demands | plants)
        return consumers

    @property
    def producers(self) -> dict[str, Asset]:
        return self._producers()

    def _producers(self) -> dict[str, Asset]:
        """Subclass-by-subclass definition of producers. Ensure that each `Product` subclass has a unique definition
        for this method"""
        return {
            plant_or_demand.instance_1.name: plant_or_demand.instance_1
            for plant_or_demand in self.processes.values()
            if plant_or_demand.instance_3.name == self.name
        }

    @property
    def sequestration_plants(self) -> dict[str, Asset]:
        return {
            sequestration_process.instance_1.name: sequestration_process.instance_1
            for sequestration_process in self.processes.values()
            if isinstance(sequestration_process, SequestrationProcess)
        }

    @field_validator("unit", mode="before")
    @classmethod
    def convert_unit_string(cls, unit: str | pint.Unit) -> pint.Unit:
        if isinstance(unit, str):
            return units.parse_units(unit)
        else:
            return unit

    @model_validator(mode="before")
    @classmethod
    def validate_hourly_prices_and_availability(cls, values: dict[str, Any]):
        """Hourly price stream or combination of monthly price shape + annual price shape must be passed.

        # TODO 2022-03-31: This should be rewritten/made more robust. The current implementation should work
                           in most cases but takes a brute-force approach.

        Steps to calculate the monthly price shape from the monthly shape and annual price:
            #. Interpolate & extrapolate annual price to 2000-2100 (this is currently hard-coded)
            #. Resample to monthly
            #. Map monthly price shape to all months in the 2000-2100 time horizon
            #. Multiply annual price by monthly_price_multiplier

        Also validates that `availability` is unset if fuel is not a commodity
        """
        price_per_unit_alias = cls.model_fields["price_per_unit"].alias
        commodity_alias = cls.model_fields["commodity"].alias

        commodity = values.get("commodity", values.get(commodity_alias, cls.model_fields["commodity"].default))
        values["commodity"] = convert_to_bool(commodity)

        price_per_unit = values.get("price_per_unit", values.get(price_per_unit_alias, None))
        annual_price = values.get("annual_price", None)
        monthly_price_multiplier = values.get("monthly_price_multiplier", None)
        availability = values.get("availability", None)

        if not commodity:
            if not ((price_per_unit is None) and (annual_price is None) and (availability is None)):
                logger.warning(
                    "If product is not a commodity, product prices and availability should not be defined, all prices are set to None."
                )
                values["price_per_unit"] = None
                values["annual_price"] = None
                values["availability"] = None

        else:
            if price_per_unit is not None:
                if any([monthly_price_multiplier, annual_price]):
                    logger.warning(
                        f"For {values['name']}, if `price_per_unit` is provided, `monthly_price_multiplier` and "
                        f"`annual_price` will be ignored."
                    )
            elif all([monthly_price_multiplier, annual_price]):
                # Calculate hourly price shape from two other attributes (first to interpolate annual prices, aligned with
                #   field settings, then to monthly ffill)
                df = annual_price.data
                df[max(annual_price.data.index) + pd.DateOffset(years=1)] = 0
                df = df.resample("YS").interpolate().resample("H", closed="right").ffill()

                # Multiply by monthly_price_multiplier
                temp = monthly_price_multiplier.data.copy(deep=True)
                temp.index = temp.index.month
                multipliers = pd.Series(df.index.month.map(temp), index=df.index)
                df = df * multipliers

                values["price_per_unit"] = ts.NumericTimeseries(data=df, name="price_per_unit")

            else:
                raise ValueError(
                    f"For {values['name']}, product price can be entered via `price_per_unit` or by providing both "
                    f"`monthly_price_multiplier` and `annual_price`"
                )

        return values

    def revalidate(self):
        """Check that product price is specified if commodity is True."""
        if self.commodity and self.price_per_unit is None:
            raise ValueError(
                f"Error in {self.__class__.__name__} {self.name}: `price_per_unit` must be specified if `commodity` is "
                f"set to True."
            )

    def _construct_operational_rules(
        self, model: ModelTemplate, construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)
        pyomo_components.update(
            # TODO: Are these operational rules? Or merely output expressions?
            total_consumption=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._total_consumption,
            ),
            total_production=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._total_production,
            ),
            # todo: move to pollutant as output expr
            total_sequestration=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._total_sequestration,
            ),
            annual_total_consumption=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_total_consumption,
                doc=f"Annual consumption of product ({self.unit:e3})",
            ),
            annual_total_production=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_total_production,
                doc=f"Annual production of product ({self.unit:e3})",
            ),
            annual_total_sequestration=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_total_sequestration,
                doc=f"Annual sequestration of product ({self.unit:e3})",
            ),
            consumption_availability_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                rule=self._consumption_availability_constraint,
            ),
        )

        return pyomo_components

    def _total_consumption(self, block, modeled_year, dispatch_window, timestamp):
        """Calculate total product consumption across all plants and demands in system."""
        return sum(
            consumer.formulation_block.consumption[self.name, modeled_year, dispatch_window, timestamp]
            for consumer in self.consumers.values()
            if hasattr(consumer.formulation_block, "consumption")
        )

    def _total_production(self, block, modeled_year, dispatch_window, timestamp):
        """Calculate total product production across all plants and demands in system."""
        return sum(
            producer.formulation_block.production[self.name, modeled_year, dispatch_window, timestamp]
            for producer in self.producers.values()
            if hasattr(producer.formulation_block, "production")
        )

    def _total_sequestration(self, block, modeled_year, dispatch_window, timestamp):
        """Calculate total sequestration of product across all sequestration plants in system. Should only be non-zero for pollutants."""
        return sum(
            plant.formulation_block.produced_product_sequestered[self.name, modeled_year, dispatch_window, timestamp]
            for plant in self.sequestration_plants.values()
            if plant.has_operational_rules
        )

    def _annual_total_consumption(self, block, modeled_year):
        """Calculate total consumption annually"""
        return block.model().sum_timepoint_component_slice_to_annual(block.total_consumption[modeled_year, :, :])

    def _annual_total_production(self, block, modeled_year):
        """Calculate total production annually"""
        return block.model().sum_timepoint_component_slice_to_annual(block.total_production[modeled_year, :, :])

    def _annual_total_sequestration(self, block, modeled_year):
        """Calculate total sequestration of product annually"""
        return block.model().sum_timepoint_component_slice_to_annual(block.total_sequestration[modeled_year, :, :])

    def _consumption_availability_constraint(self, block, modeled_year):
        """Annual total consumption should be less than availaibility. This should only be active when `availability` is not None."""
        if self.availability is not None:
            return block.annual_total_consumption[modeled_year] <= self.availability.data.at[modeled_year]
        else:
            return pyo.Constraint.Skip

class ProductBlend(Product):

    products: dict[str, ProductToBlend] = {}

    @model_validator(mode="after")
    def validate_blend(self):
        assert (
            sum(product.min_blend for product in self.products.values()) <= 1
        ), f"Minimum blending rates must sum to less than 1 on ProductBlend {self.name}"
        assert (
            sum(product.max_blend for product in self.products.values()) >= 1
        ), f"Maximum blending rates must sum to greater than 1 on ProductBlend {self.name}"

    def _construct_operational_rules(
        self, model: ModelTemplate, construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)
        pyomo_components.update(
            products=pyo.Set(initialize=list(self.products.values())),
            link_blend_and_product_consumption=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._link_blend_and_product_consumption,
                doc="Ensure that blend and total product consumption are equal",
            ),
            min_blend_constraint=pyo.Constraint(
                self.formulation_block.products,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._min_blend_constraint,
            ),
            max_blend_constraint=pyo.Constraint(
                self.formulation_block.products,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._max_blend_constraint,
            ),
        )
        return pyomo_components

    def _link_blend_and_product_consumption(self, block, modeled_year, dispatch_window, timestamp):
        """Ensure that consumption of all products in blend equals the consumption of the blend itself"""
        # TODO: This is needed, but we still need to decide on how to to implement product blending
        return pyo.Constraint.Skip

    def _min_blend_constraint(self, block, product_name, modeled_year, dispatch_window, timestamp):
        """Constrain minimum consumption of individual product as fraction of blend."""
        # TODO: This is needed, but we still need to decide on how to implement product blending
        return pyo.Constraint.Skip

    def _max_blend_constraint(self, block, product_name, modeled_year, dispatch_window, timestamp):
        """Constrain maximum consumption of individual product as fraction of blend."""
        # TODO: This is needed, but we still need to decide on how to implement product blending
        return pyo.Constraint.Skip


Product.model_rebuild()
ProductBlend.model_rebuild()
