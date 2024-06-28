# All about environments

Python environments for this project should be thought of as isolated computational spaces 
that will have the necessary configurations needed for you to run the specific project or model - which in this case is `Resolve`

Environments help in setting up packages, dependencies, libraries etc by running a simpe command and do not require much computational 
background and knowledge - thus enabling the usage of the product for a wide array of stakeholders. 

There are many softwares that help in creating, activating and maintaining environments - one of which is `Anaconda`

We recommend using the [Anaconda](https://www.continuum.io/downloads) Python distribution and package manager. 
During the installation process, we recommend selecting the "Add Anaconda3 to my `PATH` environment variable" option
so that you have easy access to the `conda` command from the command line.

```{tip}
If you run into any `conda not recognized` or `command not found: conda` messages in the command line in the following steps,
this means that you **did not** add Anaconda to your PATH. You can add either rerun the installer (easiest) or manually
add Anaconda to your PATH (see [these instructions](https://www.geeksforgeeks.org/how-to-setup-anaconda-path-to-environment-variable/) for some help).
```

## Initial `conda` Set-up

In order for `conda` to work properly, you will need to initialize your "shell" (command line, e.g., Command Prompt). 

:::::{dropdown} Windows

````{dropdown} Option 1: Using Command Prompt
If you use Command Prompt, open a new Command Prompt window and enter:

```
conda init cmd.exe
```
````

````{dropdown} Option 2: Using PowerShell
If you use PowerShell, open a new PowerShell window and enter:

```
conda init PowerShell
```
 
Then, close all PowerShell windows, and open a new PowerShell window using the "Run as 
Administrator" option (right-click on the PowerShell application icon in the Start Menu to find this option). Then, enter the following command: 
 
```
Set-ExecutionPolicy Unrestricted
```

Then, close the PowerShell window and open a new one. 
````

:::::

````{dropdown} macOS Terminal
Since macOS Catalina (10.15), the default "shell" program is `zsh`. These instructions assume you're on a recent version of macOS. 
Open Terminal and use the following command:  

```
conda init zsh
```
Earlier versions of macOS use `bash`, so replace `zsh` in the command above with `bash`.

````

----

## Creating Environments 
Once you have `Anaconda` set-up and have the necessary `Resolve` files and folders you are ready
to create environments.

We will use the `conda` command to create an isolated environment for the Resolve to run within, without 
disturbing any other Python packages you may have already installed (see the [`conda` documentation](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html) for more details on conda environments).

To create the `conda` environment, we will use the [`environment.yml`](https://github.com/e3-/kit/blob/main/environment.yml) 
file at the top level of the repository. Open your shell of choice and navigate into your cloned copy of the repository.
Then, run the following command:

-  Create an environment called `resolve-env`:
    ```bash
    conda env create -f environment.yml
    ```
- In general it is best practice to name your environment for better tractability. That can be as follows:
- 
     ```bash
    conda env create -f environment.yml --name your-environment-name 
    ```

---

## Activating Environments 


- To activate the environment, set it as the project default in your IDE or use the following command:
    ```bash
    conda activate resolve-env 
    ```
- To activate the specific named environment, use the following command:
- 
     ```bash
    conda activate your-environment-name
    ```

---

## Maintaining Environments (Advanced use cases)

    This will be specific to only some use cases 