from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class MinerUAdapterError(RuntimeError):
    """MinerU could not start or did not produce a successful extraction."""


@dataclass(frozen=True)
class MinerUResult:
    output_dir: Path
    command: tuple[str, ...]
    stdout: str
    stderr: str
    return_code: int


Runner = Callable[..., Any]


class MinerUClient:
    """Thin subprocess adapter that only writes to a caller-provided staging dir."""

    def __init__(
        self,
        command: str | None = None,
        *,
        timeout_seconds: int = 600,
        runner: Runner = subprocess.run,
    ) -> None:
        requested_command = command or os.environ.get("MINERU_CLI_COMMAND", "mineru-open-api")
        self.command = _resolve_command(requested_command)
        self.timeout_seconds = max(1, int(timeout_seconds))
        self._runner = runner

    def available(self) -> bool:
        return bool(shutil.which(self.command))

    def build_command(
        self,
        pdf_path: str | os.PathLike[str],
        output_dir: str | os.PathLike[str],
        *,
        mode: str = "auto",
        language: str = "ch",
        token: str = "",
    ) -> list[str]:
        pdf = Path(pdf_path).expanduser().resolve()
        output = Path(output_dir).expanduser().resolve()
        resolved_token = token or os.environ.get("MINERU_TOKEN") or os.environ.get("MINERU_API_TOKEN") or ""
        resolved_mode = (mode or "auto").strip().lower()
        if resolved_mode == "auto":
            resolved_mode = "extract" if resolved_token or _has_cli_token() else "flash-extract"
        elif resolved_mode == "api":
            resolved_mode = "extract"
        elif resolved_mode == "local":
            resolved_mode = "flash-extract"
        if resolved_mode not in {"extract", "flash-extract"}:
            raise ValueError("MinerU mode must be auto, local, api, extract, or flash-extract")

        args = [self.command, resolved_mode, str(pdf), "-o", str(output)]
        if resolved_mode == "extract":
            args.extend(["-f", "md"])
        if language:
            args.extend(["-l" if resolved_mode == "extract" else "--language", language])
        if resolved_token:
            args.extend(["--token", resolved_token])
        args.extend(["--timeout", str(self.timeout_seconds)])
        return args

    def parse(
        self,
        pdf_path: str | os.PathLike[str],
        output_dir: str | os.PathLike[str],
        *,
        mode: str = "auto",
        language: str = "ch",
        token: str = "",
    ) -> MinerUResult:
        pdf = Path(pdf_path).expanduser().resolve()
        output = Path(output_dir).expanduser().resolve()
        if not pdf.is_file():
            raise FileNotFoundError(f"MinerU source PDF does not exist: {pdf}")
        output.mkdir(parents=True, exist_ok=True)
        command = self.build_command(pdf, output, mode=mode, language=language, token=token)
        try:
            completed = self._runner(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds + 30,
                check=False,
            )
        except Exception as exc:
            raise MinerUAdapterError(f"MinerU failed to start: {exc}") from exc

        result = MinerUResult(
            output_dir=output,
            command=tuple(self._redact(command)),
            stdout=str(completed.stdout or "").strip(),
            stderr=str(completed.stderr or "").strip(),
            return_code=int(completed.returncode),
        )
        if result.return_code != 0:
            detail = result.stderr or result.stdout or "no diagnostic output"
            raise MinerUAdapterError(f"MinerU exited with {result.return_code}: {detail}")
        return result

    @staticmethod
    def _redact(command: Sequence[str]) -> list[str]:
        result = list(command)
        if "--token" in result:
            index = result.index("--token") + 1
            if index < len(result):
                result[index] = "***"
        return result


def _resolve_command(command: str, *, is_windows: bool | None = None) -> str:
    """Prefer a launchable Windows shim over a sibling Unix wrapper."""

    windows = os.name == "nt" if is_windows is None else is_windows
    if not windows or command.lower().endswith((".com", ".exe", ".bat", ".cmd")):
        return command
    for suffix in (".exe", ".com", ".cmd", ".bat"):
        resolved = shutil.which(f"{command}{suffix}")
        if resolved:
            return resolved
    return command


def _has_cli_token(config_path: Path | None = None) -> bool:
    """Return whether ``mineru-open-api auth`` stored a usable token."""

    path = config_path or Path.home() / ".mineru" / "config.yaml"
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return False
    return isinstance(value, dict) and bool(str(value.get("token") or "").strip())
