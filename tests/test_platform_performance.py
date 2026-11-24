"""Platform policies are tested without pretending to run on native hardware."""
from unittest.mock import patch
import pytest
from clipos.core.hardware import HardwareProfile, GPUInfo
from clipos.core import hardware


@pytest.mark.parametrize('logical,ram,expected',[(1,4096,1),(4,8192,3),(8,8192,4),(16,16384,8),(32,65536,8)])
def test_automatic_cpu_budget_leaves_ui_headroom(logical,ram,expected):
    assert HardwareProfile(cpu_threads=logical,ram_total_mb=ram).recommended_threads==expected


def test_memory_pressure_is_live_not_cached_profile():
    with patch.object(hardware,'_ram_info',side_effect=[(100,70),(100,10)]):
        assert hardware.memory_pressure()==pytest.approx(.3)
        assert hardware.memory_pressure()==pytest.approx(.9)


def test_automatic_budget_reacts_to_pressure_but_explicit_setting_is_honored():
    profile=HardwareProfile(cpu_threads=16,ram_total_mb=16384)
    with patch.object(hardware,'detect_hardware',return_value=profile),patch.object(hardware,'memory_pressure',return_value=.9):
        assert hardware.suggest_worker_threads()==2
        assert hardware.suggest_worker_threads(6)==6
        assert hardware.suggest_worker_threads(64)==16


def test_intel_mac_is_not_reported_as_apple_silicon():
    with patch.object(hardware.platform,'system',return_value='Darwin'),patch.object(hardware.platform,'machine',return_value='x86_64'):
        gpu=hardware._detect_apple()
        assert gpu.vendor!='apple'
        assert not HardwareProfile(os_name='macOS',arch='x86_64',gpu=gpu).is_apple_silicon


def test_apple_unified_memory_is_not_invented_from_gpu_core_count():
    with patch.object(hardware.platform,'system',return_value='Darwin'),patch.object(hardware.platform,'machine',return_value='arm64'),patch.object(hardware,'_run',return_value='Total Number of Cores: 10'):
        gpu=hardware._detect_apple()
        assert gpu.vendor=='apple' and gpu.vram_mb==0


def test_intel_mac_can_use_available_videotoolbox():
    profile=HardwareProfile(os_name='macOS',arch='x86_64',gpu=GPUInfo(),ffmpeg_encoders={'h264_videotoolbox':True})
    with patch.object(hardware,'detect_hardware',return_value=profile),patch.object(hardware.platform,'system',return_value='Darwin'):
        assert hardware.choose_encoder().hw_accel=='videotoolbox'
        assert hardware.choose_encoder('cpu').hw_accel=='none'
