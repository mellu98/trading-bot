"""Acquire official public archives (Binance public data, Kenneth French library, FRED).

Read-only public GETs, no credentials. Each Binance ZIP is verified against the
official .CHECKSUM file; every download gets a UTC receipt. Existing files are
never overwritten (re-runs only verify).

Usage: python -I acquire.py <cache_dir> binance|french|fred
"""
import datetime as dt
import hashlib
import json
import pathlib
import sys
import time
import urllib.request

BASE = "https://data.binance.vision/"
UA = {"User-Agent": "opus-edge-research/1.0 (offline research; public archives)"}

BINANCE_JOBS = [
    # (prefix template, filename template)
    ("data/futures/um/monthly/fundingRate/{s}/", "{s}-fundingRate-{m}.zip"),
    ("data/futures/um/monthly/klines/{s}/1h/", "{s}-1h-{m}.zip"),
    ("data/spot/monthly/klines/{s}/1h/", "{s}-1h-{m}.zip"),
]
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
FIRST, LAST = (2020, 1), (2026, 9)


def months():
    y, m = FIRST
    while (y, m) <= LAST:
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def get(url, tries=4):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception as e:  # network hiccup: bounded retry
            if k == tries - 1:
                raise
            time.sleep(2 * (k + 1))


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def binance(cache):
    receipts = []
    for pre_t, name_t in BINANCE_JOBS:
        for s in SYMBOLS:
            for m in months():
                pre, name = pre_t.format(s=s), name_t.format(s=s, m=m)
                dest = cache / "binance" / pre / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                ck = get(BASE + pre + name + ".CHECKSUM").decode().split()[0]
                if dest.exists():
                    body = dest.read_bytes()
                    status = "cached"
                else:
                    body = get(BASE + pre + name)
                    status = "downloaded"
                sha = hashlib.sha256(body).hexdigest()
                if sha != ck:
                    raise SystemExit(f"CHECKSUM MISMATCH {pre+name}: {sha} != {ck}")
                if status == "downloaded":
                    dest.write_bytes(body)
                (dest.parent / (name + ".CHECKSUM")).write_text(f"{ck}  {name}\n")
                receipts.append({"url": BASE + pre + name, "sha256": sha, "bytes": len(body),
                                 "status": status, "verified_at_utc": now()})
                time.sleep(0.05)
    return receipts


def single(cache, sub, url, name):
    dest = cache / sub / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        body, status = dest.read_bytes(), "cached"
    else:
        body, status = get(url), "downloaded"
        dest.write_bytes(body)
    return [{"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
             "status": status, "retrieved_at_utc": now()}]


def main():
    cache, what = pathlib.Path(sys.argv[1]), sys.argv[2]
    if what == "binance":
        rec = binance(cache)
    elif what == "french":
        rec = single(cache, "french",
                     "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip",
                     "F-F_Research_Data_Factors_daily_CSV.zip")
    elif what == "fred":
        rec = single(cache, "fred", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3", "DTB3.csv")
    else:
        raise SystemExit("unknown source")
    out = cache / f"receipts-{what}.json"
    old = json.loads(out.read_text()) if out.exists() else []
    out.write_text(json.dumps(old + [{"run_at_utc": now(), "files": rec}], indent=1))
    print(what, len(rec), "files;", sum(r["status"] == "downloaded" for r in rec), "new;",
          sum(r["bytes"] for r in rec), "bytes")


if __name__ == "__main__":
    main()
