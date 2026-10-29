"""Snapshot (path,size,mtime_ns) of the project tree, excluding .venv/.codegraph, to prove the audit wrote nothing there."""
import os, sys, json
root = '/Users/locoframe/Desktop/TRADING BOT'
out = {}
for d, dirs, files in os.walk(root):
    dirs[:] = [x for x in dirs if x not in ('.venv', '.codegraph', '.pytest_cache')]
    for f in files:
        p = os.path.join(d, f); s = os.stat(p)
        out[os.path.relpath(p, root)] = [s.st_size, s.st_mtime_ns]
json.dump(out, open(sys.argv[1], 'w'))
print(len(out), 'files')
