import sys, subprocess, os, json, threading, time
from pathlib import Path
from typing import Optional
import argparse
import hashlib
import yaml

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox, QListWidget, QDialog, QStyle, QVBoxLayout
from PySide6.QtGui import QIcon, QAction, QPixmap, QDesktopServices, QCursor
from PySide6.QtCore import QTimer, QByteArray, QUrl
from PySide6.QtNetwork import QLocalServer, QLocalSocket
import httpx
import socket

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HUB_DIR = PROJECT_ROOT # / "hub_app"

print(f"project_root is {PROJECT_ROOT}")
print(f"hub_dir is {HUB_DIR}")

icon_green_base64 = b"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"
icon_red_base64 = b"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"




# class StatusDialog(QDialog):
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.setWindowTitle("LabHub – Device Status")
#         self.list = QListWidget()
#         lay = QVBoxLayout(self)
#         lay.addWidget(self.list)
        
#         self.client = httpx.Client(base_url=HUB_HOST, timeout=1.0)
#         self.timer = QTimer(self)
#         self.timer.timeout.connect(self.refresh)
#         self.timer.start(1500)
#         self.refresh()

#     def refresh(self):
#         try:
#             r = self.client.get("/api/v1/devices")
#             devices = r.json()
#             self.list.clear()
#             for d in devices:
#                 st = d.get("state", {})
#                 v = st.get("voltage")
#                 vmax = st.get("maximum_voltage")
#                 extra = []
#                 if v is not None: extra.append(f"V={v:.3f}")
#                 if vmax is not None: extra.append(f"Vmax={vmax}")
#                 self.list.addItem(f"{d['id']}  [{d['kind']}]  {d['status']}  {'  '.join(extra)}")
#         except Exception as e:
#             self.list.clear()
#             self.list.addItem(f"(server offline) {e}")

