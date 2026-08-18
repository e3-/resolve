from __future__ import annotations

from typing import Annotated
from typing import Any
from typing import ClassVar
from typing import Union

import pandas as pd
import pyomo.environ as pyo
from kit.core.custom_model import FieldCategory
from kit.core.custom_model import Metadata
from kit.core.utils.core_utils import convert_to_bool
from loguru import logger
from pydantic import Field
from pydantic import model_validator

from resolve.core.component import Component
from resolve.core.component import LastUpdatedOrderedDict
from resolve.core.model import ModelTemplate
from resolve.core.temporal import timeseries as ts
from resolve.core.three_way_linkage import CustomConstraintLinkage
from resolve.system import Asset
from resolve.system.generics.demand import Demand
from resolve.system.generics.generic_linkages import DemandToProduct
from resolve.system.generics.generic_linkages import ProductToBlend
from resolve.system.generics.generic_linkages import ProductToTransportation
from resolve.system.generics.generic_linkages import ZoneToProduct
from resolve.system.generics.plant import Plant
from resolve.system.generics.process import ChargeProcess
from resolve.system.generics.process import Process
from resolve.system.generics.process import SequestrationProcess


class Product(Component):
    """A global product type representing materials, fuels, or commodities in the system.

    This class represents various products (e.g., Hydrogen, Electricity, Natural Gas, CO2)
    that can be produced, consumed, transported, and traded within the modeling framework.
    Products can be either endogenously produced through system processes or treated as
    external commodities with fixed prices and availability constraints.

    The Product class manages complex relationships between producers and consumers,
    handles pricing mechanisms (hourly prices or annual price with monthly multipliers),
    and tracks production, consumption, and sequestration across the system.

    Attributes:
        processes: Dictionary of process linkages defining input-output relationships
            between products on plants, including production and consumption processes.
        charging_processes: Dictionary of charging process linkages for energy storage.
        zones: Dictionary of zone-to-product linkages for spatial product distribution.
        transportations: Dictionary of transportation linkages for product movement.
        demands: Dictionary of demand-to-product linkages for consumption requirements.
        product_blends: Dictionary of product blend linkages for fuel mixing.
        unit: Physical unit for the product (e.g., MWh, kg, tonnes).
        commodity: Boolean flag indicating if product is an external commodity (True)
            or endogenously produced (False).
        availability: Time series of maximum annual availability for commodity products.
        price_per_unit: Hourly time series of product prices.
        monthly_price_multiplier: Monthly price multiplier applied to annual prices.
        annual_price: Annual price time series used with monthly multipliers.

    Note:
        Products can be priced either through direct hourly price streams or by
        combining annual prices with monthly multipliers. For commodity products,
        pricing information is required. For endogenously produced products,
        prices are determined by the optimization based on marginal costs.

        The class supports both material balance tracking and economic optimization
        through production costs, consumption patterns, and availability constraints.
    """

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
    custom_constraints: Annotated[
        dict[str, CustomConstraintLinkage], Metadata(linkage_order=3, default_exclude=True)
    ] = {}

    unit: str

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
    ] = Field(None, default_freq="h", up_method="ffill", down_method="mean", weather_year=False)

    monthly_price_multiplier: Annotated[
        ts.NumericTimeseries | None,
        Metadata(units="unitless", category=FieldCategory.OPERATIONS, excel_short_title="Multiplier"),
    ] = Field(None, default_freq="MS", up_method="ffill", down_method="mean")

    annual_price: Annotated[
        ts.NumericTimeseries | None, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Annual Price")
    ] = Field(None, default_freq="YS", up_method="interpolate", down_method="sum")

    @property
    def consumers(self) -> dict[str, Demand | Plant]:
        """Get all consumers of this product in the system.

        Returns:
            dict: Dictionary mapping consumer names to Demand or Plant instances
                that consume this product, including both direct demands and
                plants that use this product as an input in their processes.
        """
        return self._consumers()

    def _consumers(self) -> dict[str, Demand | Plant]:
        """Internal method to identify all consumers of this product.

        Aggregates consumers from both direct demand linkages and plant processes
        that consume this product as an input material or fuel.

        Returns:
            dict: Combined dictionary of demands and plants that consume this product.
        """
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
        """Get all producers of this product in the system.

        Returns:
            dict: Dictionary mapping producer names to Asset instances that
                produce this product through their operational processes.
        """
        return self._producers()

    def _producers(self) -> dict[str, Asset]:
        """Internal method to identify all producers of this product.

        Examines all processes to find assets that produce this product as an output.
        This method should be customized by subclasses to handle specific product
        types and their unique production pathways.

        Returns:
            dict: Dictionary of assets that produce this product through processes.

        Note:
            Subclasses should provide unique definitions for this method to handle
            specific producer identification logic for different product types.
        """
        return {
            plant_or_demand.instance_1.name: plant_or_demand.instance_1
            for plant_or_demand in self.processes.values()
            if plant_or_demand.instance_3.name == self.name
        }

    @property
    def sequestration_plants(self) -> dict[str, Asset]:
        """Get all sequestration plants linked to this product.

        Returns:
            dict: Dictionary mapping plant names to Asset instances that have
                sequestration processes capable of capturing and storing this product.

        Note:
            Sequestration is primarily relevant for pollutant products like CO2
            that can be captured and stored rather than released to the atmosphere.
        """
        return {
            sequestration_process.instance_1.name: sequestration_process.instance_1
            for sequestration_process in self.processes.values()
            if isinstance(sequestration_process, SequestrationProcess)
        }

    @model_validator(mode="before")
    @classmethod
    def validate_hourly_prices_and_availability(cls, values: dict[str, Any]):
        """Validate product pricing and availability configuration.

        Ensures proper configuration of product pricing through either direct hourly
        prices or combination of annual prices with monthly multipliers. Also validates
        that availability constraints are only set for commodity products.

        For commodity products, pricing can be specified through:
        1. Direct hourly price_per_unit time series, OR
        2. Combination of annual_price and monthly_price_multiplier

        When using option 2, the method calculates hourly prices by:
        1. Interpolating and extrapolating annual prices to 2000-2100 timeframe
        2. Resampling to monthly frequency with forward-fill
        3. Mapping monthly multipliers to all months in the time horizon
        4. Multiplying annual prices by corresponding monthly multipliers

        Args:
            values: Dictionary of field values being validated.

        Returns:
            dict: Validated and potentially modified field values with proper
                pricing configuration and cleared fields for non-commodity products.

        Raises:
            ValueError: If pricing configuration is invalid for commodity products.

        Warns:
            Issues warnings when conflicting pricing methods are provided or when
            non-commodity products have pricing/availability fields set.

        Note:
            For non-commodity (endogenously produced) products, all pricing and
            availability fields are automatically cleared since prices are determined
            by the optimization based on production costs and market dynamics.
        """
        # TODO (2022-03-31): Rewrite using a more robust approach rather than the current brute-force
        # method for price calculation from annual and monthly components.
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
                df = df.resample("YS").interpolate().resample("h", closed="right").ffill()

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
        """Validate product configuration after model initialization.

        Performs post-system initialization validation to ensure commodity products have
        required pricing information. This validation occurs after all model
        components have been loaded and linked.

        Raises:
            ValueError: If a commodity product lacks required price_per_unit specification.
        """
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
                doc=f"Annual consumption of product ({self.unit})",
            ),
            annual_total_production=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_total_production,
                doc=f"Annual production of product ({self.unit})",
            ),
            annual_total_sequestration=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_total_sequestration,
                doc=f"Annual sequestration of product ({self.unit})",
            ),
            consumption_availability_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                rule=self._consumption_availability_constraint,
            ),
        )

        return pyomo_components

    def _total_consumption(self, block, modeled_year, dispatch_window, timestamp):
        """Calculate total product consumption across all components in system.

        Aggregates product consumption from all linked consumers including both
        direct demand components and plants that use this product as an input
        in their production processes.

        Args:
            block: Pyomo block containing consumption variables.
            modeled_year: Year for consumption calculation.
            dispatch_window: Dispatch window (e.g., representative day).
            timestamp: Specific hour within the dispatch window.

        Returns:
            pyo.Expression: Total hourly consumption across all consumers in product units.

        Note:
            Only includes consumers that have consumption formulation blocks defined.
            Missing formulation blocks are skipped to avoid calculation errors.
        """
        return sum(
            consumer.formulation_block.consumption[self.name, modeled_year, dispatch_window, timestamp]
            for consumer in self.consumers.values()
            if hasattr(consumer.formulation_block, "consumption")
        )

    def _total_production(self, block, modeled_year, dispatch_window, timestamp):
        """Calculate total product production across all components in system.

        Aggregates product production from all linked producers including plants
        and other assets that generate this product as an output from their
        operational processes.

        Args:
            block: Pyomo block containing production variables.
            modeled_year: Year for production calculation.
            dispatch_window: Dispatch window (e.g., representative day).
            timestamp: Specific hour within the dispatch window.

        Returns:
            pyo.Expression: Total hourly production across all producers in product units.

        Note:
            Only includes producers that have production formulation blocks defined.
            Missing formulation blocks are skipped to avoid calculation errors.
        """
        return sum(
            producer.formulation_block.production[self.name, modeled_year, dispatch_window, timestamp]
            for producer in self.producers.values()
            if hasattr(producer.formulation_block, "production")
        )

    def _total_sequestration(self, block, modeled_year, dispatch_window, timestamp):
        """Calculate total product sequestration across all sequestration facilities.

        Aggregates product sequestration (capture and storage) from all linked
        sequestration plants. This is primarily relevant for pollutant products
        like CO2 that can be captured rather than released to the atmosphere.

        Args:
            block: Pyomo block containing sequestration variables.
            modeled_year: Year for sequestration calculation.
            dispatch_window: Dispatch window (e.g., representative day).
            timestamp: Specific hour within the dispatch window.

        Returns:
            pyo.Expression: Total hourly sequestration across all facilities in product units.

        Note:
            Only includes sequestration plants with operational rules defined.
            Should only be non-zero for pollutant products that can be captured.
        """
        return sum(
            plant.formulation_block.produced_product_sequestered[self.name, modeled_year, dispatch_window, timestamp]
            for plant in self.sequestration_plants.values()
            if plant.has_operational_rules
        )

    def _annual_total_consumption(self, block, modeled_year):
        """Calculate total annual consumption by aggregating hourly consumption.

        Uses the model's temporal aggregation method to properly weight and sum
        hourly consumption values across all dispatch windows to get annual totals.

        Args:
            block: Pyomo block containing total_consumption expression.
            modeled_year: Year for consumption aggregation.

        Returns:
            pyo.Expression: Total annual consumption in product units, properly
                weighted for dispatch window frequencies and temporal representation.
        """
        return block.model().sum_timepoint_component_slice_to_annual(block.total_consumption[modeled_year, :, :])

    def _annual_total_production(self, block, modeled_year):
        """Calculate total annual production by aggregating hourly production.

        Uses the model's temporal aggregation method to properly weight and sum
        hourly production values across all dispatch windows to get annual totals.

        Args:
            block: Pyomo block containing total_production expression.
            modeled_year: Year for production aggregation.

        Returns:
            pyo.Expression: Total annual production in product units, properly
                weighted for dispatch window frequencies and temporal representation.
        """
        return block.model().sum_timepoint_component_slice_to_annual(block.total_production[modeled_year, :, :])

    def _annual_total_sequestration(self, block, modeled_year):
        """Calculate total annual sequestration by aggregating hourly sequestration.

        Uses the model's temporal aggregation method to properly weight and sum
        hourly sequestration values across all dispatch windows to get annual totals.

        Args:
            block: Pyomo block containing total_sequestration expression.
            modeled_year: Year for sequestration aggregation.

        Returns:
            pyo.Expression: Total annual sequestration in product units, properly
                weighted for dispatch window frequencies and temporal representation.
        """
        return block.model().sum_timepoint_component_slice_to_annual(block.total_sequestration[modeled_year, :, :])

    def _consumption_availability_constraint(self, block, modeled_year):
        """Enforce annual consumption limits based on product availability.

        Creates a constraint ensuring that total annual consumption does not exceed
        the specified availability limit for commodity products. This constraint
        is only active when availability is explicitly defined for the product.

        Args:
            block: Pyomo block containing annual_total_consumption expression.
            modeled_year: Year for constraint application.

        Returns:
            pyo.Constraint or pyo.Constraint.Skip: Availability constraint limiting
                consumption to available quantities, or Skip if no availability limit.
        """
        if self.availability is not None:
            return block.annual_total_consumption[modeled_year] <= self.availability.data.at[modeled_year]
        else:
            return pyo.Constraint.Skip


