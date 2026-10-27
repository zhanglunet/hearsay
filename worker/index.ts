/**
 * Hearsay 在 Cloudflare Containers 上的入口 Worker。
 *
 * 结构：所有请求 → 这个 Worker → 单例 Durable Object（HearsayContainer）→ 容器内 8764 端口
 * （统一首页兼网关，再按 /listen/ /shadow/ /retell/ /converse/ /plan/ 转给各切片）。
 *
 * 学习者数据持久化（容器磁盘是临时的，空闲 sleepAfter 后休眠，再启动时按镜像重建）：
 *   容器内 Python（prototype/m3_learner/r2sync.py）用 S3 协议读写
 *   http://learner-store.hearsay.internal/<bucket>/<key>。
 *   这个主机名不存在于公网：容器发往它的请求被下面的 outboundByHost 拦截，
 *   由 Worker 用 R2 绑定（env.LEARNER_BUCKET）直接读写。
 *   所以整条链路上没有 R2 访问密钥；容器只能读写这一个对象键。
 *
 * 访问控制不在这里做：开放公网地址前，先在 Cloudflare Zero Trust 里给它配 Access。
 */
import { Container, getContainer } from "@cloudflare/containers";

// 出站拦截必须从入口导出 ContainerProxy
export { ContainerProxy } from "@cloudflare/containers";

const LEARNER_STORE_HOST = "learner-store.hearsay.internal";

interface Env {
  HEARSAY: DurableObjectNamespace<HearsayContainer>;
  LEARNER_BUCKET: R2Bucket;
  // wrangler.jsonc 的 vars（非敏感默认值）
  HEARSAY_LLM: string;
  HEARSAY_LLM_MODEL: string;
  HEARSAY_R2_BUCKET: string;
  HEARSAY_R2_KEY: string;
  // wrangler secret put（不写进仓库）
  HEARSAY_LLM_API_KEY?: string;
  HEARSAY_LLM_BASE_URL?: string;
}

// 原样传进容器的变量；未设置的不传（容器内按默认值处理）
const PASS_THROUGH = [
  "HEARSAY_LLM",
  "HEARSAY_LLM_MODEL",
  "HEARSAY_LLM_API_KEY",
  "HEARSAY_LLM_BASE_URL",
] as const;

/** 处理容器发往 LEARNER_STORE_HOST 的 S3 风格请求。只认 /<bucket>/<key> 这一个对象。 */
async function handleLearnerStore(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url);
  const expected = `/${env.HEARSAY_R2_BUCKET}/${env.HEARSAY_R2_KEY}`;
  if (decodeURIComponent(url.pathname) !== expected) {
    return new Response("forbidden", { status: 403 });
  }
  const key = env.HEARSAY_R2_KEY;
  switch (req.method) {
    case "GET": {
      const obj = await env.LEARNER_BUCKET.get(key);
      if (!obj) return new Response("not found", { status: 404 });
      return new Response(obj.body, {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    case "PUT": {
      const body = await req.arrayBuffer();
      try {
        JSON.parse(new TextDecoder().decode(body));
      } catch {
        return new Response("body is not JSON", { status: 400 });
      }
      await env.LEARNER_BUCKET.put(key, body, {
        httpMetadata: { contentType: "application/json" },
      });
      return new Response(null, { status: 200 });
    }
    case "DELETE":
      await env.LEARNER_BUCKET.delete(key);
      return new Response(null, { status: 204 });
    default:
      return new Response("method not allowed", { status: 405 });
  }
}

export class HearsayContainer extends Container<Env> {
  // 统一首页端口；请求会被挂起直到容器在这个端口上开始监听
  defaultPort = 8764;
  // 空闲 10 分钟休眠。学习者数据每次保存都会同步写入 R2，休眠不丢数据
  sleepAfter = "10m";
  // LLM 调用要访问公网（HTTPS 不拦截，直接放行）
  enableInternet = true;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    const vars: Record<string, string> = {};
    for (const name of PASS_THROUGH) {
      const value = env[name];
      if (typeof value === "string" && value !== "") vars[name] = value;
    }
    // r2sync.py 要求四项齐全才启用；凭据只是占位，签名由 Worker 忽略
    Object.assign(vars, {
      HEARSAY_R2_ENDPOINT: `http://${LEARNER_STORE_HOST}`,
      HEARSAY_R2_ACCOUNT_ID: "worker-binding",
      HEARSAY_R2_BUCKET: env.HEARSAY_R2_BUCKET,
      HEARSAY_R2_KEY: env.HEARSAY_R2_KEY,
      HEARSAY_R2_ACCESS_KEY_ID: "worker-binding",
      HEARSAY_R2_SECRET_ACCESS_KEY: "unused",
    });
    this.envVars = vars;
  }
}

HearsayContainer.outboundByHost = {
  [LEARNER_STORE_HOST]: (req: Request, env: Env) => handleLearnerStore(req, env),
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 单学习者、单数据文件：所有请求都进同一个实例，避免两个容器并发写同一个对象
    return getContainer(env.HEARSAY).fetch(request);
  },
};
