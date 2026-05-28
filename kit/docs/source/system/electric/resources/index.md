# Resources

```{toctree}
:hidden:

generic
thermal
hydro
variable
storage
hybrids
shed_dr
flex_loads
```

There are seven basic resource types. This includes shed demand response and flexible loads, which are modeled as
resources (instead of as loads).

In Recap, resources are grouped into 7 different types. Each of these resources have their own inputs, assumptions, and
constraints. Future work includes making Recap a mulit-zonal model. Challenges include how resources would heuristically
dispatch and tuning perfect capacity across multiple zones.

| **Resource**         | **Type**                | **Heuristic Dispatch** | **Optimized Dispatch** |
|----------------------|-------------------------|------------------------|------------------------|
| Generic              | Availability            | Yes                    | No                     |
| Variable             | Availability            | Yes                    | No                     |
| Hydro                | Energy-Limited Resource | Yes                    | Yes                    |
| Storage              | Energy-Limited Resource | Yes                    | Yes                    |
| Hybrid               | Energy-Limited Resource | Yes                    | Yes                    |
| Shed Demand Response | Energy-Limited Resource | Yes                    | Yes                    |
| Flexible Loads       | Energy-Limited Resource | Yes                    | Yes                    |

Each resource class as their own set of constraints and therefore their own set of constraints. Below is a list of
Attributes for all resource classes

##### Shared Attributes for all Resource Classes

|                            | Generic, Hydro, Variable | Thermal | Thermal Unit Commitment | Storage | Shed | Shift |
|----------------------------|:------------------------:|:-------:|:-----------------------:|:-------:|:----:|:-----:|
| candidate_fuels            |                          |    ✓    |            ✓            |         |      |       |
| elcc_surfaces              |            ✓             |    ✓    |            ✓            |    ✓    |  ✓   |   ✓   |
| outage_distributions       |            ✓             |    ✓    |            ✓            |    ✓    |  ✓   |   ✓   |
| policies                   |            ✓             |    ✓    |            ✓            |    ✓    |  ✓   |   ✓   |
| reserves                   |            ✓             |    ✓    |            ✓            |    ✓    |  ✓   |   ✓   |
| zones                      |            ✓             |    ✓    |            ✓            |    ✓    |  ✓   |   ✓   |
| adjacency                  |                          |         |                         |         |      |   ✓   |
| can_build_new              |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| can_retire                 |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| capacity_planned           |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| charging_efficiency        |                          |         |                         |    ✓    |      |   ✓   |
| cost_fixed_om              |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| cost_investment            |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| discharging_efficiency     |                          |         |                         |    ✓    |      |   ✓   |
| duration                   |                          |         |                         |    ✓    |      |   ✓   |
| energy_budget_annual       |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| energy_budget_daily        |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| energy_budget_monthly      |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| lifetime_financial         |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| lifetime_physical          |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| max_annual_calls           |                          |         |                         |         |  ✓   |   ✓   |
| max_call_duration          |                          |         |                         |         |  ✓   |   ✓   |
| max_daily_calls            |                          |         |                         |         |  ✓   |   ✓   |
| max_monthly_calls          |                          |         |                         |         |  ✓   |   ✓   |
| mean_time_to_repair        |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| min_down_time              |                          |         |            ✓            |         |  ✓   |   ✓   |
| min_stable_level           |                          |         |            ✓            |         |  ✓   |   ✓   |
| min_up_time                |                          |         |            ✓            |         |  ✓   |   ✓   |
| name                       |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| outage_profile             |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| parasitic_loss             |                          |         |                         |    ✓    |      |   ✓   |
| power_input_max            |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| power_input_min            |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| power_output_max           |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| power_output_min           |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| ramp_rate                  |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| random_seed                |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| shift_direction            |                          |         |                         |         |      |   ✓   |
| shutdown_cost              |                          |         |            ✓            |         |  ✓   |   ✓   |
| start_cost                 |                          |         |            ✓            |         |  ✓   |   ✓   |
| start_fuel_use             |                          |         |            ✓            |         |  ✓   |   ✓   |
| stochastic_outage_rate     |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| storage_cost_fixed_om      |                          |         |                         |    ✓    |      |   ✓   |
| storage_cost_investment    |                          |         |                         |    ✓    |      |   ✓   |
| td_losses_adjustment       |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| unit_size                  |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| variable_cost_power_input  |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| variable_cost_power_output |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |
| vintage                    |            ✓             |    ✓    |            ✓            |         |  ✓   |   ✓   |

