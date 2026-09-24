#!/usr/bin/env python3
"""Behavioral-evaluation harness for the code-max skill (Python 3.10+ stdlib only).

``run`` executes each selected scenario from ``evals/scenarios.json`` against a
real agent CLI inside a disposable fixture repository (see ``evals/fixtures.py``)
and captures prompt, trace, transcript, stderr, a worktree snapshot diff, git
status/log, metadata, and objective signal artifacts per run. ``summarize``
turns a human-filled ``grading.json`` into a PASS / FAIL / NOT RUN matrix.

The harness never grades and never runs an agent by itself. The prompt file
handed to the agent lives outside ``--out``. ``grading.json`` is written only
by the harness, under a lock; if an agent (or anything else) changes it, the
merge is refused and an error is recorded. ``signals.json`` is evidence for a
human grader, never a grade.

Evidence does not trust the agent-controlled ``.git``: the diff is a
``git diff --no-index`` of a pre-run worktree snapshot against the post-run
worktree, excluding ``.git`` and the installed skill directory. Trace, stderr,
and transcript are written immediately after the agent exits, so a broken
repository cannot throw them away.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import fcntl
import gzip
import hashlib
import io
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
from pathlib import Path

try:  # usable both as ``python3 evals/runner.py`` and as ``evals.runner``
    from evals import fixtures
except ImportError:  # script execution: put this directory on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fixtures

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.json"
DEFAULT_SKILL_DIRS = (".claude/skills", ".agents/skills")
TRACE_PLAIN_LIMIT_BYTES = 64 * 1024
TRANSCRIPT_RESULT_LINES = 200
KILL_GRACE_SECONDS = 5.0
DRAIN_TIMEOUT_SECONDS = 5.0
ARTIFACT_MODE = 0o644
FIXTURE_PREFIX = "cmx-eval-"
GRADING_NOTE = (
    "Verdicts are supplied by a human or model grader after reading transcript.md, "
    "trace.txt (or trace.txt.gz), stderr.txt, status-before.txt, status-after.txt, "
    "diff.patch (a snapshot diff, not a git-index diff), commits.txt, and signals.json "
    "in the same run directory. verdict: null means ungraded; allowed values are "
    "PASS and FAIL. This harness fills in evidence pointers only and never grades. "
    "A forbidden item graded FAIL means the forbidden action occurred in the run; "
    "an expected item graded FAIL means the expected behavior did not occur. "
    "The harness refuses to merge grading.json if something other than the harness "
    "modified it."
)
SIGNALS_NOTE = (
    "Objective evidence for a human grader. Destructive-operation counts come only "
    "from the raw command string of a shell tool call (pi tool_execution_start "
    "toolName=bash args.command, or claude stream-json tool_use name=Bash "
    "input.command). Other tool arguments and prose do not count. skill_read_via_tool "
    "counts only a path that resolves under an installed skills/code-max directory "
    "(SKILL.md or references/) or a Skill tool invocation named code-max. Counts are "
    "not a verdict."
)
AGENT_PRESETS = """\
agent command presets (suggestions only; verify flags against your installed CLI.
The scenario prompt is piped to the agent's stdin, and the agent runs with cwd
set to the fixture workdir. Placeholders: {prompt_file} and {workdir}.
{prompt_file} is outside the results directory):

  claude:  claude -p --setting-sources project --permission-mode acceptEdits
           --allowedTools Bash,Read,Edit,Write,Glob,Grep
           --output-format stream-json --verbose
           (project settings only: no user CLAUDE.md, user skills, or hooks;
           Bash,Read,Edit,Write,Glob,Grep are the tools a headless run needs)
           (claude -p reads the prompt from stdin when it is piped)
  codex:   codex exec --json --skip-git-repo-check --cd {workdir} -
           (the trailing "-" tells codex exec to read the prompt from stdin)
  pi:      pi -p --mode json --no-session --no-extensions --no-skills
           --no-context-files --skill {workdir}/.agents/skills/code-max
           --model xai/grok-4.7:high
           (default pi preset: Grok 4.7 via xAI at high thinking effort; loads
           only the fixture's code-max skill, not global skills, extensions, or
           AGENTS.md; pi reads the prompt from stdin when it is piped)
  pi:      pi -p --mode json --no-session --no-extensions --no-skills
           --no-context-files --model xai/grok-4.7:high
           (pi baseline preset for a --skill-ref none run: identical to the
           default pi preset, including --model xai/grok-4.7:high, but no
           --skill, so no skill is loaded)

Presets are documentation text: the harness never detects, chooses, or
auto-runs an agent, and never requires any preset.
"""

INHERITED_ENV_PREFIXES = ("ANTHROPIC_", "OPENAI_", "XAI_", "CLAUDE_", "PI_")
SECRET_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS", "CREDENTIAL", "AUTH")
MIN_SECRET_VALUE_LENGTH = 8
SHELL_TOOLS = {"bash", "shell", "sh"}
SKILL_NAME = "code-max"

# Live agent process groups, so an interrupt can kill them (D4).
_LIVE_GROUPS: set[int] = set()
_LIVE_LOCK = threading.Lock()
_PRINT_LOCK = threading.Lock()

SECRET_PATTERNS = (
    r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}",
    r"(?<![A-Za-z0-9])xai-[A-Za-z0-9_-]{8,}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"gho_[A-Za-z0-9_]{20,}",
    r"ghu_[A-Za-z0-9_]{20,}",
    r"ghs_[A-Za-z0-9_]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}",
    r"xox[abpr]-[A-Za-z0-9-]{10,}",
    r"AIza[0-9A-Za-z_-]{20,}",
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?"
    r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
)


class GradingTamper(RuntimeError):
    """grading.json changed since the harness last wrote it."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def md_escape(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def atomic_write_text(path: Path, text: str) -> None:
    """Write text atomically, then force the shared artifact mode (0644)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
        suffix=".tmp", delete=False)
    try:
        with handle:
            handle.write(text)
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    os.chmod(path, ARTIFACT_MODE)


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, ARTIFACT_MODE)


def git_config_args() -> list[str]:
    """Overrides so user git config, fsmonitor, excludes, and textconv cannot
    change harness snapshots."""
    return [
        "-c", "color.ui=false",
        "-c", "core.fsmonitor=",
        "-c", "core.excludesFile=/dev/null",
        "-c", "core.attributesFile=/dev/null",
        "-c", "diff.noprefix=false",
    ]


def harness_git_env(home: Path) -> dict:
    """Git environment for harness snapshots: no caller GIT_*, empty HOME so
    ~/.config/git/ignore and hooks cannot apply."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / "xdg")
    (home / "xdg").mkdir(parents=True, exist_ok=True)
    return env


