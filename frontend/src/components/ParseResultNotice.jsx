import { AlertTriangle, BrainCircuit, Gauge } from 'lucide-react'

export default function ParseResultNotice({ metadata }) {
  if (!metadata?.解析引擎) return null

  const fallback = metadata.自动回退 === true
  const intelligent = metadata.解析引擎 === 'ollama'
  const title = fallback
    ? '智能解析失败，已使用快速解析'
    : intelligent
      ? 'qwen3:4b 智能解析完成'
      : '快速规则解析完成'
  const engine = intelligent ? `Ollama · ${metadata.模型 || 'qwen3:4b'}` : '本地规则解析器'

  return (
    <section className={fallback ? 'parse-result-notice parse-result-notice--fallback' : 'parse-result-notice'} aria-live="polite">
      {fallback ? <AlertTriangle size={19} /> : intelligent ? <BrainCircuit size={19} /> : <Gauge size={19} />}
      <div>
        <strong>{title}</strong>
        <p>实际引擎：{engine}{metadata.耗时秒 ? ` · ${metadata.耗时秒} 秒` : ''}</p>
        {fallback && metadata.回退原因 ? <p className="parse-result-reason">回退原因：{metadata.回退原因}</p> : null}
      </div>
    </section>
  )
}
