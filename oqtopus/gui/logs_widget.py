import logging

from qgis.PyQt.QtCore import QAbstractItemModel, QModelIndex, QSortFilterProxyModel, Qt
from qgis.PyQt.QtWidgets import QAbstractItemView, QApplication, QStyle, QWidget

from ..utils.plugin_utils import LoggingBridge, PluginUtils

DIALOG_UI = PluginUtils.get_ui_class("logs_widget.ui")


COLUMNS = ["Level", "Module", "Message"]


class LogModel(QAbstractItemModel):
    def __init__(self, parent=None):
        QAbstractItemModel.__init__(self, parent)
        self.logs = []

    def add_log(self, log):
        self.beginInsertRows(QModelIndex(), len(self.logs), len(self.logs))
        self.logs.append(log)
        self.endInsertRows()

    def headerData(self, section: int, orientation: Qt.Orientation, role: Qt.ItemDataRole = None):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def rowCount(self, parent=None):
        return len(self.logs)

    def columnCount(self, parent=None):
        return len(COLUMNS)

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = None):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        if (
            index.row() < 0
            or index.row() >= len(self.logs)
            or index.column() < 0
            or index.column() >= len(COLUMNS)
        ):
            return None
        log = self.logs[index.row()]
        return log[COLUMNS[index.column()]]

    def index(self, row: int, column: int, parent=None):
        if row < 0 or row >= len(self.logs) or column < 0 or column >= len(COLUMNS):
            return QModelIndex()
        return self.createIndex(row, column)

    def parent(self, index: QModelIndex):
        if not index.isValid():
            return QModelIndex()
        return QModelIndex()

    def flags(self, index: QModelIndex):
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemNeverHasChildren
        )

    def clear(self):
        self.beginResetModel()
        self.logs = []
        self.endResetModel()


class LogFilterProxyModel(QSortFilterProxyModel):
    LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level_filter = None

    def setLevelFilter(self, level):
        self.level_filter = level
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        index_level = model.index(source_row, 0, source_parent)  # Level column
        index_message = model.index(source_row, 2, source_parent)  # Message column
        index_module = model.index(source_row, 1, source_parent)  # Module column
        # Level filter (show entries with at least the selected level)
        if self.level_filter and self.level_filter != "ALL":
            level = model.data(index_level, Qt.ItemDataRole.DisplayRole)
            try:
                filter_idx = self.LEVELS.index(self.level_filter)
                level_idx = self.LEVELS.index(level)
                if level_idx < filter_idx:
                    return False
            except ValueError:
                return False
        # Text filter (from QLineEdit)
        filter_text = self.filterRegularExpression().pattern()
        if filter_text:
            msg = model.data(index_message, Qt.ItemDataRole.DisplayRole) or ""
            mod = model.data(index_module, Qt.ItemDataRole.DisplayRole) or ""
            if filter_text.lower() not in msg.lower() and filter_text.lower() not in mod.lower():
                return False
        return True


class LogsWidget(QWidget, DIALOG_UI):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)
        self.loggingBridge = LoggingBridge(
            level=logging.NOTSET, excluded_modules=["urllib3.connectionpool"]
        )
        self.logs_model = LogModel(self)

        # Use custom proxy model
        self.proxy_model = LogFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.logs_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)

        self.logs_treeView.setModel(self.proxy_model)
        self.logs_treeView.setAlternatingRowColors(True)
        self.logs_treeView.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.logs_treeView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.logs_treeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.loggingBridge.loggedLine.connect(self.__logged_line)
        logging.getLogger().addHandler(self.loggingBridge)

        self.logs_level_comboBox.addItems(
            [
                "DEBUG",
                "INFO",
                "WARNING",
                "ERROR",
                "CRITICAL",
            ]
        )
        self.logs_level_comboBox.currentTextChanged.connect(self.proxy_model.setLevelFilter)
        self.logs_level_comboBox.setCurrentText("INFO")

        self.logs_openFile_toolButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        )
        self.logs_openFolder_toolButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self.logs_clear_toolButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton)
        )
        self.logs_openFile_toolButton.clicked.connect(self.__logsOpenFileClicked)
        self.logs_openFolder_toolButton.clicked.connect(self.__logsOpenFolderClicked)
        self.logs_clear_toolButton.clicked.connect(self.__logsClearClicked)
        self.logs_filter_LineEdit.textChanged.connect(self.proxy_model.setFilterFixedString)

    def close(self):
        # uninstall the logging bridge
        logging.getLogger().removeHandler(self.loggingBridge)

    def __logged_line(self, record, line):

        log_entry = {
            "Level": record.levelname,
            "Module": record.name,
            "Message": record.msg,
        }

        self.logs_model.add_log(log_entry)

        # Automatically scroll to the bottom of the logs
        scroll_bar = self.logs_treeView.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def __logsOpenFileClicked(self):
        PluginUtils.open_log_file()

    def __logsOpenFolderClicked(self):
        PluginUtils.open_logs_folder()

    def __logsClearClicked(self):
        self.logs_model.clear()
