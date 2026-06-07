from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop_py.core.models import AppSettings


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        *,
        startup_enabled: bool,
        parent: QWidget | None = None,
        file_dialog: Any = None,
        prepare_shared_browser_profile_dir_fn: Any = None,
        validate_shared_browser_profile_dir_fn: Any = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._file_dialog = file_dialog
        self._prepare_shared_browser_profile_dir_fn = prepare_shared_browser_profile_dir_fn
        self._validate_shared_browser_profile_dir_fn = validate_shared_browser_profile_dir_fn
        self.setWindowTitle("全局设置")
        self.setModal(True)
        self.resize(560, 360)
        self.setObjectName("settingsDialog")

        self.webhook_edit = QLineEdit(settings.feishu_webhook)
        self.profile_dir_edit = QLineEdit(settings.browser_profile_dir)
        self.webhook_edit.setPlaceholderText("填写飞书机器人 Webhook，用于汇总推送")
        self.profile_dir_edit.setPlaceholderText("可选，复用共享浏览器资料目录")

        self.startup_switch = QCheckBox()
        self.startup_switch.setObjectName("startupSwitch")
        self.startup_switch.setChecked(startup_enabled)

        startup_option = QWidget()
        startup_option.setObjectName("startupOption")
        startup_option_layout = QHBoxLayout(startup_option)
        startup_option_layout.setContentsMargins(0, 0, 0, 0)
        startup_option_layout.setSpacing(12)
        startup_option_label = QLabel("开机自启")
        startup_option_label.setObjectName("startupOptionLabel")
        startup_option_layout.addWidget(startup_option_label)
        startup_option_layout.addStretch(1)
        startup_option_layout.addWidget(self.startup_switch)

        browse_button = QPushButton("选择目录")
        browse_button.setProperty("role", "primary")
        browse_button.clicked.connect(self.choose_profile_dir)

        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(14)
        form.addWidget(QLabel("飞书 Webhook"), 0, 0)
        form.addWidget(self.webhook_edit, 0, 1, 1, 2)
        form.addWidget(QLabel("共享浏览器资料目录"), 1, 0)
        form.addWidget(self.profile_dir_edit, 1, 1)
        form.addWidget(browse_button, 1, 2)
        form.addWidget(QLabel("启动选项"), 2, 0)
        form.addWidget(startup_option, 2, 1, 1, 2)
        form.setColumnStretch(1, 1)

        buttons = QWidget()
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(10)
        buttons_layout.addStretch(1)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        ok_button = QPushButton("保存")
        ok_button.setProperty("role", "primary")
        ok_button.clicked.connect(self.accept)
        buttons_layout.addWidget(cancel_button)
        buttons_layout.addWidget(ok_button)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("全局设置")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("统一维护通知、共享浏览器资料目录和开机启动选项。")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)

        card = QFrame()
        card.setObjectName("dialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)
        card_layout.addLayout(form)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(card)
        root.addWidget(buttons)

        self.setStyleSheet(
            """
            QDialog#settingsDialog {
                background: #f4f7fb;
            }
            QLabel#dialogTitle {
                color: #132238;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#dialogSubtitle {
                color: #607086;
                font-size: 13px;
                line-height: 1.5;
            }
            QFrame#dialogCard {
                background: #ffffff;
                border: 1px solid #d8e1ec;
                border-radius: 18px;
            }
            QLineEdit {
                min-height: 40px;
                padding: 0 12px;
                border: 1px solid #c8d3df;
                border-radius: 6px;
                background: #f9fbfd;
                color: #132238;
            }
            QLineEdit:focus {
                border: 1px solid #2f80ed;
                background: #ffffff;
            }
            QPushButton {
                min-height: 40px;
                padding: 0 18px;
                border-radius: 6px;
                border: 1px solid #d0dae5;
                background: #ffffff;
                color: #24384d;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #f4f8fc;
            }
            QPushButton[role="primary"] {
                background: #2f80ed;
                border-color: #2f80ed;
                color: #ffffff;
            }
            QPushButton[role="primary"]:hover {
                background: #1d6fd9;
            }
            QWidget#startupOption {
                min-height: 40px;
            }
            QLabel#startupOptionLabel {
                color: #24384d;
                font-size: 13px;
                font-weight: 600;
            }
            QCheckBox#startupSwitch {
                min-height: 40px;
            }
            QCheckBox#startupSwitch::indicator {
                width: 20px;
                height: 20px;
                border-radius: 6px;
                border: 1px solid #b8c6d5;
                background: #ffffff;
            }
            QCheckBox#startupSwitch::indicator:checked {
                background: #1f9a54;
                border-color: #1f9a54;
            }
            """
        )

    def choose_profile_dir(self) -> None:
        if self._file_dialog is None or self._prepare_shared_browser_profile_dir_fn is None:
            return
        target = self._file_dialog.getExistingDirectory(
            self, "选择共享浏览器资料目录", self.profile_dir_edit.text().strip()
        )
        if target:
            profile_dir = self._prepare_shared_browser_profile_dir_fn(target)
            self.profile_dir_edit.setText(profile_dir)

    def build_settings(self) -> AppSettings:
        profile_dir = self.profile_dir_edit.text().strip()
        if self._validate_shared_browser_profile_dir_fn is not None:
            profile_dir = self._validate_shared_browser_profile_dir_fn(profile_dir)
        return AppSettings(
            feishu_webhook=self.webhook_edit.text().strip(),
            login_wait_seconds=self._settings.login_wait_seconds,
            headless_fetch=self._settings.headless_fetch,
            browser_profile_dir=profile_dir,
            current_main_account_name=self._settings.current_main_account_name,
            auto_fetch_push_enabled=self._settings.auto_fetch_push_enabled,
            startup_enabled=self.startup_switch.isChecked(),
            diagnostic_retention_days=self._settings.diagnostic_retention_days,
        )
