"""Official zero-shot adapter; no network activity during inference/model loading."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import importlib.metadata
import base64
import hashlib
import json
import time
import numpy as np
from .schema import Prediction, HORIZONS, LEVELS, UTC
from .data import features, file_hash

SOURCE_REVISION = 'a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff'

@dataclass(frozen=True)
class Pin:
    repo: str
    revision: str
    config_sha256: str
    weights_sha256: str
    weights_bytes: int

PINS = {
    '28M': Pin('mistralai/Timestral-28M', '49b26409ac87b5935539a5d8ffe7f397b720db47',
               '0cdf44b8ea981191de53078e0a5ecbbd437046bd939a546d5dbe17868f71281f',
               'dfc83c6220937ce5fc6687b35a4df94cd25e28a2cfe6fb92a23dad6301b2015d', 111296464),
    '209M': Pin('mistralai/Timestral-209M', '9874d252ab0aae16f7f7c999f98f98d6ad7d8365',
                '1764139bb6d37ee5ff543f470495c086cfa6c373f7134fc61c7e3d844538bfd8',
                '1456effb9927e3daa8c7234f10497e3424233869245a9c72b8ecebaf7ad2b7fa', 837271648),
}


def verify_checkpoint(path, pin):
    path = Path(path)
    for name, expected in [('config.json', pin.config_sha256), ('model.safetensors', pin.weights_sha256)]:
        if file_hash(path/name) != expected: raise ValueError(f"checkpoint checksum mismatch: {name}")
    if (path/'model.safetensors').stat().st_size != pin.weights_bytes: raise ValueError("checkpoint size mismatch")


def verify_source():
    dist = importlib.metadata.distribution('timestral')
    direct = json.loads(dist.read_text('direct_url.json') or '{}')
    if direct.get('vcs_info', {}).get('commit_id') != SOURCE_REVISION or direct.get('url') != 'https://github.com/mistralai/timestral.git':
        raise ValueError("Timestral must be installed from the pinned Git revision (not an unverified local edit)")
    sources = [entry for entry in (dist.files or ()) if str(entry).startswith('timestral/') and str(entry).endswith('.py')]
    if not sources: raise ValueError('installed Timestral source RECORD missing')
    for entry in sources:
        digest = base64.urlsafe_b64encode(hashlib.sha256(dist.locate_file(entry).read_bytes()).digest()).decode().rstrip('=')
        if entry.hash is None or entry.hash.mode != 'sha256' or entry.hash.value != digest:
            raise ValueError('installed Timestral source differs from its pinned installation RECORD')


class OfficialAdapter:
    def __init__(self, model, checkpoint, max_context=512, forecaster_class=None):
        self.name, self.pin = model, PINS[model]
        verify_checkpoint(checkpoint, self.pin)
        verify_source()
        if forecaster_class is None:
            from timestral import TimestralForecaster
            forecaster_class = TimestralForecaster
        self.forecaster = forecaster_class.from_pretrained(str(checkpoint), revision=self.pin.revision,
                                 device='cpu', max_context=max_context, local_files_only=True)

    def predict(self, request):
        if request.model != self.name: raise ValueError("request/model mismatch")
        f = features(request)
        start = time.perf_counter()
        result = self.forecaster.forecast(f.context, prediction_length=15,
                   past_covariates=f.past if request.variant == 'past_covariates' else None,
                   symmetric_averaging=True, clip_nonnegative=False)
        latency = time.perf_counter()-start
        if tuple(result.quantile_levels) != LEVELS: raise ValueError("official output quantiles changed")
        values = result.quantiles.detach().cpu().numpy()
        if values.shape != (1, 1, 15, 21): raise ValueError("unexpected official forecast shape")
        return Prediction(request.key, request.symbol, request.contract, request.origin,
             max(datetime.now(UTC), request.requested_at), self.name, self.pin.revision, SOURCE_REVISION,
             self.pin.config_sha256, self.pin.weights_sha256, request.variant, HORIZONS, LEVELS,
             tuple(tuple(float(x) for x in values[0, 0, h-1]) for h in HORIZONS), latency, 'wall', len(request.bars))


def provision(model, destination, license_eligibility_reviewed=False):
    """Explicit user command only. This function is never called by service/research inference."""
    if license_eligibility_reviewed is not True:
        raise ValueError("Review the checkpoint Modified MIT license, including company/employer revenue eligibility, first")
    from huggingface_hub import snapshot_download
    pin = PINS[model]
    path = snapshot_download(pin.repo, revision=pin.revision, local_dir=str(destination),
                             allow_patterns=['config.json', 'model.safetensors', 'LICENSE'])
    verify_checkpoint(path, pin)
    return path
