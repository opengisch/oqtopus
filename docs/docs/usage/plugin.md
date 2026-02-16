# Plugin

The **Plugin** tab lets you install or export the companion QGIS plugin shipped with a module release.

## Install the plugin

Click **Install** to install the plugin directly into the running QGIS profile.

!!! note

    Direct plugin installation is only available when running oQtopus from within QGIS.
    The dialog shows the current QGIS profile name and the currently installed plugin version (if any).

## Export the plugin ZIP

Click **Copy ZIP to directory** to save the plugin archive to a directory of your choice.
You can then install it manually in QGIS:

1. Open QGIS.
2. Go to **Extensions → Manage and Install Plugins → Install from ZIP**.
3. Browse to the exported ZIP file and install.

## See changelog

Click **See Changelog** to open the module release page on GitHub in your browser.

!!! info "Plugin asset"

    The plugin tab is only enabled when the selected module release contains an
    asset labeled `oqtopus.plugin`. See [Adding Modules](../adding_modules.md)
    for details on how to structure a module repository.
