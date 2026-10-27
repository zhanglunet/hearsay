"""各服务共用的 HTTP 服务器类。

为什么不直接用 http.server.ThreadingHTTPServer：
它的 server_bind() 会调用 socket.getfqdn(host) 反查本机完整主机名，只为了填 server_name。
监听 0.0.0.0 时，反查的是容器自己的主机名。Cloudflare Containers 的主机名是一段很长的哈希，
单个标签超过 DNS 的 63 字符上限，idna 编码抛 UnicodeError("label too long")，服务起不来，
容器随即退出（2026-10-27 线上实测）。本项目不使用 server_name，这里直接跳过反查。
"""

import socketserver
from http.server import ThreadingHTTPServer


class HearsayHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host or "localhost"
        self.server_port = port
