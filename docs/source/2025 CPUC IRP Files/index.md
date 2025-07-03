## 2025 CPUC IRP Files

The core of the RESOLVE public package includes the following content that the user may directly need to use:

| **Content**                       | **Description**                                                                                                                                                                 |
|-----------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| RESOLVE Scenario Tool             | Contains the data used to run the shared public portfolios. The user is also encouraged to use the workbook to setup new cases if desired.                                      |
| RESOLVE Results Viewer Template   | To be used only if the user needs to load in a new case run.                                                                                                                    |
| RESOLVE Data Folder               | Include raw input data from Scenario Tool, profiles, as well as case settings of public portfolio runs for an IRP cycle                                                         |
| RESOLVE Case Results              | Each folder contains the raw outputs for a specific RESOLVE portfolio run                                                                                                       |
| Saved Case Results Viewer         | Results Viewer includes the loaded results viewer                                                                                                                               |
| Code repository                   | Includes the code base for anyone interested in running a new case. See the installation instructions for details.                                                              |
| Hourly Results Aggregation Script | Includes a Jupyter Notebook that can be toggled with an existing RESOLVE case results to review hourly results and generate aggregated files if desired.                        |
| RESOLVE Results Loading Script    | A script to load the results of a new RESOLVE case run in the Results Viewer template.                                                                                          |
| RESOLVE Day Sampling Script       | This script was used to create sample days in RESOLVE. Sampled days are included in the Scenario Tool, so users should not need to interact with this script unless interested. |

Additional workbooks may also be included in a RESOLVE package if CPUC desired. In the past, some of the upstream workbooks such as baseline resource data workbook, candidate resource cost and potential workbooks have made available along with a RESOLVE typical package.