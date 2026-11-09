"""Execute workflow shell blocks with a closed PATH and inert native-tool stubs."""

import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/release.yml").read_text()
PRODUCT = "Get Folder Size"
SPEC = importlib.util.spec_from_file_location(
    "native_source_version", ROOT / ".github/scripts/source_version.py"
)
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)
PWSH = shutil.which("pwsh") or (
    "/usr/local/bin/pwsh" if Path("/usr/local/bin/pwsh").exists() else None
)


def step(name):
    matches = re.findall(
        rf"^      - name: {re.escape(name)}\n"
        r"(?:(?!      - ).*\n)*?        run: \|\n"
        r"((?:          .*(?:\n|$)|[ \t]*\n)+)", WORKFLOW, re.MULTILINE,
    )
    if len(matches) != 1:
        raise AssertionError(f"Expected one shell block for {name!r}")
    return textwrap.dedent(matches[0])


STUB = r'''
import json
import os
from pathlib import Path
import plistlib
import re
import runpy
import sys

tool, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps([tool, *args]) + "\n")
product = "Get Folder Size"
bundle = Path(os.environ["BUNDLE_PATH"])
contents = bundle / "Contents"
mode = os.environ.get("BUILD_MODE", "complete")
if tool == "xcodebuild":
    for path in (contents / "MacOS" / product, contents / "Info.plist",
                 contents / "Resources/English.lproj/InfoPlist.strings",
                 contents / "_CodeSignature", bundle.parent / "Default",
                 bundle.parent / (product + ".build")):
        assert not path.exists(), "stale output survived: " + str(path)
    if mode != "missing-binary":
        (contents / "MacOS").mkdir(parents=True, exist_ok=True)
        (contents / "MacOS" / product).write_bytes(
            b"" if mode == "empty-binary" else b"fresh universal binary"
        )
    if mode != "missing-plist":
        data = plistlib.loads(Path("Info.plist").read_bytes())
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            if key in data:
                data[key] = re.sub(r"\$\([^)]+\)|\$\{[^}]+\}",
                                   os.environ["SOURCE_VERSION"], data[key])
        if mode == "stale-plist":
            data["CFBundleShortVersionString"] = os.environ["STALE_VERSION"]
        if mode == "stale-build":
            data["CFBundleVersion"] = os.environ["STALE_VERSION"]
        (contents / "Info.plist").write_bytes(plistlib.dumps(data))
    if mode != "missing-localized":
        data = Path("English.lproj/InfoPlist.strings").read_bytes()
        if mode == "stale-localized":
            data = data.replace(os.environ["SOURCE_VERSION"].encode(),
                                os.environ["STALE_VERSION"].encode())
        target = contents / "Resources/English.lproj/InfoPlist.strings"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
elif tool == "lipo":
    assert args in (["-info", str(contents / "MacOS" / product)],
                    ["-archs", str(contents / "MacOS" / product)])
    print(os.environ.get("ARCHS", "arm64 x86_64"))
elif tool == "python3":
    if args[0] == ".github/scripts/source_version.py":
        assert args in ([".github/scripts/source_version.py"],
                        [".github/scripts/source_version.py", "--verify-bundle", str(bundle)])
        os.execv(os.environ["REAL_PYTHON"], [os.environ["REAL_PYTHON"], *args])
    else:
        assert args[0] == ".github/scripts/release.py"
        assert args[1] in ("preflight", "publish")
        expected = [".github/scripts/release.py", args[1], "--sha", os.environ["SELECTED_SHA"]]
        if args[1] == "publish":
            expected += [os.environ["ZIP_PATH"], os.environ["DMG_PATH"]]
        assert args == expected
        version = runpy.run_path(".github/scripts/source_version.py")["read"]()
        assert version == os.environ["SOURCE_VERSION"]
        if os.environ.get("RELEASE_MODE") == "fail":
            sys.exit(77)
        if args[1] == "preflight":
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.write("version=" + version + "\ntag=v" + version + "\n")
elif tool == "security":
    assert args == ["find-identity", "-v", "-p", "codesigning", os.environ["KEYCHAIN_PATH"]]
    if os.environ.get("SIGN_MODE") != "missing-identity":
        print('1) FAKE "Developer ID Application: Fixture (TEST)"')
elif tool == "codesign":
    verify = args[0] == "--verify"
    expected = (["--verify", "--deep", "--strict", "--verbose=2", str(bundle)] if verify
                else ["--verbose", "--deep", "--timestamp", "--force", "--options=runtime",
                      "--sign", "Developer ID Application: Fixture (TEST)", str(bundle)])
    assert args == expected
    if os.environ.get("SIGN_MODE") == ("verify" if verify else "sign"):
        sys.exit(76)
elif tool in ("ditto", "hdiutil"):
    assert bundle.is_dir()
    expected = (["-c", "-k", "--keepParent", str(bundle)] if tool == "ditto"
                else ["create", "-format", "UDBZ", "-volname", product,
                      "-srcfolder", str(bundle)])
    assert args[:-1] == expected
    Path(args[-1]).write_bytes(b"inert archive")
elif tool == "xcrun":
    scenario = os.environ.get("NOTARY_MODE", "accepted")
    if args[:2] == ["notarytool", "submit"]:
        assert args[3:] == ["--keychain-profile", "notarytool-profile", "--keychain",
                            os.environ["KEYCHAIN_PATH"], "--wait", "--output-format", "json"]
        assert Path(args[2]).is_file()
        second = args[2].endswith(".dmg")
        if scenario == "transport" or (scenario == "second-transport" and second):
            sys.exit(71)
        if scenario == "malformed":
            print("not JSON")
        elif scenario == "missing-status":
            print('{"id":"fixture"}')
        else:
            status = "Invalid" if (
                scenario == "invalid" or (scenario == "second-invalid" and second)
            ) else "Accepted"
            print(json.dumps({"id": "dmg" if second else "zip", "status": status}))
    elif args[:2] == ["notarytool", "log"]:
        assert args[3:] == ["--keychain-profile", "notarytool-profile",
                            "--keychain", os.environ["KEYCHAIN_PATH"]]
        sys.exit(72)
    elif args[:2] == ["stapler", "staple"]:
        assert args == ["stapler", "staple", product + "-" + os.environ["SOURCE_VERSION"] + ".dmg"]
        if scenario == "staple":
            sys.exit(73)
    else:
        raise AssertionError(args)
elif tool == "plutil":
    assert args[0] == "-extract" and args[2:] == ["raw", "-o", "-", "-"]
    try:
        value = json.load(sys.stdin)[args[1]]
        assert isinstance(value, str)
        print(value)
    except (ValueError, KeyError, AssertionError):
        sys.exit(74)
else:
    raise AssertionError("Unexpected native tool: " + tool)
'''