| **Attributes**                                                       | **Thermal**  | **Variable** | **HybridVariable** | **Hydro**      | **Storage**    | **HybridStorage** | **ShedDr**     | **FlexLoad**   |
|----------------------------------------------------------------------|--------------|--------------|--------------------|----------------|----------------|-------------------|----------------|----------------|
| Resource Type                                                        | Availability | Availability | Energy-limited     | Energy-limited | Energy-limited | Energy-limited    | Energy-limited | Energy-limited |
| Category                                                             | -            | Yes          | Yes                | -              | -              | -                 | -              | -              |
| Can Build New                                                        | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | Yes            | Yes            |
| Can Retire                                                           | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | Yes            | Yes            |
| Planned Installed Capacity (MW)                                      | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | Yes            | Yes            |
| Minimum Operational Capacity in Modeled Year (MW)                    | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | Yes            | Yes            |
| Minimum Cumulative New Build (MW)                                    | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | Yes            | Yes            |
| Total (Existing + Candidate) Resource Potential in Modeled Year (MW) | -            | Yes          | Yes                | -              | -              | -                 | -              | -              |
| Variable O&M Cost ($/MWh)                                            | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | Yes            | Yes            |
| Curtailment Cost ($/MWh)                                             | -            | Yes          | Yes                | Yes            | Yes            | Yes               | -              | -              |
| All-In Fixed Cost by Vintage ($/kW-year)                             | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | -              | -              |
| New Fixed O&M Cost by Vintage ($/kW-year)                            | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | -              | -              |
| Planned Fixed O&M Cost by Vintage ($/kW-year)                        | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | -              | -              |
| Curtailable (Default: True)                                          | -            | Yes          | Yes                | Yes            | -              | -                 | -              | -              |
| Pmax Rating                                                          
 (CSV file)                                                           | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | -              | -              |
| Daily Energy Budget                                                  
 (Capacity Factor)                                                    | -            | Yes          | Yes                | Yes            | Yes            | Yes               | -              | Yes            |
| Daily Energy Budget                                                  
 (CSV file)                                                           | -            | Yes          | Yes                | Yes            | Yes            | Yes               | -              | Yes            |
| Annual Energy Budget                                                 
 (Capacity Factor)                                                    | -            | Yes          | Yes                | Yes            | Yes            | Yes               | -              | Yes            |
| Annual Energy Budget                                                 
 (CSV file)                                                           | -            | Yes          | Yes                | Yes            | Yes            | Yes               | -              | Yes            |
| Stochastic Outage Rate                                               | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | Yes            | Yes            |
| Mean Time to Repair                                                  | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | Yes            | Yes            |
| Random Seed                                                          | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | Yes            | Yes            |
| Outage Distribution                                                  | Yes          | Yes          | Yes                | Yes            | Yes            | Yes               | Yes            | Yes            |
| Fixed Duration (hour)                                                | -            | -            | -                  | -              | Yes            | Yes               | -              | -              |
| Planned Storage Capacity (MWh)                                       | -            | -            | -                  | -              | Yes            | Yes               | -              | -              |
| Total (Planned + New) Resource Potential in Modeled Year (MW)        | Yes          | -            | -                  | Yes            | Yes            | Yes               | Yes            | Yes            |
| All-In Storage Fixed Cost by Vintage ($/kWh-year)                    | -            | -            | -                  | -              | Yes            | Yes               | -              | -              |
| New Storage Fixed O&M Cost by Vintage ($/kWh-year)                   | -            | -            | -                  | -              | Yes            | Yes               | -              | -              |
| Planned Storage Fixed O&M Cost by Vintage ($/kWh-year)               | -            | -            | -                  | -              | Yes            | Yes               | -              | -              |
| Charging Efficiency (%)                                              | -            | -            | -                  | -              | Yes            | Yes               | -              | Yes            |
| Discharging Efficiency (%)                                           | -            | -            | -                  | -              | Yes            | Yes               | -              | Yes            |
| Parasitic Loss (% SoC/hour)                                          | -            | -            | -                  | -              | Yes            | Yes               | -              | Yes            |
| 1-Hour Ramp Rate Limit                                               | Yes          | -            | -                  | Yes            | Yes            | Yes               | -              | -              |
| 2-Hour Ramp Rate Limit                                               | Yes          | -            | -                  | Yes            | Yes            | Yes               | -              | -              |
| 3-Hour Ramp Rate Limit                                               | Yes          | -            | -                  | Yes            | Yes            | Yes               | -              | -              |
| 4-Hour Ramp Rate Limit                                               | Yes          | -            | -                  | Yes            | Yes            | Yes               | -              | -              |
| Pmin Rating                                                          
 (% Nameplate)                                                        | Yes          | -            | -                  | Yes            | Yes            | Yes               | -              | -              |
