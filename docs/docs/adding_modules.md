# Adding new modules to oQtopus

This guide explains how to add new modules to your oQtopus deployment by editing the YAML configuration file.

## Overview

oQtopus uses a YAML configuration file to define available modules. Each module entry describes the name and repository required for deployment.

## Steps to add a new module

### 1. Locate the YAML configuration

The main configuration file is typically named `default_config.yaml` and is found in the root of your oQtopus installation.

!!! warning

    At the moment the path to `default_config.yaml` is hard coded in Oqtopus.


### 2. Edit the YAML file

Open `default_config.yaml` in a text editor. Each module is defined as a dictionary under the `modules` key.

#### Example configuration file

```yaml
modules:
  - name: TEKSI Wastewater
    id: tww
    organisation: teksi
    repository: wastewater
```

### 3. Required fields

Each module entry must include:

- **name**: Human-readable name for the module.
- **organisation**: GitHub organization or user that owns the repository.
- **repository**: The repository name containing the module.

### 4. Save and test

After editing the YAML file, save your changes and restart oQtopus. The new module should appear in the module selection list.


## Module structure

oQtopus assumes a certain structure of the module/repository.

### Datamodel

To setup/update the database structure, oQtopus downloads the source
code from the configured module repository and looks for a pum configuration
file at this path (from the repository root): `datamodel/.pum.yaml`.
Please look at the PUM <a href="https://opengisch.github.io/pum/" target="_blank">documentation</a>
 for more information about the
configuration file.

### Project

oQtopus search in the Github release for an asset labeled `oqtopus.project`. The asset is expected to be a
ZIP archive containing a .qgs or .qgz QGIS project file.


### Plugin

oQtopus search in the Github release for an asset labeled `oqtopus.plugin`. The asset is expected to be the ZIP archive of the QGIS plugin, ready to be installed.
