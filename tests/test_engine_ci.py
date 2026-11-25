"""Prevent later native builds from silently dropping the new engine regressions."""
from pathlib import Path

import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]
MODULES=(
    'test_creator_workflows.py','test_timeline.py','test_timeline_history.py',
    'test_timeline_recovery.py','test_timeline_integrity.py','test_animated_captions.py',
    'test_audio_ducking.py','test_encoder_preflight.py','test_reference_enhancements.py',
    'test_native_render_stability.py','test_performance_release.py','test_automatic_selection.py','test_tightening.py','test_longform_preferences.py','test_speaker_vision_intent.py','test_local_av_models.py','test_multitrack.py','test_graphical_multitrack.py','test_waveform.py','test_diarization.py',
)


@pytest.mark.parametrize('filename',['build-installers.yml','release.yml'])
def test_native_builds_gate_on_new_regressions_including_intel_runtime(filename):
    workflow=yaml.safe_load((ROOT/'.github/workflows'/filename).read_text())
    regular=[];intel=[]
    for job in workflow['jobs'].values():
        for step in job.get('steps',[]):
            command=step.get('run','')
            if '-m pytest' not in command:continue
            if 'CLIPOS_INTEL_PYTHON' in command:intel.append(command)
            else:regular.append(command)
    assert regular and len(intel)==1
    for command in regular+intel:
        for name in MODULES:
            assert 'tests/'+name in command
        assert 'PIPESTATUS[0]' in command
        assert '--junitxml=' in command
        assert 'report_test_failures.py' in command
        assert 'exit "$test_status"' in command
    assert 'platform.machine() == "x86_64"' in intel[0]
