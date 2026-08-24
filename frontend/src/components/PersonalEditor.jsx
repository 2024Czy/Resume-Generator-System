import Field from './Field.jsx'
import Section from './Section.jsx'

export default function PersonalEditor({ value, onChange }) {
  const update = (key, next) => onChange({ ...value, [key]: key === 'age' ? (next ? Number(next) : null) : next })
  return (
    <Section title="基本信息">
      <div className="personal-grid">
        <Field label="姓名" value={value.name} onChange={(next) => update('name', next)} />
        <Field label="出生年月" value={value.birth_date} placeholder="2000/01/01" onChange={(next) => update('birth_date', next)} />
        <Field label="年龄" value={value.age ?? ''} type="number" onChange={(next) => update('age', next)} />
        <Field label="手机" value={value.phone} onChange={(next) => update('phone', next)} />
        <Field label="邮箱" value={value.email} onChange={(next) => update('email', next)} />
        <Field label="现居地" value={value.location} onChange={(next) => update('location', next)} />
        <Field label="目标岗位" value={value.target_role} placeholder="例如：大模型算法工程师" onChange={(next) => update('target_role', next)} />
        <Field label="求职状态" value={value.job_status} placeholder="例如：快速到岗-实习6个月" onChange={(next) => update('job_status', next)} />
        <Field label="到岗 / 周期" value={value.availability} placeholder="例如：立即到岗，可实习6个月" onChange={(next) => update('availability', next)} />
      </div>
    </Section>
  )
}
