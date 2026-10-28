# 公开门户站设计（hearsay.fans）

日期：2026-10-28　状态：待确认

## 1. 为什么做

现在的 Hearsay 只有一个需要登录的应用（Cloudflare Access 只放行作者邮箱），外人打开 hearsay.fans 只看到登录页，不知道这是什么。需要一个**任何人都能打开的公开门户站**：介绍 Hearsay 是什么、有哪些功能，看完的人可以**申请试用**。

现阶段应用是单用户的（学习数据只有 R2 里的一个文件、容器只有一个实例），不能真的给别人开通。所以申请**只是登记意向**：作者每收到一条申请就收到一封邮件，等以后做完多用户改造再决定开通谁。多用户改造是另一个独立项目，不在本设计范围内。

成功的样子：陌生人用手机打开 hearsay.fans，一分钟内看懂 Hearsay 和多邻国有什么不同，用不到 30 秒留下邮箱；作者的邮箱随即收到通知。

## 2. 目标 / 非目标 / 反目标

**目标**
- hearsay.fans（和 www.hearsay.fans）变成公开门户站，手机优先，单页。
- 应用搬到 app.hearsay.fans，继续受 Access 保护。
- 申请表单：提交即登记，存起来，并给作者发邮件通知。

**非目标**
- 不做账户、登录、自助开通；不自动把申请人加进 Access。
- 不改现有应用的功能和学习数据。
- 不做英文版，不放产品截图或视频。
- 不做后台管理页（看名单靠邮件，必要时用 `wrangler d1 execute` 查）。

**反目标（做成这样就算失败，即使技术上能跑）**
- 应用在任何时刻出现在不受 Access 保护的公开地址上（包括迁移过程中）。
- 门户站的访问唤醒了应用容器（门户流量不应产生容器费用）。
- 申请流程在手机上需要缩放、横向滚动，或要填三项以上信息。
- 向申请人承诺具体的开通时间。

## 3. 已定的决定（作者确认过的）

- 地址：**hearsay.fans 放门户站，应用搬到 app.hearsay.fans**。作者接受原书签变成门户页、要多点一次「登录」。
- 申请只是「登记意向」。
- 每来一条申请，发邮件到作者邮箱 zhanglu.net@gmail.com。
- 布局选 **B · 先讲清楚再申请**（草图见 `.superpowers/brainstorm/` 下的 `layout.html`）：
  1. 首屏：「HEARSAY · 听说」标志、标语「听得懂，说得出」、一句和多邻国对比的定位、一个「申请试用 ↓」按钮（平滑滚动到表单）。右上角一个不显眼的「登录」链接指向 https://app.hearsay.fans 。
  2. 「一条循环」：听 → 跟读 → 复述 → 对话，四张卡片，每张一句说明。
  3. 理念：说错的话变成复习、在新对话里再用一次；进度是「能做什么」（CEFR can-do），不是宝石；针对中文母语者的常见难点。
  4. 申请表单（页面底部）：邮箱（必填）、「想练什么」（可选，一行文本）、提交按钮。提交后在原位显示「已登记，开放时会发邮件通知你」。
- 越简单越好，手机打开就能申请。

## 4. 我做的决定（作者没说，可推翻）

- **只做中文**页面，文案直接点名多邻国做对比（README 第一节已有现成论述可改写）。
- **不放截图**，用 emoji/简单图标加文字。
- **防刷**（作者确认：申请人主要在中国大陆，Turnstile 脚本 `challenges.cloudflare.com` 在大陆可能加载慢或失败，不能让它挡住真实用户）：
  - 表单加 Cloudflare Turnstile（托管模式）。前端等它最多 5 秒；拿到 token 就随表单提交，拿不到也照样提交，不让用户卡住。
  - 服务端：token 校验通过 → 正常入库；**没有 token 或校验失败 → 仍然入库**，记录 `verified = 0`，通知邮件标题加「[未验证]」。
  - 另两层不依赖 Turnstile 的防线：隐藏字段（蜜罐，被填了就假装成功、不入库不发信）；Workers Rate Limiting 绑定按来访 IP 限流（同一 IP 每 60 秒最多 3 次（该绑定的窗口只支持 10 秒或 60 秒），超过返回「提交太频繁，请稍后再试」）。IP 只用作限流键，不入库。
- **重复提交**：同一邮箱（小写、去首尾空格后）只记一次，再次提交同样显示成功，但不再发通知邮件，也不覆盖原记录。
- **独立 Worker**：门户站做成单独的 Worker `hearsay-portal`（仓库新目录 `portal/`），用 Workers 静态资源托管页面，`POST /api/apply` 处理申请。理由：门户和应用互不影响，门户流量永远不会唤醒容器（反目标第 2 条），Access 也按主机名清楚地分开。
- **存储**：D1 数据库 `hearsay-portal`，一张表：

  | 列 | 说明 |
  |---|---|
  | `email` | 主键，规范化后的邮箱 |
  | `note` | 「想练什么」，最多 200 字 |
  | `created_at` | ISO 时间 |
  | `country` | `request.cf.country`，便于了解来源；不存 IP |
  | `verified` | 1 = Turnstile 校验通过，0 = 没拿到或没通过 |

