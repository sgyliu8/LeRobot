from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_excludes_generated_frontend_from_source_inventory() -> None:
    script = (ROOT / "tools" / "bootstrap_upstream.ps1").read_text(encoding="utf-8")

    assert "$currentPath.StartsWith('frontend/dist/'" in script
    assert "npm run build --prefix $frontendRoot" in script


def _git_fixture(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def _check_inventory(repo: Path, patch: Path) -> subprocess.CompletedProcess[str]:
    # Load only this function through PowerShell's parser: no bootstrap, npm,
    # network, production job discovery or device construction may execute.
    environment = os.environ.copy()
    environment.update(
        LELAB_TEST_SCRIPT=str(ROOT / "tools" / "bootstrap_upstream.ps1"),
        LELAB_TEST_VENDOR=str(repo),
        LELAB_TEST_PATCH=str(patch),
    )
    return subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-Command",
            """
            Set-StrictMode -Version Latest
            $ErrorActionPreference = 'Stop'
            $tokens = $null
            $errors = $null
            $ast = [System.Management.Automation.Language.Parser]::ParseFile(
                $env:LELAB_TEST_SCRIPT, [ref]$tokens, [ref]$errors)
            if ($errors.Count) { throw 'Invalid PowerShell source' }
            $function = $ast.Find({ param($node)
                $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                $node.Name -eq 'Assert-ExactPatchedSource'
            }, $true)
            Invoke-Expression $function.Extent.Text
            $vendorRoot = $env:LELAB_TEST_VENDOR
            $patchPath = $env:LELAB_TEST_PATCH
            Assert-ExactPatchedSource
            Write-Output 'INVENTORY_PASS'
            """,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


@pytest.mark.parametrize("edited", [False, True])
@pytest.mark.parametrize("mutation", ["staged", "unstaged", "changed", "missing", "extra", "old_restored"])
def test_bootstrap_checks_real_git_renames(tmp_path: Path, edited: bool, mutation: str) -> None:
    repo = tmp_path / "vendor fixture"
    repo.mkdir()
    _git_fixture(repo, "init")
    original = repo / "original.ts"
    renamed = repo / "renamed provider.ts"
    content = "".join(f"export const value{i} = {i};\n" for i in range(20))
    original.write_text(content, encoding="utf-8")
    _git_fixture(repo, "add", "original.ts")
    _git_fixture(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-m", "Synthetic upstream")
    original.rename(renamed)
    if edited:
        renamed.write_text(content.replace("value0 = 0", "value0 = 100"), encoding="utf-8")
    _git_fixture(repo, "add", "-A")
    patch = tmp_path / "fixture.patch"
    patch_text = _git_fixture(repo, "diff", "--cached", "--binary", "--full-index", "--find-renames", "HEAD")
    assert "rename from original.ts" in patch_text
    assert any(line.startswith("index ") for line in patch_text.splitlines()) is edited
    patch.write_text(patch_text, encoding="utf-8")
    if mutation != "staged":
        _git_fixture(repo, "read-tree", "HEAD")  # Restore fixture index only; keep patched files.
    if mutation == "changed":
        renamed.write_text("unexpected content\n", encoding="utf-8")
    elif mutation == "missing":
        renamed.unlink()
    elif mutation == "extra":
        (repo / "unreviewed.ts").write_text("extra\n", encoding="utf-8")
    elif mutation == "old_restored":
        original.write_text(content, encoding="utf-8")

    result = _check_inventory(repo, patch)
    if mutation in {"staged", "unstaged"}:
        assert result.returncode == 0, result.stderr
        assert "INVENTORY_PASS" in result.stdout
    else:
        assert result.returncode != 0
        assert "INVENTORY_PASS" not in result.stdout


def _make_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        pass
    environment = os.environ.copy()
    environment["LELAB_TEST_LINK"] = str(link)
    environment["LELAB_TEST_TARGET"] = str(target)
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                "New-Item -ItemType Junction -Path $env:LELAB_TEST_LINK "
                "-Target $env:LELAB_TEST_TARGET | Out-Null"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode != 0:
        pytest.skip(f"directory link unavailable: {result.stderr}")


def test_bootstrap_rejects_reparse_in_manifest_path(tmp_path: Path) -> None:
    project = tmp_path / "project"
    tools = project / "tools"
    external = tmp_path / "external-config"
    tools.mkdir(parents=True)
    external.mkdir()
    shutil.copy2(ROOT / "tools" / "bootstrap_upstream.ps1", tools / "bootstrap_upstream.ps1")
    (external / "upstream-pins.json").write_text("{}", encoding="utf-8")
    _make_directory_link(project / "configs", external)

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tools / "bootstrap_upstream.ps1"),
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "reparse point" in result.stderr
    assert "Unable to read the authoritative upstream pin manifest" not in result.stderr
