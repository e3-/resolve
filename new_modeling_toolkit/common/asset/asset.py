from typing import Optional

from loguru import logger
from pydantic import confloat
from pydantic import Field
from pydantic import PositiveInt
from pydantic import validator

from new_modeling_toolkit import get_units
from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.custom_model import convert_str_float_to_int
from new_modeling_toolkit.core.temporal import timeseries as ts


class Asset(component.Component):
    """
    Define an Asset component, defined as a component of the energy supply system that can be built by the model and
    has costs that must be accounted for.
    """

    class Config:
        validate_assignment = True

    ######################
    # Mapping Attributes #
    ######################
    asset_groups: dict[str, linkage.AssetToAssetGroup] = {}
    elcc_surfaces: dict[str, linkage.Linkage] = {}
    fuel_zones: dict[str, linkage.Linkage] = {}
    policies: dict[str, linkage.Linkage] = {}
    proformas: dict[str, linkage.Linkage] = {}
    tranches: dict[str, linkage.TrancheToAsset] = {}
    zones: dict[str, linkage.Linkage] = {}

    #################################
    # Build & Retirement Attributes #
    #################################

    can_build_new: bool = Field(
        False,
        description="Whether resource can be expanded (for now only linear capacity expansion).",
    )

    can_retire: bool = Field(
        False,
        description="Whether resource can be retired. By default, resources cannot be retired.",
    )

    physical_lifetime: Optional[PositiveInt] = Field(
        None,
        description="[Currently unused] Years after vintage is installed "
        "(or first year of modeling for planned capacity) after which vintage will be retired.",
        unit=get_units("physical_lifetime"),
    )

    planned_installed_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Nameplate MW capacity of the asset. Applies to both directions of power transfer.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
        units=get_units("planned_installed_capacity"),
    )
    min_cumulative_new_build: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Forced-in new build capacity.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )
    min_op_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Minimum operational capacity in a given modeled year.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )
    potential: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Maximum operational capacity in a given modeled year.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )

    ###################################
    # Operational Attributes #
    ###################################
    # TODO 2021-09-21: Something about ramp rate constraint as-implemented doesn't allow condecimal
    ramp_rate: Optional[confloat(gt=0)] = Field(
        None,
        description="Single-hour ramp rate (% of rating/hour). When used in conjunction with the other ramp rate limits (2-4 hour), a resource's dispatch will be constrained by all applicable ramp rate limits on a rolling basis.",
        units=get_units("ramp_rate"),
    )
    ramp_rate_2_hour: Optional[confloat(gt=0)] = Field(
        None, description="Two-hour ramp rate (% of rating/hour).", units=get_units("ramp_rate_2_hour")
    )
    ramp_rate_3_hour: Optional[confloat(gt=0)] = Field(
        None, description="Three-hour ramp rate (% of rating/hour).", units=get_units("ramp_rate_3_hour")
    )
    ramp_rate_4_hour: Optional[confloat(gt=0)] = Field(
        None, description="Four-hour ramp rate (% of rating/hour).", units=get_units("ramp_rate_4_hour")
    )

    td_losses_adjustment: Optional[confloat(ge=1)] = Field(
        None,
        description="T&D loss adjustment to gross up to system-level loads. For example, a DER may be able to serve "
        "8% more load (i.e., 1.08) than an equivalent bulk system resource due to T&D losses.",
        units=get_units("td_losses_adjustment"),
    )

    stochastic_outage_rate: Optional[confloat(ge=0)] = Field(
        None,
        description="Stochastic forced outage rate",
        units=get_units("stochastic_outage_rate"),
    )

    mean_time_to_repair: Optional[confloat(ge=0)] = Field(
        None, description="Mean time to repair", units=get_units("mean_time_to_repair")
    )

    random_seed: Optional[float] = Field(None, description="Random seed", units=get_units("random_seed"))

    ###################
    # Cost Attributes #
    ###################

    financial_lifetime: Optional[PositiveInt] = Field(
        None,
        description="Years after vintage is installed (or first year of modeling for planned capacity) "
        'after which fixed cost of resource will drop down to (as-yet-undefined) "recontracting" or "repowering" cost.',
        units=get_units("financial_lifetime"),
    )

    planned_fixed_om_by_model_year: Optional[ts.NumericTimeseries] = Field(
        None,
        description="For the planned portion of the resource's power output capacity, "
        "the ongoing fixed O&M cost ($/kW-year).",
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("planned_fixed_om_by_model_year"),
    )

    new_capacity_annualized_all_in_fixed_cost_by_vintage: Optional[ts.NumericTimeseries] = Field(
        None,
        description="For new power output capacity, the total annualized fixed cost of investment INCLUDING FOM. "
        "This is an annualized version of an overnight cost that could include financing costs ($/kW-year).",
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("new_capacity_annualized_all_in_fixed_cost_by_vintage"),
    )

    new_capacity_fixed_om_by_vintage: Optional[ts.NumericTimeseries] = Field(
        None,
        description="For new power output capacity, the ongoing fixed O&M of each vintage ($/kW-year). ",
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("new_capacity_fixed_om_by_vintage"),
    )

    # Convert strings that look like floats to integers for integer fields
    _convert_int = validator(
        "physical_lifetime",
        "financial_lifetime",
        allow_reuse=True,
        pre=True,
    )(convert_str_float_to_int)

    ########################
    # Optimization Results #
    ########################

    opt_operational_planned_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized operational capacity of planned resources by model year.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    opt_operational_new_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description=(
            "Optimized operational capacity of new build resources by model year. This is equivalent to "
            "`opt_operational_new_capacity_by_vintage_mw` summed across vintages for each model year."
        ),
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    opt_annual_fixed_om_cost_dollars: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized total annual fixed O&M of planned and new build resources, in dollars.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_installed_cost_dollars: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized total annual installed costs of new build resources, in dollars.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_retired_new_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized retired new capacity by model year.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    @property
    def opt_total_operational_capacity(self):
        total_operational_capacity = self.sum_timeseries_attributes(
            attributes=["opt_operational_planned_capacity", "opt_operational_new_capacity"],
            name="opt_total_operational_capacity",
            skip_none=True,
        )

        return total_operational_capacity

    @property
    def opt_retired_capacity(self):
        return ts.NumericTimeseries(
            name="opt_retired_capacity",
            data=(
                (
                    self.planned_installed_capacity.data - self.opt_operational_planned_capacity.data
                    if self.planned_installed_capacity is not None
                    else 0
                )
                + self.opt_retired_new_capacity.data
            ),
        )

    ########################################################################
    # PROPERTIES TO PULL PRO FORMA OR USER-DEFINED COST INPUTS DYNAMICALLY #
    ########################################################################

    def _map_proforma_data_to_property(
        self,
        resource_attr: str,
        proforma_attr: str,
        attr_descriptor: str,
        energy_component: bool = False,
    ) -> Optional[ts.Timeseries]:
        """Helper function to get cost data from either associated pro forma or from user input CSV.

        There are two ways to get cost data into a Resource instance:
            1. From a E3 proforma output CSV, which has a defined format that we parse in pro_forma.py
            2. As an attribute read in through resource_dynamic input.csv

        This method uses the following logic to return the cost values:
            - If users input cost data through resource_dynamic input.csv, return that data
            - If not, search the pro forma outputs for the corresponding costs:
                - When first read in, the proforma values are MultiIndexed pandas Series, where the indices are
                  ("Technology", "Year")
                - Some technologies (e.g., storage) have costs split between two entries in the CSV with
                  "[Energy]" or "[Capacity]"
                - This method will **modify** the pd.Series to turn it into a plain single-Indexed series the first time
                  this logic runs.

        TODO: If retrieving from the pro forma, we return **copy** of the attribute rather than the attribute directly,
        meaning if someone wants to modify it, they cannot through this property

        """

        if self.proformas is None or len(self.proformas) == 0 or getattr(self, resource_attr) is not None:
            return getattr(self, resource_attr)

        # If previous guard clause fails, set/get hidden attribute for pro forma value
        # TODO (2021-10-07): Doesn't deal with case where proforma linkage gets changed.
        if not hasattr(self, f"__{resource_attr}"):
            # Else, pull values from linked pro forma
            # Get first (only) pro forma
            proforma_name = list(self.proformas.keys())[0]
            # Get corresponding cost attribute from pro forma
            val = getattr(self.proformas[proforma_name].proforma_slice, proforma_attr)
            # Not all techs in proforma have all cost attributes
            if val is None:
                return None
            else:
                val = val.copy()
            val.data = val.data.reset_index()
            if "Technology" in val.data.columns:
                # Clean up MultiIndex Series if needed
                techs = val.data["Technology"].unique()
                if energy_component:
                    if any("[Energy]" in t for t in techs):
                        val.data = val.data.loc[val.data["Technology"].str.contains("\[Energy\]"), :]
                    else:
                        return None
                elif any("[Capacity]" in t for t in techs):
                    val.data = val.data.loc[val.data["Technology"].str.contains("\[Capacity\]"), :]
                # Drop Technology index
                val.data = val.data.drop("Technology", axis=1)
            # Set index back to just the Year
            val.data = val.data.set_index("Year").squeeze()
            logger.debug(f"Retrieving {attr_descriptor} for resource '{self.name}' from pro forma '{proforma_name}'")
            setattr(self, f"__{resource_attr}", val)
        return getattr(self, f"__{resource_attr}")

    @property
    def _new_capacity_annualized_all_in_fixed_cost_by_vintage(self):
        return self._map_proforma_data_to_property(
            resource_attr="new_capacity_annualized_all_in_fixed_cost_by_vintage",
            proforma_attr="lfc_total",
            attr_descriptor="total annualized fixed cost including FOM ($/kW-year)",
        )

    # TODO (2021-10-06): Planned vs. new costs may not be pulled from proforma correctly
    @property
    def _new_capacity_fixed_om_by_vintage(self):
        return self._map_proforma_data_to_property(
            resource_attr="new_capacity_fixed_om_by_vintage",
            proforma_attr="lfc_fixed_om",
            attr_descriptor="annual FOM ($/kW-year)",
        )

    @property
    def _planned_fixed_om_by_model_year(self):
        return self._map_proforma_data_to_property(
            resource_attr="planned_fixed_om_by_model_year",
            proforma_attr="lfc_fixed_om",
            attr_descriptor="fixed O&M cost ($/kW-year)",
        )


class AssetGroup(Asset):
    """A group of Assets."""

    assets: dict[str, linkage.AssetToAssetGroup] = {}


class Tranche(Asset):
    """An asset used to represent a tranche of another Asset."""

    assets: dict[str, linkage.TrancheToAsset] = {}
