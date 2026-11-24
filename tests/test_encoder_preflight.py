"""Runtime preflight policy tests; mocks are not native GPU acceptance."""
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from clipos.core import hardware
from clipos.core.hardware import GPUInfo, HardwareProfile


@pytest.fixture(autouse=True)
def clear_probe_cache():
    hardware._probe_encoder.cache_clear()
    yield
    hardware._probe_encoder.cache_clear()


@pytest.mark.parametrize('name', ['h264_nvenc', 'hevc_nvenc', 'h264_qsv', 'hevc_qsv',
                                  'h264_videotoolbox', 'hevc_videotoolbox'])
def test_preflight_is_bounded_local_and_cached(name):
    with patch.object(hardware.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
        assert hardware._probe_encoder('/bundled/ffmpeg', (1, 2), name, 5)
        assert hardware._probe_encoder('/bundled/ffmpeg', (1, 2), name, 5)
        assert run.call_count == 1
        args = run.call_args.args[0]
        assert args[0] == '/bundled/ffmpeg'
        assert args[args.index('-c:v')+1] == name
        assert args[args.index('-frames:v')+1] == '3'
        assert args[-3:] == ['-f', 'null', '-']
        assert '-nostdin' in args
        assert run.call_args.kwargs['timeout'] == 8
        assert run.call_args.kwargs['stdin'] == subprocess.DEVNULL
        if 'videotoolbox' in name:
            assert args[args.index('-allow_sw')+1] == '0'


@pytest.mark.parametrize('failure', [OSError('missing'), subprocess.TimeoutExpired('ffmpeg', 8)])
def test_preflight_exceptions_fail_closed(failure):
    with patch.object(hardware.subprocess, 'run', side_effect=failure):
        assert not hardware._probe_encoder('/ffmpeg', (), 'h264_nvenc', 0)


def test_failures_expire_and_binary_replacement_invalidates_cache():
    with patch.object(hardware.subprocess, 'run', side_effect=[SimpleNamespace(returncode=1),
            SimpleNamespace(returncode=0), SimpleNamespace(returncode=0)]) as run:
        assert not hardware._probe_encoder('/ffmpeg', (1, 2), 'h264_nvenc', 1)
        assert not hardware._probe_encoder('/ffmpeg', (1, 2), 'h264_nvenc', 1)
        assert hardware._probe_encoder('/ffmpeg', (1, 2), 'h264_nvenc', 2)
        assert hardware._probe_encoder('/ffmpeg', (2, 3), 'h264_nvenc', 2)
        assert run.call_count == 3


def test_unknown_encoders_never_spawn():
    with patch.object(hardware.subprocess, 'run') as run:
        assert not hardware._probe_encoder('/ffmpeg', (), 'unexpected', 0)
        run.assert_not_called()


def test_resolved_binary_and_time_are_part_of_key(tmp_path):
    binary = tmp_path/'ffmpeg'
    binary.write_text('placeholder')
    with patch.object(hardware, 'require_ffmpeg', return_value=str(binary)), \
         patch.object(hardware.time, 'monotonic', return_value=125), \
         patch.object(hardware, '_probe_encoder', return_value=True) as probe:
        assert hardware.encoder_works('h264_nvenc')
        assert probe.call_args.args == (str(binary), (binary.stat().st_mtime_ns, binary.stat().st_size), 'h264_nvenc', 2)
    with patch.object(hardware, 'require_ffmpeg', return_value=str(tmp_path/'missing')):
        assert not hardware.encoder_works('h264_nvenc')


@pytest.mark.parametrize('pref,name,codec,platform', [
    ('nvidia','h264_nvenc','h264','Windows'),
    ('nvidia','hevc_nvenc','hevc','Windows'),
    ('intel','h264_qsv','h264','Windows'),
    ('apple','hevc_videotoolbox','hevc','Darwin'),
])
def test_advertised_hardware_failure_selects_cpu(pref,name,codec,platform):
    profile=HardwareProfile(gpu=GPUInfo(cuda_available=True,qsv_available=True),ffmpeg_encoders={name:True})
    with patch.object(hardware,'detect_hardware',return_value=profile), \
         patch.object(hardware.platform,'system',return_value=platform), \
         patch.object(hardware,'encoder_works',return_value=False) as probe:
        choice=hardware.choose_encoder(pref,codec)
        assert not choice.is_hardware
        assert choice.video_encoder==('libx265' if codec=='hevc' else 'libx264')
        probe.assert_called_once_with(name)


def test_auto_tries_next_accelerator_and_cpu_never_probes():
    profile=HardwareProfile(gpu=GPUInfo(cuda_available=True,qsv_available=True),
        ffmpeg_encoders={'h264_nvenc':True,'h264_qsv':True})
    with patch.object(hardware,'detect_hardware',return_value=profile), \
         patch.object(hardware.platform,'system',return_value='Windows'), \
         patch.object(hardware,'encoder_works',side_effect=[False,True]) as probe:
        assert hardware.choose_encoder().hw_accel=='qsv'
        assert hardware.choose_encoder('cpu').hw_accel=='none'
        assert probe.call_count==2


def test_nonblocking_diagnostics_do_not_claim_runtime_validation():
    profile=HardwareProfile(gpu=GPUInfo(cuda_available=True),ffmpeg_encoders={'h264_nvenc':True})
    with patch.object(hardware,'detect_hardware',return_value=profile), \
         patch.object(hardware,'encoder_works') as probe:
        assert hardware.choose_encoder(verify=False).video_encoder=='h264_nvenc'
        probe.assert_not_called()
