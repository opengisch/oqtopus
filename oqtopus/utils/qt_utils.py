"""
/***************************************************************************
                              -------------------
        begin                : 2016
        copyright            : (C) 2016 by OPENGIS.ch
        email                : info@opengis.ch
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

import traceback

from qgis.PyQt.QtWidgets import QApplication, QMessageBox


class OverrideCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        QApplication.setOverrideCursor(self.cursor)

    def __exit__(self, exc_type, exc_val, exc_tb):
        QApplication.restoreOverrideCursor()


class QtUtils:

    @staticmethod
    def setForegroundColor(widget, color):
        """
        Set the foreground color of a widget.
        :param widget: The widget to set the foreground color for.
        :param color: The color to set.
        """
        palette = widget.palette()
        palette.setColor(widget.foregroundRole(), color)
        widget.setPalette(palette)

    @staticmethod
    def resetForegroundColor(widget):
        """
        Reset the foreground color of a widget to the default.
        :param widget: The widget to reset the foreground color for.
        """
        palette = widget.palette()
        palette.setColor(
            widget.foregroundRole(),
            QApplication.style().standardPalette().color(palette.ColorRole.WindowText),
        )
        widget.setPalette(palette)

    @staticmethod
    def setFontItalic(widget, italic):
        """
        Set the font of a widget to italic.
        :param widget: The widget to set the font for.
        """
        font = widget.font()
        font.setItalic(italic)
        widget.setFont(font)

    @staticmethod
    def setTextWithEllipsis(label, text, max_length=80):
        """
        Set text on a label with ellipsis in the middle if too long.
        Sets full text as tooltip.
        :param label: The QLabel widget to set text on.
        :param text: The text to display.
        :param max_length: Maximum length before truncating (default: 80).
        """
        if len(text) <= max_length:
            label.setText(text)
            label.setToolTip("")
        else:
            # Calculate how many characters to keep on each side
            side_length = (max_length - 3) // 2  # 3 for the ellipsis
            truncated = f"{text[:side_length]}…{text[-side_length:]}"
            label.setText(truncated)
            label.setToolTip(text)


class CriticalMessageBox(QMessageBox):
    def __init__(self, title: str, description: str, exception: Exception = None, parent=None):
        super().__init__(parent)
        self.setIcon(QMessageBox.Icon.Critical)
        self.setWindowTitle(title)
        message = description
        if exception is not None:
            message += f"\n{str(exception)}"
            details = "".join(
                traceback.format_exception(type(exception), exception, exception.__traceback__)
            )
            self.setDetailedText(details)
        self.setText(message)

    def exec(self):
        try:
            return super().exec()
        except Exception:
            return super().exec_()

    def showEvent(self, event):
        super().showEvent(event)
        self.resize(700, 1000)  # Set your preferred initial size here
