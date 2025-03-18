# CI/CD for HunchBank Auto Email Support

This project uses GitHub Actions to automatically build and package the application for different platforms when a new version is released.

## How It Works

The CI/CD pipeline will:

1. Build Python package files (wheel and source distribution)
2. Create a Windows zip package with installation script
3. Create a Unix (macOS/Linux) zip package with installation script
4. Upload all artifacts as GitHub release assets

## Triggering a Build

There are two ways to trigger the build workflow:

### 1. Create a Version Tag (Recommended)

To create a new release:

```bash
# Tag a new version
git tag -a v1.0.0 -m "Release version 1.0.0"

# Push the tag to GitHub
git push origin v1.0.0
```

This will automatically trigger the workflow and create a GitHub release with all the package assets.

### 2. Manual Trigger

You can also manually trigger the workflow from the GitHub Actions tab:

1. Go to the GitHub repository
2. Click on the "Actions" tab
3. Select the "Build and Package" workflow
4. Click "Run workflow" button
5. Choose the branch to build from
6. Click "Run workflow"

## Package Contents

The workflow creates three types of packages:

### 1. Python Packages

- `.whl` file for pip installation
- `.tar.gz` source distribution

### 2. Windows Package (`hunchbank-windows.zip`)

Contains:
- All source code files
- Windows installation script (`install_and_run.bat`)
- PowerShell script to create desktop shortcut
- Windows-specific README

### 3. Unix Package (`hunchbank-unix.zip`)

Contains:
- All source code files
- Unix installation script (`install_and_run.sh`)
- Linux desktop file for application menu
- Unix-specific README for macOS and Linux

## Installation Instructions

### For End Users

1. Download the appropriate package for your operating system from the latest GitHub release
2. Extract the zip file
3. Follow the platform-specific instructions in the README

### For Developers (Using Python Package)

```bash
# Install from PyPI (if published)
pip install hunchbank-auto-email-support

# Or install from wheel file
pip install hunchbank_auto_email_support-1.0.0-py3-none-any.whl
```

## Customizing the Build

To customize the build process, edit the workflow file at `.github/workflows/build.yml`.

## Requirements for Building

The CI/CD pipeline requires:
- GitHub repository with Actions enabled
- Python 3.11 (provided by the workflow)
- Valid setup.py file for packaging