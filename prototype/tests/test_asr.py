import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m1_shadow.asr import AsrDisabled, asr_enabled, transcribe_file


class AsrGateTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("HEARSAY_ASR", None)

    def test_default_does_not_import_or_read_a_file(self):
        os.environ.pop("HEARSAY_ASR", None)
        self.assertFalse(asr_enabled())
        sys.modules.pop("faster_whisper", None)
        with self.assertRaises(AsrDisabled):
            transcribe_file(Path("/tmp/hearsay-missing-on-purpose.wav"))
        self.assertNotIn("faster_whisper", sys.modules)
        self.assertFalse(Path("/tmp/hearsay-missing-on-purpose.wav").exists())

    def test_other_truthy_values_stay_off(self):
        os.environ["HEARSAY_ASR"] = "1"
        self.assertFalse(asr_enabled())


if __name__ == "__main__":
    unittest.main()
