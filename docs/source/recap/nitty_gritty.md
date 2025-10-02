# 🔎 Nitty Gritty

## 1. Model Inputs

### 📈 Recap Loads (Hourly ANN)

RECLAIM is a Neural Network regression algorithm used to simulate load profiles across a broad range of weather
conditions. It is a key pre-requisite to running any Recap cases when only relatively short sample of actual historical
load data are available.

Below is a step-by-step user guide for running RECLAIM model. For detailed documentation on model structure, please
reach out to Ruoshui, Yuchi.

#### Step 1: Setting up Environment

**Pulling RECLAIM from GitHub**: Navigate to [RESERVE-RECLAIM branch](https://github.com/e3-/RESERVE-RECLAIM), then get
the code off of GitHub by clicking the green “Code” tab on top of the repository, and “Download ZIP” to download a copy
of the codebase on your device. After that, unzip the file in the project folder.

For folks that’re more familiar with PyCharm, the same actions can be accomplished using PyCharm’s built-in version
control tools. For more info, please refer
to [Getting started for PyCharm](../quick_start.md/installing-pycharm-as-a-graphical-interface-optional).

> Note that it is not necessary to run RECLAIM on an AWS instance, but similar to Recap, you will need a certificated
> GitHub account to access and clone the RECLAIM codebase.

**Installing the RECLAIM Environment**: Use `conda` to set up a specific python environment for RECLAIM. To do that,
open a Command Prompt window in the “RESERVE-RECLAIM” directory by typing `cmd` in the address bar and use the following
command: `conda env update -f environment.yml`.

- It might be necessary to reinstall the `netcdf` package if you run into problem with the *near surface* dataset down
  the line.

**Obtaining a license for ERA5 dataset**: RECLAIM is set up to download weather data (for the most case, temperature)
from ERA5, a data provider of a large number of atmospheric, land and oceanic climate variables in the historical
periods at an hourly resolution.

To access these data, you must first sign up for a Climate Data Store (CDS) account and get an API key that you add to
home directory. Follow the instruction in [this link](https://cds.climate.copernicus.eu/api-how-to) to obtain the
license.

After signing up, it's also necessary to
click [this link](https://cds.climate.copernicus.eu/cdsapp/#!/terms/licence-to-use-copernicus-products) and agree to the
terms prior to downloading.

> The preferrable way is always to create your own license following the instructions, but if you're time-constrained
> and wish to skip this process, you can reach out to Ruoshui for a shared license file. *However, since there is a
maximum limit on single account connection, you may end up waiting in the queue when using the shared license*.

<br>

#### Step 2: Download Temperature Data

Hourly temperature is the key input to the ANN model. If you have already gathered historical temperature data from
other source, skip this part and jump to **“Run RECLAIM Case”** to set up simulations. Otherwise, follow the steps below
and use the prepared UI to download data from ERA5.

> Note that if you’re feeding external temperature data into RECLAIM, you need to make sure the profiles are properly
> formatted to be recognizable for RECLAIM. For more details on data format, please refer to “Run RECLAIM Case” section
> step 3.

0. In the repository folder, navigate to `“RESERVE-RECLAIM\data\settings\templates”`. Make a copy
   of `“Template_ERA5_download.xlsx”` and paste under the parent folder (`“RESERVE-RECLAIM\data\settings”`). Rename the
   file with project name if you wish to.

1. Read the “<span style="color:white;background-color:#034E6E">Instructions</span>” tab for general guidelines on the
   role of each tab.

2. Fill in the “<span style="color:black;background-color:#FFAF00">Main Parameters</span>”
   and “<span style="color:black;background-color:#FFAF00">Variables</span>” tab following the inline documentation.
   Fill in the locations via the “<span style="color:black;background-color:#FFAF00">Box Query</span>” tab.

3. After populating the UI, navigate to `“RESERVE-RECLAIM\scripts\ERA5_tools”`, run `“download_era5_data.py”` by
   typing `cmd` in the address bar and use the following
   command: `python run download_era5_data.py [NameofTemplateUI].xlsx`

   > <font color='#595959'>***What will happen here?***</font>
   >
   > The UI will be requesting data from the dataset of your choice through a CDS API. After downloading all requested
   items (in **`.grib`** form, under `“RESERVE-RECLAIM\data\raw\ERA5_raw”` folder), the script will clean up the data
   and store a copy of **`.csv`** format under `“RESERVE-RECLAIM\data\raw\ERA5_cleaned”` folder.
   >
   > If the toggle for *Generate Reclaim Input* is `TRUE` in the UI “<span style="color:black;background-color:#FFAF00">
   Main Parameters</span>” tab, the formatted temperature data that’s recognizable for RECLAIM will be stored
   under `“RESERVE-RECLAIM\data\raw\reclaim_raw”` folder.

>

5. After all data variables are downloaded, check out the data under `“RESERVE-RECLAIM\data\raw”` folder and conduct
   QAQC when necessary.
    - For the full reanalysis dataset, you should expect <u>10~30 mins</u> downloading time per year, per box query
    - For the near surface dataset, you should expect <u>~12 mins</u> per year regardless the amount of box/points. (
      *Reminder that near surface dataset only have data available till 2019.*)

<br>

#### Step 3: Run RECLAIM Cases

We will make use of another UI to define neural net training parameters, specify start / end time for training and
inference dataset in the model, and set up RECLAIM cases.

0. In the repository folder, navigate to `“RESERVE-RECLAIM\data\settings\templates”`, make a copy
   of `“Template_RECLAIM_case_setup.xlsx”` and paste under the parent folder (`“RESERVE-RECLAIM\data\settings”`). Rename
   the file with project name if you wish to.

1. Read the “<span style="color:white;background-color:#034E6E">Instructions</span>” tab for general guidelines on the
   role of each tab.

2. In “<span style="color:black;background-color:#FFAF00">Main Parameters</span>” tab, fill in *Project Name*. Leave
   *Sample Interval* as `1H` if you’re training model with hourly load/temperature input.
   In “<span style="color:black;background-color:#FFAF00">Training Parameters</span>” tab, leave modeling parameter
   assumptions as it is if there’s no specific needs in the training.

3. Navigate to “<span style="color:black;background-color:#FFAF00">Timeseries Attributes</span>” tab, fill in profiles
   names and file paths. Training features (e.g., temperature) should be marked as Input while target output (e.g.,
   loads) are Output. <u>It’s critical to provide the proper profiles, so make sure to double check data quality &
   profile formats following the spreadsheet inline instructions</u>.

4. Specify start and end time for training, testing, and inference set in
   the “<span style="color:black;background-color:#FFAF00">Starts and End</span>” tab. Note that start time is
   inclusive, while end time is exclusive.

5. Modify “<span style="color:black;background-color:#FFAF00">Lag Term
   Configs"</span>, “<span style="color:black;background-color:#FFAF00">Lead Term Configs"</span>,
   and “<span style="color:black;background-color:#FFAF00">Temporal Features"</span> when needed, following the notes in
   the “<span style="color:white;background-color:#034E6E">Instructions</span>” page. You can leave the template input
   as it is for general load simulation.

6. After populating the UI, navigate to `“RESERVE-RECLAIM\scripts”`, run `“reclaim.py”` by typing `cmd` in the address
   bar and use the following command: `python run reclaim.py [NameofTemplateUI].xlsx`

   > <font color='#595959'>***What will happen here?***</font>
   >
   > While most likely users are only providing the path to weather data (e.g., temperature) in
   the “<span style="color:black;background-color:#FFAF00">Timeseries Attributes</span>” tab, the script will append
   profiles for other training features (e.g. calendar inputs) depending upon the toggle for lag term, lead term, and
   temporal settings.
   >
   > The data essentially passed over to the ANN model are stored
   here: `“RESERVE-RECLAIM\data\interim\[User-SpecifiedProjectName]”`, which include training input for 1). training &
   validation dataset; 2). Testing dataset; and 3). Inference dataset, as well as ground truth outputs for 1) and 2).
   The cross validation folds are also set up during this process.
   >
   > The script will then construct the ANN model with the data input and training parameters specified in the UI.

