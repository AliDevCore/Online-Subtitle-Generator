"""
Main Application Window for Online Subtitle Generator.
Generates English subtitles directly from video/audio files using Cloudflare Workers AI Whisper.
Equipped with multi-account pool (up to 10 accounts) with seamless failover upon neuron quota exhaustion.
"""

from __future__ import annotations
import logging
import math
import os
import sys
import time
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox,
    QProgressBar, QFileDialog, QMessageBox, QGroupBox, QStatusBar,
    QFrame, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer

from app.core.config import (
    APP_NAME, APP_VERSION, SETTINGS_FILE, DEFAULT_PERFORMANCE_SETTINGS,
    VERIFIED_ASR_PROVIDERS, load_chunking_settings, get_app_icon
)
from app.core.credential_manager import CredentialManager
from app.core.database import Database
from app.core.resource_controller import ResourceController
from app.core.types import TimeRange, PerformanceSettings
from app.services.ffmpeg_service import FFmpegService
from app.services.asr_service import ASRService
from app.services.batch_service import BatchService
from app.ui.components.batch_dialog import BatchDialog
from app.ui.components.credentials_dialog import CredentialsDialog
from app.ui.components.log_viewer_dialog import LogViewerDialog
from app.ui.styles import DARK_THEME_QSS
from app.workers.asr_worker import ASRWorker

logger = logging.getLogger("OnlineSubtitleGenerator.UI")