class NativeShellTests(unittest.TestCase):
    bumped = False

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".native-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in (*source.SOURCE_PATHS, Path(".github/scripts/source_version.py")):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)
        if self.bumped:
            source.bump("patch", self.root)
        self.version = source.read(self.root)
        parts = list(map(int, self.version.split(".")))
        self.stale = f"{parts[0]}.{parts[1]}.{parts[2] + 1}"
        self.relative = f"test/Plugins/{PRODUCT}.bundle"
        self.bundle = self.root / self.relative
        self.contents = self.bundle / "Contents"
        self.log = self.root / "calls.jsonl"
        self.env_file = self.root / "github-env"
        self.env_file.touch()
        self.output_file = self.root / "github-output"
        self.output_file.touch()
        self.bin = self.root / "stub-bin"
        self.bin.mkdir()
        for name in ("xcodebuild", "lipo", "python3", "security", "codesign",
                     "ditto", "hdiutil", "xcrun", "plutil"):
            executable = self.bin / name
            executable.write_text(f"#!{sys.executable}\n" + textwrap.dedent(STUB))
            executable.chmod(0o755)
        for name in ("rm", "ls", "grep", "head", "sed", "mkdir", "cp"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable)
            (self.bin / name).symlink_to(executable)
        self.env = {
            "PATH": str(self.bin), "CALL_LOG": str(self.log), "REAL_PYTHON": sys.executable,
            "PYTHONDONTWRITEBYTECODE": "1", "SOURCE_VERSION": self.version,
            "STALE_VERSION": self.stale, "BUNDLE_PATH": self.relative,
            "KEYCHAIN_PATH": str(self.root / "fake.keychain-db"),
            "GITHUB_ENV": str(self.env_file), "GITHUB_OUTPUT": str(self.output_file),
            "SELECTED_SHA": "a" * 40, "TAG": "v" + self.version,
            "ZIP_PATH": f"{PRODUCT}-{self.version}.zip",
            "DMG_PATH": f"{PRODUCT}-{self.version}.dmg",
        }
        self.preserved = {}
        for path in (ROOT / self.relative / "Contents").rglob("*"):
            if path.is_file():
                relative = str(path.relative_to(ROOT / self.relative / "Contents"))
                if relative.startswith(("MacOS/", "_CodeSignature/")) or relative in (
                    "Info.plist", "Resources/English.lproj/InfoPlist.strings"
                ):
                    continue
                self.preserved[relative] = path.read_bytes()
        self.preserved["Frameworks/Dependency.framework/Versions/A/Dependency"] = b"dependency"
        for relative, data in self.preserved.items():
            self.write(relative, data)
        (self.contents / "Frameworks/Dependency.framework/Versions/Current").symlink_to("A")
        for relative in (f"MacOS/{PRODUCT}", "Info.plist",
                         "Resources/English.lproj/InfoPlist.strings", "_CodeSignature/CodeResources"):
            self.write(relative, b"stale build product")
        for relative in ("Default/stale", f"{PRODUCT}.build/stale"):
            path = self.bundle.parent / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"stale intermediate")

    def write(self, relative, data):
        path = self.contents / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run_step(self, name, **env):
        script = step(name)
        for key, value in {
            "env.PRODUCT_NAME": PRODUCT, "env.BASE_DIR": "test",
            "env.MACOS_DEPLOYMENT_TARGET": "11.0", "needs.version.outputs.version": self.version,
        }.items():
            script = script.replace("${{ " + key + " }}", value)
        self.assertNotIn("${{", script)
        return subprocess.run(
            ["/bin/bash", "-c", script], cwd=self.root, env={**self.env, **env},
            text=True, capture_output=True, timeout=30,
        )

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def calls(self, tool):
        return [call[1:] for line in self.log.read_text().splitlines()
                if (call := json.loads(line))[0] == tool] if self.log.exists() else []

    def build(self, **env):
        self.assert_ok(self.run_step("build macOS plugin (universal)", **env))

    def test_fresh_universal_build_preserves_resources(self):
        self.build()
        self.assertEqual((self.contents / f"MacOS/{PRODUCT}").read_bytes(), b"fresh universal binary")
        for relative, data in self.preserved.items():
            self.assertEqual((self.contents / relative).read_bytes(), data, relative)
        self.assertEqual(
            (self.contents / "Frameworks/Dependency.framework/Versions/Current").readlink(), Path("A")
        )
        self.assert_ok(self.run_step("verify universal binary"))
        self.assertEqual(self.calls("xcodebuild"), [[
            "-project", f"{PRODUCT}.xcodeproj", "-target", PRODUCT, "-configuration", "Default",
            "ARCHS=arm64 x86_64", "ONLY_ACTIVE_ARCH=NO", "MACOSX_DEPLOYMENT_TARGET=11.0",
            "CODE_SIGNING_ALLOWED=NO", f"CONFIGURATION_BUILD_DIR={self.root}/test/Plugins", "build",
        ]])

    def test_strict_source_outputs_and_early_availability_check(self):
        self.assert_ok(self.run_step("validate source and publication availability"))
        self.assertEqual(self.output_file.read_text().splitlines(),
                         [f"version={self.version}", f"tag=v{self.version}"])
        self.assertEqual(self.calls("python3"), [
            [".github/scripts/release.py", "preflight", "--sha", "a" * 40],
        ])
        self.output_file.write_text("")
        self.assertNotEqual(self.run_step("validate source and publication availability",
                                         RELEASE_MODE="fail").returncode, 0)
        self.assertEqual(self.output_file.read_text(), "")
        self.log.unlink()
        (self.root / source.PLIST).write_bytes(b"invalid source plist")
        self.assertNotEqual(self.run_step("validate source and publication availability").returncode, 0)
        self.assertEqual(self.calls("python3"), [
            [".github/scripts/release.py", "preflight", "--sha", "a" * 40],
        ])
        self.assertEqual(self.output_file.read_text(), "")

    def test_final_publication_passes_selected_sha_tag_and_exact_assets(self):
        self.assert_ok(self.run_step("create GitHub Release"))
        self.assertEqual(self.calls("python3"), [[
            ".github/scripts/release.py", "publish", "--sha", "a" * 40,
            f"{PRODUCT}-{self.version}.zip", f"{PRODUCT}-{self.version}.dmg",
        ]])
        self.assertNotEqual(self.run_step("create GitHub Release", RELEASE_MODE="fail").returncode, 0)

    def test_missing_empty_and_stale_products_fail_verification(self):
        for mode in ("missing-binary", "empty-binary", "missing-plist", "missing-localized",
                     "stale-plist", "stale-build", "stale-localized"):
            with self.subTest(mode=mode):
                self.build(BUILD_MODE=mode)
                result = self.run_step("verify universal binary")
                self.assertNotEqual(result.returncode, 0)
                if mode.startswith("stale-"):
                    self.assertIn("differs from selected source", result.stderr)
                elif mode in ("missing-plist", "missing-localized"):
                    self.assertIn("FileNotFoundError", result.stderr)
                else:
                    self.assertIn("Expected binary not found", result.stdout)

    def test_exact_architecture_set(self):
        self.build()
        for arches in ("arm64", "x86_64", "arm64e x86_64", "arm64 x86_64h",
                       "arm64 x86_64 i386", "arm64 arm64 x86_64", ""):
            with self.subTest(arches=arches):
                self.assertNotEqual(self.run_step("verify universal binary", ARCHS=arches).returncode, 0)
        self.assertEqual(self.calls("python3"), [])
        self.assert_ok(self.run_step("verify universal binary", ARCHS="x86_64 arm64"))

    def test_compiled_localizations_checked_against_selected_source(self):
        self.build()
        values = dict(re.findall(r'(?m)^(\w+)\s*=\s*"([^"]*)";',
                                 source.text(self.root / source.LOCALIZED)))
        for fmt in (plistlib.FMT_XML, plistlib.FMT_BINARY):
            self.write("Resources/English.lproj/InfoPlist.strings", plistlib.dumps(values, fmt=fmt))
            self.assert_ok(self.run_step("verify universal binary"))
            for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
                stale = {**values, key: values[key].replace(self.version, self.stale)}
                self.write("Resources/English.lproj/InfoPlist.strings", plistlib.dumps(stale, fmt=fmt))
                self.assertNotEqual(self.run_step("verify universal binary").returncode, 0)

    def test_utf16_built_localization_matches_selected_source(self):
        self.build()
        localized = source.text(self.root / source.LOCALIZED)
        relative = "Resources/English.lproj/InfoPlist.strings"
        self.write(relative, localized.encode("utf-16"))
        self.assert_ok(self.run_step("verify universal binary"))
        self.write(relative, localized.replace(self.version, self.stale).encode("utf-16"))
        result = self.run_step("verify universal binary")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from selected source", result.stderr)

    def test_windows_merge_requires_exact_nonempty_artifact(self):
        artifact = self.root / f"winbuild/{PRODUCT}.4DX"
        stale = artifact.parent / f"nested/{PRODUCT}.4DX"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"wrong recursive match")
        for data in (None, b""):
            if data is not None:
                artifact.write_bytes(data)
            self.assertNotEqual(self.run_step("merge Windows binaries into the bundle").returncode, 0)
            self.assertEqual(self.env_file.read_text(), "")
        artifact.write_bytes(b"fresh Windows binary")
        self.assert_ok(self.run_step("merge Windows binaries into the bundle"))
        self.assertEqual((self.contents / f"Windows64/{PRODUCT}.4DX").read_bytes(), artifact.read_bytes())

    def test_signing_identity_sign_and_strict_verification_are_gates(self):
        self.assert_ok(self.run_step("codesign"))
        self.assertEqual(len(self.calls("codesign")), 2)
        for mode, count in (("missing-identity", 0), ("sign", 1), ("verify", 2)):
            self.log.unlink(missing_ok=True)
            self.assertNotEqual(self.run_step("codesign", SIGN_MODE=mode).returncode, 0)
            self.assertEqual(len(self.calls("codesign")), count)

    def test_both_accepted_then_staple_exports_only_versioned_assets(self):
        self.assert_ok(self.run_step("package, notarize & staple"))
        calls = self.calls("xcrun")
        self.assertEqual([call[:2] for call in calls], [
            ["notarytool", "submit"], ["notarytool", "submit"], ["stapler", "staple"],
        ])
        self.assertEqual(self.env_file.read_text().splitlines(), [
            f"ZIP_PATH={PRODUCT}-{self.version}.zip", f"DMG_PATH={PRODUCT}-{self.version}.dmg",
        ])

    def test_every_notarization_failure_blocks_publication_paths(self):
        for mode, submissions, staples in (
            ("invalid", 1, 0), ("transport", 1, 0), ("malformed", 1, 0),
            ("missing-status", 1, 0), ("second-invalid", 2, 0),
            ("second-transport", 2, 0), ("staple", 2, 1),
        ):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                self.assertNotEqual(self.run_step("package, notarize & staple",
                                                 NOTARY_MODE=mode).returncode, 0)
                calls = self.calls("xcrun")
                self.assertEqual(sum(call[:2] == ["notarytool", "submit"] for call in calls), submissions)
                self.assertEqual(sum(call[:2] == ["stapler", "staple"] for call in calls), staples)
                self.assertEqual(self.env_file.read_text(), "")


