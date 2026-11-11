import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from app import create_app


class SensorAPI(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = str(Path(self.folder.name) / "test.sqlite")
        self.client = TestClient(create_app(self.db))
        self.addCleanup(self.client.close)
        self.sample = {"device": "bench", "sequence": 1,
                       "observed_at": "2026-01-01T00:00:00Z", "millivolts": 2500}

    def post(self, **changes):
        return self.client.post("/samples", json={**self.sample, **changes})

    def test_replay_is_idempotent_and_conflicts_are_visible(self):
        self.assertEqual(self.post().json()["status"], "recorded")
        self.assertEqual(self.post(observed_at="2026-01-01T01:00:00+01:00").json()["status"], "duplicate")
        self.assertEqual(self.post(millivolts=3301).status_code, 409)
        self.assertEqual(self.client.get("/devices/bench/summary").json()["counts"]["normal"], 1)

    def test_boundary_and_missing_sample(self):
        for seq, mv, state in [(1, 2799, "normal"), (2, 2800, "above_limit"), (3, None, "sensor_fault")]:
            self.assertEqual(self.post(sequence=seq, millivolts=mv).json()["state"], state)
        summary = self.client.get("/devices/bench/summary").json()
        self.assertEqual(summary["counts"], {"normal": 1, "above_limit": 1, "sensor_fault": 1})
        self.assertEqual(summary["latest"]["sequence"], 3)

    def test_invalid_samples_rejected(self):
        for fields in [{"millivolts": 5001}, {"millivolts": True},
                       {"sequence": -1}, {"observed_at": "2026-01-01T00:00:00"}]:
            self.assertEqual(self.post(**fields).status_code, 422)
        self.assertEqual(self.client.get("/devices/bench/summary").status_code, 404)

    def test_out_of_order_and_persistence(self):
        self.post(sequence=4)
        self.post(sequence=2)
        with TestClient(create_app(self.db)) as restarted:
            self.assertEqual(restarted.get("/devices/bench/summary").json()["latest"]["sequence"], 4)

    def test_concurrent_replays_write_one_row(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(lambda _: self.post().json()["status"], range(4)))
        self.assertCountEqual(statuses, ["recorded", "duplicate", "duplicate", "duplicate"])
