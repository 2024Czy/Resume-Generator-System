import { Plus, Trash2 } from 'lucide-react'
import { emptyExperience } from '../data.js'
import Field from './Field.jsx'
import Section from './Section.jsx'

export default function ExperienceEditor({ title, kind, items, onChange }) {
  const updateItem = (index, next) => onChange(items.map((item, itemIndex) => itemIndex === index ? next : item))
  const update = (index, key, value) => updateItem(index, { ...items[index], [key]: value })
  const updateHighlight = (itemIndex, highlightIndex, key, value) => {
    const highlights = items[itemIndex].highlights.map((highlight, index) => index === highlightIndex ? { ...highlight, [key]: value } : highlight)
    update(itemIndex, 'highlights', highlights)
  }
  const removeHighlight = (itemIndex, highlightIndex) => update(itemIndex, 'highlights', items[itemIndex].highlights.filter((_, index) => index !== highlightIndex))

  return (
    <Section title={title} onAdd={() => onChange([...items, { ...emptyExperience, highlights: [], results: [] }])} addLabel={`添加${title}`}>
      {items.length ? items.map((item, index) => (
        <article className="experience-block" key={index}>
          <div className="experience-toolbar">
            <strong>{item.name || item.organization || `${title} ${index + 1}`}</strong>
            <button className="icon-button danger" type="button" aria-label={`删除${title}`} onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={16} /></button>
          </div>
          <div className="experience-grid">
            <Field label="时间" value={item.period} onChange={(value) => update(index, 'period', value)} />
            <Field label={kind === 'project' ? '项目归属' : '公司'} value={item.organization} onChange={(value) => update(index, 'organization', value)} />
            <Field label="角色 / 职位" value={item.role} onChange={(value) => update(index, 'role', value)} />
            <Field label="项目名称" value={item.name} onChange={(value) => update(index, 'name', value)} />
            <Field label="技术栈" value={item.technologies} onChange={(value) => update(index, 'technologies', value)} />
            <Field label="背景 / 简介" value={item.background} multiline onChange={(value) => update(index, 'background', value)} />
          </div>
          <div className="subsection-label">
            <span>核心工作</span>
            <button type="button" className="text-button" onClick={() => update(index, 'highlights', [...item.highlights, { label: '', content: '' }])}><Plus size={14} />添加要点</button>
          </div>
          <div className="highlight-list">
            {item.highlights.map((highlight, highlightIndex) => (
              <div className="highlight-row" key={highlightIndex}>
                <Field label="要点标题" value={highlight.label} onChange={(value) => updateHighlight(index, highlightIndex, 'label', value)} />
                <Field label="内容" value={highlight.content} onChange={(value) => updateHighlight(index, highlightIndex, 'content', value)} />
                <button className="icon-button danger" type="button" aria-label="删除要点" onClick={() => removeHighlight(index, highlightIndex)}><Trash2 size={15} /></button>
              </div>
            ))}
          </div>
          <Field label="成果（每行一条）" value={item.results.join('\n')} multiline onChange={(value) => update(index, 'results', value.split('\n').map((line) => line.trim()).filter(Boolean))} />
        </article>
      )) : <p className="empty-copy">尚未识别{title}；该分节会在导出时自动省略。</p>}
    </Section>
  )
}
