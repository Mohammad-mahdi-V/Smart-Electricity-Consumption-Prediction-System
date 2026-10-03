"""control_panel/app.py

Main application shell for the PySide6 + qfluentwidgets Control Panel.

Uses qfluentwidgets.FluentWindow as the native Fluent shell.

Responsibilities:
- Fluent Windows-style main window
- Fluent navigation
- Lazy page construction/caching
- Page routing
- Status bar
- Theme propagation
- Global error presentation

Business logic and services remain outside this module.
"""

from __future__ import annotations

import traceback
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    FluentIcon as FIF,
    FluentWindow,
    MessageBox,
    NavigationItemPosition,
    PushButton,
)

from .theme import Theme


PAGE_REGISTRY = {
    "dashboard": ("pages.dashboard", "DashboardPage"),
    "errors": ("pages.errors", "ErrorsPage"),
    "models": ("pages.models", "ModelsPage"),
    "users": ("pages.users", "UsersPage"),
    "predictions": ("pages.predictions", "PredictionsPage"),
    "model_builder": ("pages.model_builder", "ModelBuilderPage"),
    "script_runner": ("pages.script_runner", "ScriptRunnerPage"),
    "scheduler": ("pages.scheduler", "SchedulerPage"),
    "system_log": ("pages.system_log", "SystemLogPage"),
    "setup": ("pages.setup", "SetupPage"),
}


PAGE_TITLES = {
    "dashboard": "Dashboard",
    "errors": "Errors",
    "models": "Models",
    "users": "Devices",
    "predictions": "Predictions",
    "model_builder": "Model Builder",
    "script_runner": "Script Runner",
    "scheduler": "Scheduler",
    "system_log": "System Log",
    "setup": "Setup",
}


PAGE_ICONS = {
    "dashboard": FIF.HOME,
    "errors": FIF.INFO,
    "models": FIF.APPLICATION,
    "users": FIF.PEOPLE,
    "predictions": FIF.CALENDAR,
    "model_builder": FIF.ADD,
    "script_runner": FIF.COMMAND_PROMPT,
    "scheduler": FIF.SYNC,
    "system_log": FIF.DOCUMENT,
    "setup": FIF.SETTING,
}


class _BackgroundEffect(QWidget):
    """Soft Fluent-like background effect for the main content area.

    The widget paints the active theme background plus subtle radial accent
    glows. Child pages remain transparent where appropriate, so the effect
    stays visible without replacing cards/surfaces.
    """

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.theme.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self, mode: str) -> None:
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect()
        bg = QColor(self.theme.colors["bg"])
        accent = QColor(self.theme.colors["accent"])

        # Base theme background.
        painter.fillRect(rect, bg)

        # Soft top-right glow.
        accent_top = QColor(accent)
        accent_top.setAlpha(52 if self.theme.mode == "dark" else 44)
        grad_top = QRadialGradient(
            rect.width() * 0.86,
            rect.height() * 0.08,
            max(rect.width(), rect.height()) * 0.70,
        )
        grad_top.setColorAt(0.0, accent_top)
        accent_top_edge = QColor(accent)
        accent_top_edge.setAlpha(0)
        grad_top.setColorAt(1.0, accent_top_edge)
        painter.fillRect(rect, grad_top)

        # Very subtle lower-left glow for depth.
        accent_low = QColor(accent)
        accent_low.setAlpha(30 if self.theme.mode == "dark" else 26)
        grad_low = QRadialGradient(
            rect.width() * 0.08,
            rect.height() * 0.88,
            max(rect.width(), rect.height()) * 0.65,
        )
        grad_low.setColorAt(0.0, accent_low)
        accent_low_edge = QColor(accent)
        accent_low_edge.setAlpha(0)
        grad_low.setColorAt(1.0, accent_low_edge)
        painter.fillRect(rect, grad_low)

        # Soft central bloom. This is intentionally stronger in Light Mode
        # so the background effect remains visible against the near-white
        # base instead of looking completely flat.
        accent_center = QColor(accent)
        accent_center.setAlpha(16 if self.theme.mode == "dark" else 24)
        grad_center = QRadialGradient(
            rect.width() * 0.52,
            rect.height() * 0.46,
            max(rect.width(), rect.height()) * 0.58,
        )
        grad_center.setColorAt(0.0, accent_center)
        accent_center_edge = QColor(accent)
        accent_center_edge.setAlpha(0)
        grad_center.setColorAt(1.0, accent_center_edge)
        painter.fillRect(rect, grad_center)

        painter.end()