- **发邮件**：Cloudflare Email Routing 的 `send_email` 绑定，发件人 `noreply@hearsay.fans`，收件人限定为作者邮箱（`destination_address` 写死在绑定里）。邮件正文：邮箱、想练什么、国家、时间。发信失败不影响申请成功（记录已入库，日志里留一条错误）。
- **旧地址**：门户 Worker 收到 hearsay.fans 上应用的旧路径（`/listen/`、`/shadow/`、`/retell/`、`/converse/`、`/plan/` 及其子路径）时，301 跳到 app.hearsay.fans 的同一路径，旧书签不失效。www.hearsay.fans 301 跳到 hearsay.fans。门户的 workers.dev 地址关闭（`workers_dev: false`）。
- **样式**：沿用应用的青绿配色（`#0c5c5c`）和 system-ui 字体；无前端框架、无外部字体，纯 HTML/CSS + 一小段 JS。
- **隐私说明**：表单下方一行小字：「只用于开放时通知你，不会用于其他用途。」

## 5. 迁移顺序（保证应用始终在 Access 后面）

部署方式：应用和门户都**在本机手动 `npx wrangler deploy`**，没有接 Workers Builds（推到 `main` 不会自动部署）。所以下面每一步都可以先部署、检查通过再做下一步；代码合进 `main` 的时机不影响线上顺序。门户也保持手动部署。

1. 在 Access 应用「hearsay 听说练习」里**加上** app.hearsay.fans（先加，不删旧的）。
2. 应用 Worker（`wrangler.jsonc`）的 `routes` 加上 app.hearsay.fans，部署；确认未登录访问 app.hearsay.fans 跳到 Access 登录页。
3. 应用 Worker 的 `routes` **去掉** hearsay.fans 和 www.hearsay.fans，部署。
4. 门户 Worker 绑定 hearsay.fans 和 www.hearsay.fans，部署。
5. 在 Access 应用里**去掉** hearsay.fans 和 www.hearsay.fans；确认未登录能打开门户站、app.hearsay.fans 仍然要登录。
6. 更新 `docs/ops/cloudflare-deploy.md` 与 README 里的地址。

第 3、4 步之间 hearsay.fans 会有短暂不可用，可以接受；任何一步都不能让应用出现在没有 Access 的地址上。

## 6. 需要作者在 Cloudflare 后台亲手做的

- 在 hearsay.fans 上开通 **Email Routing**（会添加 MX/TXT 记录；2026-10-28 查过 hearsay.fans 没有 MX 和 TXT 记录，不会切断现有邮件），并验证收件地址 zhanglu.net@gmail.com（Gmail 里点确认链接）。
- 创建 **Turnstile** 站点（域名 hearsay.fans、www.hearsay.fans），把 secret 用 `wrangler secret put TURNSTILE_SECRET --name hearsay-portal` 设置；site key 是公开的，写进页面。
- Access 应用的主机名增删（第 5 节第 1、5 步），可由 Claude 用浏览器代做，登录由作者处理。

## 7. 验收

- 手机宽度（375px）下：无横向滚动；首屏能看到标语和「申请试用」按钮；按钮和输入框高度 ≥ 44px。
- 未登录访问 hearsay.fans、www.hearsay.fans 直接看到门户站；访问 app.hearsay.fans 跳到 Access 登录；hearsay.zhanglu-net.workers.dev 仍要登录。
- 提交一个新邮箱：页面显示成功，D1 多一条记录，作者邮箱收到通知。同一邮箱再提交：显示成功，不新增记录、不再发邮件。
- 邮箱格式不对、note 超长：返回明确的中文错误，不入库。
- 屏蔽 `challenges.cloudflare.com` 后提交：仍然成功，记录 `verified = 0`，通知邮件带「[未验证]」。同一 IP 60 秒内第 4 次提交被拒。
- 作者用大陆网络（手机流量）实测一次：页面打开和提交都在 30 秒内完成。
- 页面不引用任何大陆访问不稳的外部资源（外部字体、CDN 脚本等），除 Turnstile 外全部同域。
- 门户访问期间应用容器不被唤醒（容器日志里没有新的启动）。

## 8. 留给实现者

- 具体文案（以第 3 节结构和 README 第一、二节为素材）、图标选择、细节间距。
- `portal/` 的目录结构、测试方式（建议与 `worker/voice.test.mjs` 一样用 node 跑纯函数测试：邮箱规范化、输入校验、重复判断）。
- 是否给门户站加 favicon、Open Graph 标签（建议加，分享到微信/社交平台时有标题和描述）。
