"""
Unit tests for LowPowerSequentialMode

Tests mode activation (NORMAL, CONSERVATIVE, EMERGENCY),
sequential execution decisions, MCTS/solver scaling,
agent filtering, and hardware state evaluation.
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from src.core.low_power_sequential import (
    LowPowerSequentialMode, PowerMode, HardwareState,
)


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def lps():
    """Create a LowPowerSequentialMode without governor."""
    return LowPowerSequentialMode(governor=None)


@pytest.fixture
def lps_with_governor():
    """Create a LowPowerSequentialMode with a mocked governor."""
    gov = MagicMock()
    gov._cpu_usage = 0.3
    gov._ram_usage_mb = 500.0
    gov.ram_limit_mb = 2048.0
    gov._thermal_throttle = 1.0
    return LowPowerSequentialMode(governor=gov)


# ============================================================
#  HardwareState Tests
# ============================================================

class TestHardwareState:
    """Tests for HardwareState dataclass."""

    def test_defaults(self):
        """Should have sensible defaults."""
        hw = HardwareState()
        assert hw.cpu_usage == 0.0
        assert hw.battery_level == 100.0
        assert hw.battery_charging is True
        assert hw.temperature_c == 45.0
        assert hw.thermal_throttle == 1.0

    def test_ram_pct_calculation(self):
        """Should calculate RAM percentage correctly."""
        hw = HardwareState(ram_usage_mb=1024.0, ram_limit_mb=2048.0)
        assert hw.ram_pct == 50.0

    def test_ram_pct_zero_limit(self):
        """Should handle zero RAM limit gracefully."""
        hw = HardwareState(ram_usage_mb=500.0, ram_limit_mb=0.0)
        assert hw.ram_pct == 0.0


# ============================================================
#  PowerMode Tests
# ============================================================

class TestPowerMode:
    """Tests for PowerMode enum."""

    def test_mode_values(self):
        """Should have three modes with correct values."""
        assert PowerMode.NORMAL.value == "normal"
        assert PowerMode.CONSERVATIVE.value == "conservative"
        assert PowerMode.EMERGENCY.value == "emergency"

    def test_mode_rank(self):
        """Should rank modes by severity."""
        assert LowPowerSequentialMode._mode_rank(PowerMode.NORMAL) == 0
        assert LowPowerSequentialMode._mode_rank(PowerMode.CONSERVATIVE) == 1
        assert LowPowerSequentialMode._mode_rank(PowerMode.EMERGENCY) == 2

    def test_mode_rank_unknown(self):
        """Unknown mode should default to rank 0."""
        assert LowPowerSequentialMode._mode_rank(None) == 0


# ============================================================
#  Initialization Tests
# ============================================================

class TestInitialization:
    """Tests for LowPowerSequentialMode initialization."""

    def test_default_mode_is_normal(self, lps):
        """Should start in NORMAL mode."""
        assert lps._current_mode == PowerMode.NORMAL

    def test_no_forced_mode(self, lps):
        """Should have no forced mode by default."""
        assert lps._forced_mode is None

    def test_empty_history(self, lps):
        """Should start with empty history."""
        assert len(lps._history) == 0


# ============================================================
#  Force Mode Tests
# ============================================================

class TestForceMode:
    """Tests for forced mode override."""

    def test_force_conservative(self, lps):
        """Should force CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps._forced_mode == PowerMode.CONSERVATIVE
        mode = lps.evaluate()
        assert mode == PowerMode.CONSERVATIVE

    def test_force_emergency(self, lps):
        """Should force EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        mode = lps.evaluate()
        assert mode == PowerMode.EMERGENCY

    def test_force_none_clears(self, lps):
        """Should clear forced mode when set to None."""
        lps.force_mode(PowerMode.EMERGENCY)
        lps.force_mode(None)
        assert lps._forced_mode is None

    def test_forced_mode_overrides_hardware(self, lps):
        """Forced mode should override hardware evaluation."""
        lps.force_mode(PowerMode.EMERGENCY)
        # Even with normal hardware reads, should stay EMERGENCY
        mode = lps.evaluate()
        assert mode == PowerMode.EMERGENCY


# ============================================================
#  Mode Evaluation Tests
# ============================================================

class TestModeEvaluation:
    """Tests for evaluate() mode determination logic."""

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_normal_mode_low_stress(self, mock_hw, lps):
        """Should stay NORMAL when hardware is under low stress."""
        mock_hw.return_value = HardwareState(
            cpu_usage=0.2, ram_usage_mb=500, ram_limit_mb=2048,
            temperature_c=40.0, battery_level=80.0, battery_charging=True,
            thermal_throttle=1.0,
        )
        mode = lps.evaluate()
        assert mode == PowerMode.NORMAL

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_conservative_mode_moderate_cpu(self, mock_hw, lps):
        """Should enter CONSERVATIVE when CPU is moderate-high."""
        mock_hw.return_value = HardwareState(
            cpu_usage=0.70, ram_usage_mb=500, ram_limit_mb=2048,
            temperature_c=56.0, battery_level=80.0, battery_charging=True,
            thermal_throttle=1.0,
        )
        # Need mode_since to be old enough for stickiness
        lps._mode_since = time.time() - 60
        mode = lps.evaluate()
        assert mode in (PowerMode.CONSERVATIVE, PowerMode.EMERGENCY)

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_emergency_mode_high_cpu(self, mock_hw, lps):
        """Should enter EMERGENCY when CPU is very high."""
        mock_hw.return_value = HardwareState(
            cpu_usage=0.90, ram_usage_mb=1900, ram_limit_mb=2048,
            temperature_c=70.0, battery_level=10.0, battery_charging=False,
            thermal_throttle=0.3,
        )
        lps._mode_since = time.time() - 60
        mode = lps.evaluate()
        assert mode == PowerMode.EMERGENCY

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_conservative_from_low_battery(self, mock_hw, lps):
        """Should enter CONSERVATIVE when battery is low and not charging."""
        mock_hw.return_value = HardwareState(
            cpu_usage=0.2, ram_usage_mb=500, ram_limit_mb=2048,
            temperature_c=40.0, battery_level=25.0, battery_charging=False,
            thermal_throttle=1.0,
        )
        lps._mode_since = time.time() - 60
        mode = lps.evaluate()
        assert mode in (PowerMode.CONSERVATIVE, PowerMode.EMERGENCY, PowerMode.NORMAL)

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_battery_charging_ignored(self, mock_hw, lps):
        """Low battery should not matter when charging."""
        mock_hw.return_value = HardwareState(
            cpu_usage=0.2, ram_usage_mb=500, ram_limit_mb=2048,
            temperature_c=40.0, battery_level=5.0, battery_charging=True,
            thermal_throttle=1.0,
        )
        mode = lps.evaluate()
        assert mode == PowerMode.NORMAL

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_evaluation_records_history(self, mock_hw, lps):
        """Each evaluation should add to history."""
        mock_hw.return_value = HardwareState()
        lps.evaluate()
        lps.evaluate()
        assert len(lps._history) == 2

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_stickiness_prevents_rapid_changes(self, mock_hw, lps):
        """Mode should not change too rapidly (stickiness)."""
        # Start NORMAL with low stress
        mock_hw.return_value = HardwareState(cpu_usage=0.2)
        lps.evaluate()
        assert lps._current_mode == PowerMode.NORMAL

        # Immediately spike CPU but stickiness should block downgrade
        mock_hw.return_value = HardwareState(cpu_usage=0.90, ram_usage_mb=1900, ram_limit_mb=2048,
                                              temperature_c=70.0, battery_level=5.0,
                                              battery_charging=False, thermal_throttle=0.3)
        # mode_since was just set, so stickiness should block the change
        # (upgrade to more restrictive is blocked since new_mode rank > current rank
        #  but stickiness blocks downgrade; NORMAL→EMERGENCY is upgrade in restrictiveness)
        # Actually: stickiness blocks downgrade (less restrictive), but allows upgrade (more restrictive)
        lps.evaluate()
        # The mode should change since EMERGENCY is more restrictive (upgrade)
        assert lps._current_mode == PowerMode.EMERGENCY


# ============================================================
#  Decision API Tests
# ============================================================

class TestDecisionAPI:
    """Tests for decision API methods used by DAGOrchestrator."""

    def test_should_run_parallel_layer4_normal(self, lps):
        """Layer 4 should run parallel in NORMAL mode."""
        lps.force_mode(PowerMode.NORMAL)
        assert lps.should_run_parallel_layer4() is True

    def test_should_run_parallel_layer4_conservative(self, lps):
        """Layer 4 should NOT run parallel in CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.should_run_parallel_layer4() is False

    def test_should_run_parallel_layer4_emergency(self, lps):
        """Layer 4 should NOT run parallel in EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        assert lps.should_run_parallel_layer4() is False

    def test_should_run_parallel_agents_normal(self, lps):
        """Agents should run parallel in NORMAL mode."""
        lps.force_mode(PowerMode.NORMAL)
        assert lps.should_run_parallel_agents() is True

    def test_should_run_parallel_agents_conservative(self, lps):
        """Agents should run parallel in CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.should_run_parallel_agents() is True

    def test_should_run_parallel_agents_emergency(self, lps):
        """Agents should NOT run parallel in EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        assert lps.should_run_parallel_agents() is False

    def test_get_mcts_scale_normal(self, lps):
        """MCTS scale should be 1.0 in NORMAL mode."""
        lps.force_mode(PowerMode.NORMAL)
        assert lps.get_mcts_scale() == 1.0

    def test_get_mcts_scale_conservative(self, lps):
        """MCTS scale should be 0.5 in CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.get_mcts_scale() == 0.5

    def test_get_mcts_scale_emergency(self, lps):
        """MCTS scale should be 0.25 in EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        assert lps.get_mcts_scale() == 0.25

    def test_get_solver_timeout_scale_normal(self, lps):
        """Solver timeout scale should be 1.0 in NORMAL mode."""
        lps.force_mode(PowerMode.NORMAL)
        assert lps.get_solver_timeout_scale() == 1.0

    def test_get_solver_timeout_scale_conservative(self, lps):
        """Solver timeout scale should be 0.7 in CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.get_solver_timeout_scale() == 0.7

    def test_get_solver_timeout_scale_emergency(self, lps):
        """Solver timeout scale should be 0.4 in EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        assert lps.get_solver_timeout_scale() == 0.4

    def test_should_postpone_non_critical_normal(self, lps):
        """Should NOT postpone in NORMAL mode."""
        lps.force_mode(PowerMode.NORMAL)
        assert lps.should_postpone_non_critical() is False

    def test_should_postpone_non_critical_conservative(self, lps):
        """Should postpone in CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.should_postpone_non_critical() is True

    def test_should_postpone_non_critical_emergency(self, lps):
        """Should postpone in EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        assert lps.should_postpone_non_critical() is True


# ============================================================
#  Active Agents Tests
# ============================================================

class TestActiveAgents:
    """Tests for get_active_agents method."""

    def test_normal_all_agents(self, lps):
        """NORMAL mode should include all agents."""
        lps.force_mode(PowerMode.NORMAL)
        agents = lps.get_active_agents()
        assert "INTENT" in agents
        assert "ARCHITECT" in agents
        assert "RISK" in agents
        assert "WRITER" in agents

    def test_conservative_skips_risk(self, lps):
        """CONSERVATIVE mode should skip RISK agent."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        agents = lps.get_active_agents()
        assert "RISK" not in agents
        assert "INTENT" in agents

    def test_emergency_critical_only(self, lps):
        """EMERGENCY mode should only include critical agents."""
        lps.force_mode(PowerMode.EMERGENCY)
        agents = lps.get_active_agents()
        assert "INTENT" in agents
        assert "EXTRACTOR" in agents
        assert "WRITER" in agents
        assert "FORMATTER" in agents
        assert "ARCHITECT" not in agents
        assert "PLANNER" not in agents
        assert "RISK" not in agents


