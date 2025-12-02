# Frequently Asked Questions

1.  **What is a Component?**

    A **component** is anything that is modeled in the RESOLVE optimization problem. Examples include zones, loads, assets, and policies, to name a few.

2.  **What is a Linkage?**

    A **linkage** is type of assignment between any two components in RESOLVE. For example, a resource may be “linked” to a particular zone because its power output is meant to meet load in that zone.

3.  **What is an Asset?**

    An **asset** is a modeled component that has an investment cost and a quantity (or size). Assets can also be defined with a potential, a planned capacity, a minimum cumulative build, investment costs, and some other attributes, and it is linked to other components such as zones and transmission constraints. Examples include all resources, transmission paths, and other transmission assets. Build decisions are made in each modeled year, thus each asset build in a specific model year is specified by its vintage. A group of vintages of the same asset are called an Asset Group. For example, an asset build in 2035 is a 2035 vintage. All vintages of Solar_Fresno Asset are aggregated and reported for Solar_Fresno Asset Group.

4.  **What are resources and resource types?**

    A **resource** is a type of asset that can provide power and therefore has operational characteristics (e.g., heat rate, charging efficiency) as well as investment costs and other linkages such as zones, fuels and policies. Here are different types of resources and their critical operational data requirements:

| Resource Type   | Specific Inputs for each type  |
|-----------------|--------------------------------------------------------------------------|
| Thermal         | Fuel, heat rate slope and intercept, variable O&M. Example: biomass and biogas resources                                                  |
| Unit Commitment | Fuel, heat rate slope and intercept, ramp rate, startup and shutdown costs, variable O&M Example: combined cycles and combustion turbines |
| Generic         | Variable O&M, curtailable flag, curtailment costs, production profile (optional) Example: Geothermal                                                         |
| Solar           | Production profile, curtailable flag, curtailment costs                                                                                   |
| Wind            | Production profile, curtailable flag, curtailment costs                                                                                   |
| Storage         | Duration, charging efficiency, discharge efficiency, parasitic losses, inter-period sharing flag                                          |
| Hydro           | Min, Max and energy budget production profiles                                                                                            |
| Shed DR         | Number of calls per year, duration of each call Not modeled as dispatchable in the CPUC model                                             |

5.  **What is an Asset Group?**

    An **asset group** is a collection of assets; that is, each asset in the group has a linkage to the asset group. Asset groups behave almost just like assets, except that the selected, retired, and operational capacities of asset groups is simply the sum of all the assets within the group. That is, investment decisions of the groups themselves are not optimized by the model; investment decisions are made at the individual asset level, not the asset group level. Rather, this type of aggregation can be helpful for reporting or for defining constraints on the group, such as a minimum cumulative build or a maximum operational capacity. The model can then choose which assets within the group to build while still meeting the constraint on the group.

6.  **What is a Resource Group?**

    A **resource group** is a type of asset group that could also have operational characteristics and constraints. All resource groups are asset groups, but not all asset groups are resource groups. Like resources, resource groups have a resource type, where the type defines the resource type of each resource within the group (e.g., a Solar resource group contains only solar resources). To reduce the computational burden, you can group resources that have the same operational characteristics into a special kind of asset group called an **Operational Group**. An operational group contains all the operations-related variables and constraints (e.g., hourly power output) for the members of the group so that they are optimized only once. For example, Fresno_Solar in different CAISO cluster locations of different vintages are operationally aggregated into Fresno_Solar operational group, greatly reducing the number of hourly variables that would otherwise be needed to optimize the dispatch of these different resources.

7.  **Can a resource belong to multiple resource groups?**

    Yes, a resource can belong to multiple resource groups. In fact, this is common. For example, a resource could count toward a particular technology’s maximum build limit (e.g., Solar_MaxBuild group) and toward a locational maximum build (e.g., Kern_Solar_MaxBuild group). However, a resource can only belong to one operational group. If a resource is linked to more than one operational group, RESOLVE will throw an error because this would result in double-counting of the energy provided by that resource. To avoid this issue, all operational groups are on the “Resource Dispatch Groups” sheet of the Scenario Tool, where the “Aggregate Operations” column is TRUE for all operational groups. The “Aggregate Operations” column is labeled as FALSE for all other resource groups on all other sheets.

8.  **How to set min and max build limits?**

    Two worksheets are included in the Scenario Tool that specify minimum and maximum build limits for defined Asset Groups. The assignment of Assets to min and max build Asset Groups are defined in the Candidate Resources worksheet. You have the flexibility to define a min build limit on the most granular cluster level build resources or at the aggregated level for an Asset Group.

