# Adding new modules to oQtopus

This guide explains how to add new modules to your oQtopus deployment by editing the YAML configuration file.

## Overview

oQtopus uses a YAML configuration file to define available modules. Each module entry describes the repository, metadata, and assets required for deployment.

## Steps to add a new module

### 1. Locate the YAML configuration

The main configuration file is typically named `default_config.yaml` and is found in the root of your oQtopus installation.

### 2. Edit the YAML file

Open `default_config.yaml` in a text editor. Each module is defined as a dictionary under the `modules` key.

#### Example configuration file

```yaml
modules:
  - name: "TEKSI Wastewater"
    organisation: "teksi"
    repository: "wastewater"
```

### 3. Required fields

Each module entry must include:

- **name**: Human-readable name for the module.
- **organisation**: GitHub organization or user that owns the repository.
- **repository**: The repository name containing the module.

### 4. Save and test

After editing the YAML file, save your changes and restart oQtopus. The new module should appear in the module selection list.
