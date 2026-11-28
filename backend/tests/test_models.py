from types import SimpleNamespace

from app import config
from app.services.models import CATALOG, recommended_models


def test_every_model_has_an_action_link():
    for model in CATALOG:
        assert model.get("downloadUrl") or model.get("apiUrl"), model["id"]


def test_cloud_models_have_direct_api_links():
    cloud = [model for model in CATALOG if model.get("needsApi")]
    assert len(cloud) >= 3
    for model in cloud:
        assert model["apiUrl"].startswith("https://")


def test_local_models_can_be_downloaded_in_one_click():
    local = [model for model in CATALOG if not model.get("needsApi")]
    assert len(local) >= 8
    for model in local:
        assert model["autoInstall"] or model["provider"] == "comfyui"


def test_nvidia_smi_vram_is_normalized_to_gigabytes(monkeypatch):
    monkeypatch.setattr(config.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stdout="NVIDIA Smaller, 8192 MiB\nNVIDIA Larger, 16384 MiB\n",
    ))
    gpu = config._gpu_info()
    assert gpu["cuda"] is True
    assert gpu["name"] == "NVIDIA Larger"
    assert gpu["vram_total_gb"] == 16.0


def test_hardware_profile_scales_asr_and_llm_without_large_optional_downloads():
    low_memory = recommended_models({"ram_total_gb": 8, "gpu": {"cuda": False, "metal": False}})
    assert "whisper-small" in low_memory
    assert "gemma3:4b" in low_memory
    assert "yolox-nano" in low_memory
    assert "sdxl-1.0" not in low_memory

    balanced_gpu = recommended_models({
        "ram_total_gb": 16,
        "gpu": {"cuda": True, "metal": False, "vram_total_gb": 8},
    })
    assert "whisper-medium" in balanced_gpu
    assert "gemma2:7b" in balanced_gpu

    high_memory = recommended_models({
        "ram_total_gb": 32,
        "gpu": {"cuda": True, "metal": False, "vram_total_gb": 16},
    })
    assert "gemma3:12b" in high_memory
    assert "whisper-medium" in high_memory
