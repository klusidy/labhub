import sys, subprocess, os, time
from pathlib import Path
from typing import Optional
import argparse
import hashlib

# Ensure project root is importable (for server.server_config)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.server_config import (
    ServerConfig,
    ServerSection,
    LoggingSection,
    ScriptingSection,
    InfluxSection,
    CustomGuiEntry,
    load_server_config,
    save_server_config,
    ENV_VAR,
)

from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QTabWidget,
    QWidget,
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)

from PySide6.QtGui import QIcon, QAction, QPixmap, QDesktopServices, QCursor
from PySide6.QtCore import QUrl, QByteArray
from PySide6.QtNetwork import QLocalServer, QLocalSocket
import httpx
import socket

import logging

logger = logging.getLogger("labhub.launcher")

LABHUB_DIR = _PROJECT_ROOT

logger.debug(f"project_root is {LABHUB_DIR}")

icon_green_base64 = b"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"
icon_red_base64 = b"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"


LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class ConfigureDialog(QDialog):
    """Dialog for configuring launcher settings."""

    def __init__(self, launcher: "Launcher", parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.setWindowTitle("Configure LabHub Launcher")
        self.setMinimumWidth(500)
        self._build_ui()
        self._load_current_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ===== General tab =====
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)

        # Server settings group
        server_group = QGroupBox("Server")
        server_layout = QFormLayout(server_group)

        self.host_edit = QLineEdit()
        self.port_edit = QLineEdit()
        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 128)
        self.max_workers_spin.setToolTip("Thread pool size for blocking driver operations")
        server_layout.addRow("Host:", self.host_edit)
        server_layout.addRow("Port:", self.port_edit)
        server_layout.addRow("Max Workers:", self.max_workers_spin)
        general_layout.addWidget(server_group)

        # Config file group
        config_group = QGroupBox("Device Configuration")
        config_layout = QVBoxLayout(config_group)

        config_path_layout = QHBoxLayout()
        self.config_edit = QLineEdit()
        self.config_edit.setReadOnly(True)
        btn_config_browse = QPushButton("Browse...")
        btn_config_browse.clicked.connect(self._browse_config)
        config_path_layout.addWidget(self.config_edit)
        config_path_layout.addWidget(btn_config_browse)
        config_layout.addLayout(config_path_layout)

        config_btn_layout = QHBoxLayout()
        btn_config_edit = QPushButton("Edit")
        btn_config_edit.clicked.connect(self._edit_config)
        btn_config_folder = QPushButton("Open Folder")
        btn_config_folder.clicked.connect(self._open_config_folder)
        config_btn_layout.addWidget(btn_config_edit)
        config_btn_layout.addWidget(btn_config_folder)
        config_btn_layout.addStretch()
        config_layout.addLayout(config_btn_layout)
        general_layout.addWidget(config_group)

        # Profile file group
        profile_group = QGroupBox("Profile")
        profile_layout = QVBoxLayout(profile_group)

        profile_path_layout = QHBoxLayout()
        self.profile_edit = QLineEdit()
        self.profile_edit.setReadOnly(True)
        btn_profile_browse = QPushButton("Browse...")
        btn_profile_browse.clicked.connect(self._browse_profile)
        profile_path_layout.addWidget(self.profile_edit)
        profile_path_layout.addWidget(btn_profile_browse)
        profile_layout.addLayout(profile_path_layout)

        profile_btn_layout = QHBoxLayout()
        btn_profile_edit = QPushButton("Edit")
        btn_profile_edit.clicked.connect(self._edit_profile)
        btn_profile_folder = QPushButton("Open Folder")
        btn_profile_folder.clicked.connect(self._open_profile_folder)
        profile_btn_layout.addWidget(btn_profile_edit)
        profile_btn_layout.addWidget(btn_profile_folder)
        profile_btn_layout.addStretch()
        profile_layout.addLayout(profile_btn_layout)
        general_layout.addWidget(profile_group)

        # Logging group
        log_group = QGroupBox("Logging")
        log_layout = QFormLayout(log_group)

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(LOG_LEVELS)
        log_layout.addRow("Log Level:", self.log_level_combo)

        log_file_layout = QHBoxLayout()
        self.log_file_edit = QLineEdit()
        btn_log_browse = QPushButton("Browse...")
        btn_log_browse.clicked.connect(self._browse_log_file)
        btn_log_clear = QPushButton("Clear")
        btn_log_clear.clicked.connect(lambda: self.log_file_edit.clear())
        log_file_layout.addWidget(self.log_file_edit)
        log_file_layout.addWidget(btn_log_browse)
        log_file_layout.addWidget(btn_log_clear)
        log_layout.addRow("Log File:", log_file_layout)
        general_layout.addWidget(log_group)

        general_layout.addStretch()
        tabs.addTab(general_tab, "General")

        # ===== Scripting tab =====
        scripting_tab = QWidget()
        scripting_layout = QVBoxLayout(scripting_tab)

        # Macros folder group
        macros_group = QGroupBox("Macros Folder")
        macros_layout = QVBoxLayout(macros_group)

        macros_path_layout = QHBoxLayout()
        self.macros_edit = QLineEdit()
        self.macros_edit.setReadOnly(True)
        btn_macros_browse = QPushButton("Browse...")
        btn_macros_browse.clicked.connect(self._browse_macros)
        macros_path_layout.addWidget(self.macros_edit)
        macros_path_layout.addWidget(btn_macros_browse)
        macros_layout.addLayout(macros_path_layout)

        macros_btn_layout = QHBoxLayout()
        btn_macros_folder = QPushButton("Open Folder")
        btn_macros_folder.clicked.connect(self._open_macros_folder)
        btn_macros_clear = QPushButton("Clear")
        btn_macros_clear.clicked.connect(lambda: self.macros_edit.clear())
        macros_btn_layout.addWidget(btn_macros_folder)
        macros_btn_layout.addWidget(btn_macros_clear)
        macros_btn_layout.addStretch()
        macros_layout.addLayout(macros_btn_layout)
        scripting_layout.addWidget(macros_group)

        # Python interpreter group
        python_group = QGroupBox("Python Interpreter (for REPL)")
        python_layout = QVBoxLayout(python_group)

        python_path_layout = QHBoxLayout()
        self.python_edit = QLineEdit()
        self.python_edit.setReadOnly(True)
        self.python_edit.setPlaceholderText("Default: .venv/Scripts/python.exe")
        btn_python_browse = QPushButton("Browse...")
        btn_python_browse.clicked.connect(self._browse_python)
        python_path_layout.addWidget(self.python_edit)
        python_path_layout.addWidget(btn_python_browse)
        python_layout.addLayout(python_path_layout)

        python_btn_layout = QHBoxLayout()
        btn_python_clear = QPushButton("Clear (Use Default)")
        btn_python_clear.clicked.connect(lambda: self.python_edit.clear())
        python_btn_layout.addWidget(btn_python_clear)
        python_btn_layout.addStretch()
        python_layout.addLayout(python_btn_layout)
        scripting_layout.addWidget(python_group)

        # Startup folder group
        startup_group = QGroupBox("Startup Folder (REPL working directory)")
        startup_layout = QVBoxLayout(startup_group)

        startup_path_layout = QHBoxLayout()
        self.startup_folder_edit = QLineEdit()
        self.startup_folder_edit.setReadOnly(True)
        self.startup_folder_edit.setPlaceholderText("Default: temporary directory")
        btn_startup_browse = QPushButton("Browse...")
        btn_startup_browse.clicked.connect(self._browse_startup_folder)
        startup_path_layout.addWidget(self.startup_folder_edit)
        startup_path_layout.addWidget(btn_startup_browse)
        startup_layout.addLayout(startup_path_layout)

        startup_btn_layout = QHBoxLayout()
        btn_startup_folder = QPushButton("Open Folder")
        btn_startup_folder.clicked.connect(self._open_startup_folder)
        btn_startup_clear = QPushButton("Clear (Use Temp)")
        btn_startup_clear.clicked.connect(lambda: self.startup_folder_edit.clear())
        startup_btn_layout.addWidget(btn_startup_folder)
        startup_btn_layout.addWidget(btn_startup_clear)
        startup_btn_layout.addStretch()
        startup_layout.addLayout(startup_btn_layout)
        scripting_layout.addWidget(startup_group)

        scripting_layout.addStretch()
        tabs.addTab(scripting_tab, "Scripting")

        # ===== InfluxDB tab =====
        influx_tab = QWidget()
        influx_layout = QVBoxLayout(influx_tab)

        # Enable checkbox
        self.influx_enabled_cb = QCheckBox("Enable InfluxDB integration")
        influx_layout.addWidget(self.influx_enabled_cb)

        # Connection group
        influx_conn_group = QGroupBox("Connection")
        influx_conn_layout = QFormLayout(influx_conn_group)

        self.influx_url_edit = QLineEdit()
        self.influx_url_edit.setPlaceholderText("http://localhost:8086")
        influx_conn_layout.addRow("URL:", self.influx_url_edit)

        self.influx_token_edit = QLineEdit()
        self.influx_token_edit.setEchoMode(QLineEdit.Password)
        influx_conn_layout.addRow("Token:", self.influx_token_edit)

        self.influx_org_edit = QLineEdit()
        influx_conn_layout.addRow("Organization:", self.influx_org_edit)

        self.influx_bucket_edit = QLineEdit()
        influx_conn_layout.addRow("Bucket:", self.influx_bucket_edit)

        influx_layout.addWidget(influx_conn_group)

        # Executable group
        influx_exe_group = QGroupBox("InfluxDB Executable (auto-start)")
        influx_exe_layout = QVBoxLayout(influx_exe_group)

        influx_exe_path_layout = QHBoxLayout()
        self.influx_exe_edit = QLineEdit()
        self.influx_exe_edit.setReadOnly(True)
        self.influx_exe_edit.setPlaceholderText("Not configured (no auto-start)")
        btn_influx_exe_browse = QPushButton("Browse...")
        btn_influx_exe_browse.clicked.connect(self._browse_influx_exe)
        btn_influx_exe_clear = QPushButton("Clear")
        btn_influx_exe_clear.clicked.connect(lambda: self.influx_exe_edit.clear())
        influx_exe_path_layout.addWidget(self.influx_exe_edit)
        influx_exe_path_layout.addWidget(btn_influx_exe_browse)
        influx_exe_path_layout.addWidget(btn_influx_exe_clear)
        influx_exe_layout.addLayout(influx_exe_path_layout)

        self.influx_stop_on_exit_cb = QCheckBox("Stop InfluxDB when launcher exits")
        influx_exe_layout.addWidget(self.influx_stop_on_exit_cb)

        influx_layout.addWidget(influx_exe_group)

        # Tuning group
        influx_tuning_group = QGroupBox("Tuning")
        influx_tuning_layout = QFormLayout(influx_tuning_group)

        self.influx_batch_size_spin = QSpinBox()
        self.influx_batch_size_spin.setRange(1, 10000)
        influx_tuning_layout.addRow("Batch size:", self.influx_batch_size_spin)

        self.influx_flush_interval_spin = QSpinBox()
        self.influx_flush_interval_spin.setRange(100, 60000)
        self.influx_flush_interval_spin.setSuffix(" ms")
        influx_tuning_layout.addRow("Flush interval:", self.influx_flush_interval_spin)

        self.influx_max_retries_spin = QSpinBox()
        self.influx_max_retries_spin.setRange(0, 20)
        influx_tuning_layout.addRow("Max retries:", self.influx_max_retries_spin)

        self.influx_snapshot_interval_spin = QDoubleSpinBox()
        self.influx_snapshot_interval_spin.setRange(0.1, 3600.0)
        self.influx_snapshot_interval_spin.setDecimals(1)
        self.influx_snapshot_interval_spin.setSuffix(" s")
        influx_tuning_layout.addRow("Snapshot interval:", self.influx_snapshot_interval_spin)

        influx_layout.addWidget(influx_tuning_group)

        influx_layout.addStretch()
        tabs.addTab(influx_tab, "InfluxDB")

        # ===== Custom GUIs tab =====
        guis_tab = QWidget()
        guis_layout = QVBoxLayout(guis_tab)

        self.guis_table = QTableWidget(0, 3)
        self.guis_table.setHorizontalHeaderLabels(["Device ID", "Route", "Dist Path"])
        self.guis_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.guis_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.guis_table.setSelectionMode(QAbstractItemView.SingleSelection)
        guis_layout.addWidget(self.guis_table)

        guis_btn_layout = QHBoxLayout()
        btn_gui_add = QPushButton("Add")
        btn_gui_add.clicked.connect(self._add_custom_gui)
        btn_gui_remove = QPushButton("Remove")
        btn_gui_remove.clicked.connect(self._remove_custom_gui)
        btn_gui_browse_dist = QPushButton("Browse Dist...")
        btn_gui_browse_dist.clicked.connect(self._browse_gui_dist)
        guis_btn_layout.addWidget(btn_gui_add)
        guis_btn_layout.addWidget(btn_gui_remove)
        guis_btn_layout.addWidget(btn_gui_browse_dist)
        guis_btn_layout.addStretch()
        guis_layout.addLayout(guis_btn_layout)

        guis_layout.addStretch()
        tabs.addTab(guis_tab, "Custom GUIs")

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        self.btn_restart = QPushButton("(Re)Start Server")
        self.btn_restart.clicked.connect(self._apply_and_restart)
        self.btn_restart.setDefault(True)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_restart)
        layout.addLayout(btn_layout)

    def _load_current_values(self):
        cfg = self.launcher.cfg
        self.host_edit.setText(cfg.server.host)
        self.port_edit.setText(str(cfg.server.port))
        self.max_workers_spin.setValue(cfg.server.max_workers)
        self.config_edit.setText(str(cfg.devices_path) if cfg.devices_path else "")
        self.profile_edit.setText(str(cfg.profile_path) if cfg.profile_path else "")
        self.macros_edit.setText(str(cfg.macros_path) if cfg.macros_path else "")
        self.python_edit.setText(str(cfg.python_path) if cfg.python_path else "")
        self.startup_folder_edit.setText(
            str(cfg.startup_folder_path) if cfg.startup_folder_path else ""
        )

        level = cfg.logging.level
        if level and level in LOG_LEVELS:
            self.log_level_combo.setCurrentText(level)
        else:
            self.log_level_combo.setCurrentText("INFO")

        self.log_file_edit.setText(cfg.logging.file or "")

        # InfluxDB tab
        influx = cfg.influx
        self.influx_enabled_cb.setChecked(influx.enabled)
        self.influx_url_edit.setText(influx.url)
        self.influx_token_edit.setText(influx.token)
        self.influx_org_edit.setText(influx.org)
        self.influx_bucket_edit.setText(influx.bucket)
        self.influx_exe_edit.setText(influx.exe_path or "")
        self.influx_stop_on_exit_cb.setChecked(influx.stop_on_exit)
        self.influx_batch_size_spin.setValue(influx.batch_size)
        self.influx_flush_interval_spin.setValue(influx.flush_interval_ms)
        self.influx_max_retries_spin.setValue(influx.max_retries)
        self.influx_snapshot_interval_spin.setValue(influx.snapshot_interval)

        # Custom GUIs tab
        self.guis_table.setRowCount(0)
        for gui in cfg.custom_guis:
            row = self.guis_table.rowCount()
            self.guis_table.insertRow(row)
            self.guis_table.setItem(row, 0, QTableWidgetItem(gui.device_id))
            self.guis_table.setItem(row, 1, QTableWidgetItem(gui.route))
            self.guis_table.setItem(row, 2, QTableWidgetItem(gui.dist))

    def _browse_config(self):
        start_dir = (
            str(Path(self.config_edit.text()).parent)
            if self.config_edit.text()
            else str(LABHUB_DIR / "launcher")
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select config.yaml",
            start_dir,
            "YAML Files (*.yaml *.yml);;All Files (*)",
        )
        if file_path:
            self.config_edit.setText(file_path)

    def _browse_profile(self):
        start_dir = (
            str(Path(self.profile_edit.text()).parent)
            if self.profile_edit.text()
            else str(LABHUB_DIR / "launcher")
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select profile.yaml",
            start_dir,
            "YAML Files (*.yaml *.yml);;All Files (*)",
        )
        if file_path:
            self.profile_edit.setText(file_path)

    def _browse_log_file(self):
        start_dir = (
            str(Path(self.log_file_edit.text()).parent)
            if self.log_file_edit.text()
            else str(LABHUB_DIR)
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Select log file", start_dir, "Log Files (*.log *.txt);;All Files (*)"
        )
        if file_path:
            self.log_file_edit.setText(file_path)

    def _edit_config(self):
        if self.config_edit.text():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.config_edit.text()))

    def _open_config_folder(self):
        if self.config_edit.text():
            folder = str(Path(self.config_edit.text()).parent.resolve())
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _edit_profile(self):
        if self.profile_edit.text():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.profile_edit.text()))

    def _open_profile_folder(self):
        if self.profile_edit.text():
            folder = str(Path(self.profile_edit.text()).parent.resolve())
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _browse_macros(self):
        start_dir = (
            str(self.macros_edit.text())
            if self.macros_edit.text()
            else str(LABHUB_DIR / "launcher" / "macros")
        )
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Macros Folder", start_dir
        )
        if folder_path:
            self.macros_edit.setText(folder_path)

    def _browse_python(self):
        start_dir = (
            str(Path(self.python_edit.text()).parent)
            if self.python_edit.text()
            else str(LABHUB_DIR / ".venv" / "Scripts")
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Python Interpreter",
            start_dir,
            "Python Executable (python.exe);;All Files (*.*)",
        )
        if file_path:
            self.python_edit.setText(file_path)

    def _open_macros_folder(self):
        if self.macros_edit.text():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.macros_edit.text()))

    def _browse_startup_folder(self):
        start_dir = (
            str(self.startup_folder_edit.text())
            if self.startup_folder_edit.text()
            else str(LABHUB_DIR)
        )
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Startup Folder", start_dir
        )
        if folder_path:
            self.startup_folder_edit.setText(folder_path)

    def _open_startup_folder(self):
        if self.startup_folder_edit.text():
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(self.startup_folder_edit.text())
            )

    def _browse_influx_exe(self):
        start_dir = (
            str(Path(self.influx_exe_edit.text()).parent)
            if self.influx_exe_edit.text()
            else str(LABHUB_DIR)
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select influxd executable", start_dir,
            "Executable (influxd.exe influxd);;All Files (*)",
        )
        if file_path:
            self.influx_exe_edit.setText(file_path)

    def _add_custom_gui(self):
        row = self.guis_table.rowCount()
        self.guis_table.insertRow(row)
        self.guis_table.setItem(row, 0, QTableWidgetItem(""))
        self.guis_table.setItem(row, 1, QTableWidgetItem("/"))
        self.guis_table.setItem(row, 2, QTableWidgetItem(""))
        self.guis_table.setCurrentCell(row, 0)

    def _remove_custom_gui(self):
        row = self.guis_table.currentRow()
        if row >= 0:
            self.guis_table.removeRow(row)

    def _browse_gui_dist(self):
        row = self.guis_table.currentRow()
        if row < 0:
            return
        current = (self.guis_table.item(row, 2) or QTableWidgetItem("")).text()
        start_dir = current if current else str(LABHUB_DIR)
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select GUI dist folder", start_dir,
        )
        if folder_path:
            self.guis_table.setItem(row, 2, QTableWidgetItem(folder_path))

    def _apply_and_restart(self):
        # Validate
        try:
            port = int(self.port_edit.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid Port", "Port must be a number.")
            return

        config_path = self.config_edit.text()
        if not config_path or not Path(config_path).exists():
            QMessageBox.warning(
                self, "Invalid Config", "Please select a valid config file."
            )
            return

        # Update ServerConfig fields
        cfg = self.launcher.cfg
        cfg.server.host = self.host_edit.text()
        cfg.server.port = port
        cfg.server.max_workers = self.max_workers_spin.value()
        cfg.devices = config_path
        cfg.profile = self.profile_edit.text() or "./profile.yaml"
        cfg.logging.level = self.log_level_combo.currentText()
        cfg.logging.file = self.log_file_edit.text() or None
        cfg.scripting.macros = self.macros_edit.text() or None
        cfg.scripting.python = self.python_edit.text() or None
        cfg.scripting.startup_folder = self.startup_folder_edit.text() or None

        # InfluxDB settings
        cfg.influx.enabled = self.influx_enabled_cb.isChecked()
        cfg.influx.url = self.influx_url_edit.text() or "http://localhost:8086"
        cfg.influx.token = self.influx_token_edit.text()
        cfg.influx.org = self.influx_org_edit.text() or "labhub"
        cfg.influx.bucket = self.influx_bucket_edit.text() or "labhub"
        cfg.influx.exe_path = self.influx_exe_edit.text() or None
        cfg.influx.stop_on_exit = self.influx_stop_on_exit_cb.isChecked()
        cfg.influx.batch_size = self.influx_batch_size_spin.value()
        cfg.influx.flush_interval_ms = self.influx_flush_interval_spin.value()
        cfg.influx.max_retries = self.influx_max_retries_spin.value()
        cfg.influx.snapshot_interval = self.influx_snapshot_interval_spin.value()

        # Custom GUIs
        cfg.custom_guis = []
        for row in range(self.guis_table.rowCount()):
            device_id = (self.guis_table.item(row, 0) or QTableWidgetItem("")).text().strip()
            route = (self.guis_table.item(row, 1) or QTableWidgetItem("")).text().strip()
            dist = (self.guis_table.item(row, 2) or QTableWidgetItem("")).text().strip()
            if device_id and route and dist:
                cfg.custom_guis.append(CustomGuiEntry(
                    device_id=device_id, route=route, dist=dist,
                ))

        # Re-resolve paths and update convenience attribute
        cfg._resolve_paths()
        self.launcher.host_full = f"http://{cfg.server.host}:{cfg.server.port}"

        # Persist to server.yaml
        save_server_config(cfg)

        # Restart server
        self.launcher.stop_server(silent=True)
        self.launcher.start_server()

        self.accept()


class Launcher:
    def __init__(self, server_config: ServerConfig, disable_influx: bool = False):
        self.cfg = server_config
        self.host_full = f"http://{self.cfg.server.host}:{self.cfg.server.port}"

        # InfluxDB management
        self.disable_influx = disable_influx
        self.influx_proc: Optional[subprocess.Popen] = None

        self.app = QApplication(sys.argv)
        QApplication.setQuitOnLastWindowClosed(False)

        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(
                None, "LabHub", "System tray not available on this system."
            )
            sys.exit(1)

        # Single-instance guard (per server.yaml path key)
        self._launcher_key = f"labhub_tray_{hashlib.sha256(str(self.cfg.config_file).encode('utf-8')).hexdigest()[:12]}"
        try:
            QLocalServer.removeServer(self._launcher_key)
        except Exception:
            pass
        self._server = QLocalServer(self.app)
        if not self._server.listen(self._launcher_key):
            sock = QLocalSocket()
            sock.connectToServer(self._launcher_key)
            if sock.waitForConnected(200):
                sock.write(b"show")
                sock.flush()
                sock.waitForBytesWritten(200)
                sock.disconnectFromServer()
            sys.exit(0)
        self._server.newConnection.connect(self._on_new_connection)

        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray.fromBase64(icon_green_base64))
        self.icon_green = QIcon(pixmap)

        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray.fromBase64(icon_red_base64))
        self.icon_red = QIcon(pixmap)

        self.tray = QSystemTrayIcon(self.icon_red, self.app)
        self.menu = QMenu()
        self.proc: Optional[subprocess.Popen] = None
        self._build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip("LabHub launcher")
        self.tray.activated.connect(self._on_launcher_activated)
        self.tray.show()
        self._set_icon_from_server()

        # Start server when program is created
        self.start_server()

    def _on_launcher_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.menu.popup(QCursor.pos())

    # ======= InfluxDB Management =======

    def _check_influxdb_health(self, url: str, timeout: float = 2.0) -> bool:
        """Check if InfluxDB is healthy via /health endpoint."""
        try:
            r = httpx.get(f"{url}/health", timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                return data.get("status") == "pass"
            return False
        except Exception:
            return False

    def _start_influxdb(self) -> bool:
        """Start InfluxDB if configured and not running. Returns True if OK to proceed."""
        if self.disable_influx:
            logger.info("InfluxDB disabled via --no-influx flag")
            return True

        influx = self.cfg.influx
        if not influx.enabled:
            return True

        url = influx.url
        exe_path = influx.exe_path

        if self._check_influxdb_health(url):
            logger.info(f"InfluxDB already running at {url}")
            return True

        if not exe_path:
            logger.warning(f"InfluxDB not running at {url} and no exe_path configured")
            self.tray.showMessage(
                "LabHub",
                "InfluxDB not running and no exe_path configured. Telemetry disabled.",
                QSystemTrayIcon.Warning,
                3000,
            )
            return True

        exe_path = Path(exe_path)
        if not exe_path.exists():
            logger.error(f"InfluxDB executable not found: {exe_path}")
            self.tray.showMessage(
                "LabHub",
                f"InfluxDB executable not found: {exe_path}",
                QSystemTrayIcon.Warning,
                3000,
            )
            return True

        logger.info(f"Starting InfluxDB from {exe_path}...")
        try:
            self.influx_proc = subprocess.Popen(
                [str(exe_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            for _ in range(30):
                time.sleep(1)
                if self._check_influxdb_health(url):
                    logger.info("InfluxDB started successfully")
                    return True

                if self.influx_proc.poll() is not None:
                    logger.error("InfluxDB process exited unexpectedly")
                    self.tray.showMessage(
                        "LabHub",
                        "InfluxDB process exited unexpectedly. Telemetry disabled.",
                        QSystemTrayIcon.Warning,
                        3000,
                    )
                    return True

            logger.error("InfluxDB failed to become healthy within timeout")
            self.tray.showMessage(
                "LabHub",
                "InfluxDB failed to start. Telemetry disabled.",
                QSystemTrayIcon.Warning,
                3000,
            )
            return True

        except Exception as e:
            logger.error(f"Failed to start InfluxDB: {e}")
            self.tray.showMessage(
                "LabHub",
                f"Failed to start InfluxDB: {e}",
                QSystemTrayIcon.Warning,
                3000,
            )
            return True

    def _stop_influxdb(self):
        """Stop InfluxDB if we started it and stop_on_exit is enabled."""
        if not self.influx_proc or self.influx_proc.poll() is not None:
            return

        if not self.cfg.influx.stop_on_exit:
            logger.info("InfluxDB stop_on_exit=False, leaving InfluxDB running")
            return

        logger.info("Stopping InfluxDB...")
        try:
            self.influx_proc.terminate()
            self.influx_proc.wait(timeout=10)
            logger.info("InfluxDB stopped")
        except subprocess.TimeoutExpired:
            self.influx_proc.kill()
            logger.warning("InfluxDB killed after timeout")
        except Exception as e:
            logger.warning(f"Error stopping InfluxDB: {e}")

    def _on_new_connection(self):
        sock = self._server.nextPendingConnection()
        if sock and sock.waitForReadyRead(200):
            try:
                bytes(sock.readAll()).decode(errors="ignore")
            except Exception:
                pass
            self.tray.showMessage(
                "LabHub", "Launcher already running", QSystemTrayIcon.Information, 1500
            )
        if sock:
            sock.disconnectFromServer()

    def _build_menu(self):
        # Toggle Start/Stop action
        self.act_toggle = QAction("Start Server", self.menu)
        self.act_toggle.triggered.connect(self._toggle_server)

        # Configure action
        self.act_configure = QAction("Configure...", self.menu)
        self.act_configure.triggered.connect(self._open_configure)

        # Main GUI actions
        self.act_launch_gui = QAction("Launch GUI", self.menu)
        self.act_launch_gui.triggered.connect(self.open_gui)

        # Built-in "More" submenu actions
        self.act_old_gui = QAction("Old GUI", self.menu)
        self.act_old_gui.triggered.connect(self.open_old_gui)

        self.act_admin_gui = QAction("Devices", self.menu)
        self.act_admin_gui.triggered.connect(self.open_admin_gui)

        self.act_profile_gui = QAction("Profile", self.menu)
        self.act_profile_gui.triggered.connect(self.open_profile_gui)

        self.act_docs = QAction("Open API Docs", self.menu)
        self.act_docs.triggered.connect(self.open_docs)

        # Quit action
        self.act_quit = QAction("Quit", self.menu)
        self.act_quit.triggered.connect(self.quit)

        # Build menu
        self.menu.addAction(self.act_toggle)
        self.menu.addAction(self.act_configure)
        self.menu.addSeparator()
        self.menu.addAction(self.act_launch_gui)

        # Custom GUIs from server.yaml (top-level menu items)
        for gui in self.cfg.custom_guis:
            act = QAction(gui.device_id.capitalize(), self.menu)
            route = gui.route
            act.triggered.connect(
                lambda checked=False, r=route: self._open_custom_gui(r)
            )
            self.menu.addAction(act)

        # "More" submenu
        self.more_menu = QMenu("More", self.menu)
        self.more_menu.addAction(self.act_old_gui)
        self.more_menu.addAction(self.act_admin_gui)
        self.more_menu.addAction(self.act_profile_gui)
        self.more_menu.addAction(self.act_docs)
        self.menu.addMenu(self.more_menu)

        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)

    def _update_toggle_action(self):
        """Update toggle action text based on server status."""
        if self._is_server_running():
            self.act_toggle.setText("Stop Server")
        else:
            self.act_toggle.setText("Start Server")

    def _is_server_running(self) -> bool:
        """Check if server process is running."""
        return self.proc is not None and self.proc.poll() is None

    def _toggle_server(self):
        """Toggle server start/stop."""
        if self._is_server_running():
            self.stop_server()
        else:
            self.start_server()

    def _open_configure(self):
        """Open the configure dialog."""
        dialog = ConfigureDialog(self)
        dialog.exec()
        self._update_toggle_action()

    def _port_available(self, host, port):
        try:
            with socket.create_server((host, port), reuse_port=False):
                return True
        except OSError:
            return False

    def _ping(self, path="/api/v2/devices", timeout=0.4):
        try:
            r = httpx.get(f"{self.host_full}{path}", timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False

    def _wait_server_ready(self, timeout=20.0):
        """Wait until server responds or process dies. Returns (ok, reason_str)."""
        t0 = time.monotonic()
        paths = ["/api/v2/devices", "/docs"]
        i = 0
        while time.monotonic() - t0 < timeout:
            if self.proc and self.proc.poll() is not None:
                return False, "process exited early"
            if self._ping(paths[i % len(paths)]):
                return True, "http ok"
            i += 1
            time.sleep(0.2)
        return False, "timeout waiting for HTTP"

    def start_server(self):
        if self._is_server_running():
            self.tray.showMessage(
                "LabHub", "Server already running", QSystemTrayIcon.Information, 1200
            )
            return

        host = self.cfg.server.host
        port = self.cfg.server.port

        if not self._port_available(host, port):
            self.tray.setIcon(self.icon_red)
            self.tray.setToolTip("LabHub: stopped")
            self.tray.showMessage(
                "LabHub",
                f"Port {port} already in use on {host}.",
                QSystemTrayIcon.Critical,
                2500,
            )
            self._update_toggle_action()
            return

        self._start_influxdb()

        env = os.environ.copy()
        env[ENV_VAR] = str(self.cfg.config_file)

        cwd = str(LABHUB_DIR)

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "server.main:app",
            "--host",
            str(host),
            "--port",
            str(port),
        ]
        try:
            self.proc = subprocess.Popen(cmd, cwd=cwd, env=env)

            ok, reason = self._wait_server_ready(timeout=20.0)
            if ok:
                self.tray.setIcon(self.icon_green)
                self.tray.setToolTip("LabHub: running")
                self.tray.showMessage(
                    "LabHub", "Server started successfully", self.icon_green, 1200
                )
            else:
                try:
                    if self.proc and self.proc.poll() is None:
                        self.proc.terminate()
                        self.proc.wait(timeout=3)
                except Exception:
                    try:
                        if self.proc and self.proc.poll() is None:
                            self.proc.kill()
                    except Exception:
                        pass
                self.tray.setIcon(self.icon_red)
                self.tray.setToolTip("LabHub: stopped")
                self.tray.showMessage(
                    "LabHub",
                    f"Failed to start server ({reason}).",
                    QSystemTrayIcon.Critical,
                    6000,
                )

        except Exception as e:
            self.tray.showMessage(
                "LabHub", f"Failed to start server: {e}", QSystemTrayIcon.Critical, 3000
            )

        self._update_toggle_action()

    def stop_server(self, silent=False):
        if not self._is_server_running():
            if not silent:
                self.tray.showMessage(
                    "LabHub", "Server not running", QSystemTrayIcon.Information, 1200
                )
            return
        try:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

            self._stop_influxdb()

            self.tray.setIcon(self.icon_red)
            self.tray.setToolTip("LabHub: stopped")
            if not silent:
                self.tray.showMessage(
                    "LabHub",
                    "Server stopped successfully",
                    QSystemTrayIcon.Information,
                    200,
                )
        except Exception as e:
            if not silent:
                self.tray.showMessage(
                    "LabHub",
                    f"Failed to stop server: {e}",
                    QSystemTrayIcon.Critical,
                    2000,
                )

        self._update_toggle_action()

    def open_docs(self):
        import webbrowser

        webbrowser.open(f"{self.host_full}/docs")

    def open_gui(self):
        import webbrowser

        webbrowser.open(f"{self.host_full}/ui")

    def _open_custom_gui(self, route: str):
        import webbrowser

        webbrowser.open(f"{self.host_full}{route}")

    def open_admin_gui(self):
        import webbrowser

        webbrowser.open(f"{self.host_full}/devices")

    def open_old_gui(self):
        import webbrowser

        webbrowser.open(f"{self.host_full}/v1ui")

    def open_profile_gui(self):
        import webbrowser

        webbrowser.open(f"{self.host_full}/profile")

    def quit(self):
        try:
            if self._is_server_running():
                self.proc.terminate()
        except Exception:
            pass
        self.tray.hide()
        self.app.quit()

    def _set_icon_from_server(self):
        try:
            r = httpx.get(f"{self.host_full}/api/v2/devices", timeout=0.5)
            if r.status_code == 200:
                self.tray.setIcon(self.icon_green)
                self.tray.setToolTip("LabHub: running")
                self._update_toggle_action()
                return
        except Exception:
            pass
        self.tray.setIcon(self.icon_red)
        self.tray.setToolTip("LabHub: stopped")
        self._update_toggle_action()

    def run(self):
        sys.exit(self.app.exec())


def main():
    parser = argparse.ArgumentParser(description="Start LabGlue Hub")
    parser.add_argument(
        "--server-config",
        type=str,
        help="Path to server.yaml (default: launcher/server_default.yaml)",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to device config.yaml (overrides server.yaml)",
    )
    parser.add_argument(
        "--profile",
        type=str,
        help="Path to profile.yaml (overrides server.yaml)",
    )
    parser.add_argument(
        "--macros",
        type=str,
        help="Path to macros folder (overrides server.yaml)",
    )
    parser.add_argument(
        "--python",
        type=str,
        help="Path to Python interpreter for REPL (overrides server.yaml)",
    )
    parser.add_argument(
        "--startup-folder",
        type=str,
        help="Working directory for REPL sessions (overrides server.yaml)",
    )
    parser.add_argument(
        "--host",
        type=str,
        help="Host for the hub server (overrides server.yaml)",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port for the hub server (overrides server.yaml)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=LOG_LEVELS,
        help="Logging level (overrides server.yaml)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        help="Optional path to log file (overrides server.yaml)",
    )
    parser.add_argument(
        "--no-influx",
        action="store_true",
        help="Disable InfluxDB integration even if configured",
    )

    args = parser.parse_args()

    # Load ServerConfig: explicit --server-config > default search paths
    cfg = load_server_config(args.server_config)

    # Apply CLI overrides on top of server.yaml values
    if args.host:
        cfg.server.host = args.host
    if args.port:
        cfg.server.port = args.port
    if args.config:
        cfg.devices = str(Path(args.config).resolve())
    if args.profile:
        cfg.profile = str(Path(args.profile).resolve())
    if args.log_level:
        cfg.logging.level = args.log_level
    if args.log_file:
        cfg.logging.file = args.log_file
    if args.macros:
        cfg.scripting.macros = str(Path(args.macros).resolve())
    if args.python:
        cfg.scripting.python = str(Path(args.python).resolve())
    if args.startup_folder:
        cfg.scripting.startup_folder = str(Path(args.startup_folder).resolve())

    # Re-resolve paths after overrides
    cfg._resolve_paths()

    # Validate device config exists
    if not cfg.devices_path.exists():
        logger.error(f"Device config file not found: {cfg.devices_path}")
        sys.exit(1)

    Launcher(cfg, disable_influx=args.no_influx).run()


if __name__ == "__main__":
    main()
