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

### ModuleConfig reference

::: oqtopus.core.modules_config.ModuleConfig

### Save and test

After editing the file, restart oQtopus. The new module appears in the module selection dropdown.
