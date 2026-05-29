from kit.system.electric.resources.variable.variable import BaseVariableResource
from kit.system.electric.resources.variable.variable import BaseVariableResourceGroup


class BaseSolarResource(BaseVariableResource):
    pass


class BaseSolarResourceGroup(BaseVariableResourceGroup, BaseSolarResource):
    pass
