from enum import Enum

from qgis.PyQt.QtCore import QThread


class ModuleVersionLoaderCanceled(Exception):
    pass


class ModuleVersionLoader(QThread):

    class Mode(Enum):
        NORMAL = 1
        DEVELOPMENT = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.__module = None
        self.__mode = self.Mode.NORMAL

        self.lastError = None

    def start_load_versions(self, module, mode: Mode = Mode.NORMAL):
        if self.isRunning():
            self.cancel()
            self.wait()

        self.__module = module
        self.__mode = mode

        self.start()

    def run(self):
        self.lastError = None
        try:
            if self.__mode == self.Mode.NORMAL:
                self.__module.load_versions()
            elif self.__mode == self.Mode.DEVELOPMENT:
                self.__module.load_development_versions()

        except Exception as e:
            self.lastError = e
