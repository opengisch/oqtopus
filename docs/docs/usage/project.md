# Project

The **Project** tab lets you install the QGIS project template shipped with a module release.

## Install a project

1. Make sure a module and version are selected in the **Module Selection** box, and a database is connected.
2. Switch to the **Project** tab.
3. Click **Install template project** and choose a destination directory.

oQtopus copies all project files (`.qgs` / `.qgz` and accompanying files) from the module package into the selected directory.

For `.qgs` files, oQtopus automatically rewrites the `service='…'` entries to point to the currently selected PG service, so the project is ready to open.

!!! note "Translated projects"

    If your QGIS locale is set and a matching translated project file exists
    (e.g. `module_name_fr_CH.qgs`), oQtopus installs the translated version.

## See changelog

Click **See Changelog** to open the module release page on GitHub in your browser.

!!! info "Project asset"

    The project tab is only enabled when the selected module release contains an
    asset labeled `oqtopus.project`. See [Adding Modules](../adding_modules.md)
    for details on how to structure a module repository.