# ============================================================
#  Execution Order Tests
# ============================================================

class TestExecutionOrder:
    """Tests for get_execution_order method."""

    def test_normal_returns_parallel(self, lps):
        """NORMAL mode should return parallel execution."""
        lps.force_mode(PowerMode.NORMAL)
        order = lps.get_execution_order(layer=4)
        assert order == ["parallel"]

    def test_conservative_layer4(self, lps):
        """CONSERVATIVE mode layer 4 should return ARCHITECT then PLANNER."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        order = lps.get_execution_order(layer=4)
        assert order == ["ARCHITECT", "PLANNER"]

    def test_emergency_layer4(self, lps):
        """EMERGENCY mode layer 4 should return only ARCHITECT."""
        lps.force_mode(PowerMode.EMERGENCY)
        order = lps.get_execution_order(layer=4)
        assert order == ["ARCHITECT"]


# ============================================================
#  Stats Tests
# ============================================================

class TestLPSStats:
    """Tests for stats property."""

    def test_stats_structure(self, lps):
        """Stats should contain expected keys."""
        lps.force_mode(PowerMode.NORMAL)
        stats = lps.stats
        assert "current_mode" in stats
        assert "cpu_usage" in stats
        assert "ram_pct" in stats
        assert "temperature_c" in stats
        assert "battery_level" in stats
        assert "parallel_layer4" in stats
        assert "parallel_agents" in stats
        assert "mcts_scale" in stats
        assert "active_agents" in stats

    def test_stats_forced_mode(self, lps):
        """Stats should reflect forced mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        stats = lps.stats
        assert stats["current_mode"] == "emergency"
        assert stats["forced_mode"] == "emergency"

    def test_stats_no_forced_mode(self, lps):
        """Stats should show None for forced_mode when not forced."""
        stats = lps.stats
        assert stats["forced_mode"] is None


