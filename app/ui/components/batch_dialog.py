"""
Batch processing management dialog for Online Subtitle Generator.
Allows queuing multiple video files with individual time ranges and automated overnight execution.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QFileDialog, QHeaderView, QMessageBox, QLabel,
    QCheckBox, QWidget, QProgressBar, QFrame, QSpinBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from app.core.config import get_app_icon
from app.services.batch_service import BatchService, BatchVideoItem, VIDEO_EXTENSIONS
from app.workers.batch_worker import VideoBatchWorker


class SetRangeDialog(QDialog):
    """Dialog to apply start/end minutes across all queued videos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Time Range For All Videos")
        self.resize(360, 200)
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        layout = QVBoxLayout(self)

        lbl_desc = QLabel("Set start and end minutes for all queued videos:\n(Select 'Full Duration' for entire movie)")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        row_st = QHBoxLayout()
        row_st.addWidget(QLabel("Start Minute:"))
        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 9999)
        self.spin_start.setSingleStep(1)
        self.spin_start.setValue(0)
        self.spin_start.setSuffix(" min")
        row_st.addWidget(self.spin_start)
        layout.addLayout(row_st)

        row_end = QHBoxLayout()
        row_end.addWidget(QLabel("End Minute:"))
        self.spin_end = QSpinBox()
        self.spin_end.setRange(0, 9999)
        self.spin_end.setSingleStep(1)
        self.spin_end.setValue(0)
        self.spin_end.setSuffix(" min")
        row_end.addWidget(self.spin_end)
        layout.addLayout(row_end)

        self.chk_full = QCheckBox("Full Duration (To end of video)")
        self.chk_full.setChecked(True)
        self.spin_end.setEnabled(False)
        self.chk_full.toggled.connect(lambda checked: self.spin_end.setEnabled(not checked))
        layout.addWidget(self.chk_full)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.btn_ok = QPushButton("Apply to All")
        self.btn_ok.setObjectName("btn_success")
        self.btn_ok.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        layout.addLayout(btn_box)

    @property
    def start_min(self) -> float:
        return float(self.spin_start.value())

    @property
    def end_min(self) -> Optional[float]:
        if self.chk_full.isChecked() or self.spin_end.value() <= 0:
            return None
        return float(self.spin_end.value())


