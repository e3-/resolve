from kit.system.electric.resources.generic import BaseGenericResource
from kit.system.electric.resources.generic import BaseGenericResourceGroup


class BaseStorageResource(BaseGenericResource):
    pass


class BaseStorageResourceGroup(BaseGenericResourceGroup, BaseStorageResource):
    pass
