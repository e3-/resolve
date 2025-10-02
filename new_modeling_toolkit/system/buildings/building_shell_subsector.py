from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import dir_str
from new_modeling_toolkit.core.linkage import Linkage


class BuildingShellSubsector(component.Component):
    """This class defines a BuildingShellSubsector object and its methods."""

    ######################
    # Mapping Attributes #
    ######################
    building_shell_types: dict[str, Linkage] = {}
    sectors: dict[str, Linkage] = {}


if __name__ == "__main__":
    test_subsector = Sector(name="Test building shell subsector")
    print(f"From test object: {test_subsector}")

    test_subsector_csv = Sector.from_dir(data_path=dir_str.data_dir / "interim" / "building_shell_sectors")
    print(f"From csv file: {test_subsector_csv}")
