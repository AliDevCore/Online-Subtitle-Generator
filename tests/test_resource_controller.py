"""
Tests for ResourceController, Windows process priority, threads, and memory budget.
"""

from app.core.resource_controller import ResourceController
from app.core.types import PerformanceSettings


def test_system_info_detection():
    info = ResourceController.get_system_info()
    assert info.physical_cores >= 1
    assert info.logical_cores >= 1
    assert info.total_ram_gb > 0.0
    assert info.available_ram_gb > 0.0


def test_effective_threads_automatic():
    ctrl = ResourceController(PerformanceSettings(cpu_usage_target=100, cpu_threads="Automatic"))
    threads = ctrl.get_effective_threads()
    assert threads >= 1


def test_effective_threads_manual():
    ctrl = ResourceController(PerformanceSettings(cpu_threads="6"))
    assert ctrl.get_effective_threads() == 6


def test_ram_warning_triggers_on_large_request():
    ctrl = ResourceController()
    # If model needs 999 GB RAM, must generate warning
    warn = ctrl.check_ram_warning(999.0)
    assert warn is not None
    assert "System paging" in warn


def test_throttling_never_active_at_100_percent():
    ctrl = ResourceController(PerformanceSettings(cpu_usage_target=100))
    # Must return immediately without sleeping
    import time
    start = time.time()
    for _ in range(10):
        ctrl.throttle_if_needed(is_local_cpu_intensive=True)
    elapsed = time.time() - start
    assert elapsed < 0.05  # essentially instantaneous
