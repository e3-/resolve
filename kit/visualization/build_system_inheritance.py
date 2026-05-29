#!/usr/bin/env python3
"""
Make one inheritance DAG per .py file in ./system by reusing make_inheritance_graph.py.

Outputs mirror the tree:
  ./visualizations/system/<subdirs>/<filename>.png  (or .mmd)

Usage (from repo root or anywhere):
  python ./visualizations/build_system_inheritance_per_file.py \
    --system-root ./system \
    --viz-root ./visualizations/system \
    --local-package . \
    --make-script ./visualizations/make_inheritance_graph.py
"""
import argparse
import subprocess
import sys
from pathlib import Path


def run_make_script(
    python_exe: str,
    make_script: Path,
    target_file: Path,
    out_base: Path,
    local_pkg: str,
) -> int:
    out_base.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        python_exe,
        str(make_script),
        str(target_file),
        "--out",
        str(out_base),
        "--local-package",
        local_pkg,
    ]
    print("›", " ".join(cmd))
    return subprocess.call(cmd)


def main():
    ap = argparse.ArgumentParser(
        description="Generate one inheritance DAG per .py file in ./system"
    )
    ap.add_argument("--system-root", default="./system", help="Path to ./system")
    ap.add_argument("--viz-root", default="./dag/system", help="Output root for graphs")
    ap.add_argument(
        "--local-package",
        default=".",
        help="Local package label passed to the maker script",
    )
    ap.add_argument(
        "--make-script",
        default=str(Path(__file__).with_name("make_inheritance_graph.py")),
        help="Path to make_inheritance_graph.py",
    )
    args = ap.parse_args()

    system_root = Path(args.system_root).resolve()
    viz_root = Path(args.viz_root).resolve()
    make_script = Path(args.make_script).resolve()
    python_exe = sys.executable

    if not system_root.exists():
        raise SystemExit(f"System root not found: {system_root}")
    if not make_script.exists():
        raise SystemExit(f"make_inheritance_graph.py not found: {make_script}")

    py_files = sorted(
        p for p in system_root.rglob("*.py") if "__pycache__" not in p.parts
    )
    if not py_files:
        print("No Python files found under", system_root)
        return

    failures = 0
    for f in py_files:
        rel_dir = f.parent.relative_to(
            system_root
        )  # e.g., asset/, electric/resources/generic/
        out_dir = viz_root / rel_dir
        out_base = out_dir / f.stem  # e.g., generic.py -> generic.(png|mmd)
        rc = run_make_script(python_exe, make_script, f, out_base, args.local_package)
        if rc != 0:
            print(f"WARNING: generation failed for {f} (exit {rc})")
            failures += 1

    print(
        f"✅ Done. Created graphs for {len(py_files) - failures} files; {failures} failures."
    )


if __name__ == "__main__":
    main()
