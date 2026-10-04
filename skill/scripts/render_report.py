#!/usr/bin/env python3
"""Make the readable report: the few files a person actually opens, in one
easy-to-find folder, apart from the working files in outputs/.

  report/<name>-v<N>/
    briefing.md     the briefing, as written and checked
    briefing.html   the same as one self-contained web page (no internet needed)
    briefing.pdf    the same, printed by a headless Chrome/Chromium/Edge if one
                    is installed (skipped, with a message, if not)
    cases/          the full deep-dive case write-ups (.md and .html), linked
                    from the web page

Pure code, standard library only. Never overwrites: each call makes a new vN.

Usage:
  python3 render_report.py --brief <brief run>/briefing.md --name <dataset>
                           [--dossiers <deepdive run>/dossiers] [--root report]
"""

import argparse
import glob
import html
import os
import re
import shutil
import subprocess

NUM_RE = re.compile(r"^\d+[a-z]?\.\s*")

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1f;--muted:#6b6b70;--rule:#e3e0d8;--accent:#7a3b1d;--quote:#f2efe7;--cite:#8a8a90}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#17171a;--fg:#e8e6e1;--muted:#a0a0a8;--rule:#2e2e33;--accent:#e0a37f;--quote:#222226;--cite:#8d8d96}}
:root[data-theme="dark"]{--bg:#17171a;--fg:#e8e6e1;--muted:#a0a0a8;--rule:#2e2e33;--accent:#e0a37f;--quote:#222226;--cite:#8d8d96}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 Georgia,"Iowan Old Style","Times New Roman",serif}
main{max-width:46rem;margin:0 auto;padding:2.5rem 16px 5rem}
h1,h2,h3,h4{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;line-height:1.25;color:var(--fg)}
h1{font-size:2rem;margin:0 0 1.5rem}
h2{font-size:1.45rem;margin:3rem 0 1rem;padding-top:1rem;border-top:1px solid var(--rule)}
h3{font-size:1.15rem;margin:2rem 0 .6rem}
h4{font-size:1rem;margin:1.5rem 0 .4rem;color:var(--accent)}
a{color:var(--accent)}
blockquote{margin:1rem 0;padding:.6rem 1rem;background:var(--quote);border-left:3px solid var(--accent);border-radius:4px;font-size:.95rem}
blockquote p{margin:.35rem 0}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85em;background:var(--quote);padding:.05em .3em;border-radius:3px}
pre{background:var(--quote);padding:.8rem;overflow-x:auto;border-radius:4px}
pre code{background:none;padding:0}
.cite{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.68em;color:var(--cite);white-space:nowrap}
table{border-collapse:collapse;width:100%;font-size:.9rem;margin:1rem 0;display:block;overflow-x:auto}
th,td{border:1px solid var(--rule);padding:.35rem .55rem;text-align:left;vertical-align:top}
li{margin:.25rem 0}
hr{border:0;border-top:1px solid var(--rule);margin:2rem 0}
nav.toc{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;font-size:.92rem;background:var(--quote);border-radius:6px;padding:.8rem 1.2rem;margin:0 0 2rem}
nav.toc ol{margin:.3rem 0;padding-left:1.2rem}
.meta{color:var(--muted);font-size:.85rem;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
@media print{body{background:#fff;color:#000;font-size:11pt}main{max-width:none;padding:0}
  blockquote{break-inside:avoid;background:#f5f3ee}h2{break-after:avoid}h3,h4{break-after:avoid}nav.toc{display:none}}
"""


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", lambda m: "<code>" + m.group(1) + "</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"(?<![\w*])_(?!\s)(.+?)(?<!\s)_(?![\w*])", r"<em>\1</em>", s)
    # event-ID citations: [x~1], [a, b], [uuid]: shown small, kept checkable
    s = re.sub(r"\[([^\[\]<>]{4,200})\](?!\()",
               lambda m: f'<span class="cite">[{m.group(1)}]</span>'
               if all(re.search(r"\d", t) for t in re.split(r"[,;]\s*", m.group(1))) else m.group(0), s)
    return s


def slug(text, used):
    base = re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-") or "s"
    s, i = base, 2
    while s in used:
        s, i = f"{base}-{i}", i + 1
    used.add(s)
    return s


def md_to_html(md):
    """Small Markdown renderer for briefings: headings, paragraphs, nested
    lists, block quotes, tables, code blocks, rules, emphasis, links."""
    lines = md.splitlines()
    out, toc, used = [], [], set()
    i = 0
    para = []

    def flush():
        if para:
            out.append("<p>" + inline(" ".join(x.strip() for x in para)) + "</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            flush()
            level, text = len(m.group(1)), inline(m.group(2).strip())
            sid = slug(text, used)
            out.append(f'<h{level} id="{sid}">{text}</h{level}>')
            if level == 2:
                toc.append((sid, text))
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", ln):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if ln.startswith(">"):
            flush()
            block = []
            while i < len(lines) and lines[i].startswith(">"):
                block.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            ps = [p for p in "\n".join(block).split("\n") if p.strip()]
            out.append("<blockquote>" + "".join("<p>" + inline(p) + "</p>" for p in ps) + "</blockquote>")
            continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*:?-", lines[i + 1]):
            flush()
            head = [c.strip() for c in ln.strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
                       + "</tbody></table>")
            continue
        if re.match(r"^\s*([-*+]|\d+[.)])\s+", ln):
            flush()
            items = []
            while i < len(lines) and (re.match(r"^\s*([-*+]|\d+[.)])\s+", lines[i])
                                      or (lines[i].startswith("  ") and lines[i].strip() and items)):
                mm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
                if mm:
                    items.append([len(mm.group(1).expandtabs(4)), not mm.group(2)[0].isdigit(), mm.group(3)])
                else:
                    items[-1][2] += " " + lines[i].strip()
                i += 1
            out.append(render_list(items))
            continue
        if not ln.strip():
            flush()
            i += 1
            continue
        para.append(ln)
        i += 1
    flush()
    return "\n".join(out), toc


def render_list(items):
    html_out, stack = [], []   # stack of (indent, tag)
    for indent, bullet, text in items:
        tag = "ul" if bullet else "ol"
        while stack and indent < stack[-1][0]:
            html_out.append(f"</li></{stack.pop()[1]}>")
        if not stack or indent > stack[-1][0]:
            html_out.append(f"<{tag}>")
            stack.append((indent, tag))
        else:
            html_out.append("</li>")
        html_out.append("<li>" + inline(text))
    while stack:
        html_out.append(f"</li></{stack.pop()[1]}>")
    return "".join(html_out)


def page(md, title_fallback, extra_html="", toc_on=True):
    body, toc = md_to_html(md)
    m = re.search(r"^#\s+(.*)$", md, re.M)
    title = re.sub(r"[*_`]", "", m.group(1)).strip() if m else title_fallback
    nav = ""
    if toc_on and len(toc) > 2:
        nav = '<nav class="toc"><strong>Contents</strong><ol>' + "".join(
            f'<li><a href="#{sid}">{NUM_RE.sub("", t)}</a></li>' for sid, t in toc) + "</ol></nav>"
        body = re.sub(r"(</h1>)", r"\1" + nav, body, count=1) if "</h1>" in body else nav + body
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
            f"<body><main>{body}{extra_html}</main></body></html>")


def find_browser():
    cands = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "/Applications/Chromium.app/Contents/MacOS/Chromium",
             "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
             "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
             r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    for c in cands:
        if os.path.exists(c):
            return c
    for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge"]:
        p = shutil.which(name)
        if p:
            return p
    return None


def to_pdf(html_path, pdf_path):
    b = find_browser()
    if not b:
        return "no Chrome, Chromium, Edge or Brave found; PDF skipped (open briefing.html and print to PDF)"
    url = "file://" + os.path.abspath(html_path)
    for flags in (["--headless=new", "--no-pdf-header-footer"], ["--headless", "--print-to-pdf-no-header"]):
        try:
            subprocess.run([b, *flags, "--disable-gpu", "--no-sandbox", f"--print-to-pdf={os.path.abspath(pdf_path)}", url],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        except (subprocess.TimeoutExpired, OSError):
            continue
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            return f"PDF written with {os.path.basename(b)}"
    return "the browser did not produce a PDF; open briefing.html and print to PDF"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brief", required=True)
    ap.add_argument("--name", required=True, help="dataset name, used for the folder")
    ap.add_argument("--dossiers")
    ap.add_argument("--root", default="report")
    args = ap.parse_args()

    n = 1
    while os.path.exists(os.path.join(args.root, f"{args.name}-v{n}")):
        n += 1
    out = os.path.join(args.root, f"{args.name}-v{n}")
    os.makedirs(out)
    brief_md = open(args.brief, encoding="utf-8").read()
    shutil.copy2(args.brief, os.path.join(out, "briefing.md"))

    extra = ""
    cases = []
    if args.dossiers and os.path.isdir(args.dossiers):
        os.makedirs(os.path.join(out, "cases"))
        for f in sorted(glob.glob(os.path.join(args.dossiers, "*.md"))):
            if f.endswith(".check.md"):
                continue
            md = open(f, encoding="utf-8").read()
            base = os.path.splitext(os.path.basename(f))[0]
            shutil.copy2(f, os.path.join(out, "cases", base + ".md"))
            m = re.search(r"^#\s+(.*)$", md, re.M)
            title = re.sub(r"[*_`]", "", m.group(1)).strip() if m else base
            back = '<p class="meta"><a href="../briefing.html">← Back to the briefing</a></p>'
            with open(os.path.join(out, "cases", base + ".html"), "w", encoding="utf-8") as fh:
                fh.write(page(md, title, extra_html=back, toc_on=False).replace("<main>", "<main>" + back, 1))
            cases.append((base, title))
        if cases:
            extra = ('<h2 id="full-case-write-ups">Full case write-ups</h2><p>The cases told in the briefing, '
                     'each in its full form: timeline, transcripts and answers to the case questions.</p><ul>'
                     + "".join(f'<li><a href="cases/{b}.html">{html.escape(t)}</a></li>' for b, t in cases) + "</ul>")
    html_path = os.path.join(out, "briefing.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(page(brief_md, args.name, extra_html=extra))
    # the PDF is the briefing alone (links to case files don't work on paper)
    pdf_src = os.path.join(out, ".print.html")
    with open(pdf_src, "w", encoding="utf-8") as fh:
        fh.write(page(brief_md, args.name, toc_on=False))
    msg = to_pdf(pdf_src, os.path.join(out, "briefing.pdf"))
    os.remove(pdf_src)
    print(f"report written to {out}/: briefing.md, briefing.html"
          + (", briefing.pdf" if os.path.exists(os.path.join(out, "briefing.pdf")) else "")
          + (f", cases/ ({len(cases)} write-ups)" if cases else "") + f". {msg}.")


if __name__ == "__main__":
    main()
