"""Isolated free-metadata planner; existing adapter source is read-only."""
from pathlib import Path
import sys

_ADAPTER = Path(__file__).resolve().parents[3] / 'databento' / 'src'
if not (_ADAPTER / 'mnq_data' / 'core.py').is_file():
    raise RuntimeError('verified_adapter_source_missing')
sys.path.insert(0, str(_ADAPTER))
__version__ = '0.1.0'
