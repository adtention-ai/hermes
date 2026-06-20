import importlib.util
import shutil
import sys
import types
from pathlib import Path


def test_directory_plugin_loads_like_hermes_namespace_package(tmp_path, monkeypatch):
    """Hermes imports directory plugins as hermes_plugins.<slug>.

    The plugin root must use package-relative imports, because the plugin
    directory itself is not added to sys.path by Hermes' loader.
    """
    source = Path.cwd()
    plugin_dir = tmp_path / "adtention"
    shutil.copytree(
        source,
        plugin_dir,
        ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", "*.pyc"),
    )

    # Hide the repo checkout from normal absolute imports so this catches the
    # exact failure users would hit after `hermes plugins install owner/repo`.
    hidden_paths = {str(source), ""}
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p not in hidden_paths])
    for name in list(sys.modules):
        if name == "adtention_hermes" or name.startswith("adtention_hermes."):
            sys.modules.pop(name)

    ns_pkg = types.ModuleType("hermes_plugins")
    ns_pkg.__path__ = []
    ns_pkg.__package__ = "hermes_plugins"
    monkeypatch.setitem(sys.modules, "hermes_plugins", ns_pkg)

    module_name = "hermes_plugins.adtention"
    spec = importlib.util.spec_from_file_location(
        module_name,
        plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module.__package__ = module_name
    module.__path__ = [str(plugin_dir)]
    monkeypatch.setitem(sys.modules, module_name, module)

    spec.loader.exec_module(module)

    assert callable(module.register)