class BumpedNativeShellTests(NativeShellTests):
    bumped = True


class NativeConfigurationTests(unittest.TestCase):
    def test_exact_windows_output_matches_actual_project(self):
        project = ET.parse(ROOT / f"{PRODUCT}.vcxproj")
        ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
        condition = "'$(Configuration)|$(Platform)'=='Release|x64'"
        outdirs = [node.text for node in project.findall(".//m:OutDir", ns)
                   if node.get("Condition") == condition]
        self.assertEqual(len(outdirs), 1)
        output = (outdirs[0].replace("$(ProjectDir)", "").replace("$(ProjectName)", PRODUCT)
                  .replace("\\", "/") + PRODUCT + ".4DX")
        normalize = step("normalize windows output to canonical case")
        expected = re.search(r'^\$source = "([^"]+)"$', normalize, re.MULTILINE)[1]
        self.assertEqual(output, expected.replace("$base", "test").replace("$product", PRODUCT))
        self.assertNotIn("-Recurse", normalize)
        self.assertIn("$sourceResolved -ieq $destResolved", normalize)
        self.assertEqual({n.text for n in project.findall(".//m:PlatformToolset", ns)}, {"v143"})
        self.assertIn("/p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "
                      "/p:WindowsTargetPlatformVersion=10.0 /m", step("build x64"))

    def test_source_pinning_dispatch_and_publication_order(self):
        self.assertRegex(WORKFLOW, r"(?m)^name: Build$")
        self.assertRegex(WORKFLOW, r"on:\n  workflow_dispatch:\n\npermissions:")
        self.assertEqual(re.findall(r"ref: (.+)", WORKFLOW), ["${{ github.sha }}"] * 3)
        self.assertIn("group: release-publication\n  cancel-in-progress: false", WORKFLOW)
        self.assertIn('release.py preflight --sha "$SELECTED_SHA"', WORKFLOW)
        self.assertIn('release.py publish --sha "$SELECTED_SHA" '
                      '"$ZIP_PATH" "$DMG_PATH"', WORKFLOW)
        for earlier, later in (
            ("validate source and publication availability", "build x64"),
            ("build macOS plugin (universal)", "verify universal binary"),
            ("verify universal binary", "merge Windows binaries into the bundle"),
            ("merge Windows binaries into the bundle", "codesign"),
            ("codesign", "package, notarize & staple"),
            ("package, notarize & staple", "create GitHub Release"),
        ):
            self.assertLess(WORKFLOW.index("- name: " + earlier), WORKFLOW.index("- name: " + later))
        self.assertNotIn("continue-on-error", WORKFLOW)
        self.assertNotIn("always()", WORKFLOW)

    def test_original_resources_secrets_artifacts_and_xcode_target(self):
        project = (ROOT / source.PROJECT).read_text()
        for item in ("English.lproj/InfoPlist.strings", "manifest.json in CopyFiles",
                     "constants.xlf in CopyFiles", "Cocoa.framework in Frameworks"):
            self.assertIn(item, project)
        self.assertEqual(set(re.findall(r"\$\{\{ secrets\.([A-Z_]+) \}\}", WORKFLOW)), {
            "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
            "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID", "NOTARYTOOL_PASSWORD",
        })
        self.assertEqual(WORKFLOW.count("name: windows-binaries"), 2)
        self.assertIn("if-no-files-found: error", WORKFLOW)
        self.assertIn("needs: [version, build-windows]", WORKFLOW)
        self.assertIn("-configuration Default", step("build macOS plugin (universal)"))


