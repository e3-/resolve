from kit.system.electric.resources.generic import BaseGenericResource
from kit.system.electric.resources.generic import BaseGenericResourceGroup


class BaseUnitCommitmentResource(BaseGenericResource):
    pass


class BaseUnitCommitmentResourceGroup(
    BaseGenericResourceGroup, BaseUnitCommitmentResource
):
    pass
