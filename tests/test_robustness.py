import os
import tempfile
import time
import unittest

import utils
from arxiv_manager import DATASET_FOLDER, _resolve_redirect_target, cleanup_stale_temp_files
from utils import extract_text_from_document, get_sliding_windows


class BackpressureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import api
        import auth_db

        cls.api = api
        cls.auth_db = auth_db
        cls._tmp = tempfile.TemporaryDirectory()
        cls._orig_db = auth_db.DB_FILE
        auth_db.DB_FILE = os.path.join(cls._tmp.name, "bp.sqlite")
        auth_db.init_db()
        cls.client = TestClient(api.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.auth_db.DB_FILE = cls._orig_db
        cls._tmp.cleanup()

    def test_saturated_heavy_slots_return_503_with_retry_after(self):
        # Occupy every heavy slot, then prove the next job is rejected with
        # 503 (backpressure) instead of queueing silently.
        with self.client:
            portal = self.client.portal
            portal.call(self.api.heavy_job_semaphore.acquire)
            portal.call(self.api.heavy_job_semaphore.acquire)
            try:
                with self.assertRaises(Exception) as ctx:
                    portal.call(self.api.run_heavy_job, lambda: "never")
                exc = ctx.exception
                status = getattr(exc, "status_code", None)
                self.assertTrue(status == 503 or "503" in str(exc), f"expected 503, got {exc!r}")
            finally:
                self.api.heavy_job_semaphore.release()
                self.api.heavy_job_semaphore.release()

    def test_deep_health_reports_components(self):
        r = self.client.get("/health/deep")
        self.assertIn(r.status_code, (200, 503))
        body = r.json()
        for key in ("model", "vector_db", "users_db", "disk"):
            self.assertIn(key, body["components"])


class QuotaTests(unittest.TestCase):
    def test_per_user_vector_quota_is_enforced(self):
        import db_manager

        original = db_manager.MAX_VECTORS_PER_USER
        db_manager.MAX_VECTORS_PER_USER = 2
        path = os.path.join(tempfile.gettempdir(), "quota_probe.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Gauge gravity duality maps strongly coupled matter. " * 30)
            ok, msg = db_manager.add_file_to_db(99998, path, "quota_probe.txt")
            self.assertFalse(ok)
            self.assertIn("quota", msg.lower())
        finally:
            db_manager.MAX_VECTORS_PER_USER = original
            if os.path.exists(path):
                os.remove(path)
            try:
                db_manager.delete_source_from_db(99998, "quota_probe.txt")
            except Exception:
                pass


class RedirectTargetTests(unittest.TestCase):
    BASE = "https://arxiv.org/pdf/1706.03762v7.pdf"

    def test_same_host_redirect_is_followed(self):
        self.assertEqual(
            _resolve_redirect_target(self.BASE, "/pdf/1706.03762v7"),
            "https://arxiv.org/pdf/1706.03762v7",
        )

    def test_absolute_same_host_redirect_is_followed(self):
        self.assertEqual(
            _resolve_redirect_target(self.BASE, "https://export.arxiv.org/pdf/1234.5678"),
            "https://export.arxiv.org/pdf/1234.5678",
        )

    def test_evil_host_redirect_is_rejected(self):
        self.assertIsNone(
            _resolve_redirect_target(self.BASE, "https://arxiv.org.evil.example/pdf/1234.5678")
        )

    def test_non_pdf_redirect_is_rejected(self):
        self.assertIsNone(_resolve_redirect_target(self.BASE, "https://arxiv.org/abs/1234.5678"))

    def test_missing_location_is_rejected(self):
        self.assertIsNone(_resolve_redirect_target(self.BASE, ""))
        self.assertIsNone(_resolve_redirect_target(self.BASE, None))


class TruncationFlagTests(unittest.TestCase):
    def test_sliding_windows_reports_capping(self):
        original = utils.MAX_CHUNKS
        utils.MAX_CHUNKS = 3
        try:
            chunks, capped = get_sliding_windows([{"page": 1, "text": "word " * 500}])
            self.assertTrue(capped)
            self.assertEqual(len(chunks), 3)
        finally:
            utils.MAX_CHUNKS = original

    def test_sliding_windows_no_cap_flag(self):
        chunks, capped = get_sliding_windows([{"page": 1, "text": "hello world foo bar test case here"}])
        self.assertFalse(capped)
        self.assertTrue(len(chunks) >= 1)

    def test_oversized_txt_is_truncated_not_rejected(self):
        original = utils.MAX_TEXT_CHARACTERS
        utils.MAX_TEXT_CHARACTERS = 200
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write("lorem ipsum dolor sit amet " * 50)
                path = f.name
            try:
                pages, info = extract_text_from_document(path)
                self.assertTrue(info["truncated"])
                self.assertEqual(info["reason"], "char_limit")
                self.assertTrue(len(pages) == 1)
            finally:
                os.remove(path)
        finally:
            utils.MAX_TEXT_CHARACTERS = original


class OrphanSweepTests(unittest.TestCase):
    def test_stale_temp_files_removed_fresh_kept(self):
        stale = os.path.join(DATASET_FOLDER, "arxiv_unittest_stale.pdf")
        fresh = os.path.join(DATASET_FOLDER, "arxiv_unittest_fresh.pdf")
        try:
            open(stale, "wb").write(b"%PDF-1.4 stale")
            open(fresh, "wb").write(b"%PDF-1.4 fresh")
            old = time.time() - 25 * 3600
            os.utime(stale, (old, old))
            cleanup_stale_temp_files()
            self.assertFalse(os.path.exists(stale))
            self.assertTrue(os.path.exists(fresh))
        finally:
            for p in (stale, fresh):
                if os.path.exists(p):
                    os.remove(p)


if __name__ == "__main__":
    unittest.main()
