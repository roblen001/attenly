import React, { useState } from 'react';
import './CustomAgentCard.css';

interface QuestionOut {
  id: string;
  placeholder: string;
  prompt: string;
}

interface CustomAgent {
  id: string;
  name: string;
  description: string;
  reportTemplate: string;
  questions: QuestionOut[];
  user_id: string;
  is_custom: boolean;
  created_by_name?: string;
  createdAt: string;
  updatedAt: string;
  can_delete: boolean;
}

interface CustomAgentCardProps {
  agent: CustomAgent;
  onExecute: (agent: CustomAgent) => void;
  onDelete: (agentId: string) => void;
  onEdit: (agentId: string) => void;
}

const CustomAgentCard: React.FC<CustomAgentCardProps> = ({
  agent,
  onExecute,
  onDelete,
  onEdit
}) => {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const handleCardClick = () => {
    onExecute(agent);
  };


  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowDeleteConfirm(true);
  };

  const handleConfirmDelete = () => {
    onDelete(agent.id);
    setShowDeleteConfirm(false);
  };

  const handleCancelDelete = () => {
    setShowDeleteConfirm(false);
  };

  const handleEditClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onEdit(agent.id);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  return (
    <>
      <div className="custom-agent-card" onClick={handleCardClick}>
        <div className="card-header">
          <div className="card-icon">
            <span className="agent-emoji">🤖</span>
          </div>
          <div className="custom-badge">
            <span className="custom-text">CUSTOM</span>
          </div>
        </div>

        <div className="card-body">
          <h3 className="card-title">{agent.name}</h3>
          <p className="card-description">
            {agent.description || 'No description provided'}
          </p>

          <div className="card-meta">
            <div className="meta-item">
              <span className="meta-icon">📊</span>
              <span className="meta-text">{agent.questions.length} extraction points</span>
            </div>
            <div className="meta-item">
              <span className="meta-icon">📅</span>
              <span className="meta-text">Created {formatDate(agent.createdAt)}</span>
            </div>
          </div>

          {agent.created_by_name && (
            <div className="created-by">
              <span className="created-by-text">Created by {agent.created_by_name}</span>
            </div>
          )}
        </div>

        <div className="card-actions">
          {agent.can_delete && (
            <button 
              className="btn-edit"
              onClick={handleEditClick}
              title="Edit custom agent"
            >
              <span className="btn-icon">✏️</span>
            </button>
          )}
          
          {agent.can_delete && (
            <button 
              className="btn-delete"
              onClick={handleDeleteClick}
              title="Delete custom agent"
            >
              <span className="btn-icon">🗑️</span>
            </button>
          )}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="delete-modal-overlay">
          <div className="delete-modal">
            <div className="delete-modal-header">
              <h3>Delete Custom Agent</h3>
            </div>
            <div className="delete-modal-body">
              <p>Are you sure you want to delete <strong>"{agent.name}"</strong>?</p>
              <p className="warning-text">This action cannot be undone.</p>
            </div>
            <div className="delete-modal-actions">
              <button 
                className="btn-cancel"
                onClick={handleCancelDelete}
              >
                Cancel
              </button>
              <button 
                className="btn-confirm-delete"
                onClick={handleConfirmDelete}
              >
                Delete Agent
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default CustomAgentCard;
