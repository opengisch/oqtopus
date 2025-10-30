"""
/***************************************************************************
 Plugin Utils
                              -------------------
        begin                : 28.4.2018
        copyright            : (C) 2018 by OPENGIS.ch
        email                : matthias@opengis.ch
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import logging
import os
from logging import LogRecord
from logging.handlers import TimedRotatingFileHandler

from qgis.PyQt.QtCore import (
    QDir,
    QFileInfo,
    QObject,
    QSettings,
    QStandardPaths,
    QUrl,
    pyqtSignal,
)
from qgis.PyQt.QtGui import QColor, QDesktopServices, QIcon
from qgis.PyQt.uic import loadUiType

logger = logging.getLogger("oqtopus")


class PluginUtils:

    PLUGIN_NAME = "Oqtopus"

    logsDirectory = ""

    COLOR_GREEN = QColor(12, 167, 137)
    COLOR_WARNING = QColor(255, 165, 0)

    DOCUMENTATION_URL = "https://opengisch.github.io/oqtopus/"

    @staticmethod
    def plugin_root_path():
        """
        Returns the root path of the plugin
        """
        return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

    @staticmethod
    def plugin_temp_path():
        plugin_basename = PluginUtils.plugin_root_path().split(os.sep)[-1]

        plugin_temp_dir = os.path.join(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation),
            plugin_basename,
        )
        if not os.path.exists(plugin_temp_dir):
            os.makedirs(plugin_temp_dir)

        return plugin_temp_dir

    @staticmethod
    def get_plugin_icon_path(icon_filename):
        return os.path.join(PluginUtils.plugin_root_path(), "icons", icon_filename)

    @staticmethod
    def get_plugin_icon(icon_filename):
        return QIcon(PluginUtils.get_plugin_icon_path(icon_filename=icon_filename))

    @staticmethod
    def get_ui_class(ui_file):
        """Get UI Python class from .ui file.
           Can be filename.ui or subdirectory/filename.ui
        :param ui_file: The file of the ui in svir.ui
        :type ui_file: str
        """
        os.path.sep.join(ui_file.split("/"))
        ui_file_path = os.path.abspath(os.path.join(PluginUtils.plugin_root_path(), "ui", ui_file))
        return loadUiType(ui_file_path)[0]

    @staticmethod
    def get_metadata_file_path():
        return os.path.join(PluginUtils.plugin_root_path(), "metadata.txt")

    @staticmethod
    def get_plugin_version():
        ini_text = QSettings(PluginUtils.get_metadata_file_path(), QSettings.Format.IniFormat)
        return ini_text.value("version")

    @staticmethod
    def init_logger(logs_directory=None):
        if logs_directory is not None:
            PluginUtils.logsDirectory = logs_directory
        else:
            PluginUtils.logsDirectory = f"{PluginUtils.plugin_root_path()}/logs"

        directory = QDir(PluginUtils.logsDirectory)
        if not directory.exists():
            directory.mkpath(PluginUtils.logsDirectory)

        if directory.exists():
            logfile = QFileInfo(directory, "Oqtopus.log")

            # Handler for files rotation, create one log per day
            rotationHandler = TimedRotatingFileHandler(
                logfile.filePath(), when="midnight", backupCount=10
            )

            # Configure logging
            logging.basicConfig(
                level=logging.DEBUG,
                format="%(asctime)s %(levelname)-7s %(message)s",
                handlers=[rotationHandler],
            )
        else:
            logger.error(f"Can't create log files directory '{PluginUtils.logsDirectory}'.")

    @staticmethod
    def open_logs_folder():
        QDesktopServices.openUrl(QUrl.fromLocalFile(PluginUtils.logsDirectory))

    @staticmethod
    def open_log_file():
        log_file_path = os.path.join(PluginUtils.logsDirectory, "Oqtopus.log")
        if os.path.exists(log_file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(log_file_path))
        else:
            logger.error(f"Log file '{log_file_path}' does not exist.")

    @staticmethod
    def get_github_token():
        settings = QSettings()
        return settings.value("oqtopus/github_token", type=str)

    @staticmethod
    def set_github_token(token: str):
        settings = QSettings()
        settings.setValue("oqtopus/github_token", token)

    @staticmethod
    def get_github_headers():
        token = PluginUtils.get_github_token()
        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"
        return headers

    @staticmethod
    def open_documentation():
        QDesktopServices.openUrl(QUrl(PluginUtils.DOCUMENTATION_URL))


class LoggingBridge(logging.Handler, QObject):

    loggedLine = pyqtSignal(LogRecord, str)

    def __init__(self, level=logging.NOTSET, excluded_modules=[]):
        QObject.__init__(self)
        logging.Handler.__init__(self, level)

        self.formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")

        self.excluded_modules = excluded_modules

    def filter(self, record):
        return record.name not in self.excluded_modules

    def emit(self, record):
        log_entry = self.format(record)
        print(log_entry)
        self.loggedLine.emit(record, log_entry)
