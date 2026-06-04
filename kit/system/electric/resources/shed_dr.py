from kit.system.electric.resources.unit_commitment import BaseUnitCommitmentResource
from kit.system.electric.resources.unit_commitment import (
    BaseUnitCommitmentResourceGroup,
)


class BaseShedDrResource(BaseUnitCommitmentResource):
    pass


class BaseShedDrResourceGroup(BaseUnitCommitmentResourceGroup, BaseShedDrResource):
    pass
