#!/usr/bin/env python3
# vim: set fileencoding=utf-8 :
"""
test_get_updates.py — Live integration test for dnfd_client.GetPackages(scope='upgrades').

Connects to the running dnf5daemon over D-Bus (system bus) and retrieves the
list of packages that have an available upgrade.  Results are printed in a
3-column table (name | evr | repo) together with the total count.

Requirements:
  - dnf5daemon must be running (or startable via D-Bus activation)
  - The caller must have permission to read package data (no root needed for reads)

Usage:
    cd /home/angelo/src/manatools
    python -m pytest dnfdragora/test/test_get_updates.py -v
  or simply:
    python dnfdragora/test/test_get_updates.py
"""

import sys
import os
import unittest

# Make sure the source tree is on the path so the local dnfdragora package is
# used instead of (or before) any installed copy.
_SRC = os.path.join(os.path.dirname(__file__), "..")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COL_W_NAME = 40   # width of the Name column
COL_W_EVR  = 30   # width of the EVR column
COL_W_REPO = 25   # width of the Repo column


def _print_header():
    header = (
        f"{'Name':<{COL_W_NAME}}"
        f"{'EVR':<{COL_W_EVR}}"
        f"{'Repo':<{COL_W_REPO}}"
    )
    sep = "-" * (COL_W_NAME + COL_W_EVR + COL_W_REPO)
    print(sep)
    print(header)
    print(sep)


def _print_row(name: str, evr: str, repo: str):
    # Truncate fields that are too wide so the columns stay aligned.
    name = name[:COL_W_NAME - 1] if len(name) >= COL_W_NAME else name
    evr  = evr[:COL_W_EVR  - 1] if len(evr)  >= COL_W_EVR  else evr
    repo = repo[:COL_W_REPO - 1] if len(repo) >= COL_W_REPO else repo
    print(f"{name:<{COL_W_NAME}}{evr:<{COL_W_EVR}}{repo:<{COL_W_REPO}}")


def fetch_upgrades():
    """Connect to dnf5daemon and return the raw list of upgrade package dicts.

    Returns a list of dicts, each containing at least:
      'name', 'evr', 'arch', 'repo_id', 'summary'
    """
    from dnfdragora.dnfd_client import Client

    client = Client()
    try:
        options = {
            "package_attrs": ["name", "evr", "arch", "repo_id", "summary"],
            "scope": "upgrades",
        }
        result = client.GetPackages(options, sync=True)
        # result is a list of dicts after unpack_dbus()
        return result or []
    finally:
        try:
            client.Exit(sync=True)
        except Exception:
            pass


def print_upgrades(packages):
    """Print *packages* in a 3-column table and a summary line."""
    _print_header()
    # Sort alphabetically by name for readability.
    for pkg in sorted(packages, key=lambda p: p.get("name", "").lower()):
        name = pkg.get("name", "")
        evr  = pkg.get("evr",  "")
        repo = pkg.get("repo_id", "")
        _print_row(name, evr, repo)
    sep = "-" * (COL_W_NAME + COL_W_EVR + COL_W_REPO)
    print(sep)
    print(f"Total packages with available upgrades: {len(packages)}")


# ---------------------------------------------------------------------------
# unittest test case — also usable as a plain script
# ---------------------------------------------------------------------------

class TestGetUpdates(unittest.TestCase):
    """Integration test: verify that GetPackages(scope='upgrades') works."""

    @classmethod
    def setUpClass(cls):
        """Fetch the upgrade list once; share across all test methods."""
        print("\n--- Connecting to dnf5daemon and fetching upgrades ---")
        cls.packages = fetch_upgrades()
        print_upgrades(cls.packages)

    def test_returns_a_list(self):
        """GetPackages must return a list (possibly empty)."""
        self.assertIsInstance(self.packages, list)

    def test_packages_have_required_keys(self):
        """Every returned package dict must contain 'name', 'evr', 'repo_id'."""
        for pkg in self.packages:
            with self.subTest(pkg=pkg.get("name", "<unknown>")):
                self.assertIn("name",    pkg, "missing 'name' key")
                self.assertIn("evr",     pkg, "missing 'evr' key")
                self.assertIn("repo_id", pkg, "missing 'repo_id' key")

    def test_count_is_non_negative(self):
        """Package count must be >= 0."""
        self.assertGreaterEqual(len(self.packages), 0)


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Fetching packages with available upgrades from dnf5daemon …\n")
    try:
        pkgs = fetch_upgrades()
    except Exception as exc:
        print(f"ERROR: could not connect to dnf5daemon: {exc}", file=sys.stderr)
        sys.exit(1)

    print_upgrades(pkgs)
