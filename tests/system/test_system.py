class TestSystem:
    def test_copy(self, test_system_with_operational_groups):
        system = test_system_with_operational_groups
        system_copy = system.copy()

        # Check that all the expected components are present
        assert system.components.keys() == system_copy.components.keys()

        assert system.linkages.keys() == system_copy.linkages.keys()
        for linkage_type, linkages_list in system.linkages.items():
            assert [linkage.name for linkage in linkages_list] == [
                linkage_copy.name for linkage_copy in system_copy.linkages[linkage_type]
            ]
        assert system.three_way_linkages.keys() == system_copy.three_way_linkages.keys()
        for three_way_linkage_type, three_way_linkages_list in system.three_way_linkages.items():
            assert [linkage.name for linkage in three_way_linkages_list] == [
                linkage_copy.name for linkage_copy in system_copy.three_way_linkages[three_way_linkage_type]
            ]

        # For each component:
        for component_name in system.components:
            original_component = system.components[component_name]
            copy_component = system_copy.components[component_name]

            # Check that the components are not the same object
            assert original_component is not copy_component

            # Check that all non-linkage attributes are equal
            for attr_name in original_component.non_linkage_attributes:
                assert getattr(original_component, attr_name) == getattr(copy_component, attr_name)

            # For all linkage-dict attributes on the component:
            for linkage_attr_name in original_component.linkage_attributes:
                # Check that the dict keys are the same
                assert (
                    getattr(original_component, linkage_attr_name).keys()
                    == getattr(copy_component, linkage_attr_name).keys()
                )

                # For each linkage in the linkage-dict attribute
                for linkage_name in getattr(original_component, linkage_attr_name).keys():
                    original_component_linkage = getattr(original_component, linkage_attr_name)[linkage_name]
                    copy_component_linkage = getattr(copy_component, linkage_attr_name)[linkage_name]

                    # Check that the instance_from name and instance_to name are the same
                    assert original_component_linkage.instance_from.name == copy_component_linkage.instance_from.name
                    assert original_component_linkage.instance_to.name == copy_component_linkage.instance_to.name

                    # Check that the actual instances are not the same
                    assert original_component_linkage.instance_from is not copy_component_linkage.instance_from
                    assert original_component_linkage.instance_to is not copy_component_linkage.instance_to

                    # Check that the objects in the linkage are in the appropriate system
                    assert (
                        original_component_linkage.instance_from
                        is system.components[original_component_linkage.instance_from.name]
                    )
                    assert (
                        original_component_linkage.instance_to
                        is system.components[original_component_linkage.instance_to.name]
                    )
                    assert (
                        copy_component_linkage.instance_to
                        is system_copy.components[copy_component_linkage.instance_to.name]
                    )
                    assert (
                        copy_component_linkage.instance_from
                        is system_copy.components[copy_component_linkage.instance_from.name]
                    )

                    # Check that components in the linkages are not in the wrong system
                    assert original_component_linkage.instance_from not in system_copy.components.values()
                    assert original_component_linkage.instance_to not in system_copy.components.values()
                    assert copy_component_linkage.instance_to not in system.components.values()
                    assert copy_component_linkage.instance_from not in system.components.values()

            for three_way_linkage_attr_name in original_component.three_way_linkage_attributes:
                # Check that the dict keys are the same
                assert (
                    getattr(original_component, three_way_linkage_attr_name).keys()
                    == getattr(copy_component, three_way_linkage_attr_name).keys()
                )

                # For each linkage in the linkage-dict attribute
                for three_way_linkage_name in getattr(original_component, three_way_linkage_attr_name).keys():
                    original_component_linkage = getattr(original_component, three_way_linkage_attr_name)[
                        three_way_linkage_name
                    ]
                    copy_component_linkage = getattr(copy_component, three_way_linkage_attr_name)[
                        three_way_linkage_name
                    ]

                    # Check that the instance_1, instance_2, and instance_3 name are the same
                    assert original_component_linkage.instance_1.name == copy_component_linkage.instance_1.name
                    assert original_component_linkage.instance_2.name == copy_component_linkage.instance_2.name
                    assert original_component_linkage.instance_3.name == copy_component_linkage.instance_3.name

                    # Check that the actual instances are not the same
                    assert original_component_linkage.instance_1 is not copy_component_linkage.instance_1
                    assert original_component_linkage.instance_2 is not copy_component_linkage.instance_2
                    assert original_component_linkage.instance_3 is not copy_component_linkage.instance_3

                    # Check that the objects in the linkage are in the appropriate system
                    assert (
                        original_component_linkage.instance_1
                        is system.components[original_component_linkage.instance_1.name]
                    )
                    assert (
                        original_component_linkage.instance_2
                        is system.components[original_component_linkage.instance_2.name]
                    )
                    assert (
                        original_component_linkage.instance_3
                        is system.components[original_component_linkage.instance_3.name]
                    )
                    assert (
                        copy_component_linkage.instance_1
                        is system_copy.components[copy_component_linkage.instance_1.name]
                    )
                    assert (
                        copy_component_linkage.instance_2
                        is system_copy.components[copy_component_linkage.instance_2.name]
                    )
                    assert (
                        copy_component_linkage.instance_3
                        is system_copy.components[copy_component_linkage.instance_3.name]
                    )

                    # Check that components in the linkages are not in the wrong system
                    assert original_component_linkage.instance_1 not in system_copy.components.values()
                    assert original_component_linkage.instance_2 not in system_copy.components.values()
                    assert original_component_linkage.instance_3 not in system_copy.components.values()
                    assert copy_component_linkage.instance_1 not in system.components.values()
                    assert copy_component_linkage.instance_2 not in system.components.values()
                    assert copy_component_linkage.instance_3 not in system.components.values()
