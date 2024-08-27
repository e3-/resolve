import enum
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger
from pydantic import confloat
from pydantic import conint
from pydantic import Field
from pydantic import PositiveFloat
from pydantic import root_validator
from pydantic import validator

from .plant import Plant
from new_modeling_toolkit import get_units
from new_modeling_toolkit.core import dir_str
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.custom_model import convert_str_float_to_int
from new_modeling_toolkit.core.temporal import timeseries as ts


@enum.unique
class ResourceCategory(enum.Enum):
    THERMAL = "thermal"
    FIRM = "firm"
    VARIABLE = "variable"
    HYDRO = "hydro"
    STORAGE = "storage"
    DEMAND_RESPONSE = "dr"
    HYBRID_STORAGE = "hybrid_storage"
    FLEXIBLE_LOAD = "flexible_load"


class Resource(Plant):
    """A component in the electric system that generates power or increases load subject to operational constraints.

    A ``Resource`` is intended to represent any of the following:
        - Fuel-burning generator (CT, CCGT, coal, biomass, etc.), with or without unit commitment constraints
        - Nuclear
        - Geothermal
        - Solar
        - Wind
        - Storage (both short- and long-duration)

    Resources have up to two components that can be sized (e.g., for capacity expansion):
        - Provide power rating (MW)
        - Storage capacity (MWh)

    For both components, there are multiple types of costs to be defined:
        - Planned capacity fixed O&M cost (by year)
        - New build annualized fixed cost (by vintage)
        - New build annual fixed O&M cost (by vintage)

    TODO: In a future update, we will consider how to model hybrid resources as a single Resource.
    At this time, hybrid resources would be modeled as multiple separate resources tied together with custom constraints.

    Attributes removed relative to ``RESOLVE`` resources:
        - Move to custom constraints:
            - ``generate_at_max``
            - ``paired_supply_resource``
            - ``min_operational_planned_capacity_mw``
            - ``min_cumulative_new_build_mw``
            - ``min_duration_h``
            - ``energy_budget_cap_factor``
            - ``max_daily_capacity_factor``
            - ``min_daily_increase_load_cap_factor``
            - ``max_increase_load_fraction``
            - ``min_increase_load_fraction``
            - ``can_produce_less_than_energy_budget``
            - ``max_ramp_duration_to_constrain``
            - ``ramp_up_intertimepoint_limit_fraction``
            - ``ramp_down_intertimepoint_limit_fraction``
            - ``adjacency_h``
            - ``conventional_dr_availability_hours_per_year``
            - ``conventional_dr_reliability_hours_per_day``

        - Removed as unuseful:
            - ``thermal``
            - ``variable``
            - ``conventional_dr``
            - ``energy_efficiency``
            - ``storage``
            - ``load_only``
            - ``enable_hourly_energy_tracking``
            - ``energy_taken_offline_mwh`` (bring this back when we get to load resources)
            - ``energy_borught_online_mwh`` (merged with :py:attr:`new_modeling_toolkit.common.resource.Resource.provide_power_potential_profile`)
            - ``shape`` (renamed :py:attr:`new_modeling_toolkit.common.resource.Resource.provide_power_potential_profile`)
    """

    category: Optional[ResourceCategory] = Field(
        None,
        description='Resource type name. Currently, most functionality (e.g., storage SoC tracking) is enabled via other attributes or implicitly via model logic. Over time, we may choose to use the ``type`` attribute to provide a more explicit toggle for certain "out-of-the-box" behavior for certain standard resource types.',
    )

    ######################
    # Mapping Attributes #
    ######################
    # TODO: Think about how to validate or constrain linkages that should only be one,
    #  instead of allowing any number of items in a dict (i.e., only 1 pro forma per resource)
    policies: dict[str, linkage.Linkage] = {}
    elcc_surfaces: dict[str, linkage.Linkage] = {}
    resource_groups: Optional[dict[str, linkage.Linkage]] = {}
    outage_distributions: Optional[dict[str, linkage.Linkage]] = {}

    ######################
    # Boolean Attributes #
    ######################

    integer_build: bool = Field(
        False,
        description="Consider integer (rather than linear) build decisions.",
    )
    build_year: Optional[int] = Field(None, description="For resources using `integer_build`, the build year decision")

    curtailable: bool = Field(
        True,
        description="Whether resource's power output can be curtailed relative to "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.potential_provide_power_profile`.",
    )

    # TODO (5/12): Add validations to make sure unit commitment fields are defined if these are True
    unit_commitment_linear: bool = Field(
        False,
        description="[UC] Whether resource should be subject to linearized unit commitment constraints. "
        "Exclusive of :py:attr:`new_modeling_toolkit.common.resource.Resource.unit_commitment_integer`.",
    )
    unit_commitment_integer: bool = Field(
        False,
        description="[UC] Whether resource should be subject to integer unit commitmennt constraints. "
        "Exclusive of :py:attr:`new_modeling_toolkit.common.resource.Resource.unit_commitment_linear`.",
    )
    provide_power_potential_profile: ts.FractionalTimeseries = Field(
        default_factory=ts.Timeseries.one,
        description="Fixed shape of resource's potential power output (e.g., solar or wind shape or flat shape"
        "for firm resources or storage resources). Used in conjunction with "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.curtailable`.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        units=get_units("provide_power_potential_profile"),
    )
    provide_power_min_profile: ts.FractionalTimeseries = Field(
        default_factory=ts.Timeseries.zero,
        description="Fixed shape of resource's minimum power output (e.g., hydro minimum generation)",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        units=get_units("provide_power_min_profile"),
    )
    # Convert strings that look like floats to integers for integer fields
    _convert_int = validator(
        "build_year",
        "min_up_time",
        "min_down_time",
        "adjacency",
        "max_annual_calls",
        "max_call_duration",
        "max_shift_hr",
        "grid_charging_allowed",
        allow_reuse=True,
        pre=True,
    )(convert_str_float_to_int)

    @root_validator
    def check_unit_commitment(cls, values):
        """Check that resources are either linear or integer unit commitment, or not at all (economic dispatch)."""
        # Temporarily include this error until integer UC is complete.
        if values["unit_commitment_integer"]:
            raise ValueError(
                f"For resource {values['name']}, `unit_commitment_integer` cannot be True. Feature not implemented yet."
            )

        if all([values["unit_commitment_linear"], values["unit_commitment_integer"]]):
            raise ValueError(
                f"Check resource {values['name']}. At most one of `unit_commitment_linear` and `unit_commitment_integer` can be True for a single resource."
            )
        else:
            return values

    @property
    def outage_distribution_obj(self):
        outage_dist_name = list(self.outage_distributions.keys())[0]
        return self.outage_distributions[outage_dist_name]._instance_to

    #################################
    # Build & Retirement Attributes #
    #################################

    # Increase load & energy storage attributes
    duration: Optional[PositiveFloat] = Field(
        None,
        description="For resource with storage capacity, the rated duration relative to the nameplate capacity. "
        "Exclusive of :py:attr:`new_modeling_toolkit.common.resource.Resource.planned_storage_capacity`.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
        units=get_units("duration"),
    )
    planned_storage_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Nameplate MWh capacity of the resource."
        "Exclusive of :py:attr:`new_modeling_toolkit.common.resource.Resource.duration`.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
        units=get_units("planned_storage_capacity"),
    )

    # Hybrid storage attributes
    paired_resource: Optional[str] = Field(
        None, description="Name of paired variable resource for hybrid storage resource."
    )

    hybrid_resource_interconnection_limit: Optional[PositiveFloat] = Field(
        None, description="Combined interconnection limit for hybrid variable + storage resource."
    )

    grid_charging_allowed: Optional[conint(ge=0, le=1)] = Field(
        None, description="Whether to allow hybrid storage resource to charge from grid as well as paired resource?"
    )

    # Hydro attributes
    energy_budget_daily: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Weekly MWh energy budget of the resource.",
        default_freq="D",  # double-check
        up_method="ffill",
        down_method="weekly",  # check this w rogo
        # todo kw: fix this (add to units file and pull in)
        units=get_units("planned_storage_capacity"),
    )

    energy_budget_monthly: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Monthly MWh energy budget of the resource.",
        default_freq="MS",
        up_method="ffill",
        down_method="monthly",  # check this w rogo
        # todo kw: fix this (add to units file and pull in)
        units=get_units("planned_storage_capacity"),
    )

    energy_budget_annual: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Annual MWh energy budget of the resource.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",  # check this w rogo
        # todo kw: fix this (add to units file and pull in)
        units=get_units("planned_storage_capacity"),
    )

    # Demand Response attribute
    ## Currently used only by RECAP 2.0
    max_annual_calls: Optional[conint(ge=0)] = Field(
        None, description="Annual number of allowable calls for a shed DR resource."
    )

    # Shift DR / Flex Load attribute
    ## Currently used only by RECAP 2.0
    max_shift_hr: Optional[conint(ge=0)] = Field(
        None,
        description="Demand can be shifted to an hour within +/- max_shift_hours (total window  = 2*max_shift_hours)",
    )

    scaling_factor: Optional[PositiveFloat] = Field(
        None,
        description="unserved energy * scaling factor to be shifted ; "
        "ex: if 3MW UE w 1.5 scaling_factor, 4.5MW must be shifted to avoid event "
        "(1.5 is typical scaling_factor)",
    )

    @root_validator()
    def validate_storage_duration(cls, values):
        if values["duration"] is not None and values["planned_storage_capacity"] is not None:
            if not np.isclose(
                values["planned_installed_capacity"].data * values["duration"],
                values["planned_storage_capacity"].data,
                rtol=0.001,
            ).all():
                raise ValueError(
                    f"For Resource `{values['name']}`, the specified `planned_storage_capacity` does not "
                    f"equal the specified `planned_installed_capacity` * `duration`."
                )
        return values

    ###################################
    # Operational Dispatch Attributes #
    ###################################

    # Unit commitment attributes (all on a per-unit scale, rather than per-MW)
    unit_size_mw: Optional[float] = Field(
        None,
        description="[UC] Optional unit size (a resource may be made up of multiple units) "
        "used in reference to other unit commitment parameters (labeled [UC])",
        units=get_units("unit_size_mw"),
    )
    min_down_time: Optional[conint(ge=0)] = Field(
        None, description="[UC] Minimum downtime between commitments (hours).", units=get_units("min_down_time")
    )
    min_up_time: Optional[conint(ge=0)] = Field(
        None, description="[UC] Minimum uptime during a commitment (hours).", units=get_units("min_up_time")
    )
    min_stable_level: Optional[ts.NumericTimeseries] = Field(
        None,
        description="[UC] Minimum stable level when committed",
        units=get_units("min_stable_level"),
        default_freq="YS",
        up_method="ffill",
        down_method=None,
        weather_year=False,
    )
    start_cost: Optional[confloat(ge=0)] = Field(
        None,
        description="[UC] Cost for each unit startup ($/unit start). "
        "If using linearized UC, this cost will be linearized as well.",
        units=get_units("start_cost"),
    )
    shutdown_cost: Optional[confloat(ge=0)] = Field(
        None,
        description="[UC] Cost for each unit shutdown ($/unit shutdown). "
        "If using linearized UC, this cost will be linearized as well.",
        units=get_units("shutdown_cost"),
    )
    # Increase load & energy storage attributes
    # TODO (RG): If resource is a storage resource, validate that charging efficiency, discharging efficiency, and parasitic loss are initialized to some value
    charging_efficiency: Optional[confloat(ge=0, le=1)] = Field(
        None,
        description="[Storage] Efficiency losses associated with charging (increasing load) "
        'to increase storage "state of charge".',
        units=get_units("charging_efficiency"),
    )
    discharging_efficiency: Optional[confloat(ge=0, le=1)] = Field(
        None,
        description="[Storage] Efficiency losses associated with discharging (providing power), "
        'taking energy out of storage "state of charge".',
        units=get_units("discharging_efficiency"),
    )
    state_of_charge_min: Optional[confloat(ge=0, le=1)] = Field(
        None,
        description="[Storage] Minimum state-of-charge at any given time.",
        units=get_units("discharging_efficiency"),
    )
    parasitic_loss: Optional[confloat(ge=0, le=1)] = Field(
        None, description="[Storage] Hourly state of charge losses.", units=get_units("parasitic_loss")
    )
    start_fuel_use: Optional[confloat(ge=0)] = Field(
        None, description="[UC] Amount of fuel used per unit start", units=get_units("start_fuel_use")
    )
    fuel_burn_slope: Optional[confloat(ge=0)] = Field(
        None, description="Fuel burn slope (MMBTU/MWh)", units=get_units("fuel_burn_slope")
    )
    fuel_burn_intercept: Optional[confloat(ge=0)] = Field(
        None, description="Fuel burn intercept (MMBTU/hour)", units=get_units("fuel_burn_intercept")
    )

    daily_budget: ts.FractionalTimeseries = Field(
        None,
        description="Daily energy generation budget as a fraction of operational capacity (effectively a daily "
        "capacity factor).",
        default_freq="H",
        up_method="ffill",
        down_method=None,
        weather_year=True,
    )
    monthly_budget: ts.FractionalTimeseries = Field(
        None,
        description="Monthly energy generation budget as a fraction of operational capacity (effectively a monthly "
        "capacity factor).",
        default_freq="H",
        up_method="ffill",
        down_method=None,
        weather_year=True,
    )
    annual_budget: ts.FractionalTimeseries = Field(
        None,
        description="Annual energy generation budget as a fraction of operational capacity (effectively an annual "
        "capacity factor).",
        default_freq="YS",
        up_method="ffill",
        down_method=None,
        weather_year=False,
    )

    # TODO 2023-07-23: Temporarily add these attributes
    max_call_duration: Optional[int] = None
    max_annual_calls: Optional[int] = None

    ###########################
    # Flexible Load Attribute #
    ###########################

    adjacency: Optional[conint(gt=0)] = Field(
        None,
        description="For flexible load resource, # of adjacent hours to constrain energy shifting.",
        units=get_units("adjacency"),
    )

    ###################
    # Cost Attributes #
    ###################
    planned_storage_capacity_fixed_om_by_model_year: Optional[ts.NumericTimeseries] = Field(
        None,
        description="For the planned portion of the resource's storage capacity, "
        "the ongoing fixed O&M cost ($/kWh-year).",
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("planned_storage_capacity_fixed_om_by_model_year"),
    )
    new_storage_annual_fixed_cost_dollars_per_kwh_yr_by_vintage: Optional[ts.NumericTimeseries] = Field(
        None,
        description="For new storage capacity, the annualized fixed cost of investment. "
        "This is an annualized version of an overnight cost that could include financing costs ($/kWh-year).",
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("new_storage_annual_fixed_cost_dollars_per_kwh_yr_by_vintage"),
    )
    new_storage_capacity_fixed_om_by_vintage: Optional[ts.NumericTimeseries] = Field(
        None,
        description=(
            "For new storage capacity, the ongoing fixed O&M of each vintage ($/kWh-year). "
            'Depending on how fixed costs are calculated, user may choose to use an "all-in" cost via '
            ":py:attr:`new_modeling_toolkit.common.resource.Resource.new_provide_power_capacity_annualized_fixed_cost` "
            "instead of breaking out fixed O&M."
        ),
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("new_storage_capacity_fixed_om_by_vintage"),
    )

    curtailment_cost: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Cost of curtailment - the exogeneously assumed cost"
        "at which different contract zones would be willing to curtail their"
        "variable renewable generation",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        units=get_units("curtailment_cost"),
    )

    ########################
    # Optimization Results #
    ########################
    opt_annual_curtailment_mwh: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual curtailment, in MWh.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_fuel_consumption_by_fuel_mmbtu: Optional[pd.Series] = Field(
        None,
        description="Optimized annual fuel consumption, in MMBTU.",
    )
    opt_annual_fuel_cost_dollars: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual fuel cost, in dollars.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_curtailment_cost_dollars: Optional[ts.NumericTimeseries] = Field(
        None,
        desciption="Optimized total annual curtailment costs, in dollars.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_operational_planned_storage_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized operational energy capacity of planned storage resources by model year.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_retired_new_storage_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized retired energy capacity of new storage resources by model year.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_operational_new_storage_capacity: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized operational energy capacity of new build storage resources by model year.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    # TODO (myuan + skramer): revisit and decide what to do with the SOCs
    opt_soc_intra_period: Optional[pd.Series] = Field(None, description="Optimized intra-period SOC by timepoint.")
    opt_soc_inter_period: Optional[pd.Series] = Field(
        None, description="Optimized inter-period SOC by model year and chrono period."
    )
    opt_soc_inter_intra_joint: Optional[pd.Series] = Field(
        None, description="Joint inter-intra-period SOC by model year, chrono period, and hour."
    )

    opt_annual_start_units: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized number of starts of unit commitment resources by model year.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_shutdown_units: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized number of shutdowns of unit commitment resources by model year.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    opt_annual_start_cost_dollars: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized start costs of unit commitment resources by model year, in dollars.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_shutdown_cost_dollars: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized shutdown costs of unit commitment resources by model year, in dollars.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    @property
    def _new_storage_annual_fixed_cost_dollars_per_kwh_yr_by_vintage(self):
        return self._map_proforma_data_to_property(
            resource_attr="new_storage_annual_fixed_cost_dollars_per_kwh_yr_by_vintage",
            proforma_attr="lfc_total",
            attr_descriptor="total annualized storage fixed cost ($/kWh-year)",
            energy_component=True,
        )

    @property
    def _planned_storage_capacity_fixed_om_by_model_year(self):
        return self._map_proforma_data_to_property(
            resource_attr="planned_storage_capacity_fixed_om_by_model_year",
            proforma_attr="lfc_fixed_om",
            attr_descriptor="storage fixed O&M cost ($/kWh-year)",
            energy_component=True,
        )

    @property
    def _new_storage_capacity_fixed_om_by_vintage(self):
        return self._map_proforma_data_to_property(
            resource_attr="new_storage_capacity_fixed_om_by_vintage",
            proforma_attr="lfc_fixed_om",
            attr_descriptor="storage fixed O&M cost ($/kWh-year)",
            energy_component=True,
        )

    @property
    def opt_total_operational_storage_capacity(self):
        total_operational_capacity = self.sum_timeseries_attributes(
            attributes=["opt_operational_planned_storage_capacity", "opt_operational_new_storage_capacity"],
            name="opt_total_operational_storage_capacity",
            skip_none=True,
        )

        return total_operational_capacity

    @property
    def opt_retired_storage_capacity(self):
        if self.charging_efficiency is None:
            return None
        else:
            return ts.NumericTimeseries(
                name="opt_retired_storage_capacity",
                data=(
                    (self.planned_storage_capacity.data if self.planned_storage_capacity is not None else 0)
                    - self.opt_operational_planned_storage_capacity.data
                    + self.opt_retired_new_storage_capacity.data
                ),
            )

    def revalidate(self):
        super().revalidate()
        self.revalidate_has_policies()

    def revalidate_has_policies(self):
        """Log warning message if resource has an ELCC surface but no reliability policy."""
        not_linked_to_prm_policies = (
            not self.policies or len([p for p in self.policies.values() if p._instance_to.type == "prm"]) == 0
        )
        if self.elcc_surfaces and not_linked_to_prm_policies:
            logger.warning(
                f"Resource {self.name} has an ELCC surface but is not linked to any reliability policies. "
                f"Check linkages.csv in system inputs."
            )

    def get_generation_profile(self, model_year):
        """
        Returns capacity-scaled generation profile of resource in given model year
        """
        # Up-sample provide_power_potential_profile with interpolation
        field_settings = self.__fields__["provide_power_potential_profile"].field_info.extra
        up_method, freq = field_settings["up_method"], field_settings["default_freq"]
        interpolated_profile = self.provide_power_potential_profile.resample_up(
            self.provide_power_potential_profile.data,
            freq,
            up_method,
        )
        return self.planned_installed_capacity.slice_by_year(model_year) * interpolated_profile

    def rescale_resource_capacity(self, model_year, capacity, incremental=False):
        # Scale resource by incremental/absolute capacity

        # Define scaling factor; scale by 1 + capacity ratio if incremental; else scale by capacity ratio
        scaling_factor = int(incremental) + capacity / self.planned_installed_capacity.slice_by_year(model_year)

        # Re-scale planned installed capacity
        self.planned_installed_capacity.data.loc[pd.Timestamp(year=model_year, month=1, day=1)] *= scaling_factor

        # Re-scale planned storage capacity if charging efficiency and duration defined
        resource_to_resource_group_inst = list(self.resource_groups.keys())[0]  # Get resource group of resource
        resource_group = self.resource_groups[resource_to_resource_group_inst]._instance_to
        if resource_group.category in [ResourceCategory.STORAGE, ResourceCategory.HYBRID_STORAGE]:
            if self.duration:
                if self.planned_storage_capacity is None or self.charging_efficiency is None:
                    self.planned_storage_capacity = ts.NumericTimeseries(
                        name="planned_storage_capacity", data=self.planned_installed_capacity.data * self.duration
                    )
                else:
                    self.planned_storage_capacity.data.loc[pd.Timestamp(year=model_year, month=1, day=1)] = (
                        self.planned_installed_capacity.data.loc[pd.Timestamp(year=model_year, month=1, day=1)]
                        * self.duration
                    )
            else:
                raise ValueError(f"Need to specify duration to rescale storage resource {self.name}")


if __name__ == "__main__":
    data_path = dir_str.data_dir / "interim" / "resources"
    # instantiate proforma
    # proforma = ProForma.from_csv(data_path)
    # instantiate resources
    resources = Resource.from_csv(data_path / "Gas_CCGT")
    print(resources)
