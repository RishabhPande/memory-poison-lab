"""Regression tests for the built demo page.

The A6 build shipped demo/index.html with no event handlers on the
Play / Reveal / Defend / Reset buttons: every visitor saw a static
page whose controls did nothing (only #play=A1-style deep links
worked). These tests pin the wiring and the freshness of the built
file so the template and the shipped page cannot drift apart again.
"""

import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "demo", "index.html")
BUILDER = os.path.join(ROOT, "scripts", "build_demo.py")

BINDINGS = (
    "playBtn.onclick = play;",
    "revealBtn.onclick = reveal;",
    "defendBtn.onclick = defend;",
    "resetBtn.onclick = reset;",
)


class DemoPageTests(unittest.TestCase):
    def test_controls_are_wired(self):
        with open(DEMO) as fh:
            html = fh.read()
        for binding in BINDINGS:
            self.assertIn(binding, html, f"missing handler: {binding}")

    def test_evidence_controls_and_safe_text_rendering_are_wired(self):
        with open(DEMO) as fh:
            html = fh.read()
        for binding in ("renderTrace('naive');", "renderTrace('defended');",
                        "document.getElementById('download').onclick = downloadReplay;",
                        "node.textContent = text", "row.dataset.reason = entry.reason"):
            self.assertIn(binding, html)
        self.assertIn('aria-label="Decision evidence"', html)
        self.assertIn('schema_version:1', html)
        self.assertIn("defensesShown ? ['naive','defended','repaired'] : ['naive']", html)

    def test_built_page_is_fresh(self):
        """demo/index.html must match a fresh run of scripts/build_demo.py."""
        with open(DEMO, "rb") as fh:
            before = fh.read()
        subprocess.run([sys.executable, BUILDER], check=True,
                       stdout=subprocess.DEVNULL)
        with open(DEMO, "rb") as fh:
            after = fh.read()
        self.assertEqual(before, after,
                         "demo/index.html is stale; run scripts/build_demo.py")


if __name__ == "__main__":
    unittest.main()
