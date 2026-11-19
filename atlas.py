#!/usr/bin/env python3
"""agent-failure-atlas CLI. Python 3.9+, stdlib only, never writes files.

  python3 atlas.py list [--category CTX] [--severity critical]
  python3 atlas.py show CTX-03
  python3 atlas.py search 'duplicate charge'
  python3 atlas.py repro CTX-03
  python3 atlas.py check [check.py args]
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from check import CATEGORIES, SECTIONS, parse_entry  # noqa: E402

FIELD_WEIGHTS = (("title", 5), ("symptom", 3), ("tags", 3), ("body", 1))


def normalize_id(raw):
    m = re.fullmatch(r"([A-Za-z]+)-?(\d+)", raw.strip())
    return f"{m.group(1).upper()}-{int(m.group(2)):02d}" if m else raw.strip().upper()


def load_all():
    entries = []
    for path in sorted((ROOT / "atlas").glob("*.md")):
        try:
            meta, body = parse_entry(path)
        except ValueError as e:
            print(f"warning: skipping {path.name}: {e}", file=sys.stderr)
            continue
        entries.append((meta, body))
    order = {p: n for n, (p, *_) in enumerate(CATEGORIES)}
    entries.sort(key=lambda e: (order.get(e[0]["id"].split("-")[0], 99), e[0]["id"]))
    return entries


def category_prefix(value):
    for prefix, slug, _, title in CATEGORIES:
        if value.lower() in (prefix.lower(), slug.lower()):
            return prefix
    valid = ", ".join(f"{p}/{s}" for p, s, *_ in CATEGORIES)
    sys.exit(f"unknown category {value!r}; use one of: {valid}")


def cmd_list(args):
    rows = load_all()
    if args.category:
        prefix = category_prefix(args.category)
        rows = [r for r in rows if r[0]["id"].startswith(prefix + "-")]
    if args.severity:
        rows = [r for r in rows if r[0]["severity"] == args.severity]
    if not rows:
        print("no entries match")
        return 0
    table = [("ID", "SEVERITY", "FREQUENCY", "TITLE")]
    table += [(m["id"], m["severity"], m["frequency"], m["title"]) for m, _ in rows]
    widths = [max(len(r[i]) for r in table) for i in range(3)]
    for n, r in enumerate(table):
        print("  ".join(r[i].ljust(widths[i]) for i in range(3)) + "  " + r[3])
        if n == 0:
            print("  ".join("-" * w for w in widths) + "  " + "-" * 5)
    print(f"\n{len(rows)} {'entry' if len(rows) == 1 else 'entries'}")
    return 0


def render_body(body, width):
    out, para, fenced = [], [], False

    def flush():
        if para:
            out.extend(textwrap.wrap(" ".join(para), width) or [""])
            para.clear()

    for line in body.rstrip("\n").split("\n"):
        if line.lstrip().startswith("```"):
            flush()
            if fenced:
                out.append("")
            fenced = not fenced
            continue
        if fenced:
            out.append(("    " + line).rstrip())
            continue
        if line.startswith("## "):
            flush()
            if out and out[-1] != "":
                out.append("")
            out += [line[3:].upper(), "-" * len(line[3:])]
        elif not line.strip():
            flush()
            out.append("")
        elif re.match(r"\s|[-*|]|\d+\.", line):
            flush()
            out.append(line)
        else:
            para.append(line.strip())
    flush()
    return "\n".join(out)


def cmd_show(args):
    wanted = normalize_id(args.id)
    for meta, body in load_all():
        if meta["id"] != wanted:
            continue
        width = min(100, shutil.get_terminal_size((100, 24)).columns)
        title = f"{meta['id']}  {meta['title']}"
        print(title)
        print("=" * min(len(title), width))
        print(f"category: {meta['category']}   severity: {meta['severity']}   "
              f"frequency: {meta['frequency']}   stage: {meta['stage']}")
        print(f"tags: {meta['tags']}")
        print("\n".join(textwrap.wrap("symptom: " + meta["symptom"], width, subsequent_indent="  ")))
        print(render_body(body, width))
        return 0
    print(f"no entry {wanted}; try: python3 atlas.py list", file=sys.stderr)
    return 1


def cmd_search(args):
    query = " ".join(args.query).lower().strip()
    terms = query.split()
    if not terms:
        sys.exit("search needs a query")
    scored = []
    for meta, body in load_all():
        texts = {"title": meta["title"], "symptom": meta["symptom"], "tags": meta["tags"], "body": body}
        low = {k: v.lower() for k, v in texts.items()}
        if not all(any(t in v for v in low.values()) for t in terms):
            continue
        score, hit_fields = 0, []
        for field, weight in FIELD_WEIGHTS:
            text = low[field]
            s = 0
            if len(terms) > 1 and query in text:
                s += 3 * weight
            for t in terms:
                n = text.count(t)
                s += weight * (min(n, 5) if field == "body" else (1 if n else 0))
            if s:
                score += s
                hit_fields.append(field)
        scored.append((score, meta, hit_fields))
    scored.sort(key=lambda r: (-r[0], r[1]["id"]))
    if not scored:
        print(f"no entries match {query!r}")
        return 0
    for score, meta, fields in scored:
        print(f"{meta['id']:<9} {score:>4}  {meta['title']}")
        print(f"{'':<9}       matched: {', '.join(fields)}")
    print(f"\n{len(scored)} {'match' if len(scored) == 1 else 'matches'}; python3 atlas.py show <ID> for the full entry")
    return 0


def cmd_repro(args):
    wanted = normalize_id(args.id)
    path = ROOT / "repro" / f"{wanted}.py"
    if not path.exists():
        print(f"no repro for {wanted}", file=sys.stderr)
        return 1
    print(f"$ python3 repro/{wanted}.py\n", flush=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    code = subprocess.call([sys.executable, str(path)], env=env)
    print(f"\nexit code: {code}")
    return code


def cmd_check(args):
    return subprocess.call([sys.executable, str(ROOT / "check.py")] + args.rest,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))


def main():
    parser = argparse.ArgumentParser(prog="atlas.py", description="Agent Failure Atlas CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="table of entries")
    p.add_argument("--category", help="PLAN, TOOL, CTX, MEM, VERIFY, SEC, OPS, COST (or the slug)")
    p.add_argument("--severity", choices=["critical", "high", "medium"])
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show", help="render one entry")
    p.add_argument("id")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("search", help="ranked substring search")
    p.add_argument("query", nargs="+")
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser("repro", help="run an entry's reproduction")
    p.add_argument("id")
    p.set_defaults(fn=cmd_repro)
    p = sub.add_parser("check", help="run check.py")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_check)
    args = parser.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
