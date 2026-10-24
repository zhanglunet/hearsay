import os
import sys
import unittest
from importlib.util import spec_from_loader
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m1_shadow.asr import (
    AsrDisabled,
    asr_disabled_reason,
    asr_enabled,
    faster_whisper_installed,
    transcribe_file,
)

INSTALLED = spec_from_loader("faster_whisper", loader=None)


class AsrGateTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("HEARSAY_ASR", None)

    def test_default_does_not_import_or_read_a_file(self):
        os.environ.pop("HEARSAY_ASR", None)
        with mock.patch("m1_shadow.asr.find_spec", return_value=None):
            self.assertFalse(asr_enabled())
            sys.modules.pop("faster_whisper", None)
            with self.assertRaises(AsrDisabled):
                transcribe_file(Path("/tmp/hearsay-missing-on-purpose.wav"))
        self.assertNotIn("faster_whisper", sys.modules)
        self.assertFalse(Path("/tmp/hearsay-missing-on-purpose.wav").exists())

    def test_other_truthy_values_stay_off(self):
        os.environ["HEARSAY_ASR"] = "1"
        with mock.patch("m1_shadow.asr.find_spec", return_value=INSTALLED):
            self.assertFalse(asr_enabled())

    def test_installed_package_enables_asr_without_env(self):
        os.environ.pop("HEARSAY_ASR", None)
        with mock.patch("m1_shadow.asr.find_spec", return_value=INSTALLED):
            self.assertTrue(asr_enabled())
            self.assertIsNone(asr_disabled_reason())

    def test_missing_package_reason_mentions_install_and_paste(self):
        os.environ.pop("HEARSAY_ASR", None)
        with mock.patch("m1_shadow.asr.find_spec", return_value=None):
            reason = asr_disabled_reason()
        self.assertIn("pip install faster-whisper", reason)
        self.assertIn("粘贴", reason)

    def test_forced_off_reason_does_not_echo_env_value(self):
        os.environ["HEARSAY_ASR"] = "some-secret-value"
        reason = asr_disabled_reason()
        self.assertIn("强制关闭", reason)
        self.assertNotIn("some-secret-value", reason)

    def test_installed_check_tolerates_broken_module(self):
        with mock.patch("m1_shadow.asr.find_spec", side_effect=ValueError):
            self.assertFalse(faster_whisper_installed())


if __name__ == "__main__":
    unittest.main()
