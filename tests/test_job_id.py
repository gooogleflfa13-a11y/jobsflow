from tools.fresh_24h.job_id import allocate_ids


def test_allocate_ids_preserves_existing_url_mapping_and_allocates_new_rows():
    rows = [
        {
            "链接": "https://example.com/existing",
            "简历版本": "A",
            "CareerOps分数": "4.20",
            "CareerOps等级": "B",
        },
        {
            "链接": "https://example.com/new",
            "简历版本": "A",
            "CareerOps分数": "4.10",
            "CareerOps等级": "B",
        },
    ]

    allocate_ids(
        rows,
        baseline_max={},
        existing_ids={"https://example.com/existing": "A0-017"},
    )

    assert rows[0]["岗位编号"] == "A0-017"
    assert rows[1]["岗位编号"] == "A0-018"


def test_allocate_ids_does_not_duplicate_reserved_existing_id():
    rows = [
        {
            "链接": "https://example.com/new",
            "简历版本": "A",
            "CareerOps分数": "4.20",
            "CareerOps等级": "B",
        }
    ]

    allocate_ids(
        rows,
        baseline_max={},
        existing_ids={"https://example.com/other": "A0-001"},
    )

    assert rows[0]["岗位编号"] == "A0-002"