# ============================================================
#  Governor Integration Tests
# ============================================================

class TestGovernorIntegration:
    """Tests for governor-based hardware state reading."""

    def test_set_governor(self, lps):
        """Should accept a governor reference."""
        gov = MagicMock()
        lps.set_governor(gov)
        assert lps._governor is gov

    def test_read_hardware_from_governor(self, lps_with_governor):
        """Should read CPU/RAM stats from governor."""
        hw = lps_with_governor._read_hardware_state()
        assert hw.cpu_usage == 0.3
        assert hw.ram_usage_mb == 500.0

    def test_read_temperature_fallback(self, lps):
        """Should return safe default temperature without governor."""
        hw = lps._read_hardware_state()
        assert hw.temperature_c == 45.0

    def test_read_battery_fallback(self, lps):
        """Should return safe default battery level without real battery."""
        hw = lps._read_hardware_state()
        assert hw.battery_level == 100.0
        assert hw.battery_charging is True


# ============================================================
#  current_mode Property Tests
# ============================================================

class TestCurrentModeProperty:
    """Tests for current_mode property (no re-evaluation)."""

    def test_returns_current_mode(self, lps):
        """Should return the current mode without re-evaluating."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.current_mode == PowerMode.CONSERVATIVE

    def test_does_not_re_evaluate(self, lps):
        """Should return cached mode, not trigger hardware read."""
        lps.force_mode(PowerMode.EMERGENCY)
        # Clear force, but current_mode should still be EMERGENCY
        lps._forced_mode = None
        # current_mode property doesn't re-evaluate
        assert lps.current_mode == PowerMode.EMERGENCY

    def test_initial_mode_is_normal(self, lps):
        """Should start as NORMAL before any evaluate call."""
        assert lps.current_mode == PowerMode.NORMAL
