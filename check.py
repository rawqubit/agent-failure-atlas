#!/usr/bin/env python3
"""Validator and assembler for agent-failure-atlas. Stdlib only.

  python3 check.py                      run every check, exit 0 only if all pass
  python3 check.py --assemble           regenerate ATLAS.md from the entries
  python3 check.py --ids CTX-01,CTX-02  validate only the named entries (entry
                                        checks only; skips counts, docs, ATLAS.md)
"""
import ast
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CATEGORIES = [
    ("PLAN", "planning", 6, "Plan and decomposition"),
    ("TOOL", "tool-use", 8, "Tool use and actions"),
    ("CTX", "context", 6, "Context"),
    ("MEM", "memory", 5, "Memory and state"),
    ("VERIFY", "verification", 5, "Verification and evals"),
    ("SEC", "security", 5, "Security"),
    ("OPS", "operations", 4, "Operations"),
    ("COST", "economics", 2, "Economics"),
]
EXPECTED_IDS = [f"{p}-{i:02d}" for p, _, n, _ in CATEGORIES for i in range(1, n + 1)]
SLUG_BY_PREFIX = {p: s for p, s, _, _ in CATEGORIES}
TITLE_BY_PREFIX = {p: t for p, _, _, t in CATEGORIES}

KEYS = ["id", "title", "category", "severity", "frequency", "symptom", "stage", "tags"]
SEVERITIES = {"critical", "high", "medium"}
FREQUENCIES = {"common", "occasional", "rare"}
SECTIONS = [
    "What you see",
    "Why it happens",
    "Minimal reproduction",
    "Detection",
    "The fix",
    "How it still bites",
]
FORBIDDEN = [
    "monitor it",
    "best practice",
    "leverage",
    "seamless",
    "in today's",
    "it is important to note",
    "lorem",
]
FORBIDDEN_RE = [(re.compile(r"\bTODO\b"), "TODO")]
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\uFE0F\u200D\u2190-\u21FF\u2900-\u297F]"
)
ID_REF_RE = re.compile(r"\b(" + "|".join(p for p, *_ in CATEGORIES) + r")-(\d\d)\b")
DASH_SEP_RE = re.compile(r"\s(?:-|--|\u2014|\u2013)\s+\S")


def parse_entry(path):
    """Return (meta dict, body str). Raises ValueError on malformed front matter."""
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("file must start with a --- line")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("front matter is not closed by a --- line")
    meta, order = {}, []
    for n, line in enumerate(lines[1:end], start=2):
        if not line.strip():
            raise ValueError(f"line {n}: blank line inside front matter")
        key, sep, value = line.partition(":")
        if not sep or key != key.strip() or not key or " " in key:
            raise ValueError(f"line {n}: expected 'key: value', got {line!r}")
        if key in meta:
            raise ValueError(f"line {n}: duplicate key {key!r}")
        meta[key] = value.strip()
        order.append(key)
    if order != KEYS:
        raise ValueError(f"front-matter keys must be exactly {KEYS} in that order, got {order}")
    for key, value in meta.items():
        if not value:
            raise ValueError(f"key {key!r} is empty")
    return meta, "\n".join(lines[end + 1 :]).strip("\n") + "\n"


def headings(body):
    """H2 headings outside code fences."""
    found, fenced = [], False
    for line in body.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            found.append(line[3:].strip())
    return found


def section_text(body, name):
    out, active, fenced = [], False, False
    for line in body.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            active = line[3:].strip() == name
            continue
        if active:
            out.append(line)
    return "\n".join(out)


def python_blocks(text):
    blocks, cur, in_py, fenced = [], [], False, False
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```"):
            if fenced and in_py:
                blocks.append(cur)
                cur, in_py = [], False
            elif not fenced:
                in_py = s == "```python"
            fenced = not fenced
        elif fenced and in_py:
            cur.append(line)
    return blocks


