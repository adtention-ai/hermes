import importlib.util
from pathlib import Path


def test_plugin_yaml_has_required_fields():
    text = Path("plugin.yaml").read_text()
    assert "manifest_version: 1" in text
    assert "name: adtention" in text
    assert "pre_gateway_dispatch" in text


def test_root_init_exports_register():
    spec = importlib.util.spec_from_file_location("adtention_plugin_root", Path("__init__.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.register)


def test_after_install_mentions_gateway_restart():
    text = Path("after-install.md").read_text()
    assert "hermes gateway restart" in text
    assert "/adtention status" in text


def test_readme_documents_privacy_and_install():
    text = Path("README.md").read_text()
    assert "hermes plugins install adtention-ai/hermes --enable" in text
    assert "never sends prompts" in text.lower()
    assert "wait-state sponsor line" in text.lower()


def test_ci_workflow_runs_pytest():
    text = Path(".github/workflows/ci.yml").read_text()
    assert "pytest" in text
    assert "compileall" in text
