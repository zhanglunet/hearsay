# 从 GitHub 部署到 Cloudflare

本应用是 **Python 后端 + 多端口服务**，不是静态网页。因此：

- **Cloudflare Pages 不适用**（只托管静态文件，不能跑 Python）。
- 选 **Cloudflare Containers**（若你的账号已开放该能力）或一台 VPS。
- 上公网前建议先配 **Cloudflare Access（Zero Trust）**，因为服务会用到 LLM key 和学习者数据。

## 镜像

仓库根目录有 `Dockerfile`（Python 3.11 slim，无第三方依赖，启动 `start_all.py`）。
镜像只含标准库代码，**不含 whisperX / piper / faster-whisper 模型**：
- M1 的本机 ASR 默认关闭（装了 faster-whisper 才启用）
- M2 批处理默认关闭（`HEARSAY_M2_BATCH=whisperx` 时才需要 whisperX 环境）
- piper TTS 只用于 `realtime.py`（不在 `start_all.py` 里），需要的话自行下载语音模型到 `~/.cache/pipecat/piper`

## GitHub → Cloudflare Containers

1. 在 Cloudflare Dashboard 的 **Workers & Pages → Containers** 中选择从 GitHub 导入仓库
   （第一次用先连接 GitHub 账号并授权 `zhanglunet/hearsay`）。
2. 构建方式选 **Dockerfile**（仓库根目录）。
3. 环境变量按下面配置，服务监听 `0.0.0.0`（`HEARSAY_HOST` 已内置）。
4. 暴露 **8764**（统一首页），其余端口按需开放（M1 8765、M2 8766、M4 8767、retell 8768、listen 8769）。
5. 学习者数据在容器内 `prototype/runtime/m3-learner.json`，**重建会丢失**；
   要保留就挂持久卷到 `/app/prototype/runtime`。

## 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `HEARSAY_HOST` | 监听地址 | 容器内已设 `0.0.0.0`（本地默认 127.0.0.1） |
| `HEARSAY_HOME_PORT` | 统一首页端口 | 8764 |
| `HEARSAY_LLM` | mock / anthropic | mock（离线） |
| `HEARSAY_LLM_API_KEY` | LLM key（优先） | 无 |
| `HEARSAY_ANTHROPIC_API_KEY` | 兼容旧变量名 | 无 |
| `ANTHROPIC_BASE_URL` | Anthropic 兼容端点 | https://api.anthropic.com |
| `HEARSAY_LLM_MODEL` | 模型名 | claude-haiku-4-5-20251001 |
| `HEARSAY_M3_STORE` | 学习者数据文件 | prototype/runtime/m3-learner.json |
| `HEARSAY_M2_BATCH` | 批处理开关 | 关闭 |

## 安全提醒

- `HEARSAY_HOST=0.0.0.0` 会让整个练习界面和 API 暴露公网，**先加 Access 再上线**。
- 密钥只走环境变量，不进镜像、不进仓库。
- 学习者录音默认不经过服务端；M2 批处理开启时才写系统临时目录并在结束后删除。

## 本地构建验证

```bash
docker build -t hearsay .
docker run --rm -p 8764:8764 -p 8765:8765 -p 8766:8766 -p 8767:8767 -p 8768:8768 -p 8769:8769 hearsay
# 打开 http://127.0.0.1:8764/
```
