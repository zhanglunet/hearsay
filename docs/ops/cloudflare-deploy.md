# 部署到 Cloudflare Containers

本应用是 **Python 后端**，不是静态网页，所以 Cloudflare Pages 不适用，用的是 Cloudflare Containers。

## 架构

```
浏览器 ─► Cloudflare Access ─► Worker（worker/index.ts）
                                  │ getContainer(env.HEARSAY)，单例
                                  ▼
                       Durable Object：HearsayContainer
                                  │ defaultPort = 8764
                                  ▼
                     容器（仓库根目录 Dockerfile，python start_all.py）
                       统一首页 8764 兼网关 ─► /listen/ /shadow/ /retell/ /converse/ /plan/
                                  │ 每次保存学习者数据：S3 协议请求发往
                                  │ http://learner-store.hearsay.internal/…（公网不存在）
                                  ▼
                       Worker 的出站拦截（outboundByHost）
                                  │ R2 绑定 env.LEARNER_BUCKET，只认一个对象键
                                  ▼
                       R2 存储桶 hearsay-learner（learner/m3-learner.json）
```

三件事要知道：

- **Containers 不能单独从 Dockerfile 导入运行。** 它必须由一个 Worker 加 Durable Object 类管理。仓库根目录的 `wrangler.jsonc` 和 `worker/index.ts` 就是这一层。
- **容器磁盘是临时的。** 默认空闲 10 分钟后休眠，再启动时文件系统按镜像重建。没有持久卷可挂。学习者数据因此由容器里的 Python 代码镜像到 R2，见 `prototype/m3_learner/r2sync.py`：
  - 新容器启动、本地没有数据文件时，先从 R2 拉取。
  - 每次保存后，把同一份字节同步上传。
  - 删除学习者数据时，R2 上的对象一起删掉。

  容器不持有任何 R2 密钥。它的读写请求发往一个公网不存在的内部主机名，被 Worker 拦截后经 R2 绑定读写；拦截处理只认 `/<桶>/<键>` 这一个对象，其他路径返回 403。所以不需要建 R2 API 令牌。
- **只跑一个实例。** 只有一个学习者、一个数据文件，两个实例并发写同一个 R2 对象会互相覆盖。容器用的是 `durable_object` 调度策略（本账号不允许 `default`），它不支持 `max_instances`，所以单实例靠 Worker 始终用同一个名字取实例来保证。
- **规格是 `lite`。** 1/16 vCPU、256 MiB 内存，这是 `durable_object` 策略下的默认值，`@cloudflare/containers` 0.3.7 也不支持改它。2026-10-27 在同样的资源限制下实测：启动 4 秒，所有页面响应在 35 毫秒内，内存 18.7 MiB。以后要在容器里跑 whisperX 之类的模型，就得换更大的规格。

镜像只含标准库代码，不含 whisperX、piper、faster-whisper 的模型：

- M1 的本机 ASR 在镜像里不可用，跟读页会提示改用浏览器语音识别或粘贴转写。
- M2 批处理默认关闭。
- `realtime.py` 不在 `start_all.py` 里，不随容器运行。

## 前提

- Cloudflare 账号开通 **Workers Paid** 计划，Containers 只在付费计划上可用。
- 运行 `wrangler deploy` 的地方要能用 Docker，因为它要在本机构建镜像再推送。用 Workers Builds 从 GitHub 自动部署时，构建环境自带 Docker。

## 第一次部署

下面用本机命令行部署，需要先 `npx wrangler login` 登录。也可以改用 Workers Builds 从 GitHub 自动部署，见本节末尾。

### 1. 建 R2 存储桶

```bash
npx wrangler r2 bucket create hearsay-learner
```

桶名要和 `wrangler.jsonc` 里的 `HEARSAY_R2_BUCKET` 与 `r2_buckets[].bucket_name` 一致。不要开启公开访问。

### 2. 部署，先不开公网地址

