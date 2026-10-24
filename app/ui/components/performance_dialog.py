"""
Dedicated Performance Settings dialog.
Hardware detection, CPU target controls, Windows process priority & affinity, and RAM monitoring.
"""

from __future__ import annotations
import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton, QGroupBox, QGridLayout, QMessageBox
)
from PySide6.QtCore import Qt

from app.core.config import (
    SETTINGS_FILE, DEFAULT_PERFORMANCE_SETTINGS,
    DEFAULT_CHUNKING_SETTINGS, load_chunking_settings, save_chunking_settings,
    get_app_icon
)
from app.core.resource_controller import ResourceController
from app.core.types import PerformanceSettings, ChunkingSettings


class PerformanceDialog(QDialog):
    """Configuration dialog for local performance settings and hardware detection."""

    def __init__(self, resource_controller: ResourceController, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OnlineSub — Performance & Hardware Settings")
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.setMinimumWidth(550)
        self.ctrl = resource_controller
        self.settings = self.ctrl.settings

        self._build_ui()
        self._load_hardware_info()
        self._populate_fields()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # 1. Hardware Detection Section
        hw_group = QGroupBox("System Hardware Detected")
        hw_layout = QGridLayout(hw_group)

        self.lbl_cpu = QLabel("Detecting...")
        self.lbl_cores = QLabel("Detecting...")
        self.lbl_ram = QLabel("Detecting...")
        self.lbl_gpu = QLabel("Detecting...")

        hw_layout.addWidget(QLabel("CPU Model:"), 0, 0)
        hw_layout.addWidget(self.lbl_cpu, 0, 1)
        hw_layout.addWidget(QLabel("Processor Cores:"), 1, 0)
        hw_layout.addWidget(self.lbl_cores, 1, 1)
        hw_layout.addWidget(QLabel("System Memory:"), 2, 0)
        hw_layout.addWidget(self.lbl_ram, 2, 1)
        hw_layout.addWidget(QLabel("Graphics (GPU):"), 3, 0)
        hw_layout.addWidget(self.lbl_gpu, 3, 1)
        layout.addWidget(hw_group)

        # 2. Local Resource Controls Section
        res_group = QGroupBox("Local Workload Controls (Extraction & Local Whisper)")
        res_layout = QGridLayout(res_group)

        # Notice label explaining strict separation
        notice_lbl = QLabel(
            "Note: These settings control local CPU-intensive processing (FFmpeg, local Whisper).\n"
            "Cloud API calls (Gemini, Cloudflare, Hugging Face) run on remote servers and are not throttled."
        )
        notice_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; margin-bottom: 8px;")
        res_layout.addWidget(notice_lbl, 0, 0, 1, 2)

        # CPU Usage Target
        res_layout.addWidget(QLabel("CPU Usage Target:"), 1, 0)
        cpu_box = QHBoxLayout()
        self.combo_cpu_target = QComboBox()
        self.combo_cpu_target.addItems(["100% (Maximum - Default)", "75%", "50%", "25%"])
        cpu_box.addWidget(self.combo_cpu_target)
        res_layout.addLayout(cpu_box, 1, 1)

        # Process Priority
        res_layout.addWidget(QLabel("Process Priority:"), 2, 0)
        self.combo_priority = QComboBox()
        self.combo_priority.addItems(["Normal (Default)", "Below Normal", "Above Normal"])
        res_layout.addWidget(self.combo_priority, 2, 1)

        # CPU Threads
        res_layout.addWidget(QLabel("CPU Threads:"), 3, 0)
        self.combo_threads = QComboBox()
        self.combo_threads.addItems(["Automatic (Default)", "1 Thread", "2 Threads", "4 Threads", "8 Threads", "16 Threads"])
        res_layout.addWidget(self.combo_threads, 3, 1)

        # RAM Limit / Budget
        res_layout.addWidget(QLabel("RAM Budget:"), 4, 0)
        self.combo_ram = QComboBox()
        self.combo_ram.addItems(["Automatic (Default)", "2048 MB (2 GB)", "4096 MB (4 GB)", "8192 MB (8 GB)"])
        res_layout.addWidget(self.combo_ram, 4, 1)

        layout.addWidget(res_group)

        # 3. Audio Chunking (Cloudflare Workers AI ASR)
        chunk_group = QGroupBox("Audio Chunking (Cloudflare Workers AI ASR)")
        chunk_layout = QGridLayout(chunk_group)

        self.chk_chunking_enabled = QCheckBox("Enable Audio Chunking (Divide long audio into segments)")
        self.chk_chunking_enabled.setChecked(True)
        self.chk_chunking_enabled.toggled.connect(self._on_chunking_toggled)
        chunk_layout.addWidget(self.chk_chunking_enabled, 0, 0, 1, 2)

        chunk_hint = QLabel(
            "When enabled, audio exceeding the chunk duration is split at natural pauses.\n"
            "When disabled, the entire selected time range is sent in a single request.\n"
            "(Recommended: 3 to 5 minutes to prevent Cloudflare edge gateway timeout 504)."
        )
        chunk_hint.setStyleSheet("color: #94a3b8; font-size: 11px; margin-bottom: 6px;")
        chunk_layout.addWidget(chunk_hint, 1, 0, 1, 2)

        # Cloudflare Workers AI Chunk Duration
        chunk_layout.addWidget(QLabel("Cloudflare Chunk Duration:"), 2, 0)
        self.spin_cloudflare = QDoubleSpinBox()
        self.spin_cloudflare.setRange(1.0, 60.0)
        self.spin_cloudflare.setSingleStep(0.5)
        self.spin_cloudflare.setDecimals(1)
        self.spin_cloudflare.setSuffix(" min")
        self.spin_cloudflare.setToolTip("Recommended: 3 to 5 minutes to avoid Cloudflare edge gateway timeout (504).")
        chunk_layout.addWidget(self.spin_cloudflare, 2, 1)

        layout.addWidget(chunk_group)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.setObjectName("btn_secondary")
        self.btn_reset.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(self.btn_reset)

        self.btn_save = QPushButton("Save & Apply")
        self.btn_save.setObjectName("btn_success")
        self.btn_save.clicked.connect(self._save_and_apply)
        btn_layout.addWidget(self.btn_save)

        self.btn_close = QPushButton("Cancel")
        self.btn_close.setObjectName("btn_secondary")
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _on_chunking_toggled(self, checked: bool):
        self.spin_cloudflare.setEnabled(checked)

    def _load_hardware_info(self):
        info = ResourceController.get_system_info()
        self.lbl_cpu.setText(info.cpu_name)
        self.lbl_cores.setText(f"{info.physical_cores} Physical / {info.logical_cores} Logical Processors")
        self.lbl_ram.setText(f"{info.available_ram_gb:.1f} GB Available / {info.total_ram_gb:.1f} GB Total")
        self.lbl_gpu.setText(info.gpu_name if info.has_gpu else "Integrated / Software (CPU Mode)")

    def _populate_fields(self):
        # Target CPU
        tgt = self.settings.cpu_usage_target
        if tgt >= 100:
            self.combo_cpu_target.setCurrentIndex(0)
        elif tgt == 75:
            self.combo_cpu_target.setCurrentIndex(1)
        elif tgt == 50:
            self.combo_cpu_target.setCurrentIndex(2)
        elif tgt == 25:
            self.combo_cpu_target.setCurrentIndex(3)

        # Priority
        pri = self.settings.process_priority
        if pri == "Below Normal":
            self.combo_priority.setCurrentIndex(1)
        elif pri == "Above Normal":
            self.combo_priority.setCurrentIndex(2)
        else:
            self.combo_priority.setCurrentIndex(0)

        # Threads
        th = self.settings.cpu_threads
        if th == "Automatic":
            self.combo_threads.setCurrentIndex(0)
        else:
            idx = self.combo_threads.findText(f"{th} Threads")
            if idx >= 0:
                self.combo_threads.setCurrentIndex(idx)

        # RAM
        ram = self.settings.ram_limit
        if ram == "Automatic":
            self.combo_ram.setCurrentIndex(0)
        else:
            idx = self.combo_ram.findText(f"{ram} MB", Qt.MatchContains)
            if idx >= 0:
                self.combo_ram.setCurrentIndex(idx)

        # Audio Chunking Preferences
        chunk_cfg = load_chunking_settings()
        self.chk_chunking_enabled.setChecked(chunk_cfg.enabled)
        self.spin_cloudflare.setValue(chunk_cfg.cloudflare_minutes)
        self._on_chunking_toggled(chunk_cfg.enabled)

    def _reset_defaults(self):
        self.combo_cpu_target.setCurrentIndex(0)
        self.combo_priority.setCurrentIndex(0)
        self.combo_threads.setCurrentIndex(0)
        self.combo_ram.setCurrentIndex(0)

        self.chk_chunking_enabled.setChecked(DEFAULT_CHUNKING_SETTINGS.enabled)
        self.spin_cloudflare.setValue(DEFAULT_CHUNKING_SETTINGS.cloudflare_minutes)
        self._on_chunking_toggled(DEFAULT_CHUNKING_SETTINGS.enabled)

    def _save_and_apply(self):
        # Parse target
        cpu_text = self.combo_cpu_target.currentText()
        if "100%" in cpu_text:
            cpu_target = 100
        elif "75%" in cpu_text:
            cpu_target = 75
        elif "50%" in cpu_text:
            cpu_target = 50
        else:
            cpu_target = 25

        # Priority
        pri_text = self.combo_priority.currentText()
        if "Below Normal" in pri_text:
            priority = "Below Normal"
        elif "Above Normal" in pri_text:
            priority = "Above Normal"
        else:
            priority = "Normal"

        # Threads
        th_text = self.combo_threads.currentText()
        threads = "Automatic" if "Automatic" in th_text else th_text.split()[0]

        # RAM
        ram_text = self.combo_ram.currentText()
        ram = "Automatic" if "Automatic" in ram_text else ram_text.split()[0]

        new_settings = PerformanceSettings(
            cpu_usage_target=cpu_target,
            process_priority=priority,
            cpu_threads=threads,
            ram_limit=ram
        )

        self.ctrl.apply_settings(new_settings)

        # Chunking Settings save
        new_chunking = ChunkingSettings(
            enabled=self.chk_chunking_enabled.isChecked(),
            cloudflare_minutes=self.spin_cloudflare.value(),
        )
        save_chunking_settings(new_chunking)

        # Persist performance settings to disk
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            existing = {}
            if SETTINGS_FILE.exists():
                try:
                    existing = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            existing["performance"] = new_settings.to_dict()
            existing["chunking"] = new_chunking.to_dict()
            SETTINGS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Save Warning", f"Could not persist settings to file: {e}")

        self.accept()
