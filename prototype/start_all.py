"""一键启动全部 Hearsay 切片与统一首页。

    cd prototype && python start_all.py

统一首页在 8764；其余端口：M1 8765、M2 8766、M4 8767、retell 8768、listen 8769。
各服务独立线程，Ctrl-C 全部停止。LLM 与存储配置仍走各服务原有的环境变量。
"""

import threading

from home.server import make_server as make_home
from listen.server import make_server as make_listen
from m1_shadow.server import make_server as make_shadow
from m2_dialogue.server import make_server as make_dialogue
from m4_plan.server import make_server as make_plan
from retell.server import make_server as make_retell

PORTS = [("home", 8764), ("shadow", 8765), ("dialogue", 8766),
         ("plan", 8767), ("retell", 8768), ("listen", 8769)]


def main():
    servers = []
    for name, port in PORTS:
        if name == "home":
            server = make_home(port)
        elif name == "shadow":
            server = make_shadow(port)
        elif name == "dialogue":
            server = make_dialogue(port)
        elif name == "plan":
            server = make_plan(port)
        elif name == "retell":
            server = make_retell(port)
        else:
            server = make_listen(port)
        thread = threading.Thread(target=server.serve_forever, daemon=True, name=name)
        thread.start()
        servers.append((name, server, thread))
        print(f"{name}: http://127.0.0.1:{port}/")
    print("\n统一首页：http://127.0.0.1:8764/ （Ctrl-C 停止全部）")
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
