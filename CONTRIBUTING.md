# Contributing
This document covers the information needed for somebody to be able to contribute code to RESOLVE.

## Development setup

To set up your environment for development, please follow these steps:

1. Clone the repository
   ```bash
   git clone git@github.com:e3-/resolve-e3.git
   cd kit
   ```

2. Create and activate the conda environment:
   ```bash
   conda env create -f environment-dev.yml
   conda activate resolve-dev
   ```

3. After cloning the repository and creating your conda environment (see the README.md for more details), you'll need to set up pre-commit:
   ```bash
   pre-commit install
   ```
This will run certain checks on the code prior to committing changes in git.


## Running Tests
Tests are written using pytest and can be run with:
```bash
pytest
```

## Documentation
The project documentation is built using Sphinx and is hosted on [ReadTheDocs](https://docs.ethree.com/projects/kit/en/main/). You will need to sign in with your *Willdan* (not E3) SSO id.

To build the documentation locally:
```bash
cd docs
make html
```
