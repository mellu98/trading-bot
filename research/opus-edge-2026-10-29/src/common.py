"""Shared loaders and statistics for the Opus edge research (pure, offline)."""
import csv
import datetime as dt
import io
import math
import pathlib
import random
import zipfile

UTC = dt.timezone.utc
HOUR_MS = 3_600_000


def to_ms(raw, strict=True):
    """Binance spot archives use ms until 2024-12 and µs from 2025-01; normalise to ms.

    Open times must sit on a ms boundary (strict); close times end in ...999 µs and are floored.
    """
    v = int(raw)
    if v > 10**14:  # µs (ms values are ~1.6e12 in this era)
        if strict and v % 1000:
            raise ValueError(f"µs timestamp not on a ms boundary: {v}")
        v //= 1000
    return v


def _rows(zpath):
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        if len(names) != 1:
            raise ValueError(f"unexpected archive members {names}")
        text = z.read(names[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if not row[0].lstrip("-").isdigit():  # header line (newer futures archives)
            continue
        yield row


ANOMALIES = []  # (archive, kind, open_ms, close_ms) recorded by load_klines


def load_klines(folder):
    """Return {open_ms: (open, high, low, close, close_ms)} for every monthly ZIP in folder.

    Bars whose open is not on the hour are dropped (treated as missing); bars with an
    irregular duration (exchange maintenance) are kept at their hour and recorded in ANOMALIES.
    """
    out = {}
    for zp in sorted(pathlib.Path(folder).glob("*.zip")):
        for r in _rows(zp):
            o_ms, c_ms = to_ms(r[0]), to_ms(r[6], strict=False)
            if o_ms % HOUR_MS:
                ANOMALIES.append((zp.name, "unaligned_open_dropped", o_ms, c_ms))
                continue
            if c_ms != o_ms + HOUR_MS - 1:
                ANOMALIES.append((zp.name, "irregular_duration_kept", o_ms, c_ms))
            if o_ms in out:
                raise ValueError(f"{zp.name}: duplicate bar {o_ms}")
            o, h, l, c = map(float, r[1:5])
            if not (h >= max(o, c) and l <= min(o, c) and l > 0):
                raise ValueError(f"{zp.name}: invalid OHLC at {o_ms}")
            out[o_ms] = (o, h, l, c, c_ms)
    return out


def load_funding(folder):
    """Return sorted [(calc_ms, interval_hours, rate)] from fundingRate monthly ZIPs."""
    out = []
    for zp in sorted(pathlib.Path(folder).glob("*.zip")):
        for r in _rows(zp):
            out.append((int(r[0]), int(r[1]), float(r[2])))
    out.sort()
    for a, b in zip(out, out[1:]):
        if a[0] == b[0]:
            raise ValueError(f"duplicate funding timestamp {a[0]}")
    return out


def ms(d):
    return int(d.replace(tzinfo=UTC).timestamp() * 1000)


def iso(m):
    return dt.datetime.fromtimestamp(m / 1000, UTC).isoformat()


# ---------- statistics ----------

def mean(x):
    return sum(x) / len(x) if x else float("nan")


def stdev(x):
    if len(x) < 2:
        return float("nan")
    m = mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def sharpe(x, periods):
    s = stdev(x)
    return mean(x) / s * math.sqrt(periods) if s and s == s and s > 0 else float("nan")


def sortino(x, periods):
    dn = [min(v, 0.0) for v in x]
    dd = math.sqrt(sum(v * v for v in dn) / len(dn)) if dn else float("nan")
    return mean(x) / dd * math.sqrt(periods) if dd and dd > 0 else float("nan")


def max_drawdown(nav):
    peak, mdd = nav[0], 0.0
    for v in nav:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak)
    return mdd


def circular_block_bootstrap(x, block, reps, seed, stat=mean):
    """Circular block bootstrap distribution of stat(x); deterministic given seed."""
    rng = random.Random(seed)
    n = len(x)
    out = []
    for _ in range(reps):
        sample = []
        while len(sample) < n:
            s = rng.randrange(n)
            sample.extend(x[(s + k) % n] for k in range(block))
        out.append(stat(sample[:n]))
    out.sort()
    return out


def quantile(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return sorted_vals[f] if f == c else sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def newey_west_t(x, lags):
    """t-statistic of mean(x) with Newey-West (Bartlett) HAC standard error."""
    n = len(x)
    m = mean(x)
    e = [v - m for v in x]
    g0 = sum(v * v for v in e) / n
    s = g0
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        gl = sum(e[t] * e[t - L] for t in range(L, n)) / n
        s += 2 * w * gl
    se = math.sqrt(s / n) if s > 0 else float("nan")
    return m / se if se == se and se > 0 else float("nan")


def ols_alpha_beta_hac(y, x, lags):
    """OLS y = a + b x; returns a, b, HAC t-stat of a (Newey-West)."""
    n = len(y)
    mx, my = mean(x), mean(y)
    sxx = sum((v - mx) ** 2 for v in x)
    b = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / sxx
    a = my - b * mx
    u = [y[i] - a - b * x[i] for i in range(n)]
    # HAC variance for the intercept via the sandwich on regressors (1, x)
    X = [(1.0, x[i]) for i in range(n)]
    xtx = [[n, sum(x)], [sum(x), sum(v * v for v in x)]]
    det = xtx[0][0] * xtx[1][1] - xtx[0][1] * xtx[1][0]
    inv = [[xtx[1][1] / det, -xtx[0][1] / det], [-xtx[1][0] / det, xtx[0][0] / det]]
    S = [[0.0, 0.0], [0.0, 0.0]]
    for L in range(0, lags + 1):
        w = 1.0 if L == 0 else 1 - L / (lags + 1)
        G = [[0.0, 0.0], [0.0, 0.0]]
        for t in range(L, n):
            g1 = (X[t][0] * u[t], X[t][1] * u[t])
            g2 = (X[t - L][0] * u[t - L], X[t - L][1] * u[t - L])
            for i in range(2):
                for j in range(2):
                    G[i][j] += g1[i] * g2[j]
        for i in range(2):
            for j in range(2):
                S[i][j] += w * (G[i][j] + (G[j][i] if L else 0.0)) if L else G[i][j]
    V = [[sum(inv[i][k] * S[k][l] * inv[l][j] for k in range(2) for l in range(2)) for j in range(2)] for i in range(2)]
    se_a = math.sqrt(V[0][0]) if V[0][0] > 0 else float("nan")
    return a, b, a / se_a if se_a == se_a and se_a > 0 else float("nan")
