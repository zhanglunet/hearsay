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
                                  │ 每次保存学习者数据
                                  ▼
                       R2 存储桶（S3 兼容 API，learner/m3-learner.json）
```

三件事要知道：

- **Containers 不能单独从 Dockerfile 导入运行。** 它必须由一个 Worker 加 Durable Object 类管理。仓库根目录的 `wrangler.jsonc` 和 `worker/index.ts` 就是这一层。
- **容器磁盘是临时的。** 默认空闲 10 分钟后休眠，再启动时文件系统按镜像重建。没有持久卷可挂。学习者数据因此由容器里的 Python 代码镜像到 R2，见 `prototype/m3_learner/r2sync.py`：
  - 新容器启动、本地没有数据文件时，先从 R2 拉取。
  - 每次保存后，把同一份字节同步上传。
  - 删除学习者数据时，R2 上的对象一起删掉。
- **只跑一个实例。** `max_instances` 设为 1，因为只有一个学习者、一个数据文件，两个实例并发写同一个 R2 对象会互相覆盖。

镜像只含标准库代码，不含 whisperX、piper、faster-whisper 的模型：

- M1 的本机 ASR 在镜像里不可用，跟读页会提示改用浏览器语音识别或粘贴转写。
- M2 批处理默认关闭。
- `realtime.py` 不在 `start_all.py` 里，不随容器运行。

## 前提

- Cloudflare 账号开通 **Workers Paid** 计划，Containers 只在付费计划上可用。
- 运行 `wrangler deploy` 的地方要能用 Docker，因为它要在本机构建镜像再推送。用 Workers Builds 从 GitHub 自动部署时，构建环境自带 Docker。

## 第一次部署

### 1. 建 R2 存储桶和 API 令牌

1. Dashboard → **R2 对象存储** → 创建存储桶，例如 `hearsay-learner`。不要开启公开访问。
2. R2 → **管理 R2 API 令牌** → 创建令牌：
   - 权限选「对象读和写」
   - 范围只限上一步的存储桶
3. 记下这几项，下一步要用：
   - Access Key ID
   - Secret Access Key
   - 账户 ID，在 R2 概览页右侧

### 2. 连接 GitHub（Workers Builds）

Dashboard → **Workers 和 Pages** → 创建 → 导入存储库 → 选 `zhanglunet/hearsay`。

| 设置 | 值 |
|---|---|
| 项目名称 | `hearsay`，必须和 `wrangler.jsonc` 的 `name` 一致 |
| 生产分支 | `main` |
| 构建命令 | `npm ci` |
| 部署命令 | `npx wrangler deploy` |
| 根目录 | 仓库根目录，留空 |

非生产分支默认只上传版本，不更新镜像。只有生产分支跑 `wrangler deploy` 才会更新容器。

### 3. 设置密钥

Worker → 设置 → **变量和机密**，下面每一项都选「密钥」类型添加：

| 名字 | 值 |
|---|---|
| `HEARSAY_R2_ACCOUNT_ID` | 第 1 步的账户 ID |
| `HEARSAY_R2_BUCKET` | 存储桶名，例如 `hearsay-learner` |
| `HEARSAY_R2_ACCESS_KEY_ID` | 第 1 步的 Access Key ID |
| `HEARSAY_R2_SECRET_ACCESS_KEY` | 第 1 步的 Secret Access Key |
| `HEARSAY_LLM_API_KEY` | LLM 的 API key，不用真实 LLM 可以不设 |
| `HEARSAY_LLM_BASE_URL` | Anthropic 兼容的完整 Messages 端点，例如 `https://api.kimi.com/coding/v1/messages`；用官方 API 可以不设 |

也可以在本机命令行设置，效果相同：

```bash
npx wrangler secret put HEARSAY_R2_SECRET_ACCESS_KEY
```

要启用真实 LLM，还要改 `wrangler.jsonc` 里 `vars` 的 `HEARSAY_LLM`，从 `mock` 改成 `anthropic`，然后提交。每次部署都会用 `vars` 覆盖 Dashboard 上同名的明文变量，所以 `vars` 里的值要在文件里改。

容器只在启动时读环境变量。改了密钥以后，要等容器下次启动才生效：重新部署，或者等它空闲休眠后再访问。

### 4. 先配 Access，再公开

Dashboard → **Zero Trust** → Access → 应用程序 → 添加「自托管」应用：

- 域名填 Worker 的地址，例如 `hearsay.<你的子域>.workers.dev`，或者你绑定的自定义域名。
- 策略：只允许你自己的邮箱。

在这一步完成之前，不要把地址发给任何人。练习界面和 API 没有自己的登录，一旦公开，任何人都能读写你的学习者数据，也能消耗你的 LLM 额度。

### 5. 部署并验证

推送到 `main` 会触发 Workers Builds。首次部署后，按顺序检查：

1. 打开首页，确认 Access 先要求登录。
2. 把五个练习各点一遍：

   ```text
   /listen/  /shadow/  /retell/  /converse/  /plan/
   ```
3. 在复述或对话里完成一次练习，让学习者数据写入。然后在 R2 存储桶里确认 `learner/m3-learner.json` 出现了。
4. 等 10 分钟以上，让容器休眠，再打开 `/plan/`，确认刚才的复习卡还在。
5. 如果数据没有保存下来，到 Worker → 日志里搜 `[hearsay r2]`，看上传或拉取失败的原因。

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
| `HEARSAY_R2_ACCOUNT_ID` | Cloudflare 账户 ID | 无 | 密钥 |
| `HEARSAY_R2_BUCKET` | R2 存储桶名 | 无 | 密钥 |
| `HEARSAY_R2_ACCESS_KEY_ID` | R2 API 令牌 | 无 | 密钥 |
| `HEARSAY_R2_SECRET_ACCESS_KEY` | R2 API 令牌 | 无 | 密钥 |
| `HEARSAY_R2_KEY` | R2 对象键 | `learner/m3-learner.json` | `wrangler.jsonc` vars |
| `HEARSAY_R2_ENDPOINT` | 覆盖 R2 端点，只用于测试或其他 S3 兼容服务 | 由账户 ID 拼出 | 本地开发 |
| `HEARSAY_M3_STORE` | 容器内学习者数据文件路径 | `prototype/runtime/m3-learner.json` | 一般不改 |
| `HEARSAY_M2_BATCH` | 批处理开关 | 关闭 | 镜像里没有 whisperX，不要开 |

四个 `HEARSAY_R2_ACCOUNT_ID`、`BUCKET`、`ACCESS_KEY_ID`、`SECRET_ACCESS_KEY` 要全部设置才会启用 R2；少一个就退回纯本地存储，容器休眠后数据会丢。

## 安全提醒

- 先配 Access 再上线，原因见第 4 步。
- 密钥只走 Worker 密钥和容器环境变量，不进镜像，不进仓库，也不写日志。
- R2 令牌只给一个存储桶的对象读写权限，存储桶不要开公开访问。
- 学习者录音默认不经过服务端。M2 批处理开启时，录音才写进系统临时目录，处理结束后删除。

## 本地验证

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