class ProductBlend(Product):
    """A product representing a blend of multiple constituent products.

    This class extends the Product class to handle blended products where multiple
    constituent products are mixed according to specified blending ratios. Common
    examples include fuel blends like gasoline with ethanol or natural gas with
    renewable gas components.

    The class enforces blending constraints to ensure constituent products are
    mixed within specified minimum and maximum ratios, and that total blending
    ratios are feasible (minimum ratios sum to ≤1, maximum ratios sum to ≥1).

    Attributes:
        products: Dictionary of ProductToBlend linkages defining constituent products
            and their blending parameters (min_blend, max_blend ratios).

    Note:
        The blending functionality is currently under development. Constraint
        methods return pyo.Constraint.Skip until the blending implementation
        is finalized.
    """

    products: dict[str, ProductToBlend] = {}

    @model_validator(mode="after")
    def validate_blend(self):
        """Validate that blending ratios are mathematically feasible.

        Ensures that the minimum and maximum blending rates across all constituent
        products allow for feasible blending solutions. The sum of minimum rates
        must be ≤1 to avoid over-specification, and the sum of maximum rates must
        be ≥1 to ensure complete blending is possible.

        Raises:
            AssertionError: If minimum blending rates sum to >1 or maximum blending
                rates sum to <1, indicating infeasible blending specifications.
        """
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
