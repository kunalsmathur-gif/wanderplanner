"""
Unit tests for core/qdrant.py::delete_stale_destination_points.

Found live 2026-07-20: ingestion upserts by a stable hash of
(destination, name)/(url, section, text) — safe for re-running unchanged
logic, but when the category-selection/chunking logic itself changes,
points dropped by the new logic are never deleted, only new ones added
(London's osm_pois count went 58 -> 112 after re-ingesting with the
round-robin fix: 60 new points plus ~52 orphaned all-food/drink points from
the old logic, still there). delete_stale_destination_points is meant to be
called right before each re-ingestion's upsert so stale points from a prior
run's different selection logic get cleaned up rather than accumulating
forever.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from core.qdrant import delete_stale_destination_points


def _point(point_id: int):
    p = MagicMock()
    p.id = point_id
    return p


class TestDeleteStaleDestinationPoints:
    def test_deletes_points_not_in_keep_set(self):
        client = MagicMock()
        client.scroll.return_value = ([_point(1), _point(2), _point(3)], None)

        deleted = delete_stale_destination_points(client, "osm_pois", "London", keep_ids={2, 3})

        assert deleted == 1
        client.delete.assert_called_once()
        _, kwargs = client.delete.call_args
        assert kwargs["collection_name"] == "osm_pois"
        assert kwargs["points_selector"] == [1]

    def test_no_deletion_when_all_points_are_kept(self):
        client = MagicMock()
        client.scroll.return_value = ([_point(1), _point(2)], None)

        deleted = delete_stale_destination_points(client, "osm_pois", "London", keep_ids={1, 2})

        assert deleted == 0
        client.delete.assert_not_called()

    def test_paginates_through_scroll_offsets(self):
        client = MagicMock()
        client.scroll.side_effect = [
            ([_point(1), _point(2)], "next-page-token"),
            ([_point(3)], None),
        ]

        deleted = delete_stale_destination_points(client, "wiki", "London", keep_ids=set())

        assert deleted == 3
        assert client.scroll.call_count == 2

    def test_empty_collection_returns_zero_without_calling_delete(self):
        client = MagicMock()
        client.scroll.return_value = ([], None)

        deleted = delete_stale_destination_points(client, "osm_pois", "Nowhere", keep_ids={1})

        assert deleted == 0
        client.delete.assert_not_called()
