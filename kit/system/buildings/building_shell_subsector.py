from kit.core import component
from kit.core import dir_str
from kit.core.linkage import Linkage


class BuildingShellSubsector(component.BaseComponent):
    """This class defines a BuildingShellSubsector object and its methods."""

    ######################
    # Mapping Attributes #
    ######################
    building_shell_types: dict[str, Linkage] = {}
    sectors: dict[str, Linkage] = {}


if __name__ == "__main__":
    test_subsector = Sector(name="Test building shell subsector")
    print(f"From test object: {test_subsector}")

    test_subsector_csv = Sector.from_dir(
        data_path=dir_str.data_dir / "interim" / "building_shell_sectors"
    )
    print(f"From csv file: {test_subsector_csv}")
