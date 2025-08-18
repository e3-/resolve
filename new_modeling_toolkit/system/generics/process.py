from __future__ import annotations

from typing import ClassVar
from typing import Self

from pydantic import Field
from pydantic import model_validator

from new_modeling_toolkit.core.linkage import LinkageRelationshipType
from new_modeling_toolkit.core.three_way_linkage import ThreeWayLinkage


class Process(ThreeWayLinkage):
    """Define an input product -> plant -> output product.

    The input & output products **must** be tied to nodes, since we want to be tracking product flows.

    I didn't want to use the Linkage or ThreeWayLinkage, because they were too messy for this use case.

    As an input, there is an associated variable cost & conversion efficiency.
        - If the product is not also an **output**, then the conversion efficiency effectively "destroys" the product.
        - The conversion efficiency is in units of the product's base units / plant's "working" units
          (e.g., MMBtu / MWh for a power plant, ton/something for biofuel feedstock)
    """

    SAVE_PATH: ClassVar[str] = "processes.csv"

    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "process"
    _component_type_1 = "plants"
    _component_type_2 = "products"
    _component_type_3 = "products"
    _attribute_to_announce = "processes"

    # TODO: Allow the process instance to dynamically recognize which of plant or demand is linked to it. See
    #  new_modeling_toolkit/core/linkage.py::_AllToPolicy as inspiration.
    @property
    def plant(self):  # TODO: rename? plant or demand
        return self.instance_1

    @property
    def consumed_product(self):
        return self.instance_2

    @property
    def produced_product(self):
        return self.instance_3

    conversion_rate: float = Field(1, description="Units of input product needed per output product produced.")
    input_capture_rate: float = Field(0, description="Volumetric fraction of input captured.")
    output_capture_rate: float = Field(1, description="Volumetric fraction of output captured, post-conversion.")


class ChargeProcess(Process):
    """A process used to model product storage charging"""

    SAVE_PATH = "charging_processes.csv"
    _attribute_to_announce = "charging_processes"


class SequestrationProcess(Process):
    """A process used to model product sequestration"""

    SAVE_PATH = "sequestration_processes.csv"

    output_capture_rate: float = Field(0, description="Volumetric fraction of output captured, post-conversion.")
    sequestration_rate: float = Field(1, description="Volumetric fraction of product sequestered.")

    @model_validator(mode="after")
    def validate_capture_and_sequestration_rates(self) -> Self:
        """Validate that sum of output capture rate and sequestration rate is not greater than 1."""
        assert (
            self.output_capture_rate + self.sequestration_rate <= 1
        ), f"For `{self.__class__.__name__}` `{self.name}`: the sum of the `output_capture_rate` and `sequestration_rate` cannot exceed 1."
        return self

    @model_validator(mode="after")
    def validate_same_input_and_output(self) -> Self:
        """Validate that the input and output of the sequestration process are the same."""

        assert self.consumed_product.name == self.produced_product.name
        return self
