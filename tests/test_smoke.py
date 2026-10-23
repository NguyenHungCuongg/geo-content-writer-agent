import importlib

import pytest


@pytest.mark.parametrize("name", ["agent", "evals"])
def test_package_imports(name):
    importlib.import_module(name)
