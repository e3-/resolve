from __future__ import annotations

from typing import ClassVar
from typing import TypeVar

from pydantic import ConfigDict

from kit.core.from_csv_mix_in import BaseFromCSVMixIn


# Create an alias Component class type annotation (see return value in `from_csv` method)
C = TypeVar("Component")
# TODO: This doesn't seem to work as-expected for return type annotation


class BaseComponent(BaseFromCSVMixIn):
    __TABLE_COUNTER: ClassVar[int] = 1
    model_config = ConfigDict(protected_namespaces=())
