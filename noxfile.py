"""nox build configuration for Safir."""

import shutil
import sys
from pathlib import Path

import nox
from nox.command import CommandFailed

# Default sessions
nox.options.sessions = [
    "lint",
    "typing",
    "test",
    "docs",
    "docs-linkcheck",
]

# Other nox defaults
nox.options.default_venv_backend = "uv"
nox.options.reuse_existing_virtualenvs = True

# pip-installable dependencies for all the Safir modules.
PIP_DEPENDENCIES = (
    ("-e", "./safir-logging"),
    ("-e", "./safir-arq"),
    ("-e", "./safir[arq,db,dev,gcs,kubernetes,redis,uws]"),
)


def _install(session: nox.Session) -> None:
    """Install the application and all dependencies into the session."""
    for deps in PIP_DEPENDENCIES:
        session.install(*deps)


def _install_dev(session: nox.Session, bin_prefix: str = "") -> None:
    """Install the application and dev dependencies into the session."""
    python = f"{bin_prefix}python"
    precommit = f"{bin_prefix}pre-commit"

    # Install dev dependencies
    session.run(python, "-m", "pip", "install", "uv", external=True)
    uv_install = (python, "-m", "uv", "pip", "install")
    session.run(*uv_install, "nox[uv]", "pre-commit", external=True)
    for deps in PIP_DEPENDENCIES:
        session.run(*uv_install, *deps, external=True)

    # Install pre-commit hooks
    session.run(precommit, "install", external=True)


def _pytest(
    session: nox.Session, directory: str, module: str, *, coverage: bool = True
) -> None:
    """Run pytest for the given directory and module, if needed."""
    generic = []
    per_directory = []
    found_per_directory = False
    for arg in session.posargs:
        if arg.startswith("-"):
            generic.append(arg)
        elif arg.startswith(f"{directory}/"):
            per_directory.append(arg.removeprefix(f"{directory}/"))
            found_per_directory = True
        elif "/" in arg and Path(arg).exists():
            found_per_directory = True
        else:
            generic.append(arg)
    if not session.posargs or not found_per_directory or per_directory:
        args = []
        if coverage:
            args.extend([f"--cov={module}", "--cov-branch", "--cov-report="])
        with session.chdir(directory):
            session.run(
                "pytest",
                *args,
                *generic,
                *per_directory,
            )


@nox.session(name="venv-init", venv_backend="virtualenv")
def venv_init(session: nox.Session) -> None:
    """Set up a development venv.

    Create a venv in the current directory, replacing any existing one.
    """
    session.run("python", "-m", "venv", ".venv", "--clear")
    _install_dev(session, bin_prefix=".venv/bin/")

    print(
        "\nTo activate this virtual env, run:\n\n\tsource .venv/bin/activate\n"
    )


@nox.session(name="init", python=False)
def init(session: nox.Session) -> None:
    """Set up the development environment in the current virtual env."""
    _install_dev(session, bin_prefix="")


@nox.session
def lint(session: nox.Session) -> None:
    """Run pre-commit hooks."""
    session.install("--upgrade", "pre-commit")
    session.run("pre-commit", "run", "--all-files", *session.posargs)


@nox.session
def typing(session: nox.Session) -> None:
    """Check type annotations with mypy."""
    _install(session)
    session.run(
        "mypy",
        *session.posargs,
        "--namespace-packages",
        "--explicit-package-bases",
        "noxfile.py",
        "safir/src",
        "safir-arq/src",
        "safir-logging/src",
        "safir/tests",
        env={"MYPYPATH": "safir/src:safir-arq/src:safir-logging/src"},
    )


@nox.session
def test(session: nox.Session) -> None:
    """Run tests of Safir."""
    _install(session)
    _pytest(session, "safir", "safir", coverage=True)


@nox.session
def docs(session: nox.Session) -> None:
    """Build the documentation."""
    _install(session)
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


@nox.session(name="docs-clean")
def docs_clean(session: nox.Session) -> None:
    """Build the documentation without any cache."""
    if Path("docs/_build").exists():
        shutil.rmtree("docs/_build")
    if Path("docs/api").exists():
        shutil.rmtree("docs/api")
    docs(session)


@nox.session(name="docs-linkcheck")
def docs_linkcheck(session: nox.Session) -> None:
    """Check documentation links."""
    _install(session)
    doctree_dir = (session.cache_dir / "doctrees").absolute()
    with session.chdir("docs"):
        try:
            session.run(
                "sphinx-build",
                "-W",
                "--keep-going",
                "-n",
                "-T",
                "-blinkcheck",
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


@nox.session(name="update-deps")
def update_deps(session: nox.Session) -> None:
    """Update pre-commit hooks."""
    session.install("--upgrade", "uv")
    session.run("uv", "pip", "install", "pre-commit")
    session.run("pre-commit", "autoupdate")
