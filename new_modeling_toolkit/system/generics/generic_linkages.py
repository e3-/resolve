from __future__ import annotations

from typing import Annotated
from typing import Any

import pydantic
from pydantic import Field
from pydantic import model_validator

from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.linkage import Linkage
from new_modeling_toolkit.core.linkage import LinkageRelationshipType
from new_modeling_toolkit.core.temporal import timeseries as ts


class ProductToBlend(Linkage):

    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    component_type_from_: str = "product_blends"
    component_type_to_: str = "products"

    min_blend: Annotated[float, Field(ge=0, le=1)] = 0
    max_blend: Annotated[float, Field(ge=0, le=1)] = 1

    @model_validator(mode="after")
    def validate_blend(self):
        assert self.min_blend <= self.max_blend, (
            f"{self.product.name}'s minimum blend must be less than or equal to maximum blend on {self.name} "
            f"ProductBlend"
        )

    @property
    def blend(self):
        return self.instance_from

    @property
    def product(self):
        return self.instance_to


class ProductToTransportation(Linkage):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    component_type_from_: str = "products"
    component_type_to_: str = "transportations"
    SAVE_PATH = "products_to_transportations.csv"

    hurdle_rate_forward_direction: Annotated[
        ts.NumericTimeseries, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Forward Hurdle")
    ] = Field(
        default_factory=ts.NumericTimeseries.zero,
        default_freq="YS",
        up_method="interpolate",
        down_method="mean",
        title=f"Forward Hurdle Rate",
    )
    hurdle_rate_reverse_direction: Annotated[
        ts.NumericTimeseries, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Reverse Hurdle")
    ] = Field(
        default_factory=ts.NumericTimeseries.zero,
        default_freq="YS",
        up_method="interpolate",
        down_method="mean",
        title=f"Reverse Hurdle Rate",
    )

    @property
    def product(self):
        return self.instance_from

    @property
    def transportation(self):
        return self.instance_to


# TODO: probably want to update to Process with "None" output product
class DemandToProduct(Linkage):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    component_type_from_: str = "demands"
    component_type_to_: str = "demand_products"

    @property
    def demand(self):
        return self.instance_from

    @property
    def product(self):
        return self.instance_to

    @property
    def unit(self):
        return self.input.unit


class ZoneToProduct(Linkage):
    """Each `Node` is linked to at least one `Product`, as long as they're interchangeable (e.g., bio-methane & fossil natural gas)."""

    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    component_type_from_: str = "zones"
    component_type_to_: str = "products"
    SAVE_PATH = "zones_to_products.csv"

    #######################################
    # Penalties for Unmet Demand and Overproduction #
    #######################################
    penalty_unmet_demand: Annotated[
        float, Metadata(category=FieldCategory.OPERATIONS, units=units.dollar / units.megawatt_hour)
    ] = Field(
        10000,
        description="Modeled penalty for unmet demand.",
        title=f"Unmet Demand Penalty",
    )

    penalty_overproduction: Annotated[
        float, Metadata(category=FieldCategory.OPERATIONS, units=units.dollar / units.megawatt_hour)
    ] = Field(
        10000,
        description="Modeled penalty for overproduced product.",
        title=f"Overproduced Product Penalty",
    )

    @property
    def product(self):
        return self.instance_to

    @property
    def zone(self):
        return self.instance_from


class ZoneToXDirectional(Linkage):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY

    from_zone: bool = False
    to_zone: bool = False

    @property
    def zone(self):
        return self.instance_from

    @pydantic.root_validator(skip_on_failure=True)
    @classmethod
    def linkage_is_from_zone_xor_to_zone(cls, values: dict[str, Any]):
        if not values["from_zone"] and not values["to_zone"]:
            raise ValueError(
                f"{cls.__name__} linkage for {values['name']} must have either 'from_zone' or 'to_zone' set to True."
            )
        elif values["from_zone"] and values["to_zone"]:
            raise ValueError(
                f"{cls.__name__} linkage for {values['name']} must have either 'from_zone' or 'to_zone' set to True, "
                f"but not both."
            )
        else:
            return values


class ZoneToDemand(ZoneToXDirectional):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    component_type_to_: str = "demands"
    SAVE_PATH = "zones_to_demands.csv"

    @property
    def demand(self):
        return self.instance_to


class FromZoneToDemand(ZoneToDemand):
    component_type_to_: str = "consuming_generic_demands"
    component_type_from_: str = "input_zones"

    from_zone: bool = True


class ToZoneToDemand(ZoneToDemand):
    component_type_to_: str = "producing_generic_demands"
    component_type_from_: str = "output_zones"

    to_zone: bool = True


class ZoneToPlant(ZoneToXDirectional):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    component_type_to_: str = "plants"
    SAVE_PATH = "zones_to_plants.csv"

    @property
    def plant(self):
        return self.instance_to


class FromZoneToPlant(ZoneToPlant):
    component_type_from_: str = "input_zones"
    component_type_to_: str = "consuming_generic_plants"

    from_zone: bool = True


class ToZoneToPlant(ZoneToPlant):
    component_type_from_: str = "output_zones"
    component_type_to_: str = "producing_generic_plants"

    to_zone: bool = True


class ZoneToFuelProductionPlant(ZoneToPlant):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    component_type_to_: str = "fuel_production_plants"

    @property
    def fuel_production_plant(self):
        return self.instance_to


class FromZoneToFuelProductionPlant(FromZoneToPlant, ZoneToFuelProductionPlant):
    component_type_from_: str = "input_zones"
    component_type_to_: str = "consuming_fuel_production_plants"


class ToZoneToFuelProductionPlant(ToZoneToPlant, ZoneToFuelProductionPlant):
    component_type_from_: str = "output_zones"
    component_type_to_: str = "producing_fuel_production_plants"


class ZoneToFuelStorage(ZoneToFuelProductionPlant):
    component_type_to_: str = "fuel_storage_plants"

    @property
    def fuel_storage_plant(self):
        return self.instance_to


class FromZoneToFuelStorage(FromZoneToPlant, ZoneToFuelStorage):
    component_type_from_: str = "input_zones"
    component_type_to_: str = "consuming_fuel_storage_plants"


class ToZoneToFuelStorage(ToZoneToPlant, ZoneToFuelStorage):
    component_type_from_: str = "output_zones"
    component_type_to_: str = "producing_fuel_storage_plants"

class ZoneToTransportation(ZoneToXDirectional):
    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    component_type_from_: str = "zones"
    component_type_to_: str = "transportations"
    SAVE_PATH = "zones_to_transportations.csv"

    @property
    def transportation(self):
        return self.instance_to


class FromZoneToTransportation(ZoneToTransportation):
    from_zone: bool = True


class ToZoneToTransportation(ZoneToTransportation):
    to_zone: bool = True
