"""
Secure API Credentials configuration dialog for Online Subtitle Generator.
Manages up to 10 Cloudflare accounts (ASR transcription) and up to 10 Google Gemini accounts (AI subtitle refinement).
Stores keys directly in Windows Credential Manager. Zero plaintext storage.
"""

from __future__ import annotations
import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QGridLayout, QMessageBox, QComboBox,
    QTabWidget, QWidget
)
from app.core.config import get_app_icon
from app.core.credential_manager import CredentialManager


class CredentialsDialog(QDialog):
    """Dialog for securely managing Cloudflare and Google Gemini multi-account API credentials."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Online Subtitle Generator — API Credentials Manager")
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.setMinimumWidth(640)
        self.current_cf_slot = 1
        self.current_gemini_slot = 1
        self._build_ui()
        self._load_cf_slot(1)
        self._load_gemini_slot(1)
        self._update_all_summaries()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        sec_note = QLabel(
            "Security Guarantee: All API tokens and credentials are encrypted and stored directly in Windows Credential Manager.\n"
            "They are never saved in plain text, database files, or logs."
        )
        sec_note.setStyleSheet("color: #38bdf8; font-size: 11.5px; font-weight: 500;")
        layout.addWidget(sec_note)

        self.tabs = QTabWidget()

        # -------------------------------------------------------------
        # Tab 1: Cloudflare Accounts (Whisper ASR)
        # -------------------------------------------------------------
        cf_tab = QWidget()
        cf_tab_layout = QVBoxLayout(cf_tab)
        cf_tab_layout.setSpacing(12)

        cf_desc = QLabel(
            "Cloudflare Workers AI Audio Engine (OpenAI Whisper Large v3 Turbo):\n"
            "Each free account provides 10,000 neurons daily (~214 minutes of audio). "
            "Configure up to 10 accounts for seamless automatic rotation without hitting daily limits."
        )
        cf_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        cf_desc.setWordWrap(True)
        cf_tab_layout.addWidget(cf_desc)

        cf_group = QGroupBox("Cloudflare Account Slot")
        cf_layout = QGridLayout(cf_group)
        cf_layout.setSpacing(10)

        cf_layout.addWidget(QLabel("Select Slot:"), 0, 0)
        cf_slot_box = QHBoxLayout()
        self.combo_cf_slots = QComboBox()
        for idx in range(1, 11):
            lbl = f"Account #{idx} (Primary)" if idx == 1 else f"Account #{idx}"
            self.combo_cf_slots.addItem(lbl, idx)
        self.combo_cf_slots.currentIndexChanged.connect(self._on_cf_slot_changed)
        cf_slot_box.addWidget(self.combo_cf_slots, 1)

        self.lbl_cf_slot_status = QLabel("[Checking...]")
        self.lbl_cf_slot_status.setStyleSheet("font-weight: bold; color: #a3a3a3;")
        cf_slot_box.addWidget(self.lbl_cf_slot_status)
        cf_layout.addLayout(cf_slot_box, 0, 1)

        cf_layout.addWidget(QLabel("Account ID:"), 1, 0)
        self.txt_cf_account = QLineEdit()
        self.txt_cf_account.setPlaceholderText("Enter Cloudflare Account ID (32 hex characters)")
        cf_layout.addWidget(self.txt_cf_account, 1, 1)

        cf_layout.addWidget(QLabel("API Token:"), 2, 0)
        self.txt_cf_token = QLineEdit()
        self.txt_cf_token.setEchoMode(QLineEdit.Password)
        self.txt_cf_token.setPlaceholderText("Enter Cloudflare API Token (with Workers AI Read permission)")
        cf_layout.addWidget(self.txt_cf_token, 2, 1)

        cf_btn_box = QHBoxLayout()
        self.btn_cf_toggle = QPushButton("Show")
        self.btn_cf_toggle.setObjectName("btn_secondary")
        self.btn_cf_toggle.clicked.connect(self._toggle_cf_echo)
        cf_btn_box.addWidget(self.btn_cf_toggle)

        self.btn_cf_test = QPushButton("Test Connection")
        self.btn_cf_test.setObjectName("btn_secondary")
        self.btn_cf_test.clicked.connect(self._test_cf_account)
        cf_btn_box.addWidget(self.btn_cf_test)

        self.btn_cf_save = QPushButton("Save Account")
        self.btn_cf_save.setObjectName("btn_primary")
        self.btn_cf_save.clicked.connect(self._save_cf_slot)
        cf_btn_box.addWidget(self.btn_cf_save)

        self.btn_cf_clear = QPushButton("Clear Slot")
        self.btn_cf_clear.setObjectName("btn_danger")
        self.btn_cf_clear.clicked.connect(self._clear_cf_slot)
        cf_btn_box.addWidget(self.btn_cf_clear)

        cf_layout.addLayout(cf_btn_box, 3, 1)
        cf_tab_layout.addWidget(cf_group)

        self.lbl_cf_summary = QLabel("")
        self.lbl_cf_summary.setStyleSheet(
            "background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; border-radius: 6px; "
            "padding: 8px 12px; color: #cbd5e1; font-size: 11.5px;"
        )
        cf_tab_layout.addWidget(self.lbl_cf_summary)
        cf_tab_layout.addStretch(1)

        self.tabs.addTab(cf_tab, "Cloudflare (ASR Transcription)")

        # -------------------------------------------------------------
        # Tab 2: Google Gemini (AI Subtitle Refiner)
        # -------------------------------------------------------------
        gemini_tab = QWidget()
        gem_tab_layout = QVBoxLayout(gemini_tab)
        gem_tab_layout.setSpacing(12)

        gem_desc = QLabel(
            "Google Gemini AI Subtitle Refiner & Proofreader (Recommended):\n"
            "Ultra-accurate spelling, homophone correction, grammar polishing, and half-space (نیم‌فاصله) formatting.\n"
            "Free tier on Google AI Studio includes 1,500 free requests daily with multi-model auto-rotation "
            "(gemini-3.5-flash-lite, gemini-3-flash, gemini-3.8-flash)."
        )
        gem_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        gem_desc.setWordWrap(True)
        gem_tab_layout.addWidget(gem_desc)

        gem_group = QGroupBox("Google Gemini Account Slot")
        gem_layout = QGridLayout(gem_group)
        gem_layout.setSpacing(10)

        gem_layout.addWidget(QLabel("Select Slot:"), 0, 0)
        gem_slot_box = QHBoxLayout()
        self.combo_gemini_slots = QComboBox()
        for idx in range(1, 11):
            lbl = f"Account #{idx} (Primary)" if idx == 1 else f"Account #{idx}"
            self.combo_gemini_slots.addItem(lbl, idx)
        self.combo_gemini_slots.currentIndexChanged.connect(self._on_gemini_slot_changed)
        gem_slot_box.addWidget(self.combo_gemini_slots, 1)

        self.lbl_gemini_slot_status = QLabel("[Checking...]")
        self.lbl_gemini_slot_status.setStyleSheet("font-weight: bold; color: #a3a3a3;")
        gem_slot_box.addWidget(self.lbl_gemini_slot_status)
        gem_layout.addLayout(gem_slot_box, 0, 1)

        gem_layout.addWidget(QLabel("Gemini API Key:"), 1, 0)
        self.txt_gemini_key = QLineEdit()
        self.txt_gemini_key.setEchoMode(QLineEdit.Password)
        self.txt_gemini_key.setPlaceholderText("Enter Google AI Studio API Key (AIzaSy...)")
        gem_layout.addWidget(self.txt_gemini_key, 1, 1)

        gem_btn_box = QHBoxLayout()
        self.btn_gemini_toggle = QPushButton("Show")
        self.btn_gemini_toggle.setObjectName("btn_secondary")
        self.btn_gemini_toggle.clicked.connect(self._toggle_gemini_echo)
        gem_btn_box.addWidget(self.btn_gemini_toggle)

        self.btn_gemini_test = QPushButton("Test Connection")
        self.btn_gemini_test.setObjectName("btn_secondary")
        self.btn_gemini_test.clicked.connect(self._test_gemini_account)
        gem_btn_box.addWidget(self.btn_gemini_test)

        self.btn_gemini_save = QPushButton("Save Account")
        self.btn_gemini_save.setObjectName("btn_primary")
        self.btn_gemini_save.clicked.connect(self._save_gemini_slot)
        gem_btn_box.addWidget(self.btn_gemini_save)

        self.btn_gemini_clear = QPushButton("Clear Slot")
        self.btn_gemini_clear.setObjectName("btn_danger")
        self.btn_gemini_clear.clicked.connect(self._clear_gemini_slot)
        gem_btn_box.addWidget(self.btn_gemini_clear)

        gem_layout.addLayout(gem_btn_box, 2, 1)
        gem_tab_layout.addWidget(gem_group)

        self.lbl_gemini_summary = QLabel("")
        self.lbl_gemini_summary.setStyleSheet(
            "background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; border-radius: 6px; "
            "padding: 8px 12px; color: #cbd5e1; font-size: 11.5px;"
        )
        gem_tab_layout.addWidget(self.lbl_gemini_summary)
        gem_tab_layout.addStretch(1)

        self.tabs.addTab(gemini_tab, "Google Gemini (AI Refiner)")
        layout.addWidget(self.tabs)

        # Bottom Close button
        bottom_box = QHBoxLayout()
        bottom_box.addStretch(1)
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("btn_secondary")
        self.btn_close.clicked.connect(self.accept)
        bottom_box.addWidget(self.btn_close)
        layout.addLayout(bottom_box)

    # -------------------------------------------------------------
    # Cloudflare Slot Operations
    # -------------------------------------------------------------
    def _on_cf_slot_changed(self, index: int):
        slot = self.combo_cf_slots.itemData(index)
        self._load_cf_slot(slot)

    def _load_cf_slot(self, slot: int):
        self.current_cf_slot = slot
        accounts = CredentialManager.get_cloudflare_accounts()
        target = next((a for a in accounts if a["index"] == slot), None)

        if target and target.get("configured"):
            self.txt_cf_account.setText(target.get("account_id", ""))
            self.txt_cf_token.setText(target.get("api_key", ""))
            self.lbl_cf_slot_status.setText("✓ Configured")
            self.lbl_cf_slot_status.setStyleSheet("font-weight: bold; color: #4ade80;")
        else:
            self.txt_cf_account.clear()
            self.txt_cf_token.clear()
            self.lbl_cf_slot_status.setText("○ Empty")
            self.lbl_cf_slot_status.setStyleSheet("font-weight: bold; color: #94a3b8;")

    def _toggle_cf_echo(self):
        if self.txt_cf_token.echoMode() == QLineEdit.Password:
            self.txt_cf_token.setEchoMode(QLineEdit.Normal)
            self.btn_cf_toggle.setText("Hide")
        else:
            self.txt_cf_token.setEchoMode(QLineEdit.Password)
            self.btn_cf_toggle.setText("Show")

    def _test_cf_account(self):
        acct_id = self.txt_cf_account.text().strip()
        token = self.txt_cf_token.text().strip()

        if not acct_id or not token:
            QMessageBox.warning(self, "Incomplete Credentials", "Please enter both Account ID and API Token.")
            return

        headers = {"Authorization": f"Bearer {token}"}
        ai_url = f"https://api.cloudflare.com/client/v4/accounts/{acct_id}/ai/models/search?search=whisper"
        try:
            ai_resp = requests.get(ai_url, headers=headers, timeout=10)
            if ai_resp.status_code == 200:
                QMessageBox.information(
                    self,
                    "Connection Successful",
                    f"Cloudflare Account #{self.current_cf_slot} verified successfully with Workers AI access!"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Verification Failed",
                    f"HTTP {ai_resp.status_code}: {ai_resp.text[:200]}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Network Error", f"Connection test failed: {e}")

    def _save_cf_slot(self):
        acct_id = self.txt_cf_account.text().strip()
        token = self.txt_cf_token.text().strip()

        if not acct_id and not token:
            CredentialManager.delete_cloudflare_account(self.current_cf_slot)
        else:
            CredentialManager.set_cloudflare_account(self.current_cf_slot, acct_id, token)

        self._load_cf_slot(self.current_cf_slot)
        self._update_all_summaries()
        QMessageBox.information(
            self,
            "Saved",
            f"Cloudflare Account #{self.current_cf_slot} credentials saved securely in Windows Credential Manager."
        )

    def _clear_cf_slot(self):
        confirm = QMessageBox.question(
            self,
            "Clear Slot",
            f"Are you sure you want to clear credentials for Cloudflare Account #{self.current_cf_slot}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            CredentialManager.delete_cloudflare_account(self.current_cf_slot)
            self._load_cf_slot(self.current_cf_slot)
            self._update_all_summaries()

    # -------------------------------------------------------------
    # Google Gemini Slot Operations
    # -------------------------------------------------------------
    def _on_gemini_slot_changed(self, index: int):
        slot = self.combo_gemini_slots.itemData(index)
        self._load_gemini_slot(slot)

    def _load_gemini_slot(self, slot: int):
        self.current_gemini_slot = slot
        accounts = CredentialManager.get_gemini_accounts()
        target = next((a for a in accounts if a["index"] == slot), None)

        if target and target.get("configured"):
            self.txt_gemini_key.setText(target.get("api_key", ""))
            self.lbl_gemini_slot_status.setText("✓ Configured")
            self.lbl_gemini_slot_status.setStyleSheet("font-weight: bold; color: #4ade80;")
        else:
            self.txt_gemini_key.clear()
            self.lbl_gemini_slot_status.setText("○ Empty")
            self.lbl_gemini_slot_status.setStyleSheet("font-weight: bold; color: #94a3b8;")

    def _toggle_gemini_echo(self):
        if self.txt_gemini_key.echoMode() == QLineEdit.Password:
            self.txt_gemini_key.setEchoMode(QLineEdit.Normal)
            self.btn_gemini_toggle.setText("Hide")
        else:
            self.txt_gemini_key.setEchoMode(QLineEdit.Password)
            self.btn_gemini_toggle.setText("Show")

    def _test_gemini_account(self):
        key = self.txt_gemini_key.text().strip()
        if not key:
            QMessageBox.warning(self, "Missing Key", "Please enter a Google Gemini API Key.")
            return

        headers = {"Content-Type": "application/json", "x-goog-api-key": key}
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"
        payload = {
            "contents": [{"parts": [{"text": "Hello"}]}]
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=12)
            if resp.status_code == 200:
                QMessageBox.information(
                    self,
                    "Connection Successful",
                    f"Google Gemini Account #{self.current_gemini_slot} verified successfully!"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Verification Failed",
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Network Error", f"Connection test failed: {e}")

    def _save_gemini_slot(self):
        key = self.txt_gemini_key.text().strip()
        if not key:
            CredentialManager.delete_gemini_account(self.current_gemini_slot)
        else:
            CredentialManager.set_gemini_account(self.current_gemini_slot, key)

        self._load_gemini_slot(self.current_gemini_slot)
        self._update_all_summaries()
        QMessageBox.information(
            self,
            "Saved",
            f"Google Gemini Account #{self.current_gemini_slot} key saved securely in Windows Credential Manager."
        )

    def _clear_gemini_slot(self):
        confirm = QMessageBox.question(
            self,
            "Clear Slot",
            f"Are you sure you want to clear credentials for Gemini Account #{self.current_gemini_slot}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            CredentialManager.delete_gemini_account(self.current_gemini_slot)
            self._load_gemini_slot(self.current_gemini_slot)
            self._update_all_summaries()

    def _update_all_summaries(self):
        # Cloudflare summary
        cf_accounts = [a for a in CredentialManager.get_cloudflare_accounts() if a.get("configured")]
        cf_count = len(cf_accounts)
        cf_slots = ", ".join(f"#{a['index']}" for a in cf_accounts) if cf_accounts else "None"
        self.lbl_cf_summary.setText(
            f"Active Cloudflare Pool: {cf_count} of 10 accounts configured (Slots: {cf_slots}).\n"
            f"Automatic Failover: If Account #1 hits its 10,000 daily neuron limit, processing continues "
            f"seamlessly on Account #2 and beyond without stopping."
        )

        # Gemini summary
        gem_accounts = [a for a in CredentialManager.get_gemini_accounts() if a.get("configured")]
        gem_count = len(gem_accounts)
        gem_slots = ", ".join(f"#{a['index']}" for a in gem_accounts) if gem_accounts else "None"
        self.lbl_gemini_summary.setText(
            f"Active Gemini Pool: {gem_count} of 10 accounts configured (Slots: {gem_slots}).\n"
            f"Active Multi-Model Pool: Automatically switches across 8 Flash models upon rate limits (429/503)."
        )
