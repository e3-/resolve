# Getting Started & Installation

```{toctree}
:hidden:

System_Requirements
Github and Cloning
Files & Data Structure
```


This version of `Resolve` requires Python 3 and either Office 365 Excel, Excel 2021, or later. 
This page goes through instructions to set up Resolve on your local computer.

## System Requirements

- Supported Operating Systems: 
  - Windows: Has been tested on Windows 10, Windows 11, and Windows Server 2022
  - macOS: Has been tested on macOS Big Sur (macOS 11) and above.
  - Linux: Has been run on Ubuntu, but other distributions may work. Notably, Excel Scenario Tool does **not** work 
    (since Excel is not available on Linux)
- Python: 3.9+ (via Anaconda distribution)
- Excel: Excel for Microsoft 365, Excel 2021, or later

## Python Installation 

![python_img](_images/python_img.png)

The computational logic, optimization and associated code for `RESOLVE` is built in the `Python` programming language. 
Installing the right version and the related dependencies is very important to make sure that the code and the model runs as intended.
E3 recommends downloading the [Anaconda distribution package](https://www.anaconda.com/download) as this is an open source and widely used
distribution platform for working in python.

Depending on your operating system and local computer, detailed instructions for set-up and installation can be found on this [website](https://docs.anaconda.com/anaconda/install/)

It is important to note there are other available platforms as well - as long as you have Python 3.9 + installed, you should be good. 

## Github

- `Resolve` uses a combination of Excel spreadsheets, Jupyter notebooks, and Python scripts. 
- [Github](https://github.com) helps in maintaining, operating and structuring these file types so that the model can work 
seamlessly.
- The latest release of `Resolve` can be downloaded from [GitHub](https://github.com/e3-/resolve/releases/latest)
- You can use a python or anaconda package or software like PyCharm (Recommended by E3) that enables you to clone the repository
- What is Cloning?
  - Cloning in GitHub means making a copy of a repository (a project or codebase) from GitHub to your local computer. 
  - This lets you work on the project locally, with all the files and history from the original repository.
  - Further instructions on cloning and github can be found here:


:::{admonition} 2023 CPUC IRP {octicon}`zap`
Stakeholders for the 2023 California Public Utilities Integrated Resource Planning (2023 CPUC IRP) process can download 
`Resolve` and additional data, ruling case results directly from the [2022-23 IRP Events & Materials page](https://www.cpuc.ca.gov/industries-and-topics/electrical-energy/electric-power-procurement/long-term-procurement-planning/2022-irp-cycle-events-and-materials).
:::

# Files & Data Structure 

Once you've downloaded or cloned the Resolve package, you should see (at a minimum) the following files & subfoldrers:

* **LICENSE.md:** GNU AGPLv3 open-source license used for `Resolve`
  * **data/:** Data folder for any pre-existing data & case settings
  * **src/resolve/:** `Resolve` source code
* **environment.yml:** Python environment settings
* **pyproject.toml:** Python dependencies
* **User Guide** {bdg-warning}`.pdf`
* **Scenario Tool** {bdg-info}`.xlsm`
* **Results Viewer** {bdg-info}`.xlsm`

## 2023 CPUC IRP Files

The 2023 CPUC IRP release will also include additional files or files that have been renamed:
- **CPUC IRP Resource Cost & Build - PUBLIC** {bdg-success}`.xlsx`
- **Scenario Tool** → Resolve Scenario Tool - CPUC IRP 2023 PSP - PUBLIC - v1.1 {bdg-info}`.xlsm`
- **Results Viewer** → Resolve Results Viewer - CPUC IRP 2023 PSP - PUBLIC - v1.1 {bdg-info}`.xlsm`
- **results/:** Results for released 2023-23 PSP cases 

## Understanding the folders


## Saving Input Data & Case Settings

Users who want to run pre-existing cases can save all necessary inputs from the "Resolve Settings" tab of the Scenario Tool.

