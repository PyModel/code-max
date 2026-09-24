"""Negative controls prove package checks reject deliberately broken inputs."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from skill_meta import ValidationError, read_metadata
from validate import REQUIRED, check_links, check_scenarios, links, validate

ROOT = Path(__file__).resolve().parents[1]

VALID = "---\nname: code-max\ndescription: Use when testing code\n---\n\n# code-max\n"
CASE = {"id": "smoke", "trigger": True, "prompt": "Fix the bug", "expected": ["regression proof"], "forbidden": ["invented pass"]}


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in REQUIRED:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("content\n")
        self.skill = self.root / "SKILL.md"
        self.skill.write_text(VALID)
        self.scenarios = self.root / "evals/scenarios.json"
        self.scenarios.write_text(json.dumps({"version": 1, "scenarios": [CASE]}))
        self.doc = self.root / "README.md"

    def test_valid_package_and_renamed_checkout(self):
        self.assertEqual(read_metadata(self.skill)["name"], "code-max")
        self.assertEqual(validate(self.root)[1], 1)

    def test_invalid_frontmatter(self):
        cases = ["", VALID.lstrip("-"), VALID.replace("---\n\n#", "\n#"),
                 VALID.replace("name: code-max", "name: code-max\nname: other"),
                 VALID.replace("name: code-max", "name: Bad_Name"),
                 VALID.replace("name: code-max", "name: bad--name"),
                 VALID.replace("name: code-max", "name: " + "a" * 65),
                 VALID.replace("name: code-max", "name: other-skill"),
                 VALID.replace("description: Use when testing code", "description: Use when " + "x" * 1024),
                 VALID.replace("description: Use when testing code\n", ""),
                 VALID.replace("Use when testing code", "Use when testing: code"),
                 VALID.replace("Use when testing code", "Use when bad\x00input"),
                 VALID.replace("Use when testing code", "Use when testing # comment"),
                 VALID.replace("# code-max", ""),
                 VALID.replace("name: code-max", "license: MIT\nname: code-max")]
        for text in cases:
            with self.subTest(text=text):
                self.skill.write_text(text)
                with self.assertRaises(ValidationError):
                    read_metadata(self.skill)

    def test_missing_required_file(self):
        (self.root / "LICENSE").unlink()
        with self.assertRaisesRegex(ValidationError, "missing"):
            validate(self.root)

    def test_deleting_test_suite_fails_real_package(self):
        package = self.root / "package"
        shutil.copytree(ROOT, package, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        validate(package)
        shutil.rmtree(package / "tests")
        with self.assertRaisesRegex(ValidationError, "tests/test_install.py"):
            validate(package)

    def test_context_budget_checks_lines_and_bytes(self):
        for text in (VALID + "line\n" * 201, VALID + "x" * 12000):
            self.skill.write_text(text)
            with self.assertRaisesRegex(ValidationError, "context budget"):
                validate(self.root)

    def test_inline_reference_html_and_fragment_paths(self):
        for text in ("[skill](SKILL.md#code-max)", "[skill][s]\n[s]: SKILL.md",
                     '<a href="SKILL.md">skill</a>', '<img src="SKILL.md">'):
            self.doc.write_text(text)
            check_links(self.doc, self.root)
        for text in ("[bad](missing.md)", "[bad][b]\n[b]: missing.md",
                     '<img src="missing.svg">', "[bad](missing.md#anchor)"):
            self.doc.write_text(text)
            with self.assertRaisesRegex(ValidationError, "broken link"):
                check_links(self.doc, self.root)

    def test_external_urls_and_fenced_examples_ignored(self):
        self.doc.write_text('[site](https://example.com/a)\n```md\n[x](absent.md)\n```\n~~~\n[y](absent.md)\n~~~')
        check_links(self.doc, self.root)

    def test_percent_encoded_paths(self):
        (self.root / "a b.md").write_text("ok")
        self.doc.write_text("[space](a%20b.md)")
        check_links(self.doc, self.root)
        self.doc.write_text("[escape](%2e%2e/outside.md)")
        with self.assertRaisesRegex(ValidationError, "escapes"):
            check_links(self.doc, self.root)

    def test_path_escape_and_unsafe_symlinks(self):
        self.doc.write_text("[outside](../outside.md)")
        with self.assertRaisesRegex(ValidationError, "escapes"):
            check_links(self.doc, self.root)
        self.doc.write_text("ok")
        (self.root / "unsafe").symlink_to(self.root.parent)
        with self.assertRaisesRegex(ValidationError, "symlink escapes"):
            validate(self.root)

    def test_dangling_symlink_rejected(self):
        (self.root / "dangling").symlink_to(self.root / "missing")
        with self.assertRaises(OSError):
            validate(self.root)

    def test_historical_research_relative_link(self):
        doc = self.root / "docs/research/note.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("[skill](../../SKILL.md)")
        check_links(doc, self.root)
        doc.write_text("[skill](../SKILL.md)")
        with self.assertRaisesRegex(ValidationError, "broken link"):
            check_links(doc, self.root)

    def test_raw_eval_run_artifacts_are_not_link_checked(self):
        raw = self.root / "evals/results/2026-01-01-x/some-scenario/run-1/transcript.md"
        raw.parent.mkdir(parents=True)
        raw.write_text("[agent quoted](references/missing.md)")
        validate(self.root)
        summary = self.root / "evals/results/2026-01-01-x/matrix.md"
        summary.write_text("[broken](missing.md)")
        with self.assertRaisesRegex(ValidationError, "broken link"):
            validate(self.root)

    def test_scenario_schema_negative_controls(self):
        invalid = [[], {}, {"version": True, "scenarios": [CASE]},
                   {"version": 1, "scenarios": []},
                   {"version": 1, "scenarios": [CASE, CASE]},
                   {"version": 1, "scenarios": [{**CASE, "trigger": "true"}]},
                   {"version": 1, "scenarios": [{**CASE, "expected": []}]},
                   {"version": 1, "scenarios": [{**CASE, "prompt": " "}]},
                   {"version": 1, "scenarios": [{**CASE, "extra": "ignored?"}]}]
        for data in invalid:
            self.scenarios.write_text(json.dumps(data))
            with self.subTest(data=data), self.assertRaises(ValidationError):
                check_scenarios(self.scenarios)

    def test_link_positive_control(self):
        self.assertEqual(links('[proof](SKILL.md)\n<img src="banner.svg">'), ["SKILL.md", "banner.svg"])


if __name__ == "__main__":
    unittest.main()
