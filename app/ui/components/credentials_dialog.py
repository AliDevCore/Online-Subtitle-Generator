"""
Secure API Credentials configuration dialog for Online Subtitle Generator.
Manages up to 10 Cloudflare accounts with automatic failover upon daily neuron quota exhaustion.
Stores keys directly in Windows Credential Manager. Zero plaintext storage.
"""

from __future__ import annotations
import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QGridLayout, QMessageBox, QComboBox
)
from app.core.config import get_app_icon
from app.core.credential_manager import CredentialManager


class CredentialsDialog(QDialog):
    """Dialog for securely managing Cloudflare multi-account API credentials."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Online Subtitle Generator — Cloudflare Accounts")
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.setMinimumWidth(600)
        self.current_slot = 1
        self._build_ui()
        self._load_slot(1)
        self._update_pool_summary()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        sec_note = QLabel(
            "Security Guarantee: All API tokens and Account IDs are encrypted and stored in Windows Credential Manager.\n"
            "They are never saved in plain text, database files, or logs."
        )
        sec_note.setStyleSheet("color: #38bdf8; font-size: 11.5px; font-weight: 500;")
        layout.addWidget(sec_note)

        # Multi-Account Cloudflare Group
        cf_group = QGroupBox("Cloudflare Multi-Account Pool (Up to 10 Accounts)")
        cf_layout = QGridLayout(cf_group)
        cf_layout.setSpacing(10)

        # Account Slot Selector
        cf_layout.addWidget(QLabel("Select Account Slot:"), 0, 0)
        slot_box = QHBoxLayout()
        self.combo_slots = QComboBox()
        for idx in range(1, 11):
            self.combo_slots.addItem(f"Account #{idx}", idx)
        self.combo_slots.currentIndexChanged.connect(self._on_slot_changed)
        slot_box.addWidget(self.combo_slots, 1)

        self.lbl_slot_status = QLabel("[Checking...]")
        self.lbl_slot_status.setStyleSheet("font-weight: bold; color: #a3a3a3;")
        slot_box.addWidget(self.lbl_slot_status)
        cf_layout.addLayout(slot_box, 0, 1)

        # Account ID input
        cf_layout.addWidget(QLabel("Account ID:"), 1, 0)
        self.txt_cf_account = QLineEdit()
        self.txt_cf_account.setPlaceholderText("Enter Cloudflare Account ID (32 hex characters)")
        cf_layout.addWidget(self.txt_cf_account, 1, 1)

        # API Token input
        cf_layout.addWidget(QLabel("API Token:"), 2, 0)
        self.txt_cf_token = QLineEdit()
        self.txt_cf_token.setEchoMode(QLineEdit.Password)
        self.txt_cf_token.setPlaceholderText("Enter Cloudflare API Token (with Workers AI Read permission)")
        cf_layout.addWidget(self.txt_cf_token, 2, 1)

        # Action Buttons per slot
        btn_box = QHBoxLayout()
        self.btn_toggle = QPushButton("Show")
        self.btn_toggle.setObjectName("btn_secondary")
        self.btn_toggle.clicked.connect(self._toggle_echo)
        btn_box.addWidget(self.btn_toggle)

        self.btn_test = QPushButton("Test Account")
        self.btn_test.setObjectName("btn_secondary")
        self.btn_test.clicked.connect(self._test_account)
        btn_box.addWidget(self.btn_test)

        self.btn_clear = QPushButton("Clear Slot")
        self.btn_clear.setObjectName("btn_danger")
        self.btn_clear.clicked.connect(self._clear_current_slot)
        btn_box.addWidget(self.btn_clear)

        cf_layout.addLayout(btn_box, 3, 1)

        layout.addWidget(cf_group)

        # Pool summary overview
        self.lbl_pool_summary = QLabel("")
        self.lbl_pool_summary.setStyleSheet(
            "background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; border-radius: 6px; "
            "padding: 8px 12px; color: #cbd5e1; font-size: 11.5px;"
        )
        layout.addWidget(self.lbl_pool_summary)

        # Save and Close buttons
        bottom_box = QHBoxLayout()
        bottom_box.addStretch(1)

        self.btn_save = QPushButton("Save Account")
        self.btn_save.setObjectName("btn_primary")
        self.btn_save.clicked.connect(self._save_current_slot)
        bottom_box.addWidget(self.btn_save)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("btn_secondary")
        self.btn_close.clicked.connect(self.accept)
        bottom_box.addWidget(self.btn_close)

        layout.addLayout(bottom_box)

    def _on_slot_changed(self, index: int):
        slot = self.combo_slots.itemData(index)
        self._load_slot(slot)

    def _load_slot(self, slot: int):
        self.current_slot = slot
        accounts = CredentialManager.get_cloudflare_accounts()
        target = next((a for a in accounts if a["index"] == slot), None)

        if target and target.get("configured"):
            self.txt_cf_account.setText(target.get("account_id", ""))
            self.txt_cf_token.setText(target.get("api_key", ""))
            self.lbl_slot_status.setText("✓ Configured")
            self.lbl_slot_status.setStyleSheet("font-weight: bold; color: #4ade80;")
        else:
            self.txt_cf_account.clear()
            self.txt_cf_token.clear()
            self.lbl_slot_status.setText("○ Empty")
            self.lbl_slot_status.setStyleSheet("font-weight: bold; color: #94a3b8;")

    def _update_pool_summary(self):
        accounts = CredentialManager.get_cloudflare_accounts()
        configured = [a for a in accounts if a.get("configured")]
        count = len(configured)
        slots_str = ", ".join(f"#{a['index']}" for a in configured) if configured else "None"

        self.lbl_pool_summary.setText(
            f"Active Cloudflare Pool: {count} of 10 accounts configured (Slots: {slots_str}).\n"
            f"Automatic Failover: If Account #1 hits its 10,000 daily neuron limit, processing continues "
            f"seamlessly on Account #2 and beyond without stopping."
        )

    def _toggle_echo(self):
        if self.txt_cf_token.echoMode() == QLineEdit.Password:
            self.txt_cf_token.setEchoMode(QLineEdit.Normal)
            self.btn_toggle.setText("Hide")
        else:
            self.txt_cf_token.setEchoMode(QLineEdit.Password)
            self.btn_toggle.setText("Show")

    def _test_account(self):
        acct_id = self.txt_cf_account.text().strip()
        token = self.txt_cf_token.text().strip()

        if not acct_id or not token:
            QMessageBox.warning(self, "Incomplete Credentials", "Please enter both Account ID and API Token.")
            return

        url = f"https://api.cloudflare.com/client/v4/accounts/{acct_id}/tokens/verify"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200 and resp.json().get("success"):
                QMessageBox.information(
                    self,
                    "Connection Successful",
                    f"Cloudflare Account #{self.current_slot} verified successfully!"
                )
            else:
                # Some tokens only have Workers AI permissions without User Token verification
                ai_url = f"https://api.cloudflare.com/client/v4/accounts/{acct_id}/ai/models/search?search=whisper"
                ai_resp = requests.get(ai_url, headers=headers, timeout=10)
                if ai_resp.status_code == 200:
                    QMessageBox.information(
                        self,
                        "Connection Successful",
                        f"Cloudflare Account #{self.current_slot} verified successfully with Workers AI access!"
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Verification Failed",
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
        except Exception as e:
            QMessageBox.critical(self, "Network Error", f"Connection test failed: {e}")

    def _save_current_slot(self):
        acct_id = self.txt_cf_account.text().strip()
        token = self.txt_cf_token.text().strip()

        if not acct_id and not token:
            CredentialManager.delete_cloudflare_account(self.current_slot)
        else:
            CredentialManager.set_cloudflare_account(self.current_slot, acct_id, token)

        self._load_slot(self.current_slot)
        self._update_pool_summary()
        QMessageBox.information(
            self,
            "Saved",
            f"Cloudflare Account #{self.current_slot} credentials saved securely in Windows Credential Manager."
        )

    def _clear_current_slot(self):
        confirm = QMessageBox.question(
            self,
            "Clear Slot",
            f"Are you sure you want to clear credentials for Account #{self.current_slot}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            CredentialManager.delete_cloudflare_account(self.current_slot)
            self._load_slot(self.current_slot)
            self._update_pool_summary()
