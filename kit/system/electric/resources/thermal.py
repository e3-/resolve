from kit.system.electric.resources.generic import BaseGenericResource
from kit.system.electric.resources.generic import BaseGenericResourceGroup
from kit.system.electric.resources.unit_commitment import BaseUnitCommitmentResource
from kit.system.electric.resources.unit_commitment import (
    BaseUnitCommitmentResourceGroup,
)


class BaseThermalResource(BaseGenericResource):
    pass


class BaseThermalUnitCommitmentResource(
    BaseThermalResource, BaseUnitCommitmentResource
):
    pass


class BaseThermalResourceGroup(BaseGenericResourceGroup, BaseThermalResource):
    pass


class BaseThermalUnitCommitmentResourceGroup(
    BaseUnitCommitmentResourceGroup, BaseThermalUnitCommitmentResource
):
    pass
