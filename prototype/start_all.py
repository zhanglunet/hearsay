"""一键启动全部 Hearsay 切片与统一首页。

    cd prototype && python start_all.py

对外只有一个端口：统一首页（HEARSAY_HOME_PORT，默认 8764，监听 HEARSAY_HOST）。
各切片挂在路径前缀下：/listen/、/shadow/、/retell/、/converse/、/plan/。
切片本身只监听 127.0.0.1 的临时端口，由首页反向代理，不对外暴露。
各服务独立线程，Ctrl-C 全部停止。LLM 与存储配置仍走各服务原有的环境变量。
"""

import os
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


def start(name, server, servers):
    thread = threading.Thread(target=server.serve_forever, daemon=True, name=name)
    thread.start()
    servers.append((name, server, thread))


def main():
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
        print("\n正在停止…")
        for _name, server, _thread in servers:
            server.shutdown()
        for _name, server, _thread in servers:
            server.server_close()


if __name__ == "__main__":
    main()
