# Running RESOLVE

After saving your input data & case settings (refer below to see how this should look like) (as described in [Saving Input Data & Case Settings](https://docs.ethree.com/projects/resolve/en/latest/user_guide/index.html#saving-inputs)), you are now ready to run RESOLVE. Here is the file directory structure with the main folders that you interact with when running a RESOLVE case. The “data” folder then holds all input data

Table 1. The subfolders in the

| Folder name                                       | Description                                                                                                                                                                                                                                                                                      |
|---------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| The “data” folder                                 |                                                                                                                                                                                                                                                                                                  |
| interim                                           | Includes all system data that gets saved from Scenario Tool via macro. Each folder saved data for a specific component type. The subfolders of “systems” and “linkages” share data regarding the relationship between components.                                                                |
| profiles                                          | Includes hourly profiles. Subfolders include different components of the system that require hourly profiles.                                                                                                                                                                                    |
| processed                                         | Includes re-scaled profiles from RESOLVE which gets created the first time running a RESOLVE case with all profiles and sample days.                                                                                                                                                             |
| settings                                          | Includes sample days in the “timeseries” subfolder and all case definitions in the “resolve” subfolder. The subfolder of “temporal_settings” is where modeling years and other temporal settings get saved.                                                                                      |
| The “results” folder                              |                                                                                                                                                                                                                                                                                                  |
| Subfolders in “resolve” folder for each case name | Includes results of a case run. If a run is successful, the main results will be saved in the “summary” folder for the case. Results folder for a case will still be created if the run fails but no summary results will be available. The log file may help identify the case failure reason.  |

![RESOLVE Data Folder Structure](06124daeeb86dd1b8d9246153b3dc8c0.emf)

Figure 1. RESOLVE Data Folder Structure
