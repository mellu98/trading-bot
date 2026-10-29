# Capital credential input — local verification

## Root control and correction
`Credentials.__post_init__` emitted `missing_or_malformed_demo_credentials` from one aggregate check over API key, identifier, password and account. In particular, `value == value.strip()` and blanket control-character checks were incorrectly applied to the opaque API password. Dummy passwords with boundary spaces, tabs or Unicode whitespace reproduced that rejection before any Keychain write or HTTP request.

The exact value/field in the user's historical invocation is not recoverable from that aggregate error; it was never saved. This investigation does not claim to know or reconstruct the user's password. The current stored API key was independently validated without printing any part of it; no real identifier/password record exists.

Password validation now requires a nonempty UTF-8 string only. It never strips, normalizes or silently alters whitespace, punctuation or Unicode. Identifier and API-key rules remain distinct; the key is checked BEFORE prompting, and identifier input is checked BEFORE asking for the password. Empty/wrong-type/invalid-Unicode values have field-specific codes. Incorrect identifier boundary whitespace is reported rather than silently corrected.

## Input and phase boundaries
- `credential_input`: `hidden_input_unavailable_*`, `hidden_input_eof_*`, `hidden_input_cancelled_*`, `hidden_input_encoding_failed_*`, `hidden_input_terminal_failed_*`.
- `credential_validation`: `credential_<field>_empty`, `_wrong_type`, `_invalid_unicode`, plus identifier/key-specific rules.
- `keychain_configuration`: access, write and exact-readback failures.
- HTTP authentication remains a separate, later phase. The previously fixed durable attempt latch and rejection retention are preserved.

`GetPassWarning` is raised before an unsafe echo fallback can read input; EOF/cancel are not mislabeled as empty credentials. This follows the behavior documented at https://docs.python.org/3.13/library/getpass.html. No fallback to visible `input()` or shell password arguments exists. In a noninteractive console, setup fails with an explicit hidden-input error: run the command in macOS Terminal.

A successful local save/readback now sets `credentials_saved:true` independently of later HTTP success; a 401 cannot falsely report that locally verified values were never saved.

## Actual executed evidence
98 Capital/local tests passed, including all 64 previous Capital cases (4 pre-existing pandas warnings). RED failures for password handling, acquisition ordering, phase reporting and saved-state flag are retained.

`test_actual_hidden_tty_and_real_keychain_roundtrip` used a fresh real PTY child with the current macOS/Python locale, not mocked getpass. Both prompts had terminal ECHO disabled before dummy input. A dummy password containing leading/trailing whitespace, tab, nonbreaking space, quotes, backslash and Unicode was recovered exactly from the real macOS Keychain. Identifier and API key also matched exactly. No input values were echoed. The record's HTTP-attempt flag remained false. All disposable entries were removed. See `tty-keychain-probe.json`.

A separate real process with no controlling TTY confirmed safe failure before echoed stdin fallback. All integration values were fictitious; no real credentials were requested during this investigation. No actual Capital authentication or order request was attempted.

Only Capital credential/authentication sources and relevant regression tests changed. Timestral, strategies, Risk Engine, dashboard and prior evidence were verified unchanged. `preservation.json` and delivery hashes document the scope. Rollback boundary is these Capital credential helpers and their auth/input tests only; no unrelated component is involved.

## One command for real completion
In macOS Terminal:

```sh
cd "/Users/locoframe/Desktop/TRADING BOT" && ./run-capital-demo.sh setup
```

The existing API key is reused. Only the two missing fields are entered through hidden prompts. Setup saves and reads them back BEFORE one controlled POST/session; on verified DEMO success the existing quote monitor starts with orders disabled. Authentication failure retains the values and blocks repeated automatic attempts. This local verification is NOT a claim that real Capital authentication has passed.

## Reproduce tests
`PYTHONPATH=src:adapters/databento/src:adapters/databento_planner/src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests_local/test_capital_input.py tests_local/test_capital_credentials.py tests_local/test_capital_auth.py tests_local/test_capital_demo.py tests_local/test_capital_runtime.py -q`