9.  **How to add a new Baseline resource?**

    Baseline resources are existing resources with planned capacity in all zones. There are separate worksheets formatted to define baseline resources and candidate resources. If you are adding/modifying a Baseline resource, make sure to go to the Baseline worksheet, add a new row to the end of the table, find a similar type of resource from existing list and follow column by column to accurately define each column value.

10. **How to add a new Candidate resource?**

    For candidate resources, in addition to updating Candidate Resources worksheet (similar to Baseline worksheet), you may need to make updates to “Operational Groups” and “Max Build” and “Min Build” worksheets as well. For Operational Groups, you should make sure that both the resource and its mapped operational group have the exact same operational and policy attributes and values. For example, a storage resource and its operational group must have the same duration, charging and discharging efficiency, and power output max attributes, to name a few. Note that all investment costs are entered for candidate resources (groups do not have investment cost parameters because investment decisions are made at the asset level, not the group level). Additionally, make sure Aggregate Operations is tagged as “FALSE” for the resource and is tagged as “TRUE” for operational groups.

11. **What defines a zone in RESOLVE?**

    **Zones** can be defined in the “Zonal Topology” worksheet in the Scenario Tool, and it should be the first set of input data to enter to the model. Loads, resources, transmission assets and operational groups must be assigned to a defined zone in their respective worksheets. A resource that is not linked to a zone cannot generate energy to meet load in that zone, so it would not be selected by the model.

12. **What are the inter-zonal characteristics that are captured in RESOLVE?**

    Each zone is linked to another zone via a defined power flow **path** in the Zonal Topology worksheet. The direction, the limit, and hurdle rates for inter-zonal power flow for each path are defined as attributes. Additional candidate paths for existing zones can also be added to the model to allow for it to select expansions amounts for a specific path flow. Additional constraints can also be defined to limit hourly power flow across a group of inter-zonal path flows (e.g., a total hourly power flow limit to CAISO from aggregated power flowing from all external zones to PGE, SCE, and SDGE). It is also an option to include upgrade assets for certain power flow path between defined zones.

13. **How is a CAISO transmission constraint defined?**

    The CAISO transmission constraints have three deliverability membership types: FCDS (Full Capacity Deliverability Status) Highest System Need (HSN), FCDS SSN (Secondary System Need), and EODS (Energy-Only Deliverability Status). Each CAISO transmission constraint has a defined existing headroom across all three periods. Additionally, most constraints have identified CAISO transmission upgrade(s), which provide the option to increase constraint headroom for new resource capacity (at additional cost).

    By default, RESOLVE has the optionality to determine whether candidate resources are fully deliverable (contributing to RA policy) or energy-only. For a resource to be fully deliverable, it must utilize headroom across all three deliverability membership types (HSN, SSN, EODS); an energy-only resource only contributes towards the EODS constraint. In the candidate resources workbook, you can specify whether certain resources are required to be fully deliverable (i.e. forced to provide RA and utilize headroom on all three deliverability types); this is typically done for energy storage and out-of-state wind resources.

    In RESOLVE, only candidate resources (in fact, almost all candidate resources) have memberships with CAISO transmission constraints, which informs the locations of selected capacity additions. Transmission constraints are defined in their specific worksheet. Each constraint must have a membership with at least one asset. The membership between candidate resources, transmission constraints and transmission upgrades are specified in the “Tx Membership” worksheet. Each membership has all three deliverability coefficients that are fixed for all modeling years.

14. **What are the modeled policies?**

    For each planning policy, the main inputs are the policy target (we recommend using absolute targets in the specified units in the policy table header), any adjustments to the target, and resource/asset contributions. All resource contributions are defined with a TRUE/FALSE membership toggle and a multiplier. These policies produce a non-zero shadow price if any of them bind in any of the modeled years. *(For example, the shadow price reported for the GHG policy represents the marginal cost of reducing emissions by one unit in \$/ton.)* There are four main policy targets that are modeled in RESOLVE, each defined in its own worksheet. The user can include any number of policies as they wish:

-   The systemwide planning **reliability** policy with a target reliability need (in MW) for each modeled year and a target adjustment (in MW) which covers any adjustment for out of system factors such as import availability during reliability-constrained periods. Other inputs include parameterized ELCC surfaces/curves. Resources are accredited based on ELCCs. For each resource to contribute to system’s reliability, it must have either a fixed annual ELCC defined for the resource or an assigned ELCC surface/curve, axis number and annual multipliers. Both Baseline and Candidate resources are accredited for reliability.

    -   **Mid-term reliability** (MTR) needs are modeled with a separate set of inputs for target, adjustment and resource contributions. In this case, RESOLVE portfolio is forced to meet the MTR need based on a fixed ELCC accreditation from eligible resources. More than one MTR policy can be modeled to reflect specific targets for clean firm and long-duration energy storage, for example.

