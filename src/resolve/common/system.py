import inspect
import pathlib
import sys
from json import dumps
from typing import Optional

import pandas as pd
from loguru import logger
from pydantic import Field
from pydantic import validator
from tqdm import tqdm

from resolve.common import asset
from resolve.common import biomass_resource
from resolve.common import elcc
from resolve.common import fuel
from resolve.common import load_component
from resolve.common import policy
from resolve.common import reserve
from resolve.common import zone
from resolve.common.asset import tx_path
from resolve.common.asset.plant import resource
from resolve.common.fuel_system import electrolyzer
from resolve.common.fuel_system import fuel_conversion_plant
from resolve.common.fuel_system import fuel_storage
from resolve.common.fuel_system import fuel_transportation
from resolve.common.fuel_system import fuel_zone
from resolve.core import component
from resolve.core import linkage
from resolve.core.custom_model import convert_str_float_to_int
from resolve.core.temporal import timeseries as ts
from resolve.core.utils.core_utils import timer
from resolve.core.utils.util import DirStructure

# Mapping between `System` attribute name and component class to construct.


NON_COMPONENT_FIELDS = [
    "attr_path",
    "dir_str",
    "linkages",
    "name",
    "scenarios",
    "year_end",
    "year_start",
]

# Create a list of linkages to construct
LINKAGE_TYPES = [
    cls_obj
    for cls_name, cls_obj in inspect.getmembers(sys.modules["resolve.core.linkage"])
    if inspect.isclass(cls_obj)
]


class SystemCost(component.Component):
    """A basic cost data container.

    In the future, costs could be linked to other system components to calculate endogenously scaling costs.
    Alternative implementations could just have the `System` class be able to hold an arbitrary number of cost timeseries.
    """

    annual_cost: ts.NumericTimeseries = Field(
        default_factory=ts.Timeseries.zero,
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )

class System(component.Component):
    """Initializes Component and Linkage instances."""

    ####################
    # FIELDS FROM FILE #
    ####################
    # TODO: Tradeoff between using a Timeseries, which will be read automatically, and being able to constrain values.
    #  Think if there's a way to constrain data types--maybe only be subclassing timeseries?
    #  A silly way to do this would be to read them in as Timeseries but then use validators to convert them to dicts/lists

    """
    TODO (5/3):
    1. Make a list of timestamps we want to model (will eventually be more dynamic)
    2. Write methods for Timeseries that return a "view" of the timeseries that matches the timestamps we want to model

    """
    dir_str: DirStructure

    ##############
    # Components #
    ##############
    # fmt: off
    # TODO 2023-05-05: Probably can come up with a default data_filepath to reduce repeating name of component (e.g., data_filepath="assets")
    # Assets
    asset_groups: dict[str, asset.AssetGroup] = Field({}, data_filepath="asset_groups")
    fuel_storages: dict[str, fuel_storage.FuelStorage] = Field({}, data_filepath="fuel_storages")
    fuel_transportations: dict[str, fuel_transportation.FuelTransportation] = Field({}, data_filepath="fuel_transportations")
    electrolyzers: dict[str, electrolyzer.Electrolyzer] = Field({}, data_filepath="electrolyzers")
    fuel_conversion_plants: dict[str, fuel_conversion_plant.FuelConversionPlant] = Field({}, data_filepath="fuel_conversion_plants")
    generic_assets: dict[str, asset.Asset] = Field({}, data_filepath="assets")
    resources: dict[str, resource.Resource] = Field({}, data_filepath="resources")
    tranches: dict[str, asset.Tranche] = Field({}, data_filepath="assets")
    tx_paths: dict[str, tx_path.TXPath] = Field({}, data_filepath="tx_paths")

    # Policies
    emissions_policies: dict[str, policy.AnnualEmissionsPolicy] = Field({}, data_filepath="policies")
    energy_policies: dict[str, policy.AnnualEnergyStandard] = Field({}, data_filepath="policies")
    prm_policies: dict[str, policy.PlanningReserveMargin] = Field({}, data_filepath="policies")

    # Other component classes
    biomass_resources: dict[str, biomass_resource.BiomassResource] = Field({}, data_filepath="biomass_resources")
    candidate_fuels: dict[str, fuel.CandidateFuel] = Field({}, data_filepath="candidate_fuels")
    elcc_surfaces: dict[str, elcc.ELCCSurface] = Field({}, data_filepath="elcc_surfaces")
    fuel_zones: dict[str, fuel_zone.FuelZone] = Field({}, data_filepath="fuel_zones")
    final_fuels: dict[str, fuel.FinalFuel] = Field({}, data_filepath="final_fuels")
    loads: dict[str, load_component.Load] = Field({}, data_filepath="loads")
    reserves: dict[str, reserve.Reserve] = Field({}, data_filepath="reserves")
    system_costs: dict[str, SystemCost] = Field({}, data_filepath="system_costs")
    zones: dict[str, zone.Zone] = Field({}, data_filepath="zones")
    # fmt: on

    ############
    # Linkages #
    ############
    linkages: dict[str, list[linkage.Linkage]] = {}

    ##########
    # FIELDS #
    ##########
    # TODO 2023-05-05: year_start and year_end ideally would come from New
    year_start: Optional[int] = None
    year_end: Optional[int] = None

    scenarios: list = []

    # Convert strings that look like floats to integers for integer fields
    _convert_int = validator("year_start", "year_end", allow_reuse=True, pre=True)(convert_str_float_to_int)

    @property
    def electric_plants(self):
        return self.resources

    @property
    def electric_assets(self):
        return self.generic_assets | self.asset_groups | self.plants | self.resources | self.tx_paths | self.tranches

    @property
    def plants(self):
        """Superset of all `Asset` child classes."""
        return self.resources | self.fuel_production_plants | self.fuel_storages

    @property
    def assets(self):
        """Superset of all `Asset` child classes."""
        return self.electric_assets | self.fuel_transportations | self.fuel_storages

    @property
    def policies(self):
        """Superset of all `Policy` child classes."""
        return self.emissions_policies | self.energy_policies | self.prm_policies

    @property
    def _component_fields(self):
        """Return list of component FIELDS in `System` (by manually excluding non-`Component` attributes)."""
        return {name: field for name, field in self.__fields__.items() if name not in NON_COMPONENT_FIELDS}

    @property
    def components(self):
        """Return list of component ATTRIBUTES and "virtual" components (i.e., properties that are the union of other components)."""
        return (
            {name: getattr(self, name) for name, field in self.__fields__.items() if name not in NON_COMPONENT_FIELDS}
            | {"assets": self.assets}
            | {"plants": self.plants}
            | {"policies": self.policies}
        )

    @property
    def fuel_production_plants(self):
        return self.electrolyzers | self.fuel_conversion_plants

    @property
    def fuel_components(self):
        return self.fuel_production_plants | self.fuel_storages | self.fuel_transportations | self.fuel_zones

    def __init__(self, **data):
        """
        Initializes a electrical system based on csv inputs. The sequence of initialization can be found in the
        comments of the system class

        Args:
            graph_dict: the dictionary that determines the linkage between different components of the system
        """
        super().__init__(**data)

        ###########################################
        # READ IN COMPONENTS & LINKAGES FROM FILE #
        ###########################################
        self._construct_components()
        self.linkages = self._construct_linkages(
            linkage_subclasses_to_load=LINKAGE_TYPES, linkage_type="linkages", linkage_cls=linkage.Linkage
        )

        ##########################
        # ADDITIONAL VALIDATIONS #
        ##########################
        logger.info("Revalidating components...")
        for components in self.components.values():
            for instance in components.values():
                try:
                    instance.revalidate()
                except Exception as e:
                    raise AssertionError(f"Error encountered when revalidating instance `{instance.name}`") from e

        logger.info("Running remaining validations...")

    @timer
    def _construct_components(self):
        components_to_load = pd.read_csv(self.dir_str.data_interim_dir / "systems" / self.name / "components.csv")

        components_to_load = components_to_load.sort_values(["component", "instance"]).groupby("component")

        # Populate component attributes with data from instance CSV files
        # Get field class by introspecting the field info
        for field_name, field_info in self._component_fields.items():
            field_type = field_info.type_
            field_data_filepath = self.__fields__[field_name].field_info.extra["data_filepath"]

            self.update_component_attrs(
                field_name=field_name,
                field_type=field_type,
                field_data_filepath=field_data_filepath,
                components_to_load=components_to_load,
            )

    def update_component_attrs(
        self, *, field_name: str, field_type: "Component", field_data_filepath: str, components_to_load: pd.DataFrame
    ):
        """Load all components of a certain type listed in `components_to_load`."""
        if field_type.__name__ not in components_to_load.groups:
            logger.debug(f"Component type {field_type.__name__} not loaded because component type not recognized")
            # Escape this method
            return
        for component_name in tqdm(
            components_to_load.get_group(field_type.__name__)["instance"],
            desc=f"Loading {field_type.__name__}:".ljust(48),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            vintages = field_type.from_csv(
                self.dir_str.data_interim_dir / field_data_filepath / f"{component_name}.csv",
                scenarios=self.scenarios,
            )
            # TODO 2023-05-28: Sort of weird that this method directly works on the attr instead of returning a dict
            getattr(self, field_name).update(vintages)

    @timer
    def _construct_linkages(self, *, linkage_subclasses_to_load: list, linkage_type: str, linkage_cls):
        """This function now can be used to initialize both two- and three-way linkages."""
        if (self.dir_str.data_interim_dir / "systems" / self.name / f"{linkage_type}.csv").exists():
            linkages_to_load = pd.read_csv(
                self.dir_str.data_interim_dir / "systems" / self.name / f"{linkage_type}.csv"
            )
            linkages_to_load = self._get_scenario_linkages(linkages=linkages_to_load, scenarios=self.scenarios)
            linkages_to_load = linkages_to_load.groupby("linkage")

            for linkage_class in linkage_subclasses_to_load:
                # If no linkages of this class type specified by user, skip this iteration of the loop (`continue` keyword)
                if linkage_class.__name__ not in linkages_to_load.groups:
                    logger.debug(
                        f"Linkage type {linkage_class.__name__} not loaded because linkage type not recognized"
                    )
                else:
                    # Assume the data/interim folder has the same name as the file that lists the linkages
                    linkage_class.from_dir(
                        dir_path=self.dir_str.data_interim_dir / f"{linkage_type}",
                        linkages_df=linkages_to_load.get_group(linkage_class.__name__),
                        components_dict=self.components,
                        scenarios=self.scenarios,
                        linkages_csv_path=self.dir_str.data_interim_dir / "systems" / self.name / f"{linkage_type}.csv",
                    )
            # Announce linkages
            linkage_cls.announce_linkage_to_instances()

            return linkage_cls._instances
        else:
            return {}

    def _get_scenario_linkages(self, *, linkages: pd.DataFrame, scenarios: list):
        """Filter for the highest priority data based on scenario tags."""

        # Create/fill a dummy (base) scenario tag that has the lowest priority order
        if "scenario" not in linkages.columns:
            linkages["scenario"] = "__base__"
        # Create a dummy (base) scenario tag that has the lowest priority order
        linkages["scenario"] = linkages["scenario"].fillna("__base__")

        # Create a categorical data type in the order of the scenario priority order (lowest to highest)
        linkages["scenario"] = pd.Categorical(linkages["scenario"], ["__base__"] + scenarios)

        # Drop any scenarios that weren't provided in the scenario list (or the default `__base__` tag)
        len_linkages_unfiltered = len(linkages)
        linkages = linkages.sort_values("scenario").dropna(subset="scenario")

        # Log error if scenarios filtered out all data
        if len_linkages_unfiltered != 0 and len(linkages) == 0:
            err = f"No linkages for active scenario(s): {scenarios}. "
            logger.error(err)

        # Keep only highest priority scenario data
        linkages = linkages.groupby(["linkage", "component_from", "component_to"]).last().reset_index()

        return linkages

    @timer
    def resample_ts_attributes(
        self,
        modeled_years: tuple[int, int],
        weather_years: tuple[int, int],
        resample_weather_year_attributes=True,
        resample_non_weather_year_attributes=True,
    ):
        """Interpolate/extrapolate timeseries attributes so that they're all defined for the range of modeled years."""
        # Dictionary of objects & their attributes that were extrapolated (i.e., start/end dates too short)
        extrapolated = {}
        logger.info("Resampling timeseries attributes...")
        for field_name, components in {
            name: getattr(self, name) for name, field in self.__fields__.items() if name not in NON_COMPONENT_FIELDS
        }.items():
            logger.debug(f"{field_name.title()}")
            for instance in tqdm(
                components.values(),
                desc=f"{field_name.title()}:".rjust(48),
                bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
            ):
                extrapolated[instance.name] = instance.resample_ts_attributes(
                    modeled_years,
                    weather_years,
                    resample_weather_year_attributes=resample_weather_year_attributes,
                    resample_non_weather_year_attributes=resample_non_weather_year_attributes,
                )

        # Load treated differently: forecast future load
        for instance in tqdm(
            self.loads.keys(),
            desc=f"Loads".rjust(48),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            self.loads[instance].forecast_load(modeled_years=modeled_years, weather_years=weather_years)

        # loads to policies
        for inst in self.policies.keys():
            self.policies[inst].update_targets_from_loads()

        # ELCC treated differently
        for inst in self.elcc_surfaces.keys():
            for facet in self.elcc_surfaces[inst].facets:
                extrapolated[inst] = (
                    self.elcc_surfaces[inst]
                    .facets[facet]
                    .resample_ts_attributes(
                        modeled_years,
                        weather_years,
                        resample_weather_year_attributes=resample_weather_year_attributes,
                        resample_non_weather_year_attributes=resample_non_weather_year_attributes,
                    )
                )

        # Regularize timeseries attributes, if any, in linkages (same as components above)
        for linkage_class in self.linkages:
            for linkage_inst in tqdm(
                self.linkages[linkage_class],
                desc=f"{linkage_class.title()}:".rjust(48),
                bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
            ):
                extrapolated[", ".join(linkage_inst.name)] = linkage_inst.resample_ts_attributes(
                    modeled_years,
                    weather_years,
                    resample_weather_year_attributes=resample_weather_year_attributes,
                    resample_non_weather_year_attributes=resample_non_weather_year_attributes,
                )

        if extrapolated := {str(k): list(v) for k, v in extrapolated.items() if v is not None}:
            logger.debug(
                f"The following timeseries attributes were extrapolated to cover model years: \n{dumps(extrapolated, indent=4)}"
            )

    @timer
    def write_json_file(self, *, output_dir: pathlib.Path):
        logger.info("Saving system to JSON file.")
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(
            output_dir / f"{self.dir_str.output_resolve_dir.parts[-1]}.json",
            "w",
        ) as f:
            f.write(
                self.json(
                    exclude={"dir_str", "dir_structure"},
                    exclude_defaults=True,
                    exclude_none=True,
                    indent=1,
                )
            )

    @classmethod
    def from_csv(cls, filename: pathlib.Path, scenarios: list = [], data: dict = {}):
        input_df = pd.read_csv(filename).sort_index()

        scalar_attrs = cls._parse_scalar_attributes(filename=filename, input_df=input_df, scenarios=scenarios)
        ts_attrs = cls._parse_timeseries_attributes(filename=filename, input_df=input_df, scenarios=scenarios)
        nodate_ts_attrs = cls._parse_nodate_timeseries_attributes(
            filename=filename, input_df=input_df, scenarios=scenarios
        )
        attrs = {
            **{"name": filename.parent.stem, "scenarios": scenarios},
            **scalar_attrs,
            **ts_attrs,
            **nodate_ts_attrs,
            **data,
        }
        return attrs["name"], cls(**attrs)


if __name__ == "__main__":
    system = System(name="test", scenarios=["B"], dir_str=DirStructure(data_folder="data-test"))
    print(system)