`wrangler.jsonc` 里 `workers_dev` 是 `false`，所以第一次部署后 Worker 没有可访问的地址。

```bash
npm ci
npx wrangler deploy
```

需要本机 Docker 在运行，wrangler 会在本机构建镜像再推送。

### 3. 设置 LLM 密钥（可选）

不用真实 LLM 可以跳过，对话等切片会用离线的 mock。

```bash
npx wrangler secret put HEARSAY_LLM_API_KEY
npx wrangler secret put HEARSAY_LLM_BASE_URL
```

`HEARSAY_LLM_BASE_URL` 要填 Anthropic 兼容的完整 Messages 端点，例如 `https://api.kimi.com/coding/v1/messages`；用官方 API 可以不设。

要启用真实 LLM，还要把 `wrangler.jsonc` 里 `vars` 的 `HEARSAY_LLM` 从 `mock` 改成 `anthropic`，再部署。每次部署都会用 `vars` 覆盖 Dashboard 上同名的明文变量，所以 `vars` 里的值要在文件里改。

容器只在启动时读环境变量。改了密钥以后，要等容器下次启动才生效：重新部署，或者等它空闲休眠后再访问。

### 4. 先配 Access，再打开公网地址

1. Dashboard → **Zero Trust** → Access → 应用程序 → 添加「自托管」应用：
   - 域名填 `hearsay.<你的子域>.workers.dev`，或者你绑定的自定义域名。
   - 策略：只允许你自己的邮箱。
2. 把 `wrangler.jsonc` 里的 `workers_dev` 改成 `true`，再部署一次。

顺序不能反。练习界面和 API 没有自己的登录，一旦公开，任何人都能读写你的学习者数据，也能消耗你的 LLM 额度。

当前部署（2026-10-27）的状态：Access 应用「hearsay 听说练习」用的是 Workers 类型的目标，直接绑定 `hearsay` 这个 Worker，类型为「Worker 的生产和预览 URL」，策略 `hearsay-owner-only` 只放行账号所有者的邮箱。之后 `workers_dev` 已改为 `true`，地址是 `hearsay.zhanglu-net.workers.dev`。

### 5. 验证

1. 打开首页，确认 Access 先要求登录。
2. 把五个练习各点一遍：

   ```text
   /listen/  /shadow/  /retell/  /converse/  /plan/
   ```
3. 在复述或对话里完成一次练习，让学习者数据写入，然后确认对象出现了：

   ```bash
   npx wrangler r2 object get hearsay-learner/learner/m3-learner.json --remote --pipe
   ```
4. 等 10 分钟以上，让容器休眠，再打开 `/plan/`，确认刚才的记录还在。
5. 如果数据没有保存下来，用 `npx wrangler tail hearsay` 看实时日志，搜 `[hearsay r2]`。

### 改用 Workers Builds（可选）

Dashboard → **Workers 和 Pages** → `hearsay` → 设置 → 构建 → 连接 `zhanglunet/hearsay`：

| 设置 | 值 |
|---|---|
| 生产分支 | `main` |
| 构建命令 | `npm ci` |
| 部署命令 | `npx wrangler deploy` |
| 根目录 | 留空 |

之后推送到 `main` 就会自动部署。非生产分支默认只上传版本，不更新镜像。

## 环境变量参考

容器内读取的变量如下。Worker 只把下表里的变量传进容器，未设置的不传。

