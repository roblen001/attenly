/**
 * EditAnswerModal Component
 * 
 * Modal dialog for editing report answers. Allows users to modify answer text
 * and view associated source quotes. Provides save/cancel functionality.
 * 
 * @param editingAnswer - The answer being edited (null if modal is closed)
 * @param editedAnswerText - Current text in the edit field
 * @param setEditedAnswerText - Function to update the edited text
 * @param onSave - Function to save the edited answer
 * @param onCancel - Function to cancel editing and close modal
 */

import React from 'react';
import type { ReportAnswer } from '../../types';
import './EditAnswerModal.css';

interface EditAnswerModalProps {
  editingAnswer: ReportAnswer | null;
  editedAnswerText: string;
  setEditedAnswerText: (text: string) => void;
  onSave: () => void;
  onCancel: () => void;
}

const EditAnswerModal: React.FC<EditAnswerModalProps> = ({
  editingAnswer,
  editedAnswerText,
  setEditedAnswerText,
  onSave,
  onCancel
}) => {
  if (!editingAnswer) return null;

  return (
    <div className="modal-overlay">
      <div className="modal-content edit-modal">
        <div className="modal-header">
          <h3>Edit Answer</h3>
          <button onClick={onCancel} className="modal-close">
            ×
          </button>
        </div>
        
        <div className="modal-body">
          <div className="form-group">
            <label className="form-label">
              Answer for <code>{'{{' + editingAnswer.placeholder + '}}'}</code>
            </label>
            <div className="question-text">
              <strong>Question:</strong> {editingAnswer.question}
            </div>
            <textarea
              value={editedAnswerText}
              onChange={(e) => setEditedAnswerText(e.target.value)}
              className="form-textarea"
              rows={4}
              placeholder="Enter your answer..."
            />
          </div>
          
          {editingAnswer.quotes.length > 0 && (
            <div className="source-quotes">
              <label className="form-label">Source References</label>
              <div className="quotes-list">
                {editingAnswer.quotes.map((quote) => (
                  <div key={quote.id} className="quote-item">
                    <span className="quote-number">{quote.index}</span>
                    <span className="quote-preview">{quote.text.substring(0, 100)}...</span>
                    <span className="quote-page">Page {quote.page_range}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        
        <div className="modal-footer">
          <button onClick={onCancel} className="btn btn-secondary">
            Cancel
          </button>
          <button 
            onClick={onSave}
            disabled={!editedAnswerText.trim()}
            className="btn btn-primary"
          >
            <span className="btn-icon">💾</span>
            Save Answer
          </button>
        </div>
      </div>
    </div>
  );
};

export default EditAnswerModal;