| Pmin Rating                                                          
 (CSV file)                                                           | Yes          | -            | -                  | Yes            | Yes            | Yes               | -              | -              |
| Pmax Rating                                                          
 (% Nameplate)                                                        | Yes          | -            | -                  | Yes            | Yes            | Yes               | -              | -              |
| Max Charging Rating (% Nameplate)                                    | -            | -            | -                  | Yes            | -              | -                 | -              | -              |
| Max Charging Rating (CSV file)                                       | -            | -            | -                  | Yes            | -              | -                 | -              | -              |
| Daily Energy Budget (MWh)                                            | -            | -            | -                  | Yes            | -              | -                 | Yes            | Yes            |
| Monthly Energy Budget (MWh)                                          | -            | -            | -                  | Yes            | -              | -                 | Yes            | Yes            |
| Annual Energy Budget (MWh)                                           | -            | -            | -                  | Yes            | -              | -                 | Yes            | Yes            |
| Fixed O&M Cost ($/kW-year)                                           | -            | -            | -                  | -              | -              | -                 | Yes            | Yes            |
| Shed Profile                                                         
 (% of Nameplate)                                                     | -            | -            | -                  | -              | -              | -                 | Yes            | -              |
| Take Profile (% Nameplate)                                           | -            | -            | -                  | -              | -              | -                 | Yes            | Yes            |
| Pmin profile (% Nameplate)                                           | -            | -            | -                  | -              | -              | -                 | Yes            | Yes            |
| # of Calls per Year                                                  | -            | -            | -                  | -              | -              | -                 | Yes            | Yes            |
| # of Calls per Month                                                 | -            | -            | -                  | -              | -              | -                 | Yes            | Yes            |
| # of Calls per Day                                                   | -            | -            | -                  | -              | -              | -                 | Yes            | Yes            |
| Call Duration (hr)                                                   | -            | -            | -                  | -              | -              | -                 | Yes            | Yes            |
| Grouping                                                             | -            | -            | -                  | -              | -              | -                 | -              | Yes            |
| Adjacency                                                            | -            | -            | -                  | -              | -              | -                 | -              | Yes            |
| Allow inter-period sharing                                           | -            | -            | -                  | -              | -              | -                 | -              | Yes            |
| Shift Direction                                                      | -            | -            | -                  | -              | -              | -                 | -              | Yes            |
| Shed Profile                                                         
 (% Nameplate)                                                        | -            | -            | -                  | -              | -              | -                 | -              | Yes            |
| Unit Commitment (Default: False)                                     | Yes          | -            | -                  | -              | -              | -                 | -              | -              |
| Unit Size (MW)                                                       | Yes          | -            | -                  | -              | -              | -                 | -              | -              |
| Min Stable Level                                                     | Yes          | -            | -                  | -              | -              | -                 | -              | -              |
| Start Cost ($/unit)                                                  | Yes          | -            | -                  | -              | -              | -                 | -              | -              |
| Shutdown Cost ($/unit)                                               | Yes          | -            | -                  | -              | -              | -                 | -              | -              |
| Start Fuel Use (MMBtu)                                               | Yes          | -            | -                  | -              | -              | -                 | -              | -              |
| Fuel Burn Intercept (MMBtu/hr)                                       | Yes          | -            | -                  | -              | -              | -                 | -              | -              |
| Fuel Burn Slope (MMBtu/MW)                                           | Yes          | -            | -                  | -              | -              | -                 | -              | -              |
| Min Down Time (hr)                                                   | Yes          | -            | -                  | -              | -              | -                 | -              | -              |
| Min Up Time (hr)                                                     | Yes          | -            | -                  | -              | -              | -                 | -              | -              |

Not all these inputs are needed for Recap. This table shows which of these are needed for each class