def run_script(path, timeout=5):
    """Run a python file in a scratch cwd. Returns (exit_code|None, seconds, output)."""
    start = time.monotonic()
    with tempfile.TemporaryDirectory() as cwd:
        try:
            p = subprocess.run(
                [sys.executable, str(path)], cwd=cwd, capture_output=True,
                text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return None, time.monotonic() - start, "timeout after %ss" % timeout
    return p.returncode, time.monotonic() - start, p.stdout + p.stderr


def load_entries(ids):
    entries, problems = {}, []
    for i in ids:
        path = ROOT / "atlas" / f"{i}.md"
        if not path.exists():
            problems.append(f"{i}: missing atlas/{i}.md")
            continue
        try:
            entries[i] = parse_entry(path)
        except ValueError as e:
            problems.append(f"{i}: {e}")
    return entries, problems


def assemble(entries):
    out = [
        "# Agent Failure Atlas: all entries",
        "",
        "Generated by python3 check.py --assemble. Edit the files in atlas/, not this file.",
        "",
        "## Index",
        "",
    ]
    for prefix, slug, _, title in CATEGORIES:
        out.append(f"### {title}")
        out.append("")
        for i in [e for e in EXPECTED_IDS if e.startswith(prefix + "-")]:
            if i in entries:
                out.append(f"- {i}: {entries[i][0]['title']}")
        out.append("")
    for prefix, slug, _, cat_title in CATEGORIES:
        for i in [e for e in EXPECTED_IDS if e.startswith(prefix + "-")]:
            if i not in entries:
                continue
            meta, body = entries[i]
            out += [
                "---", "",
                f"## {i}: {meta['title']}", "",
                f"Category: {meta['category']} | Severity: {meta['severity']} | "
                f"Frequency: {meta['frequency']} | Stage: {meta['stage']}", "",
                f"Symptom: {meta['symptom']}", "",
                f"Tags: {meta['tags']}", "",
            ]
            fenced = False
            for line in body.rstrip("\n").split("\n"):
                if line.lstrip().startswith("```"):
                    fenced = not fenced
                out.append("#" + line if (not fenced and line.startswith("## ")) else line)
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def main(argv):
    only = None
    if "--ids" in argv:
        only = argv[argv.index("--ids") + 1].split(",")
    full = only is None
    ids = EXPECTED_IDS if full else only
    results = []  # (name, [problems])

    entries, problems = load_entries(ids)
    if "--assemble" in argv:
        if problems:
            print("cannot assemble:\n  " + "\n  ".join(problems))
            return 1
        (ROOT / "ATLAS.md").write_text(assemble(entries), encoding="utf-8")
        print(f"wrote ATLAS.md ({len(entries)} entries)")
        return 0

    # 1. ids and counts
    p1 = list(problems)
    if full:
        files = sorted(f.stem for f in (ROOT / "atlas").glob("*.md"))
        if len(files) != 41:
            p1.append(f"expected exactly 41 entries, found {len(files)}")
        for f in files:
            if f not in EXPECTED_IDS:
                p1.append(f"{f}: id outside the category ranges")
        if len(set(files)) != len(files):
            p1.append("duplicate ids")
    for i, (meta, _) in entries.items():
        if meta["id"] != i:
            p1.append(f"{i}: front-matter id {meta['id']!r} does not match filename")
        prefix = i.split("-")[0]
        if meta["category"] != SLUG_BY_PREFIX[prefix]:
            p1.append(f"{i}: category must be {SLUG_BY_PREFIX[prefix]!r}, got {meta['category']!r}")
    results.append(("1. entry count, id ranges, uniqueness (%d entries)" % len(entries), p1))

    # 2. front matter values
    p2 = []
    for i, (meta, _) in entries.items():
        if meta["severity"] not in SEVERITIES:
            p2.append(f"{i}: severity {meta['severity']!r} not in {sorted(SEVERITIES)}")
        if meta["frequency"] not in FREQUENCIES:
            p2.append(f"{i}: frequency {meta['frequency']!r} not in {sorted(FREQUENCIES)}")
        if len([t for t in meta["tags"].split(",") if t.strip()]) < 2:
            p2.append(f"{i}: tags needs at least two comma-separated tags")
    results.append(("2. front-matter keys and enum values", p2))

    # 3. sections, repro block shape
    p3 = []
    for i, (meta, body) in entries.items():
        h = headings(body)
        if h != SECTIONS:
            p3.append(f"{i}: headings {h} != {SECTIONS}")
            continue
        pre = ("\n" + body).split("\n## ", 1)[0].strip()
        if pre:
            p3.append(f"{i}: text before the first section heading")
        repro = section_text(body, "Minimal reproduction")
        blocks = python_blocks(repro)
        if len(blocks) != 1:
            p3.append(f"{i}: Minimal reproduction needs exactly one python block, found {len(blocks)}")
        else:
            n = len(blocks[0])
            if n > 40:
                p3.append(f"{i}: python block is {n} lines, max 40")
            try:
                ast.parse("\n".join(blocks[0]))
            except SyntaxError as e:
                p3.append(f"{i}: python block does not parse: {e}")
        if f"repro/{i}.py" not in repro:
            p3.append(f"{i}: Minimal reproduction must point at repro/{i}.py")
        for name in SECTIONS:
            if len(section_text(body, name).split()) < 15 and name != "Minimal reproduction":
                p3.append(f"{i}: section {name!r} is too short")
    results.append(("3. section headings, order, repro block shape", p3))

    # 4. repros run
    p4 = []
    jobs = []
    for i in entries:
        path = ROOT / "repro" / f"{i}.py"
        if not path.exists():
            p4.append(f"{i}: missing repro/{i}.py")
        else:
            jobs.append((i, path))
    with ThreadPoolExecutor(max_workers=4) as pool:
        outs = list(pool.map(lambda j: run_script(j[1]), jobs))
    slowest = 0.0
    for (i, _), (code, secs, out) in zip(jobs, outs):
        slowest = max(slowest, secs)
        if code != 0:
            p4.append(f"{i}: repro exited {code} after {secs:.1f}s: {out.strip()[-300:]}")
        elif not out.strip():
            p4.append(f"{i}: repro printed nothing")
        else:
            lines = out.splitlines()
            if not any(l.startswith("FAILURE") for l in lines):
                p4.append(f"{i}: repro output has no line starting with FAILURE")
            if not any(l.startswith("FIXED") for l in lines):
                p4.append(f"{i}: repro output has no line starting with FIXED")
    block_jobs = []
    for i, (meta, body) in entries.items():
        blocks = python_blocks(section_text(body, "Minimal reproduction"))
        if len(blocks) == 1:
            block_jobs.append((i, blocks[0]))
    with tempfile.TemporaryDirectory() as td:
        paths = []
        for i, block in block_jobs:
            f = Path(td) / f"{i}_block.py"
            f.write_text("\n".join(block) + "\n", encoding="utf-8")
            paths.append((i, f))
        with ThreadPoolExecutor(max_workers=4) as pool:
            bouts = list(pool.map(lambda j: run_script(j[1]), paths))
    for (i, _), (code, secs, out) in zip(paths, bouts):
        if code != 0:
            p4.append(f"{i}: embedded markdown block exited {code}: {out.strip()[-300:]}")
        elif not out.strip():
            p4.append(f"{i}: embedded markdown block printed nothing")
    results.append((
        "4. repro/<ID>.py and embedded block run: exit 0, <5s, output has FAILURE and FIXED lines "
        "(slowest %.2fs)" % slowest, p4))

    # 5. forbidden phrases, emoji, dangling id references
    p5 = []
    scan = [ROOT / "README.md", ROOT / "ATLAS.md"]
    scan += sorted((ROOT / "docs").glob("*.md")) + sorted((ROOT / "atlas").glob("*.md"))
    scan += sorted((ROOT / "repro").glob("*.py"))
    if not full:
        scan = [ROOT / "atlas" / f"{i}.md" for i in entries] + [ROOT / "repro" / f"{i}.py" for i in entries]
    for f in scan:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        low = text.lower()
        rel = f.relative_to(ROOT)
        for phrase in FORBIDDEN:
            if phrase in low:
                p5.append(f"{rel}: forbidden phrase {phrase!r}")
        for rx, name in FORBIDDEN_RE:
            if rx.search(text):
                p5.append(f"{rel}: forbidden phrase {name!r}")
        if EMOJI_RE.search(text):
            p5.append(f"{rel}: emoji or pictograph character")
        for m in ID_REF_RE.finditer(text):
            if m.group(0) not in EXPECTED_IDS:
                p5.append(f"{rel}: reference to unknown id {m.group(0)}")
    results.append(("5. forbidden phrases, emoji, unknown id references", p5))

    if full:
        # 6. docs
        p6 = []
        for name in ["taxonomy.md", "how-to-use.md", "citations.md"]:
            if not (ROOT / "docs" / name).exists():
                p6.append(f"missing docs/{name}")
        cit = ROOT / "docs" / "citations.md"
        if cit.exists():
            n = 0
            for line in cit.read_text(encoding="utf-8").split("\n"):
                if line.startswith("-"):
                    n += 1
                    if not DASH_SEP_RE.search(line[1:]):
                        p6.append(f"citations.md: no ' - note' after: {line[:80]}")
            if n < 20:
                p6.append(f"citations.md has only {n} citation lines, expected at least 20")
        readme = ROOT / "README.md"
        if not readme.exists():
            p6.append("missing README.md")
        else:
            rt = readme.read_text(encoding="utf-8")
            for i, (meta, _) in entries.items():
                if f"| {i} |" not in rt:
                    p6.append(f"README.md: index table has no row for {i}")
                elif meta["title"] not in rt:
                    p6.append(f"README.md: title of {i} differs from the entry")
        results.append(("6. docs exist, citations carry notes, README indexes every entry", p6))

        # 7. ATLAS.md fresh
        p7 = []
        atlas = ROOT / "ATLAS.md"
        if not atlas.exists():
            p7.append("ATLAS.md missing; run python3 check.py --assemble")
        elif not problems and atlas.read_text(encoding="utf-8") != assemble(entries):
            p7.append("ATLAS.md is stale; run python3 check.py --assemble")
        results.append(("7. ATLAS.md matches the entries", p7))

    failed = 0
    for name, probs in results:
        print(("PASS  " if not probs else "FAIL  ") + name)
        for p in probs:
            print("      - " + p)
        failed += bool(probs)
    print("\n%d/%d checks passed" % (len(results) - failed, len(results)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
