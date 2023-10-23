# 3. Define Case Settings

## Case Settings

### Input Scenarios

### Representative Period Settings

### Financial Settings & Modeled Years

## Custom Constraints

Custom constraints allow users to customize the functionality of `Resolve` by adding additional constraints 
without needing to change the code. These are defined on the "Custom Constraints" tab and saved to 
`./data/settings/resolve/[case name]/custom_constraints/`

:::{admonition} 2023 CPUC IRP {octicon}`zap`
For the CPUC IRP, custom constraints are used for various custom functionality:
- Resource deliverability (i.e., CAISO FCDS/EO designation) and accompanying CAISO transmission upgrades
- Connecting disaggregated build variables to aggregate operational resources (which allows `Resolve` to make granular
  investment decisions while reducing the model size needed to represent operations. 
- Group-level constraints (e.g., "Resolve must build 15 GW of offshore wind by 2045" but can select amongst the 4 candidate OSW resources.)
:::

To create custom constraints, first create a "Custom Constraint Group" name of your choosing. These groups are toggled 
on/off in the active case settings together, so group custom constraints accordingly.

Within each custom constraint group, 

## Timeseries Clustering

{bdg-warning-line}`Advanced Topic` 

Users who want to create a new set of sampled days can do so using the included 
Jupyter notebook in `./notebooks/cluster.py`. This is a [Jupytext file](https://jupytext.readthedocs.io). 
To open this notebook:
1. Open a Command Prompt or Terminal and navigate to the `./notebooks` subfolder
2. Activate the `resolve-env` environment using `conda activate resolve-env`
3. Open the notebook using the following commands:
  ```
  jupytext-config set-default-viewer
  jupyter lab cluster.py
  ```
4. Run the cells and follow the prompts (for Jupyter notebook basics, users can [start here](https://realpython.com/jupyter-notebook-introduction/#running-cells)).