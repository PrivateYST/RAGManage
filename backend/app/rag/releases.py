"""知识库 Release 清单与差异计算。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def release_manifest_hash(
    *,
    knowledge_base_id: int,
    input_epoch: int,
    ingestion_profile_id: int,
    embedding_profile_id: int,
    items: Sequence[Mapping[str, Any]],
) -> str:
    """生成与数据库 ID 顺序无关的不可变发布清单摘要。"""
    manifest = {
        "knowledge_base_id": knowledge_base_id,
        "input_epoch": input_epoch,
        "ingestion_profile_id": ingestion_profile_id,
        "embedding_profile_id": embedding_profile_id,
        "items": sorted(
            [
                {
                    "document_id": int(item["document_id"]),
                    "document_version_id": int(item["document_version_id"]),
                    "artifact_id": int(item["artifact_id"]),
                }
                for item in items
            ],
            key=lambda item: item["document_id"],
        ),
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def release_diff(
    candidate_items: Sequence[Mapping[str, Any]],
    current_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """按逻辑文档比较候选构建和当前 Release。"""
    candidate = {int(item["document_id"]): item for item in candidate_items}
    current = {int(item["document_id"]): item for item in current_items}
    item_diffs: list[dict[str, Any]] = []

    for document_id in sorted(candidate.keys() | current.keys()):
        candidate_item = candidate.get(document_id)
        current_item = current.get(document_id)
        source = candidate_item or current_item
        if candidate_item is None:
            change = "removed"
        elif current_item is None:
            change = "added"
        elif int(candidate_item["document_version_id"]) != int(
            current_item["document_version_id"]
        ) or int(candidate_item["artifact_id"]) != int(current_item["artifact_id"]):
            change = "updated"
        else:
            change = "unchanged"
        item_diffs.append(
            {
                "document_id": str(document_id),
                "title": str(source["title"]) if source else "",
                "change": change,
                "from_version": (
                    int(current_item["version_no"]) if current_item is not None else None
                ),
                "to_version": (
                    int(candidate_item["version_no"]) if candidate_item is not None else None
                ),
            }
        )

    counts = {
        change: sum(item["change"] == change for item in item_diffs)
        for change in ("added", "updated", "removed", "unchanged")
    }
    return {"counts": counts, "items": item_diffs}


def rollback_candidate_ids(
    releases: Sequence[Mapping[str, Any]],
    *,
    current_release_id: int | None,
    limit: int = 2,
) -> set[int]:
    """从按时间倒序的发布历史中选择最近可回退的 Release。"""
    candidates: set[int] = set()
    for release in releases:
        release_id = int(release["id"])
        if release_id == current_release_id or release["state"] != "retired":
            continue
        candidates.add(release_id)
        if len(candidates) >= limit:
            break
    return candidates
