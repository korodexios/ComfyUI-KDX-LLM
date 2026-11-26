"""pytest plugin (loaded by pytest.ini) for running the suite from the pack root (`uv run pytest`).

The pack root is a ComfyUI package (`__init__.py` with relative imports), so pytest
would treat it as a Python package and import it, which fails outside ComfyUI.
Collect the root as a plain directory instead; the tests load modules themselves.
"""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


@pytest.hookimpl(tryfirst=True)
def pytest_collect_directory(path, parent):
    if Path(path).resolve() == _ROOT:
        return pytest.Dir.from_parent(parent, path=Path(path))
    return None
