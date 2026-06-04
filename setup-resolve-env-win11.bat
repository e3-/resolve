@echo off
setlocal enabledelayedexpansion

echo ========================================
echo RESOLVE Conda Environment Setup Script
echo ========================================
echo.
echo This script works around Windows path length limitations by:
echo   1. Creating short temp directory (C:\tmp)
echo   2. Mapping project to short drive (R:)
echo   3. Mapping conda installation to short drive (M:)
echo   4. Creating conda environment with short paths
echo.

:: Check if running with admin privileges (recommended for subst)
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo WARNING: Not running as administrator. Drive mapping may fail. But you can still proceed with no risk of harm.
    echo If a second attempt is needed, right-click this script and select "Run as administrator"
    echo.
    pause
)

:: Create or verify C:\tmp exists
if not exist "C:\tmp" (
    echo Creating C:\tmp directory...
    mkdir "C:\tmp"
    if !errorLevel! neq 0 (
        echo ERROR: Failed to create C:\tmp
        exit /b 1
    )
) else (
    echo C:\tmp directory already exists
)
echo.

:: Find conda installation path
echo Detecting conda installation...
where conda >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: conda command not found in PATH
    echo Please ensure conda/miniconda is installed and in your PATH
    exit /b 1
)

:: Get conda base path
for /f "tokens=*" %%i in ('conda info --base 2^>nul') do set CONDA_BASE=%%i
if "!CONDA_BASE!"=="" (
    echo ERROR: Could not determine conda base directory
    exit /b 1
)
echo Found conda at: !CONDA_BASE!
echo.

:: Check if M: is already mapped
if exist M:\ (
    echo WARNING: Drive M: is already mapped
    echo Current M: mapping:
    subst M:
    echo.
    set /p REMAP_M="Remap M: to conda path? (y/n): "
    if /i "!REMAP_M!"=="y" (
        subst M: /d >nul 2>&1
        echo Unmapped M:
    ) else (
        echo Using existing M: mapping
        goto :skip_m_map
    )
)

:: Map M: to conda base
echo Mapping M: to !CONDA_BASE!...
subst M: "!CONDA_BASE!"
if !errorLevel! neq 0 (
    echo ERROR: Failed to create M: drive mapping
    exit /b 1
)
echo.

:skip_m_map

:: Check if R: is already mapped
if exist R:\ (
    echo WARNING: Drive R: is already mapped
    echo Current R: mapping:
    subst R:
    echo.
    set /p REMAP_R="Remap R: to project path? (y/n): "
    if /i "!REMAP_R!"=="y" (
        subst R: /d >nul 2>&1
        echo Unmapped R:
    ) else (
        echo Using existing R: mapping
        goto :skip_r_map
    )
)

:: Map R: to current project directory
echo Mapping R: to %~dp0...
subst R: "%~dp0"
if !errorLevel! neq 0 (
    echo ERROR: Failed to create R: drive mapping
    exit /b 1
)
echo.

:skip_r_map

:: Set short temp paths
echo Setting temporary directories to C:\tmp...
set TEMP=C:\tmp
set TMP=C:\tmp
set TMPDIR=C:\tmp
echo.

:: Change to R: drive
echo Changing to project directory (R:\)...
cd /d R:\
if !errorLevel! neq 0 (
    echo ERROR: Failed to change to R: drive
    exit /b 1
)
echo.

:: Display environment file info
echo Environment file: R:\environment.yml
if exist R:\environment.yml (
    for /f "tokens=2" %%a in ('findstr /b "name:" R:\environment.yml') do set ENV_NAME=%%a
    echo Environment name: !ENV_NAME!
) else (
    echo ERROR: environment.yml not found at R:\environment.yml
    exit /b 1
)
echo.

:: Confirm before proceeding
echo Ready to create conda environment with short paths:
echo   - TEMP: !TEMP!
echo   - Project: R:\ (mapped to %~dp0)
echo   - Conda: M:\ (mapped to !CONDA_BASE!)
echo.
set /p CONFIRM="Proceed with environment creation? (y/n): "
if /i not "!CONFIRM!"=="y" (
    echo Cancelled by user
    goto :cleanup_drives
)
echo.

:: Create conda environment
echo ========================================
echo Creating conda environment...
echo ========================================
echo.

call conda env create -f R:\environment.yml
if !errorLevel! neq 0 (
    echo.
    echo ========================================
    echo ERROR: Environment creation failed
    echo ========================================
    echo.
    echo If you still encounter path length issues, try:
    echo   1. Moving conda installation to C:\conda
    echo   2. Using even shorter environment name in environment.yml
    echo   3. Consider using Docker instead
    echo.
    goto :cleanup_drives
)

echo.
echo ========================================
echo SUCCESS: Environment created!
echo ========================================
echo.
echo To activate the environment:
echo   conda activate !ENV_NAME!
echo.
echo To remove this environment later, run:
echo   conda env remove -n !ENV_NAME!
echo.

:cleanup_drives
echo.
echo ========================================
echo Drive Mapping Information
echo ========================================
echo.
echo The following drive mappings are active:
echo   M: -^> Conda installation
echo   R: -^> Project directory
echo.
echo These mappings will persist until:
echo   - You restart your computer
echo   - You manually remove them with: subst M: /d
echo.
echo You can keep these mappings for future use or remove them now.
set /p REMOVE_MAPS="Remove drive mappings now? (y/n): "
if /i "!REMOVE_MAPS!"=="y" (
    echo Removing drive mappings...
    cd /d %~dp0
    subst R: /d >nul 2>&1
    subst M: /d >nul 2>&1
    echo Drive mappings removed
) else (
    echo Drive mappings kept for future use
)
echo.

echo Press any key to exit...
pause >nul
endlocal
