from __future__ import annotations

import copy
from typing import Any
from typing import ClassVar
from typing import Dict
from typing import List
from typing import Optional
from typing import Self
from typing import Type

from loguru import logger
from pydantic import ConfigDict

from kit.core.from_csv_mix_in import BaseFromCSVMixIn
from kit.core.utils.core_utils import filter_not_none
from kit.core.utils.core_utils import map_dict


class BaseComponent(BaseFromCSVMixIn):
    __TABLE_COUNTER: ClassVar[int] = 1
    model_config = ConfigDict(protected_namespaces=())

    @property
    def timeseries_attrs(self) -> list[str]:
        """Names of all ``Timeseries``-typed fields on this instance."""
        return [
            attr
            for attr, field_settings in self.model_fields.items()
            if self.field_is_timeseries(field_info=field_settings)
        ]

    def revalidate(self) -> None:
        """Hook called by downstream linkage machinery after all linkages are announced.

        Override in subclasses to run cross-field or cross-component validations that can
        only be performed once linked instances are available.
        """

    def extract_attribute_from_components(
        self,
        component_dict: Optional[Dict[str, "BaseComponent"]],
        attribute: str,
    ) -> Optional[Dict[str, Any]]:
        """Extract a named attribute from every component in ``component_dict``.

        Args:
            component_dict: mapping of name → component, or ``None``.
            attribute: name of the attribute to extract from each component.

        Returns:
            Mapping of the same keys to the extracted attribute values, or ``None`` if
            ``component_dict`` is ``None``.
        """
        if component_dict is None:
            return None
        else:
            component_attributes = map_dict(
                dict_=component_dict,
                func=lambda component: getattr(component, attribute),
            )

            return component_attributes

    def sum_attribute_from_components(
        self,
        component_dict: Optional[Dict[str, "BaseComponent"]],
        attribute: str,
        timeseries: bool = False,
        skip_none: bool = False,
    ) -> Optional[Any]:
        """Sum a named attribute across all components in ``component_dict``.

        For scalar attributes the values are summed directly. For ``Timeseries`` attributes
        the underlying ``data`` series are summed and wrapped in a new instance of the same
        ``Timeseries`` subclass as the first component's value.

        Args:
            component_dict: mapping of name → component, or ``None``.
            attribute: name of the attribute to sum.
            timeseries: set to ``True`` when the attribute is a ``Timeseries`` object.
            skip_none: if ``True``, components where the attribute is ``None`` are skipped;
                returns ``None`` if all components are skipped.

        Returns:
            Aggregated scalar or ``Timeseries``, or ``None`` if ``component_dict`` is ``None``
            or all values were skipped.
        """

        if component_dict is None:
            return None
        else:
            component_attributes = self.extract_attribute_from_components(
                component_dict=component_dict, attribute=attribute
            )
            if skip_none:
                component_attributes = {
                    key: value
                    for key, value in component_attributes.items()
                    if value is not None
                }
                if len(component_attributes) == 0:
                    return None

            if timeseries:
                ts_instances = list(component_attributes.values())
                ts_cls = type(ts_instances[0])
                component_attributes = map_dict(
                    dict_=component_attributes, func=lambda x: x.data
                )
                aggregate = ts_cls(
                    name=attribute, data=sum(component_attributes.values())
                )
            else:
                aggregate = sum(component_attributes.values())

            return aggregate

    def sum_timeseries_attributes(
        self,
        attributes: List[str],
        name: str,
        skip_none: bool = False,
    ) -> Optional[Any]:
        """Sum multiple ``Timeseries`` attributes on this instance.

        The result is a new instance of the same ``Timeseries`` subclass as the first
        attribute, with its ``data`` equal to the element-wise sum of all inputs.

        Args:
            attributes: names of the ``Timeseries`` attributes to sum.
            name: name assigned to the resulting ``Timeseries``.
            skip_none: if ``True``, ``None`` attributes are silently skipped; returns
                ``None`` when all are ``None``.

        Returns:
            A ``Timeseries`` instance containing the summed data, or ``None`` if all
            inputs were skipped.
        """
        timeseries_attributes = [getattr(self, attribute) for attribute in attributes]

        if skip_none:
            timeseries_attributes = filter_not_none(timeseries_attributes)
            if len(timeseries_attributes) == 0:
                return None

        ts_cls = type(timeseries_attributes[0])
        result = ts_cls(
            name=name, data=sum([ts_.data for ts_ in timeseries_attributes])
        )

        return result

    def copy(
        self,
        exclude: Optional[list[str]] = None,
        include_linkages: bool = False,
        update: Optional[dict[str, Any]] = None,
        new_class: Optional[Type[Self]] = None,
    ) -> Self:
        """Return a deep copy of this component, optionally changing its class or field values.

        Linkage and three-way-linkage attributes are excluded from the copy by default. If
        ``include_linkages=True``, each linked instance is re-wired to point to the new copy
        (shallow copy of the linkage object — mutating a shared linkage attribute on either
        side will affect the other).

        Args:
            exclude: additional field names to exclude from the copy.
            include_linkages: if ``True``, re-announce all two-way and three-way linkages on
                the copy so they point to the new instance.
            update: field overrides applied to the copied data before constructing the new
                instance. Note: if the original has a ``formulation_block``, supplying
                ``update`` will drop it from the copy (logged as a warning).
            new_class: if provided, the copy is instantiated as this class instead of
                ``self.__class__``.

        Returns:
            New component instance of the same (or specified) class.
        """
        attrs_to_excl = getattr(self, "linkage_attributes", []) + getattr(
            self, "three_way_linkage_attributes", []
        )
        if exclude is not None:
            attrs_to_excl += exclude
        attrs_to_excl = set(attrs_to_excl)
        data = self.model_dump(exclude=set(attrs_to_excl))
        if update is not None:
            data.update(**update)
        data = copy.deepcopy(data)
        class_to_use = self.__class__ if new_class is None else new_class
        copied = class_to_use.model_validate(data)

        if update is not None and getattr(self, "formulation_block", None) is not None:
            logger.warning(
                f"Cannot duplicate formulation block for `{self.name}` because fields have been updated in the `copy()` "
                f"method. Setting `formulation_block` to None on the copy."
            )
        elif getattr(self, "_formulation_block", None) is not None:
            copied._formulation_block = self.formulation_block.clone()

        if include_linkages:
            for linkage_attribute in getattr(
                copied, "_linkage_attributes", lambda: []
            )():
                curr_linkages = getattr(self, linkage_attribute)
                for linkage in curr_linkages.values():
                    # Warning: this creates a shallow copy of the linkage, meaning updating a linkage attribute on
                    # the copied version will change the original attribute, and vice versa.
                    linkage_copy = linkage.copy()
                    if linkage_copy.instance_from is self:
                        linkage_copy.instance_from = copied
                        linkage_copy.name = (copied.name, linkage_copy.instance_to.name)
                    elif linkage_copy.instance_to is self:
                        linkage_copy.instance_to = copied
                        linkage_copy.name = (
                            linkage_copy.instance_from.name,
                            copied.name,
                        )
                    else:
                        raise ValueError(
                            f"When copying Component `{self.name} with linkages, the Component was not found in "
                            f"`instance_from` or `instance_to` of the connected Linkage `{linkage.name}`"
                        )
                    linkage_copy.announce_linkage_to_instances()

            for linkage_attribute in getattr(self, "three_way_linkage_attributes", []):
                curr_linkages = getattr(self, linkage_attribute)
                for linkage in curr_linkages.values():
                    linkage_copy = linkage.copy()
                    if linkage_copy.instance_1 is self:
                        linkage_copy.instance_1 = copied
                        linkage_copy.name = (
                            copied.name,
                            linkage_copy.instance_2.name,
                            linkage_copy.instance_3.name,
                        )
                    elif linkage_copy.instance_2 is self:
                        linkage_copy.instance_2 = copied
                        linkage_copy.name = (
                            linkage_copy.instance_1.name,
                            copied.name,
                            linkage_copy.instance_3.name,
                        )
                    elif linkage_copy.instance_3 is self:
                        linkage_copy.instance_3 = copied
                        linkage_copy.name = (
                            linkage_copy.instance_1.name,
                            linkage_copy.instance_2.name,
                            copied.name,
                        )
                    else:
                        raise ValueError(
                            f"When copying Component `{self.name} with linkages, the Component was not found in "
                            f"`instance_from` or `instance_to` of the connected Linkage `{linkage.name}`"
                        )
                    linkage_copy.announce_linkage_to_instances()

        return copied
