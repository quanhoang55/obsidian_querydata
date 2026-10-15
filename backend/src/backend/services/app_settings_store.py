"""Persist editable app settings and Gemini credentials for desktop use."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


APP_NAME = "ObsidianQuery"
KEYCHAIN_SERVICE = "ObsidianQuery Gemini API Key"


class SettingsStorageError(RuntimeError):
    """The operating system could not store or retrieve app settings."""


def settings_file() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME / "settings.json"


def read_preferences() -> dict[str, Any]:
    path = settings_file()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        raise SettingsStorageError("Could not read saved app settings") from error
    return value if isinstance(value, dict) else {}


def write_preferences(values: dict[str, Any]) -> None:
    path = settings_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(path)
        if os.name != "nt":
            path.chmod(0o600)
    except OSError as error:
        raise SettingsStorageError("Could not save app settings") from error


def get_api_key() -> str:
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", APP_NAME, "-w"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SettingsStorageError("Could not access macOS Keychain") from error
        if result.returncode == 44:
            return ""
        if result.returncode:
            raise SettingsStorageError("Could not access macOS Keychain")
        return result.stdout.rstrip("\r\n")
    if os.name == "nt":
        return _windows_read_secret()
    return ""


def set_api_key(value: str | None) -> None:
    if sys.platform == "darwin":
        if value:
            command = ["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", APP_NAME, "-w", value]
        else:
            command = ["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", APP_NAME]
        try:
            result = subprocess.run(command, check=False, capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SettingsStorageError("Could not access macOS Keychain") from error
        if result.returncode and value:
            raise SettingsStorageError("Could not save the Gemini API key in macOS Keychain")
        if result.returncode and not value and b"could not be found" not in result.stderr.lower():
            raise SettingsStorageError("Could not remove the Gemini API key from macOS Keychain")
        return
    if os.name == "nt":
        _windows_write_secret(value)
        return
    raise SettingsStorageError("Secure API key storage is supported on macOS and Windows")


def _windows_read_secret() -> str:
    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", ctypes.c_uint32), ("Type", ctypes.c_uint32), ("TargetName", ctypes.c_wchar_p),
            ("Comment", ctypes.c_wchar_p), ("LastWritten", FILETIME), ("CredentialBlobSize", ctypes.c_uint32),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", ctypes.c_uint32),
            ("AttributeCount", ctypes.c_uint32), ("Attributes", ctypes.c_void_p),
            ("TargetAlias", ctypes.c_wchar_p), ("UserName", ctypes.c_wchar_p),
        ]

    advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    credential = ctypes.POINTER(CREDENTIAL)()
    if not advapi.CredReadW(f"{APP_NAME}/Gemini API Key", 1, 0, ctypes.byref(credential)):
        error = ctypes.get_last_error()
        if error == 1168:
            return ""
        raise SettingsStorageError("Could not access Windows Credential Manager")
    try:
        data = ctypes.string_at(credential.contents.CredentialBlob, credential.contents.CredentialBlobSize)
        return data.decode("utf-8")
    finally:
        advapi.CredFree(credential)


def _windows_write_secret(value: str | None) -> None:
    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", ctypes.c_uint32), ("Type", ctypes.c_uint32), ("TargetName", ctypes.c_wchar_p),
            ("Comment", ctypes.c_wchar_p), ("LastWritten", FILETIME), ("CredentialBlobSize", ctypes.c_uint32),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", ctypes.c_uint32),
            ("AttributeCount", ctypes.c_uint32), ("Attributes", ctypes.c_void_p),
            ("TargetAlias", ctypes.c_wchar_p), ("UserName", ctypes.c_wchar_p),
        ]

    advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    target = f"{APP_NAME}/Gemini API Key"
    if not value:
        if not advapi.CredDeleteW(target, 1, 0) and ctypes.get_last_error() != 1168:
            raise SettingsStorageError("Could not remove the Gemini API key from Windows Credential Manager")
        return
    blob = ctypes.create_string_buffer(value.encode("utf-8"))
    credential = CREDENTIAL(
        Flags=0,
        Type=1,
        TargetName=target,
        CredentialBlobSize=len(blob.value),
        CredentialBlob=ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte)),
        Persist=2,
        UserName=APP_NAME,
    )
    if not advapi.CredWriteW(ctypes.byref(credential), 0):
        raise SettingsStorageError("Could not save the Gemini API key in Windows Credential Manager")
