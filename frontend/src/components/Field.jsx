export default function Field({ label, value = '', onChange, type = 'text', placeholder = '', multiline = false }) {
  const Component = multiline ? 'textarea' : 'input'
  return (
    <label className={`field ${multiline ? 'field--multiline' : ''}`}>
      <span>{label}</span>
      <Component
        type={multiline ? undefined : type}
        value={value ?? ''}
        placeholder={placeholder}
        rows={multiline ? 3 : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}
