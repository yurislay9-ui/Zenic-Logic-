"""
Unit tests for ResourceGovernor

Tests resource monitoring, adaptive budgeting, GC tuning,
and singleton management.
"""

import gc
import sys
import time
import threading
import pytest

sys.path.insert(0, "/home/z/my-project/Zenic-Logic-")

from src.core.shared.resource_governor import (
    ResourceGovernor,
    get_governor,
    init_governor,
    tune_gc_for_arm,
    set_process_priority_low,
)


# ============================================================
#  Constructor Tests
# ============================================================

class TestResourceGovernorConstructor:
    """Tests for ResourceGovernor initialization."""

    def test_default_parameters(self):
        """Should use default RAM limit and GC threshold."""
        gov = ResourceGovernor()
        assert gov.ram_limit_mb == ResourceGovernor.DEFAULT_RAM_LIMIT_MB
        assert gov.gc_threshold_mb == ResourceGovernor.DEFAULT_GC_THRESHOLD_MB

    def test_custom_ram_limit(self):
        """Should accept custom RAM limit."""
        gov = ResourceGovernor(ram_limit_mb=1024)
        assert gov.ram_limit_mb == 1024

    def test_custom_gc_threshold(self):
        """Should accept custom GC threshold."""
        gov = ResourceGovernor(gc_threshold_mb=768)
        assert gov.gc_threshold_mb == 768

    def test_default_cpu_sleep(self):
        """Should have DEFAULT_CPU_SLEEP_MS constant."""
        assert ResourceGovernor.DEFAULT_CPU_SLEEP_MS == 50

    def test_initial_state(self):
        """Should initialize monitoring state correctly."""
        gov = ResourceGovernor()
        assert gov._cpu_usage == 0.0
        assert gov._ram_usage_mb == 0.0
        assert gov._thermal_throttle == 1.0
        assert gov._gc_count == 0
        assert gov._request_count == 0

    def test_stats_initialized(self):
        """Should initialize stats dict."""
        gov = ResourceGovernor()
        assert "gc_forced" in gov.stats
        assert "thermal_throttles" in gov.stats
        assert "ram_peaks" in gov.stats
        assert "requests_served" in gov.stats

    def test_default_constants(self):
        """Should have sensible default constants."""
        assert ResourceGovernor.DEFAULT_RAM_LIMIT_MB == 2048
        assert ResourceGovernor.DEFAULT_GC_THRESHOLD_MB == 1536
        assert ResourceGovernor.THERMAL_SCALE_BACK_THRESHOLD == 30


# ============================================================
#  Monitoring Tests
# ============================================================

class TestMonitoring:
    """Tests for start/stop monitoring."""

    def test_start_monitoring(self):
        """Should start the monitoring thread."""
        gov = ResourceGovernor()
        gov.start_monitoring()
        try:
            assert gov._monitor_thread is not None
            assert gov._monitor_thread.is_alive()
        finally:
            gov.stop_monitoring()

    def test_stop_monitoring(self):
        """Should stop the monitoring thread."""
        gov = ResourceGovernor()
        gov.start_monitoring()
        gov.stop_monitoring()
        assert gov._stop_event.is_set()

    def test_double_start(self):
        """Should not create duplicate threads on double start."""
        gov = ResourceGovernor()
        gov.start_monitoring()
        try:
            thread1 = gov._monitor_thread
            gov.start_monitoring()  # Second call
            thread2 = gov._monitor_thread
            assert thread1 is thread2  # Same thread
        finally:
            gov.stop_monitoring()

    def test_monitoring_is_daemon(self):
        """Monitoring thread should be a daemon thread."""
        gov = ResourceGovernor()
        gov.start_monitoring()
        try:
            assert gov._monitor_thread.daemon is True
        finally:
            gov.stop_monitoring()


# ============================================================
#  CPU Throttle Tests
# ============================================================

