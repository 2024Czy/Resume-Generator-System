import Field from './Field.jsx'
import Section from './Section.jsx'

export default function SummaryEditor({ summary, selfEvaluation, onSummaryChange, onSelfEvaluationChange }) {
  return (
    <Section title="个人陈述">
      <div className="summary-fields">
        <Field label="个人简介" value={summary} multiline onChange={onSummaryChange} />
        <Field label="自我评价" value={selfEvaluation} multiline onChange={onSelfEvaluationChange} />
        <p className="template-field-note">当前 v7.3 模板暂不输出个人陈述；内容会保留在解析 JSON 中，便于后续模板使用。</p>
      </div>
    </Section>
  )
}
