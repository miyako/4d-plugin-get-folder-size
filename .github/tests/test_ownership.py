"""Compile actual plugin/helpers and full SDK; replace only the 4D engine."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("clang"),
                     "requires the macOS SDK and clang")
class OwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="folder-size-ownership-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        cls.tree = work / "tree"
        cls.tree.mkdir()
        for i in range(16384):
            (cls.tree / str(i)).write_bytes(b"x")
        sdk = ROOT / "4D Plugin API"
        flags = ["-g", "-O1", "-fsanitize=address,undefined",
                 "-fno-omit-frame-pointer", "-Wno-deprecated-declarations",
                 "-Wno-incompatible-pointer-types", "-I", str(ROOT),
                 "-I", str(sdk), "-I", str(sdk / "Classes")]
        sdk_object = work / "sdk.o"
        result = subprocess.run(["clang", *flags, "-Wno-error=int-conversion",
                                 "-c", str(sdk / "4DPluginAPI.c"),
                                 "-o", str(sdk_object)], text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.binary = work / "ownership"
        result = subprocess.run([
            "clang++", *flags, "-std=c++17", "-x", "objective-c++",
            str(ROOT / ".github/tests/ownership_host.mm"),
            str(ROOT / "4DPlugin-Get-Folder-Size.cpp"),
            str(sdk / "Classes/C_TEXT.cpp"), str(sdk / "Classes/C_REAL.cpp"),
            str(sdk / "Classes/ARRAY_TEXT.cpp"),
            str(ROOT / "support/4DPlugin-JSON.cpp"),
            "-x", "none", str(sdk_object),
            "-framework", "Cocoa", "-framework", "CoreGraphics",
            "-o", str(cls.binary),
        ], text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def run_case(self, case):
        for empty in ("allocated", "null"):
            with self.subTest(empty=empty):
                result = subprocess.run(
                    [str(self.binary), case, empty, str(self.tree)],
                    env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                         "UBSAN_OPTIONS": "halt_on_error=1"},
                    text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_named_callback(self):
        self.run_case("named")

    def test_callback_results(self):
        self.run_case("callbacks")

    def test_json_setters(self):
        self.run_case("setters")

    def test_json_getters(self):
        self.run_case("getters")

    def test_sdk_and_dormant_array_contracts(self):
        self.run_case("contracts")


if __name__ == "__main__":
    unittest.main()
