"""#61 — get_top_processes('memory') não quebra com memory_percent None (AccessDenied)."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests._stubs import install

install()

import core.SystemInfo as sysinfo_mod  # noqa: E402


def _proc(name, mem):
    return SimpleNamespace(info={"pid": 1, "name": name, "memory_percent": mem})


class TestTopMemory(unittest.TestCase):
    def test_none_memory_percent_goes_last(self):
        procs = [_proc("protegido.exe", None), _proc("chrome.exe", 12.5), _proc("code.exe", 3.0)]
        monitor = sysinfo_mod.SystemInfo.__new__(sysinfo_mod.SystemInfo)  # sem threads/hardware
        with patch.object(sysinfo_mod.psutil, "process_iter", return_value=procs):
            top = monitor.get_top_processes("memory", limit=3)
        self.assertEqual(top, ["chrome.exe (12.5%)", "code.exe (3.0%)", "protegido.exe (0.0%)"])


if __name__ == "__main__":
    unittest.main()
