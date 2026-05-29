# Conda Environment Setup for Windows Path Length Issues

This directory contains scripts to work around Windows path length limitations when creating conda environments.
The scripts are provided as a fallback tool in case of difficulty creating conda environments.

Normally RESOLVE Analysts should not need to use this script - reach out to the E3 Tech Team for assistance.

## Problem

Windows has a maximum path length of 260 characters by default (LongPathsEnabled=0). Building the RESOLVE conda environment with `conda env create -f environment.yml` fails because:
- Long user profile paths (e.g., `C:\Users\myname\Documents\GitHub\resolve-e3`)
- Deep conda package paths during installation
- Python pip editable install creating deep wheel build directories

## Alternative Solutions

1. Software designers remove any optional packages from RESOLVE that are impacting the build depth
1. Modify the compute environment from LongPathsEnabled=0 to LongPathsEnabled=1 (Computer\HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem:LongPathsEnabled)
1. Use these provided scripts that employ drive letter mapping (`subst`) to create shorter paths that _may_ (or may not) bypass Windows path length limitations.

## Prerequisites (for `subst` strategy)

- Conda/Miniconda already installed and in PATH
- Administrator privileges _may_ be needed (recommended for drive mapping)

## Usage

### Creating the Environment

1. **Double-click `setup-resolve-env-win11.bat`** <br>
   Or Right-click `setup-resolve-env-win11.bat` and select "Run as administrator" <br>
   Or from cmd or PowerShell:
   ```cmd
   setup-resolve-env-win11.bat
   ```

2. The script will:
   - Create `C:\tmp` for short temporary paths
   - Map `M:` to your conda installation directory
   - Map `R:` to this project directory
   - Create the conda environment with short paths
   - Prompt you whether to keep the drive mappings

3. Follow the prompts to confirm environment creation

### Activating the Environment

After creation, activate normally:
```cmd
conda activate resolve
```

### Removing the Environment

Remove normally:
```cmd
conda env remove -n resolve
```

### Removing Drive Mappings

If you kept the drive mappings and want to remove them later:
```cmd
subst M: /d
subst R: /d
```

To view current mappings:
```cmd
subst
```

## What the Script Does

### setup-resolve-env-win11.bat
- Detects conda installation path
- Creates short temp directory (`C:\tmp`)
- Maps drives to short paths:
  - `M:` → Conda installation directory
  - `R:` → Project directory
- Sets environment variables for short temp paths
- Runs `conda env create -f environment.yml`
- Provides option to clean up drive mappings

## Drive Mappings Persistence

Drive mappings created with `subst` persist until:
- System restart
- Manual removal with `subst X: /d`

You can keep them for convenience when working with this project.

## Troubleshooting

### "Not running as administrator" warning
- Right-click the script and select "Run as administrator"
- Or open cmd as administrator and run the script

### Drive letter already in use
- The script will detect this and ask if you want to remap
- Choose 'n' to keep existing mapping if it's correct
- Choose 'y' to remap to the new path

### Environment creation still fails
If you still encounter path issues:
1. Move your conda installation to `C:\conda` (shorter path)
2. Shorten the environment name in `environment.yml`
3. Consider using Docker instead (see `docker/` directory)

### "conda: command not found"
- Ensure conda is installed and in your PATH
- Restart your terminal after conda installation
- Try: `C:\Users\<username>\miniconda3\Scripts\activate.bat`

## Notes

- Drive mappings are session-persistent but survive across terminal windows
- The `C:\tmp` directory will remain after script execution (safe to delete)
- You can customize drive letters by editing the scripts if `M:` or `R:` conflict with existing drives
