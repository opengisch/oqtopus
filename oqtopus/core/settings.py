from qgis.PyQt.QtCore import QSettings

try:
    from qgis.core import (
        QgsSettingsEntryBool,
        QgsSettingsEntryString,
        QgsSettingsTree,
    )

    HAS_QGS_SETTINGS = True
except ImportError:
    HAS_QGS_SETTINGS = False

PLUGIN_NAME = "oqtopus"


# ---------------------------------------------------------------------------
# Thin QSettings wrappers that expose the same .value() / .setValue() API
# as QgsSettingsEntry* so callers don't need to know the backend.
# ---------------------------------------------------------------------------


class _QSettingsEntryString:
    """QSettings-backed string setting with the same API as QgsSettingsEntryString."""

    def __init__(self, key: str, default: str = ""):
        self._key = f"{PLUGIN_NAME}/{key}"
        self._default = default

    def value(self, **_kwargs) -> str:
        return QSettings().value(self._key, self._default, type=str)

    def setValue(self, value: str, **_kwargs) -> None:
        QSettings().setValue(self._key, value)


class _QSettingsEntryBool:
    """QSettings-backed bool setting with the same API as QgsSettingsEntryBool."""

    def __init__(self, key: str, default: bool = False):
        self._key = f"{PLUGIN_NAME}/{key}"
        self._default = default

    def value(self, **_kwargs) -> bool:
        return QSettings().value(self._key, self._default, type=bool)

    def setValue(self, value: bool, **_kwargs) -> None:
        QSettings().setValue(self._key, value)


class Settings:
    """Singleton holding all oQtopus settings.

    When running inside QGIS, settings are registered via
    ``QgsSettingsTree`` / ``QgsSettingsEntry*`` so they appear in the
    QGIS settings infrastructure.  In standalone mode the class falls
    back to plain ``QSettings`` wrappers that expose the same
    ``.value()`` / ``.setValue()`` API.

    Usage::

        from oqtopus.core.settings import Settings

        token = Settings().github_token.value()
        Settings().github_token.setValue("ghp_…")

    The QGIS-only ``installed_project_path`` setting is ``None`` in
    standalone mode.  It requires a ``dynamicKeyPartList``::

        Settings().installed_project_path.setValue(
            path, dynamicKeyPartList=[module_id, version]
        )
    """

    instance = None

    def __new__(cls):
        if cls.instance is not None:
            return cls.instance

        cls.instance = super().__new__(cls)

        if HAS_QGS_SETTINGS:
            settings_node = QgsSettingsTree.createPluginTreeNode(pluginName=PLUGIN_NAME)

            cls.github_token = QgsSettingsEntryString(
                "github-token",
                settings_node,
                "",
                "GitHub personal access token for API authentication",
            )
            cls.allow_multiple_modules = QgsSettingsEntryBool(
                "allow-multiple-modules",
                settings_node,
                False,
                "Allow installing multiple modules simultaneously",
            )
            cls.show_experimental_modules = QgsSettingsEntryBool(
                "show-experimental-modules",
                settings_node,
                False,
                "Show experimental module versions in the list",
            )
            cls.log_show_datetime = QgsSettingsEntryBool(
                "log-show-datetime",
                settings_node,
                True,
                "Show the date/time column in the log view",
            )
            cls.log_show_level = QgsSettingsEntryBool(
                "log-show-level",
                settings_node,
                True,
                "Show the log-level column in the log view",
            )
            cls.log_show_module = QgsSettingsEntryBool(
                "log-show-module",
                settings_node,
                True,
                "Show the module column in the log view",
            )
            cls.show_logs = QgsSettingsEntryBool(
                "show-logs",
                settings_node,
                False,
                "Show the logs panel in the main dialog",
            )

            # Dynamic per-module/version setting (QGIS only)
            cls.installed_project_path = QgsSettingsEntryString(
                "project/modules/%1/version/%2/installed-project-path",
                settings_node,
                "",
                "Path to the installed QGIS project file for a given module/version",
            )
        else:
            # Standalone fallback using QSettings wrappers
            cls.github_token = _QSettingsEntryString("github-token", "")
            cls.allow_multiple_modules = _QSettingsEntryBool("allow-multiple-modules", False)
            cls.show_experimental_modules = _QSettingsEntryBool("show-experimental-modules", False)
            cls.log_show_datetime = _QSettingsEntryBool("log-show-datetime", True)
            cls.log_show_level = _QSettingsEntryBool("log-show-level", True)
            cls.log_show_module = _QSettingsEntryBool("log-show-module", True)
            cls.show_logs = _QSettingsEntryBool("show-logs", False)

            # Not available in standalone mode
            cls.installed_project_path = None

        return cls.instance
