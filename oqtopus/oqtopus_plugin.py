from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication

from .gui.about_dialog import AboutDialog
from .gui.main_dialog import MainDialog
from .utils.plugin_utils import PluginUtils, logger


class OqtopusPlugin:

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.__version__ = PluginUtils.get_plugin_version()

        PluginUtils.init_logger()

        logger.info("")
        logger.info(f"Starting {PluginUtils.PLUGIN_NAME} plugin version {self.__version__}")

        self.actions = []
        self.main_menu_name = self.tr(f"&{PluginUtils.PLUGIN_NAME}")

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
        self.add_action(
            icon_path=PluginUtils.get_plugin_icon_path("oqtopus-logo.png"),
            text=self.tr("Show &main dialog"),
            callback=self.show_main_dialog,
            parent=self.iface.mainWindow(),
        )
        self.add_action(
            icon_path=None,
            text=self.tr("Show &log folder"),
            callback=self.show_logs_folder,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False,
        )
        self.add_action(
            icon_path=PluginUtils.get_plugin_icon_path("oqtopus-logo.png"),
            text=self.tr("&About"),
            callback=self.show_about_dialog,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False,
        )

        self._get_main_menu_action().setIcon(
            PluginUtils.get_plugin_icon("oqtopus-logo.png"),
        )

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(self.main_menu_name, action)
            self.iface.removeToolBarIcon(action)

    def show_main_dialog(self):
        conf_path = Path(__file__).parent / "default_config.yaml"

        main_dialog = MainDialog(modules_config_path=conf_path, parent=self.iface.mainWindow())
        main_dialog.exec()

    def show_logs_folder(self):
        PluginUtils.open_logs_folder()

    def show_about_dialog(self):
        about_dialog = AboutDialog(self.iface.mainWindow())
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
