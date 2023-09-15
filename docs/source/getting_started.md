(getting_started)=
# Getting Started

We want you to feel like a developer: empowered to both understand how `Resolve` works under the hood and contribute 
changes, bug fixes, and new functionality to support the growing `Resolve` and `kit` ecosystem.

## 1. Clone the Repository for Each Project

Clone the [`kit`](https://github.com/e3-/kit) repository. 
In general, we recommend most users use one of the following applications, though advanced users may feel comfortable
using `git` commands directly. 

```{warning}
You will need to create a GitHub account and be added as a member of the E3 organization before you can clone the 
repository.
```

For now, we'll want to `checkout` the `resolve/2023-training` branch.

### Cloning via Pycharm

If you use Pycharm as your IDE, the easiest way to clone the repository is to do so through Pycharm directly. Go to 
"Git" --> "Clone..." and a pop-up window should open. Select "GitHub" on the left-hand side of this window and you 
should see a button to login to GitHub. This should take you to your browser, where you will be prompted to login to 
your GitHub account. This should link your GitHub account to Pycharm permanently. 

Once you are done, return to Pycharm and you should see the window populate with a list of 
available repositories. Select "e3-/kit" and specify the path where you want the repository to live
on your computer. 

### Cloning via GitHub Desktop

If you have GitHub Desktop installed, follow the instructions [here](https://docs.github.com/en/desktop/contributing-and-collaborating-using-github-desktop/adding-and-cloning-repositories/cloning-a-repository-from-github-to-github-desktop)
to clone the repository. 

### Cloning via git CLI

To clone via the git CLI, open the GitHub page for `kit` repository in your broswer. Click the 
green "Code" button and copy the HTTP link to your clipboard. 

```{warning}
You will need to create a Personal Access Token (PAT) in GitHub in order to clone a repository using the git CLI. Follow 
the instructions [here](https://docs.github.com/en/enterprise-server@3.6/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
to create a PAT.   
```

```{image} ./_images/github-clone.png
:alt: Screenshot of GitHub "Clone" button.
:width: 60%
:align: center
```

Once you have the link copied, open your command line shell of choice (Command Prompt or PowerShell on Windows, Terminal 
on Mac) and navigate to the folder in which you want to clone the repository. Then run the following command:

```commandline
git clone paste-the-repository-link-here
```

When prompted, enter the email address associated with your GitHub account as the username and your Personal Access 
Token as the password. 

```{warning}
If you are on a Windows computer, you will need to install [Git for Windows](https://gitforwindows.org/) before you can
use the git CLI. 
```

(setting-up-conda)=
## 2. Setting Up a `conda` Environment

````{hint}
If updating the environment is taking an unusually long time, it can sometimes be easier to [remove the environment](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#removing-an-environment) 
and then set up the environment fresh. This can be done with the following command:
    ```commandline
    conda env remove -n [environment name]
    ```
````

We recommend using the [Anaconda](https://www.continuum.io/downloads) Python distribution and package manager. 
You can also use [Miniconda](https://docs.conda.io/en/latest/miniconda.html), which is a smaller version that only includes `conda` not all the default packages. 
During the installation process, we recommend selecting the "Add Anaconda3 to my PATH environment variable" option
so that you have easy access to the `conda` command from the command line.

```{note}
If you run into any `conda not recognized` or `command not found: conda` messages in the command line in the following steps,
this means that you **did not** add Anaconda to your PATH. You can add either rerun the installer (easiest) or manually
add Anaconda to your PATH (see [these instructions](https://www.geeksforgeeks.org/how-to-setup-anaconda-path-to-environment-variable/) for some help).
```

In order for `conda` to work properly, you can either use the "Anaconda Prompt" application that comes packaged with 
your installation, or you will need to initialize your shell of choice for use. If you use Command Prompt, open a new 
Command Prompt window and enter:

```commandline
conda init cmd.exe
```

If you use Powershell, open a new Powershell window and enter:

```commandline
conda init powershell
 ```
 
Then, close all Powershell windows, and open a new Powershell window using the "Run as 
Administrator" option (right-click on the PowerShell application icon in the Start Menu to find this option). Then, enter the following command: 
 
```commandline
Set-ExecutionPolicy Unrestricted
```

Then, close the Powershell window and open a new one. 

We will use the `conda` command to create an isolated environment for the Resolve to run within, without 
disturbing any other Python packages you may have already installed (see the [`conda` documentation](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html) for more details on conda environments).

To create the `conda` environment, we will use the [`environment.yml`](https://github.com/e3-/kit/blob/main/environment.yml) 
file at the top level of the repository. Open your shell of choice and navigate into your cloned copy of the repository.
Then, run the following command:

-  Create an environment called `new-modeling-toolkit`:
    ```commandline
    conda env create -f environment.yml
    ```

-  Alternatively, if you want to give your environment a customized name (e.g., a project name suffix), do the following:
    ```commandline
    conda env create -f environment.yml -n [desired-environment-name-goes-here] 
    ```

- To activate the environment, set it as the project default in your IDE or use the following command:
    ```
    conda activate kit  # or whatever custom name you gave your environment 
    ```

- If updates are made to the codebase that add new Python package dependencies to the model or change the required 
versions of existing dependencies, you can update your environment with the following command from the same location:

    ```
    conda env update -n new-modeling-toolkit -f environment.yml  # Again, replace with custom name if necessary
    ```
````{hint}
If updating the environment is taking a long time, it can sometimes be easier to remove the environment completely 
and set up the environment fresh. This can be done with the following command: `conda env remove -n [environment name]`
````

```{note}
Developers should use the `environment-dev.yml` file instead of `environment.yml`, which will install several additional 
dependencies (e.g., `pytest`, `sphinx`). See the "Development Guide" section for more details.
```

---
(getting-started/xlwings-setup)=
## 3. Setting Up `xlwings` for Excel User Interfaces

Many of `kit`'s user interfaces are Excel spreadsheets that rely on the [`xlwings`](https://www.xlwings.org) package. 
Using `xlwings` means that the UI will now work with both Windows and macOS versions of Excel (with some minor differences in behavior).

(configure-xlwings-macos)=
### Configuring `xlwings` on macOS

Users using the spreadsheet tools on macOS need to do one more step the first time they set up `kit` 
environment (due to how macOS deals with permissions):
1. Open Terminal
2. Activate the `new-modeling-toolkit` environment
3. Run the command `xlwings runpython install`
4. You should see a prompt from macOS asking you for permission for Terminal to automate Excel. Allow this.

That's it!

## 4. Installing Solvers

### Gurobi

To install the Gurobi solver, follow the instructions in [this Powerpoint.](https://ethreesf.sharepoint.com/:p:/s/Models/EXFqRF-YLhZAi7DX4eOU37IBXgWnI7uKZy5TGFSMxUBRhw?e=We1bOv&nav=eyJzSWQiOjI2MSwiY0lkIjoyODY2NTk2OTM4fQ)
**It is highly recommended that you install Gurobi, as it is substantially faster than CBC.**

### CBC
[CBC](https://github.com/coin-or/Cbc) is a free, open-source solver. 
A Windows executable is included in the `./solvers` subdirectory to allow users to run a test case out-of-the box. 

For macOS and Linux systems, we do not include the corresponding executables (which are different than the Windows one). 
You have two options for installing CBC:
1. Use Anaconda to install CBC in your `kit` conda environment (see {ref}`setting-up-conda`):
```
conda install -c conda-forge coincbc
```
2. Select the corresponding CBC from the AMPL open-source solver download page ([link](https://ampl.com/products/solvers/open-source/)).

### Commercial Solvers

Thanks to the underlying Pyomo package, commercial LP/MIP solvers like [Gurobi](https://www.gurobi.com/), IBM CPLEX, and FICO XPRESS are all supported. 
These commercial solvers are subject to additional costs and licensing for the user. Follow the vendor installation & licensing instructions. 
