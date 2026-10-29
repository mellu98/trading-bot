"""Statistical power of Sharpe-ratio tests (Lo 2002 / Jobson-Korkie-Memmel asymptotics, iid approximation).

Usage: python -I power.py <research_dir>
Answers: how many years of daily data are needed to confirm a given Sharpe (or Sharpe difference)?
Serial dependence and fat tails make the true requirement LONGER; these are optimistic lower bounds.
"""
import json
import pathlib
import sys

Z_A, Z_B = 1.6449, 0.8416  # one-sided 5% test, 80% power


def years_single(sr):
    # H0: SR=0 (Var 1/T) vs H1: SR=sr (Var (1+sr^2/2)/T), annualised SR, T in years
    return ((Z_A + Z_B * (1 + sr ** 2 / 2) ** 0.5) / sr) ** 2


def _v(s1, s2, rho):
    # Memmel (2003) corrected Jobson-Korkie variance of SR1 - SR2 per year of data
    return 2 * (1 - rho) + 0.5 * (s1 ** 2 + s2 ** 2 - 2 * s1 * s2 * rho ** 2)


def years_difference(sr1, sr2, rho, diff):
    # H0: both equal to sr2; H1: sr1 = sr2 + diff
    return ((Z_A * _v(sr2, sr2, rho) ** 0.5 + Z_B * _v(sr1, sr2, rho) ** 0.5) / diff) ** 2


root = pathlib.Path(sys.argv[1])
out = {"assumptions": "iid returns, one-sided alpha 5%, power 80%; optimistic (ignores autocorrelation, fat tails, multiple testing)",
       "single_strategy_years_needed": {str(s): round(years_single(s), 2) for s in (0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0)},
       "difference_cases": {}}
cases = {
    "B_vs_riskcapped_passive_2024_point": (2.04, 1.68, 0.8, 0.36),
    "B_vs_riskcapped_passive_rho0.9": (2.04, 1.68, 0.9, 0.36),
    "generic_0.5_difference_rho0.7": (1.0, 0.5, 0.7, 0.5),
}
for k, (a, b, r, d) in cases.items():
    out["difference_cases"][k] = {"sr1": a, "sr2": b, "rho": r, "diff": d, "years_needed": round(years_difference(a, b, r, d), 1)}
(root / "results" / "power.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
