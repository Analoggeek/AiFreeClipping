from app.services.models import CATALOG


def test_every_model_has_an_action_link():
    for model in CATALOG:
        assert model.get("downloadUrl") or model.get("apiUrl"), model["id"]


def test_cloud_models_have_direct_api_links():
    cloud = [model for model in CATALOG if model.get("needsApi")]
    assert len(cloud) >= 4
    for model in cloud:
        assert model["apiUrl"].startswith("https://")


def test_local_models_can_be_downloaded_in_one_click():
    local = [model for model in CATALOG if not model.get("needsApi")]
    assert len(local) >= 8
    for model in local:
        assert model["autoInstall"] or model["provider"] == "comfyui"