class BatchDialog(QDialog):
    """Queue management dialog for multi-video batch subtitle generation."""

    def __init__(self, batch_service: BatchService, parent=None, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("Online Subtitle Generator — Batch Video Processing Manager")
        self.resize(920, 600)
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.batch_service = batch_service
        self.active_video_worker: Optional[VideoBatchWorker] = None
        self._updating_table = False

        self._build_ui()
        self._refresh_video_table()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(12)

        # Top Bar
        top_bar = QHBoxLayout()
        self.btn_add_video_folder = QPushButton("📁 Add Video Folder...")
        self.btn_add_video_folder.clicked.connect(self._add_video_folder)
        top_bar.addWidget(self.btn_add_video_folder)

        self.btn_add_video_files = QPushButton("➕ Add Video Files...")
        self.btn_add_video_files.clicked.connect(self._add_video_files)
        top_bar.addWidget(self.btn_add_video_files)

        self.btn_set_range = QPushButton("⏱️ Set Time Range For All...")
        self.btn_set_range.setObjectName("btn_secondary")
        self.btn_set_range.clicked.connect(self._set_range_for_all)
        top_bar.addWidget(self.btn_set_range)

        self.btn_remove_video = QPushButton("🗑️ Remove Selected")
        self.btn_remove_video.setObjectName("btn_secondary")
        self.btn_remove_video.clicked.connect(self._remove_selected_videos)
        top_bar.addWidget(self.btn_remove_video)

        self.btn_clear_videos = QPushButton("🧹 Clear All")
        self.btn_clear_videos.setObjectName("btn_secondary")
        self.btn_clear_videos.clicked.connect(self._clear_all_videos)
        top_bar.addWidget(self.btn_clear_videos)

        top_bar.addStretch()
        root_layout.addLayout(top_bar)

        # Video Table
        self.table_videos = QTableWidget(0, 6)
        self.table_videos.setHorizontalHeaderLabels([
            "Video File", "Duration", "Start (Min)", "End (Min)", "Status", "Output Subtitle (.srt)"
        ])
        self.table_videos.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_videos.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_videos.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_videos.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_videos.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_videos.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table_videos.itemChanged.connect(self._on_video_cell_changed)
        root_layout.addWidget(self.table_videos)

        # Rate Limit Alert Banner (hidden by default)
        self.frame_video_rate_limit = QFrame()
        self.frame_video_rate_limit.setStyleSheet(
            "QFrame { background-color: #3b2d03; border: 1px solid #d97706; border-radius: 6px; padding: 6px; }"
            "QLabel { color: #fef08a; font-weight: 600; font-size: 13px; }"
        )
        self.lbl_video_rate_limit = QLabel("")
        self.lbl_video_rate_limit.setAlignment(Qt.AlignCenter)
        frame_vl = QVBoxLayout(self.frame_video_rate_limit)
        frame_vl.addWidget(self.lbl_video_rate_limit)
        self.frame_video_rate_limit.setVisible(False)
        root_layout.addWidget(self.frame_video_rate_limit)

        # Progress bar
        self.progress_video = QProgressBar()
        self.progress_video.setValue(0)
        root_layout.addWidget(self.progress_video)

        # Bottom Bar
        bottom_box = QHBoxLayout()
        self.lbl_video_count = QLabel("0 videos in queue")
        bottom_box.addWidget(self.lbl_video_count)
        bottom_box.addStretch()

        self.btn_start_video = QPushButton("▶ Start Video Batch")
        self.btn_start_video.setObjectName("btn_success")
        self.btn_start_video.setFixedHeight(36)
        self.btn_start_video.clicked.connect(self._start_video_batch)
        bottom_box.addWidget(self.btn_start_video)

        self.btn_cancel_video = QPushButton("⏹ Cancel Batch")
        self.btn_cancel_video.setObjectName("btn_danger")
        self.btn_cancel_video.setFixedHeight(36)
        self.btn_cancel_video.setEnabled(False)
        self.btn_cancel_video.clicked.connect(self._cancel_video_batch)
        bottom_box.addWidget(self.btn_cancel_video)

        self.btn_close_video = QPushButton("Close")
        self.btn_close_video.setObjectName("btn_secondary")
        self.btn_close_video.setFixedHeight(36)
        self.btn_close_video.clicked.connect(self.close)
        bottom_box.addWidget(self.btn_close_video)

        root_layout.addLayout(bottom_box)

    def _refresh_video_table(self):
        self._updating_table = True
        self.table_videos.setRowCount(0)
        for item in self.batch_service.video_queue:
            row = self.table_videos.rowCount()
            self.table_videos.insertRow(row)

            # 0: File Name
            f_item = QTableWidgetItem(item.name)
            f_item.setFlags(f_item.flags() & ~Qt.ItemIsEditable)
            f_item.setToolTip(str(item.video_path))
            self.table_videos.setItem(row, 0, f_item)

            # 1: Duration
            d_item = QTableWidgetItem(item.duration_str)
            d_item.setFlags(d_item.flags() & ~Qt.ItemIsEditable)
            self.table_videos.setItem(row, 1, d_item)

            # 2: Start Min (editable, integer)
            st_val = f"{int(round(item.start_min))}"
            st_item = QTableWidgetItem(st_val)
            self.table_videos.setItem(row, 2, st_item)

            # 3: End Min (editable, integer)
            end_val = f"{int(round(item.end_min))}" if (item.end_min and item.end_min > 0) else "End"
            end_item = QTableWidgetItem(end_val)
            self.table_videos.setItem(row, 3, end_item)

            # 4: Status
            s_item = QTableWidgetItem(item.status.value)
            s_item.setFlags(s_item.flags() & ~Qt.ItemIsEditable)
            self._color_status_item(s_item, item.status.value)
            self.table_videos.setItem(row, 4, s_item)

            # 5: Output SRT
            out_name = item.generated_en_srt.name if item.generated_en_srt else "-"
            out_item = QTableWidgetItem(out_name)
            out_item.setFlags(out_item.flags() & ~Qt.ItemIsEditable)
            self.table_videos.setItem(row, 5, out_item)

        cnt = len(self.batch_service.video_queue)
        self.lbl_video_count.setText(f"{cnt} video(s) in queue")
        self._updating_table = False

    def _color_status_item(self, item: QTableWidgetItem, status: str):
        if status == "COMPLETED":
            item.setForeground(QColor("#4ade80"))
        elif status in ("TRANSCRIBING", "EXTRACTING"):
            item.setForeground(QColor("#38bdf8"))
        elif status == "FAILED":
            item.setForeground(QColor("#f87171"))
        elif status == "CANCELLED":
            item.setForeground(QColor("#fbbf24"))
        else:
            item.setForeground(QColor("#94a3b8"))

    def _on_video_cell_changed(self, item: QTableWidgetItem):
        if self._updating_table:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self.batch_service.video_queue):
            return

        batch_item = self.batch_service.video_queue[row]
        try:
            if col == 2:  # Start min
                val = max(0.0, float(int(round(float(item.text().strip())))))
                batch_item.start_min = val
                item.setText(f"{int(val)}")
            elif col == 3:  # End min
                txt = item.text().strip().lower()
                if txt in ("end", "full", "0", ""):
                    batch_item.end_min = None
                    item.setText("End")
                else:
                    val = max(0.0, float(int(round(float(txt)))))
                    batch_item.end_min = val
                    item.setText(f"{int(val)}")
        except ValueError:
            pass

    def _add_video_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Videos")
        if not folder:
            return
        found = self.batch_service.scan_and_add_videos(folder)
        self._refresh_video_table()
        if found:
            # Prompt user to ask if they want to configure time ranges
            ans = QMessageBox.question(
                self,
                "Time Range",
                f"Found {len(found)} videos.\nDo you want to set a specific time range for these videos (e.g. from minute X to Y)?\n\nClick 'No' to process entire movies.",
                QMessageBox.Yes | QMessageBox.No
            )
            if ans == QMessageBox.Yes:
                self._set_range_for_all()
        else:
            QMessageBox.information(self, "No Videos Found", "No supported video files found in the selected folder.")

    def _add_video_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Video Files",
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts *.wmv);;All Files (*.*)"
        )
        if not files:
            return
        for f in files:
            self.batch_service.add_video_file(f)
        self._refresh_video_table()

    def _set_range_for_all(self):
        if not self.batch_service.video_queue:
            QMessageBox.information(self, "Queue Empty", "Add video files first before setting time ranges.")
            return

        dlg = SetRangeDialog(self)
        if dlg.exec():
            st = dlg.start_min
            end = dlg.end_min
            for item in self.batch_service.video_queue:
                item.start_min = st
                item.end_min = end
            self._refresh_video_table()

    def _remove_selected_videos(self):
        selected_rows = sorted(set(idx.row() for idx in self.table_videos.selectedIndexes()), reverse=True)
        for r in selected_rows:
            if 0 <= r < len(self.batch_service.video_queue):
                self.batch_service.video_queue.pop(r)
        self._refresh_video_table()

    def _clear_all_videos(self):
        self.batch_service.clear_video_queue()
        self._refresh_video_table()

    def _start_video_batch(self):
        if not self.batch_service.video_queue:
            QMessageBox.information(self, "Queue Empty", "Please add at least one video file.")
            return

        self._set_video_ui_busy(True)
        self.progress_video.setValue(0)
        self.frame_video_rate_limit.setVisible(False)

        self.active_video_worker = VideoBatchWorker(
            batch_service=self.batch_service,
            asr_provider="cloudflare",
            asr_model="@cf/openai/whisper",
            parent=self
        )
        self.active_video_worker.item_updated.connect(self._on_video_item_update)
        self.active_video_worker.rate_limit_wait.connect(self._on_video_rate_limit)
        self.active_video_worker.rate_limit_cleared.connect(self._on_video_rate_limit_cleared)
        self.active_video_worker.batch_finished.connect(self._on_video_batch_finished)
        self.active_video_worker.failed.connect(self._on_video_batch_failed)
        self.active_video_worker.start()

    def _cancel_video_batch(self):
        if self.active_video_worker:
            self.lbl_video_rate_limit.setText("Cancelling video batch...")
            self.active_video_worker.cancel()

    def _on_video_item_update(self, name: str, idx: int, total: int, status: str):
        pct = int(((idx - 1) / max(total, 1)) * 100)
        self.progress_video.setValue(pct)
        self._refresh_video_table()

    def _on_video_rate_limit(self, provider: str, rem_sec: int, attempt: int, reason: str):
        self.frame_video_rate_limit.setVisible(True)
        self.lbl_video_rate_limit.setText(
            f"⏳ {provider} Quota Exhausted across all accounts. Waiting {rem_sec}s before next retry (Attempt {attempt})..."
        )

    def _on_video_rate_limit_cleared(self, provider: str):
        self.frame_video_rate_limit.setVisible(False)

    def _on_video_batch_finished(self, success_cnt: int, failed_cnt: int):
        self._set_video_ui_busy(False)
        self.active_video_worker = None
        self.progress_video.setValue(100)
        self.frame_video_rate_limit.setVisible(False)
        self._refresh_video_table()

        QMessageBox.information(
            self,
            "Batch Completed",
            f"Video Batch Completed!\nSuccessful: {success_cnt}\nFailed/Cancelled: {failed_cnt}"
        )

    def _on_video_batch_failed(self, err: str):
        self._set_video_ui_busy(False)
        self.active_video_worker = None
        self.frame_video_rate_limit.setVisible(False)
        self._refresh_video_table()
        QMessageBox.critical(self, "Batch Error", f"Batch execution stopped with error:\n{err}")

    def _set_video_ui_busy(self, busy: bool):
        self.btn_add_video_folder.setEnabled(not busy)
        self.btn_add_video_files.setEnabled(not busy)
        self.btn_set_range.setEnabled(not busy)
        self.btn_remove_video.setEnabled(not busy)
        self.btn_clear_videos.setEnabled(not busy)
        self.btn_start_video.setEnabled(not busy)
        self.btn_cancel_video.setEnabled(busy)
