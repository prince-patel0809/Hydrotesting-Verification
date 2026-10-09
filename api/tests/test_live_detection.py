import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Callable

import numpy as np
from fastapi.testclient import TestClient

from app.db import Database
from app.main import app
from app.models.detection import DetectionSettings
from app.pipeline import PipelineResult
from app.services.vehicle_tracker import VehicleTracker


class LiveDetectionTests(unittest.TestCase):
    def test_websocket_starts_replays_frames_and_stops(self) -> None:
        original_pipeline = app.state.detection_pipeline
        original_database = app.state.hydrotest_db
        settings_received: list[DetectionSettings] = []
        trackers_received: list[VehicleTracker] = []

        def run(
            settings: DetectionSettings,
            progress_callback: Callable[[str, str, int], None],
            frame_number: int,
            vehicle_tracker: VehicleTracker,
        ) -> PipelineResult:
            settings_received.append(settings)
            trackers_received.append(vehicle_tracker)
            progress_callback("detecting", "Finding vehicles", 15)
            progress_callback("complete", "Frame analysis complete", 100)
            image = np.zeros((24, 32, 3), dtype=np.uint8)
            return PipelineResult(
                source_image=image,
                annotated_image=image,
                detections=[],
                candidates_before_filter=0,
                filtered_out_count=0,
                model_name="test-model",
                settings=settings,
                frame_number=frame_number,
            )

        app.state.detection_pipeline = SimpleNamespace(
            source=SimpleNamespace(
                filename="test-frame.jpg",
                read=lambda: np.zeros((24, 32, 3), dtype=np.uint8),
            ),
            run=run,
        )
        with TemporaryDirectory() as database_directory:
            app.state.hydrotest_db = Database(
                Path(database_directory) / "hydrotest-test.sqlite3"
            )
            try:
                with TestClient(app) as client:
                    with client.websocket_connect("/api/detection/live") as websocket:
                        ready = websocket.receive_json()
                        self.assertEqual(ready["type"], "ready")
                        self.assertEqual(ready["mode"], "sample-image-replay")
                        self.assertTrue(
                            ready["preview"].startswith("data:image/jpeg;base64,")
                        )
                        websocket.send_json(
                            {
                                "action": "start",
                                "confidence": 0.4,
                                "min_area_percent": 3,
                                "max_detections": 2,
                            }
                        )
                        events = [websocket.receive_json()]
                        while True:
                            event = websocket.receive_json()
                            events.append(event)
                            if event["type"] == "frame":
                                break
                        websocket.send_json({"action": "stop"})
                        stopped = websocket.receive_json()
                        websocket.send_json(
                            {
                                "action": "start",
                                "confidence": 0.4,
                                "min_area_percent": 3,
                                "max_detections": 2,
                            }
                        )
                        self.assertEqual(
                            websocket.receive_json(),
                            {"type": "status", "status": "running"},
                        )
                        second_frame = None
                        while second_frame is None:
                            event = websocket.receive_json()
                            if event["type"] == "frame":
                                second_frame = event
                        websocket.send_json({"action": "stop"})
                        websocket.receive_json()
            finally:
                app.state.detection_pipeline = original_pipeline
                app.state.hydrotest_db = original_database

        self.assertEqual(events[0], {"type": "status", "status": "running"})
        self.assertEqual(
            [event["stage"] for event in events if event["type"] == "progress"],
            ["detecting", "complete"],
        )
        frame = events[-1]
        self.assertEqual(frame["type"], "frame")
        self.assertEqual(frame["source_image"], "test-frame.jpg")
        self.assertEqual(frame["frame_number"], 1)
        self.assertTrue(frame["annotated_image"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(frame["counts"]["total"], 0)
        self.assertEqual(stopped, {"type": "status", "status": "stopped"})
        self.assertEqual(settings_received[0].confidence_threshold, 0.4)
        self.assertEqual(settings_received[0].min_area_percent, 3)
        self.assertEqual(settings_received[0].max_detections, 2)
        self.assertEqual(second_frame["frame_number"], 2)
        self.assertIs(trackers_received[0], trackers_received[1])


if __name__ == "__main__":
    unittest.main()
