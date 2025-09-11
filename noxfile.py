"""nox build configuration for Safir."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import nox
from nox.command import CommandFailed
from nox_uv import session

# Default sessions
nox.options.sessions = ["lint", "typing", "test", "docs", "docs-linkcheck"]

# Other nox defaults
nox.options.default_venv_backend = "uv"
nox.options.reuse_existing_virtualenvs = True

# Extras to include for most actions. This should be all of the extras from
# the top-level pyproject.toml.
_EXTRAS = [
    "arq",
    "db",
    "gcs",
    "kafka",
    "kubernetes",
    "redis",
    "testcontainers",
    "uws",
]


@session(uv_groups=["dev", "docs"], uv_extras=_EXTRAS)
def docs(session: nox.Session) -> None:
    """Build the documentation."""
    doctree_dir = (session.cache_dir / "doctrees").absolute()
    with session.chdir("docs"):
        session.run(
            "sphinx-build",
            "-W",
            "--keep-going",
            "-n",
            "-T",
            "-b",
            "html",
            "-d",
            str(doctree_dir),
            ".",
            "./_build/html",
        )


@session(name="docs-clean", uv_groups=["dev", "docs"], uv_extras=_EXTRAS)
def docs_clean(session: nox.Session) -> None:
    """Build the documentation without any cache."""
    if Path("docs/_build").exists():
        shutil.rmtree("docs/_build")
    if Path("docs/api").exists():
        shutil.rmtree("docs/api")
    docs(session)


@session(name="docs-linkcheck", uv_groups=["dev", "docs"], uv_extras=_EXTRAS)
def docs_linkcheck(session: nox.Session) -> None:
    """Check links in the documentation."""
    doctree_dir = (session.cache_dir / "doctrees").absolute()
    with session.chdir("docs"):
        try:
            session.run(
                "sphinx-build",
                "-W",
                "--keep-going",
                "-n",
                "-T",
                "-b",
                "linkcheck",
                "-d",
                str(doctree_dir),
                ".",
                "./_build/linkcheck",
            )
        except CommandFailed:
            output_path = Path("_build") / "linkcheck" / "output.txt"
            if output_path.exists():
                sys.stdout.write(output_path.read_text())
            session.error("Link check reported errors")


@session(uv_only_groups=["lint"], uv_no_install_project=True)
def lint(session: nox.Session) -> None:
    """Run pre-commit hooks."""
    session.run("pre-commit", "run", "--all-files", *session.posargs)


@session(uv_groups=["dev"], uv_extras=_EXTRAS)
def test(session: nox.Session) -> None:
    """Run the test suite."""
    session.run("pytest", *session.posargs)


@session(uv_groups=["dev", "typing"], uv_extras=_EXTRAS)
def typing(session: nox.Session) -> None:
    """Check type annotations with mypy."""
    session.run(
        "mypy",
        *session.posargs,
        "--namespace-packages",
        "--explicit-package-bases",
        "noxfile.py",
        "safir-arq/src",
        "safir-logging/src",
        "src",
        "tests",
        env={"MYPYPATH": "safir-arq/src:safir-logging/src:src"},
    )
