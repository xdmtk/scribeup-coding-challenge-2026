import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from .settings import env_bool, load_local_environments


class LocalEnvironmentTests(TestCase):
    def test_root_env_loads_and_takes_priority_over_backend(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory) / ".env"
            backend = Path(directory) / "backend" / ".env"
            backend.parent.mkdir()
            root.write_text("OPENAI_MODEL=root-model\n")
            backend.write_text("OPENAI_MODEL=backend-model\nBACKEND_ONLY=yes\n")
            loaded = load_local_environments((root, backend))
            self.assertEqual(loaded, str(root))
            self.assertEqual(os.environ["OPENAI_MODEL"], "root-model")
            self.assertEqual(os.environ["BACKEND_ONLY"], "yes")

    def test_backend_env_loads_when_root_is_missing(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory) / ".env"
            backend = Path(directory) / "backend" / ".env"
            backend.parent.mkdir()
            backend.write_text("OPENAI_MODEL=backend-model\n")
            self.assertEqual(load_local_environments((root, backend)), str(backend))
            self.assertEqual(os.environ["OPENAI_MODEL"], "backend-model")

    def test_shell_environment_wins_and_boolean_parsing_is_safe(self):
        with TemporaryDirectory() as directory, patch.dict(
                os.environ, {"OPENAI_MODEL": "shell-model"}, clear=True):
            path = Path(directory) / ".env"
            path.write_text("OPENAI_MODEL=file-model\nOPENAI_SUBSCRIPTION_REVIEW_ENABLED=true\n")
            load_local_environments((path,))
            self.assertEqual(os.environ["OPENAI_MODEL"], "shell-model")
            self.assertTrue(env_bool("OPENAI_SUBSCRIPTION_REVIEW_ENABLED"))
            self.assertFalse(env_bool("MISSING_REVIEW_SETTING"))
