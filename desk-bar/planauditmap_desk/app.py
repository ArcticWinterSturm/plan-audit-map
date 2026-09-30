from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from .config import APP_NAME, AppConfig, ensure_config
from .storage import DeskDatabase, LaunchRecord, parse_ts


def run_desk_app(config_path: str = "") -> int:
    try:
        from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, QObject, Signal
        from PySide6.QtGui import QAction, QCloseEvent, QIcon, QMouseEvent
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        from PySide6.QtWidgets import (
            QApplication,
            QFrame,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMenu,
            QPushButton,
            QSystemTrayIcon,
            QVBoxLayout,
            QWidget,
            QStyle,
        )
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is required for the desk bar UI. Install it with: pip install PySide6"
        ) from exc

    cfg = ensure_config(config_path or None)
    db = DeskDatabase(cfg.db_path)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    class InstanceBridge(QObject):
        message_received = Signal(str)

        def __init__(self, config: AppConfig) -> None:
            super().__init__()
            self.config = config
            self.server_name = "planauditmap-desk-bar"
            self.server = QLocalServer()
            self.server.newConnection.connect(self._consume)

        def claim_primary(self) -> bool:
            if not self.config.data.get("single_instance", True):
                return True
            if self.server.listen(self.server_name):
                return True
            QLocalServer.removeServer(self.server_name)
            return self.server.listen(self.server_name)

        def notify_existing(self, message: str) -> bool:
            sock = QLocalSocket()
            sock.connectToServer(self.server_name)
            if not sock.waitForConnected(300):
                return False
            sock.write(message.encode("utf-8"))
            sock.flush()
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return True

        def _consume(self) -> None:
            while self.server.hasPendingConnections():
                sock = self.server.nextPendingConnection()
                sock.waitForReadyRead(250)
                raw = bytes(sock.readAll()).decode("utf-8", errors="ignore")
                self.message_received.emit(raw or "show")
                sock.disconnectFromServer()

    bridge = InstanceBridge(cfg)
    if cfg.data.get("single_instance", True):
        if not bridge.claim_primary():
            if bridge.notify_existing("show"):
                return 0
            raise SystemExit("Could not create or notify the primary desk bar instance.")

    class HeaderFrame(QFrame):
        def __init__(self, window: "DeskBarWindow") -> None:
            super().__init__(window)
            self.window = window
            self._drag_origin: Optional[QPoint] = None
            self.setObjectName("HeaderFrame")

        def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
            if event.button() == Qt.MouseButton.LeftButton:
                self.window.minimize_to_taskbar()
                event.accept()
                return
            super().mouseDoubleClickEvent(event)

        def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_origin = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
            if self._drag_origin is not None and bool(self.window.config.data["window"].get("frameless", False)):
                self.window.move(event.globalPosition().toPoint() - self._drag_origin)
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
            self._drag_origin = None
            super().mouseReleaseEvent(event)

    class DeskBarWindow(QMainWindow):
        def __init__(self, config: AppConfig, database: DeskDatabase) -> None:
            super().__init__()
            self.config = config
            self.db = database
            self.setObjectName("DeskBarWindow")
            self.setWindowTitle(APP_NAME)
            self.setMinimumSize(
                int(self.config.data["window"].get("width", 460)),
                int(self.config.data["window"].get("height", 720)),
            )
            self.resize(
                int(self.config.data["window"].get("width", 460)),
                int(self.config.data["window"].get("height", 720)),
            )
            self._apply_window_flags()
            self._build_ui()
            self._apply_styles()
            self._restore_geometry()
            self.refresh_data(mark_seen=False)
            self._setup_tray()

        def _apply_window_flags(self) -> None:
            flags = Qt.WindowType.Window
            if bool(self.config.data["window"].get("frameless", False)):
                flags |= Qt.WindowType.FramelessWindowHint
            if bool(self.config.data["window"].get("always_on_top", False)):
                flags |= Qt.WindowType.WindowStaysOnTopHint
            self.setWindowFlags(flags)

        def _build_ui(self) -> None:
            root = QWidget(self)
            self.setCentralWidget(root)
            outer = QVBoxLayout(root)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)

            self.header = HeaderFrame(self)
            header_layout = QHBoxLayout(self.header)
            header_layout.setContentsMargins(14, 12, 10, 12)
            title_box = QVBoxLayout()
            title = QLabel("MapThinkDo Desk Bar")
            title.setObjectName("Title")
            subtitle = QLabel("Cross-agent launch and live usage overview")
            subtitle.setObjectName("Subtitle")
            title_box.addWidget(title)
            title_box.addWidget(subtitle)
            header_layout.addLayout(title_box)
            header_layout.addStretch(1)
            self.min_button = QPushButton("_")
            self.min_button.clicked.connect(self.minimize_to_taskbar)
            self.close_button = QPushButton("X")
            self.close_button.clicked.connect(self.close)
            for button in (self.min_button, self.close_button):
                button.setFixedSize(28, 28)
                header_layout.addWidget(button)
            outer.addWidget(self.header)

            body = QWidget()
            body_layout = QHBoxLayout(body)
            body_layout.setContentsMargins(12, 12, 12, 12)
            body_layout.setSpacing(12)

            sidebar = QFrame()
            sidebar.setObjectName("Sidebar")
            sidebar_layout = QVBoxLayout(sidebar)
            sidebar_layout.setContentsMargins(12, 12, 12, 12)
            sidebar_layout.setSpacing(10)

            self.overall_stats = QLabel()
            self.overall_stats.setWordWrap(True)
            self.overall_stats.setObjectName("OverallStats")
            sidebar_layout.addWidget(self.overall_stats)

            side_title = QLabel("Agents")
            side_title.setObjectName("SectionTitle")
            sidebar_layout.addWidget(side_title)
            self.agent_list = QListWidget()
            sidebar_layout.addWidget(self.agent_list, 1)

            actions = QHBoxLayout()
            self.refresh_button = QPushButton("Refresh")
            self.refresh_button.clicked.connect(self.refresh_data)
            self.toggle_button = QPushButton("Minimize")
            self.toggle_button.clicked.connect(self.minimize_to_taskbar)
            actions.addWidget(self.refresh_button)
            actions.addWidget(self.toggle_button)
            sidebar_layout.addLayout(actions)
            body_layout.addWidget(sidebar, 1)

            main = QWidget()
            main_layout = QVBoxLayout(main)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(12)

            cards = QGroupBox("Live state")
            cards_layout = QGridLayout(cards)
            self.card_total_launches = QLabel("0")
            self.card_active = QLabel("0")
            self.card_agents = QLabel("0")
            self.card_last_event = QLabel("No events yet")
            card_pairs = [
                ("Total launches", self.card_total_launches),
                ("Active instances", self.card_active),
                ("Known agents", self.card_agents),
                ("Last event", self.card_last_event),
            ]
            for idx, (label_text, value) in enumerate(card_pairs):
                label = QLabel(label_text)
                label.setObjectName("CardLabel")
                value.setObjectName("CardValue")
                cards_layout.addWidget(label, idx, 0)
                cards_layout.addWidget(value, idx, 1)
            main_layout.addWidget(cards)

            active_group = QGroupBox("Active instances")
            active_layout = QVBoxLayout(active_group)
            self.active_list = QListWidget()
            active_layout.addWidget(self.active_list)
            main_layout.addWidget(active_group, 2)

            recent_group = QGroupBox("Recent launches")
            recent_layout = QVBoxLayout(recent_group)
            self.recent_list = QListWidget()
            recent_layout.addWidget(self.recent_list)
            main_layout.addWidget(recent_group, 3)

            footer = QLabel(f"Config: {self.config.config_path}\nDB: {self.config.db_path}")
            footer.setObjectName("Footer")
            footer.setWordWrap(True)
            main_layout.addWidget(footer)

            body_layout.addWidget(main, 2)
            outer.addWidget(body, 1)

        def _apply_styles(self) -> None:
            self.setStyleSheet(
                """
                QMainWindow#DeskBarWindow { background: #11161f; color: #f4f7fb; }
                QFrame#HeaderFrame { background: #182131; border-bottom: 1px solid #2c3e5a; }
                QFrame#Sidebar { background: #151c28; border: 1px solid #28364d; border-radius: 12px; }
                QLabel#Title { font-size: 18px; font-weight: 700; color: #f4f7fb; }
                QLabel#Subtitle { font-size: 11px; color: #9eb0c7; }
                QLabel#SectionTitle { font-size: 12px; font-weight: 700; color: #b9cae5; }
                QLabel#OverallStats { color: #c8d6ea; line-height: 1.3; }
                QLabel#CardLabel { color: #93a7c3; font-size: 11px; }
                QLabel#CardValue { color: #f4f7fb; font-size: 14px; font-weight: 700; }
                QLabel#Footer { color: #91a3bc; font-size: 10px; }
                QGroupBox {
                    border: 1px solid #28364d;
                    border-radius: 12px;
                    margin-top: 8px;
                    padding-top: 14px;
                    font-weight: 700;
                    color: #dbe7f7;
                    background: #151c28;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 4px;
                }
                QListWidget {
                    background: #101722;
                    border: 1px solid #28364d;
                    border-radius: 10px;
                    padding: 6px;
                    color: #edf4ff;
                }
                QListWidget::item {
                    padding: 8px 6px;
                    border-radius: 8px;
                }
                QListWidget::item:selected {
                    background: #22314a;
                }
                QPushButton {
                    background: #21314a;
                    color: #f4f7fb;
                    border: 1px solid #2d4264;
                    border-radius: 8px;
                    padding: 8px 10px;
                }
                QPushButton:hover { background: #274068; }
                QPushButton:pressed { background: #1b2a40; }
                """
            )

        def _setup_tray(self) -> None:
            self.tray: Optional[QSystemTrayIcon] = None
            if not QSystemTrayIcon.isSystemTrayAvailable():
                return
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            self.setWindowIcon(icon)
            tray = QSystemTrayIcon(icon, self)
            tray.setToolTip(APP_NAME)
            menu = QMenu(self)
            show_action = QAction("Show desk bar", self)
            show_action.triggered.connect(self.show_popup)
            hide_action = QAction("Minimize to taskbar", self)
            hide_action.triggered.connect(self.minimize_to_taskbar)
            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(QApplication.instance().quit)
            menu.addAction(show_action)
            menu.addAction(hide_action)
            menu.addSeparator()
            menu.addAction(quit_action)
            tray.setContextMenu(menu)
            tray.activated.connect(self._on_tray_activated)
            tray.show()
            self.tray = tray

        def _on_tray_activated(self, reason: Any) -> None:
            if self.tray is None:
                return
            if reason in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick,
            ):
                self.toggle_visible_state()

        def _restore_geometry(self) -> None:
            if not bool(self.config.data["window"].get("remember_geometry", True)):
                self.position_to_corner()
                return
            raw = self.db.get_state("window_geometry", "")
            if raw:
                try:
                    payload = json.loads(raw)
                    rect = QRect(
                        int(payload["x"]),
                        int(payload["y"]),
                        int(payload["w"]),
                        int(payload["h"]),
                    )
                    self.setGeometry(rect)
                    return
                except Exception:
                    pass
            self.position_to_corner()

        def _save_geometry(self) -> None:
            rect = self.geometry()
            payload = {
                "x": rect.x(),
                "y": rect.y(),
                "w": rect.width(),
                "h": rect.height(),
            }
            self.db.set_state("window_geometry", json.dumps(payload))

        def position_to_corner(self) -> None:
            screen = self.screen() or QApplication.primaryScreen()
            if screen is None:
                return
            available = screen.availableGeometry()
            margin_x = int(self.config.data["window"].get("margin_x", 24))
            margin_y = int(self.config.data["window"].get("margin_y", 24))
            x = available.right() - self.width() - margin_x
            y = available.bottom() - self.height() - margin_y
            self.move(max(available.left() + 4, x), max(available.top() + 4, y))

        def show_popup(self) -> None:
            self.refresh_data(mark_seen=True)
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            self.show()
            self.raise_()
            self.activateWindow()
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.show()
            self.position_to_corner()

        def minimize_to_taskbar(self) -> None:
            self.showMinimized()

        def toggle_visible_state(self) -> None:
            if self.isVisible() and not self.isMinimized():
                self.minimize_to_taskbar()
            else:
                self.show_popup()

        def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
            self._save_geometry()
            event.accept()
            QApplication.instance().quit()

        def changeEvent(self, event: QEvent) -> None:  # noqa: N802
            if event.type() == QEvent.Type.WindowStateChange:
                self._save_geometry()
            super().changeEvent(event)

        def refresh_data(self, mark_seen: bool = True) -> None:
            live_timeout = int(self.config.live_timeout_seconds)
            active = self.db.active_launches(live_timeout)
            recent = self.db.recent_launches(30)
            summaries = self.db.agent_summaries(live_timeout)
            latest_id = self.db.latest_launch_id()

            total_launches = len(recent) if latest_id < len(recent) else latest_id
            self.card_total_launches.setText(str(total_launches))
            self.card_active.setText(str(len(active)))
            self.card_agents.setText(str(len(summaries)))
            self.card_last_event.setText(recent[0].started_at if recent else "No events yet")

            stats_lines = [
                f"Window stays available in the taskbar.",
                f"Double-click the header to minimize.",
                f"Live timeout: {live_timeout}s",
                f"Latest launch id: {latest_id}",
            ]
            self.overall_stats.setText("\n".join(stats_lines))

            self.agent_list.clear()
            for summary in summaries:
                text = (
                    f"{summary['agent']}\n"
                    f"Launches: {summary['launch_count']}  Live: {summary['active_count']}"
                )
                item = QListWidgetItem(text)
                self.agent_list.addItem(item)

            self.active_list.clear()
            counts: dict[str, int] = defaultdict(int)
            for row in active:
                counts[row.agent] += 1
                instance_no = counts[row.agent]
                started = row.started_at.replace("+0000", "Z")
                line = (
                    f"Instance {instance_no} · {row.agent}\n"
                    f"cwd: {row.cwd or row.project_path}\n"
                    f"venv: {row.venv_path or '(system)'}\n"
                    f"started: {started}"
                )
                self.active_list.addItem(QListWidgetItem(line))
            if not active:
                self.active_list.addItem(QListWidgetItem("No live agent instances right now."))

            self.recent_list.clear()
            for row in recent:
                status = "live" if row.ended_at is None else f"exit={row.exit_code}"
                text = (
                    f"#{row.id} · {row.agent} · {status}\n"
                    f"{row.started_at.replace('+0000', 'Z')}\n"
                    f"{row.command or row.cwd or row.project_path}"
                )
                self.recent_list.addItem(QListWidgetItem(text))
            if not recent:
                self.recent_list.addItem(QListWidgetItem("No launch history yet."))

            if mark_seen:
                self.db.set_state("last_seen_launch_id", str(latest_id))

        def poll_for_updates(self) -> None:
            previous = int(self.db.get_state("last_seen_launch_id", "0") or "0")
            latest = self.db.latest_launch_id()
            if latest > previous:
                self.refresh_data(mark_seen=True)
                if bool(self.config.data.get("show_on_new_launch", True)):
                    self.show_popup()
            else:
                self.refresh_data(mark_seen=False)

    window = DeskBarWindow(cfg, db)
    bridge.message_received.connect(lambda message: window.show_popup())

    timer = QTimer()
    timer.timeout.connect(window.poll_for_updates)
    timer.start(cfg.poll_interval_ms)

    if not bool(cfg.data["window"].get("start_minimized", False)):
        window.show_popup()
    else:
        window.showMinimized()

    return app.exec()