>

7. After the training is done, navigate to `“RESERVE-RECLAIM\data\processed\[User-SpecifiedProjectName]\pred\”`,
   simulated load are stored in `“pred_infer.pkl”` file. It would contain 10 predictions (this is the default number of
   cross validation folders set in "Training parameters" tab) from the ensemble of models that reclaim trained as well
   as a simple average to get to your end results.

<br>

#### Step 4: Profile Diagnostics

```{note}
Under construction
```

### Recap Resources

```{note}
Under construction
```

##### 🏭 Dispatchable resources

outages, capacities

##### 🌞💨 Renewable resources

NREL SAM / WIND Toolkit

##### 🔋 Energy limited resources

## 2. Model Outputs

```{note}
Under construction
```

## 3. Model Mechanics

```{note}
Under construction

Documentation to-do: Integrate DrawIO file below 
into documentation.

Maybe helpful: 
https://pypi.org/project/sphinxcontrib-drawio/
```

Download [this DRAWIO file from Google Drive](https://drive.google.com/file/d/1BKZp3KrtxF9P3a_VBaPiyclfDVB7CM0T/view) \
and then open the interactive diagram using [Diagrams.net](https://app.diagrams.net/).

It should look like this:
![](../_images/RecapCodeFlow.PNG)

### Data Flow in Recap

![](../_images/RecapDataFlow.jpg)

### Monte Carlo Simulation

```{note}
Under construction
```

### Optimization Model Formulation

[**Full Model Formulation Here
** (thanks Reza!)](https://ethreesf.sharepoint.com/:w:/s/Models/ESWsdgyI85lDtKq8NlvdxXcB2KOeLfmv9Zqayb4GBnAfYw?e=D2EBGG)
<br>

Recap optimally dispatches energy-limited resources (ELRs), i.e., storage, hydro, demand response, against the load net
of non-ELRs (dispatchable w outages, variable resources) to minimize unserved energy.

Unlike Resolve - with its numerous constraints (emissions, PRM, deliverability, etc.) - Recap's model formulation is
relatively straightforward.

![](../_images/optimization_graphic_1.png)

## 4. 🍬 Recap 3.0 ➡️ Recap 2.0 Wrapper

The Recap3 —> Recap2 wrapper allows the user to create cases in the Recap 3 UI and generate and run cases using Recap 2.

**Motivation:** As of Jan 2023, Recap 3.0 cases take a long time to finish (dispatch optimization solve time). This
wrapper serves as a “backup”.

**How To Run**

* Set the `Use Recap 2.0 Wrapper?` toggle to TRUE in the **> Case Dashboard** tab of the Recap 3.0 UI.
    * This will execute the `run_Recap2_wrapper.py` script

**Inputs**

* Recap 3.0 input CSVs: `> new_modeling_toolkit > data` folder
* Mapping files w default values: `> new_modeling_toolkit > Recap > Recap2_wrapper_inputs_mapping` folder

**Outputs**

* Recap 2.0 input CSVs: `> new_modeling_toolkit > Recap 2.0 > inputs` folder
* Recap 2.0 output CSVs: `> new_modeling_toolkit > Recap 2.0 > results` folder

<br>

<ins>**❗ Notes + Warnings:**</ins>
<br>

1. **DEFAULT VALUES:** Certain values used by Recap 2.0 have defaults not in the Recap 3.0 UI.

   Default values (and input name mappings) are specified in the
   `> Recap2_wrapper_inputs_mapping` folder.

   For example: the generator module and dynamic storage inputs assumes 0% maintenace rate for all months. And the
   outage distribution 64 is used for all outages.

   Please confirm these default values are OK for your system, and coordinate with Recap 3.0 dev team to add them to the
   UI and wrapper if they are not acceptable.

2. **Some inputs used only by Recap 2.0:** There are a set of inputs used by Recap 2.0 that are not used by Recap 3.0.
   These were added to the UI to enable the Recap 2.0 wrapper.

3. **Recap 3.0 ELCC functionality preserved:** Recap 3.0 allows the user to create marginal ELCCs and ELCC surfaces
   without having to manually create each case. Separate Recap 2.0 cases are generated.

4. **Future 3.0 Functionality will not be supported:** Any Recap 3.0 developments beyond Recap 2.0 functionality will
   not be effectively represented by the wrapper (e.g., flexible load formulations w call limits, correlated thermal
   outages, etc.)

<ins>**💻 Code Details:**</ins>

1. Main code lives in [`Recap2_wrapper.py`](../../../new_modeling_toolkit/Recap/Recap2_wrapper.py)
    1. Using 3.0 input CSVs, the wrapper object (a child classs of `RecapCase`) constructs a system and then uses the
       objects in that system (i.e., `Resource`, `ResourceGroup`) to parse out the inputs used.
2. Most all Recap 2.0 input CSVs are constructed using the following procedure w the `map_inputs` helper function:
    1. System is constructed (only once for all input CSVs)
    2. Input map is loaded in from `> Recap2_wrapper_inputs_mapping` folder; and all Recap 2.0 inputs
       (`column` column) are determined by one of three methods:
        1. (2.1) a 3.0 input is used directly (`attribute` column)
        2. (2.2) a helper function defined in `Recap2wrapper.py` is used for more involved inputs
           (`helper_function` column)
        3. (2.3) a default value is used (`default_value` column)

   Exceptions to this include "outage_distributions.csv", which is copied to Recap 2.0 inputs folder by default to
   create 0/1 outage distribution, and "hydro.csv" which has indvidual rows for each hydro resource, hydro year, and
   month. Budgets and Pmin / Pmax for "hydro.csv" are partially inferred from `kit` hydro resource inputs.

