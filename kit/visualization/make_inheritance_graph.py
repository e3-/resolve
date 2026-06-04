#!/usr/bin/env python3
"""
Build a class inheritance graph (DAG) for Python code.

- Labels nodes as <top_pkg>.<ClassName> (e.g., kit.BaseGenericResource)
- Wraps long labels instead of truncating (...).
- Outputs Graphviz PNGs if available, otherwise Mermaid (.mmd).

Usage:
  python make_inheritance_graph.py path/to/file_or_dir --out output_basename
"""
import argparse
import ast
import textwrap
from pathlib import Path

# -----------------------
# Helpers for AST parsing
# -----------------------


def top_pkg(module: str | None) -> str | None:
    if not module:
        return None
    return module.split(".")[0]


def qualname_from_base(base):
    """Extract qualified name from AST node."""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        parts = []
        cur = base
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))  # e.g., resolve.system.asset.Asset
    if isinstance(base, ast.Subscript):
        return qualname_from_base(base.value)
    return None


def build_import_maps(tree: ast.AST):
    """Map imported symbols and module aliases to their top-level packages."""
    name_pkg_map = {}
    module_alias_top_pkg = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            pkg = top_pkg(node.module)
            for alias in node.names:
                sym = alias.asname or alias.name
                if pkg:
                    name_pkg_map[sym] = pkg
        elif isinstance(node, ast.Import):
            for alias in node.names:
                pkg = top_pkg(alias.name)
                if not pkg:
                    continue
                if alias.asname:
                    module_alias_top_pkg[alias.asname] = pkg
                else:
                    module_alias_top_pkg[pkg] = pkg
    return name_pkg_map, module_alias_top_pkg


def collapse_to_pkg_plus_class(qualname: str):
    """Split fully qualified name into (pkg, class)."""
    if "." not in qualname:
        return None, qualname
    parts = qualname.split(".")
    return parts[0], parts[-1]


# -----------------------
# Scanning / Graph build
# -----------------------


def scan_py(path: Path, local_pkg_label: str):
    """Scan a single Python file for class inheritance relationships."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    name_pkg_map, module_alias_top_pkg = build_import_maps(tree)
    edges = []
    defined_classes = {}
    base_refs = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            child_name = node.name
            child_label = f"{local_pkg_label}.{child_name}"
            defined_classes[child_name] = child_label
            for base in node.bases:
                bq = qualname_from_base(base)
                if bq:
                    base_refs.append((bq, child_name))

    def parent_label_for(bq: str) -> str | None:
        pkg, cls = collapse_to_pkg_plus_class(bq)
        if pkg:
            return f"{pkg}.{cls}"
        if bq in name_pkg_map:
            return f"{name_pkg_map[bq]}.{bq}"
        if "." in bq:
            left, right = bq.split(".", 1)
            if left in module_alias_top_pkg:
                cls = right.split(".")[-1]
                return f"{module_alias_top_pkg[left]}.{cls}"
        return bq

    for raw_parent, child_short in base_refs:
        parent_lbl = parent_label_for(raw_parent)
        child_lbl = defined_classes.get(child_short, f"{child_short}")
        if parent_lbl:
            edges.append((parent_lbl, child_lbl))

    classes = set(defined_classes.values())
    for p, c in edges:
        classes.add(p)
        classes.add(c)
    return classes, edges


def merge_graph(graphs):
    classes = set()
    edges = set()
    for c, e in graphs:
        classes |= c
        edges |= set(e)
    return classes, list(edges)


# -----------------------
# Output: Graphviz / Mermaid
# -----------------------


def _sanitize_id(label: str) -> str:
    """Sanitize label for use as a Graphviz node id."""
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in label)


def write_mermaid(classes, edges, out_path: Path):
    mer = ["graph TD"]
    for p, c in sorted(edges):
        pid = _sanitize_id(p)
        cid = _sanitize_id(c)
        mer.append(f'  {pid}["{p}"] --> {cid}["{c}"]')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(mer), encoding="utf-8")
    return out_path


def try_graphviz_png(classes, edges, out_path: Path):
    try:
        from graphviz import Digraph
    except Exception:
        return None  # fallback if graphviz is missing

    dot = Digraph("inheritance", format="png")
    dot.attr(rankdir="LR", splines="spline", fontname="Helvetica")
    dot.attr(
        "node",
        shape="box",
        style="rounded,filled",
        fillcolor="white",
        fontname="Helvetica",
        fontsize="10",
    )

    max_width = 25  # wrap width in characters
    # Collect all nodes from edges (ensures we include external parents)
    nodes = set()
    for p, c in edges:
        nodes.add(p)
        nodes.add(c)

    for n in sorted(nodes):
        wrapped = "\n".join(textwrap.wrap(n, width=25))
        dot.node(
            _sanitize_id(n),
            wrapped,
            width="0",
            fixedsize="false",
            style="rounded,filled",
            fillcolor="white",
            fontname="Helvetica",
            fontsize="10",
        )

    for p, c in edges:
        dot.edge(_sanitize_id(p), _sanitize_id(c), arrowhead="vee")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    png_path = out_path.with_suffix(".png")
    dot.render(png_path.stem, png_path.parent, cleanup=True)
    return png_path


# -----------------------
# CLI Entrypoint
# -----------------------


def collect_py_files(paths):
    files = []
    for p in paths:
        P = Path(p)
        if P.is_dir():
            files += list(P.rglob("*.py"))
        elif P.suffix == ".py":
            files.append(P)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Build class inheritance DAG with wrapped labels"
    )
    parser.add_argument("paths", nargs="+", help="Python files or directories to scan")
    parser.add_argument(
        "--out", default="inheritance_graph", help="Output basename (no extension)"
    )
    parser.add_argument(
        "--local-package", default="local", help="Label for locally defined classes"
    )
    args = parser.parse_args()

    files = collect_py_files(args.paths)
    if not files:
        raise SystemExit("No .py files found.")

    graphs = [scan_py(f, args.local_package) for f in files]
    classes, edges = merge_graph(graphs)

    out_base = Path(args.out)
    png = try_graphviz_png(classes, edges, out_base)
    if png:
        print(f"✅ Wrote {png}")
    else:
        mer = write_mermaid(classes, edges, out_base.with_suffix(".mmd"))
        print("ℹ️ Graphviz not found; wrote Mermaid instead.")
        print(f"✅ Wrote {mer}")


if __name__ == "__main__":
    main()
