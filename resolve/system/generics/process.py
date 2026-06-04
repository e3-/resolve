from __future__ import annotations

from typing import ClassVar
from typing import Self

from pydantic import Field
from pydantic import model_validator

from resolve.core.linkage import LinkageRelationshipType
from resolve.core.three_way_linkage import ThreeWayLinkage


class Process(ThreeWayLinkage):
    """Define a three-way-linkage between input product, plant/demand, and output product.

    This class represents a transformation process where an input product is consumed
    by a Plant or Demand object to produce an output product
    (input product → plant/demand → output product), with associated conversion parameters
    and capture rates. Both inputs and outputs must be Product objects.

    Attributes:
        SAVE_PATH: File path for saving process configurations.
        plant: The plant or demand component (instance_1) performing the conversion.
        consumed_product: The input product (instance_2) being consumed.
        produced_product: The output product (instance_3) being produced.
        conversion_rate: Units of input product needed per unit of output product.
        input_capture_rate: Fraction of input product that can be captured (0-1).
        output_capture_rate: Fraction of output product that is captured post-conversion (0-1).

    Note:
        The conversion efficiency is in units of the product's base units / plant's "working" units
          (e.g., MMBtu / MWh for a power plant, ton/something for biofuel feedstock)
        If a product is only consumed (not produced elsewhere), use DemandToProduct linkage instead.
    """

    SAVE_PATH: ClassVar[str] = "processes.csv"

    _RELATIONSHIP_TYPE = LinkageRelationshipType.MANY_TO_MANY
    _class_descriptor = "process"
    _component_type_1 = "plants"
    _component_type_2 = "products"
    _component_type_3 = "products"
    _attribute_to_announce = "processes"

    # TODO: Allow the process instance to dynamically recognize which of plant or demand is linked to it. See
    #  resolve/core/linkage.py::_AllToPolicy as inspiration.
    @property
    def plant(self):  # TODO: rename? plant or demand
        """Get the plant or demand component performing the conversion.

        Returns:
            Plant or Demand: The component that consumes input and produces output.
        """
        return self.instance_1

    @property
    def consumed_product(self):
        """Get the input (consumed) product being consumed in this process.

        Returns:
            Product: The product consumed as input to the conversion process.
        """
        return self.instance_2

    @property
    def produced_product(self):
        """Get the output (produced)product being produced in this process.

        Returns:
            Product: The product produced as output from the conversion process.
        """
        return self.instance_3

    conversion_rate: float = Field(
        1,
        description=(
            "Process conversion efficiency expressed as units of input product needed per unit of output "
            "product produced. Higher values indicate lower efficiency (more input required). Default 1.0 assumes 1:1 "
            "conversion."
        ),
        gt=0,
    )
    input_capture_rate: float = Field(
        0,
        description=(
            "Volumetric fraction (0-1) of input product that can be captured during processing, "
            "typically for environmental control or recycling. Default 0.0 indicates no input capture."
        ),
        ge=0,
        le=1,
    )
    output_capture_rate: float = Field(
        1,
        description=(
            "Volumetric fraction (0-1) of output product that is captured post-conversion for further "
            "processing or environmental control. Default 1.0 indicates complete output capture."
        ),
        ge=0,
        le=1,
    )


class ChargeProcess(Process):
    """Model storage charging processes for energy and product storage systems.

    This class represents processes where products (typically energy) are stored
    for later use. The charging process converts input products into stored forms with associated
    conversion losses and capture rates.

    Attributes:
        SAVE_PATH: File path for saving charging process configurations.

    Note:
        ChargeProcess inherits all attributes from the base Process class.
    """

    SAVE_PATH = "charging_processes.csv"
    _attribute_to_announce = "charging_processes"


class SequestrationProcess(Process):
    """Model product sequestration processes for product capture.

    This class represents processes where products (e.g., pollutants) are removed from
    the system through sequestration. The sequestration process handles the same input and output product,
    with fractions being either captured for potential reuse or permanently sequestered.
    The sum of output_capture_rate and sequestration_rate cannot exceed 1.0.

    Attributes:
        SAVE_PATH: File path for saving sequestration process configurations.
        output_capture_rate: Fraction of output product captured for potential reuse (0-1).
        sequestration_rate: Fraction of product permanently sequestered (0-1).

    Note:
        The input and output products must be the same for sequestration processes,
        representing the conservation of the material being processed.

        Total material balance: output_capture_rate + sequestration_rate ≤ 1.0
        The remainder (if any) represents process losses or emissions.
    """

    SAVE_PATH = "sequestration_processes.csv"

    output_capture_rate: float = Field(
        0,
        description=(
            "Volumetric fraction (0-1) of output product captured post-conversion for potential reuse, "
            "recycling, or further processing. Default 0.0 indicates no output capture for reuse."
        ),
        ge=0,
        le=1,
    )
    sequestration_rate: float = Field(
        1,
        description=(
            "Volumetric fraction (0-1) of product permanently sequestered and removed from the system. "
            "Default 1.0 indicates complete sequestration of processed material."
        ),
        ge=0,
        le=1,
    )

    @model_validator(mode="after")
    def validate_capture_and_sequestration_rates(self) -> Self:
        """Validate material balance constraints for sequestration processes.

        Ensures that the combined fractions of captured and sequestered product
        do not exceed the total available product (100%).

        Returns:
            Self: The validated SequestrationProcess instance.

        Raises:
            AssertionError: If output_capture_rate + sequestration_rate > 1.0.

        Note:
            The validation allows for process losses when the sum is less than 1.0.
        """
        assert self.output_capture_rate + self.sequestration_rate <= 1, (
            f"For `{self.__class__.__name__}` `{self.name}`: the sum of the `output_capture_rate` and "
            f"`sequestration_rate` cannot exceed 1."
        )
        return self

    @model_validator(mode="after")
    def validate_same_input_and_output(self) -> Self:
        """Validate that input and output products are identical for sequestration.

        Sequestration processes must have the same product as both input and output
        since they represent physical processing of a single material type rather
        than conversion between different materials. This ensures proper material
        tracking and conservation.

        Returns:
            Self: The validated SequestrationProcess instance.

        Raises:
            AssertionError: If consumed_product and produced_product names differ.

        Example:
            Valid: CO₂ → carbon capture plant → CO₂ (with fractions captured/sequestered)
            Invalid: Natural gas → capture plant → CO₂ (this would be a conversion process)
        """

        assert self.consumed_product.name == self.produced_product.name
        return self
