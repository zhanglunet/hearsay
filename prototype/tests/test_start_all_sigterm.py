"""回归：start_all.py 收到 SIGTERM 必须退出。

容器里它是 1 号进程，不注册处理函数时 SIGTERM 会被忽略；Cloudflare Containers 靠 SIGTERM
让空闲容器休眠，忽略它会让容器一直运行（2026-10-27 线上实测）。
这里用普通子进程测：处理函数在不在、能不能让进程正常退出，与是否 1 号进程无关。
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROTOTYPE = Path(__file__).resolve().parents[1]


class StartAllSigtermTests(unittest.TestCase):
    def test_exits_cleanly_on_sigterm(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HEARSAY_HOME_PORT="0", HEARSAY_HOST="127.0.0.1",
                       HEARSAY_M3_STORE=str(Path(tmp) / "learner.json"), PYTHONUNBUFFERED="1")
            for k in [k for k in env if k.startswith("HEARSAY_R2_")]:
                env.pop(k)
            proc = subprocess.Popen([sys.executable, "start_all.py"], cwd=PROTOTYPE, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                deadline = time.time() + 30
                started = False
                while time.time() < deadline:
                    line = proc.stdout.readline()
                    if "统一首页" in line:
                        started = True
                        break
                    if not line and proc.poll() is not None:
                        break
                self.assertTrue(started, "start_all.py 没有启动起来")
                proc.send_signal(signal.SIGTERM)
                code = proc.wait(timeout=10)
                self.assertEqual(code, 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                proc.stdout.close()


if __name__ == "__main__":
    unittest.main()
