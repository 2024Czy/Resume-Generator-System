import { useEffect, useState } from 'react'
import { AlertTriangle, BrainCircuit, CheckCircle2, ClipboardPaste, FileText, Gauge, LoaderCircle, ShieldCheck, UploadCloud, X } from 'lucide-react'

const steps = [
  ['导入资料', '上传 Word 或粘贴文本'],
  ['校对信息', '检查并修正结构化结果'],
  ['生成文件', '套用 v7.3 表格模板'],
]

export default function UploadRail({ fileName, status, error, onFile, onText, onCancelText, hasContent, aiStatus, parseMetadata }) {
  const [inputMode, setInputMode] = useState('file')
  const [text, setText] = useState('')
  const [importMode, setImportMode] = useState('replace')
  const [engine, setEngine] = useState('hybrid')
  const currentStep = status === 'ready' ? 2 : fileName ? 1 : 0
  const loading = status === 'loading'
  const fallback = status === 'ready' && parseMetadata?.自动回退 === true
  const completedLabel = fallback
    ? '智能解析失败，已使用快速解析'
    : parseMetadata?.解析引擎 === 'ollama'
      ? '智能解析完成'
      : parseMetadata?.解析引擎 === 'rules'
        ? '快速解析完成'
        : '解析完成'

  useEffect(() => {
    if (hasContent && inputMode === 'text') setImportMode('merge')
  }, [hasContent, inputMode])

  const switchMode = (nextMode) => {
    setInputMode(nextMode)
    if (nextMode === 'text') setImportMode(hasContent ? 'merge' : 'replace')
  }

  const submitText = async (event) => {
    event.preventDefault()
    if (!text.trim() || loading) return
    await onText(text.trim(), hasContent ? importMode : 'replace', engine)
  }

  return (
    <aside className="upload-rail">
      <div className="steps">
        {steps.map(([title, description], index) => (
          <div className={`step ${index <= currentStep ? 'step--active' : ''}`} key={title}>
            <span className="step-number">{index + 1}</span>
            <div>
              <strong>{title}</strong>
              <p>{description}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="source-tabs" role="tablist" aria-label="资料导入方式">
        <button type="button" role="tab" aria-selected={inputMode === 'file'} className={inputMode === 'file' ? 'source-tab source-tab--active' : 'source-tab'} onClick={() => switchMode('file')}>
          <UploadCloud size={15} />上传 Word
        </button>
        <button type="button" role="tab" aria-selected={inputMode === 'text'} className={inputMode === 'text' ? 'source-tab source-tab--active' : 'source-tab'} onClick={() => switchMode('text')}>
          <ClipboardPaste size={15} />粘贴文本
        </button>
      </div>

      {inputMode === 'file' ? (
        <label className="drop-zone">
          {loading ? <LoaderCircle className="spin" size={34} /> : <UploadCloud size={34} />}
          <strong>{loading ? '正在解析…' : '点击选择 Word 简历'}</strong>
          <span>支持 DOCX、DOCM · 最大 20 MB</span>
          <input
            type="file"
            disabled={loading}
            accept=".docx,.docm,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-word.document.macroEnabled.12"
            onChange={(event) => event.target.files?.[0] && onFile(event.target.files[0])}
          />
        </label>
      ) : (
        <form className="text-import" onSubmit={submitText}>
          <label htmlFor="resume-source-text">粘贴个人介绍、教育、项目或工作经历</label>
          <textarea
            id="resume-source-text"
            value={text}
            maxLength={50000}
            disabled={loading}
            placeholder="例如：我叫张三，2022 年毕业于……曾在……实习，负责……"
            onChange={(event) => setText(event.target.value)}
          />
          <div className="text-import-meta">
            <span>{text.length.toLocaleString()} / 50,000</span>
            <span><ShieldCheck size={13} />仅在本机处理</span>
          </div>
          <fieldset className="engine-picker">
            <legend>解析方式</legend>
            <button type="button" className={engine === 'hybrid' ? 'engine-option engine-option--active' : 'engine-option'} aria-pressed={engine === 'hybrid'} disabled={loading} onClick={() => setEngine('hybrid')}>
              <BrainCircuit size={16} />
              <span><strong>智能解析</strong><small>qwen3:4b + 规则校验</small></span>
            </button>
            <button type="button" className={engine === 'rules' ? 'engine-option engine-option--active' : 'engine-option'} aria-pressed={engine === 'rules'} disabled={loading} onClick={() => setEngine('rules')}>
              <Gauge size={16} />
              <span><strong>快速解析</strong><small>仅使用现有规则</small></span>
            </button>
          </fieldset>
          {engine === 'hybrid' ? (
            <p className={aiStatus?.available && aiStatus?.installed ? 'model-status model-status--ready' : 'model-status model-status--warning'}>
              {aiStatus?.available && aiStatus?.installed
                ? `qwen3:4b 已就绪${aiStatus.loaded ? ' · 已加载' : ' · 首次解析需加载模型'}`
                : 'qwen3:4b 未就绪，提交后将自动回退规则解析'}
            </p>
          ) : null}
          {hasContent ? (
            <label className="import-mode">
              导入方式
              <select value={importMode} onChange={(event) => setImportMode(event.target.value)}>
                <option value="merge">合并并保留当前内容</option>
                <option value="replace">替换当前内容</option>
              </select>
            </label>
          ) : null}
          {loading ? (
            <div className="parsing-actions">
              <div className="parse-text-button parse-text-button--loading">
                <LoaderCircle className="spin" size={16} />
                {engine === 'hybrid' ? 'qwen3:4b 正在理解文本…' : '正在使用规则识别…'}
              </div>
              <button className="cancel-parse-button" type="button" onClick={onCancelText}>取消解析</button>
            </div>
          ) : (
            <button className="parse-text-button" type="submit" disabled={!text.trim()}>
              {engine === 'hybrid' ? <BrainCircuit size={16} /> : <ClipboardPaste size={16} />}
              {engine === 'hybrid' ? '智能识别并填入表单' : '快速识别并填入表单'}
            </button>
          )}
        </form>
      )}

      {fileName ? (
        <div className={fallback ? 'file-row file-row--fallback' : 'file-row'}>
          <FileText size={18} />
          <div>
            <strong>{fileName}</strong>
            <span>{status === 'ready' ? completedLabel : loading ? '读取中' : '等待处理'}</span>
          </div>
          {status === 'ready' ? fallback ? <AlertTriangle className="warning" size={18} /> : <CheckCircle2 className="success" size={18} /> : null}
        </div>
      ) : null}
      {error ? (
        <div className="rail-error">
          <X size={16} />
          <span>{error}</span>
        </div>
      ) : null}
    </aside>
  )
}