-   The **clean energy** policies such as RPS and SB100 are modeled with two separate clean energy targets and adjustments, respecting their specific definitions on retail sales. Generation from operational groups (i.e., dispatch resources) are defined to have contributions to each of the clean energy policies if eligible. In this case the multiplier for resource contribution is defined for the resource generation, not capacity.

-   The **greenhouse gas (GHG) emissions** policy puts a cap on total emissions from generation within CAISO (or any zone of interest) and imports to CAISO based on CARB accounting method. The target is defined based on the CPUC IRP planning trajectory, and the adjustments represent any emissions coming from non-modeled resources (namely, behind-the-meter combined heat and power plants). Multipliers are applied to fuel consumption from emitting resources in the zone of interest where GHG emissions are capped (e.g., CAISO zones in the case of the CPUC IRP). For imports, multipliers are applied to power flow from external zones to the zone of interest to capture emissions from any unspecified imports contributing to the system’s GHG emissions. The exception is the representation of imports from NW Hydro to CAISO that are modeled as exempt from GHG accounting.

-   Another policy that is modeled in RESOLVE is a **cap-and-trade** policy. Unlike the other policies, cap-and-trade policies do not have an annual target. Instead, for this policy, the \$/ton carbon price is defined and gets applied to fuel consumption and fuel emissions intensity from resources that have attributes with this policy. Each operational resource (Baseline or Candidate), depending on the zone in which it is located, may need to be modeled with a cap-and-trade cost adder (for example, all California zones in the model). Additionally, any unspecified imports from external zones to California zones are subject to a cap-and-trade cost adder on top of hurdle rates assuming a fixed unspecified imports GHG emissions rate of 0.428 ton/MWh.

15. **How to add new load component?**

    To model a new load component:

- Go to the “Load Components” worksheet, add a new row and fill in the data for profiles, annual load, and applicable T&D loss factor. It is recommended to set “Scale by Mean Annual Energy” to TRUE, so output annual load perfectly matches the input annual load after sample days are pulled for optimization. Select or add a new Data Scenario Tag and make sure to specify the zone and flag TRUE in the “Include” column.

- Go to the “System Reliability” tab and make sure to adjust or add a new “System_RA” scenario if you are expecting your changes to load can result in system gross peak changes. The percentage targets are provided for reference to scale the system peak for absolute PRM target calculation, but they are not used in modeling.

- Go to the “Clean Energy Policy” tab and make sure you update or add a new scenario tag for RPS and SB100 absolute targets. The percentage targets are provided for reference to scale the retail sales for absolute RPS or CES target calculation.

16. **Where to define sample days?**

    Sample days are defined in the “Timeseries Clusters” tab. To add a new set of days, go to this tab, rename the cluster name under “New_Days_Placeholder”, and copy the timeseries data in the “chrono_period” and “dispatch_window” for your desired historical days and their represented sample day or dispatch window mapping. It is recommended for historical chronological periods to not contain leap days, though it will not cause an error if you prefer to include the leap days. You also have the option to exclude leap days from the case settings tab. Please note that all profiles used for modeling must contain data for the specified sample days (you can update the profiles from the data directory that contains a folder called “profiles”). Day weights for dispatch windows or sample days will be calculated endogenously.

17. **What format should the load and renewable profiles be?**

    You can add normalized or scaled profiles as input to the model. In the Scenario Tool, relevant profile paths should be added for the component of interest. Additionally, the csv file associated with the profile must be copied to the data folder directory inside “profiles” folder and within the appropriate subfolder that matches with the file path inserted in the Scenario Tool. Note that to make sure RESOLVE scales renewable production to the average capacity factor across the entire timeseries of the provided profile to make sure annual generation matches with historical average and not is not skewed by sample days. For loads, you have the option to scale the load profile by energy and or peak (we often scale it by energy only). Please note that, if you are adding a new profile, make sure to use a new name so that it triggers the profile re-scaling code appropriately.

18. **What are passthrough inputs?**

    These tables contain data that have no impact on portfolio optimization and are passed to data inputs folder solely for results summarization on the Results Viewer workbook. Examples are IEPR peak forecast and non-optimized costs that capture fixed costs for baseline resources and behind-the-meter resources.
