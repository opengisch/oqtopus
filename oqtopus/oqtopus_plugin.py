from pathlib import Path

from qgis.core import QgsSettingsTree
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication

from .core.settings import Settings
from .gui.about_dialog import AboutDialog
from .gui.main_dialog import MainDialog
from .utils.plugin_utils import PluginUtils, logger


class OqtopusPlugin:

    def __init__(
        self,
        iface,
        modules_config_path=None,
        about_dialog_cls=None,
        settings_plugin_name=None,
        icon=None,
        title=None,
    ):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        :param modules_config_path: Optional path to the modules configuration YAML file.
            Defaults to ``default_config.yaml`` next to this file.
        :type modules_config_path: Path | None
        :param about_dialog_cls: Optional custom About dialog class.
            Defaults to the bundled ``AboutDialog``.
        :type about_dialog_cls: type | None
        :param settings_plugin_name: Optional name for the QGIS settings tree node.
            Defaults to ``"oqtopus"``.
        :type settings_plugin_name: str | None
        :param icon: Optional path to the plugin icon.
            Defaults to the bundled ``oqtopus-logo.png``.
        :type icon: str | None
        :param title: Optional title for the main dialog window.
            Defaults to the UI file's window title.
        :type title: str | None
        """
        # Save reference to the QGIS interface
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self._modules_config_path = (
            modules_config_path or Path(__file__).parent / "default_config.yaml"
        )
        self._about_dialog_cls = about_dialog_cls or AboutDialog
        self._settings_plugin_name = settings_plugin_name
        self._icon = icon or PluginUtils.get_plugin_icon_path("oqtopus-logo.png")
        self._title = title

        self.__version__ = PluginUtils.get_plugin_version()

        PluginUtils.init_logger()

        logger.info("")
        logger.info(f"Starting {PluginUtils.PLUGIN_NAME} plugin version {self.__version__}")

        self.actions = []
        self.main_menu_name = f"&{PluginUtils.PLUGIN_NAME}"

    # noinspection PyMethodMayBeStatic
    def tr(self, source_text):
        """
        This does not inherit from QObject but for the translation to work
        :rtype : unicode
        :param source_text: The text to translate
        :return: The translated text
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QApplication.translate("OqtopusPlugin", source_text)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None,
    ):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.main_menu_name, action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        # Register settings tree node early
        Settings(plugin_name=self._settings_plugin_name)

        self.add_action(
            icon_path=self._icon,
            text=self.tr("Show &main dialog"),
            callback=self.show_main_dialog,
            parent=self.iface.mainWindow(),
            add_to_toolbar=True,
        )
        self.add_action(
            icon_path=None,
            text=self.tr("Show &log folder"),
            callback=self.show_logs_folder,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False,
        )
        self.add_action(
            icon_path=PluginUtils.get_plugin_icon_path("help.svg"),
            text=self.tr("Help"),
            callback=PluginUtils.open_documentation,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False,
        )
        self.add_action(
            icon_path=self._icon,
            text=self.tr("&About"),
            callback=self.show_about_dialog,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False,
        )

        self._get_main_menu_action().setIcon(
            QIcon(self._icon),
        )

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(self.main_menu_name, action)
            self.iface.removeToolBarIcon(action)

        # Unregister the plugin settings tree node
        plugin_name = getattr(Settings, "_plugin_name", PluginUtils.PLUGIN_ID)
        QgsSettingsTree.unregisterPluginTreeNode(plugin_name)
        Settings.instance = None

        # Remove plugin and bundled-lib modules from sys.modules so that:
        # 1. The plugin can be cleanly reloaded after an upgrade.
        # 2. On Windows, Python releases its file handles on .pyc files,
        #    allowing QGIS to delete the plugin folder on uninstall.
        import sys

        prefixes = ("oqtopus", "pum", "pgserviceparser")
        stale = [mod for mod in sys.modules if mod.startswith(prefixes)]
        for mod in stale:
            del sys.modules[mod]
            logger.debug(f"Removed {mod} from sys.modules for clean reload")

    def show_main_dialog(self):
        main_dialog = MainDialog(
            modules_config_path=self._modules_config_path,
            about_dialog_cls=self._about_dialog_cls,
            parent=self.iface.mainWindow(),
        )
        if self._title:
            main_dialog.setWindowTitle(self._title)
        main_dialog.exec()

    def show_logs_folder(self):
        PluginUtils.open_logs_folder()

    def show_about_dialog(self):
        about_dialog = self._about_dialog_cls(self.iface.mainWindow())
        about_dialog.exec()

    def _get_main_menu_action(self):
        actions = self.iface.pluginMenu().actions()
        result_actions = [action for action in actions if action.text() == self.main_menu_name]

        # OSX does not support & in the menu title
        if not result_actions:
            result_actions = [
                action
                for action in actions
                if action.text() == self.main_menu_name.replace("&", "")
            ]

        return result_actions[0]
