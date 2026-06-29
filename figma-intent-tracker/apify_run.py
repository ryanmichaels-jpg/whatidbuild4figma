"""Minimal Apify actor runner.

These LinkedIn actors run longer than the run-sync window allows (observed 408s),
so we start an async run and poll the run status, then fetch the dataset items.
One helper, shared by discover.py and extract.py.
"""
from __future__ import annotations

import os
import time

import requests

_BASE = "https://api.apify.com/v2"
_TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


def run_actor(slug: str, body: dict, *, poll_secs: int = 10, max_polls: int = 60) -> list[dict]:
    """Start an actor run, poll to completion, return its dataset items.

    Raises on a non-SUCCEEDED terminal status so the pipeline fails loudly rather
    than silently surfacing nothing.
    """
    token = os.environ["APIFY_TOKEN"]
    actor = slug.replace("/", "~")

    run = requests.post(
        f"{_BASE}/acts/{actor}/runs?token={token}", json=body, timeout=60
    ).json()["data"]
    run_id = run["id"]

    status = run["status"]
    for _ in range(max_polls):
        if status in _TERMINAL:
            break
        time.sleep(poll_secs)
        run = requests.get(f"{_BASE}/actor-runs/{run_id}?token={token}", timeout=60).json()["data"]
        status = run["status"]

    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify actor {slug} ended {status} (run {run_id})")

    dataset_id = run["defaultDatasetId"]
    items: list[dict] = []
    offset = 0
    while True:
        page = requests.get(
            f"{_BASE}/datasets/{dataset_id}/items?token={token}&offset={offset}&limit=1000",
            timeout=60,
        ).json()
        if not page:
            break
        items.extend(page)
        if len(page) < 1000:
            break
        offset += len(page)
    return items
