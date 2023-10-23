"""HECO-specific functionality.
 - Energy Reserve Margin planning criteria
 - Fast frequency response reserve requirement calculations
"""
import pandas as pd
import pyomo.environ as pyo
from loguru import logger


def main(resolve_model):
    """Main function, which will be called by `run_opt.py`.

    Args:
        resolve_model:

    Returns:
        resolve_model: Updated resolve_model instance (e.g., with additional/modified constraints).
    """
    logger.info("Adding HECO-specific model functionality")

    ##################################################
    #  Fast frequency response (FFR)                 #
    ##################################################

    # FFR - single largest contingency
    resolve_model.model.SINGLE_LARGEST_CONTINGENCY_RESOURCES = pyo.Set(
        initialize=pd.read_csv(
            resolve_model.dir_structure.resolve_settings_dir / "extras" / "freq_resp_contingency_resources.csv"
        )["freq_resp_contingency_resources"]
        .dropna()
        .values
    )

    resolve_model.model.Single_Largest_Contingency_MW = pyo.Var(
        resolve_model.model.TIMEPOINTS,
        units=pyo.units.MW,
        within=pyo.NonNegativeReals,
    )

    @resolve_model.model.Constraint(resolve_model.model.PLANTS, resolve_model.model.TIMEPOINTS)
    def Single_Largest_Contingency_Constraint(model, plant, model_year, rep_period, hour):
        if plant in resolve_model.model.SINGLE_LARGEST_CONTINGENCY_RESOURCES:
            return (
                model.Single_Largest_Contingency_MW[model_year, rep_period, hour]
                >= model.Plant_Provide_Power_Capacity_In_Timepoint_MW[plant, model_year, rep_period, hour]
            )
        else:
            return pyo.Constraint.Skip

    # FFR - net load shedding adjustment to the requirement
    flexible_params = pd.read_csv(resolve_model.dir_structure.resolve_settings_dir / "extras" / "flexible_params.csv")
    under_freq_load_shedding_fraction = (
        flexible_params.loc[flexible_params["param"] == "under_freq_load_shedding_fraction", "value"]
        .astype(float)
        .iloc[0]
    )

    resolve_model.model.PLANTS_THAT_ADJUST_FFR = pyo.Set(
        initialize=pd.read_csv(
            resolve_model.dir_structure.resolve_settings_dir / "extras" / "freq_resp_adjust_resources.csv"
        )["freq_resp_adjust_resources"]
        .dropna()
        .values
    )

    resolve_model.model.Net_Load_FFR_Adjustment_MW = pyo.Var(
        resolve_model.model.TIMEPOINTS, units=pyo.units.MW, within=pyo.NonNegativeReals
    )

    @resolve_model.model.Constraint(resolve_model.model.TIMEPOINTS)
    def Net_Load_FFR_Adjustment_Constraint(model, model_year, rep_period, hour):
        return model.Net_Load_FFR_Adjustment_MW[
            model_year, rep_period, hour
        ] >= under_freq_load_shedding_fraction * sum(
            model.Provide_Power_MW[plant, model_year, rep_period, hour] for plant in model.PLANTS_THAT_ADJUST_FFR
        )

    ###########################################
    # Adjust FFR operating reserve            #
    ###########################################
    # TODO: Put this in a function (and generally wrap heco.py in a main function with clear function calls)
    for idx in resolve_model.model.Operating_Reserve_Balance_Constraint:
        # Unpack the idx tuple
        reserve, model_year, rep_period, hour = idx

        if resolve_model.system.reserves[reserve].category == "ffr":
            # Example of adding a variable and a number to the body (LHS) of the constraint
            resolve_model.model.Operating_Reserve_Balance_Constraint[idx]._body = (
                resolve_model.model.Operating_Reserve_Balance_Constraint[idx]._body
                - resolve_model.model.Single_Largest_Contingency_MW[model_year, rep_period, hour]
                - resolve_model.model.Net_Load_FFR_Adjustment_MW[model_year, rep_period, hour]
            )

    ##################################################
    #  Energy Reserve Margin (ERM)                   #
    ##################################################

    resolve_model.model.energy_reserve_margin = flexible_params.loc[
        flexible_params["param"] == "energy_reserve_margin", "value"
    ].iloc[0] in ["TRUE", "True", True]

    resolve_model.model.itc_paired_storage = flexible_params.loc[
        flexible_params["param"] == "itc_paired_storage", "value"
    ].iloc[0] in ["TRUE", "True", True]

    resolve_model.model.paired_charging_constraint_active_in_year = pyo.Param(
        resolve_model.model.MODEL_YEARS,
        within=pyo.Boolean,
        initialize=lambda model, model_year: flexible_params.loc[
            (flexible_params["param"] == "paired_charging_constraint_active_in_year")
            & (pd.to_numeric(flexible_params["period"], errors="coerce") == model_year),
            "value",
        ].iloc[0]
        in ["TRUE", "True", True],
    )

    if resolve_model.model.energy_reserve_margin:
        # read in data
        resolve_model.model.erm_shifting_window = (
            pd.to_numeric(flexible_params.loc[flexible_params["param"] == "erm_shifting_window", "value"])
            .astype(int)
            .iloc[0]
        )

        erm_groups_data = pd.read_csv(resolve_model.dir_structure.resolve_settings_dir / "extras" / "erm_group.csv")
        resolve_model.model.ERM_GROUPS = pyo.Set(initialize=erm_groups_data["erm_group"].tolist())

        resolve_model.model.ERM_RESOURCE_GROUP_MAP = pd.read_csv(
            resolve_model.dir_structure.resolve_settings_dir / "extras" / "erm_resource_group_map.csv"
        )
        erm_percentage = pd.read_csv(resolve_model.dir_structure.resolve_settings_dir / "extras" / "erm_params.csv")
        erm_hdc_fraction = pd.read_csv(resolve_model.dir_structure.resolve_settings_dir / "extras" / "erm_shapes.csv")

        # Read in ERM hourly requirement
        erm_requirement = pd.read_csv(
            resolve_model.dir_structure.resolve_settings_dir / "extras" / "erm_timepoint_params.csv",
            index_col=0,
            parse_dates=True,
        )

        # Unpivot requirement
        erm_requirement = erm_requirement.reset_index()
        erm_requirement = erm_requirement.melt(id_vars=erm_requirement.columns[0])

        # Convert hour to numeric
        erm_requirement["variable"] = (
            erm_requirement["variable"].str.lower().str.replace("hour|hr| ", "", regex=True).astype(int)
        )

        # Remove leap days
        erm_requirement = erm_requirement[
            ~((erm_requirement.iloc[:, 0].dt.month == 2) & (erm_requirement.iloc[:, 0].dt.day == 29))
        ]

        # Slice out relevant years
        erm_requirement = erm_requirement[
            erm_requirement.iloc[:, 0].dt.year.isin(set(int(p) for p in sorted(resolve_model.model.MODEL_YEARS)))
        ]

        # Sort values by date & hour of day
        erm_requirement = erm_requirement.sort_values(erm_requirement.columns[:2].tolist()).reset_index(drop=True)

        # Convert date & hour of day to year (period) and hour of year (out of 8760)
        erm_requirement.iloc[:, 0] = erm_requirement.iloc[:, 0].dt.year
        erm_requirement["variable"] = erm_requirement.index % 8760 + 1

        # Add to the DataPortal instance
        erm_requirement = erm_requirement.set_index(erm_requirement.columns[:2].tolist()).to_dict()["value"]
        resolve_model.model.erm_input_load_mw = erm_requirement

        # the following params should be initialized even if ERM toggle is off to prevent breaking the code

        resolve_model.model.ERM_HOURS = pyo.RangeSet(1, 8760)

        # e.g. ERM_RESOURCE_GROUPS['solar'] = ('solar_1', 'solar_2')
        resolve_model.model.ERM_RESOURCE_GROUPS = pyo.Set(
            resolve_model.model.ERM_GROUPS,
            within=resolve_model.model.RESOURCES,
            initialize=lambda model, erm_group: (
                resolve_model.model.ERM_RESOURCE_GROUP_MAP.loc[
                    resolve_model.model.ERM_RESOURCE_GROUP_MAP["erm_group"] == erm_group, "resource"
                ].unique()
            ),
            doc="2-d set conditional on ERM_GROUPS",
        )

        # param initialization
        resolve_model.model.erm_percentage = pyo.Param(
            resolve_model.model.MODEL_YEARS,
            within=pyo.PercentFraction,
            initialize=lambda model, model_year: erm_percentage.loc[
                erm_percentage["period"] == model_year, "erm_percentage"
            ].iloc[0],
        )

        resolve_model.model.erm_hdc_fraction = pyo.Param(
            resolve_model.model.ERM_HOURS,
            resolve_model.model.ERM_GROUPS,
            within=pyo.PercentFraction,
            initialize=lambda model, erm_hour, erm_group: erm_hdc_fraction.loc[
                erm_hdc_fraction["erm_hour"] == erm_hour, erm_group
            ].iloc[0],
        )

        # resolve_model.model.paired_charging_constraint_active_in_year = pyo.Param(
        #     resolve_model.model.MODEL_YEARS,
        #     within=pyo.Boolean,
        #     initialize=lambda model, model_year:
        #         flexible_params.loc[
        #             (flexible_params['param'] == 'paired_charging_constraint_active_in_year') &
        #             (pd.to_numeric(flexible_params['period'], errors="coerce") == model_year),
        #             'value'
        #         ].iloc[0] in ["TRUE", "True", True],
        # )

        resolve_model.model.erm_storage_dispatch_cost_per_MWh = pyo.Param(within=pyo.Reals, initialize=10.0**-2)
        resolve_model.model.next_erm_opt_hour = pyo.Param(
            resolve_model.model.ERM_HOURS, initialize=_next_erm_opt_hour_init
        )

        resolve_model.model.ERM_FIRM_GROUPS = pyo.Set(
            within=resolve_model.model.ERM_GROUPS,
            initialize=erm_groups_data.loc[erm_groups_data["firm"] == 1, "erm_group"].tolist(),
        )

        resolve_model.model.ERM_SOLAR_GROUPS = pyo.Set(
            within=resolve_model.model.ERM_GROUPS,
            initialize=erm_groups_data.loc[erm_groups_data["solar"] == 1, "erm_group"].tolist(),
        )

        resolve_model.model.ERM_WIND_GROUPS = pyo.Set(
            within=resolve_model.model.ERM_GROUPS,
            initialize=erm_groups_data.loc[erm_groups_data["wind"] == 1, "erm_group"].tolist(),
        )

        resolve_model.model.ERM_STORAGE_GROUPS = pyo.Set(
            within=resolve_model.model.ERM_GROUPS,
            initialize=erm_groups_data.loc[erm_groups_data["storage"] == 1, "erm_group"].tolist(),
        )

        resolve_model.model.ERM_LSDR_GROUPS = pyo.Set(
            within=resolve_model.model.ERM_GROUPS,
            initialize=erm_groups_data.loc[erm_groups_data["lsdr"] == 1, "erm_group"].tolist(),
        )

        resolve_model.model.ERM_PAIRED_SOLAR_GROUPS = pyo.Set(
            within=resolve_model.model.ERM_GROUPS,
            initialize=erm_groups_data.loc[erm_groups_data["paired_solar"] == 1, "erm_group"].tolist(),
        )

        resolve_model.model.ERM_PAIRED_WIND_GROUPS = pyo.Set(
            within=resolve_model.model.ERM_GROUPS,
            initialize=erm_groups_data.loc[erm_groups_data["paired_wind"] == 1, "erm_group"].tolist(),
        )

        resolve_model.model.ERM_PAIRED_STORAGE_GROUPS = pyo.Set(
            within=resolve_model.model.ERM_GROUPS,
            initialize=erm_groups_data.loc[erm_groups_data["paired_storage"] == 1, "erm_group"].tolist(),
        )

        ##################################################
        # Energy Reserve Margin (ERM) VARIABLES          #
        ##################################################

        resolve_model.model.ERM_Charge_Storage_MW = pyo.Var(
            resolve_model.model.ERM_STORAGE_GROUPS,
            resolve_model.model.MODEL_YEARS,
            resolve_model.model.ERM_HOURS,
            within=pyo.NonNegativeReals,
        )
        resolve_model.model.ERM_Discharge_Storage_MW = pyo.Var(
            resolve_model.model.ERM_STORAGE_GROUPS,
            resolve_model.model.MODEL_YEARS,
            resolve_model.model.ERM_HOURS,
            within=pyo.NonNegativeReals,
        )
        resolve_model.model.ERM_Energy_in_Storage_MWh = pyo.Var(
            resolve_model.model.ERM_STORAGE_GROUPS,
            resolve_model.model.MODEL_YEARS,
            resolve_model.model.ERM_HOURS,
            within=pyo.NonNegativeReals,
        )

        ##################################################
        # Energy Reserve Margin (ERM) EXPRESSIONS        #
        ##################################################

        # TODO: the prior formulation distinguished fully deliverable resources vs others, check that we don't need to do that here
        @resolve_model.model.Expression(resolve_model.model.ERM_GROUPS, resolve_model.model.MODEL_YEARS)
        def ERM_Aggregated_Operational_Capacity_MW(model, erm_group, model_year):
            return sum(
                model.Operational_Capacity_In_Model_Year[plant, model_year]
                for plant in model.ERM_RESOURCE_GROUPS[erm_group]
            )

        @resolve_model.model.Expression(resolve_model.model.MODEL_YEARS, resolve_model.model.ERM_HOURS)
        def Hourly_Available_Capacity(model, model_year, erm_hour):
            return sum(
                model.erm_hdc_fraction[erm_hour, erm_group]
                * model.ERM_Aggregated_Operational_Capacity_MW[erm_group, model_year]
                for erm_group in (model.ERM_GROUPS - model.ERM_STORAGE_GROUPS)
            ) + sum(
                model.ERM_Discharge_Storage_MW[storage_group, model_year, erm_hour]
                - model.ERM_Charge_Storage_MW[storage_group, model_year, erm_hour]
                for storage_group in model.ERM_STORAGE_GROUPS
            )

        @resolve_model.model.Expression(resolve_model.model.ERM_STORAGE_GROUPS, resolve_model.model.MODEL_YEARS)
        def ERM_Aggregated_Storage_Energy_Capacity_MWh(model, storage_group, model_year):
            return sum(
                model.Operational_Storage_In_Model_Year[r, model_year] for r in model.ERM_RESOURCE_GROUPS[storage_group]
            )

        @resolve_model.model.Expression(resolve_model.model.ERM_STORAGE_GROUPS)
        def ERM_Storage_Average_Charging_Efficiency(model, storage_group):
            storage_group_len = len(model.ERM_RESOURCE_GROUPS[storage_group])
            if storage_group_len == 0:
                return 1.0
            else:
                return sum(
                    resolve_model.system.resources[storage_resource].charging_efficiency
                    for storage_resource in model.ERM_RESOURCE_GROUPS[storage_group]
                ) / len(model.ERM_RESOURCE_GROUPS[storage_group])

        @resolve_model.model.Expression(resolve_model.model.ERM_STORAGE_GROUPS)
        def ERM_Storage_Average_Discharging_Efficiency(model, storage_group):
            storage_group_len = len(model.ERM_RESOURCE_GROUPS[storage_group])
            if storage_group_len == 0:
                return 1.0
            else:
                return sum(
                    resolve_model.system.resources[storage_resource].discharging_efficiency
                    for storage_resource in model.ERM_RESOURCE_GROUPS[storage_group]
                ) / len(model.ERM_RESOURCE_GROUPS[storage_group])

        ##################################################
        # Energy Reserve Margin (ERM) CONSTRAINTS        #
        ##################################################

        @resolve_model.model.Constraint(resolve_model.model.MODEL_YEARS, resolve_model.model.ERM_HOURS)
        def Energy_Reserve_Margin_Constraint(model, model_year, erm_hour):
            """
            ERM constraint: Hourly dependable capacity (HDC) should be equal or higher than load * ( 1 + ERM )
            :param model:
            :param period:
            :param erm_hour:
            :return:
            """
            return model.Hourly_Available_Capacity[model_year, erm_hour] >= model.erm_input_load_mw[
                model_year, erm_hour
            ] * (1 + model.erm_percentage[model_year])

        @resolve_model.model.Constraint(
            resolve_model.model.ERM_STORAGE_GROUPS, resolve_model.model.MODEL_YEARS, resolve_model.model.ERM_HOURS
        )
        def ERM_Storage_Discharge_Constraint(model, storage_group, model_year, erm_hour):
            """
            storage cannot discharge at a higher rate than implied by its total installed power capacity.
            Charge and discharge rate limits are currently the same.
            :param model:
            :param storage_group:
            :param period:
            :param erm_hour:
            :return:
            """
            return (
                model.ERM_Discharge_Storage_MW[storage_group, model_year, erm_hour]
                <= model.ERM_Aggregated_Operational_Capacity_MW[storage_group, model_year]
                * model.erm_hdc_fraction[erm_hour, storage_group]
            )

        @resolve_model.model.Constraint(
            resolve_model.model.ERM_STORAGE_GROUPS, resolve_model.model.MODEL_YEARS, resolve_model.model.ERM_HOURS
        )
        def ERM_Storage_Charge_Constraint(model, storage_group, model_year, erm_hour):
            """
            storage cannot discharge at a higher rate than implied by its total installed power capacity.
            Charge and discharge rate limits are currently the same.
            :param model:
            :param storage_group:
            :param period:
            :param erm_hour:
            :return:
            """
            return (
                model.ERM_Charge_Storage_MW[storage_group, model_year, erm_hour]
                <= model.ERM_Aggregated_Operational_Capacity_MW[storage_group, model_year]
                * model.erm_hdc_fraction[erm_hour, storage_group]
            )

        @resolve_model.model.Constraint(
            resolve_model.model.ERM_STORAGE_GROUPS, resolve_model.model.MODEL_YEARS, resolve_model.model.ERM_HOURS
        )
        def ERM_Storage_Energy_Constraint(model, storage_group, model_year, erm_hour):
            """
            No more total energy can be stored at any point that the total storage energy capacity.
            :param model:
            :param storage_group:
            :param period:
            :param erm_hour:
            :return:
            """
            return (
                model.ERM_Energy_in_Storage_MWh[storage_group, model_year, erm_hour]
                <= model.ERM_Aggregated_Storage_Energy_Capacity_MWh[storage_group, model_year]
            )

        @resolve_model.model.Constraint(
            resolve_model.model.ERM_STORAGE_GROUPS, resolve_model.model.MODEL_YEARS, resolve_model.model.ERM_HOURS
        )
        def ERM_Storage_Energy_Tracking_Constraint(model, storage_group, model_year, erm_hour):
            """
            The total energy in storage at the start of the next timepoint must equal
            the energy in storage at the start of the current timepoint
            plus charging that happened in the current timepoint, adjusted for the charging efficiency,
            minus discharging in the current timepoint, adjusted for the discharging efficiency.

            Assume no AS provided from storage resources in ERM dispatch (reliability dispatch)

            :param model:
            :param storage_group:
            :param period:
            :param erm_hour:
            :return:
            """
            charging_mwh = model.ERM_Charge_Storage_MW[storage_group, model_year, erm_hour]
            discharging_mwh = model.ERM_Discharge_Storage_MW[storage_group, model_year, erm_hour]
            return (
                model.ERM_Energy_in_Storage_MWh[storage_group, model_year, model.next_erm_opt_hour[erm_hour]]
                == model.ERM_Energy_in_Storage_MWh[storage_group, model_year, erm_hour]
                + charging_mwh * model.ERM_Storage_Average_Charging_Efficiency[storage_group]
                - discharging_mwh / model.ERM_Storage_Average_Discharging_Efficiency[storage_group]
            )

        if resolve_model.model.itc_paired_storage:

            @resolve_model.model.Constraint(
                resolve_model.model.ERM_PAIRED_STORAGE_GROUPS,
                resolve_model.model.MODEL_YEARS,
                resolve_model.model.ERM_HOURS,
            )
            def ERM_Paired_Storage_Charging_Constraint(model, storage_group, model_year, erm_hour):
                """
                Constrain a paired storage resource by the energy production of its paired generation resources.
                :param model:
                :param storage_group:
                :param period:
                :param erm_hour:
                :return:
                """
                if not model.paired_charging_constraint_active_in_year[model_year]:
                    return pyo.Constraint.Skip
                # Else
                return model.ERM_Charge_Storage_MW[storage_group, model_year, erm_hour] <= sum(
                    model.ERM_Aggregated_Operational_Capacity_MW[paired_supply_group, model_year]
                    * model.erm_hdc_fraction[erm_hour, paired_supply_group]
                    for paired_supply_group in (model.ERM_PAIRED_WIND_GROUPS | model.ERM_PAIRED_SOLAR_GROUPS)
                )

        if resolve_model.model.itc_paired_storage:

            @resolve_model.model.Constraint(
                resolve_model.model.ERM_PAIRED_STORAGE_GROUPS,
                resolve_model.model.MODEL_YEARS,
                resolve_model.model.ERM_HOURS,
            )
            def ERM_Paired_Storage_Discharging_Constraint(model, storage_group, model_year, erm_hour):
                """
                Constrain a paired generation and storage resource total output by the capacity of the paired generation resource.
                :param model:
                :param storage_group:
                :param period:
                :param erm_hour:
                :return:
                """
                if not model.paired_charging_constraint_active_in_year[model_year]:
                    return pyo.Constraint.Skip
                # Else
                return model.ERM_Discharge_Storage_MW[storage_group, model_year, erm_hour] + sum(
                    model.ERM_Aggregated_Operational_Capacity_MW[paired_supply_group, model_year]
                    * model.erm_hdc_fraction[erm_hour, paired_supply_group]
                    for paired_supply_group in (model.ERM_PAIRED_WIND_GROUPS | model.ERM_PAIRED_SOLAR_GROUPS)
                ) <= sum(
                    model.ERM_Aggregated_Operational_Capacity_MW[paired_supply_group, model_year]
                    for paired_supply_group in (model.ERM_PAIRED_WIND_GROUPS | model.ERM_PAIRED_SOLAR_GROUPS)
                )

        # TODO: add the following to objective function
        erm_storage_dispatch_costs = float()
        if resolve_model.model.energy_reserve_margin:
            for model_year in resolve_model.model.MODEL_YEARS:
                for erm_hour in resolve_model.model.ERM_HOURS:
                    erm_storage_dispatch_costs += sum(
                        resolve_model.model.ERM_Charge_Storage_MW[storage_group, model_year, erm_hour]
                        * resolve_model.model.erm_storage_dispatch_cost_per_MWh
                        + resolve_model.model.ERM_Discharge_Storage_MW[storage_group, model_year, erm_hour]
                        * resolve_model.model.erm_storage_dispatch_cost_per_MWh
                        for storage_group in resolve_model.model.ERM_STORAGE_GROUPS
                    )
            resolve_model.model.Total_Cost.set_value(
                expr=resolve_model.model.Total_Cost.expr + erm_storage_dispatch_costs
            )

    ##################################################
    #  Paired Storage                                #
    ##################################################

    if resolve_model.model.itc_paired_storage:
        resource_storage_paired_data = pd.read_csv(
            resolve_model.dir_structure.resolve_settings_dir / "extras" / "resource_storage_paired.csv"
        )

        resolve_model.model.PAIRED_STORAGE_RESOURCES = resource_storage_paired_data["paired_storage_resource"].to_list()

        resolve_model.model.paired_supply_resource = pyo.Param(
            resolve_model.model.PAIRED_STORAGE_RESOURCES,
            initialize=lambda model, r: resource_storage_paired_data.loc[
                resource_storage_paired_data["paired_storage_resource"] == r, "paired_supply_resource"
            ].iloc[0],
        )

        resolve_model.model.enforce_pairing_ratio = pyo.Param(
            resolve_model.model.PAIRED_STORAGE_RESOURCES,
            initialize=lambda model, r: resource_storage_paired_data.loc[
                resource_storage_paired_data["paired_storage_resource"] == r, "enforce_pairing_ratio"
            ].iloc[0]
            in ["TRUE", "True", True],
        )

        resolve_model.model.pairing_ratio = pyo.Param(
            resolve_model.model.PAIRED_STORAGE_RESOURCES,
            initialize=lambda model, r: resource_storage_paired_data.loc[
                resource_storage_paired_data["paired_storage_resource"] == r, "pairing_ratio"
            ].iloc[0],
        )

        # Additional storage variables including charging of storage and variable to track available energy in storage
        resolve_model.model.Charge_Storage_MW = pyo.Var(
            resolve_model.model.PAIRED_STORAGE_RESOURCES, resolve_model.model.TIMEPOINTS, within=pyo.NonNegativeReals
        )
        resolve_model.model.Energy_in_Storage_MWh = pyo.Var(
            resolve_model.model.PAIRED_STORAGE_RESOURCES, resolve_model.model.TIMEPOINTS, within=pyo.NonNegativeReals
        )

        @resolve_model.model.Constraint(resolve_model.model.PAIRED_STORAGE_RESOURCES, resolve_model.model.TIMEPOINTS)
        def Paired_Storage_Charging_Constraint(model, r, model_year, rep_period, hour):
            """Constrain a paired storage resource by the energy production of its paired generator.

            Args:
                model:
                r:
                t:

            Returns:

            """
            if not model.paired_charging_constraint_active_in_year[model_year]:
                return pyo.Constraint.Skip
            # Else
            storage_charging = model.Increase_Load_MW[r, model_year, rep_period, hour]
            # if r in model.REGULATION_RESERVE_RESOURCES:
            #    storage_charging += model.Provide_Downward_Reg_From_Charge_MW[r, t]

            # if r in model.LOAD_FOLLOWING_RESERVE_RESOURCES:
            #    storage_charging += model.Provide_LF_Downward_Reserve_From_Charge_MW[r, t]

            return (
                storage_charging
                <= model.Provide_Power_MW[model.paired_supply_resource[r], model_year, rep_period, hour]
            )

        @resolve_model.model.Constraint(resolve_model.model.PAIRED_STORAGE_RESOURCES, resolve_model.model.MODEL_YEARS)
        def Paired_Storage_Renewable_Ratio_Constraint(model, r, p):
            """If user defines `enforce_pairing_ratio`, force operational capacity of supply and storage components of hybrid to be fixed ratio."""
            if model.enforce_pairing_ratio[r]:
                return (
                    model.Operational_Capacity_In_Model_Year[model.paired_supply_resource[r], p]
                    == model.pairing_ratio[r] * model.Operational_Capacity_In_Model_Year[r, p]
                )
            else:
                return pyo.Constraint.Skip

    ##################################################
    #  Synchronous Condenser                         #
    ##################################################

    resolve_model.model.SYNCHRONOUS_CONDENSER_RESOURCES = pyo.Set(
        initialize=pd.read_csv(
            resolve_model.dir_structure.resolve_settings_dir / "extras" / "synchronous_condenser_resources.csv"
        )["synchronous_condenser_resources"]
        .dropna()
        .values
    )

    synchronous_condenser_addition_to_load = (
        flexible_params.loc[flexible_params["param"] == "synchronous_condenser_addition_to_load", "value"]
        .astype(float)
        .iloc[0]
    )

    @resolve_model.model.Expression(resolve_model.model.SYNCHRONOUS_CONDENSER_RESOURCES, resolve_model.model.TIMEPOINTS)
    def Synchronous_Condenser_Addition_to_Load_MW(model, resource, model_year, rep_period, hour):
        """Synchronous condensers add to zonal load.

        Args:
            model:
            resource:
            timepoint:

        Returns:

        """
        if resource in model.SYNCHRONOUS_CONDENSER_RESOURCES:
            return (
                synchronous_condenser_addition_to_load
                * model.Committed_Capacity_MW[resource, model_year, rep_period, hour]
            )
        else:
            return 0

    @resolve_model.model.Expression(resolve_model.model.ZONES, resolve_model.model.TIMEPOINTS)
    def Zonal_Synchronous_Condenser_Addition_to_Load_MW(model, zone, model_year, rep_period, hour):
        """Sum of all `Synchronous_Condenser_Addition_to_Load_MW` in a given zone."""
        return sum(
            model.Synchronous_Condenser_Addition_to_Load_MW[plant, model_year, rep_period, hour]
            for plant in model.SYNCHRONOUS_CONDENSER_RESOURCES
            if zone in resolve_model.system.plants[plant].zones.keys()
        )

    for idx in resolve_model.model.Zonal_Power_Balance_Constraint:
        # Unpack the idx tuple
        zone, model_year, rep_period, hour = idx

        # Example of adding a variable and a number to the body (LHS) of the constraint
        resolve_model.model.Zonal_Power_Balance_Constraint[idx]._body = (
            resolve_model.model.Zonal_Power_Balance_Constraint[idx]._body
            - resolve_model.model.Zonal_Synchronous_Condenser_Addition_to_Load_MW[zone, model_year, rep_period, hour]
            - resolve_model.model.Zonal_Synchronous_Condenser_Addition_to_Load_MW[zone, model_year, rep_period, hour]
        )

    ##################################################
    #  Renewables Integration - Reserves             #
    ##################################################

    # resolve_model.model.resource_downward_lf_req = pyo.Param(
    #     resolve_model.model.ERM_HOURS,
    #     resolve_model.model.ERM_GROUPS,
    #     within=pyo.PercentFraction,
    #     initialize=lambda model, erm_hour, erm_group:
    #     erm_hdc_fraction.loc[erm_hdc_fraction['erm_hour'] == erm_hour, erm_group].iloc[0],
    # )

    return resolve_model


def _next_erm_opt_hour_init(model):
    """Define a "next_erm_hour" for periodic boundary constraints
    The next timepoint for the last hour of the day is the first hour of that day
    Args:
      model:
    Returns:
    """
    return {
        hour: hour - int(model.erm_shifting_window) + 1 if (hour % int(model.erm_shifting_window)) == 0 else hour + 1
        for hour in model.ERM_HOURS
    }
