# 👨🏼‍🏭 `Kit` Quick Start Guide

The following set-up instructions should be followed each time you are setting up a new Recap or Resolve project (or any
model that uses the `kit` framework).

## One-time Setup

This setup guide assumes you have already set up Python, Anaconda, and have a Github account.

Each time you set up a new AWS instance you will have to set up Python and Anaconda for your account on that machine.
If you need help, please contact Pete at pete.ngai@ethree.com.

Follow
this [🐍 E3 Python set up guide](https://ethreesf.sharepoint.com/sites/Training/_layouts/15/Doc.aspx?sourcedoc={8e5fb17b-013c-4eb4-9b4e-e868e3530c5e}&action=edit&wd=target%28Technical%20Skills%20Training%2FPython.one%7C916c3a04-a4b3-4112-9e7f-f2f503e5b87c%2FGetting%20Started%20with%20Python%20%40%20E3%7Ce937bdef-862c-4a26-9aa5-c2ebb709f86a%2F%29&wdorigin=703)
if do not yet have these set up.

### Setup Steps

The core Resolve and Recap codebases are written in Python and hosted on GitHub as part of the E3 New Modeling
Toolkit (`kit`) framework. Follow the steps below to get a copy of the codebase and set up the model in your project
folder:

::::{dropdown} 0. {bdg-info-line}`Optional` Set up a project-specific AWS instance
:class-title: sd-fs-6 The best practice to run `kit` projects is to deploy it on an AWS instance. Refer to
{octicon}`link-external;1em;sd-text-info`[this guide](https://ethreesf.sharepoint.com/sites/E3Office/Shared%20Documents/Admin%20and%20IT/AWS%20EC2%20Instance%20FAQs.docx?web=1)
and talk to Roderick for how to set up an AWS instance for your project.

After that, place your project files in the shared drive across AWS instances (FSx) – instructions in the same guide
above.

<font color='#034E6E'>*Note that you don’t need an AWS instance for running the quick start examples in this user
guide.*</font>
::::

:::{dropdown} 1. 😸🔨 Pulling `kit` from GitHub
:class-title: sd-fs-6 Navigate to {octicon}`link-external;1em;sd-text-info`[kit repository](https://github.com/e3-/kit).
Click the green “Code” tab on top of the repository, then copy the link presented under "Clone" (it should be the same
URL you are on).'

Navigate to your project folder and open a command line by typing `cmd` in the navigation bar. Then clone the repository
with the command `git clone [repo_url_you_copied]`.

   ```{note}
   Note that kit is a private repository, so you will need a certificated GitHub account to access and clone it.  
   To authenticate your account and link with Okta, please contact Roderick for help.
   ```

:::

:::{dropdown} 2. 🌱🔨 Setting Up the Project's Anaconda Environment
:class-title: sd-fs-6 After cloning the repository, use `conda` to set up a standard Python environment for `kit`.

We will use the `conda` command to create an isolated environment for `kit` to run within, without disturbing any other
Python packages you may have already installed (see
the [`conda` documentation](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html)
for more details on conda environments).

- Make sure you have downloaded a version of [Anaconda](https://www.anaconda.com/products/individual)
  or [Miniconda](https://docs.conda.io/projects/miniconda/en/latest/miniconda-install.html) on your computer or on the
  AWS instance. Refer to
  {octicon}`link-external;1em;sd-text-info`[this link](https://ethreesf.sharepoint.com/sites/Training/SiteAssets/Training%20Notebook/Technical%20Skills%20Training/Python.one#Getting%20Started%20with%20Python%20@%20E3&section-id=%7B916C3A04-A4B3-4112-9E7F-F2F503E5B87C%7D&page-id=%7BE937BDEF-862C-4A26-9AA5-C2EBB709F86A%7D&end)
  for Anaconda installation guide.
- Now install the environment by opening a Command Prompt window in the `“kit”` directory by typing `cmd` in the address
  bar and use the following command: `conda env create -f environment.yml --n [your project name]` (
  where [your project name] is unique and does not include any spaces, e.g., `nve-Recap-kit`).

```{note}
Developers should use the `environment-dev.yml` file instead of `environment.yml`, which will install several additional 
dependencies (e.g., `pytest`, `sphinx`). See the "Development Guide" section for more details.
```

:::

:::{dropdown} 3. 🔑🔨Getting a Gurobi license
:class-title: sd-fs-6 Download a Gurobi license file (gurobi.lic) following
{octicon}`link-external;1em;sd-text-info`[this guide](https://ethreesf.sharepoint.com/:p:/r/sites/Models/Shared%20Documents/General/E3%20Gurobi%20Instant%20Cloud.pptx?d=w5f446a712e9840168bb0d7e1e394dfb2&csf=1&web=1&e=gx4xiU),
then copy the license to your master `kit` directory.

<font color='#034E6E'>*A new Gurobi pool (and license) should be used for each new project.*</font>
:::

:::{dropdown} 4. 💻🔨 Configuring `xlwings` in the UI
:class-title: sd-fs-6 

Aside from the codebase, `kit` has Excel-based User Interfaces (UIs) for users to (1) create
correctly formatted input & settings files and (2) run the model code without needing to directly interact with a
command line.

These UIs rely on the [`xlwings`](https://www.xlwings.org) package.

Open the appropriate UI (`./Recap-Resolve Scenario Tool.xlsm` or `./Resolve Scenario Tool.xlsm`) and navigate
to `“Cover & Configuration”` tab. You will need to set the correct `Python Path` and `Data Folder`.

The `Data Folder` is the full path to the `kit\data` folder (example provided in UI).

For the `Python Path` follow the instructions below.

- **For Windows:** Users will need to set the `Python Path` (you can use the `where python` command in Command Prompt,
  with your project conda environment activated, to get this path)
  and Data Folder. Examples provided in the UI.
    - If you get an error that says "Your `conda` version seems too old...", fill in the `Interpreter_Win`
      cell. You can find the the correct interpreter by activating `kit` environment, then using the
      `where python` command in Command Prompt. The path should look something
      like `C:\Users\[username]\Anaconda3\envs\kit\python.exe`.
- **For macOS:** Users will need to set the `Interpreter_Mac`, which is similar to `Conda Path` but the path to the
  Python executable within the corresponding conda environment. You can find the the correct interpreter by activating
  the
  `kit` environment, then using the `which python` command in Terminal; this should give you a path that looks something
  like `/Users/[username]/.../anaconda3/envs/kit/bin/python`
    - Users will also be prompted the first time they try to run any of the `xlwings`-based buttons in the Scenario Tool
      to allow xlwings to control your system. You must allow control for xlwings to be able to read/write from the
      Scenario Tool.

:::