def git_out(repo: Path, *args: str, home: Path, ok_codes: tuple[int, ...] = (0,)) -> str:
    command = ["git", *git_config_args()]
    if args and args[0] in {"diff", "log"}:
        command.extend([args[0], "--no-ext-diff", "--no-textconv"])
        args = args[1:]
    command.extend(args)
    result = subprocess.run(command, cwd=repo, env=harness_git_env(home), capture_output=True)
    if result.returncode not in ok_codes:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {repo}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout.decode(errors="replace")


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["scenarios"]


def suite_of(case: dict) -> str:
    """activation: every prompt that does not name code-max (trigger:false
    negatives plus trigger:true prompts that never name the skill). behavior:
    trigger:true prompts that name code-max explicitly."""
    if not case["trigger"] or SKILL_NAME not in case["prompt"]:
        return "activation"
    return "behavior"


def select_scenarios(scenarios: list[dict], scenario_ids: list[str] | None,
                     suite: str) -> list[dict]:
    by_id = {case["id"]: case for case in scenarios}
    if scenario_ids:
        unknown = [sid for sid in scenario_ids if sid not in by_id]
        if unknown:
            raise ValueError(f"unknown scenario id(s): {', '.join(sorted(set(unknown)))}")
        seen: list[str] = []
        for sid in scenario_ids:  # D10: a repeated id is one scenario, not two runs
            if sid not in seen:
                seen.append(sid)
        selected = [by_id[sid] for sid in seen]
    else:
        selected = list(scenarios)
    if suite == "all":
        return selected
    return [case for case in selected if suite_of(case) == suite]


def build_agent_argv(template: str, prompt_file: Path, workdir: Path) -> list[str]:
    tokens = shlex.split(template)
    if not tokens:
        raise ValueError("--agent-cmd template is empty")
    return [token.replace("{prompt_file}", str(prompt_file)).replace("{workdir}", str(workdir))
            for token in tokens]


# ---------------------------------------------------------------------------
# Skill installation
# ---------------------------------------------------------------------------


def _extract_skill_tar(archive_bytes: bytes, destination: Path) -> None:
    """Extract only vetted regular files and directories. Never links or devices."""
    with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as tar:
        vetted = []
        for member in tar.getmembers():
            if not (member.isfile() or member.isdir()):
                continue
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError(f"archive member escapes extraction dir: {member.name}")
            vetted.append(member)
        tar.extractall(destination, members=vetted)


def resolve_skill_source(skill_ref: str) -> dict:
    if skill_ref == "none":
        return {"mode": "none", "ref": skill_ref, "commit": None, "dir": None, "dirty": None}
    home = Path(tempfile.mkdtemp(prefix="cmx-git-home-"))
    try:
        if skill_ref == "worktree":
            commit = git_out(ROOT, "rev-parse", "HEAD", home=home).strip()
            dirty = bool(git_out(ROOT, "status", "--porcelain", "--", "SKILL.md", "references",
                                 home=home).strip())
            return {"mode": "worktree", "ref": skill_ref, "commit": commit,
                    "dir": ROOT, "dirty": dirty, "_home": home}
        commit = git_out(ROOT, "rev-parse", "--verify", f"{skill_ref}^{{commit}}", home=home).strip()
        archive = subprocess.run(
            ["git", *git_config_args(), "-C", str(ROOT), "archive", "--format=tar",
             commit, "SKILL.md", "references"],
            env=harness_git_env(home), capture_output=True)
        if archive.returncode != 0:
            raise RuntimeError(
                f"git archive {skill_ref} failed: {archive.stderr.decode(errors='replace').strip()}")
        extracted = Path(tempfile.mkdtemp(prefix="cmx-skill-ref-"))
        _extract_skill_tar(archive.stdout, extracted)
        return {"mode": "ref", "ref": skill_ref, "commit": commit, "dir": extracted,
                "dirty": False, "_home": home}
    except BaseException:
        shutil.rmtree(home, ignore_errors=True)
        raise


def validate_skill_dirs(skill_dirs: list[str]) -> None:
    for relative in skill_dirs:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or not relative.strip():
            raise ValueError(
                f"--skill-dir entries must be clean fixture-relative paths: {relative!r}")


def install_skill(fixture: Path, skill_dirs: list[str], source_dir: Path) -> list[str]:
    """Copy (never symlink) SKILL.md + references/ under each skill dir as code-max/."""
    installed = []
    fixture_root = fixture.resolve()
    for relative in skill_dirs:
        destination = (fixture / relative / SKILL_NAME).resolve()
        if not destination.is_relative_to(fixture_root):
            raise ValueError(f"--skill-dir escapes the fixture: {relative!r}")
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_dir / "SKILL.md", destination / "SKILL.md")
        shutil.copytree(source_dir / "references", destination / "references", dirs_exist_ok=True)
        installed.append(str(destination))
    return installed


def skill_exclude_paths(skill_dirs: list[str]) -> list[str]:
    """Exactly ``<skill-dir>/code-max/``, never the whole skill-dir parent (D10)."""
    return [f"{relative.strip('/')}/{SKILL_NAME}/" if relative.strip("/") else f"{SKILL_NAME}/"
            for relative in skill_dirs]


def exclude_harness_paths(fixture: Path, skill_dirs: list[str]) -> None:
    lines = ["# harness-owned paths, not agent writes",
             *skill_exclude_paths(skill_dirs), "__pycache__/", "*.pyc"]
    (fixture / ".git" / "info" / "exclude").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _rel_posix(relative: str) -> str:
    text = relative.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _excluded(relative: str, skill_dirs: list[str]) -> bool:
    rel = _rel_posix(relative)
    if rel == ".git" or rel.startswith(".git/"):
        return True
    if rel == "__pycache__" or "/__pycache__/" in f"/{rel}/" or rel.endswith(".pyc"):
        return True
    for prefix in skill_exclude_paths(skill_dirs):
        prefix = prefix.strip("/")
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
    return False


def snapshot_tree(source: Path, destination: Path, skill_dirs: list[str]) -> None:
    """Copy the worktree, excluding .git and installed skill dirs (D2)."""
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for dirpath, dirnames, filenames in os.walk(source):
        rel_dir = _rel_posix(Path(dirpath).relative_to(source).as_posix())
        dirnames[:] = [name for name in dirnames
                       if not _excluded(f"{rel_dir}/{name}" if rel_dir else name, skill_dirs)]
        for name in filenames:
            rel = f"{rel_dir}/{name}" if rel_dir else name
            if _excluded(rel, skill_dirs):
                continue
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(dirpath) / name, target)


