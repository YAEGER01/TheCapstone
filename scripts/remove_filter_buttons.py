"""One-off: remove Filter buttons that carry a filter/search icon from the 3 dashboards."""
import re

FILES = [
    "templates/website/President/president_dashboard.html",
    "templates/website/Auditor/auditor_dashboard.html",
    "templates/website/Treasurer/treasurer_dashboard.html",
]

# <button ...> ... <i class="fa-filter|fa-search"></i> Filter </button>  (multi-line safe)
PAT = re.compile(
    r'<button\b(?:(?!</button>).)*?fa-(?:filter|search)"></i>\s*Filter\s*</button>',
    re.S,
)

for f in FILES:
    with open(f, encoding="utf-8") as fh:
        src = fh.read()
    matches = PAT.findall(src)
    new = PAT.sub("", src)
    with open(f, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    print(f, "->", len(matches), "filter buttons removed")
