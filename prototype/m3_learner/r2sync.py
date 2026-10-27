"""把学习者数据文件镜像到 Cloudflare R2（S3 兼容 API），只用标准库。

为什么需要：Cloudflare Containers 的磁盘是临时的，容器空闲休眠后再启动，
文件系统会按镜像重建，`prototype/runtime/` 里的学习者数据随之丢失。

做法：本地 JSON 文件仍是容器存活期间的工作副本；R2 是持久副本。
- 本地文件不存在时（新容器），先从 R2 拉取。
- 每次保存后把同一份字节上传到 R2。
- 删除学习者数据时，同时删除 R2 上的对象。

只有设置了下面四个环境变量才启用，否则全部是空操作（本地开发和 CI 不受影响）：

    HEARSAY_R2_ACCOUNT_ID        Cloudflare 账户 ID
    HEARSAY_R2_BUCKET            R2 存储桶名
    HEARSAY_R2_ACCESS_KEY_ID     R2 API 令牌的 Access Key ID
    HEARSAY_R2_SECRET_ACCESS_KEY R2 API 令牌的 Secret Access Key

可选：

    HEARSAY_R2_KEY       对象键，默认 learner/m3-learner.json
    HEARSAY_R2_ENDPOINT  覆盖端点（测试或 S3 兼容的本地服务），
                         默认 https://<ACCOUNT_ID>.r2.cloudflarestorage.com

密钥只从环境变量读，不写日志、不进异常信息。
"""

import hashlib
import hmac
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

REGION = "auto"
SERVICE = "s3"
DEFAULT_KEY = "learner/m3-learner.json"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
TIMEOUT_S = 15


class R2Error(RuntimeError):
    """R2 请求失败。消息里不含密钥。"""


# ---------------- SigV4 ----------------

def _hmac(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _uri_encode_path(path):
    # S3 规范：逐段编码，保留 '/'，只放过 unreserved 字符
    return "/".join(urllib.parse.quote(seg, safe="-_.~") for seg in path.split("/"))


def sign(method, url, headers, payload_hash, access_key_id, secret_access_key,
         region, service, amz_date):
    """返回 Authorization 头的值。

    headers 必须已包含要签名的所有头（含 host、x-amz-date）；全部参与签名。
    amz_date 形如 20130524T000000Z。
    """
    parts = urllib.parse.urlsplit(url)
    canonical_uri = _uri_encode_path(parts.path or "/")
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    canonical_query = "&".join(
        f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
        for k, v in sorted(query))
    norm = {k.lower().strip(): " ".join(str(v).split()) for k, v in headers.items()}
    signed = sorted(norm)
    canonical_headers = "".join(f"{k}:{norm[k]}\n" for k in signed)
    signed_headers = ";".join(signed)
    canonical_request = "\n".join([method, canonical_uri, canonical_query,
                                   canonical_headers, signed_headers, payload_hash])
    date = amz_date[:8]
    scope = f"{date}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()])
    k = _hmac(("AWS4" + secret_access_key).encode("utf-8"), date)
    k = _hmac(k, region)
    k = _hmac(k, service)
    k = _hmac(k, "aws4_request")
    signature = hmac.new(k, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return (f"AWS4-HMAC-SHA256 Credential={access_key_id}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}")


# ---------------- 客户端 ----------------

@dataclass(frozen=True)
class R2Config:
    endpoint: str
    bucket: str
    key: str
    access_key_id: str
    secret_access_key: str

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        account = env.get("HEARSAY_R2_ACCOUNT_ID", "").strip()
        bucket = env.get("HEARSAY_R2_BUCKET", "").strip()
        akid = env.get("HEARSAY_R2_ACCESS_KEY_ID", "").strip()
        secret = env.get("HEARSAY_R2_SECRET_ACCESS_KEY", "").strip()
        endpoint = env.get("HEARSAY_R2_ENDPOINT", "").strip()
        if not endpoint and account:
            endpoint = f"https://{account}.r2.cloudflarestorage.com"
        if not (endpoint and bucket and akid and secret):
            return None
        key = env.get("HEARSAY_R2_KEY", "").strip().lstrip("/") or DEFAULT_KEY
        return cls(endpoint.rstrip("/"), bucket, key, akid, secret)


class R2Client:
    def __init__(self, config, now=None):
        self.config = config
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _url(self):
        c = self.config
        return f"{c.endpoint}/{c.bucket}/{c.key}"

    def _request(self, method, body=None, content_type=None):
        url = self._url()
        payload = body or b""
        payload_hash = hashlib.sha256(payload).hexdigest() if body else EMPTY_SHA256
        amz_date = self._now().strftime("%Y%m%dT%H%M%SZ")
        headers = {"host": urllib.parse.urlsplit(url).netloc,
                   "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
        if content_type:
            headers["content-type"] = content_type
        headers["Authorization"] = sign(
            method, url, {k: v for k, v in headers.items()}, payload_hash,
            self.config.access_key_id, self.config.secret_access_key,
            REGION, SERVICE, amz_date)
        send = {k: v for k, v in headers.items() if k != "host"}
        req = urllib.request.Request(url, data=body if body else None,
                                     headers=send, method=method)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise R2Error(f"R2 {method} 连接失败：{type(e).__name__}") from None

    def get(self):
        """返回对象字节；对象不存在返回 None。"""
        status, data = self._request("GET")
        if status == 200:
            return data
        if status == 404:
            return None
        raise R2Error(f"R2 GET 失败：HTTP {status}")

    def put(self, data):
        status, _ = self._request("PUT", body=data, content_type="application/json")
        if status not in (200, 201):
            raise R2Error(f"R2 PUT 失败：HTTP {status}")

    def delete(self):
        status, _ = self._request("DELETE")
        if status not in (200, 204, 404):
            raise R2Error(f"R2 DELETE 失败：HTTP {status}")


def client_from_env(environ=None):
    config = R2Config.from_env(environ)
    return R2Client(config) if config else None


def warn(message):
    print(f"[hearsay r2] {message}", file=sys.stderr, flush=True)