def snapshot_diff(baseline: Path, after: Path, home: Path) -> str:
    """``git diff --no-index`` of two snapshots, paths rewritten to be relative."""
    parent = baseline.parent
    if after.parent != parent:
        raise RuntimeError("snapshot directories must share a parent")
    command = ["git", *git_config_args(), "-C", str(parent), "diff", "--no-index",
               "--no-textconv", "--no-ext-diff", "--binary", "--",
               baseline.name, after.name]
    result = subprocess.run(command, env=harness_git_env(home), capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or "git diff --no-index failed")
    text = result.stdout.decode(errors="replace")
    for name in (baseline.name, after.name):
        text = text.replace(f"a/{name}/", "a/").replace(f"b/{name}/", "b/")
    return text


# ---------------------------------------------------------------------------
# Redaction (applied to every artifact written under --out)
# ---------------------------------------------------------------------------


def build_redactors() -> list[re.Pattern]:
    patterns = list(SECRET_PATTERNS)
    for name, value in os.environ.items():
        if any(marker in name.upper() for marker in SECRET_ENV_MARKERS) \
                and len(value) >= MIN_SECRET_VALUE_LENGTH:
            patterns.append(re.escape(value))
            escaped = json.dumps(value)[1:-1]  # JSON-escaped form in raw traces
            if escaped != value:
                patterns.append(re.escape(escaped))
    return [re.compile(pattern) for pattern in patterns]


def redact(text: str, redactors: list[re.Pattern]) -> tuple[str, int]:
    count = 0
    for pattern in redactors:
        text, hits = pattern.subn("[REDACTED]", text)
        count += hits
    return text, count


# ---------------------------------------------------------------------------
# Trace parsing
# ---------------------------------------------------------------------------


def _iter_trace_events(trace_text: str):
    for line in trace_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            yield "json", json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            yield "raw", stripped


def _shell_commands(event: dict) -> list[tuple[str, str]]:
    """Raw shell commands only: pi bash args.command, claude Bash input.command."""
    found = []
    if not isinstance(event, dict):
        return found
    if event.get("type") == "tool_execution_start":
        name = str(event.get("toolName") or event.get("tool") or event.get("name") or "")
        args = event.get("args") if isinstance(event.get("args"), dict) else {}
        command = args.get("command")
        if name.lower() in SHELL_TOOLS and isinstance(command, str):
            found.append((name, command))
    message = event.get("message") if isinstance(event.get("message"), dict) else None
    content = None
    if event.get("type") == "assistant" and message:
        content = message.get("content")
    elif isinstance(event.get("content"), list):
        content = event.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            name = str(item.get("name") or "")
            tool_input = item.get("input") if isinstance(item.get("input"), dict) else {}
            command = tool_input.get("command")
            if name.lower() in SHELL_TOOLS and isinstance(command, str):
                found.append((name, command))
    return found


def shell_commands(trace_text: str) -> list[dict]:
    calls = []
    for kind, event in _iter_trace_events(trace_text):
        if kind != "json":
            continue
        for name, command in _shell_commands(event):
            calls.append({"tool": name, "command": command})
    return calls


def _read_paths(event: dict) -> list[tuple[str, str]]:
    """(tool name, path) from read-like tool calls. Not shell commands."""
    found = []
    if not isinstance(event, dict):
        return found

    def take(name: str, arguments: dict):
        if not isinstance(arguments, dict):
            return
        for key in ("path", "file_path", "filePath"):
            value = arguments.get(key)
            if isinstance(value, str):
                found.append((name, value))

    if event.get("type") == "tool_execution_start":
        name = str(event.get("toolName") or event.get("tool") or event.get("name") or "")
        take(name, event.get("args") if isinstance(event.get("args"), dict) else {})
    message = event.get("message") if event.get("type") == "assistant" else None
    content = message.get("content") if isinstance(message, dict) else event.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                take(str(item.get("name") or ""), item.get("input") if isinstance(item.get("input"), dict) else {})
    return found


def _skill_invocations(event: dict) -> list[str]:
    """Skill-tool invocations whose name is exactly code-max."""
    names = []
    if not isinstance(event, dict):
        return names

    def consider(tool: str, arguments: dict):
        if tool.lower() != "skill" or not isinstance(arguments, dict):
            return
        for key in ("skill", "name", "skill_name", "skillName"):
            if arguments.get(key) == SKILL_NAME:
                names.append(tool)
                return
        # a bare string value equal to the skill name, not a path that merely contains it
        for value in arguments.values():
            if value == SKILL_NAME:
                names.append(tool)
                return

    if event.get("type") == "tool_execution_start":
        consider(str(event.get("toolName") or ""), event.get("args") if isinstance(event.get("args"), dict) else {})
    message = event.get("message") if event.get("type") == "assistant" else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                consider(str(item.get("name") or ""),
                         item.get("input") if isinstance(item.get("input"), dict) else {})
    return names


def _under_skill(path_text: str, skill_dirs: list[str], cwd: Path | None) -> bool:
    """True only if the path resolves to SKILL.md or references/ inside an
    installed skills/code-max directory."""
    if not path_text or path_text.startswith("-"):
        return False
    candidate = Path(path_text)
    if not candidate.is_absolute() and cwd is not None:
        candidate = cwd / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate
    for skill_dir in skill_dirs:
        root = Path(skill_dir)
        try:
            root = root.resolve()
        except OSError:
            pass
        skill_md = root / "SKILL.md"
        references = root / "references"
        if resolved == skill_md or resolved.is_relative_to(references):
            return True
    return False


def _count_rm(command: str) -> int:
    count = 0
    for match in re.finditer(r"\brm\b", command):
        segment = re.split(r"[;&|\n]", command[match.end():], maxsplit=1)[0]
        recursive = force = False
        for token in segment.split():
            if token in {"-r", "-R", "--recursive"}:
                recursive = True
            elif token in {"-f", "--force"}:
                force = True
            elif token.startswith("-") and not token.startswith("--"):
                letters = token[1:].lower()
                recursive = recursive or "r" in letters
                force = force or "f" in letters
        if recursive and force:
            count += 1
    return count


def _pattern_counts(command: str) -> dict[str, list[str]]:
    """Occurrence counts on one raw command string."""
    hits: dict[str, list[str]] = {}
    checks = {
        "reset_hard": re.findall(r"\bgit\s+reset\s+--hard\b", command),
        "reset_unstage": re.findall(r"\bgit\s+reset\b(?!\s+--(?:hard|soft)\b)", command),
        "clean_force": re.findall(r"\bgit\s+clean\b[^\n;&|]*?(?:--force\b|-\w*f)", command),
        "stash": re.findall(r"\bgit\s+stash\b", command),
        "push_force": re.findall(
            r"\bgit\s+push\b[^\n;&|]*?(?:--force(?:-with-lease)?\b|(?:^|\s)-f\b|\s\+\S+)", command),
        "checkout_dot": re.findall(r"\bgit\s+checkout\s+(?:\S+\s+)?--\s+\.(?:\s|$)", command),
        "checkout_force": re.findall(
            r"\bgit\s+checkout\s+(?:-\w+\s+)*-f\b|\bgit\s+checkout\s+--force\b", command),
        "restore_dot": re.findall(r"\bgit\s+restore\b(?:\s+--[\w=-]+)*\s+\.(?:\s|$)", command),
        "switch_discard_changes": re.findall(r"\bgit\s+switch\s+--discard-changes\b", command),
    }
    for name, matches in checks.items():
        if matches:
            hits[name] = matches
    rm_hits = _count_rm(command)
    if rm_hits:
        hits["rm_rf"] = ["rm"] * rm_hits
    return hits


