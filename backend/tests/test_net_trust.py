"""services.net_trust — softwares que o usuário manteve no Vigia de rede (SQLite temporário)."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.database as database  # noqa: E402
from core import netwatch  # noqa: E402
from core.config import settings  # noqa: E402
from services import net_trust  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class TrustCase(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path = path
        self._orig = settings.DB_PATH
        settings.DB_PATH = Path(path)
        self.db = database.DatabaseManager()
        self._patch = patch.object(net_trust, "db", self.db)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass


class TestStore(TrustCase):
    def test_keep_then_trusted_case_insensitive(self):
        self.assertFalse(net_trust.is_trusted("chrome.exe", CHROME))
        self.assertTrue(net_trust.keep("chrome.exe", CHROME, "NEW_TALKER"))
        self.assertTrue(net_trust.is_trusted("Chrome.EXE", CHROME))
        self.assertTrue(net_trust.is_trusted("chrome.exe", CHROME.lower()))   # caminho no Windows ignora caixa

    def test_same_name_other_executable_is_not_trusted(self):
        net_trust.keep("chrome.exe", CHROME, "NEW_TALKER")
        self.assertFalse(net_trust.is_trusted("chrome.exe", r"C:\Users\x\AppData\Local\Temp\chrome.exe"))

    def test_unknown_path_on_either_side_matches_by_name(self):
        net_trust.keep("tool.exe", "", "NEW_LISTENER")                  # exe não lido ao manter
        self.assertTrue(net_trust.is_trusted("tool.exe", r"C:\tools\tool.exe"))
        net_trust.keep("app.exe", r"C:\app\app.exe", "NEW_LISTENER")
        self.assertTrue(net_trust.is_trusted("app.exe", ""))             # exe não lido agora (AccessDenied)

    def test_keep_twice_is_one_row_and_list_and_forget(self):
        net_trust.keep("chrome.exe", CHROME, "NEW_TALKER")
        net_trust.keep("chrome.exe", CHROME, "NEW_LISTENER")
        net_trust.keep("python.exe", r"C:\Python311\python.exe", "NEW_LISTENER")
        items = net_trust.list_all()
        self.assertEqual([i["name"] for i in items], ["python.exe", "chrome.exe"])   # mais recente primeiro
        self.assertIn("python.exe", net_trust.forget(1))
        self.assertFalse(net_trust.is_trusted("python.exe", r"C:\Python311\python.exe"))
        self.assertIn("Não há", net_trust.forget(5))
        self.assertEqual(net_trust.count(), 1)

    def test_list_text(self):
        self.assertIn("Nenhum software mantido", net_trust.list_text())
        net_trust.keep("chrome.exe", CHROME, "NEW_TALKER")
        text = net_trust.list_text()
        self.assertIn("1. **chrome.exe**", text)
        self.assertIn(CHROME, text)

    def test_empty_name_is_ignored(self):
        self.assertFalse(net_trust.keep("", CHROME, "NEW_TALKER"))
        self.assertFalse(net_trust.is_trusted("", CHROME))

    def test_old_database_gains_the_table(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.commit()
            conn.close()
            settings.DB_PATH = Path(path)
            database.DatabaseManager()
            conn = sqlite3.connect(path)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            conn.close()
            self.assertIn("net_trusted_apps", tables)
        finally:
            settings.DB_PATH = Path(self._path)
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(path + suffix)
                except OSError:
                    pass

    def test_db_error_never_raises(self):
        broken = MagicMock()
        broken.connection.side_effect = sqlite3.OperationalError("locked")
        with patch.object(net_trust, "db", broken):
            self.assertFalse(net_trust.keep("x.exe", "", "NEW_TALKER"))
            self.assertFalse(net_trust.is_trusted("x.exe", ""))
            self.assertEqual(net_trust.list_all(), [])


class TestSnapshotExe(unittest.TestCase):
    def test_proc_info_returns_exe_and_tolerates_access_denied(self):
        proc = MagicMock()
        proc.name.return_value = "chrome.exe"
        proc.create_time.return_value = 100.0
        proc.exe.return_value = CHROME
        with patch.dict(sys.modules, {"psutil": MagicMock(Process=MagicMock(return_value=proc))}):
            self.assertEqual(netwatch._proc_info(10), ("chrome.exe", 100.0, CHROME))
        proc.exe.side_effect = PermissionError("negado")
        with patch.dict(sys.modules, {"psutil": MagicMock(Process=MagicMock(return_value=proc))}):
            self.assertEqual(netwatch._proc_info(10), ("chrome.exe", 100.0, ""))

    def test_snapshot_carries_exe(self):
        conn = MagicMock(status="ESTABLISHED", pid=10, laddr=("192.168.0.5", 5000), raddr=("142.250.0.1", 443))
        snap = netwatch.snapshot(connections=lambda: [conn], proc_info=lambda pid: ("chrome.exe", 1.0, CHROME),
                                 with_arp=False)
        self.assertEqual(snap["talkers"]["chrome.exe"]["exe"], CHROME)

    def test_snapshot_accepts_old_two_field_proc_info(self):
        conn = MagicMock(status="LISTEN", pid=11, laddr=("0.0.0.0", 8080), raddr=())
        snap = netwatch.snapshot(connections=lambda: [conn], proc_info=lambda pid: ("srv.exe", 2.0), with_arp=False)
        self.assertEqual(snap["listeners"]["srv.exe:8080"]["exe"], "")


if __name__ == "__main__":
    unittest.main()
