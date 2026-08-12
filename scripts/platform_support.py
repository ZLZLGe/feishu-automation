#!/usr/bin/env python3
"""Cross-platform paths and private-file protection for Feishu Automation."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path


class PrivateFileError(RuntimeError):
    """Raised when a credential file is missing or insufficiently protected."""


def venv_python_path(root: Path, platform_name: str | None = None) -> Path:
    """Return the Python executable created by venv on the requested platform."""
    platform_name = platform_name or os.name
    if platform_name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def secure_private_file(path: Path, platform_name: str | None = None) -> None:
    """Limit a credential file to the current user."""
    path = path.expanduser().resolve()
    if not path.is_file():
        raise PrivateFileError(f"Private file does not exist: {path}")

    platform_name = platform_name or os.name
    if platform_name == "nt":
        _set_windows_private_acl(path)
        return
    os.chmod(path, 0o600)


def require_private_file(path: Path, platform_name: str | None = None) -> None:
    """Reject a credential file that other local users can read."""
    path = path.expanduser().resolve()
    if not path.is_file():
        raise PrivateFileError(f"Private file does not exist: {path}")

    platform_name = platform_name or os.name
    if platform_name == "nt":
        _verify_windows_private_acl(path)
        return

    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PrivateFileError(f"Private file must have permission 600: {path}")


def _powershell_executable() -> str:
    executable = (
        shutil.which("pwsh.exe")
        or shutil.which("pwsh")
        or shutil.which("powershell.exe")
        or shutil.which("powershell")
    )
    if not executable:
        raise PrivateFileError(
            "PowerShell is required to protect the Feishu credential file on Windows."
        )
    return executable


def _run_powershell_acl_script(path: Path, script: str) -> None:
    environment = os.environ.copy()
    environment["FEISHU_AUTOMATION_PRIVATE_FILE"] = str(path)
    result = subprocess.run(
        [
            _powershell_executable(),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        suffix = f": {detail}" if detail else ""
        raise PrivateFileError(f"Unable to protect private file {path}{suffix}")


def _set_windows_private_acl(path: Path) -> None:
    script = r"""
$ErrorActionPreference = "Stop"
$target = $env:FEISHU_AUTOMATION_PRIVATE_FILE
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetOwner($identity.User)
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $identity.User,
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    [System.Security.AccessControl.AccessControlType]::Allow
)
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $target -AclObject $acl
"""
    _run_powershell_acl_script(path, script)


def _verify_windows_private_acl(path: Path) -> None:
    script = r"""
$ErrorActionPreference = "Stop"
$target = $env:FEISHU_AUTOMATION_PRIVATE_FILE
$acl = Get-Acl -LiteralPath $target
$currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
if (-not $acl.AreAccessRulesProtected) { exit 10 }
$hasCurrentFullControl = $false
foreach ($rule in $acl.Access) {
    $sid = $rule.IdentityReference.Translate(
        [System.Security.Principal.SecurityIdentifier]
    ).Value
    if ($rule.IsInherited) { exit 11 }
    if ($rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) {
        exit 12
    }
    if ($sid -ne $currentSid) { exit 13 }
    $full = [System.Security.AccessControl.FileSystemRights]::FullControl
    if (($rule.FileSystemRights -band $full) -eq $full) {
        $hasCurrentFullControl = $true
    }
}
if (-not $hasCurrentFullControl) { exit 14 }
"""
    try:
        _run_powershell_acl_script(path, script)
    except PrivateFileError as error:
        raise PrivateFileError(
            f"Private file ACL must grant access only to the current Windows user: {path}"
        ) from error
