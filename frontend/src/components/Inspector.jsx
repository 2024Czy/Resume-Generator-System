import { AlertTriangle, CheckCircle2, FileCheck2 } from 'lucide-react'

export default function Inspector({ resume, profile }) {
  const textMetadata = resume.other?.文本解析
  const lowConfidence = textMetadata?.低置信字段 ?? []
  const checks = [
    ['必填字段完整性', Boolean(resume.personal.name && (resume.personal.phone || resume.personal.email))],
    ['教育结构匹配', resume.education.length > 0],
    ['项目经历可用', resume.projects.length > 0],
    ['实习经历可用', resume.internships.length > 0],
    ['技能与荣誉可用', resume.skills.length > 0 || resume.awards.length > 0],
    ['照片占位处理', true],
  ]
  return (
    <aside className="inspector">
      <div className="inspector-title">
        <FileCheck2 size={19} />
        <h2>模板格式检查</h2>
      </div>
      <div className="template-facts">
        <h3>模板信息</h3>
        <dl>
          <div><dt>模板</dt><dd>{profile?.name ?? 'v7.3 表格版'}</dd></div>
          <div><dt>结构</dt><dd>1 个主表格 · 5 列网格</dd></div>
          <div><dt>行型</dt><dd>15 个原型行</dd></div>
          <div><dt>输出</dt><dd>默认 DOCX</dd></div>
        </dl>
      </div>
      <div className="mapping-table">
        <div className="mapping-head"><span>模块</span><span>条目</span><span>状态</span></div>
        {[
          ['教育经历', resume.education.length],
          ['项目经历', resume.projects.length],
          ['实习经历', resume.internships.length],
          ['技能分类', resume.skills.length],
        ].map(([label, count]) => (
          <div className="mapping-row" key={label}><span>{label}</span><span>{count}</span><span className={count ? 'success-text' : 'warning-text'}>{count ? '已映射' : '空'}</span></div>
        ))}
      </div>
      <div className="check-list">
        {checks.map(([label, passed]) => (
          <div className="check-row" key={label}>
            {passed ? <CheckCircle2 className="success" size={17} /> : <AlertTriangle className="warning" size={17} />}
            <span>{label}</span>
            <strong className={passed ? 'success-text' : 'warning-text'}>{passed ? '通过' : '需补充'}</strong>
          </div>
        ))}
      </div>
      {resume.warnings.length ? (
        <div className="warning-box">
          <AlertTriangle size={17} />
          <div>
            <strong>解析提示</strong>
            {resume.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        </div>
      ) : null}
      {textMetadata ? (
        <div className="confidence-box">
          <div className="confidence-title">
            <ClipboardPasteIcon />
            <strong>文本解析复核</strong>
          </div>
          <p>
            {textMetadata.解析引擎 === 'ollama' ? `${textMetadata.模型} 智能解析` : textMetadata.自动回退 ? '规则回退解析' : '本地规则解析'}
            {textMetadata.耗时秒 ? ` · ${textMetadata.耗时秒} 秒` : ''}
          </p>
          <p>实际引擎：{textMetadata.解析引擎 === 'ollama' ? `Ollama · ${textMetadata.模型}` : '本地规则解析器'}</p>
          {textMetadata.自动回退 && textMetadata.回退原因 ? <p className="confidence-reason">回退原因：{textMetadata.回退原因}</p> : null}
          <p>已从 {textMetadata.字符数} 个字符中提取信息；{lowConfidence.length ? `${lowConfidence.length} 项需要重点确认。` : '未发现低置信字段。'}</p>
          {lowConfidence.slice(0, 5).map((item) => (
            <div className="confidence-item" key={item.字段}>
              <strong>{item.标签} · {Math.round(item.置信度 * 100)}%</strong>
              <span>{item.原文}</span>
            </div>
          ))}
        </div>
      ) : null}
      <div className="normalization-note">
        <h3>已补齐的不规则格式</h3>
        <p>教育经历使用固定制表位对齐；实习标题统一三列宽度；条目行按内容克隆并自然分页。</p>
      </div>
    </aside>
  )
}

function ClipboardPasteIcon() {
  return <FileCheck2 size={16} aria-hidden="true" />
}
