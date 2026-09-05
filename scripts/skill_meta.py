"""Read this repository's deliberately small, dependency-free metadata profile."""
from pathlib import Path
import re


class ValidationError(ValueError):
    """An actionable skill-package validation failure."""


def read_metadata(path: Path) -> dict[str, str]:
    """Accept exactly two unquoted, single-line YAML scalars, not general YAML."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValidationError("SKILL.md must start with ---")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValidationError("SKILL.md frontmatter is not closed") from exc
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(": ")
        if not separator or key not in {"name", "description"} or key in fields:
            raise ValidationError("frontmatter requires unique name and description scalars")
        if not value or value != value.strip() or ": " in value or " #" in value or not value.isprintable():
            raise ValidationError(f"invalid plain scalar for {key}")
        fields[key] = value
    if set(fields) != {"name", "description"}:
        raise ValidationError("frontmatter requires name and description")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fields["name"]):
        raise ValidationError("invalid skill name")
    if not 1 <= len(fields["name"]) <= 64:
        raise ValidationError("skill name exceeds 64 characters")
    if not fields["description"].startswith("Use when ") or not 10 <= len(fields["description"]) <= 1024:
        raise ValidationError("description must start with Use when and fit 1024 characters")
    if not any(line.strip() for line in lines[end + 1:]):
        raise ValidationError("SKILL.md body is empty")
    return fields
