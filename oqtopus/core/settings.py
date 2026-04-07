import logging

from qgis.PyQt.QtCore import QSettings

from ..utils.plugin_utils import PluginUtils

logger = logging.getLogger(__name__)

try:
    from qgis.core import (
        QgsApplication,
        QgsAuthMethodConfig,
        QgsSettingsEntryBool,
        QgsSettingsEntryString,
        QgsSettingsTree,
    )

    HAS_QGS_SETTINGS = True
except ImportError:
    HAS_QGS_SETTINGS = False

PLUGIN_NAME = PluginUtils.PLUGIN_ID


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

        token = Settings.get_github_token()
        Settings.store_github_token("ghp_…")

    The QGIS-only ``installed_project_path`` setting is ``None`` in
    standalone mode.  It requires a ``dynamicKeyPartList``::

        Settings().installed_project_path.setValue(
            path, dynamicKeyPartList=[module_id, version]
        )

    A custom *plugin_name* can be passed on first instantiation to
    register settings under a different tree node (e.g. ``"tmmt"``).
    Subsequent calls ignore the argument and return the existing
    singleton.
    """

    instance = None

    def __new__(cls, plugin_name=None):
        if cls.instance is not None:
            return cls.instance

        cls.instance = super().__new__(cls)
        cls._plugin_name = plugin_name or PLUGIN_NAME

        if HAS_QGS_SETTINGS:
            settings_node = QgsSettingsTree.createPluginTreeNode(pluginName=cls._plugin_name)

            cls.github_auth_cfg_id = QgsSettingsEntryString(
                "github-auth-cfg-id",
                settings_node,
                "",
                "QGIS auth-db config ID that holds the GitHub token",
            )
            # Legacy setting kept for one-time migration
            cls._github_token_legacy = QgsSettingsEntryString(
                "github-token",
                settings_node,
                "",
                "(deprecated) plain-text GitHub token – migrated to auth DB",
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
            cls.skip_baseline_check = QgsSettingsEntryBool(
                "skip-baseline-check",
                settings_node,
                False,
                "Skip changelog checks when upgrading a baselined database",
            )
            cls.auto_load_development_versions = QgsSettingsEntryBool(
                "auto-load-development-versions",
                settings_node,
                False,
                "Automatically load pre-releases and development branches when selecting a module",
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
            cls.github_auth_cfg_id = _QSettingsEntryString("github-auth-cfg-id", "")
            cls._github_token_legacy = _QSettingsEntryString("github-token", "")
            cls.allow_multiple_modules = _QSettingsEntryBool("allow-multiple-modules", False)
            cls.show_experimental_modules = _QSettingsEntryBool("show-experimental-modules", False)
            cls.log_show_datetime = _QSettingsEntryBool("log-show-datetime", True)
            cls.log_show_level = _QSettingsEntryBool("log-show-level", True)
            cls.log_show_module = _QSettingsEntryBool("log-show-module", True)
            cls.show_logs = _QSettingsEntryBool("show-logs", False)
            cls.skip_baseline_check = _QSettingsEntryBool("skip-baseline-check", False)
            cls.auto_load_development_versions = _QSettingsEntryBool(
                "auto-load-development-versions", False
            )

            # Not available in standalone mode
            cls.installed_project_path = None

        return cls.instance

    # ------------------------------------------------------------------
    # GitHub token helpers  (QGIS auth-db in QGIS mode, plain QSettings
    # fallback in standalone mode)
    # ------------------------------------------------------------------
    _AUTH_CFG_NAME = "oqtopus-github"

    @staticmethod
    def has_github_token() -> bool:
        """Return True if a GitHub token is configured.

        This only checks whether an auth-config ID (or a legacy
        plain-text value) exists.  It does **not** access the
        encrypted auth DB, so it will never trigger a master-password
        prompt.
        """
        if Settings().github_auth_cfg_id.value():
            return True
        return bool(Settings()._github_token_legacy.value())

    @staticmethod
    def store_github_token(token: str) -> None:
        """Store *token* in the QGIS auth DB (or QSettings in standalone)."""
        if not HAS_QGS_SETTINGS:
            # Standalone – no auth DB available, fall back to plain text
            Settings()._github_token_legacy.setValue(token)
            return

        auth_mgr = QgsApplication.authManager()
        cfg_id = Settings().github_auth_cfg_id.value()

        cfg = QgsAuthMethodConfig()
        if cfg_id and auth_mgr.loadAuthenticationConfig(cfg_id, cfg, True):
            # Update existing entry
            cfg.setConfigMap({"token": token})
            auth_mgr.updateAuthenticationConfig(cfg)
        else:
            # Create a new entry
            cfg.setName(Settings._AUTH_CFG_NAME)
            cfg.setMethod("Basic")
            cfg.setConfigMap({"token": token})
            auth_mgr.storeAuthenticationConfig(cfg)
            Settings().github_auth_cfg_id.setValue(cfg.id())

    @staticmethod
    def get_github_token() -> str:
        """Retrieve the GitHub token from the auth DB (or QSettings fallback)."""
        if not HAS_QGS_SETTINGS:
            return Settings()._github_token_legacy.value()

        # Migrate plain-text token on first access if needed
        Settings._migrate_github_token()

        cfg_id = Settings().github_auth_cfg_id.value()
        if not cfg_id:
            return ""

        auth_mgr = QgsApplication.authManager()
        cfg = QgsAuthMethodConfig()
        if auth_mgr.loadAuthenticationConfig(cfg_id, cfg, True):
            return cfg.configMap().get("token", "")
        return ""

    @staticmethod
    def _migrate_github_token() -> None:
        """One-time migration: move a legacy plain-text token into the auth DB."""
        legacy = Settings()._github_token_legacy.value()
        if not legacy:
            return
        # Already migrated?
        if Settings().github_auth_cfg_id.value():
            # Just clear the leftover plain-text value
            Settings()._github_token_legacy.setValue("")
            return
        logger.info("Migrating GitHub token from plain-text settings to QGIS auth DB")
        Settings.store_github_token(legacy)
        Settings()._github_token_legacy.setValue("")

    @staticmethod
    def get_github_headers():
        """Return HTTP headers dict with GitHub auth token if configured."""
        token = Settings.get_github_token()
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers
