import os
import sqlite3
import tempfile
import unittest


class SnapshotRoundtripTests(unittest.TestCase):
    def setUp(self):
        import storage_sync

        self.storage_sync = storage_sync
        self.tmp = tempfile.TemporaryDirectory()
        self._orig_data_dir = os.getenv("CHECKMATE_DATA_DIR")
        os.environ["CHECKMATE_DATA_DIR"] = self.tmp.name
        # Ensure snapshot path is disabled so no network is ever touched.
        for var in (
            "SNAPSHOT_BUCKET",
            "SNAPSHOT_ACCESS_KEY",
            "SNAPSHOT_SECRET_KEY",
            "SNAPSHOT_ENDPOINT",
        ):
            os.environ.pop(var, None)

    def tearDown(self):
        if self._orig_data_dir is None:
            os.environ.pop("CHECKMATE_DATA_DIR", None)
        else:
            os.environ["CHECKMATE_DATA_DIR"] = self._orig_data_dir
        self.tmp.cleanup()

    def _seed_state(self):
        db = os.path.join(self.tmp.name, "users.sqlite")
        conn = sqlite3.connect(db)
        try:
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
            conn.execute("INSERT INTO users (email) VALUES ('a@b.com')")
            conn.commit()
        finally:
            conn.close()
        chroma_file = os.path.join(self.tmp.name, "my_plagiarism_db", "chroma.sqlite")
        os.makedirs(os.path.dirname(chroma_file), exist_ok=True)
        with open(chroma_file, "wb") as f:
            f.write(b"fake-vector-store")

    def test_snapshot_roundtrip(self):
        self._seed_state()
        payload = self.storage_sync.create_snapshot_bytes()
        self.assertTrue(len(payload) > 0)
        # Wipe local state and restore.
        import shutil

        os.remove(os.path.join(self.tmp.name, "users.sqlite"))
        shutil.rmtree(os.path.join(self.tmp.name, "my_plagiarism_db"))
        self.storage_sync.restore_snapshot_bytes(payload)
        conn = sqlite3.connect(os.path.join(self.tmp.name, "users.sqlite"))
        try:
            row = conn.execute("SELECT email FROM users").fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], "a@b.com")
        with open(os.path.join(self.tmp.name, "my_plagiarism_db", "chroma.sqlite"), "rb") as f:
            self.assertEqual(f.read(), b"fake-vector-store")

    def test_snapshot_with_no_state_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.storage_sync.create_snapshot_bytes()

    def test_restore_rejects_path_traversal(self):
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../../evil.txt", b"x")
        with self.assertRaises(ValueError):
            self.storage_sync.restore_snapshot_bytes(buffer.getvalue())

    def test_unconfigured_helpers_are_noops(self):
        self.assertFalse(self.storage_sync.snapshot_configured())
        self.assertFalse(self.storage_sync.restore_on_boot())
        # Must not raise and must not start any thread/timer.
        self.storage_sync.schedule_backup()
        self.storage_sync.flush_backup()

    def test_local_state_detection(self):
        self.assertFalse(self.storage_sync._local_state_present())
        self._seed_state()
        self.assertTrue(self.storage_sync._local_state_present())


if __name__ == "__main__":
    unittest.main()
