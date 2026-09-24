#!/usr/bin/env python3
"""Install code-max links without overwriting user-owned filesystem entries."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from skill_meta import ValidationError, read_metadata

# Presets are conveniences, not host detection or a compatibility guarantee.
TARGETS = {
    "claude": ".claude/skills",
    "codex": ".agents/skills",
    "cursor": ".cursor/skills",
    "gemini": ".gemini/skills",
    "pi": ".pi/agent/skills",
    "opencode": ".config/opencode/skills",
}


def absolute(value: str) -> Path:
    if not value or not Path(value).is_absolute():
        raise ValidationError(f"expected an absolute path, got {value!r}")
    return Path(value)


def target_paths(agents: list[str], custom: list[str]) -> list[Path]:
    paths = [absolute(value) for value in custom]
    if agents:
        home = absolute(os.environ.get("HOME", ""))
        for agent in agents:
            if agent == "opencode" and os.environ.get("XDG_CONFIG_HOME"):
                paths.append(absolute(os.environ["XDG_CONFIG_HOME"]) / "opencode/skills")
            else:
                paths.append(home / TARGETS[agent])
    # Resolve parents only: resolving the final skill link would hide conflicts.
    return list(dict.fromkeys(path.resolve() for path in paths))


def owned_link(path: Path, source: Path) -> bool:
    return path.is_symlink() and path.resolve() == source


def foreign(path: Path, source: Path) -> bool:
    # lexists includes dangling links, which must never be overwritten or removed.
    return os.path.lexists(path) and not owned_link(path, source)


def check_destination(path: Path, source: Path) -> None:
    if foreign(path, source):
        raise ValidationError(f"conflict: {path}; preserve it and choose another target")
    parent = path.parent
    while not os.path.lexists(parent):
        parent = parent.parent
    if not parent.is_dir():
        raise ValidationError(f"target ancestor is not a directory: {parent}")


def install(source: Path, targets: list[Path], *, dry_run: bool, uninstall: bool) -> list[Path]:
    """Return entries skipped by uninstall because this checkout does not own them."""
    name = read_metadata(source / "SKILL.md")["name"]
    if name != "code-max":
        raise ValidationError("this installer requires the code-max skill")
    destinations = [parent / name for parent in targets]
    selected = set(destinations)
    for destination in destinations:
        if any(parent in selected for parent in destination.parents):
            raise ValidationError(f"overlapping destinations: {destination}")
        # Installing inside the source creates a recursive skill tree.
        if destination == source or source in destination.parents:
            raise ValidationError(f"target is inside the skill source: {destination}")
        if not uninstall:
            check_destination(destination, source)
    skipped = []
    for destination in destinations:
        if uninstall and foreign(destination, source):
            # Uninstall never deletes a foreign entry, but owned links elsewhere still go.
            print(f"conflict: {destination} is not a link to this checkout; left in place", file=sys.stderr, flush=True)
            skipped.append(destination)
            continue
        # Recheck immediately before mutation; symlink creation itself is exclusive.
        check_destination(destination, source)
        linked = owned_link(destination, source)
        if uninstall:
            if linked:
                if not dry_run:
                    destination.unlink()
                print(f"{'would remove' if dry_run else 'removed'}: {destination}", flush=True)
            else:
                print(f"absent: {destination}", flush=True)
        elif linked:
            print(f"unchanged: {destination}", flush=True)
        elif dry_run:
            print(f"would link: {destination} -> {source}", flush=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Unlike ln -sfn, this cannot replace a file or nest inside a directory.
            destination.symlink_to(source, target_is_directory=True)
            print(f"linked: {destination} -> {source}", flush=True)
    return skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", action="append", choices=sorted(TARGETS), default=[])
    parser.add_argument("--target", action="append", default=[], metavar="ABSOLUTE_SKILLS_DIR")
    parser.add_argument("--all", action="store_true", help="select every preset explicitly")
    parser.add_argument("--list", action="store_true", help="print preset names and relative paths")
    parser.add_argument("--dry-run", action="store_true", help="validate and print without writes")
    parser.add_argument("--uninstall", action="store_true", help="remove only links to this checkout")
    args = parser.parse_args(argv)
    if args.list:
        if args.agent or args.target or args.all or args.dry_run or args.uninstall:
            parser.error("--list cannot be combined with other options")
        for agent, path in TARGETS.items():
            print(f"{agent}: ~/{path}")
        return 0
    if args.all and args.agent:
        parser.error("use --all or --agent, not both")
    if not (args.all or args.agent or args.target):
        parser.error("select --agent, --target, or --all; no files were changed")
    try:
        targets = target_paths(list(TARGETS) if args.all else args.agent, args.target)
        skipped = install(Path(__file__).resolve().parents[1], targets,
                          dry_run=args.dry_run, uninstall=args.uninstall)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}\nNo conflicting entry was replaced. Earlier reported operations may have completed; inspect before retrying.", file=sys.stderr)
        return 1
    if skipped:
        print(f"error: {len(skipped)} foreign entr{'y' if len(skipped) == 1 else 'ies'} preserved; "
              "inspect and remove manually only if you own them.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
