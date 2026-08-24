import { ChevronDown, Plus } from 'lucide-react'

export default function Section({ title, children, onAdd, addLabel = '添加一项' }) {
  return (
    <section className="editor-section">
      <header className="section-header">
        <h2>{title}</h2>
        <div className="section-actions">
          {onAdd ? (
            <button type="button" className="text-button" onClick={onAdd}>
              <Plus size={15} />
              {addLabel}
            </button>
          ) : null}
          <ChevronDown size={17} aria-hidden="true" />
        </div>
      </header>
      {children}
    </section>
  )
}
