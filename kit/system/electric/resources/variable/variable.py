from kit.system.electric.resources.generic import BaseGenericResource
from kit.system.electric.resources.generic import BaseGenericResourceGroup


class BaseVariableResource(BaseGenericResource):
    pass


class BaseVariableResourceGroup(BaseGenericResourceGroup, BaseVariableResource):
    pass
