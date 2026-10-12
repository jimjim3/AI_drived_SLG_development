"""Specification and regression tests for textbook scaffolding and figures."""
import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

# Add project root and scripts/textbook to sys.path
_ROOT = Path(__file__).resolve().parents[1]
_TEXTBOOK = _ROOT / "scripts" / "textbook"
_SRC = _ROOT / "src"

for p in (_ROOT, _TEXTBOOK, _SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from book import AUTHOR, BOOK, OUTLINE_TABLE, ROOT, SYSTEM_EN, SYSTEM_ZH, TITLE_EN, TITLE_ZH
from chapters import CHAPTERS, FIG_CAPTIONS, FIG_EN
from validate_spec import REQUIRED_FIELDS, validate


class TextbookSpecTests(unittest.TestCase):
    """Test suite verifying book/chapter specs, figure mappings, and validator behavior."""

    def test_validate_spec_passes(self):
        """1. validate_spec returns zero errors on current CHAPTERS specification."""
        errors = validate(CHAPTERS)
        self.assertEqual(errors, [], f"Specification validation failed with errors: {errors}")

    def test_chapters_required_fields(self):
        """2. Each chapter contains all required fields with appropriate length constraints."""
        self.assertEqual(len(CHAPTERS), 14, "Expected exactly 14 chapters (13 + appendix)")
        for c in CHAPTERS:
            ch_desc = f"Chapter {c.get('n')} ({c.get('slug')})"
            for f in REQUIRED_FIELDS:
                self.assertIn(f, c, f"{ch_desc} missing required field '{f}'")
                if f != "figures":
                    self.assertTrue(bool(c[f]), f"{ch_desc} has empty value for '{f}'")

            # Word count target checks (3500-6000, 11 and 13 may be shorter)
            min_len, max_len = c["length"]
            self.assertGreaterEqual(min_len, 2000, f"{ch_desc} min length too low")
            self.assertLessEqual(max_len, 6500, f"{ch_desc} max length too high")

    def test_figure_ids_unique_and_match_output_files(self):
        """3. Figure IDs are unique, have captions, and match generated PNG files on disk."""
        all_figs = [f for c in CHAPTERS for f in c["figures"]]
        self.assertEqual(len(all_figs), 16, "Expected exactly 16 figures in total")

        fig_ids = [f[0] for f in all_figs]
        self.assertEqual(len(fig_ids), len(set(fig_ids)), "Figure IDs must be strictly unique")

        fig_dir = ROOT / "docs" / "textbook" / "figures" / "zh-TW"
        for fid, cap_zh, sec in all_figs:
            self.assertIn(fid, FIG_EN, f"Figure {fid} missing English caption in FIG_EN")
            self.assertIn(fid, FIG_CAPTIONS, f"Figure {fid} missing in FIG_CAPTIONS")
            png_file = fig_dir / f"{fid}.png"
            self.assertTrue(png_file.exists(), f"Figure file does not exist: {png_file}")
            self.assertGreater(png_file.stat().st_size, 5000, f"Figure file is suspiciously small/empty: {png_file}")

    def test_status_script_executable(self):
        """4. status.py runs cleanly and exits with status 0."""
        res = subprocess.run(
            [sys.executable, str(_TEXTBOOK / "status.py")],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"status.py failed: {res.stderr}")
        self.assertIn("motivation", res.stdout)
        self.assertIn("appendix", res.stdout)

    def test_validate_spec_fails_on_missing_source(self):
        """5. validate_spec correctly fails when a source file is missing."""
        faulty = copy.deepcopy(CHAPTERS)
        faulty[0]["sources"].append(ROOT / "nonexistent_source_file_12345.md")
        errors = validate(faulty, check_implemented=False)
        self.assertTrue(any("source file does not exist" in e for e in errors),
                        f"Expected error about missing source file, got: {errors}")

    def test_validate_spec_fails_on_missing_must_include(self):
        """6. validate_spec correctly fails when a required fact is absent from sources."""
        faulty = copy.deepcopy(CHAPTERS)
        faulty[0]["must_include"].append("THIS_FACT_DEFINITELY_DOES_NOT_EXIST_XYZ_9999")
        errors = validate(faulty, check_implemented=False)
        self.assertTrue(any("must_include item not found in sources" in e for e in errors),
                        f"Expected error about missing fact, got: {errors}")

    def test_validate_spec_fails_on_missing_required_field(self):
        """7. validate_spec correctly fails when a required field is deleted."""
        faulty = copy.deepcopy(CHAPTERS)
        del faulty[1]["outline"]
        errors = validate(faulty, check_implemented=False)
        self.assertTrue(any("missing or empty required field 'outline'" in e for e in errors),
                        f"Expected error about missing outline field, got: {errors}")

    def test_data_fig_f10_numbers_match_json(self):
        """8. Data figure f10 uses exact 94.3% acceptance rate and +472 troop delta from source JSONs."""
        p_stage2 = ROOT / "docs/evals/2026-10-11_gemini-3.5-flash-lite_seat-faction_2_after-param-fix.json"
        p_stage3 = ROOT / "docs/evals/2026-10-11_gemini-3.5-flash-lite_seat-faction_2_after-siege-odds.json"
        
        s2 = json.loads(p_stage2.read_text(encoding="utf-8"))["summary"]
        s3 = json.loads(p_stage3.read_text(encoding="utf-8"))["summary"]

        self.assertAlmostEqual(s2["orders_accept_rate"] * 100, 94.334, places=2)
        self.assertEqual(s3["mean_troops_delta"], 472.0)

    def test_data_fig_f12_numbers_match_json(self):
        """9. Data figure f12 uses exact +2698 troop delta for faction_3 from Q1 JSON."""
        p_q1_f3 = ROOT / "docs/evals/qwen/q1_default_faction_3.json"
        s = json.loads(p_q1_f3.read_text(encoding="utf-8"))["summary"]
        self.assertEqual(s["mean_troops_delta"], 2698.0)

    def test_data_fig_f13_numbers_match_json(self):
        """10. Data figure f13 uses exact 7 successful captures out of 10 attempts from Q2 advantage JSON."""
        p_q2 = ROOT / "docs/evals/qwen/q2_advantage_faction_2.json"
        diag = json.loads(p_q2.read_text(encoding="utf-8"))["summary"]["diagnostics"]["siege_outcomes"]
        self.assertEqual(diag["experiment"]["attempts"], 10)
        self.assertEqual(diag["experiment"]["captured"], 7)
        self.assertEqual(diag["baseline"]["attempts"], 7)
        self.assertEqual(diag["baseline"]["captured"], 0)

    def test_book_metadata(self):
        """11. book.py defines required titles, author, outline table, and system prompts."""
        self.assertIn("讓 LLM 當君主", TITLE_ZH)
        self.assertTrue(len(TITLE_EN) > 10)
        self.assertIn("AI-Driven SLG", AUTHOR)
        self.assertIn("第 1 章", OUTLINE_TABLE)
        self.assertIn("第 13 章", OUTLINE_TABLE)
        self.assertIn("附錄", OUTLINE_TABLE)
        self.assertIn("繁體中文", SYSTEM_ZH)
        self.assertIn("[[FIG:", SYSTEM_ZH)
        self.assertIn("## 本章學習目標", SYSTEM_ZH)


if __name__ == "__main__":
    unittest.main()
