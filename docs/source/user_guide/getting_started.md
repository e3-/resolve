(getting_started)=
# Getting Started

We want you to feel like a developer: empowered to both understand how `Resolve` works under the hood and contribute 
changes, bug fixes, and new functionality to support the growing `Resolve` and `new-modeling-toolkit` ecosystem.

## 1. Clone the Repository

Clone the [`new-modeling-toolkit`](https://github.com/e3-/new-modeling-toolkit) repository. 
In general, we recommend most users use one of the following applications, though advanced users may feel comfortable
using `git` commands directly, 

### Cloning via GitHub Desktop

### Cloning via Pycharm

### Cloning via Visual Studio Code

(setting-up-conda)=
## 2. Setting Up a `conda` Environment

We recommend using the [Anaconda](https://www.continuum.io/downloads) Python distribution and package manager. 
You can also use [Miniconda](https://docs.conda.io/en/latest/miniconda.html), which is a smaller version that only includes `conda` not all the default packages. 
During the installation process, we recommend selecting the "Add Anaconda2 to my PATH environment variable" option
so that we have easy access to the `conda` command from the command line.

```{note}
If you run into any `conda not recognized` or `command not found: conda` messages in the command line in the following steps,
this means that you **did not** add Anaconda to your PATH. You can add either rerun the installer (easiest) or manually
add Anaconda to your PATH (see [these instructions](https://www.geeksforgeeks.org/how-to-setup-anaconda-path-to-environment-variable/) for some help).
```

We will use the `conda` command to create an isolated environment for the Resolve to run within, without 
disturbing any other Python packages you may have already installed (see the [`conda` documentation](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html) for more details on conda environments).

To create the `conda` environment, we will use the [`environment.yml`](https://github.com/e3-/new-modeling-toolkit/blob/main/environment.yml) file at the top level of the repository. 
Use the following command to create the `conda` environment

```
conda env update -f environment.yml
```

```{note}
Developers should use the `environment-dev.yml` file instead of `environment.yml`, which will install several additional 
dependencies (e.g., `pytest`, `sphinx`). See the "Development Guide" section for more details.
```


To activate the environment, set it as the project default in your IDE or use the following command:
```
conda activate new-modeling-toolkit
```

---
(getting-started/xlwings-setup)=
## 3. Setting Up `xlwings` for Excel User Interfaces

Many of the `new-modeling-toolkit`'s user interfaces are Excel spreadsheets that rely on the [`xlwings`](https://www.xlwings.org) package. 
Using `xlwings` means that the UI will now work with both Windows and macOS versions of Excel (with some minor differences in behavior). 

As `xlwings` is a new dependency, please make sure to update your `new-modeling-toolkit` conda environment using the 
following command from the top-level directory (see {ref}`setting-up-conda` for a refresher on `conda`):

```
conda env update -f environment.yml
```

```{hint}
If updating the environment is taking an unusually long time, it can sometimes be easier to [remove the environment](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#removing-an-environment) 
and then set up the environment fresh.
```

(configure-xlwings-macos)=
### Configuring `xlwings` on macOS

Users using the spreadsheet tools on macOS need to do one more step the first time they set up the `new-modeling-toolkit` 
environment (due to how macOS deals with permissions):
1. Open Terminal
2. Activate the `new-modeling-toolkit` environment
3. Run the command `xlwings runpython install`
4. You should see a prompt from macOS asking you for permission for Terminal to automate Excel. Allow this.

That's it!


## 4. Installing Solvers

### CBC
[CBC](https://github.com/coin-or/Cbc) is a free, open-source solver. 
A Windows executable is included in the `./solvers` subdirectory to allow users to run a test case out-of-the box. 

For macOS and Linux systems, we do not include the corresponding executables (which are different than the Windows one). 
You have two options for installing CBC:
1. Use Anaconda to install CBC in your `new-modeling-toolkit` conda environment (see {ref}`setting-up-conda`):
```
conda install -c conda-forge coincbc
```
2. Select the corresponding CBC from the AMPL open-source solver download page ([link](https://ampl.com/products/solvers/open-source/)).

### Commercial Solvers

Thanks to the underlying Pyomo package, commercial LP/MIP solvers like [Gurobi](https://www.gurobi.com/), IBM CPLEX, and FICO XPRESS are all supported. 
These commercial solvers are subject to additional costs and licensing for the user. Follow the vendor installation & licensing instructions. 
