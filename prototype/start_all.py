"""一键启动全部 Hearsay 切片与统一首页。

    cd prototype && python start_all.py

对外只有一个端口：统一首页（HEARSAY_HOME_PORT，默认 8764，监听 HEARSAY_HOST）。
各切片挂在路径前缀下：/listen/、/shadow/、/retell/、/converse/、/plan/。
切片本身只监听 127.0.0.1 的临时端口，由首页反向代理，不对外暴露。
各服务独立线程，Ctrl-C 或 SIGTERM 全部停止。LLM 与存储配置仍走各服务原有的环境变量。

为什么要处理 SIGTERM：容器里本进程是 1 号进程。Linux 不对 1 号进程执行信号的默认动作，
没有注册处理函数时 SIGTERM 会被直接忽略。Cloudflare Containers 空闲 sleepAfter 后
就是发 SIGTERM 让容器休眠，忽略它会让容器一直运行、一直计费（2026-10-27 线上实测）。
"""

import os
import signal
import threading

from home.server import make_server as make_home
from listen.server import make_server as make_listen
from m1_shadow.server import make_server as make_shadow
from m2_dialogue.server import make_server as make_dialogue
from m4_plan.server import make_server as make_plan
from retell.server import make_server as make_retell

# 前缀与首页 SLICES 的 kind 一致
SLICES = [("listen", make_listen), ("shadow", make_shadow), ("retell", make_retell),
          ("converse", make_dialogue), ("plan", make_plan)]
INTERNAL_HOST = "127.0.0.1"


def _stop_on_sigterm(_signum, _frame):
    # 复用 Ctrl-C 的停止路径：关掉全部服务后正常退出
    raise KeyboardInterrupt


def start(name, server, servers):
    thread = threading.Thread(target=server.serve_forever, daemon=True, name=name)
    thread.start()
    servers.append((name, server, thread))


def main():
    signal.signal(signal.SIGTERM, _stop_on_sigterm)
    servers = []
    routes = {}
    for kind, factory in SLICES:
        server = factory(0, host=INTERNAL_HOST)
        routes[kind] = (INTERNAL_HOST, server.server_address[1])
        start(kind, server, servers)
    home_port = int(os.environ.get("HEARSAY_HOME_PORT", "8764"))
    home = make_home(home_port, routes=routes)
    start("home", home, servers)
    for kind, _factory in SLICES:
        print(f"{kind}: http://127.0.0.1:{home_port}/{kind}/")
    print(f"\n统一首页：http://127.0.0.1:{home_port}/ （Ctrl-C 停止全部）")
    try:
        for _name, _server, thread in servers:
            thread.join()
    except KeyboardInterrupt:
        print("\n正在停止…", flush=True)
        for _name, server, _thread in servers:
            server.shutdown()
        for _name, server, _thread in servers:
            server.server_close()


if __name__ == "__main__":
    main()
