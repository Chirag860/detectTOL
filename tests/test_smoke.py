"""Phase 0 smoke test: the package imports and reports a version."""

import detecttol


def test_package_imports_and_has_version() -> None:
    assert isinstance(detecttol.__version__, str)
    assert detecttol.__version__
    assert callable(detecttol.analyze)
