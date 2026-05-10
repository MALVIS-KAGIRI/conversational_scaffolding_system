#!/usr/bin/env python3
"""Diagnose OpenTelemetry/Langfuse configuration without breaking on errors."""

from __future__ import annotations

import os
import platform
import sys


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def _windows_shell_unset(name: str) -> str:
    return f"Remove-Item Env:{name}"


def _posix_shell_unset(name: str) -> str:
    return f"unset {name}"


def _unset_command(name: str) -> str:
    if platform.system().lower().startswith("win"):
        return _windows_shell_unset(name)
    return _posix_shell_unset(name)


otel_vars = {
    key: value
    for key, value in os.environ.items()
    if key.startswith(("OTEL_", "TRACEPARENT", "TRACESTATE"))
}
otel_pkgs = []

_print_header("OpenTelemetry Environment Variables")
if otel_vars:
    for key, value in otel_vars.items():
        print(f"  {key}={value}")
else:
    print("  (none found)")

_print_header("Installed OTEL Packages")
try:
    import pkg_resources

    otel_pkgs = [
        dist for dist in pkg_resources.working_set if dist.project_name.lower().startswith("opentelemetry")
    ]
    if otel_pkgs:
        for pkg in otel_pkgs:
            print(f"  {pkg.project_name}=={pkg.version}")
    else:
        print("  (none found)")
except Exception as exc:
    print(f"  Could not check: {exc}")

_print_header("Python Path")
otel_paths = [path for path in sys.path if "opentelemetry" in path.lower()]
if otel_paths:
    for path in otel_paths:
        print(f"  {path}")
else:
    print("  (no opentelemetry entries found in sys.path)")

_print_header("Langfuse Version")
try:
    import langfuse

    print(f"  langfuse version: {langfuse.__version__}")
except Exception as exc:
    print(f"  Could not import langfuse: {exc}")

_print_header("Recommendations")
if otel_vars:
    print("  Remove these environment variables before starting the server if they are causing conflicts:")
    for key in otel_vars:
        print(f"    {_unset_command(key)}")
else:
    print("  No OTEL environment variables detected.")

if otel_pkgs:
    print("  OTEL packages are installed. Only uninstall them if you have confirmed they are the source of the issue:")
    for pkg in otel_pkgs:
        print(f"    pip uninstall {pkg.project_name} -y")
else:
    print("  No installed OTEL packages detected.")
