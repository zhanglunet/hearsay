/**
 * Hearsay 在 Cloudflare Containers 上的入口 Worker。
 *
 * 结构：所有请求 → 这个 Worker → 单例 Durable Object（HearsayContainer）→ 容器内 8764 端口
 * （统一首页兼网关，再按 /listen/ /shadow/ /retell/ /converse/ /plan/ 转给各切片）。
 *
 * 容器磁盘是临时的：空闲 sleepAfter 后休眠，再启动时文件系统按镜像重建。
 * 学习者数据靠容器内的 Python 代码镜像到 R2（prototype/m3_learner/r2sync.py），
 * 这里只负责把 R2 凭据和 LLM 配置作为环境变量传进容器。
 *
 * 访问控制不在这里做：上线前在 Cloudflare Zero Trust 里给这个 Worker 的域名配 Access。
 */
import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  HEARSAY: DurableObjectNamespace<HearsayContainer>;
  // wrangler.jsonc 的 vars（非敏感默认值）
  HEARSAY_LLM: string;
  HEARSAY_LLM_MODEL: string;
  HEARSAY_R2_KEY: string;
  // wrangler secret put / Dashboard「密钥」（不写进仓库）
  HEARSAY_LLM_API_KEY?: string;
  HEARSAY_LLM_BASE_URL?: string;
  HEARSAY_R2_ACCOUNT_ID?: string;
  HEARSAY_R2_BUCKET?: string;
  HEARSAY_R2_ACCESS_KEY_ID?: string;
  HEARSAY_R2_SECRET_ACCESS_KEY?: string;
}

// 只把这些变量传进容器；未设置的不传（容器内按默认值处理）
const PASS_THROUGH = [
  "HEARSAY_LLM",
  "HEARSAY_LLM_MODEL",
  "HEARSAY_LLM_API_KEY",
  "HEARSAY_LLM_BASE_URL",
  "HEARSAY_R2_ACCOUNT_ID",
  "HEARSAY_R2_BUCKET",
  "HEARSAY_R2_ACCESS_KEY_ID",
  "HEARSAY_R2_SECRET_ACCESS_KEY",
  "HEARSAY_R2_KEY",
] as const;

export class HearsayContainer extends Container<Env> {
  // 统一首页端口；请求会被挂起直到容器在这个端口上开始监听
  defaultPort = 8764;
  // 空闲 10 分钟休眠。学习者数据每次保存都会同步上传 R2，休眠不丢数据
  sleepAfter = "10m";

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    const vars: Record<string, string> = {};
    for (const name of PASS_THROUGH) {
      const value = env[name];
      if (typeof value === "string" && value !== "") vars[name] = value;
    }
    this.envVars = vars;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 单学习者、单数据文件：所有请求都进同一个实例，避免两个容器并发写同一个 R2 对象
    return getContainer(env.HEARSAY).fetch(request);
  },
};
