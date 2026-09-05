"""Black-box installer regressions. Every mutation stays in a temporary HOME."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import install

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="code-max test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "renamed checkout"
        self.source.mkdir()
        shutil.copytree(ROOT / "scripts", self.source / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(ROOT / "skills.sh", self.source / "skills.sh")
        shutil.copy2(ROOT / "SKILL.md", self.source / "SKILL.md")
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = {**os.environ, "HOME": str(self.home), "XDG_CONFIG_HOME": ""}
        self.env.pop("PYTHONDONTWRITEBYTECODE", None)
        self.target = self.home / "custom skills"
        self.dest = self.target / "code-max"

    def run_cli(self, *args, script=None):
        return subprocess.run(["bash", str(script or self.source / "skills.sh"), *args],
                              env=self.env, capture_output=True, text=True, timeout=10)

    def test_no_arguments_no_writes(self):
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_install_is_named_from_metadata_and_idempotent(self):
        first = self.run_cli("--target", str(self.target))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.dest.resolve(), self.source)
        inode = self.dest.lstat().st_ino
        self.assertIn("unchanged:", self.run_cli("--target", str(self.target)).stdout)
        self.assertEqual(self.dest.lstat().st_ino, inode)

    def test_dry_run_creates_nothing(self):
        before = set(self.source.rglob("*"))
        result = self.run_cli("--all", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(set(self.source.rglob("*")), before)

    def test_conflicts_preserved_before_any_install(self):
        for kind in ("file", "directory", "foreign", "dangling"):
            with self.subTest(kind=kind):
                target = self.home / kind
                target.mkdir()
                dest = target / "code-max"
                if kind == "file":
                    dest.write_text("user data")
                elif kind == "directory":
                    dest.mkdir()
                else:
                    dest.symlink_to(self.home if kind == "foreign" else self.home / "missing")
                before = dest.lstat()
                result = self.run_cli("--target", str(self.target), "--target", str(target))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("conflict:", result.stderr)
                self.assertFalse(self.target.exists())
                # Reading a symlink may update atime; ownership/content must not change.
                after = dest.lstat()
                for field in ("st_ino", "st_dev", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"):
                    self.assertEqual(getattr(after, field), getattr(before, field))
                if kind == "file":
                    self.assertEqual(dest.read_text(), "user data")
                if kind == "directory":
                    self.assertEqual(list(dest.iterdir()), [])

    def test_uninstall_removes_only_owned_link(self):
        self.assertEqual(self.run_cli("--target", str(self.target)).returncode, 0)
        self.assertEqual(self.run_cli("--target", str(self.target), "--uninstall", "--dry-run").returncode, 0)
        self.assertTrue(self.dest.is_symlink())
        self.assertEqual(self.run_cli("--target", str(self.target), "--uninstall").returncode, 0)
        self.assertFalse(self.dest.exists())
        self.assertTrue((self.source / "SKILL.md").is_file())
        self.assertIn("absent:", self.run_cli("--target", str(self.target), "--uninstall").stdout)
        self.dest.symlink_to(self.home)
        self.assertNotEqual(self.run_cli("--target", str(self.target), "--uninstall").returncode, 0)
        self.assertEqual(self.dest.resolve(), self.home)

    def test_relative_owned_link_is_idempotent(self):
        self.target.mkdir()
        self.dest.symlink_to(os.path.relpath(self.source, self.target))
        self.assertIn("unchanged:", self.run_cli("--target", str(self.target)).stdout)

    def test_symlinked_launcher(self):
        launcher = self.root / "launcher"
        launcher.symlink_to(self.source / "skills.sh")
        result = self.run_cli("--target", str(self.target), script=launcher)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.dest.resolve(), self.source)

    def test_presets_and_xdg(self):
        self.env["XDG_CONFIG_HOME"] = str(self.home / "xdg")
        result = self.run_cli("--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        for agent, relative in install.TARGETS.items():
            parent = self.home / ("xdg/opencode/skills" if agent == "opencode" else relative)
            self.assertEqual((parent / "code-max").resolve(), self.source)

    def test_invalid_arguments_and_environment(self):
        for args in (("--unknown",), ("--agent", "bad"), ("--target", "relative"),
                     ("--all", "--agent", "codex"), ("--list", "--all")):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_cli(*args).returncode, 0)
        self.env.pop("HOME")
        self.assertNotEqual(self.run_cli("--agent", "codex").returncode, 0)
        self.assertEqual(self.run_cli("--target", str(self.target)).returncode, 0)

    def test_bad_xdg_is_rejected(self):
        self.env["XDG_CONFIG_HOME"] = "relative"
        self.assertNotEqual(self.run_cli("--agent", "opencode").returncode, 0)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_invalid_source_does_not_write(self):
        (self.source / "SKILL.md").write_text("---\nname: code-max\n")
        self.assertNotEqual(self.run_cli("--target", str(self.target)).returncode, 0)
        self.assertFalse(self.target.exists())

    def test_directory_ancestor_and_recursive_target_rejected(self):
        self.target.write_text("not a directory")
        self.assertNotEqual(self.run_cli("--target", str(self.target / "skills")).returncode, 0)
        self.assertNotEqual(self.run_cli("--target", str(self.source / "nested")).returncode, 0)
        self.assertFalse((self.source / "nested").exists())

    def test_duplicate_target_processed_once(self):
        result = self.run_cli("--target", str(self.target), "--target", str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("linked:"), 1)

    def test_racing_directory_never_receives_nested_link(self):
        original = Path.symlink_to
        def race(path, source, **kwargs):
            path.mkdir()
            return original(path, source, **kwargs)
        with patch.object(Path, "symlink_to", race), self.assertRaises(FileExistsError):
            install.install(self.source, [self.target], dry_run=False, uninstall=False)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_overlapping_targets_are_rejected_before_writes(self):
        result = self.run_cli("--target", str(self.target), "--target", str(self.dest / "nested"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("overlapping destinations:", result.stderr)
        self.assertFalse(self.target.exists())
        self.assertFalse((self.source / "nested").exists())

    def test_invalid_utf8_is_actionable(self):
        (self.source / "SKILL.md").write_bytes(b"\xff")
        result = self.run_cli("--target", str(self.target))
        self.assertEqual(result.returncode, 1)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.target.exists())

    def test_python_entrypoint_dry_run_has_no_writes(self):
        before = set(self.source.rglob("*"))
        result = subprocess.run([sys.executable, str(self.source / "scripts/install.py"),
                                 "--target", str(self.target), "--dry-run"],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.target.exists())
        self.assertEqual(set(self.source.rglob("*")), before)

    def test_help_and_list_do_not_write(self):
        self.assertEqual(self.run_cli("--help").returncode, 0)
        self.assertIn("codex: ~/.agents/skills", self.run_cli("--list").stdout)
        self.assertEqual(list(self.home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