class TrayApp:
    def __init__(self, host, port, config_path):
        self.host = host
        self.port = port
        self.host_full = f"http://{self.host}:{self.port}"
        self.config_path = config_path
        self.app = QApplication(sys.argv)
        QApplication.setQuitOnLastWindowClosed(False)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "LabHub", "System tray not available on this system.")
            sys.exit(1)
        # Single-instance guard (per-config path key)
        self._tray_key = f"labhub_tray_{hashlib.sha256(str(self.config_path).encode('utf-8')).hexdigest()[:12]}"
        # Clean up stale socket from previous crash
        try:
            QLocalServer.removeServer(self._tray_key)
        except Exception:
            pass
        self._server = QLocalServer(self.app)
        if not self._server.listen(self._tray_key):
            sock = QLocalSocket()
            sock.connectToServer(self._tray_key)
            if sock.waitForConnected(200):
                sock.write(b'show')
                sock.flush(); sock.waitForBytesWritten(200)
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
        self.tray.setToolTip("LabHub controller")
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._set_icon_from_server()

        # start server when program is created
        self.start_server()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        # Left click (single) or double click → open the menu
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.menu.popup(QCursor.pos())

    def _on_new_connection(self):
        sock = self._server.nextPendingConnection()
        if sock and sock.waitForReadyRead(200):
            try:
                cmd = bytes(sock.readAll()).decode(errors='ignore')
            except Exception:
                cmd = ''
            # Bring attention to existing tray
            self.tray.showMessage('LabHub', 'Tray already running', QSystemTrayIcon.Information, 1500)
        if sock:
            sock.disconnectFromServer()

    def _build_menu(self):
        self.act_start = QAction("Start server", self.menu); self.act_start.triggered.connect(self.start_server)
        self.act_stop = QAction("Stop server", self.menu); self.act_stop.triggered.connect(self.stop_server)
        self.act_reload = QAction("Reload config", self.menu); self.act_reload.triggered.connect(self.reload_server)
        self.act_open_cfg = QAction("Open config folder", self.menu); self.act_open_cfg.triggered.connect(self.open_config_folder)
        self.act_edit_cfg = QAction("Edit config", self.menu);   self.act_edit_cfg.triggered.connect(self.edit_config)
        
        #self.act_status = QAction("Show status", self.menu); self.act_status.triggered.connect(self.show_status)
        self.act_docs = QAction("Open API docs", self.menu); self.act_docs.triggered.connect(self.open_docs)
        self.act_launch_gui = QAction("Launch GUI", self.menu); self.act_launch_gui.triggered.connect(self.open_gui)
        self.act_quit = QAction("Quit", self.menu); self.act_quit.triggered.connect(self.quit)
        #for a in (self.act_start, self.act_stop, self.act_reload, self.act_open_cfg, self.act_edit_cfg, self.act_docs, self.act_launch_gui):
        #    self.menu.addAction(a)
        self.menu.addAction(self.act_start)
        self.menu.addAction(self.act_stop)
        self.menu.addSeparator()
        self.menu.addAction(self.act_launch_gui)
        self.menu.addAction(self.act_docs)
        self.menu.addSeparator()
        self.menu.addAction(self.act_open_cfg)
        self.menu.addAction(self.act_edit_cfg)
        self.menu.addAction(self.act_reload)
        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)

    def _port_available(self, host, port, timeout=0.2):
        try:
            with socket.create_server((host, port), reuse_port=False) as s:
                return True
        except OSError:
            return False

    def _ping(self, path="/api/v1/devices", timeout=0.4):
        try:
            r = httpx.get(f"{self.host_full}{path}", timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False

    def _wait_server_ready(self, timeout=6.0):
        """Wait until server responds or process dies. Returns (ok, reason_str)."""
        t0 = time.monotonic()
        # try both API and docs (in case no devices route yet)
        paths = ["/api/v1/devices", "/docs"]
        i = 0
        while time.monotonic() - t0 < timeout:
            # if the child exited, it failed
            if self.proc and self.proc.poll() is not None:
                return False, "process exited early"
            # ping alternating paths
            if self._ping(paths[i % len(paths)]):
                return True, "http ok"
            i += 1
            time.sleep(0.2)
        return False, "timeout waiting for HTTP"

    def start_server(self):
        if self.proc and self.proc.poll() is None:
            self.tray.showMessage("LabHub", "Server already running", QSystemTrayIcon.Information, 1200)
            return
        
        # optional: quick port check helps produce a clearer error
        if not self._port_available(self.host, self.port):
            self.tray.setIcon(self.icon_red)
            self.tray.setToolTip("LabHub: stopped")
            self.tray.showMessage("LabHub", f"Port {self.port} already in use on {self.host}.", QSystemTrayIcon.Critical, 2500)
            return
        
        env = os.environ.copy()
        env["LABHUB_CONFIG"] = str(self.config_path)
        cwd = str(HUB_DIR)

        cmd = [
            sys.executable, "-m", "uvicorn", "hub_app.main:app",
            "--host", str(self.host), "--port", str(self.port)
        ]
        try:
            self.proc = subprocess.Popen(cmd, cwd=cwd, env=env)

            #self.proc = subprocess.Popen(
            #    cmd, cwd=cwd, env=env,
                #stdout=open(self._proc_log_path, "ab", buffering=0),
                #stderr=subprocess.STDOUT,
                #start_new_session=True  # better signal handling on POSIX
            #)

            ok, reason = self._wait_server_ready(timeout=6.0)
            # todo - how do I check that it started correctly??
            if ok:
                self.tray.setIcon(self.icon_green)
                self.tray.setToolTip("LabHub: running")
                self.tray.showMessage("LabHub", "Server started successfully", self.icon_green, 1200)#, icon=icon_green_base64)
            else:
                # process might still be running but not healthy—stop it
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
                    QSystemTrayIcon.Critical, 6000,
                )

        except Exception as e:
            self.tray.showMessage("LabHub", f"Failed to start server: {e}", QSystemTrayIcon.Critical, 3000)

    def stop_server(self):
        if not self.proc or self.proc.poll() is not None:
            self.tray.showMessage("LabHub", "Server not running", QSystemTrayIcon.Information, 1200)
            return
        try:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.tray.setIcon(self.icon_red)
            self.tray.setToolTip("LabHub: stopped")
            self.tray.showMessage("LabHub", "Server stopped successfully", QSystemTrayIcon.Information, 200)
        except Exception as e:
            self.tray.showMessage("LabHub", f"Failed to stop server: {e}", QSystemTrayIcon.Critical, 2000)
        

    def reload_server(self):
        print(" -- reloading") # todo check if server is running and not do this if not
        try:
            r = httpx.post(f"{self.host_full}/api/v1/admin/reload", timeout=2.0)
            if r.status_code == 200:
                self.tray.showMessage("LabHub", "Reloaded config.yaml", QSystemTrayIcon.Information, 1200)
            else:
                self.tray.showMessage("LabHub", f"Reload failed: {r.status_code} {r.text}", QSystemTrayIcon.Warning, 2000)
        except Exception as e:
            self.tray.showMessage("LabHub", f"Server not reachable: {e}", QSystemTrayIcon.Warning, 2000)
        print(" --reaload done")

    #def show_status(self):
    #    dlg = StatusDialog()
    #    dlg.exec()

    def open_docs(self):
        import webbrowser
        webbrowser.open(f"{self.host_full}/docs")

    def open_gui(self):
        import webbrowser
        webbrowser.open(f"{self.host_full}/ui")

    def open_config_folder(self):
        try:
            folder = str(Path(self.config_path).parent.resolve())
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        except Exception as e:
            self.tray.showMessage("LabHub", f"Open folder failed: {e}", QSystemTrayIcon.Warning, 2500)

    def edit_config(self):
        try:
            cfg = str(Path(self.config_path).resolve())
            QDesktopServices.openUrl(QUrl.fromLocalFile(cfg))  # opens with default editor
        except Exception as e:
            self.tray.showMessage("LabHub", f"Open file failed: {e}", QSystemTrayIcon.Warning, 2500)

    def quit(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass
        self.tray.hide()
        self.app.quit()

    def _set_icon_from_server(self):
        try:
            r = httpx.get(f"{self.host_full}/api/v1/devices", timeout=0.5)
            if r.status_code == 200:
                self.tray.setIcon(self.icon_green)
                self.tray.setToolTip('LabHub: running')
                return
        except Exception:
            pass
        self.tray.setIcon(self.icon_red)
        self.tray.setToolTip('LabHub: stopped')

    def run(self):
        sys.exit(self.app.exec())

def main():
    parser = argparse.ArgumentParser(description="Start LabGlue Hub")
    parser.add_argument("--config", type=str, help="Path to config.yaml")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host for the hub server, default is 127.0.0.1 (localhost)")
    parser.add_argument("--port", type=int, default=8212, help="Port for the hub server, default is 8212")
    args = parser.parse_args()

    # Determine config path
    if args.config:
        config_path = Path(args.config)
    else:
        config_path = Path(__file__).parent.parent / "config.yaml"
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        sys.exit(1)

    TrayApp(args.host, args.port, config_path).run()

if __name__ == "__main__":
    main()