class TestCPUThrottle:
    """Tests for cpu_throttle_sleep."""

    def test_throttle_sleep_returns(self):
        """cpu_throttle_sleep should return (not hang)."""
        gov = ResourceGovernor()
        start = time.time()
        gov.cpu_throttle_sleep()
        elapsed = time.time() - start
        # Should sleep at least a little
        assert elapsed >= 0.04  # At least ~50ms (default sleep)

    def test_throttle_with_low_cpu(self):
        """Low CPU should result in default sleep."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.2
        start = time.time()
        gov.cpu_throttle_sleep()
        elapsed = time.time() - start
        # Should be around 50ms for low CPU
        assert elapsed >= 0.04

    def test_throttle_with_high_cpu(self):
        """High CPU should result in longer sleep."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.9  # > 0.8
        start = time.time()
        gov.cpu_throttle_sleep()
        elapsed = time.time() - start
        # Should be around 150ms for high CPU (3x base)
        assert elapsed >= 0.1

    def test_throttle_with_thermal(self):
        """Thermal throttle should affect sleep duration."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.2
        gov._thermal_throttle = 0.5
        start = time.time()
        gov.cpu_throttle_sleep()
        elapsed = time.time() - start
        # Lower thermal throttle -> longer effective sleep (divided by smaller number)
        assert elapsed >= 0.04


# ============================================================
#  Adaptive Budget Tests
# ============================================================

class TestAdaptiveBudgets:
    """Tests for adaptive MCTS simulations and solver timeout."""

    def test_adaptive_mcts_full_sims(self):
        """Low CPU should allow full MCTS simulations."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.1
        gov._thermal_throttle = 1.0
        sims = gov.get_adaptive_mcts_simulations(base_simulations=100)
        assert sims == 100

    def test_adaptive_mcts_reduced_sims(self):
        """High CPU should reduce MCTS simulations."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.9
        gov._thermal_throttle = 1.0
        sims = gov.get_adaptive_mcts_simulations(base_simulations=100)
        assert sims < 100
        assert sims >= 10  # Minimum 10

    def test_adaptive_mcts_thermal_reduction(self):
        """Thermal throttle should further reduce MCTS simulations."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.1
        gov._thermal_throttle = 0.5
        sims = gov.get_adaptive_mcts_simulations(base_simulations=100)
        assert sims == 50  # 100 * 0.5

    def test_adaptive_mcts_minimum(self):
        """MCTS simulations should never go below 10."""
        gov = ResourceGovernor()
        gov._cpu_usage = 1.0
        gov._thermal_throttle = 0.1
        sims = gov.get_adaptive_mcts_simulations(base_simulations=100)
        assert sims >= 10

    def test_adaptive_solver_timeout_full(self):
        """Low resource usage should allow full solver timeout."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.1
        gov._ram_usage_mb = 100
        gov._thermal_throttle = 1.0
        timeout = gov.get_adaptive_solver_timeout(base_timeout_ms=15000)
        assert timeout == 15000

    def test_adaptive_solver_timeout_reduced_ram(self):
        """High RAM usage should reduce solver timeout."""
        gov = ResourceGovernor()
        gov._ram_usage_mb = 1900  # > 80% of 2048
        gov._thermal_throttle = 1.0
        timeout = gov.get_adaptive_solver_timeout(base_timeout_ms=15000)
        assert timeout < 15000

    def test_adaptive_solver_timeout_thermal(self):
        """Thermal throttle should reduce solver timeout."""
        gov = ResourceGovernor()
        gov._ram_usage_mb = 0
        gov._thermal_throttle = 0.5
        timeout = gov.get_adaptive_solver_timeout(base_timeout_ms=15000)
        assert timeout == 7500  # 15000 * 0.5

    def test_adaptive_solver_timeout_minimum(self):
        """Solver timeout should never go below 3000ms."""
        gov = ResourceGovernor()
        gov._ram_usage_mb = 3000  # Very high
        gov._thermal_throttle = 0.01  # Very low
        timeout = gov.get_adaptive_solver_timeout(base_timeout_ms=15000)
        assert timeout >= 3000


# ============================================================
#  Request Lifecycle Tests
# ============================================================

class TestRequestLifecycle:
    """Tests for pre_request and post_request."""

    def test_pre_request_increments_count(self):
        """pre_request should increment request counters."""
        gov = ResourceGovernor()
        initial_count = gov._request_count
        gov.pre_request()
        assert gov._request_count == initial_count + 1
        assert gov.stats["requests_served"] == initial_count + 1

    def test_post_request_runs(self):
        """post_request should run without error."""
        gov = ResourceGovernor()
        gov.post_request()  # Should not raise

    def test_multiple_requests(self):
        """Multiple requests should increment counter."""
        gov = ResourceGovernor()
        for _ in range(5):
            gov.pre_request()
        assert gov._request_count == 5


# ============================================================
#  RAM and Memory Tests
# ============================================================

class TestRAMAndMemory:
    """Tests for RAM-related methods."""

    def test_get_z3_memory_limit_normal(self):
        """Should return a reasonable Z3 memory limit."""
        gov = ResourceGovernor(ram_limit_mb=2048)
        gov._ram_usage_mb = 500
        limit = gov.get_z3_memory_limit_mb()
        assert 128 <= limit <= 512

    def test_get_z3_memory_limit_low_ram(self):
        """Should return minimum 128MB when RAM is very low."""
        gov = ResourceGovernor(ram_limit_mb=2048)
        gov._ram_usage_mb = 2000  # Almost all RAM used
        limit = gov.get_z3_memory_limit_mb()
        assert limit >= 128

    def test_is_ram_critical_normal(self):
        """Should return False when RAM is not critical."""
        gov = ResourceGovernor(ram_limit_mb=2048)
        gov._ram_usage_mb = 500
        assert gov.is_ram_critical() is False

    def test_is_ram_critical_high(self):
        """Should return True when RAM exceeds 95% limit."""
        gov = ResourceGovernor(ram_limit_mb=2048)
        gov._ram_usage_mb = 2000  # > 95% of 2048
        assert gov.is_ram_critical() is True

    def test_is_ram_critical_boundary(self):
        """Should correctly handle boundary at 95%."""
        gov = ResourceGovernor(ram_limit_mb=1000)
        gov._ram_usage_mb = 949  # Just below 95%
        assert gov.is_ram_critical() is False
        gov._ram_usage_mb = 960  # Above 95%
        assert gov.is_ram_critical() is True


# ============================================================
#  Status Reporting Tests
# ============================================================

class TestStatusReporting:
    """Tests for get_status method."""

    def test_status_returns_dict(self):
        """get_status should return a dictionary."""
        gov = ResourceGovernor()
        status = gov.get_status()
        assert isinstance(status, dict)

    def test_status_fields(self):
        """get_status should include all expected fields."""
        gov = ResourceGovernor()
        status = gov.get_status()
        assert "cpu_usage_pct" in status
        assert "ram_usage_mb" in status
        assert "ram_limit_mb" in status
        assert "thermal_throttle" in status
        assert "adaptive_mcts_sims" in status
        assert "adaptive_solver_timeout_ms" in status
        assert "z3_memory_limit_mb" in status
        assert "stats" in status

    def test_status_cpu_usage_percentage(self):
        """cpu_usage_pct should be a percentage (0-100)."""
        gov = ResourceGovernor()
        status = gov.get_status()
        assert 0 <= status["cpu_usage_pct"] <= 100

    def test_status_thermal_throttle_range(self):
        """thermal_throttle should be between 0 and 1."""
        gov = ResourceGovernor()
        status = gov.get_status()
        assert 0 < status["thermal_throttle"] <= 1.0


# ============================================================
#  Singleton Tests
# ============================================================

class TestSingleton:
    """Tests for get_governor and init_governor."""

    def test_get_governor_returns_instance(self):
        """get_governor should return a ResourceGovernor instance."""
        # Reset singleton
        import src.core.shared.resource_governor as rg_module
        rg_module._governor = None
        gov = get_governor()
        assert isinstance(gov, ResourceGovernor)
        # Cleanup
        rg_module._governor = None

    def test_get_governor_singleton(self):
        """get_governor should return the same instance on repeated calls."""
        import src.core.shared.resource_governor as rg_module
        rg_module._governor = None
        gov1 = get_governor()
        gov2 = get_governor()
        assert gov1 is gov2
        # Cleanup
        rg_module._governor = None

    def test_init_governor_with_config(self):
        """init_governor should create a governor with custom config."""
        import src.core.shared.resource_governor as rg_module
        rg_module._governor = None
        gov = init_governor(ram_limit_mb=1024)
        assert isinstance(gov, ResourceGovernor)
        assert gov.ram_limit_mb == 1024
        # Cleanup
        gov.stop_monitoring()
        rg_module._governor = None

    def test_init_governor_starts_monitoring(self):
        """init_governor should start monitoring."""
        import src.core.shared.resource_governor as rg_module
        rg_module._governor = None
        gov = init_governor()
        assert gov._monitor_thread is not None
        assert gov._monitor_thread.is_alive()
        # Cleanup
        gov.stop_monitoring()
        rg_module._governor = None


# ============================================================
#  GC Tuning Tests
# ============================================================

class TestGCTuning:
    """Tests for tune_gc_for_arm function."""

    def test_tune_gc_for_arm_sets_thresholds(self):
        """tune_gc_for_arm should set GC thresholds for ARM."""
        original = gc.get_threshold()
        try:
            tune_gc_for_arm()
            new_thresholds = gc.get_threshold()
            assert new_thresholds == (1000, 15, 15)
        finally:
            # Restore original thresholds
            gc.set_threshold(*original)

    def test_tune_gc_idempotent(self):
        """Calling tune_gc_for_arm twice should not change thresholds."""
        original = gc.get_threshold()
        try:
            tune_gc_for_arm()
            tune_gc_for_arm()
            assert gc.get_threshold() == (1000, 15, 15)
        finally:
            gc.set_threshold(*original)


# ============================================================
#  Process Priority Tests
# ============================================================

class TestProcessPriority:
    """Tests for set_process_priority_low function."""

    def test_set_process_priority_low_no_crash(self):
        """set_process_priority_low should not crash (may fail gracefully)."""
        # This may fail due to permissions, but should not raise
        try:
            set_process_priority_low()
        except (PermissionError, AttributeError):
            pass  # Expected in some environments
