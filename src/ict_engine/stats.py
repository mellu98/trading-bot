"""Uncertainty and multiple testing (protocol 07).

- Day-block bootstrap including no-trade days (clusters of trades stay together).
- Mean R per trade CI: resample days, statistic = sum(R) / count(trades).
- One-sided p-value for expectancy <= 0 with a centered bootstrap
  (null data: each trade R minus the observed mean R).
- Holm step-down over the registered trial family.
Defaults: 10 000 replicates, seed 20261030, block 5 days; sensitivity 1/10/20.
"""
from __future__ import annotations

import math

import numpy as np

SEED = 20261030
REPS = 10_000


def _block_indices(rng, n, block, reps):
    nb = math.ceil(n / block)
    starts = rng.integers(0, n, size=(reps, nb), dtype=np.int64)
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(reps, nb * block)[:, :n]


def bootstrap_mean_r(day_r, day_n, *, block=5, reps=REPS, seed=SEED, chunk=2000):
    """Returns dict with observed mean R, CI95 and one-sided p (H0: mean R <= 0)."""
    day_r = np.asarray(day_r, dtype=float)
    day_n = np.asarray(day_n, dtype=float)
    n_days = len(day_r)
    total_n = day_n.sum()
    if n_days == 0 or total_n == 0:
        return {"mean_R": None, "ci95": [None, None], "p_one_sided": None, "block": block, "reps": reps}
    observed = day_r.sum() / total_n
    centered = day_r - day_n * observed
    rng = np.random.default_rng(seed)
    stats, null = [], []
    done = 0
    while done < reps:
        k = min(chunk, reps - done)
        idx = _block_indices(rng, n_days, block, k)
        n = day_n[idx].sum(axis=1)
        safe = np.where(n > 0, n, 1)
        stats.append(np.where(n > 0, day_r[idx].sum(axis=1) / safe, np.nan))
        null.append(np.where(n > 0, centered[idx].sum(axis=1) / safe, np.nan))
        done += k
    s = np.concatenate(stats)
    z = np.concatenate(null)
    s = s[~np.isnan(s)]
    z = z[~np.isnan(z)]
    p = (np.sum(z >= observed) + 1) / (len(z) + 1)
    return {"mean_R": float(observed), "ci95": [float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))],
            "p_one_sided": float(p), "block": block, "reps": reps}


def bootstrap_mean(daily_returns, *, block=5, reps=REPS, seed=SEED):
    x = np.asarray(daily_returns, dtype=float)
    if len(x) == 0:
        return {"mean": None, "ci95": [None, None]}
    rng = np.random.default_rng(seed)
    idx = _block_indices(rng, len(x), block, reps)
    means = x[idx].mean(axis=1)
    return {"mean": float(x.mean()), "ci95": [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]}


def holm(pvalues: dict, alpha=0.05) -> dict:
    """Holm step-down. pvalues: {trial_id: p}. Returns {trial_id: {'p','threshold','reject'}}."""
    items = sorted(((p, k) for k, p in pvalues.items() if p is not None), key=lambda x: x[0])
    m = len(items)
    out = {}
    stopped = False
    for i, (p, k) in enumerate(items):
        threshold = alpha / (m - i)
        reject = (not stopped) and p < threshold
        if not reject:
            stopped = True
        out[k] = {"p": p, "threshold": threshold, "reject": reject, "family_size": m}
    return out


def autocorr1(x) -> float | None:
    x = np.asarray(x, dtype=float)
    if len(x) < 3 or x.std() == 0:
        return None
    return float(np.corrcoef(x[:-1], x[1:])[0, 1])