| 变量 | 作用 | 默认 | 在哪设置 |
|---|---|---|---|
| `HEARSAY_HOST` | 首页（网关）监听地址；切片始终只监听 127.0.0.1 | 镜像里已设 `0.0.0.0`，本地默认 127.0.0.1 | Dockerfile |
| `HEARSAY_HOME_PORT` | 统一首页端口 | 8764 | Dockerfile |
| `HEARSAY_LLM` | `mock` 或 `anthropic` | `mock`（离线） | `wrangler.jsonc` vars |
| `HEARSAY_LLM_MODEL` | 模型名 | `claude-haiku-4-5-20251001` | `wrangler.jsonc` vars |
| `HEARSAY_LLM_API_KEY` | LLM key（优先） | 无 | 密钥 |
| `HEARSAY_ANTHROPIC_API_KEY` | 旧变量名，仍兼容；Worker 不传它，新部署用上一行 | 无 | 本地开发 |
| `ANTHROPIC_BASE_URL` | 只对 `realtime.py` 有效（由 Anthropic SDK 读取），容器里用不到 | 无 | 本地开发 |
| `HEARSAY_LLM_BASE_URL` | Anthropic 兼容的完整 Messages 端点，不是只到域名 | `https://api.anthropic.com/v1/messages` | 密钥 |
| `HEARSAY_R2_BUCKET` | R2 存储桶名 | `hearsay-learner` | `wrangler.jsonc` vars |
| `HEARSAY_R2_KEY` | R2 对象键 | `learner/m3-learner.json` | `wrangler.jsonc` vars |
| `HEARSAY_R2_ENDPOINT` | 容器内的存储端点 | Worker 固定传 `http://learner-store.hearsay.internal` | Worker 自动设置 |
| `HEARSAY_R2_ACCOUNT_ID`、`HEARSAY_R2_ACCESS_KEY_ID`、`HEARSAY_R2_SECRET_ACCESS_KEY` | 在 Cloudflare 上只是占位，签名由 Worker 忽略；在别的 S3 兼容服务上才是真凭据 | Worker 传占位值 | Worker 自动设置 |
| `HEARSAY_M3_STORE` | 容器内学习者数据文件路径 | `prototype/runtime/m3-learner.json` | 一般不改 |
| `HEARSAY_M2_BATCH` | 批处理开关 | 关闭 | 镜像里没有 whisperX，不要开 |

在 Cloudflare 上，R2 相关变量全部由 Worker 自动传入，不用手动设置。在别处运行容器时，四个 `HEARSAY_R2_ACCOUNT_ID`、`BUCKET`、`ACCESS_KEY_ID`、`SECRET_ACCESS_KEY` 要全部设置才会启用镜像；少一个就退回纯本地存储。

## 安全提醒

- 先配 Access 再打开公网地址，原因见第 4 步。
- LLM 密钥只走 Worker 密钥和容器环境变量，不进镜像，不进仓库，也不写日志。
- 容器不持有 R2 密钥，只能经 Worker 读写一个对象键。存储桶不要开公开访问。
- 学习者录音默认不经过服务端。M2 批处理开启时，录音才写进系统临时目录，处理结束后删除。

## 本地验证

`npx wrangler dev` 会在本机 Docker 里跑容器和本地 R2。2026-10-27 在 OrbStack 上实测：

- 首次启动时，经 Worker 访问各页面、写入数据、数据落进本地 R2 都正常。
- 重启 `wrangler dev` 后，全新容器能从本地 R2 拉回数据，但 Worker 到容器的入站请求有时会卡住。这是本地开发环境的问题，和项目代码无关。遇到时删掉 `workerd-hearsay-*` 容器再启动。
- 不要用 `docker rm` 直接删正在运行的容器来模拟休眠：Durable Object 不知道容器没了，会一直报「Network connection lost」。

不连 Cloudflare，只校验配置和打包：

```bash
npm ci
npm run check
```

本地跑容器，需要 Docker：

```bash
docker build -t hearsay .
docker run --rm -p 8764:8764 hearsay
```

然后打开 `http://127.0.0.1:8764/`。

## 其他选择

如果不想用 Containers，可以把同一个 Dockerfile 部署到一台带持久磁盘的 VPS 或 Fly.io，Cloudflare 只负责域名和 Access。那样不需要 R2，不设 `HEARSAY_R2_*` 即可。
