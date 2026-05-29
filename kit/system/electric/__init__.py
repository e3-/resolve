from kit.system.electric import resources
from kit.system.electric.resources.flex_load import BaseFlexLoadResource
from kit.system.electric.resources.storage import BaseStorageResourceGroup
from kit.system.electric.resources.thermal import BaseThermalResourceGroup
from kit.system.electric.resources.thermal import BaseThermalUnitCommitmentResource
from kit.system.electric.resources.variable.variable import BaseVariableResource
from kit.system.electric.resources.variable.variable import BaseVariableResourceGroup


class BaseElectricResource(
    BaseThermalUnitCommitmentResource, BaseVariableResource, BaseFlexLoadResource
):
    """A "factory" class that creates the appropriate type of electric sector resource based on the defined `type`."""


class BaseElectricResourceGroup(
    BaseThermalResourceGroup, BaseStorageResourceGroup, BaseVariableResourceGroup
):
    """A "factory" class that creates the appropriate type of electric sector resource based on the defined `type`."""
