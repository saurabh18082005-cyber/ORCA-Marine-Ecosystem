import { AGENT_STATUS } from '../data/uiConstants.js'

const STATUS_CONFIG = {
  [AGENT_STATUS.IDLE]: { icon: '○', label: 'Ready', className: 'status-idle' },
  [AGENT_STATUS.PROCESSING]: { icon: '⏳', label: 'Processing', className: 'status-processing' },
  [AGENT_STATUS.COMPLETED]: { icon: '✓', label: 'Completed', className: 'status-completed' },
  [AGENT_STATUS.UNAVAILABLE]: { icon: '⚠', label: 'Data unavailable', className: 'status-unavailable' },
}

const META = {
  weather: ['🌦️', 'Weather Agent'],
  ocean: ['🌊', 'Ocean Agent'],
  marine: ['🐟', 'Marine Agent'],
  geospatial: ['🗺️', 'Geospatial Agent'],
  disaster: ['🚨', 'Disaster & Alerts Agent'],
  satellite: ['🛰️', 'Satellite Agent'],
  fisheries: ['🎣', 'Fisheries / PFZ Agent'],
}

export default function AgentCards({ agents }) {
  const agentKeys = Object.keys(agents || {}).length
    ? Object.keys(agents)
    : Object.keys(META)

  return (
    <section className="orca-section">
      <div className="section-heading">
        <h2>Multi-Agent Analysis</h2>
        <p>Specialist agents collaborate on weather, ocean, safety, satellite, fisheries and geospatial evidence.</p>
      </div>
      <div className="agent-grid">
        {agentKeys.map((key) => {
          const [icon, label] = META[key] || ['🤖', key.replaceAll('_', ' ')]
          const agent = agents?.[key]
          const status = agent?.status ?? AGENT_STATUS.IDLE
          const config = STATUS_CONFIG[status] ?? STATUS_CONFIG[AGENT_STATUS.IDLE]
          return (
            <article key={key} className={`agent-card agent-card--${key}`}>
              <div className="agent-card__icon">{icon}</div>
              <div className="agent-card__body">
                <h3>{agent?.name ?? label}</h3>
                <span className={`agent-status ${config.className}`}>
                  <span aria-hidden="true">{config.icon}</span>{config.label}
                </span>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
