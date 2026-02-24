# Adding Modules

This guide explains how to add new modules to oQtopus and how to structure a module repository.

## Module configuration

oQtopus uses a YAML configuration file (`default_config.yaml`) to define the list of available modules.

### Locate the configuration

The configuration file is at the root of the oQtopus package directory:

- **QGIS plugin**: inside the installed plugin folder (e.g. `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/oqtopus/default_config.yaml`).
- **Standalone**: inside the pip-installed package directory.

### Add a module entry

Open `default_config.yaml` and add an entry under the `modules` key:

```yaml
modules:
  - name: TEKSI Wastewater
    id: tww
    organisation: teksi
    repository: wastewater
```

### Required fields

Each module entry must include:

| Field            | Description                                                    |
|------------------|----------------------------------------------------------------|
| `name`           | Human-readable name shown in the module dropdown.              |
| `id`             | Short unique identifier for the module.                        |
| `organisation`   | GitHub organization or user that owns the repository.          |
| `repository`     | GitHub repository name containing the module.                  |

### ModuleConfig reference

::: oqtopus.core.modules_config.ModuleConfig

### Save and test

After editing the file, restart oQtopus. The new module appears in the module selection dropdown.

## Module repository structure

oQtopus expects a specific structure in the module's GitHub repository.

### Datamodel

oQtopus downloads the source code from the configured repository and looks for a PUM configuration file at:

```
datamodel/.pum.yaml
```

This file defines the database schema, migration scripts, parameters, roles and more.
See the [PUM documentation](https://opengisch.github.io/pum/) for details.

### Project (optional)

oQtopus looks in the GitHub release assets for an asset labeled **`oqtopus.project`**.
The asset should be a ZIP archive containing a `.qgs` or `.qgz` QGIS project file (and any accompanying files).

### Plugin (optional)

oQtopus looks in the GitHub release assets for an asset labeled **`oqtopus.plugin`**.
The asset should be the ZIP archive of the QGIS plugin, ready to be installed.
