from app.rag.releases import release_diff, release_manifest_hash, rollback_candidate_ids


def test_release_manifest_is_stable_across_item_order() -> None:
    items = [
        {"document_id": 2, "document_version_id": 20, "artifact_id": 200},
        {"document_id": 1, "document_version_id": 10, "artifact_id": 100},
    ]
    first = release_manifest_hash(
        knowledge_base_id=7,
        input_epoch=3,
        ingestion_profile_id=4,
        embedding_profile_id=5,
        items=items,
    )
    second = release_manifest_hash(
        knowledge_base_id=7,
        input_epoch=3,
        ingestion_profile_id=4,
        embedding_profile_id=5,
        items=list(reversed(items)),
    )
    assert first == second


def test_release_diff_reports_document_version_changes() -> None:
    current = [
        {
            "document_id": 1,
            "document_version_id": 10,
            "artifact_id": 100,
            "version_no": 1,
            "title": "保留文档",
        },
        {
            "document_id": 2,
            "document_version_id": 20,
            "artifact_id": 200,
            "version_no": 1,
            "title": "删除文档",
        },
    ]
    candidate = [
        {
            "document_id": 1,
            "document_version_id": 11,
            "artifact_id": 110,
            "version_no": 2,
            "title": "保留文档",
        },
        {
            "document_id": 3,
            "document_version_id": 30,
            "artifact_id": 300,
            "version_no": 1,
            "title": "新增文档",
        },
    ]

    result = release_diff(candidate, current)

    assert result["counts"] == {"added": 1, "updated": 1, "removed": 1, "unchanged": 0}
    assert [item["change"] for item in result["items"]] == [
        "updated",
        "removed",
        "added",
    ]


def test_rollback_candidates_only_include_two_recent_retired_releases() -> None:
    releases = [
        {"id": "5", "state": "ready"},
        {"id": "4", "state": "retired"},
        {"id": "3", "state": "retired"},
        {"id": "2", "state": "retired"},
        {"id": "1", "state": "invalidated"},
    ]

    result = rollback_candidate_ids(releases, current_release_id=5)

    assert result == {3, 4}
