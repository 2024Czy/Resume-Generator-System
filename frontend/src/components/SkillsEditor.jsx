import { Trash2 } from 'lucide-react'
import { emptySkill } from '../data.js'
import Field from './Field.jsx'
import Section from './Section.jsx'

export default function SkillsEditor({ items, awards, onItemsChange, onAwardsChange }) {
  const update = (index, key, value) => onItemsChange(items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))
  return (
    <Section title="技能与荣誉" onAdd={() => onItemsChange([...items, { ...emptySkill }])} addLabel="添加技能分类">
      <div className="skills-list">
        {items.map((item, index) => (
          <div className="skill-row" key={index}>
            <Field label="分类" value={item.category} onChange={(value) => update(index, 'category', value)} />
            <Field label="描述" value={item.description} onChange={(value) => update(index, 'description', value)} />
            <button className="icon-button danger" type="button" aria-label="删除技能" onClick={() => onItemsChange(items.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={16} /></button>
          </div>
        ))}
      </div>
      <Field label="荣誉奖项（每行一项）" value={awards.join('\n')} multiline onChange={(value) => onAwardsChange(value.split('\n').map((line) => line.trim()).filter(Boolean))} />
    </Section>
  )
}
