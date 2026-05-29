from kit.system.electric.resources.shed_dr import BaseShedDrResource
from kit.system.electric.resources.shed_dr import BaseShedDrResourceGroup
from kit.system.electric.resources.storage import BaseStorageResource
from kit.system.electric.resources.storage import BaseStorageResourceGroup


class BaseFlexLoadResource(BaseShedDrResource, BaseStorageResource):
    ###########################
    # Flexible Load Attribute #
    ###########################
    pass


class BaseFlexLoadResourceGroup(
    BaseShedDrResourceGroup, BaseStorageResourceGroup, BaseFlexLoadResource
):
    pass