@unittest.skipUnless(PWSH, "PowerShell required for Windows shell harness")
class WindowsShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".windows-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / f"test/plugins/{PRODUCT}.bundle/contents/windows64/{PRODUCT}.4DX"
        self.binary.parent.mkdir(parents=True)
        self.bin = self.root / "closed-path"
        self.bin.mkdir()

    def run_step(self, name):
        script = step(name).replace("${{ env.PRODUCT_NAME }}", PRODUCT).replace("${{ env.BASE_DIR }}", "test")
        self.assertNotIn("${{", script)
        return subprocess.run(
            [PWSH, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            cwd=self.root, env={**os.environ, "PATH": str(self.bin)}, text=True,
            capture_output=True, timeout=30,
        )

    def test_cleanup_preserves_resources_and_invalidates_only_products(self):
        self.binary.write_bytes(b"stale")
        resource = self.binary.parent.parent / "QuickLook/Thumbnail.png"
        resource.parent.mkdir()
        resource.write_bytes(b"preserved")
        for relative in ("test/Plugins/Default/stale", "Objs/stale"):
            path = self.root / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(b"stale")
        for _ in range(2):
            result = self.run_step("clean stale outputs")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.binary.exists())
        self.assertFalse((self.root / "Objs").exists())
        self.assertFalse((self.root / "test/Plugins/Default").exists())
        self.assertEqual(resource.read_bytes(), b"preserved")

    def test_exact_output_required_then_normalized(self):
        stale = self.root / f"stale/Plugins/{PRODUCT}.4DX"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"wrong recursive match")
        for data in (None, b""):
            if data is not None:
                self.binary.write_bytes(data)
            self.assertNotEqual(self.run_step("normalize windows output to canonical case").returncode, 0)
        self.binary.write_bytes(b"fresh")
        for _ in range(2):
            result = self.run_step("normalize windows output to canonical case")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        canonical = self.root / f"test/Plugins/{PRODUCT}.bundle/Contents/Windows64/{PRODUCT}.4DX"
        self.assertEqual(canonical.read_bytes(), b"fresh")


if __name__ == "__main__":
    unittest.main()