class MainWindow(QMainWindow):
    """Primary application window for Online Subtitle Generator."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — AI Subtitle Studio")
        self.resize(880, 680)
        self.setMinimumSize(780, 520)
        self.setStyleSheet(DARK_THEME_QSS)

        # Window icon
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        # Core services & controller
        self.db = Database()
        self.ffmpeg = FFmpegService()
        self.resource_ctrl = ResourceController(self._load_saved_performance())
        self.asr_service = ASRService(database=self.db, ffmpeg_service=self.ffmpeg, resource_controller=self.resource_ctrl)
        self.batch_service = BatchService(asr_service=self.asr_service, translation_service=None, database=self.db)

        # Active state
        self.current_video_duration: float = 0.0
        self.active_worker: Optional[ASRWorker] = None
        self.last_output_dir: Optional[Path] = None
        self.start_timestamp: float = 0.0

        # UI timer for elapsed time
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_elapsed_time)

        self._build_ui()
        self._update_asr_info()

    def _load_saved_performance(self) -> PerformanceSettings:
        if SETTINGS_FILE.exists():
            try:
                import json
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if "performance" in data:
                    return PerformanceSettings.from_dict(data["performance"])
            except Exception:
                pass
        return DEFAULT_PERFORMANCE_SETTINGS

    def _build_ui(self):
        # Wrap content in a robust QScrollArea to prevent any squashing on window resize
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content_widget = QWidget()
        content_widget.setMinimumWidth(740)
        main_layout = QVBoxLayout(content_widget)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(20, 16, 20, 16)

        # Top Bar: Toolbar Shortcuts
        top_bar = QHBoxLayout()
        title_lbl = QLabel(f"<b>{APP_NAME}</b> <span style='color:#38bdf8;'>v{APP_VERSION}</span>")
        title_lbl.setStyleSheet("font-size: 16px;")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()

        self.btn_keys = QPushButton("🔑 Cloudflare Accounts (10 Slots)")
        self.btn_keys.setObjectName("btn_secondary")
        self.btn_keys.setMinimumHeight(34)
        self.btn_keys.clicked.connect(self._open_credentials_dialog)
        top_bar.addWidget(self.btn_keys)

        self.btn_logs = QPushButton("📜 View Logs")
        self.btn_logs.setObjectName("btn_secondary")
        self.btn_logs.setMinimumHeight(34)
        self.btn_logs.clicked.connect(self._open_logs_dialog)
        top_bar.addWidget(self.btn_logs)

        main_layout.addLayout(top_bar)

        # Main Video Subtitle Generation Group
        asr_group = QGroupBox("Video Subtitle Extraction (Cloudflare Workers AI Whisper)")
        asr_layout = QVBoxLayout(asr_group)
        asr_layout.setSpacing(12)

        # Video Input Row
        asr_layout.addWidget(QLabel("<b>1. Select Local Video File:</b>"))
        v_box = QHBoxLayout()
        self.txt_video_path = QLineEdit()
        self.txt_video_path.setReadOnly(True)
        self.txt_video_path.setMinimumHeight(36)
        self.txt_video_path.setPlaceholderText("Select a video (*.mp4, *.mkv, *.avi, *.mov, *.webm)...")
        v_box.addWidget(self.txt_video_path, 1)

        self.btn_browse = QPushButton("Browse Video...")
        self.btn_browse.setMinimumHeight(36)
        self.btn_browse.clicked.connect(self._browse_video)
        v_box.addWidget(self.btn_browse)

        self.btn_batch_videos = QPushButton("📁 Batch Folder...")
        self.btn_batch_videos.setObjectName("btn_secondary")
        self.btn_batch_videos.setMinimumHeight(36)
        self.btn_batch_videos.clicked.connect(self._open_video_batch)
        v_box.addWidget(self.btn_batch_videos)

        asr_layout.addLayout(v_box)

        self.lbl_media_info = QLabel("No video selected.")
        self.lbl_media_info.setStyleSheet("color: #94a3b8; font-size: 11.5px;")
        asr_layout.addWidget(self.lbl_media_info)

        # Time Range Selection (Integer Minutes)
        asr_layout.addWidget(QLabel("<b>2. Time Range Selection (in Minutes):</b>"))
        t_grid = QGridLayout()
        t_grid.setSpacing(10)

        lbl_st = QLabel("Start:")
        lbl_st.setFixedWidth(40)
        t_grid.addWidget(lbl_st, 0, 0)

        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 9999)
        self.spin_start.setSingleStep(1)
        self.spin_start.setValue(0)
        self.spin_start.setSuffix(" min")
        self.spin_start.setMinimumHeight(36)
        t_grid.addWidget(self.spin_start, 0, 1)

        lbl_end = QLabel("End:")
        lbl_end.setFixedWidth(35)
        t_grid.addWidget(lbl_end, 0, 2)

        self.spin_end = QSpinBox()
        self.spin_end.setRange(0, 9999)
        self.spin_end.setSingleStep(1)
        self.spin_end.setValue(0)
        self.spin_end.setSuffix(" min")
        self.spin_end.setMinimumHeight(36)
        t_grid.addWidget(self.spin_end, 0, 3)

        self.btn_full_video = QPushButton("Entire Video")
        self.btn_full_video.setObjectName("btn_secondary")
        self.btn_full_video.setMinimumHeight(36)
        self.btn_full_video.clicked.connect(self._set_full_range)
        t_grid.addWidget(self.btn_full_video, 0, 4)
        asr_layout.addLayout(t_grid)

        self.lbl_range_info = QLabel("Timestamps strictly match original video playback timeline.")
        self.lbl_range_info.setStyleSheet("color: #38bdf8; font-size: 11px;")
        asr_layout.addWidget(self.lbl_range_info)

        # Engine & Multi-Account Details
        asr_layout.addWidget(QLabel("<b>3. ASR Engine & Account Pool:</b>"))
        self.lbl_asr_engine = QLabel("Cloudflare Workers AI — OpenAI Whisper Large v3 Turbo (@cf/openai/whisper-large-v3-turbo)")
        self.lbl_asr_engine.setStyleSheet("color: #f1f5f9; font-weight: 600; font-size: 12px;")
        asr_layout.addWidget(self.lbl_asr_engine)

        self.lbl_asr_pool = QLabel("Multi-Account Pool: Active")
        self.lbl_asr_pool.setStyleSheet("color: #38bdf8; font-size: 11.5px; font-weight: 500;")
        asr_layout.addWidget(self.lbl_asr_pool)

        self.lbl_asr_limits = QLabel("Mode: Initializing...")
        self.lbl_asr_limits.setWordWrap(True)
        self.lbl_asr_limits.setStyleSheet("color: #94a3b8; font-size: 11px;")
        asr_layout.addWidget(self.lbl_asr_limits)

        # Primary Action Button inside ASR
        self.btn_generate_en = QPushButton("🎬 Generate Subtitles (.srt)")
        self.btn_generate_en.setMinimumHeight(46)
        self.btn_generate_en.setObjectName("btn_primary")
        self.btn_generate_en.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_generate_en.clicked.connect(self._start_asr_pipeline)
        asr_layout.addWidget(self.btn_generate_en)

        main_layout.addWidget(asr_group)

        # Rate Limit Alert Banner
        self.rate_limit_frame = QFrame()
        self.rate_limit_frame.setStyleSheet("""
            QFrame {
                background-color: #422006;
                border: 1px solid #f59e0b;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        rl_layout = QHBoxLayout(self.rate_limit_frame)
        self.lbl_rl_icon = QLabel("⏳")
        self.lbl_rl_message = QLabel("Rate limit reached. Automatically rotating Cloudflare accounts...")
        self.lbl_rl_message.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 12px;")
        rl_layout.addWidget(self.lbl_rl_icon)
        rl_layout.addWidget(self.lbl_rl_message, 1)
        self.rate_limit_frame.hide()
        main_layout.addWidget(self.rate_limit_frame)

        # Progress Group
        prog_group = QGroupBox("Operation Progress")
        p_layout = QVBoxLayout(prog_group)

        prog_bar_box = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(24)
        prog_bar_box.addWidget(self.progress_bar)

        self.lbl_elapsed = QLabel("00:00")
        self.lbl_elapsed.setStyleSheet("font-family: monospace; font-weight: bold; color: #38bdf8;")
        prog_bar_box.addWidget(self.lbl_elapsed)
        p_layout.addLayout(prog_bar_box)

        self.lbl_stage = QLabel("Ready.")
        p_layout.addWidget(self.lbl_stage)
        main_layout.addWidget(prog_group)

        # Bottom Action Bar
        bottom_box = QHBoxLayout()
        self.btn_open_folder = QPushButton("📂 Open Output Folder")
        self.btn_open_folder.setMinimumHeight(36)
        self.btn_open_folder.setObjectName("btn_secondary")
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        bottom_box.addWidget(self.btn_open_folder)

        bottom_box.addStretch()

        self.btn_cancel = QPushButton("⛔ Cancel")
        self.btn_cancel.setMinimumHeight(36)
        self.btn_cancel.setObjectName("btn_danger")
        self.btn_cancel.setEnabled(False)  # Strictly disabled when not processing
        self.btn_cancel.clicked.connect(self._cancel_active_operation)
        bottom_box.addWidget(self.btn_cancel)

        main_layout.addLayout(bottom_box)

        scroll_area.setWidget(content_widget)
        self.setCentralWidget(scroll_area)

        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Online Subtitle Generator Ready.")

    def _update_asr_info(self):
        info = VERIFIED_ASR_PROVIDERS[0]
        self.lbl_asr_engine.setText(f"{info.display_name} — {info.model_display_name}")

        accounts = CredentialManager.get_cloudflare_accounts()
        configured = [a for a in accounts if a.get("configured")]
        cnt = len(configured)
        self.lbl_asr_pool.setText(
            f"Multi-Account Pool: {cnt} of 10 accounts active. "
            f"(Auto-failover on 10,000 daily neuron limit)"
        )

        chunk_cfg = load_chunking_settings()
        chunk_sec = chunk_cfg.get_chunk_duration_seconds("cloudflare")
        if chunk_sec is None:
            mode_str = "Single Request (Chunking Disabled)"
        else:
            mins_str = f"{chunk_sec / 60.0:.0f}"
            mode_str = f"Chunking: {mins_str}m segments (Silence-aware reconciliation)"
        self.lbl_asr_limits.setText(f"Limits: {info.free_tier_desc} | Mode: {mode_str}")

    def _browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Local Video File",
            str(self.last_output_dir or ""),
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.ts *.flv);;All Files (*.*)"
        )
        if not file_path:
            return

        path = Path(file_path)
        self.txt_video_path.setText(str(path))
        self.last_output_dir = path.parent
        self.btn_open_folder.setEnabled(True)

        try:
            info = self.ffmpeg.probe_media(path)
            dur_sec = info["duration_seconds"]
            dur_min = int(math.ceil(dur_sec / 60.0))
            self.current_video_duration = dur_sec

            audio_desc = f"{len(info['audio_streams'])} track(s)"
            if info["audio_streams"]:
                first_stream = info["audio_streams"][0]
                audio_desc = f"{first_stream.get('codec_name', 'audio')} ({first_stream.get('channels', 2)}ch)"

            self.lbl_media_info.setText(
                f"Duration: {dur_min} min ({int(dur_sec)}s) | Audio Tracks: {audio_desc} | Container: {info.get('format_name', 'media')}"
            )
            self.spin_start.setValue(0)
            self.spin_end.setValue(dur_min)
            self.statusBar.showMessage(f"Loaded: {path.name} ({dur_min} min)")

        except Exception as e:
            QMessageBox.critical(self, "Media Inspection Error", f"Failed to inspect media file:\n{e}")
            self.lbl_media_info.setText("Error analyzing video file.")

    def _set_full_range(self):
        if self.current_video_duration > 0:
            self.spin_start.setValue(0)
            self.spin_end.setValue(int(math.ceil(self.current_video_duration / 60.0)))

    def _start_asr_pipeline(self):
        try:
            video_path = self.txt_video_path.text().strip()
            if not video_path or not Path(video_path).exists():
                QMessageBox.warning(self, "Missing Video", "Please select a valid local video file first.")
                return

            # Check Cloudflare accounts
            accounts = CredentialManager.get_cloudflare_accounts()
            if not any(a.get("configured") for a in accounts):
                QMessageBox.warning(
                    self,
                    "Credentials Required",
                    "No Cloudflare Account configured.\nPlease configure at least one account in 'Cloudflare Accounts'."
                )
                self._open_credentials_dialog()
                return

            st_min = self.spin_start.value()
            end_min = self.spin_end.value()
            if self.current_video_duration > 0 and (float(end_min) * 60.0) >= self.current_video_duration:
                time_range = TimeRange(start_seconds=float(st_min) * 60.0, end_seconds=self.current_video_duration)
            else:
                time_range = TimeRange.from_minutes(float(st_min), float(end_min))

            out_srt = self.asr_service.get_default_output_path(video_path, ".en.srt", time_range)

            self._set_ui_busy(True)
            self.rate_limit_frame.hide()
            self.start_timestamp = time.time()
            self.lbl_elapsed.setText("00:00")
            self.timer.start(1000)

            self.active_worker = ASRWorker(
                asr_service=self.asr_service,
                video_path=Path(video_path),
                time_range=time_range,
                provider_id="cloudflare",
                model_id="@cf/openai/whisper-large-v3-turbo",
                output_path=out_srt
            )
            self.active_worker.progress.connect(self._on_progress_update)
            self.active_worker.rate_limit_wait.connect(self._on_rate_limit)
            self.active_worker.rate_limit_cleared.connect(self._on_rate_limit_cleared)
            self.active_worker.succeeded.connect(self._on_asr_success)
            self.active_worker.failed.connect(self._on_asr_failed)
            self.active_worker.finished.connect(self.active_worker.deleteLater)
            self.active_worker.start()

        except Exception as e:
            logger.error(f"Failed to start ASR pipeline: {e}", exc_info=True)
            self._set_ui_busy(False)
            self.timer.stop()
            QMessageBox.critical(self, "Launch Error", f"Failed to start subtitle extraction:\n{e}")

    def _on_progress_update(self, stage: str, percent: int):
        self.lbl_stage.setText(stage)
        self.progress_bar.setValue(percent)
        self.statusBar.showMessage(stage)

    def _on_rate_limit(self, provider: str, remaining_sec: int, attempt: int, reason: str):
        self.rate_limit_frame.show()
        self.lbl_rl_message.setText(
            f"Rate Limit ({provider}) — Attempt #{attempt}: Auto-rotating accounts / waiting {remaining_sec}s..."
        )

    def _on_rate_limit_cleared(self, provider: str):
        self.rate_limit_frame.hide()

    def _on_asr_success(self, result_path: str):
        self._set_ui_busy(False)
        self.timer.stop()
        self.active_worker = None
        self.rate_limit_frame.hide()

        p = Path(result_path)
        self.last_output_dir = p.parent
        self.btn_open_folder.setEnabled(True)
        self.progress_bar.setValue(100)
        self.lbl_stage.setText("Subtitles generated successfully!")
        self.statusBar.showMessage(f"Generated: {p.name}")
        QMessageBox.information(self, "Success", f"English subtitle generated successfully:\n{p.name}")

    def _on_asr_failed(self, message: str):
        self._set_ui_busy(False)
        self.timer.stop()
        self.active_worker = None
        self.rate_limit_frame.hide()

        self.lbl_stage.setText("Operation stopped.")
        self.progress_bar.setValue(0)
        if "cancelled" in message.lower():
            self.statusBar.showMessage("Operation cancelled.")
        else:
            self.statusBar.showMessage("Error generating subtitles.")
            QMessageBox.critical(self, "Processing Error", f"Failed to generate subtitles:\n{message}")

    def _cancel_active_operation(self):
        if self.active_worker:
            self.lbl_stage.setText("Cancelling operation...")
            self.statusBar.showMessage("Cancelling...")
            self.btn_cancel.setEnabled(False)  # Immediately disable to indicate cancelling
            self.active_worker.cancel()

    def _set_ui_busy(self, busy: bool):
        self.btn_browse.setEnabled(not busy)
        self.btn_batch_videos.setEnabled(not busy)
        self.btn_generate_en.setEnabled(not busy)
        self.btn_full_video.setEnabled(not busy)
        self.spin_start.setEnabled(not busy)
        self.spin_end.setEnabled(not busy)
        self.btn_keys.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)  # Enabled only during active processing

    def _update_elapsed_time(self):
        elapsed = int(time.time() - self.start_timestamp)
        mins, secs = divmod(elapsed, 60)
        self.lbl_elapsed.setText(f"{mins:02d}:{secs:02d}")

    def _open_video_batch(self):
        dlg = BatchDialog(
            batch_service=self.batch_service,
            database=self.db,
            ffmpeg_service=self.ffmpeg,
            parent=self,
            initial_tab=0
        )
        dlg.exec()

    def _open_credentials_dialog(self):
        dlg = CredentialsDialog(parent=self)
        dlg.exec()
        self._update_asr_info()

    def _open_logs_dialog(self):
        dlg = LogViewerDialog(parent=self)
        dlg.exec()

    def _open_output_folder(self):
        if self.last_output_dir and self.last_output_dir.exists():
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output_dir)))

    def closeEvent(self, event):
        if self.active_worker and self.active_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel Operation",
                "Subtitle extraction is currently in progress. Do you want to cancel and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.active_worker.cancel()
                self.active_worker.wait(1500)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
