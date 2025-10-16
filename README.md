<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./docs/source/_static/resolve-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./docs/source/_static/resolve-light.svg">
  <img alt="Hashnode logo" src="./docs/source/_static/resolve-light.svg" height="120">
</picture>


# RESOLVE
RESOLVE  is an electricity resource planning model that identifies optimal long-term electric generation and 
transmission investments subject to reliability, policy, and technical constraints. It is developed and maintained by
[Energy and Environmental Economics, Inc. (E3)](https://www.ethree.com/tools/resolve/).

The public documentation for RESOLVE can be found at the [RESOLVE documentation on Read the Docs](https://docs.ethree.com/projects/resolve/en/latest/).

The public documentation contains instructions for how to install RESOLVE (see especially [Getting Started & Installation](https://docs.ethree.com/projects/resolve/en/latest/getting_started/index.html) and [Initial Model Set-up](https://docs.ethree.com/projects/resolve/en/latest/Initial%20Model%20Set-Up/index.html)). After installing, you can verify that you have configured RESOLVE correctly by running a test case:

```bash
python new_modeling_toolkit/resolve/run_opt.py "Full_Training_Case" --data-folder="data-training”
```
