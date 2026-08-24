import { Trash2 } from 'lucide-react'
import { emptyEducation } from '../data.js'
import Field from './Field.jsx'
import Section from './Section.jsx'

export default function EducationEditor({ items, onChange }) {
  const update = (index, key, value) => onChange(items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))
  const remove = (index) => onChange(items.filter((_, itemIndex) => itemIndex !== index))
  return (
    <Section title="教育经历" onAdd={() => onChange([...items, { ...emptyEducation }])} addLabel="添加教育经历">
      {items.length ? items.map((item, index) => (
        <div className="repeat-row education-row" key={index}>
          <Field label="时间" value={item.period} placeholder="2022.09 - 2025.06" onChange={(value) => update(index, 'period', value)} />
          <Field label="学校" value={item.school} onChange={(value) => update(index, 'school', value)} />
          <Field label="专业" value={item.major} onChange={(value) => update(index, 'major', value)} />
          <Field label="学历" value={item.degree} onChange={(value) => update(index, 'degree', value)} />
          <button className="icon-button danger" type="button" aria-label="删除教育经历" onClick={() => remove(index)}><Trash2 size={16} /></button>
        </div>
      )) : <p className="empty-copy">尚未识别教育经历，请手动添加。</p>}
    </Section>
  )
}
