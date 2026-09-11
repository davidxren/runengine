from pathlib import Path

import runengine

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runengine_imports_from_src_tree() -> None:
    assert runengine.__file__ is not None
    assert Path(runengine.__file__).resolve() == REPO_ROOT / "src" / "runengine" / "__init__.py"
