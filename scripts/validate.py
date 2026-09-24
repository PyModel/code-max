#!/usr/bin/env python3
"""Offline checks for this package, not a general YAML/Markdown or model evaluator."""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

sys.dont_write_bytecode = True
from skill_meta import ValidationError, read_metadata

REQUIRED = (
    "SKILL.md", "README.md", "AGENTS.md", "LICENSE", "skills.sh",
    "references/quality-gates.md", "references/report-template.md",
    "scripts/install.py", "scripts/skill_meta.py", "scripts/validate.py", "evals/scenarios.json",
    # Canaries: silently deleting the regression suite must fail validation.
    "tests/test_install.py", "tests/test_validate.py",
)


class HTMLLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for key, value in attrs if key in {"href", "src"} and value)


def links(text: str) -> list[str]:
    # Supported profile: fenced code, inline links/images, reference definitions,
    # and HTML href/src. Heading anchors and arbitrary Markdown are not validated.
    visible = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker and fence is None:
            fence = marker.group(1)
        elif fence and marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
            fence = None
        elif fence is None:
            visible.append(line)
    text = "\n".join(visible)
    result = re.findall(r"\]\((<[^>\n]+>|[^\s)]+)", text)
    result += re.findall(r"^\s{0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)", text, re.MULTILINE)
    html = HTMLLinks()
    html.feed(text)
    return [value.strip("<>") for value in result] + html.links


def check_links(path: Path, root: Path) -> None:
    for link in links(path.read_text(encoding="utf-8")):
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        relative = unquote(parsed.path)
        candidate = (path.parent / relative).resolve()
        if Path(relative).is_absolute() or not candidate.is_relative_to(root):
            raise ValidationError(f"{path.relative_to(root)}: link escapes package: {link}")
        if not candidate.exists():
            raise ValidationError(f"{path.relative_to(root)}: broken link: {link}")


def check_scenarios(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"version", "scenarios"} or type(data["version"]) is not int or data["version"] != 1:
        raise ValidationError("scenario document requires version 1 and scenarios")
    scenarios = data["scenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        raise ValidationError("scenarios must be a nonempty list")
    seen = set()
    for case in scenarios:
        if not isinstance(case, dict) or set(case) != {"id", "trigger", "prompt", "expected", "forbidden"}:
            raise ValidationError("scenario requires id, trigger, prompt, expected, forbidden")
        identifier = case["id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identifier) or identifier in seen:
            raise ValidationError("scenario IDs must be unique lowercase slugs")
        seen.add(identifier)
        if type(case["trigger"]) is not bool or not isinstance(case["prompt"], str) or not case["prompt"].strip():
            raise ValidationError(f"{identifier}: invalid trigger or prompt")
        for key in ("expected", "forbidden"):
            value = case[key]
            if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValidationError(f"{identifier}: {key} must contain nonempty rubric strings")
    return len(scenarios)


def walk_error(error: OSError) -> None:
    raise error


def validate(root: Path) -> tuple[int, int]:
    root = root.resolve(strict=True)
    for relative in REQUIRED:
        path = root / relative
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValidationError(f"missing or unsafe required file: {relative}")
    read_metadata(root / "SKILL.md")
    text = (root / "SKILL.md").read_text(encoding="utf-8")
    if len(text.splitlines()) > 200 or len(text.encode("utf-8")) > 12000:
        raise ValidationError("SKILL.md exceeds the 200-line / 12000-byte context budget")
    count = 0
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        dirs[:] = sorted(name for name in dirs if name not in {".git", "__pycache__", ".venv"})
        for name in sorted(dirs + files):
            path = Path(directory) / name
            if path.is_symlink():
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root):
                    raise ValidationError(f"symlink escapes package: {path.relative_to(root)}")
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix == ".md":
                check_links(path, root)
                count += 1
    return count, check_scenarios(root / "evals/scenarios.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        documents, cases = validate(args.root)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: metadata, context budget, package paths, {documents} Markdown documents, {cases} scenario definitions")
    print("Model behavior, external URLs, and heading anchors were NOT evaluated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
