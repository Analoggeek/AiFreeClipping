"""Keep tests from rotating the live desktop app's API token file."""
import os

os.environ.setdefault("AIFREECLIP_TOKEN", "aifreeclip-test-token")
