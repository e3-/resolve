from kit.system.electric.resources.variable.variable import BaseVariableResource
from kit.system.electric.resources.variable.variable import BaseVariableResourceGroup


class BaseWindResource(BaseVariableResource):
    pass


class BaseWindResourceGroup(BaseVariableResourceGroup, BaseWindResource):
    pass
