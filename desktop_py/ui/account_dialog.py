from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop_py.core.models import AccountConfig


class AccountDialog(QDialog):
    def __init__(
        self,
        account: AccountConfig | None = None,
        parent: QWidget | None = None,
        *,
        enabled_only: bool = False,
    ):
        super().__init__(parent)
        self._account = account
        self._enabled_only = enabled_only
        self.setWindowTitle("账号配置")
        self.setModal(True)
        self.resize(520, 320)
        self.setObjectName("accountDialog")

        self.name_edit = QLineEdit(account.name if account else "")
        self.state_path_edit = QLineEdit(account.state_path if account else "")
        self.home_url_edit = QLineEdit(account.home_url if account else "https://mp.weixin.qq.com/")
        self.name_edit.setPlaceholderText("例如：主账号、测试账号")
        self.home_url_edit.setPlaceholderText("默认使用微信公众平台首页")
        self.enabled_check = QCheckBox("启用该账号")
        self.enabled_check.setChecked(True if account is None else account.enabled)
        if enabled_only:
            self.name_edit.setReadOnly(True)
            self.home_url_edit.setReadOnly(True)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(16)
        form.addRow("账号名称", self.name_edit)
        form.addRow("后台首页", self.home_url_edit)
        form.addRow("", self.enabled_check)

        self.cancel_button = QPushButton("取消")
        self.save_button = QPushButton("保存")
        self.save_button.setProperty("role", "primary")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("账号信息")
        title.setObjectName("dialogTitle")
        subtitle_text = (
            "导入账号仅支持调整启用状态，其余资料由入口账号同步。"
            if enabled_only
            else "只需维护基础资料，其余抓取状态仍由主窗口自动更新。"
        )
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)

        card = QFrame()
        card.setObjectName("dialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)
        card_layout.addLayout(form)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card)
        layout.addLayout(buttons)

        self.setStyleSheet(
            """
            QDialog#accountDialog {
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
                border-radius: 12px;
                background: #f9fbfd;
                color: #132238;
            }
            QLineEdit:focus {
                border: 1px solid #2f80ed;
                background: #ffffff;
            }
            QCheckBox {
                color: #24384d;
                spacing: 8px;
            }
            QPushButton {
                min-height: 40px;
                padding: 0 18px;
                border-radius: 12px;
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
            """
        )

    def build_account(self) -> AccountConfig:
        return AccountConfig(
            name=self.name_edit.text().strip(),
            state_path=self.state_path_edit.text().strip(),
            is_entry_account=True if self._account is None else self._account.is_entry_account,
            home_url=self.home_url_edit.text().strip() or "https://mp.weixin.qq.com/",
            enabled=self.enabled_check.isChecked(),
        )