| **Attributes**                                                       | **Thermal**  | **Variable** | **HybridVariable** | **Hydro**      | **Storage**    | **HybridStorage** | **ShedDr**     | **FlexLoad**   |
|----------------------------------------------------------------------|--------------|--------------|--------------------|----------------|----------------|-------------------|----------------|----------------|
| Dispatch type                                                        | Availability | Availability | Energy-limited     | Energy-limited | Energy-limited | Energy-limited    | Energy-limited | Energy-limited |
| Category                                                             | -            | Both         | Both               | -              | -              | -                 | -              | -              |
| Can Build New                                                        | Resolve      | Resolve      | Resolve            | Resolve        | Resolve        | Resolve           | Resolve        | Resolve        |
| Can Retire                                                           | Resolve      | Resolve      | Resolve            | Resolve        | Resolve        | Resolve           | Resolve        | Resolve        |
| Planned Installed Capacity (MW)                                      | Both         | Both         | Both               | Both           | Both           | Both              | Both           | Both           |
| Minimum Operational Capacity in Modeled Year (MW)                    | Resolve      | Resolve      | Resolve            | Resolve        | Resolve        | Resolve           | Resolve        | Resolve        |
| Minimum Cumulative New Build (MW)                                    | Resolve      | Resolve      | Resolve            | Resolve        | Resolve        | Resolve           | Resolve        | Resolve        |
| Total (Existing + Candidate) Resource Potential in Modeled Year (MW) | -            | Resolve      | Resolve            | -              | -              | -                 | -              | -              |
| Variable O&M Cost ($/MWh)                                            | Resolve      | Resolve      | Resolve            | Resolve        | Resolve        | Resolve           | Resolve        | Resolve        |
| Curtailment Cost ($/MWh)                                             | -            | Resolve      | Resolve            | Resolve        | Resolve        | Resolve           | -              | -              |
| All-In Fixed Cost by Vintage ($/kW-year)                             | Resolve      | Resolve      | Resolve            | Resolve        | Resolve        | Resolve           | -              | -              |
| New Fixed O&M Cost by Vintage ($/kW-year)                            | Resolve      | Resolve      | Resolve            | Resolve        | Resolve        | Resolve           | -              | -              |
| Planned Fixed O&M Cost by Vintage ($/kW-year)                        | Resolve      | Resolve      | Resolve            | Resolve        | Resolve        | Resolve           | -              | -              |
| Curtailable (Default: True)                                          | -            | Resolve      | Resolve            | Resolve        | -              | -                 | -              | -              |
| Pmax Rating                                                          
 (CSV file)                                                           | Both         | Both         | Both               | Both           | Both           | Both              | -              | -              |
| Daily Energy Budget                                                  
 (Capacity Factor)                                                    | -            | Both         | Both               | Both           | Both           | Both              | -              | Both           |
| Daily Energy Budget                                                  
 (CSV file)                                                           | -            | Both         | Both               | Both           | Both           | Both              | -              | Both           |
| Annual Energy Budget                                                 
 (Capacity Factor)                                                    | -            | Both         | Both               | Both           | Both           | Both              | -              | Both           |
| Annual Energy Budget                                                 
 (CSV file)                                                           | -            | Both         | Both               | Both           | Both           | Both              | -              | Both           |
| Stochastic Outage Rate                                               | Recap        | Recap        | Recap              | Recap          | Recap          | Recap             | Recap          | Recap          |
| Mean Time to Repair                                                  | Recap        | Recap        | Recap              | Recap          | Recap          | Recap             | Recap          | Recap          |
| Random Seed                                                          | Recap        | Recap        | Recap              | Recap          | Recap          | Recap             | Recap          | Recap          |
| Outage Distribution                                                  | Recap        | Recap        | Recap              | Recap          | Recap          | Recap             | Recap          | Recap          |
| Fixed Duration (hour)                                                | -            | -            | -                  | -              | Both           | Both              | -              | -              |
| Planned Storage Capacity (MWh)                                       | -            | -            | -                  | -              | Both           | Both              | -              | -              |
| Total (Planned + New) Resource Potential in Modeled Year (MW)        | Resolve      | -            | -                  | Resolve        | Resolve        | Resolve           | Resolve        | Resolve        |
| All-In Storage Fixed Cost by Vintage ($/kWh-year)                    | -            | -            | -                  | -              | Resolve        | Resolve           | -              | -              |
| New Storage Fixed O&M Cost by Vintage ($/kWh-year)                   | -            | -            | -                  | -              | Resolve        | Resolve           | -              | -              |
| Planned Storage Fixed O&M Cost by Vintage ($/kWh-year)               | -            | -            | -                  | -              | Resolve        | Resolve           | -              | -              |
| Charging Efficiency (%)                                              | -            | -            | -                  | -              | Both           | Both              | -              | Both           |
| Discharging Efficiency (%)                                           | -            | -            | -                  | -              | Both           | Both              | -              | Both           |
| Parasitic Loss (% SoC/hour)                                          | -            | -            | -                  | -              | Both           | Both              | -              | Both           |
| 1-Hour Ramp Rate Limit                                               | Resolve      | -            | -                  | Resolve        | Resolve        | Resolve           | -              | -              |
| 2-Hour Ramp Rate Limit                                               | Resolve      | -            | -                  | Resolve        | Resolve        | Resolve           | -              | -              |
| 3-Hour Ramp Rate Limit                                               | Resolve      | -            | -                  | Resolve        | Resolve        | Resolve           | -              | -              |
| 4-Hour Ramp Rate Limit                                               | Resolve      | -            | -                  | Resolve        | Resolve        | Resolve           | -              | -              |
| Pmin Rating                                                          
 (% Nameplate)                                                        | Both         | -            | -                  | Both           | Both           | Both              | -              | -              |
