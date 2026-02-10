import logging
from datetime import datetime

from qgis.PyQt.QtCore import QAbstractItemModel, QModelIndex, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QAction, QKeySequence, QShortcut
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QMenu,
    QStyle,
    QWidget,
)

# Import and register SQL logging level from pum
from ..libs.pum import SQL
from ..utils.plugin_utils import LoggingBridge, PluginUtils

logging.addLevelName(SQL, "SQL")


DIALOG_UI = PluginUtils.get_ui_class("logs_widget.ui")

COLUMNS = ["Timestamp", "Level", "Module", "Message"]


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
        if not index.isValid():
            return None
        if (
            index.row() < 0
            or index.row() >= len(self.logs)
            or index.column() < 0
            or index.column() >= len(COLUMNS)
        ):
            return None

        log = self.logs[index.row()]
        col_name = COLUMNS[index.column()]
        value = log[col_name]

        if role == Qt.ItemDataRole.DisplayRole:
            return value
        elif role == Qt.ItemDataRole.ToolTipRole:
            # Show full text in tooltip, especially useful for long messages
            if col_name == "Message":
                return value
        return None

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
    LEVELS = ["SQL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level_filter = None

    def setLevelFilter(self, level):
        self.level_filter = level
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        index_level = model.index(source_row, 1, source_parent)  # Level column
        index_message = model.index(source_row, 3, source_parent)  # Message column
        index_module = model.index(source_row, 2, source_parent)  # Module column
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
        self.logs_treeView.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.logs_treeView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Enable word wrapping for better readability
        self.logs_treeView.setWordWrap(True)
        self.logs_treeView.setTextElideMode(Qt.TextElideMode.ElideNone)

        # Configure column widths
        header = self.logs_treeView.header()
        header.setStretchLastSection(True)  # Message column stretches to fill space
        header.resizeSection(0, 150)  # Timestamp column - fixed width
        header.resizeSection(1, 100)  # Level column - fixed width
        header.resizeSection(2, 150)  # Module column - fixed width
        # Message column will take remaining space due to setStretchLastSection

        # Apply initial column visibility from settings
        self.logs_treeView.setColumnHidden(0, not PluginUtils.get_log_show_datetime())
        self.logs_treeView.setColumnHidden(1, not PluginUtils.get_log_show_level())
        self.logs_treeView.setColumnHidden(2, not PluginUtils.get_log_show_module())

        # Enable automatic row height adjustment
        self.logs_treeView.setUniformRowHeights(False)
        header.setDefaultSectionSize(100)

        self.loggingBridge.loggedLine.connect(self.__logged_line)
        logging.getLogger().addHandler(self.loggingBridge)

        self.logs_level_comboBox.addItems(
            [
                "SQL",
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

        # Add copy shortcut (Ctrl+C)
        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.logs_treeView)
        self.copy_shortcut.activated.connect(self.__copySelectedRows)

        # Enable context menu
        self.logs_treeView.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.logs_treeView.customContextMenuRequested.connect(self.__showContextMenu)

    def close(self):
        # uninstall the logging bridge
        logging.getLogger().removeHandler(self.loggingBridge)

    def __logged_line(self, record, line):
        # Convert timestamp from record.created (epoch time) to readable format
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

        log_entry = {
            "Timestamp": timestamp,
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

    def __showContextMenu(self, position):
        """Show context menu on right-click."""
        selection_model = self.logs_treeView.selectionModel()
        has_selection = selection_model.hasSelection()
        selected_rows = selection_model.selectedRows() if has_selection else []

        menu = QMenu(self.logs_treeView)

        copy_action = QAction(self.tr("Copy"), menu)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self.__copySelectedRows)
        copy_action.setEnabled(has_selection)
        menu.addAction(copy_action)

        copy_message_action = QAction(self.tr("Copy message"), menu)
        copy_message_action.triggered.connect(self.__copySelectedMessage)
        copy_message_action.setEnabled(len(selected_rows) == 1)
        menu.addAction(copy_message_action)

        menu.addSeparator()

        # Columns submenu
        columns_menu = menu.addMenu(self.tr("Columns"))

        datetime_action = QAction(self.tr("Timestamp"), columns_menu)
        datetime_action.setCheckable(True)
        datetime_action.setChecked(PluginUtils.get_log_show_datetime())
        datetime_action.toggled.connect(self.__toggleDatetimeColumn)
        columns_menu.addAction(datetime_action)

        level_action = QAction(self.tr("Level"), columns_menu)
        level_action.setCheckable(True)
        level_action.setChecked(PluginUtils.get_log_show_level())
        level_action.toggled.connect(self.__toggleLevelColumn)
        columns_menu.addAction(level_action)

        module_action = QAction(self.tr("Module"), columns_menu)
        module_action.setCheckable(True)
        module_action.setChecked(PluginUtils.get_log_show_module())
        module_action.toggled.connect(self.__toggleModuleColumn)
        columns_menu.addAction(module_action)

        menu.exec(self.logs_treeView.viewport().mapToGlobal(position))

    def set_datetime_column_visible(self, visible: bool):
        """Set visibility of the timestamp column."""
        self.logs_treeView.setColumnHidden(0, not visible)

    def set_level_column_visible(self, visible: bool):
        """Set visibility of the level column."""
        self.logs_treeView.setColumnHidden(1, not visible)

    def set_module_column_visible(self, visible: bool):
        """Set visibility of the module column."""
        self.logs_treeView.setColumnHidden(2, not visible)

    def update_column_visibility_from_settings(self):
        """Update column visibility based on current settings."""
        show_datetime = PluginUtils.get_log_show_datetime()
        show_level = PluginUtils.get_log_show_level()
        show_module = PluginUtils.get_log_show_module()

        self.set_datetime_column_visible(show_datetime)
        self.set_level_column_visible(show_level)
        self.set_module_column_visible(show_module)

    def __toggleDatetimeColumn(self, checked: bool):
        """Toggle timestamp column visibility and persist to settings."""
        PluginUtils.set_log_show_datetime(checked)
        self.set_datetime_column_visible(checked)

    def __toggleLevelColumn(self, checked: bool):
        """Toggle level column visibility and persist to settings."""
        PluginUtils.set_log_show_level(checked)
        self.set_level_column_visible(checked)

    def __toggleModuleColumn(self, checked: bool):
        """Toggle module column visibility and persist to settings."""
        PluginUtils.set_log_show_module(checked)
        self.set_module_column_visible(checked)

    def __copySelectedRows(self):
        """Copy selected rows to clipboard in CSV format."""
        selection_model = self.logs_treeView.selectionModel()
        selected_indexes = selection_model.selectedRows()

        if not selected_indexes:
            return

        # Sort by row number to maintain order
        selected_indexes.sort(key=lambda idx: idx.row())

        # Build CSV content with header
        csv_lines = ["Timestamp,Level,Module,Message"]

        for proxy_index in selected_indexes:
            # Map proxy index to source model index
            source_index = self.proxy_model.mapToSource(proxy_index)
            row = source_index.row()
            log_entry = self.logs_model.logs[row]

            # Escape fields that might contain commas or quotes
            def escape_csv(value):
                value = str(value)
                if "," in value or '"' in value or "\n" in value:
                    return '"' + value.replace('"', '""') + '"'
                return value

            csv_line = ",".join(
                [
                    escape_csv(log_entry["Timestamp"]),
                    escape_csv(log_entry["Level"]),
                    escape_csv(log_entry["Module"]),
                    escape_csv(log_entry["Message"]),
                ]
            )
            csv_lines.append(csv_line)

        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(csv_lines))

    def __copySelectedMessage(self):
        """Copy the message of the single selected row to clipboard."""
        selection_model = self.logs_treeView.selectionModel()
        selected_indexes = selection_model.selectedRows()

        if len(selected_indexes) != 1:
            return

        source_index = self.proxy_model.mapToSource(selected_indexes[0])
        row = source_index.row()
        log_entry = self.logs_model.logs[row]

        clipboard = QApplication.clipboard()
        clipboard.setText(str(log_entry["Message"]))