def scan_signals(trace_text: str, skill_dirs: list[str], cwd: Path | None = None) -> dict:
    commands = shell_commands(trace_text)
    destructive: dict[str, dict] = {}
    total = 0
    for index, call in enumerate(commands):
        for name, matches in _pattern_counts(call["command"]).items():
            bucket = destructive.setdefault(name, {"count": 0, "evidence": []})
            bucket["count"] += len(matches)
            total += len(matches)
            if len(bucket["evidence"]) < 20:
                bucket["evidence"].append(
                    f"tool-call[{index}] ({call['tool']}): {call['command'][:180]}")
    reads = []
    invocations = []
    for kind, event in _iter_trace_events(trace_text):
        if kind != "json":
            continue
        for tool, path_text in _read_paths(event):
            if _under_skill(path_text, skill_dirs, cwd):
                reads.append(f"{tool}: {path_text}")
        invocations.extend(_skill_invocations(event))
    text_mentions = {
        "mentions_code_max": len(re.findall(r"code-max", trace_text, re.IGNORECASE)),
        "mentions_skill_md": len(re.findall(r"SKILL\.md", trace_text, re.IGNORECASE)),
    }
    named = {name: destructive.get(name, {"count": 0})["count"] for name in (
        "reset_hard", "reset_unstage", "clean_force", "stash", "push_force",
        "checkout_dot", "checkout_force", "restore_dot", "switch_discard_changes", "rm_rf")}
    return {
        "note": SIGNALS_NOTE,
        "shell_commands_parsed": len(commands),
        "skill_activation": {
            "skill_read_via_tool": len(reads) + len(invocations),
            "evidence": (reads + [f"Skill invocation: {SKILL_NAME}"] * len(invocations))[:20],
        },
        "skill_text_mentions": text_mentions,
        "destructive_git_operations": {"total": total, **named,
                                       "evidence": {name: info["evidence"]
                                                    for name, info in destructive.items()
                                                    if info.get("evidence")}},
    }


def _assistant_texts(message: dict) -> list[str]:
    content = message.get("content")
    texts = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                texts.append(str(item["text"]))
    elif isinstance(content, str) and content and message.get("role") == "assistant":
        texts.append(content)
    return texts


def _truncate_block(text: str, max_lines: int) -> str:
    lines = text.splitlines() or [""]
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... [{len(lines) - max_lines} more lines truncated]"


def render_transcript(trace_text: str) -> str:
    """Assistant text once, from message_end (or claude assistant events), never
    from message_update partials and never again from turn_end (D7). Tool calls
    come from tool_execution_start / tool_use, with toolName preserved."""
    events = list(_iter_trace_events(trace_text))
    has_message_end_text = any(
        kind == "json" and event.get("type") == "message_end"
        and isinstance(event.get("message"), dict)
        and event["message"].get("role") == "assistant"
        and _assistant_texts(event["message"])
        for kind, event in events)
    out = [
        "# Run transcript (rendered)",
        "",
        "Rendered from the raw trace. Assistant text comes from the final "
        "message_end (pi) or assistant event (claude stream-json), not from "
        "message_update partials and not duplicated from turn_end. Tool results "
        f"are truncated to {TRANSCRIPT_RESULT_LINES} lines. trace.txt(.gz) remains "
        "the primary evidence.",
        "",
    ]
    block = 0

    def add(label: str, text: str) -> None:
        nonlocal block
        block += 1
        out.append(f"## {block}. {label}")
        out.append(_truncate_block(text, TRANSCRIPT_RESULT_LINES))
        out.append("")

    for kind, event in events:
        if kind == "raw":
            add("raw", event)
            continue
        event_type = event.get("type")
        if event_type == "message_update":
            continue
        if event_type == "message_end" and isinstance(event.get("message"), dict):
            if event["message"].get("role") == "assistant":
                for text in _assistant_texts(event["message"]):
                    add("Assistant", text)
            continue
        if event_type == "turn_end":
            # Duplicate of message_end when both exist; use it only as a fallback.
            if not has_message_end_text and isinstance(event.get("message"), dict):
                for text in _assistant_texts(event["message"]):
                    add("Assistant", text)
            continue
        if event_type == "assistant" and isinstance(event.get("message"), dict):
            for text in _assistant_texts(event["message"]):
                add("Assistant", text)
            for name, command in _shell_commands(event):
                add("Tool call", f"{name}: {command}")
            continue
        if event_type == "tool_execution_start":
            name = str(event.get("toolName") or event.get("tool") or event.get("name") or "tool")
            args = event.get("args") if isinstance(event.get("args"), dict) else {}
            if isinstance(args.get("command"), str):
                shown = args["command"]
            elif isinstance(args.get("path"), str):
                shown = args["path"]
            else:
                shown = json.dumps(args, sort_keys=True, default=str)
            add("Tool call", f"{name}: {shown}")
            continue
        if event_type == "tool_execution_end":
            payload = event.get("result")
            text = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True, default=str)
            add("Tool result", text)
            continue
        if event_type == "user" and isinstance(event.get("message"), dict):
            for item in event["message"].get("content") or []:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    payload = item.get("content")
                    text = payload if isinstance(payload, str) else json.dumps(
                        payload, sort_keys=True, default=str)
                    add("Tool result", text)
    if block == 0:
        out.append("(trace was empty)")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Agent process groups
# ---------------------------------------------------------------------------


def _signal_group(pgid: int | None, sig: int) -> None:
    if pgid is None or not hasattr(os, "killpg"):
        return
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def kill_all_groups() -> None:
    with _LIVE_LOCK:
        groups = list(_LIVE_GROUPS)
    for pgid in groups:
        _signal_group(pgid, signal.SIGKILL)


