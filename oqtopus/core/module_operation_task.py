"""Background task for module install/upgrade/uninstall operations."""

import psycopg
from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..libs.pum.feedback import Feedback
from ..libs.pum.pum_config import PumConfig
from ..libs.pum.upgrader import Upgrader
from ..utils.plugin_utils import logger


class ModuleOperationCanceled(Exception):
    """Exception raised when module operation is canceled."""


class ModuleOperationTask(QThread):
    """
    Background task for running module install/upgrade/uninstall operations.
    This allows the UI to remain responsive and show progress during long operations.
    """

    signalProgress = pyqtSignal(str, int, int)  # message, current, total
    signalFinished = pyqtSignal(bool, str)  # success, error_message

    def __init__(self, parent=None):
        super().__init__(parent)

        self.__pum_config = None
        self.__connection = None
        self.__operation = None  # 'install', 'upgrade', 'uninstall'
        self.__parameters = None
        self.__options = {}

        self.__feedback = None
        self.__canceled = False
        self.__error_message = None

    def start_install(
        self, pum_config: PumConfig, connection: psycopg.Connection, parameters: dict, **options
    ):
        """Start an install operation."""
        self.__pum_config = pum_config
        self.__connection = connection
        self.__operation = "install"
        self.__parameters = parameters
        self.__options = options
        self.__canceled = False
        self.__error_message = None
        self.start()

    def start_upgrade(
        self, pum_config: PumConfig, connection: psycopg.Connection, parameters: dict, **options
    ):
        """Start an upgrade operation."""
        self.__pum_config = pum_config
        self.__connection = connection
        self.__operation = "upgrade"
        self.__parameters = parameters
        self.__options = options
        self.__canceled = False
        self.__error_message = None
        self.start()

    def start_uninstall(
        self, pum_config: PumConfig, connection: psycopg.Connection, parameters: dict, **options
    ):
        """Start an uninstall operation."""
        self.__pum_config = pum_config
        self.__connection = connection
        self.__operation = "uninstall"
        self.__parameters = parameters
        self.__options = options
        self.__canceled = False
        self.__error_message = None
        self.start()

    def start_roles(
        self, pum_config: PumConfig, connection: psycopg.Connection, parameters: dict, **options
    ):
        """Start a create and grant roles operation."""
        self.__pum_config = pum_config
        self.__connection = connection
        self.__operation = "roles"
        self.__parameters = parameters
        self.__options = options
        self.__canceled = False
        self.__error_message = None
        self.start()

    def cancel(self):
        """Cancel the current operation."""
        self.__canceled = True
        if self.__feedback:
            self.__feedback.cancel()

    def run(self):
        """Execute the operation in a background thread."""
        try:
            # Create feedback instance that emits signals
            self.__feedback = self._create_feedback()

            upgrader = Upgrader(config=self.__pum_config)

            if self.__operation == "install":
                self._run_install(upgrader)
            elif self.__operation == "upgrade":
                self._run_upgrade(upgrader)
            elif self.__operation == "uninstall":
                self._run_uninstall(upgrader)
            elif self.__operation == "roles":
                self._run_roles()
            else:
                raise Exception(f"Unknown operation: {self.__operation}")

            # Commit if successful and not canceled
            if not self.__canceled and self.__options.get("commit", True):
                logger.info("Committing changes to database...")
                self.__connection.commit()
                logger.info("Changes committed to the database.")

            logger.info(f"Operation '{self.__operation}' completed successfully")
            self.signalFinished.emit(True, "")

        except Exception as e:
            logger.critical(f"Module operation error in '{self.__operation}': {e}")
            logger.exception("Full traceback:")  # Log full stack trace
            self.__error_message = str(e)
            # Rollback on error
            try:
                logger.info("Rolling back transaction...")
                self.__connection.rollback()
                logger.info("Transaction rolled back")
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")
            self.signalFinished.emit(False, self.__error_message)

    def _run_install(self, upgrader: Upgrader):
        """Run install operation."""
        # Extract options that should not be passed to install()
        install_demo_data = self.__options.pop("install_demo_data", False)
        demo_data_name = self.__options.pop("demo_data_name", None)

        upgrader.install(
            connection=self.__connection,
            parameters=self.__parameters,
            feedback=self.__feedback,
            commit=False,
            **self.__options,
        )

        # Install demo data if requested
        if install_demo_data and demo_data_name:
            upgrader.install_demo_data(
                connection=self.__connection,
                name=demo_data_name,
                parameters=self.__parameters,
            )

    def _run_upgrade(self, upgrader: Upgrader):
        """Run upgrade operation."""
        upgrader.upgrade(
            connection=self.__connection,
            parameters=self.__parameters,
            feedback=self.__feedback,
            **self.__options,
        )

    def _run_uninstall(self, upgrader: Upgrader):
        """Run uninstall operation."""
        logger.info("Starting uninstall operation...")
        logger.debug(f"Parameters: {self.__parameters}")
        logger.debug(f"Options: {self.__options}")

        upgrader.uninstall(
            connection=self.__connection,
            parameters=self.__parameters,
            feedback=self.__feedback,
            commit=False,
        )

        logger.info("Uninstall operation completed")

    def _run_roles(self):
        """Run create and grant roles operation."""
        logger.info("Starting create and grant roles operation...")

        role_manager = self.__pum_config.role_manager()

        if not role_manager.roles:
            logger.warning("No roles defined in the configuration")
            return

        # Create roles with grant=True to also grant permissions
        role_manager.create_roles(
            connection=self.__connection,
            grant=True,
            feedback=self.__feedback,
        )

        logger.info("Create and grant roles operation completed")

    def _create_feedback(self):
        """Create a Feedback instance that emits Qt signals."""

        class QtFeedback(Feedback):
            """Feedback implementation that emits Qt signals."""

            def __init__(self, task):
                super().__init__()
                self.task = task

            def report_progress(self, message: str, current: int = 0, total: int = 0):
                """Report progress via Qt signal.

                If current and total are provided (non-zero), use those.
                Otherwise, use the internal step counter.
                """
                # Use provided values if available, otherwise use internal counter
                if current > 0 or total > 0:
                    actual_current = current
                    actual_total = total
                else:
                    actual_current, actual_total = self.get_progress()

                logger.info(
                    f"[{actual_current}/{actual_total}] {message}" if actual_total > 0 else message
                )
                self.task.signalProgress.emit(message, actual_current, actual_total)

            def is_cancelled(self):
                """Check if operation is cancelled."""
                return self.task._ModuleOperationTask__canceled

        return QtFeedback(self)
