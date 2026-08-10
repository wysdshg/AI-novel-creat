import axios from 'axios'
import { ElMessage } from 'element-plus'

// 统一请求实例：baseURL 对应 API接口规范.md §0.1 的 /api/v1
// 拦截器自动解包统一信封 {"code":0,"data":...}，非 0 自动报错。
// 超时设为 180s：后端 /command（实体抽取）和 /chapter/generate（章节生成）均调用云端 LLM，
// NVIDIA/SiliconFlow 等免费队列常需 30~90s，60s 会频繁误超时。
const http = axios.create({
  baseURL: '/api/v1',
  timeout: 180000,
})

http.interceptors.response.use(
  (res) => {
    const body = res.data
    if (body && typeof body.code === 'number') {
      if (body.code === 0) return body.data
      ElMessage.error(body.message || `请求失败(code=${body.code})`)
      return Promise.reject(body)
    }
    return body
  },
  (err) => {
    const msg = err?.response?.data?.message || err.message || '网络错误'
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export default http
