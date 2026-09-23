from __future__ import annotations

from typing import Any, MutableMapping


def prune_finished_jobs(
    registry: MutableMapping[str, dict[str, Any]],
    *,
    now_ts: float,
    ttl_seconds: int,
    max_finished_items: int,
) -> list[tuple[str, str]]:
    """Remove expired and excess finished jobs while always retaining active jobs."""
    removed: list[tuple[str, str]] = []
    ttl = max(60, int(ttl_seconds))
    keep_finished = max(1, int(max_finished_items))

    expired_ids = [
        job_id
        for job_id, job in registry.items()
        if float(job.get('finished_ts') or 0) > 0
        and now_ts - float(job.get('finished_ts') or 0) > ttl
    ]
    for job_id in expired_ids:
        if registry.pop(job_id, None) is not None:
            removed.append((job_id, 'ttl_expired'))

    finished = sorted(
        (
            (job_id, float(job.get('finished_ts') or 0))
            for job_id, job in registry.items()
            if float(job.get('finished_ts') or 0) > 0
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    for job_id, _ in finished[keep_finished:]:
        if registry.pop(job_id, None) is not None:
            removed.append((job_id, 'retention_limit'))
    return removed
