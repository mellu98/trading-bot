"""Append-only freeze receipt: SHA256 of a protocol and the source files it depends on.

Usage: python -I freeze.py <research_dir> <protocol_file> <label> <src files...>
A receipt is written BEFORE any economic result of that protocol is computed.
"""
import datetime as dt
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
proto, label, srcs = root / sys.argv[2], sys.argv[3], sys.argv[4:]
receipts = root / "protocol" / "freeze-receipts.json"
old = json.loads(receipts.read_text()) if receipts.exists() else []
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
entry = {
    "label": label,
    "frozen_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "protocol": {"path": str(proto.relative_to(root)), "sha256": sha(proto)},
    "sources": {s: sha(root / s) for s in srcs},
    "results_present_at_freeze": sorted(str(p.relative_to(root)) for p in (root / "results").rglob("*.json")
                                        if p.name != "data-quality.json"),
}
receipts.write_text(json.dumps(old + [entry], indent=1))
print(json.dumps(entry, indent=1))