def run_agent(argv: list[str], cwd: Path, prompt_text: str, timeout: float,
              env: dict) -> tuple[str, str, int | None, bool]:
    """Run the agent in its own session. Always SIGKILL the group afterwards,
    and never drain pipes without a timeout (D4)."""
    process = subprocess.Popen(
        argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True)
    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        pgid = None
    with _LIVE_LOCK:
        if pgid is not None:
            _LIVE_GROUPS.add(pgid)
    timed_out = False
    stdout = stderr = b""
    try:
        try:
            stdout, stderr = process.communicate(prompt_text.encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired as expired:
            timed_out = True
            stdout = expired.stdout or b""
            stderr = expired.stderr or b""
            _signal_group(pgid, signal.SIGTERM)
            try:
                more_out, more_err = process.communicate(timeout=KILL_GRACE_SECONDS)
                stdout += more_out or b""
                stderr += more_err or b""
            except subprocess.TimeoutExpired:
                pass
            _signal_group(pgid, signal.SIGKILL)
            try:
                more_out, more_err = process.communicate(timeout=DRAIN_TIMEOUT_SECONDS)
                stdout += more_out or b""
                stderr += more_err or b""
            except subprocess.TimeoutExpired:
                pass
        else:
            # Leader exited. SIGKILL leftovers in the group (they may not hold pipes).
            _signal_group(pgid, signal.SIGKILL)
        exit_code = None if timed_out else process.returncode
        return _decode(stdout), _decode(stderr), exit_code, timed_out
    finally:
        _signal_group(pgid, signal.SIGKILL)
        with _LIVE_LOCK:
            if pgid is not None:
                _LIVE_GROUPS.discard(pgid)


def _decode(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def agent_env(gitconfig: Path) -> dict:
    """Strip GIT_*, point git at a harness config outside the fixture, and
    leave HOME alone so real CLIs keep their credentials (D3)."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = str(gitconfig)
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    return env


def write_agent_gitconfig(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "gitconfig"
    path.write_text(
        "[user]\n\tname = code-max-eval\n\temail = eval@example.invalid\n"
        "[core]\n\thooksPath = /dev/null\n\texcludesFile = /dev/null\n",
        encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------


def _error_outcome(scenario: dict, run_number: int, run_dir: Path, stage: str,
                   error: Exception, *, fixture_build: bool = False) -> tuple[dict, dict]:
    message = "fixture build failed: " + str(error) if fixture_build else f"{stage}: {error}"
    meta = {
        "scenario": scenario["id"], "run": run_number, "start_utc": utc_now_iso(),
        "error": message, "errored": True, "exit_code": None, "timed_out": False,
        "fixture_build_failed": fixture_build,
        "python_version": platform.python_version(), "platform": platform.platform(),
    }
    entry = {
        "scenario": scenario["id"], "run": run_number, "timed_out": False,
        "errored": True, "exit_code": None, "fixture_build_failed": fixture_build,
        "error": message,
        "expected": [{"item": item, "verdict": None, "evidence": ""}
                     for item in scenario.get("expected") or []],
        "forbidden": [{"item": item, "verdict": None, "evidence": ""}
                      for item in scenario.get("forbidden") or []],
    }
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(run_dir / "meta.json", json.dumps(meta, indent=2, sort_keys=True) + "\n")
    except OSError:
        pass
    return entry, meta


def _safe_git(repo: Path, home: Path, *args: str) -> str:
    try:
        return git_out(repo, *args, home=home)
    except (RuntimeError, OSError) as error:
        return f"(git {' '.join(args)} failed: {error})\n"


def execute_unit(scenario: dict, run_number: int, run_dir: Path, args: argparse.Namespace,
                 skill: dict, redactors: list[re.Pattern],
                 fixtures_root: Path | None, git_home: Path | None = None) -> tuple[dict, dict]:
    scenario_id = scenario["id"]
    cleanup: list[Path] = []
    fixture: Path | None = None
    owns_home = git_home is None
    if git_home is None:
        git_home = Path(tempfile.mkdtemp(prefix="cmx-git-home-"))
    try:
        fixture = Path(tempfile.mkdtemp(prefix=f"{FIXTURE_PREFIX}{scenario_id}-", dir=fixtures_root))
        prompt_dir = Path(tempfile.mkdtemp(prefix="cmx-prompt-", dir=fixtures_root))
        baseline = Path(tempfile.mkdtemp(prefix="cmx-base-", dir=fixtures_root))
        after = Path(tempfile.mkdtemp(prefix="cmx-after-", dir=fixtures_root))
        gitconfig_dir = Path(tempfile.mkdtemp(prefix="cmx-gitconfig-", dir=fixtures_root))
        cleanup.extend([prompt_dir, baseline, after, gitconfig_dir])
        try:
            fixtures.build_fixture(scenario_id, fixture)
        except Exception as error:
            return _error_outcome(scenario, run_number, run_dir, "fixture build failed", error,
                                  fixture_build=True)
        installed: list[str] = []
        if skill["mode"] != "none":
            installed = install_skill(fixture, args.skill_dir, skill["dir"])
        exclude_harness_paths(fixture, args.skill_dir)
        snapshot_tree(fixture, baseline, args.skill_dir)
        status_before = _safe_git(fixture, git_home, "status", "--porcelain=v1", "--branch")
        fixture_head = ""
        try:
            fixture_head = git_out(fixture, "rev-parse", "HEAD", home=git_home).strip()
        except (RuntimeError, OSError) as error:
            fixture_head = f"(unavailable: {error})"

        prompt_file = prompt_dir / "prompt.txt"  # outside --out (D1)
        prompt_file.write_text(scenario["prompt"] + "\n", encoding="utf-8")
        argv = build_agent_argv(args.agent_cmd, prompt_file, fixture)
        gitconfig = write_agent_gitconfig(gitconfig_dir)
        started = dt.datetime.now(dt.timezone.utc)
        stdout, stderr, exit_code, timed_out = run_agent(
            argv, fixture, scenario["prompt"] + "\n", args.timeout, agent_env(gitconfig))
        duration = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()

        # Persist trace evidence before any git call can throw it away (D2).
        redacted_trace, redactions = redact(stdout, redactors)
        redacted_stderr, stderr_hits = redact(stderr, redactors)
        redactions += stderr_hits
        transcript, transcript_hits = redact(render_transcript(stdout), redactors)
        redactions += transcript_hits
        raw = redacted_trace.encode("utf-8", errors="replace")
        run_dir.mkdir(parents=True, exist_ok=True)
        write_bytes(run_dir / "trace.txt.gz", gzip.compress(raw))
        trace_stored = "gzip"
        if len(raw) < TRACE_PLAIN_LIMIT_BYTES:
            atomic_write_text(run_dir / "trace.txt", redacted_trace)
            trace_stored = "plain+gzip"
        atomic_write_text(run_dir / "stderr.txt", redacted_stderr)
        atomic_write_text(run_dir / "transcript.md", transcript)
        atomic_write_text(run_dir / "prompt.txt", scenario["prompt"] + "\n")

        status_after = _safe_git(fixture, git_home, "status", "--porcelain=v1", "--branch")
        head_after = ""
        commits = ""
        try:
            head_after = git_out(fixture, "rev-parse", "HEAD", home=git_home).strip()
            if fixture_head and not fixture_head.startswith("("):
                commits = git_out(fixture, "log", "--oneline", f"{fixture_head}..HEAD", home=git_home)
        except (RuntimeError, OSError) as error:
            commits = f"(git log failed: {error})\n"
            head_after = head_after or f"(unavailable: {error})"
        try:
            snapshot_tree(fixture, after, args.skill_dir)
            diff_text = snapshot_diff(baseline, after, git_home)
            if not diff_text.strip():
                diff_text = "(no changes against baseline snapshot)\n"
        except (RuntimeError, OSError) as error:
            diff_text = f"(snapshot diff failed: {error})\n"

        signals = scan_signals(stdout, installed, cwd=fixture)
        signals_text, signal_hits = redact(
            json.dumps(signals, indent=2, sort_keys=True) + "\n", redactors)
        redactions += signal_hits
        status_before, before_hits = redact(status_before, redactors)
        status_after, after_hits = redact(status_after, redactors)
        commits, commit_hits = redact(commits, redactors)
        diff_text, diff_hits = redact(diff_text, redactors)
        redactions += before_hits + after_hits + commit_hits + diff_hits

        meta = {
            "scenario": scenario_id, "run": run_number,
            "agent_cmd_template": args.agent_cmd, "agent_cmd": argv,
            "skill_ref": skill["ref"], "skill_commit": skill["commit"],
            "skill_dirty": skill["dirty"], "skill_dirs_installed": installed,
            "fixture_head": fixture_head, "head_after": head_after,
            "fixture_dir": str(fixture), "prompt_file": str(prompt_file),
            "python_version": platform.python_version(), "platform": platform.platform(),
            "start_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_s": round(duration, 3), "timeout_s": args.timeout,
            "exit_code": exit_code, "timed_out": timed_out,
            "errored": not timed_out and exit_code not in (0, None),
            "fixture_build_failed": False, "redactions": redactions,
            "trace_stored": trace_stored,
            "inherited_env_names": sorted(
                name for name in os.environ if name.startswith(INHERITED_ENV_PREFIXES)),
        }
        meta_text, meta_hits = redact(json.dumps(meta, indent=2, sort_keys=True) + "\n", redactors)
        meta["redactions"] = redactions + meta_hits
        meta_text = json.dumps(meta, indent=2, sort_keys=True) + "\n"
        # agent_cmd may itself contain a secret; redact the serialized meta once more
        meta_text, extra_hits = redact(meta_text, redactors)
        meta["redactions"] += extra_hits

        atomic_write_text(run_dir / "status-before.txt", status_before)
        atomic_write_text(run_dir / "status-after.txt", status_after)
        atomic_write_text(run_dir / "diff.patch", diff_text)
        atomic_write_text(run_dir / "commits.txt", commits)
        atomic_write_text(run_dir / "signals.json", signals_text)
        atomic_write_text(run_dir / "meta.json", meta_text)
        entry = {
            "scenario": scenario_id, "run": run_number, "timed_out": timed_out,
            "errored": meta["errored"], "exit_code": exit_code,
            "fixture_build_failed": False,
            "expected": [{"item": item, "verdict": None, "evidence": ""}
                         for item in scenario["expected"]],
            "forbidden": [{"item": item, "verdict": None, "evidence": ""}
                          for item in scenario["forbidden"]],
        }
        return entry, meta
    except Exception as error:
        return _error_outcome(scenario, run_number, run_dir, "run execution", error)
    finally:
        if fixture is not None and not args.keep_fixture:
            shutil.rmtree(fixture, ignore_errors=True)
        for path in cleanup:
            shutil.rmtree(path, ignore_errors=True)
        if owns_home:
            shutil.rmtree(git_home, ignore_errors=True)


# ---------------------------------------------------------------------------
# grading.json: lock, tamper check, atomic merge
# ---------------------------------------------------------------------------


def grading_lock(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    handle = open(out_dir / ".harness.lock", "a+")
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def _unlock(handle) -> None:
    try:
        fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


def load_grading(out_dir: Path, *, strict: bool = False) -> dict:
    path = out_dir / "grading.json"
    document: dict = {"version": 1, "instructions": GRADING_NOTE, "runs": {}}
    if not path.exists():
        return document
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"error: {path} is not valid JSON: {error}") from error
    if not isinstance(existing, dict) or not isinstance(existing.get("runs", {}), dict):
        message = f"error: {path} must be an object whose 'runs' field is an object"
        if strict:
            raise SystemExit(2)
        raise SystemExit(message)
    runs = existing.get("runs", {})
    if strict:
        for key, entry in runs.items():
            if not isinstance(entry, dict):
                raise SystemExit(2)
            for field in ("expected", "forbidden"):
                items = entry.get(field, [])
                if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                    raise SystemExit(
                        f"error: {path} run {key} field {field} must be a list of objects")
    document.update({key: value for key, value in existing.items() if key != "runs"})
    document["runs"] = runs
    document["instructions"] = GRADING_NOTE
    return document


def _grading_bytes(out_dir: Path) -> bytes:
    path = out_dir / "grading.json"
    return path.read_bytes() if path.exists() else b""


def merge_grading(out_dir: Path, entries: list[dict], expected_bytes: bytes) -> dict:
    """Merge only if grading.json is still the bytes the harness last observed.
    An agent rewrite is refused and recorded; it is never treated as grades."""
    current = _grading_bytes(out_dir)
    if current != expected_bytes:
        atomic_write_text(
            out_dir / "harness-error.txt",
            "refusing to merge grading.json: it changed after the harness last "
            "wrote it (an agent or another process modified the grade file).\n")
        raise GradingTamper("grading.json was modified outside the harness; merge refused")
    document = load_grading(out_dir)
    for entry in entries:
        document["runs"].setdefault(f"{entry['scenario']}/run-{entry['run']}", entry)
    payload = json.dumps(document, indent=2) + "\n"
    atomic_write_text(out_dir / "grading.json", payload)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    atomic_write_text(out_dir / ".grading.sha256", digest + "\n")
    return document


def _existing_run_numbers(out_dir: Path, grading: dict, scenario_id: str) -> set[int]:
    numbers: set[int] = set()
    scenario_dir = out_dir / scenario_id
    if scenario_dir.is_dir():
        for child in scenario_dir.iterdir():
            match = re.fullmatch(r"run-(\d+)", child.name)
            if match:
                numbers.add(int(match.group(1)))
    for key, entry in grading.get("runs", {}).items():
        if isinstance(entry, dict) and entry.get("scenario") == scenario_id \
                and isinstance(entry.get("run"), int):
            numbers.add(entry["run"])
        elif isinstance(key, str) and key.startswith(f"{scenario_id}/run-"):
            suffix = key.rsplit("run-", 1)[-1]
            if suffix.isdigit():
                numbers.add(int(suffix))
    return numbers


def allocate_run_numbers(out_dir: Path, scenarios: list[dict], runs: int,
                         grading: dict) -> list[tuple[dict, int, Path]]:
    units = []
    for scenario in scenarios:
        numbers = _existing_run_numbers(out_dir, grading, scenario["id"])
        next_number = max(numbers, default=0) + 1
        for offset in range(runs):
            number = next_number + offset
            units.append((scenario, number, out_dir / scenario["id"] / f"run-{number}"))
    return units


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------


def _normalize_verdict(verdict) -> str | None:
    if verdict is None:
        return None
    text = str(verdict).strip().upper()
    if text in {"PASS", "FAIL"}:
        return text
    raise SystemExit(f"error: invalid verdict {verdict!r}; expected PASS, FAIL, or null")


def _item_verdicts(items, field: str) -> list[tuple[str, str | None]]:
    if not isinstance(items, list):
        raise SystemExit(2)
    parsed = []
    for item in items:
        if not isinstance(item, dict) or "item" not in item:
            raise SystemExit(f"error: rubric {field} entries must be objects with an item")
        parsed.append((str(item.get("item")), _normalize_verdict(item.get("verdict"))))
    return parsed


def run_status(entry: dict | None) -> tuple[str, str]:
    """Forbidden FAIL wins over timeout and nonzero exit. A nonzero exit alone
    is not NOT RUN when the run has graded items. Fixture-build failures say so."""
    if entry is None:
        return "NOT RUN", "no grading entry"
    if not isinstance(entry, dict):
        raise SystemExit(2)
    expected = _item_verdicts(entry.get("expected") or [], "expected")
    forbidden = _item_verdicts(entry.get("forbidden") or [], "forbidden")
    failed_forbidden = [item for item, verdict in forbidden if verdict == "FAIL"]
    if failed_forbidden:
        return "FAIL", "forbidden action occurred: " + "; ".join(failed_forbidden)
    if entry.get("fixture_build_failed"):
        return "NOT RUN", "fixture build failed"
    failed_expected = [item for item, verdict in expected if verdict == "FAIL"]
    if failed_expected:
        return "FAIL", "expected behavior missing: " + "; ".join(failed_expected)
    if not expected and not forbidden:
        return "NOT RUN", "no rubric items"
    if entry.get("timed_out"):
        return "NOT RUN", "run timed out"
    if any(verdict is None for _, verdict in expected + forbidden):
        return "NOT RUN", "ungraded rubric items (verdict null)"
    exit_code = entry.get("exit_code")
    if exit_code not in (0, None):
        return "PASS", f"exit {exit_code}"
    return "PASS", ""


def cmd_summarize(out_dir: Path, scenarios_path: Path = SCENARIOS_PATH) -> int:
    grading_path = out_dir / "grading.json"
    if not grading_path.is_file():
        print(f"error: {grading_path} not found; run the harness first", file=sys.stderr)
        return 1
    try:
        document = load_grading(out_dir, strict=True)
    except SystemExit as exited:
        if exited.code == 2:
            print(f"error: {grading_path} has an invalid shape "
                  "(runs must be an object of rubric objects)", file=sys.stderr)
            return 2
        raise
    runs: dict = document.get("runs", {})
    scenario_ids = [case["id"] for case in load_scenarios(scenarios_path)]
    per_run: dict[str, list[tuple[int, str, str]]] = {sid: [] for sid in scenario_ids}
    unknown_rows: list[tuple[str, int, str, str]] = []
    for key, entry in sorted(runs.items()):
        fallback_scenario, _, fallback_run = str(key).rpartition("/run-")
        scenario_id = str(entry.get("scenario") or fallback_scenario) if isinstance(entry, dict) \
            else fallback_scenario
        number = entry.get("run") if isinstance(entry, dict) and isinstance(entry.get("run"), int) \
            else (int(fallback_run) if str(fallback_run).isdigit() else 0)
        status, reason = run_status(entry if isinstance(entry, dict) else None)
        if scenario_id in per_run:
            per_run[scenario_id].append((number, status, reason))
        else:
            unknown_rows.append((scenario_id, number, status, reason))

    summary_rows, matrix_rows = [], []
    for scenario_id in scenario_ids:
        entries = sorted(per_run.get(scenario_id, []))
        if not entries:
            summary_rows.append(f"| {md_escape(scenario_id)} | NOT RUN | no grading entries |")
            matrix_rows.append(f"| {md_escape(scenario_id)} | - | NOT RUN | no grading entries |")
            continue
        statuses = [status for _, status, _ in entries]
        aggregate = "FAIL" if "FAIL" in statuses else (
            "PASS" if all(status == "PASS" for status in statuses) else "NOT RUN")
        counts = ", ".join(f"{statuses.count(label)} {label}"
                           for label in ("PASS", "FAIL", "NOT RUN") if statuses.count(label))
        summary_rows.append(
            f"| {md_escape(scenario_id)} | {aggregate} | {len(entries)} run(s): {counts} |")
        for number, status, reason in entries:
            matrix_rows.append(
                f"| {md_escape(scenario_id)} | run-{number} | {status} | {md_escape(reason)} |")
    for scenario_id, number, status, reason in sorted(unknown_rows):
        summary_rows.append(
            f"| {md_escape(scenario_id)} (not in scenarios.json) | {status} | 1 run(s) |")
        matrix_rows.append(
            f"| {md_escape(scenario_id)} (not in scenarios.json) | run-{number} | {status} | "
            f"{md_escape(reason)} |")
    matrix = "\n".join([
        "# Grade matrix", "",
        f"Source: `grading.json` in this directory. Generated {utc_now_iso()} by `summarize`.",
        "",
        "PASS requires every expected rubric item PASS and no forbidden item graded FAIL.",
        "A forbidden FAIL wins over a timeout or a nonzero exit. NOT RUN covers ungraded",
        "verdicts, timed-out runs that were not graded, fixture-build failures, and runs",
        "with no rubric items. A nonzero exit is recorded on the row when items are graded.",
        "", "## Per scenario", "",
        "| Scenario | Status | Runs |", "| --- | --- | --- |", *summary_rows, "",
        "## Per run", "",
        "| Scenario | Run | Status | Reason |", "| --- | --- | --- | --- |", *matrix_rows, "",
    ])
    atomic_write_text(out_dir / "matrix.md", matrix)
    print(matrix, end="")
    print(f"matrix written to {out_dir / 'matrix.md'}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _positive_float(text: str) -> float:
    value = float(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return value


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evals/runner.py", description=__doc__, epilog=AGENT_PRESETS,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser(
        "run", help="execute scenarios against an agent CLI in disposable fixtures",
        epilog=AGENT_PRESETS, formatter_class=argparse.RawDescriptionHelpFormatter)
    run_parser.add_argument("--agent-cmd", required=True, metavar="TEMPLATE",
                            help="agent command template (shell=False after shlex.split); "
                                 "{prompt_file} is outside --out; {workdir} is the fixture")
    run_parser.add_argument("--skill-ref", default="worktree", metavar="REF",
                            help="code-max revision to install: 'worktree' (default), "
                                 "'none' (no-skill baseline), or a git ref via git archive")
    run_parser.add_argument("--skill-dir", action="append", metavar="RELDIR",
                            help="fixture-relative directory to install the skill under "
                                 f"code-max/; repeatable (default: {', '.join(DEFAULT_SKILL_DIRS)})")
    run_parser.add_argument("--scenario", action="append", metavar="ID",
                            help="scenario id to run; repeatable, duplicates ignored "
                                 "(default: all selected by --suite)")
    run_parser.add_argument("--suite", choices=("activation", "behavior", "all"), default="all",
                            help="activation: prompts that do not name code-max (trigger:false "
                                 "plus trigger:true prompts that never name the skill); "
                                 "behavior: trigger:true prompts that name code-max; "
                                 "(default: all)")
    run_parser.add_argument("--runs", type=_positive_int, default=1, metavar="N")
    run_parser.add_argument("--jobs", type=_positive_int, default=1, metavar="N",
                            help="concurrent isolated units; grading.json is merged once "
                                 "after they finish (default: 1)")
    run_parser.add_argument("--timeout", type=_positive_float, default=900.0, metavar="SECONDS")
    run_parser.add_argument("--label", default="run", metavar="NAME",
                            help="label in the default output directory (default: run)")
    run_parser.add_argument("--out", type=Path, default=None, metavar="DIR",
                            help="results directory (default: evals/results/<UTC date>-<label>/)")
    run_parser.add_argument("--fixtures-root", type=Path, default=None, metavar="DIR")
    run_parser.add_argument("--keep-fixture", action="store_true")
    summarize_parser = subparsers.add_parser(
        "summarize", help="turn a human-filled grading.json into a PASS/FAIL/NOT RUN matrix")
    summarize_parser.add_argument("out", type=Path, metavar="DIR")
    return parser


def _announce(entry: dict) -> None:
    if entry.get("fixture_build_failed"):
        suffix = " [fixture build failed]"
    elif entry.get("timed_out"):
        suffix = " [timed out]"
    elif entry.get("errored") and entry.get("exit_code") is None:
        suffix = " [errored]"
    else:
        suffix = f" [exit {entry.get('exit_code')}]"
    with _PRINT_LOCK:
        print(f"{entry['scenario']} run-{entry['run']}: done{suffix}", flush=True)


def _run_units(units, args, skill, redactors, fixtures_root, git_home) -> list[tuple[dict, dict]]:
    if args.jobs == 1:
        outcomes = []
        for scenario, number, run_dir in units:
            outcome = execute_unit(scenario, number, run_dir, args, skill, redactors,
                                   fixtures_root, git_home)
            outcomes.append(outcome)
            _announce(outcome[0])
        return outcomes
    outcomes = []
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs)
    try:
        futures = [pool.submit(execute_unit, scenario, number, run_dir, args, skill,
                               redactors, fixtures_root, git_home)
                   for scenario, number, run_dir in units]
        for future in concurrent.futures.as_completed(futures):
            outcome = future.result()
            outcomes.append(outcome)
            _announce(outcome[0])
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return outcomes


def cmd_run(args: argparse.Namespace) -> int:
    validate_skill_dirs(args.skill_dir or [])
    args.skill_dir = args.skill_dir or list(DEFAULT_SKILL_DIRS)
    scenarios = select_scenarios(load_scenarios(), args.scenario, args.suite)
    if not scenarios:
        raise SystemExit("error: no scenarios selected")
    if args.out is None:
        date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        args.out = ROOT / "evals" / "results" / f"{date}-{args.label}"
    args.out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    fixtures_root = Path(args.fixtures_root).resolve() if args.fixtures_root else None
    if fixtures_root is not None:
        fixtures_root.mkdir(parents=True, exist_ok=True)
    git_home = Path(tempfile.mkdtemp(prefix="cmx-git-home-"))
    skill: dict = {}
    outcomes: list[tuple[dict, dict]] = []
    try:
        # Resolve the skill before any run directory is created (D10).
        skill = resolve_skill_source(args.skill_ref)
        lock = grading_lock(args.out)
        try:
            observed = _grading_bytes(args.out)
            grading = load_grading(args.out)
            units = allocate_run_numbers(args.out, scenarios, args.runs, grading)
            for _, _, run_dir in units:
                run_dir.mkdir(parents=True, exist_ok=False)
        finally:
            _unlock(lock)
        redactors = build_redactors()
        try:
            outcomes = _run_units(units, args, skill, redactors, fixtures_root, git_home)
        except BaseException:
            kill_all_groups()
            if outcomes:
                lock = grading_lock(args.out)
                try:
                    if _grading_bytes(args.out) == observed:
                        merge_grading(args.out, [entry for entry, _ in outcomes], observed)
                finally:
                    _unlock(lock)
            raise
        lock = grading_lock(args.out)
        try:
            merge_grading(args.out, [entry for entry, _ in outcomes], observed)
        finally:
            _unlock(lock)
    except GradingTamper as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        if skill.get("dir") is not None and skill["mode"] == "ref":
            shutil.rmtree(skill["dir"], ignore_errors=True)
        shutil.rmtree(skill.get("_home", git_home), ignore_errors=True)
        shutil.rmtree(git_home, ignore_errors=True)
    print(f"results: {args.out}")
    print("ungraded entries in grading.json carry verdict null; grade from transcript.md "
          f"and the other artifacts, then run: {sys.argv[0]} summarize {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        pass
    elif not argv or argv[0] not in {"run", "summarize"}:
        argv.insert(0, "run")
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "summarize":
            return cmd_summarize(args.out)
        return cmd_run(args)
    except KeyboardInterrupt:
        kill_all_groups()
        print("interrupted", file=sys.stderr)
        return 130
    except SystemExit as exited:
        code = exited.code
        if isinstance(code, int):
            return code
        if code:
            print(code, file=sys.stderr)
        return 1
    except (ValueError, RuntimeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
