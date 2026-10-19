"""Packaging and container hygiene guards (issue #29).

A dependency that is only bounded by ``>=`` makes two builds of the same commit
resolve different versions, test tooling in the runtime image bloats it, and a
container that runs as root turns a small escape into a host compromise. These
assertions keep all of that from creeping back in.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PINNED = re.compile(r"^[A-Za-z0-9_.\-]+(\[[^\]]+\])?==[^\s;]+$")


def _requirements_lines(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _dockerfile_instructions() -> list[str]:
    """Return the Dockerfile as logical instructions (continuations joined)."""
    raw = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()

    instructions: list[str] = []
    pending = ""
    for line in raw:
        stripped = line.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        if stripped.startswith("#"):
            continue
        pending = f"{pending} {stripped}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].strip()
            continue
        instructions.append(pending)
        pending = ""
    if pending:
        instructions.append(pending)
    return instructions


def test_runtime_requirements_are_exactly_pinned():
    for requirement in _requirements_lines(ROOT / "requirements.txt"):
        assert requirement.startswith("-r ") is False, requirement
        assert PINNED.match(requirement), f"unpinned runtime dependency: {requirement}"


def test_test_tooling_is_not_installed_in_the_runtime_image():
    names = {
        re.split(r"[=\[]", requirement, maxsplit=1)[0].lower()
        for requirement in _requirements_lines(ROOT / "requirements.txt")
    }

    assert "pytest" not in names
    assert "pytest-asyncio" not in names


def test_dev_requirements_extend_the_runtime_pins():
    dev_lines = _requirements_lines(ROOT / "requirements-dev.txt")

    assert "-r requirements.txt" in dev_lines
    assert any(line.startswith("pytest==") for line in dev_lines)
    assert any(line.startswith("pytest-asyncio==") for line in dev_lines)


def test_dockerfile_installs_only_runtime_requirements():
    instructions = " ".join(_dockerfile_instructions())

    assert "requirements.txt" in instructions
    assert "requirements-dev.txt" not in instructions


def test_dockerfile_runs_as_a_non_root_user():
    instructions = _dockerfile_instructions()

    user_lines = [line for line in instructions if line.upper().startswith("USER ")]
    assert user_lines, "the image must drop root with a USER instruction"
    assert user_lines[-1].split()[1] not in {"root", "0"}


def test_dockerfile_has_a_healthcheck():
    instructions = _dockerfile_instructions()

    assert any(line.upper().startswith("HEALTHCHECK") for line in instructions)
    assert "/health" in " ".join(line for line in instructions if line.upper().startswith("HEALTHCHECK"))


def test_package_index_is_opt_in_instead_of_hard_coded():
    """A third-party index must be a build argument, not baked into the image."""
    instructions = _dockerfile_instructions()

    assert any(line.startswith("ARG PIP_INDEX_URL") for line in instructions)
    pip_install = next(
        line for line in instructions if line.startswith("pip install") or "pip install" in line
    )
    assert '"${PIP_INDEX_URL}"' in pip_install


def test_dockerignore_keeps_the_build_context_small():
    rules = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    for expected in (".git", ".venv", "front/node_modules", "test", "**/__pycache__"):
        assert expected in rules, f".dockerignore must exclude {expected}"


def test_compose_keeps_redis_private_and_waits_for_it():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    # Redis has no password in the compose file, so it must not be published.
    redis_block = compose.split("redis:", 1)[1].split("web:", 1)[0]
    assert '"6379:6379"' not in redis_block
    assert "healthcheck:" in redis_block
    assert "condition: service_healthy" in compose
