"""End-to-end HTTP server & REST API tests for 2077view."""

from pathlib import Path
import json
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from cp2077_atelier.config import AppConfig
from cp2077_atelier.mock_generator import generate_mock_mods
from cp2077_atelier.server import create_server


class TestServerAPI(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.config = AppConfig.from_root(root, port=0)
        generate_mock_mods(self.config.mod_dir, count=18)
        self.httpd, self.state = create_server(self.config)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self._tmp.cleanup()

    def _get(self, path: str) -> tuple[int, bytes]:
        with urlopen(f"http://127.0.0.1:{self.port}{path}") as resp:
            return resp.status, resp.read()

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        req = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_ui_and_api_workflow(self) -> None:
        status, html = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"2077VIEW", html)

        status, raw = self._get("/api/items?page_size=100")
        self.assertEqual(status, 200)
        data = json.loads(raw.decode("utf-8"))
        self.assertEqual(data["summary"]["total_active"], 18)

        # Asset serving check
        first_item = data["items"][0]
        status, svg = self._get(f"/mod-assets/{first_item['preview_image']}")
        self.assertEqual(status, 200)
        self.assertIn(b"<svg", svg)

        # Reject and execute quarantine
        status, _ = self._post("/api/reject", {"item_ids": [first_item["id"]]})
        self.assertEqual(status, 200)

        status, q_res = self._post("/api/quarantine/execute", {})
        self.assertEqual(status, 200)
        self.assertTrue(len(q_res["moved_files"]) > 0)

        # CET commands endpoint
        status, cet = self._post("/api/cet-commands", {"tweak_ids": [first_item["tweak_id"]]})
        self.assertEqual(status, 200)
        self.assertIn(first_item["tweak_id"], cet["commands"])


if __name__ == "__main__":
    unittest.main()

