import importlib.util
import re
import tomllib
from pathlib import Path


def test_plugin_yaml_has_required_fields():
    text = Path("plugin.yaml").read_text()
    assert "manifest_version: 1" in text
    assert "name: adtention" in text
    assert "pre_gateway_dispatch" in text
    assert "install_options:" in text
    assert "name: referral" in text
    assert "env: ADTENTION_REFERRER" in text


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
    assert "--referral h3r7vmj" in text
    assert "never sends prompts" in text.lower()
    assert "wait-state sponsor line" in text.lower()


def test_ci_workflow_runs_pytest():
    text = Path(".github/workflows/ci.yml").read_text()
    assert "pytest" in text
    assert "compileall" in text


def test_release_workflow_builds_and_publishes_github_release():
    text = Path(".github/workflows/release.yml").read_text()
    assert "branches:" in text
    assert "- main" in text
    assert "v*.*.*" in text
    assert "Create release tag for main merge" in text
    assert "git tag -a" in text
    assert "Bump pyproject.toml" in text
    assert "python -m build" in text
    assert "scripts/extract_changelog.py" in text
    assert "--notes-file release-notes.md" in text
    assert "gh release edit" in text
    assert "gh release create" in text
    assert "pyproject.toml version" in text
    assert "plugin.yaml version" in text
    assert "DISPATCH_TAG" in text
    assert "--generate-notes" not in text
    assert 'tag="${{ inputs.tag }}"' not in text


def test_changelog_has_curated_notes_for_current_version():
    project = tomllib.loads(Path("pyproject.toml").read_text())
    version = project["project"]["version"]
    plugin_yaml = Path("plugin.yaml").read_text()
    assert f'version: "{version}"' in plugin_yaml

    changelog = Path("CHANGELOG.md").read_text()
    match = re.search(
        rf"^## \[{re.escape(version)}\].*?\n(?P<body>.*?)(?=^## \[|\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"CHANGELOG.md needs a release-note section for {version}"
    body = match.group("body")
    assert "hermes plugins install adtention-ai/hermes --enable" in body
    assert "never sends prompts" in body.lower()
    assert "telegram/discord" in body.lower()
    assert "release verification" in body.lower()
