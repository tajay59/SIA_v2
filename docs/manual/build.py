"""Builds docs/manual/index.html from the chapter sources in docs/manual/src/*.md.

Usage (from docs/manual):   pip install markdown   then   python build.py
The sources are build inputs only; readers use index.html. Re-run after editing any src/*.md.
"""
import re
from pathlib import Path

import markdown

M = Path(__file__).resolve().parent
SRC = M / "src"
chapters = ["README.md", "01-introduction.md", "02-users-roles-apps.md", "03-architecture.md", "04-data.md",
            "05-workflows.md", "06-security.md", "07-deployment-operations.md", "08-technology-stack.md",
            "09-documentation-glossary.md", "10-api.md", "11-app-flows.md", "12-design-system.md", "13-data-migration.md", "14-infrastructure.md", "15-testing.md", "16-implementation-plan.md"]
ch_ids = {f: ("home" if f == "README.md" else f[:-3]) for f in chapters}


def fix_links(md_text):
    # drop per-chapter "prev / home / next" nav lines
    md_text = re.sub(r"^\[← .*$\n?", "", md_text, flags=re.M)
    md_text = re.sub(r"^\[Manual home\].*$\n?", "", md_text, flags=re.M)
    # chapter links -> in-page anchors
    for f, cid in ch_ids.items():
        md_text = re.sub(r"\]\(" + re.escape(f) + r"#([^)]+)\)", r"](#\1)", md_text)
        md_text = md_text.replace(f"]({f})", f"](#{cid})")
    # other docs (../X.md) stay as links to the Markdown sources
    return md_text


sections, toc = [], []
for f in chapters:
    src = fix_links((SRC / f).read_text(encoding="utf-8"))
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "attr_list"],
                           extension_configs={"toc": {"toc_depth": "1-2"}})
    html = md.convert(src)
    html = re.sub(r'<img alt="([^"]*)" src="([^"]+)"\s*/?>',
                  r'<figure><a href="\2" target="_blank" title="Open full size"><img alt="\1" src="\2" loading="lazy"></a>'
                  r'<figcaption>\1</figcaption></figure>', html)
    html = re.sub(r"<p>(<figure>.*?</figure>)</p>", r"\1", html, flags=re.S)
    cid = ch_ids[f]
    sections.append(f'<section class="chapter" id="{cid}">{html}</section>')
    tokens = md.toc_tokens
    if tokens:
        top = tokens[0]
        subs = "".join(f'<li><a href="#{c["id"]}">{c["name"]}</a></li>' for c in top.get("children", []))
        title = "Overview" if f == "README.md" else top["name"]
        toc.append(f'<li><a class="ch" href="#{cid}">{title}</a>' + (f"<ul>{subs}</ul>" if subs else "") + "</li>")

page = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CIMH Stores Manual</title>
<style>
:root{--bg:#ffffff;--fg:#1f2328;--muted:#59636e;--line:#d1d9e0;--side:#f6f8fa;--accent:#1f5fbf;--code:#eff1f3;--th:#f6f8fa;--fig:#121212}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--line:#30363d;--side:#151b23;--accent:#4493f8;--code:#1f2630;--th:#151b23;--fig:#121212}}
:root[data-theme="dark"]{--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--line:#30363d;--side:#151b23;--accent:#4493f8;--code:#1f2630;--th:#151b23;--fig:#121212}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:16px}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
nav{position:fixed;top:0;left:0;bottom:0;width:290px;overflow-y:auto;background:var(--side);border-right:1px solid var(--line);padding:20px 16px}
nav .brand{font-weight:700;font-size:16px;margin-bottom:4px}
nav .sub{color:var(--muted);font-size:12px;margin-bottom:14px}
nav input{width:100%;padding:7px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);margin-bottom:12px}
nav ul{list-style:none;margin:0;padding:0}
nav li{margin:2px 0}
nav ul ul{padding-left:12px;margin:2px 0 8px;border-left:1px solid var(--line)}
nav ul ul a{color:var(--muted);font-size:13px;display:block;padding:1px 8px}
nav a.ch{font-weight:600;display:block;padding:4px 6px;border-radius:5px;color:var(--fg)}
nav a.active{background:var(--accent);color:#fff !important}
nav .theme{margin-top:16px;width:100%;padding:6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
main{margin-left:290px;padding:24px 48px 80px;max-width:1180px}
.chapter{border-bottom:2px solid var(--line);padding-bottom:32px;margin-bottom:32px}
h1{font-size:28px;border-bottom:1px solid var(--line);padding-bottom:8px}
h2{font-size:21px;margin-top:32px;border-bottom:1px solid var(--line);padding-bottom:4px}
h3{font-size:17px;margin-top:24px}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:6px 10px;vertical-align:top;text-align:left}
th{background:var(--th)}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:13px}
pre{background:var(--code);padding:12px;border-radius:6px;overflow-x:auto}pre code{padding:0;background:none}
blockquote{margin:12px 0;padding:6px 14px;border-left:4px solid var(--accent);color:var(--muted);background:var(--side)}
figure{margin:18px 0;padding:12px;background:var(--fig);border:1px solid var(--line);border-radius:8px;text-align:center}
figure img{max-width:100%;height:auto}
figcaption{color:#9198a1;font-size:13px;margin-top:6px}
.menu{display:none}
@media (max-width:900px){nav{transform:translateX(-100%);transition:.2s;z-index:10}nav.open{transform:none}
 main{margin-left:0;padding:16px}.menu{display:block;position:fixed;top:10px;right:10px;z-index:11;padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--side);color:var(--fg)}}
@media print{nav,.menu{display:none}main{margin:0;max-width:none;padding:0}.chapter{page-break-after:always;border:none}figure{page-break-inside:avoid}}
</style>
</head>
<body>
<button class="menu" onclick="document.querySelector('nav').classList.toggle('open')">☰ Contents</button>
<nav>
  <div class="brand">CIMH Stores Platform v2</div>
  <div class="sub">System Manual · SHOP · SIA · SIA Mobile</div>
  <input id="filter" type="search" placeholder="Filter sections…" aria-label="Filter sections">
  <ul id="toc">__TOC__</ul>
  <button class="theme" id="theme">Toggle light / dark</button>
</nav>
<main>__BODY__</main>
<script>
(function(){
  var root=document.documentElement,key='cimh-manual-theme';
  try{var t=localStorage.getItem(key);if(t)root.setAttribute('data-theme',t);}catch(e){}
  document.getElementById('theme').onclick=function(){
    var dark=root.getAttribute('data-theme')?root.getAttribute('data-theme')==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
    var t=dark?'light':'dark';root.setAttribute('data-theme',t);try{localStorage.setItem(key,t);}catch(e){}
  };
  document.getElementById('filter').oninput=function(){
    var q=this.value.toLowerCase();
    document.querySelectorAll('#toc li').forEach(function(li){li.style.display=li.textContent.toLowerCase().indexOf(q)>-1?'':'none';});
  };
  var links=[].slice.call(document.querySelectorAll('nav a.ch'));
  var obs=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){
    links.forEach(function(a){a.classList.toggle('active',a.getAttribute('href')==='#'+e.target.id);});}});},{rootMargin:'0px 0px -80% 0px'});
  document.querySelectorAll('section.chapter').forEach(function(s){obs.observe(s);});
  document.querySelectorAll('nav a').forEach(function(a){a.addEventListener('click',function(){document.querySelector('nav').classList.remove('open');});});
})();
</script>
</body>
</html>
"""
out = page.replace("__TOC__", "".join(toc)).replace("__BODY__", "\n".join(sections))
(M / "index.html").write_text(out, encoding="utf-8", newline="\n")  # LF on Windows too (.gitattributes)
print("wrote", M / "index.html", len(out), "bytes;", len(sections), "chapters")
