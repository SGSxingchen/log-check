import csv
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from parser.html_log import html_to_format1, preprocess_log_file


def load_web_app_module():
    spec = importlib.util.spec_from_file_location("log_check_web_app", ROOT / "web" / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HtmlLogRegressionTests(unittest.TestCase):
    def test_html_log_accepts_attribute_order_and_extra_classes(self):
        html = """
        <div data-x="1" class='entry log_child_id_42 selected'>
          <span class="log_child_time">2025/5/24 21:03</span>
          <span class="speaker">&lt;A&amp;B&gt;</span>
          <span class="log_child_content" data-y="2" contenteditable="true">
            第一行<br><img alt="[图片]">第二行
          </span>
        </div>
        """

        converted = html_to_format1(html)

        self.assertIn("A&B(0) 2025-05-24 21:03:00", converted)
        self.assertIn("第一行", converted)
        self.assertIn("[图片]", converted)
        self.assertIn("第二行", converted)

    def test_doc_html_with_long_header_is_preprocessed(self):
        body = """
        <div class="log_child_id_1">
          <span class="log_child_time">2025-05-24 21:03:10</span>
          <span>&lt;骰娘&gt;</span>
          <span contenteditable="true">检定结果</span>
        </div>
        """
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "log.doc"
            src.write_text("X" * 9000 + body, encoding="utf-8")

            converted_path, was_converted = preprocess_log_file(str(src))

            self.assertTrue(was_converted)
            self.assertTrue(converted_path.endswith(".converted.txt"))
            self.assertIn("骰娘(0) 2025-05-24 21:03:10", Path(converted_path).read_text(encoding="utf-8"))


class WebAppRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web_app = load_web_app_module()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.web_app.app.config["OUTPUT_FOLDER"] = self.tmp.name
        self.client = self.web_app.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_cleanup_removes_only_named_generated_file(self):
        download_id = "12345678-1234-4234-9234-123456789abc"
        keep = Path(self.tmp.name) / f"{download_id}_keep.csv"
        remove = Path(self.tmp.name) / f"{download_id}_report.xlsx"
        keep.write_text("keep", encoding="utf-8")
        remove.write_text("remove", encoding="utf-8")

        res = self.client.post(f"/api/cleanup/{download_id}/report.xlsx")

        self.assertEqual(res.status_code, 200)
        self.assertFalse(remove.exists())
        self.assertTrue(keep.exists())

    def test_csv_download_escapes_formula_cells(self):
        payload = {
            "filename": "report.csv",
            "stats": [
                {
                    "day": "总计",
                    "stats": [
                        {
                            "角色名": '=HYPERLINK("http://example.test")',
                            "总发言数": 1,
                        }
                    ],
                }
            ],
        }

        res = self.client.post("/api/download_csv/session-1", json=payload)

        self.assertEqual(res.status_code, 200)
        text = res.data.decode("utf-8-sig")
        res.close()
        cells = [cell for row in csv.reader(text.splitlines()) for cell in row]
        self.assertIn('\'=HYPERLINK("http://example.test")', cells)

    def test_ai_base_url_blocks_private_non_loopback_hosts(self):
        self.assertFalse(self.web_app.is_ai_base_url_allowed("http://192.168.1.10:8000/v1"))
        self.assertFalse(self.web_app.is_ai_base_url_allowed("http://169.254.169.254/latest"))
        self.assertTrue(self.web_app.is_ai_base_url_allowed("http://localhost:11434/v1"))
        self.assertTrue(self.web_app.is_ai_base_url_allowed("https://api.openai.com/v1"))


if __name__ == "__main__":
    unittest.main()