class _LazyPage(QWidget):
    """Lazy page container registered as a FluentWindow sub-interface.

    The container itself is created immediately so FluentWindow can
    register it in navigation, but the actual page class is imported and
    constructed only when the container is first shown.
    """

    def __init__(
        self,
        key: str,
        theme: Theme,
        main_window: "MainWindow",
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._key = key
        self._theme = theme
        self._main_window = main_window

        self._pending_context: dict | None = None
        self._built = False
        self.page: QWidget | None = None

        # FluentWindow.addSubInterface() requires a globally unique
        # objectName because it becomes the navigation route key.
        self.setObjectName(key)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def set_pending_context(self, context: dict | None) -> None:
        self._pending_context = context

    def showEvent(self, event) -> None:
        super().showEvent(event)

        if not self._built:
            self._build()

        if self.page is not None:
            on_navigate = getattr(
                self.page,
                "on_navigate",
                None,
            )

            if callable(on_navigate):
                on_navigate(self._pending_context)

    def _build(self) -> None:
        module_name, class_name = PAGE_REGISTRY[self._key]

        module = __import__(
            f"control_panel.{module_name}",
            fromlist=[class_name],
        )

        page_class = getattr(module, class_name)

        self.page = page_class(
            self,
            self._theme,
            self._main_window,
        )

        self._layout.addWidget(self.page)
        self._built = True

    def refresh_theme(self) -> None:
        """Refresh this page's optional theme hook."""

        if self.page is None:
            return

        refresh = getattr(
            self.page,
            "refresh_theme",
            None,
        )

        if callable(refresh):
            refresh()


class MainWindow(FluentWindow):
    """Main Control Panel Fluent window."""

    def __init__(self) -> None:
        super().__init__()

        self.root = self

        self.setObjectName("controlPanelRoot")
        self.setWindowTitle("Electricity ML Control Panel")

        self.resize(1280, 800)
        self.setMinimumSize(1024, 640)

        # --------------------------------------------------------------
        # Application theme
        # --------------------------------------------------------------

        self.theme = Theme(mode="light")
        self.theme.themeChanged.connect(
            self._on_theme_changed
        )

        # QFluentWidgets itself manages the Fluent window background.
        # Explicit custom colors make the behavior deterministic in both
        # light and dark modes.
        self.setCustomBackgroundColor(
            self.theme.colors["bg"],
            self.theme.colors["bg"],
        )

        self.setStyleSheet(
            f"""
            QMainWindow#controlPanelRoot {{
                background-color: {self.theme.colors["bg"]};
            }}
            QWidget#contentHost {{
                background: transparent;
            }}
            QStackedWidget {{
                background: transparent;
            }}
            """
        )

        # The actual qfluentwidgets FluentWindow navigation/stack is
        # already created by FluentWindow.__init__().
        self._containers: dict[str, _LazyPage] = {}
        self._current_key: str | None = None

        # --------------------------------------------------------------
        # Status bar
        # --------------------------------------------------------------

        self.status_bar = self._build_status_bar()

        # FluentWindow.widgetLayout is a horizontal layout containing
        # the stacked widget. Replace that single stack entry with our
        # own vertical host so the status bar can sit below it.
        self._install_content_host()

        # --------------------------------------------------------------
        # Navigation
        # --------------------------------------------------------------

        self._build_navigation()

        # Make sure the first page is selected.
        self.navigate("dashboard")

    # ------------------------------------------------------------------
    # Fluent content layout
    # ------------------------------------------------------------------

    def _install_content_host(self) -> None:
        """Put FluentWindow's stacked widget and our status bar into a
        vertical container.

        FluentWindow continues to own and manage `self.stackedWidget`;
        only the physical layout around it is customized.
        """

        host = QWidget(self)
        host.setObjectName("contentHost")

        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Paint a soft Fluent-like background behind the page stack.
        background = _BackgroundEffect(self.theme, host)
        self._background_effect = background

        # Remove the stacked widget from FluentWindow.widgetLayout.
        index = self.widgetLayout.indexOf(self.stackedWidget)

        if index >= 0:
            item = self.widgetLayout.takeAt(index)

            if item is not None:
                old_widget = item.widget()

                if old_widget is not None and old_widget is not self.stackedWidget:
                    old_widget.setParent(None)

        layout.addWidget(background, 1)
        background_layout = QVBoxLayout(background)
        background_layout.setContentsMargins(0, 0, 0, 0)
        background_layout.setSpacing(0)
        background_layout.addWidget(self.stackedWidget, 1)
        layout.addWidget(self.status_bar, 0)

        self.widgetLayout.addWidget(host, 1)

        self._content_host = host

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _build_navigation(self) -> None:
        for key, title in PAGE_TITLES.items():
            container = _LazyPage(
                key,
                self.theme,
                self,
            )

            self._containers[key] = container

            icon = PAGE_ICONS.get(
                key,
                FIF.DOCUMENT,
            )

            # This is FluentWindow's documented navigation API.
            self.addSubInterface(
                container,
                icon,
                title,
                NavigationItemPosition.TOP,
            )

    def navigate(
        self,
        key: str,
        context: dict | None = None,
    ) -> None:
        """Navigate to a registered page while preserving the existing
        app.navigate(key, context) contract.
        """

        container = self._containers.get(key)

        if container is None:
            return

        container.set_pending_context(context)
        self._current_key = key

        # FluentWindow handles:
        # - stacked widget switching
        # - navigation selection
        # - current-interface bookkeeping
        self.switchTo(container)

        self._touch_status_time()

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("statusBar")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(8)

        self.status_dot = QLabel(bar)
        self.status_dot.setFixedSize(10, 10)
        layout.addWidget(self.status_dot)

        self.status_label = QLabel(
            "System Ready",
            bar,
        )
        layout.addWidget(self.status_label)

        layout.addStretch(1)

        self.last_update_label = QLabel(
            "",
            bar,
        )

        layout.addWidget(self.last_update_label)

        theme_btn = PushButton(
            "Toggle Theme",
            bar,
        )
        theme_btn.clicked.connect(
            self.theme.toggle
        )

        layout.addWidget(theme_btn)

        self._paint_status_dot()
        self._touch_status_time()

        return bar

    def _paint_status_dot(self) -> None:
        self.status_dot.setStyleSheet(
            f"""
            background-color: {self.theme.colors["success"]};
            border-radius: 5px;
            """
        )

    def _touch_status_time(self) -> None:
        self.last_update_label.setText(
            f"Last update: {datetime.now().strftime('%H:%M:%S')}"
        )

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _on_theme_changed(self, mode: str) -> None:
        # The Theme class already calls qfluentwidgets.setTheme().
        # FluentWindow itself should therefore update its Fluent controls.
        #
        # setCustomBackgroundColor() is the documented FluentWindow API
        # for controlling the light/dark window background.
        self.setCustomBackgroundColor(
            self.theme.colors["bg"],
            self.theme.colors["bg"],
        )

        # Keep the physical FluentWindow/content surfaces synchronized
        # with the live Theme. Page-level widgets may be transparent, but
        # these root surfaces must always carry the active background.
        self.setStyleSheet(
            f"""
            QMainWindow#controlPanelRoot {{
                background-color: {self.theme.colors["bg"]};
            }}
            QWidget#contentHost {{
                background: transparent;
            }}
            QStackedWidget {{
                background: transparent;
            }}
            """
        )

        self._paint_status_dot()

        self.last_update_label.setStyleSheet(
            f"color: {self.theme.colors['text_muted']};"
        )

        # Refresh manually-colored widgets on the current page.
        current = self._containers.get(
            self._current_key
        )

        if current is not None:
            current.refresh_theme()

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------

    def show_error(
        self,
        title: str,
        message: str,
    ) -> None:
        try:
            from .services import log_service

            log_service.log_event(
                "UI_ERROR",
                level="ERROR",
                component="app",
                message=message,
            )
        except Exception:
            pass

        try:
            box = MessageBox(
                title,
                message,
                self,
            )

            # qfluentwidgets MessageBox normally provides yes/cancel
            # buttons. Turn it into a simple acknowledgement dialog.
            if hasattr(box, "cancelButton"):
                box.cancelButton.hide()

            if hasattr(box, "yesButton"):
                box.yesButton.setText("OK")

            box.exec()

        except Exception:
            # Never let failure to show an error dialog crash the app.
            pass

    # ------------------------------------------------------------------
    # Uncaught exceptions
    # ------------------------------------------------------------------

    def on_uncaught_exception(
        self,
        exc_type,
        exc_value,
        exc_tb,
    ) -> None:
        """Handle uncaught exceptions from Qt event handlers."""

        text = "".join(
            traceback.format_exception(
                exc_type,
                exc_value,
                exc_tb,
            )
        )

        try:
            from .services import log_service

            log_service.log_event(
                "UI_ERROR",
                level="ERROR",
                component="app",
                message=str(exc_value),
                extra={
                    "traceback": text,
                },
            )
        except Exception:
            pass

        try:
            self.show_error(
                "Unexpected Error",
                f"{exc_value}\n\nThe Control Panel will keep running.",
            )
        except Exception:
            pass