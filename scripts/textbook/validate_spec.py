"""Specification validator for the textbook pipeline.

Verifies:
1. Every chapter contains all required fields.
2. All source files exist on disk (globs expanded).
3. Every must_include item (or any of its '/' alternatives) appears in source text.
4. Every figure id has Chinese & English captions and a generator in figs_concept or figs_data.
"""
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from book import ROOT
from chapters import CHAPTERS, FIG_EN, FIG_CAPTIONS
import figs_concept
import figs_data


REQUIRED_FIELDS = ("n", "slug", "title", "part", "sources", "must_include", "figures", "length", "outline", "position")


def expand_sources(sources_list):
    """Expand paths and globs into a list of resolved Path objects."""
    paths = []
    for s in sources_list:
        if isinstance(s, tuple):
            # (path, start_marker, end_marker)
            p = Path(s[0])
            paths.append(p)
        else:
            p_str = str(s)
            if "*" in p_str:
                matched = [Path(m) for m in glob.glob(p_str)]
                paths.extend(matched)
            else:
                paths.append(Path(s))
    return paths


def validate(chapters=None, check_implemented=True):
    """Run all validation checks against the given chapter specs.
    
    Returns a list of error strings (empty if validation passes).
    """
    if chapters is None:
        chapters = CHAPTERS

    errors = []
    seen_fig_ids = set()

    for c in chapters:
        ch_id = f"Ch {c.get('n', '?')} ({c.get('slug', '?')})"

        # 1. Required fields
        for field in REQUIRED_FIELDS:
            if field not in c or c[field] is None or (isinstance(c[field], str) and not c[field].strip()):
                errors.append(f"{ch_id}: missing or empty required field '{field}'")

        # 2. Sources existence
        sources = c.get("sources", [])
        if not sources:
            errors.append(f"{ch_id}: sources list is empty")
        
        expanded = []
        for s in sources:
            p_str = str(s if not isinstance(s, tuple) else s[0])
            if "*" in p_str:
                matched = glob.glob(p_str)
                if not matched:
                    errors.append(f"{ch_id}: glob pattern matched no files: {p_str}")
                expanded.extend(Path(m) for m in matched)
            else:
                p = Path(p_str)
                if not p.exists():
                    errors.append(f"{ch_id}: source file does not exist: {p}")
                expanded.append(p)

        # Read combined sources content
        combined_text = ""
        for p in expanded:
            if p.exists() and p.is_file():
                try:
                    combined_text += p.read_text(encoding="utf-8") + "\n"
                except Exception as e:
                    errors.append(f"{ch_id}: failed to read source {p}: {e}")

        # 3. Must include validation
        must_include = c.get("must_include", c.get("facts", []))
        for item in must_include:
            alts = [alt.strip() for alt in item.split("／")]
            if not any(alt in combined_text for alt in alts):
                errors.append(f"{ch_id}: must_include item not found in sources: {item!r}")

        # 4. Figures validation
        figs = c.get("figures", [])
        for f in figs:
            if not isinstance(f, tuple) or len(f) < 2:
                errors.append(f"{ch_id}: figure spec must be a tuple of (id, caption, section): {f}")
                continue
            fid, cap_zh = f[0], f[1]
            if fid in seen_fig_ids:
                errors.append(f"{ch_id}: duplicate figure id: {fid}")
            seen_fig_ids.add(fid)

            if not cap_zh or not str(cap_zh).strip():
                errors.append(f"{ch_id}: empty Chinese caption for figure {fid}")

            if fid not in FIG_EN or not str(FIG_EN[fid]).strip():
                errors.append(f"{ch_id}: missing or empty English caption in FIG_EN for {fid}")

            if check_implemented:
                has_concept = hasattr(figs_concept, fid)
                has_data = hasattr(figs_data, fid)
                if not (has_concept or has_data):
                    errors.append(f"{ch_id}: figure {fid} has no generator function in figs_concept or figs_data")

    return errors


def main():
    errors = validate(CHAPTERS)
    if errors:
        print(f"Validation FAILED with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  [ERROR] {err}", file=sys.stderr)
        sys.exit(1)
    else:
        fig_count = sum(len(c.get("figures", [])) for c in CHAPTERS)
        print(f"Specification validation passed ({len(CHAPTERS)} chapters, {fig_count} figures).")
        sys.exit(0)


if __name__ == "__main__":
    main()
