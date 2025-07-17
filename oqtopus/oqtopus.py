import sys
import types
from pathlib import Path

# Create fake qgis.PyQt modules that point to PyQt5 modules
try:
    pyqt_core = __import__("PyQt6.QtCore", fromlist=[""])
    pyqt_gui = __import__("PyQt6.QtGui", fromlist=[""])
    pyqt_network = __import__("PyQt6.QtNetwork", fromlist=[""])
    pyqt_widgets = __import__("PyQt6.QtWidgets", fromlist=[""])
    pyqt_uic = __import__("PyQt6.uic", fromlist=[""])
except ModuleNotFoundError:
    pyqt_core = __import__("PyQt5.QtCore", fromlist=[""])
    pyqt_gui = __import__("PyQt5.QtGui", fromlist=[""])
    pyqt_network = __import__("PyQt5.QtNetwork", fromlist=[""])
    pyqt_widgets = __import__("PyQt5.QtWidgets", fromlist=[""])
    pyqt_uic = __import__("PyQt5.uic", fromlist=[""])

# Create the qgis, qgis.PyQt, and submodules in sys.modules
qgis = types.ModuleType("qgis")
pyqt = types.ModuleType("qgis.PyQt")
pyqt.QtCore = pyqt_core
pyqt.QtGui = pyqt_gui
pyqt.QtNetwork = pyqt_network
pyqt.QtWidgets = pyqt_widgets
pyqt.uic = pyqt_uic

qgis.PyQt = pyqt
sys.modules["qgis"] = qgis
sys.modules["qgis.PyQt"] = pyqt
sys.modules["qgis.PyQt.QtCore"] = pyqt_core
sys.modules["qgis.PyQt.QtGui"] = pyqt_gui
sys.modules["qgis.PyQt.QtNetwork"] = pyqt_network
sys.modules["qgis.PyQt.QtWidgets"] = pyqt_widgets
sys.modules["qgis.PyQt.uic"] = pyqt_uic

from qgis.PyQt.QtGui import QIcon  # noqa: E402

from .gui.main_dialog import MainDialog  # noqa: E402
from .utils.plugin_utils import PluginUtils  # noqa: E402


def main():
    app = pyqt_widgets.QApplication(sys.argv)
    icon = QIcon("oqtopus/icons/oqtopus-logo.png")
    app.setWindowIcon(icon)

    PluginUtils.init_logger()

    conf_path = Path(__file__).parent / "default_config.yaml"

    dialog = MainDialog(modules_config_path=conf_path)
    dialog.setWindowIcon(icon)
    dialog.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
