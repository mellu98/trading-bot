"""Assemble reports/OPUS-EDGE-RESEARCH.md from the section drafts (renumbering headings).

Usage: python -I assemble_report.py <research_dir> <project_root>
"""
import pathlib
import re
import sys

root, project = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
r = root / "results"
parts = [
    (r / "draft-top.md", {}),
    (r / "draft-head-sections.md", {}),
    (r / "draft-sources.md", {}),
    (r / "draft-ranking-answers.md", {"4": "3", "5": "4", "11": "10", "12": "11"}),
    (r / "draft-experiments-section.md", {"6": "5"}),
    (r / "draft-tail-sections.md", {"7": "6", "8": "7", "9": "8", "10": "9"}),
    (r / "draft-verdict.md", {}),
]
chunks = {}
for path, mapping in parts:
    text = path.read_text()
    text = re.sub(r"^## (\d+)\.", lambda m: f"## {mapping.get(m.group(1), m.group(1))}.", text, flags=re.M)
    chunks[path.name] = text.strip()
# keep the answers section (10, 11) after the tail sections
ranking = chunks["draft-ranking-answers.md"]
split = ranking.index("## 10.")
order = [chunks["draft-top.md"], chunks["draft-head-sections.md"], chunks["draft-sources.md"], ranking[:split].strip(),
         chunks["draft-experiments-section.md"], chunks["draft-tail-sections.md"], ranking[split:].strip(),
         chunks["draft-verdict.md"]]
out = project / "reports" / "OPUS-EDGE-RESEARCH.md"
out.write_text("\n\n".join(order) + "\n")
print(out, len(out.read_text().split()), "words")
for line in out.read_text().splitlines():
    if line.startswith("## "):
        print(line)
