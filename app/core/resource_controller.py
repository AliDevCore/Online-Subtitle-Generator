"""
Best-effort local CPU resource controller, Windows process priority & affinity manager,
and RAM detector/limiter.
Enforces strict separation between local CPU-intensive workloads and remote cloud network waits.
"""

from __future__ import annotations
import os
import sys
import time
import logging
from typing import Optional, List, Dict, Any
import psutil

from app.core.types import PerformanceSettings, SystemInfo

logger = logging.getLogger("OnlineSub.Performance")


class ResourceController:
    """
    Controls local CPU utilization, thread allocation, process priority, and memory budgeting.
    Does NOT throttle cloud API network waits.
    """

    # Windows Priority mapping
    PRIORITY_MAP = {
        "Below Normal": psutil.BELOW_NORMAL_PRIORITY_CLASS if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS") else 0x4000,
        "Normal": psutil.NORMAL_PRIORITY_CLASS if hasattr(psutil, "NORMAL_PRIORITY_CLASS") else 0x0020,
        "Above Normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS if hasattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS") else 0x8000,
    }

    def __init__(self, settings: Optional[PerformanceSettings] = None):
        self.settings = settings or PerformanceSettings()
        self._current_process = psutil.Process()
        self._smoothed_cpu: float = 0.0
        self._last_sample_time: float = time.time()
        self._is_local_work_active: bool = False

    @staticmethod
    def get_system_info() -> SystemInfo:
        """Query host hardware specifications (CPU, Cores, Memory, GPU)."""
        physical = psutil.cpu_count(logical=False) or 1
        logical = psutil.cpu_count(logical=True) or 1
        vm = psutil.virtual_memory()

        # Detect CPU model name
        cpu_name = "Unknown CPU"
        try:
            import platform
            cpu_name = platform.processor() or "x86_64 Processor"
            if sys.platform == "win32":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                cpu_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                winreg.CloseKey(key)
        except Exception:
            pass

        # Detect basic GPU presence
        has_gpu = False
        gpu_name = "None"
        try:
            # Check for NVIDIA / AMD via standard wmic or torch if present
            import subprocess
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=3
            )
            if res.returncode == 0 and res.stdout.strip():
                gpus = [g.strip() for g in res.stdout.splitlines() if g.strip()]
                if gpus:
                    gpu_name = ", ".join(gpus)
                    has_gpu = True
        except Exception:
            pass

        return SystemInfo(
            cpu_name=cpu_name.strip(),
            physical_cores=physical,
            logical_cores=logical,
            total_ram_gb=round(vm.total / (1024 ** 3), 2),
            available_ram_gb=round(vm.available / (1024 ** 3), 2),
            has_gpu=has_gpu,
            gpu_name=gpu_name
        )

    def apply_settings(self, settings: PerformanceSettings) -> None:
        """Apply process priority, affinity, and update targets."""
        self.settings = settings
        self.apply_process_priority(settings.process_priority)
        if settings.affinity_cpus is not None:
            self.apply_cpu_affinity(settings.affinity_cpus)

    def apply_process_priority(self, priority_name: str) -> bool:
        """Apply Windows process priority to the current application and workers."""
        target_val = self.PRIORITY_MAP.get(priority_name, psutil.NORMAL_PRIORITY_CLASS)
        try:
            self._current_process.nice(target_val)
            logger.info(f"Process priority set to: {priority_name}")
            return True
        except Exception as e:
            logger.warning(f"Could not adjust process priority to {priority_name}: {e}")
            return False

    def apply_cpu_affinity(self, cpu_indices: Optional[List[int]]) -> bool:
        """Limit process execution to specific logical CPU cores."""
        try:
            if not cpu_indices:
                all_cpus = list(range(psutil.cpu_count(logical=True) or 1))
                self._current_process.cpu_affinity(all_cpus)
            else:
                self._current_process.cpu_affinity(cpu_indices)
            logger.info(f"CPU affinity configured: {cpu_indices}")
            return True
        except Exception as e:
            logger.warning(f"Could not set CPU affinity: {e}")
            return False

    def get_effective_threads(self) -> int:
        """Calculate number of threads to assign to local models/workers."""
        if self.settings.cpu_threads == "Automatic":
            logical = psutil.cpu_count(logical=True) or 4
            # For 100% CPU target, use physical cores or sensible max to avoid oversubscription
            physical = psutil.cpu_count(logical=False) or (logical // 2)
            if self.settings.cpu_usage_target <= 50:
                return max(1, physical // 2)
            elif self.settings.cpu_usage_target <= 75:
                return max(1, int(physical * 0.75))
            return max(1, physical)
        else:
            try:
                val = int(self.settings.cpu_threads)
                return max(1, val)
            except ValueError:
                return 4

    def check_ram_warning(self, model_estimated_ram_gb: float) -> Optional[str]:
        """Check if loading a model may risk exceeding available system memory."""
        vm = psutil.virtual_memory()
        avail_gb = vm.available / (1024 ** 3)
        if model_estimated_ram_gb > avail_gb:
            return (
                f"Model requires ~{model_estimated_ram_gb:.1f} GB RAM, but only {avail_gb:.1f} GB is currently available. "
                "System paging or instability may occur. Consider selecting a smaller model or freeing memory."
            )
        return None

    def sample_cpu_percent(self) -> float:
        """Sample current process CPU percentage normalized across logical cores."""
        try:
            raw_percent = self._current_process.cpu_percent(interval=None)
            logical = psutil.cpu_count(logical=True) or 1
            # psutil.Process.cpu_percent() can exceed 100% on multicore systems (up to logical * 100%)
            normalized = raw_percent / logical
            # Exponential smoothing: alpha = 0.3
            self._smoothed_cpu = 0.7 * self._smoothed_cpu + 0.3 * normalized
            return self._smoothed_cpu
        except Exception:
            return 0.0

    def throttle_if_needed(self, is_local_cpu_intensive: bool = True) -> None:
        """
        Best-effort throttling hook called during local CPU-intensive loops (e.g. chunking/transcription).
        Strictly bypassed when target is 100% or during cloud network waits!
        """
        if not is_local_cpu_intensive or self.settings.cpu_usage_target >= 100:
            return

        current_usage = self.sample_cpu_percent()
        target = float(self.settings.cpu_usage_target)

        # Hysteresis: only throttle if CPU is above target + 5%
        if current_usage > (target + 5.0):
            # Compute proportional back-off sleep between 5ms and 35ms
            overshoot = min(50.0, current_usage - target)
            sleep_sec = 0.005 + (overshoot / 50.0) * 0.030
            time.sleep(sleep_sec)
