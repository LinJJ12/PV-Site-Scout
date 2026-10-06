/* 后端 API 客户端：同源优先，跨端口兜底（开发直连 5000 / 部署反代） */

const API_BASES = [
  typeof window !== "undefined" ? window.location.origin : "",
  "http://127.0.0.1:5000",
  "http://localhost:5000"
].filter(Boolean);

export const modelLabel = (loaded, torchAvailable = false) => {
  if (!loaded) return "简化公式";
  return torchAvailable ? "GAT+GBDT集成模型" : "GBDT模型";
};

/* 依次尝试各个后端地址，全部失败时抛出最后一个错误 */
export const fetchFromApi = async (path, options = {}) => {
  let lastError = null;
  for (const base of API_BASES) {
    try {
      const response = await fetch(`${base}${path}`, {
        ...options,
        signal: options.signal || AbortSignal.timeout(15000)
      });
      if (!response.ok) {
        throw new Error(`接口响应异常：${response.status}`);
      }
      return response;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("后端服务不可用");
};
