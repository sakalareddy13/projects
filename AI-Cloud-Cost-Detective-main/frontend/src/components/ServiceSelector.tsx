interface Props {
  label: string
  items: { id: string; name: string; description?: string }[]
  selected: string[]
  onChange: (selected: string[]) => void
  columns?: number
}

export default function ServiceSelector({ label, items, selected, onChange, columns = 2 }: Props) {
  const toggle = (id: string) => {
    onChange(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id])
  }

  const colClass = {
    1: 'grid-cols-1',
    2: 'grid-cols-1 sm:grid-cols-2',
    3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-2 sm:grid-cols-2 lg:grid-cols-4',
  }[columns] ?? 'grid-cols-2'

  return (
    <div>
      {label && <label className="block text-sm font-medium text-gray-300 mb-3">{label}</label>}
      <div className={`grid ${colClass} gap-2`}>
        {items.map((item) => {
          const on = selected.includes(item.id)
          return (
            <label
              key={item.id}
              className="flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-all"
              style={{
                background: on ? 'rgba(102,126,234,0.2)' : 'var(--color-section-bg)',
                border: on ? '1px solid rgba(102,126,234,0.6)' : '1px solid var(--color-section-border)',
                color: on ? 'var(--color-text)' : 'var(--color-text-secondary)',
              }}
            >
              <input
                type="checkbox"
                className="mt-0.5 shrink-0 accent-indigo-400"
                checked={on}
                onChange={() => toggle(item.id)}
              />
              <div>
                <p className="text-sm font-medium leading-4">{item.name}</p>
                {item.description && (
                  <p className="text-xs mt-0.5" style={{ color: on ? 'var(--color-text-secondary)' : 'var(--color-text-tertiary)' }}>
                    {item.description}
                  </p>
                )}
              </div>
            </label>
          )
        })}
      </div>
    </div>
  )
}
