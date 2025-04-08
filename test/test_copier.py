import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from copier import run


class TestCopier(TestCase):
    @patch('builtins.print')
    def test_empty_target_dir(self, _mock_print):
        with tempfile.TemporaryDirectory() as temp_destination_dir:
            p = Path(temp_destination_dir)
            expected_files = [p / 'main.py', p / 'settings.toml']
            self.assertTrue(all([not x.exists() for x in expected_files]))
            run(p)
            self.assertTrue(all([x.exists() for x in expected_files]))

    @patch('builtins.print')
    def test_version_already_exists(self, _mock_print):
        with tempfile.TemporaryDirectory() as temp_destination_dir:
            p = Path(temp_destination_dir)
            expected_files = [p / 'main.py', p / 'settings.toml']
            expected_files[0].write_text("HELLO")
            expected_files[1].write_text("WORLD")
            self.assertTrue(all([x.exists() for x in expected_files]))
            run(p)
            self.assertTrue(all([x.exists() for x in expected_files]))
