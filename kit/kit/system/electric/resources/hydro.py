from kit.system.electric.resources.generic import BaseGenericResource
from kit.system.electric.resources.generic import BaseGenericResourceGroup


class BaseHydroResource(BaseGenericResource):
    pass


class BaseHydroResourceGroup(BaseGenericResourceGroup, BaseHydroResource):
    pass
