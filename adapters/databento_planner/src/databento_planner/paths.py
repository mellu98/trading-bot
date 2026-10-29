"""Resolved output confinement. Call again immediately before each write."""
from pathlib import Path
from .security import PlannerError


def contained(path, root):
    candidate, boundary = Path(path).absolute(), Path(root).absolute()
    for item in (candidate, boundary):
        if '..' in item.parts or any(p.is_symlink() for p in (item,*item.parents)):
            raise PlannerError('output_traversal_or_symlink_forbidden')
    boundary=boundary.resolve()
    candidate=candidate.resolve()
    if candidate==boundary or not candidate.is_relative_to(boundary):
        raise PlannerError('output_outside_allowed_root')
    return candidate