| Pmin Rating                                                          
 (CSV file)                                                           | Both         | -            | -                  | Both           | Both           | Both              | -              | -              |
| Pmax Rating                                                          
 (% Nameplate)                                                        | Both         | -            | -                  | Both           | Both           | Both              | -              | -              |
| Max Charging Rating (% Nameplate)                                    | -            | -            | -                  | Both           | -              | -                 | -              | -              |
| Max Charging Rating (CSV file)                                       | -            | -            | -                  | Both           | -              | -                 | -              | -              |
| Daily Energy Budget (MWh)                                            | -            | -            | -                  | Both           | -              | -                 | Both           | Both           |
| Monthly Energy Budget (MWh)                                          | -            | -            | -                  | Both           | -              | -                 | Both           | Both           |
| Annual Energy Budget (MWh)                                           | -            | -            | -                  | Both           | -              | -                 | Both           | Both           |
| Fixed O&M Cost ($/kW-year)                                           | -            | -            | -                  | -              | -              | -                 | Resolve        | Resolve        |
| Shed Profile                                                         
 (% of Nameplate)                                                     | -            | -            | -                  | -              | -              | -                 | Both           | -              |
| Take Profile (% Nameplate)                                           | -            | -            | -                  | -              | -              | -                 | Both           | Both           |
| Pmin profile (% Nameplate)                                           | -            | -            | -                  | -              | -              | -                 | Both           | Both           |
| # of Calls per Year                                                  | -            | -            | -                  | -              | -              | -                 | Recap          | Recap          |
| # of Calls per Month                                                 | -            | -            | -                  | -              | -              | -                 | Recap          | Recap          |
| # of Calls per Day                                                   | -            | -            | -                  | -              | -              | -                 | Recap          | Recap          |
| Call Duration (hr)                                                   | -            | -            | -                  | -              | -              | -                 | Recap          | Recap          |
| Grouping                                                             | -            | -            | -                  | -              | -              | -                 | -              | Recap          |
| Adjacency                                                            | -            | -            | -                  | -              | -              | -                 | -              | Recap          |
| Allow inter-period sharing                                           | -            | -            | -                  | -              | -              | -                 | -              | Recap          |
| Shift Direction                                                      | -            | -            | -                  | -              | -              | -                 | -              | Recap          |
| Shed Profile                                                         
 (% Nameplate)                                                        | -            | -            | -                  | -              | -              | -                 | -              | Recap          |
| Unit Commitment (Default: False)                                     | Resolve      | -            | -                  | -              | -              | -                 | -              | -              |
| Unit Size (MW)                                                       | Resolve      | -            | -                  | -              | -              | -                 | -              | -              |
| Min Stable Level                                                     | Resolve      | -            | -                  | -              | -              | -                 | -              | -              |
| Start Cost ($/unit)                                                  | Resolve      | -            | -                  | -              | -              | -                 | -              | -              |
| Shutdown Cost ($/unit)                                               | Resolve      | -            | -                  | -              | -              | -                 | -              | -              |
| Start Fuel Use (MMBtu)                                               | Resolve      | -            | -                  | -              | -              | -                 | -              | -              |
| Fuel Burn Intercept (MMBtu/hr)                                       | Resolve      | -            | -                  | -              | -              | -                 | -              | -              |
| Fuel Burn Slope (MMBtu/MW)                                           | Resolve      | -            | -                  | -              | -              | -                 | -              | -              |
| Min Down Time (hr)                                                   | Resolve      | -            | -                  | -              | -              | -                 | -              | -              |
| Min Up Time (hr)                                                     | Resolve      | -            | -                  | -              | -              | -                 | -              | -              |


