import type { PrebuiltAgentOut } from '../../types';
import '../PrebuiltAgentCard.css';

interface PrebuiltAgentCardProps {
  agent: Omit<PrebuiltAgentOut, 'createdAt' | 'updatedAt'>;
}

export default function PrebuiltAgentCard({agent}: PrebuiltAgentCardProps) {
  return (
    <div className="prebuilt-agent-card">
      <div className="card-header">
        <div className="card-icon">
          <span className="template-badge">📋</span>
        </div>
        <div className="card-title">
          <span className="card-text">{agent.name}</span>
        </div>
        <div className="template-label">
          <span className="template-text">Agent</span>
        </div>
      </div>
      
      <div className="card-body">
        <p className="card-description">{agent.description}</p>
        
        <div className="card-meta">
          <div className="meta-item">
            <span className="meta-icon">❓</span>
            <span className="meta-text">{agent.questions.length} data fields</span>
          </div>
          <div className="meta-item">
            <span className="meta-icon">🎯</span>
            <span className="meta-text">Ready to use</span>
          </div>
        </div>
        
        <div className="card-tags">
          {agent.questions.length > 3 && (
            <span className="question-tag template-tag overflow-tag">+{agent.questions.length - 3}</span>
          )}
        </div>
      </div>
    </div>
  );
}
