// CreateAgent.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './CreateAgent.css';
import './AgentExecution.css';
import EditorStep from '../components/agent-creation/EditorStep';
import TemplateSelectionStep from '../components/agent-creation/TemplateSelectionStep';
import TemplateProcessingLoadingState from '../components/agent-creation/TemplateProcessingLoadingState';
import FileUpload from '../components/AgentExecution/FileUpload';
import { api } from '../libs/https';
import type { UploadedFile } from '../types';
import { transformCustomAgentData, addProfessionalStyling, restoreInteractivePlaceholders } from '../utils/agentTransform';

// Types matching backend schemas
interface QuestionOut {
  id: string;
  placeholder: string;
  prompt: string;
}

interface CreateCustomAgentRequest {
  name: string;
  description?: string;
  report_template: string;
  report_template_css?: string;
  questions: QuestionOut[];
}

interface AgentCreationStep {
  step: 'upload' | 'template-selection' | 'editor' | 'naming';
  data: {
    uploadedFiles?: UploadedFile[];
    reportTemplate?: string;
    reportTemplateCss?: string;
    initialTemplateHtml?: string;
    questions?: QuestionOut[];
    agentName?: string;
    agentDescription?: string;
  };
}

const CreateAgent: React.FC = () => {
  const navigate = useNavigate();
  const { agentId } = useParams<{ agentId?: string }>();
  const isEditMode = Boolean(agentId);
  
  const [currentStep, setCurrentStep] = useState<AgentCreationStep>({
    step: 'upload',
    data: {}
  });
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [loadingAgent, setLoadingAgent] = useState(isEditMode);
  const [isProcessingTemplate, setIsProcessingTemplate] = useState(false);
  const [templateUploadError, setTemplateUploadError] = useState<string | null>(null);

  // Fetch agent data for edit mode
  useEffect(() => {
    const fetchAgentForEditing = async () => {
      if (!isEditMode || !agentId) {
        return;
      }

      try {
        setLoadingAgent(true);
        const response = await api(`/agents/${agentId}`, {
          method: 'GET',
          headers: { 'Accept': 'application/json' }
        });

        if (!response.ok) {
          throw new Error('Failed to fetch agent for editing');
        }

        const agent = await response.json();
        
        // Apply reverse transformation to convert simple placeholders back to interactive ones
        const { restoredTemplate, mappedQuestions } = restoreInteractivePlaceholders(
          agent.reportTemplate,
          agent.questions
        );
        
        // Pre-populate all form fields with transformed data
        // In edit mode, skip directly to editor step (skip template-selection)
        setCurrentStep({
          step: 'editor',
          data: {
            agentName: agent.name,
            agentDescription: agent.description,
            reportTemplate: restoredTemplate,
            questions: mappedQuestions
          }
        });

      } catch (error) {
        console.error('Error fetching agent for editing:', error);
        alert('Failed to load agent for editing. Please try again.');
        navigate('/dashboard');
      } finally {
        setLoadingAgent(false);
      }
    };

    fetchAgentForEditing();
  }, [isEditMode, agentId, navigate]);

  // Clear files only on actual page unload, not on auth state changes
  useEffect(() => {
    const handleBeforeUnload = async () => {
      try {
        await api('/agents/files/clear', { method: 'DELETE' });
      } catch (error) {
        console.error('Failed to clear files on exit:', error);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, []); // No dependencies - only clear on actual page unload

  const handleStepChange = (
    newStep: 'upload' | 'template-selection' | 'editor' | 'naming',
    newData: Partial<AgentCreationStep['data']>
  ) => {
    setCurrentStep(prev => {
      return {
        step: newStep,
        data: { ...prev.data, ...newData }
      };
    });
  };

  const handleCancel = async () => {
    // Clear files when user explicitly cancels agent creation
    try {
      await api('/agents/files/clear', { method: 'DELETE' });
    } catch (error) {
      console.error('Failed to clear files on cancellation:', error);
      // Don't block navigation on cleanup failure
    }
    navigate('/dashboard');
  };

  const handleCreateAgent = async () => {
    const { agentName, agentDescription, reportTemplate, reportTemplateCss, questions } = currentStep.data;

    // Validate required fields
    if (!agentName || !reportTemplate || !questions || questions.length === 0) {
      alert('Please ensure you have provided an agent name, report template, and at least one AI extraction point.');
      return;
    }

    try {
      // Transform custom agent data to match prebuilt agent format
      const { cleanTemplate, cleanQuestions } = transformCustomAgentData(reportTemplate, questions);
      
      // Only add professional styling wrapper if NO custom CSS is provided
      // When CSS is provided, the backend will handle the complete HTML document structure
      const finalTemplate = reportTemplateCss 
        ? cleanTemplate 
        : addProfessionalStyling(cleanTemplate);

      const requestPayload: CreateCustomAgentRequest = {
        name: agentName,
        description: agentDescription || '',
        report_template: finalTemplate,
        report_template_css: reportTemplateCss,
        questions: cleanQuestions
      };

      // Use PUT for updates, POST for creation
      const endpoint = isEditMode ? `/agents/custom/${agentId}` : '/agents/create_custom_agent';
      const method = isEditMode ? 'PUT' : 'POST';
      
      const response = await api(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestPayload),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to ${isEditMode ? 'update' : 'create'} custom agent`);
      }

      await response.json();

      // Clear files after successful operation
      try {
        await api('/agents/files/clear', { method: 'DELETE' });
      } catch (error) {
        console.error(`Failed to clear files after agent ${isEditMode ? 'update' : 'creation'}:`, error);
        // Don't block success flow on cleanup failure
      }

      alert(`Custom agent "${agentName}" ${isEditMode ? 'updated' : 'created'} successfully!`);
      navigate('/dashboard');

    } catch (error) {
      console.error(`Error ${isEditMode ? 'updating' : 'creating'} custom agent:`, error);
      alert(`Failed to ${isEditMode ? 'update' : 'create'} custom agent: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const renderStepIndicator = () => {
    const steps = [
      { key: 'upload', label: 'Upload Examples', number: 1 },
      { key: 'template-selection', label: 'Choose Method', number: 2 },
      { key: 'editor', label: 'Create Template', number: 3 },
      { key: 'naming', label: 'Name & Save', number: 4 }
    ] as const;

    return (
      <div className="step-indicator">
        {steps.map((step, index) => (
          <div key={step.key} className="step-indicator-item">
            <div
              className={`step-circle ${currentStep.step === step.key ? 'active' : ''} ${
              steps.findIndex(s => s.key === currentStep.step) > index ? 'completed' : ''
              }`}
            >
              {steps.findIndex(s => s.key === currentStep.step) <= index ? step.number : null}
            </div>
            <span className="step-label">{step.label}</span>
            {index < steps.length - 1 && <div className="step-connector" />}
          </div>
        ))}
      </div>
    );
  };

  const renderCurrentStep = () => {
    switch (currentStep.step) {
      case 'upload':
        return (
          <div className="step-content">
            <h2>Upload Example Documents</h2>
            <p>Upload 1-3 source documents that your agent will extract information from to fill a single report. Multiple documents can be combined as sources for one report.</p>

            <FileUpload
              files={uploadedFiles}
              onFilesChange={(files) => {
                setUploadedFiles(files);
              }}
            />

            <div className="step-actions">
              <button className="btn-secondary" onClick={handleCancel}>
                Cancel
              </button>
              <button
                className="btn-primary"
                disabled={uploadedFiles.length === 0}
                onClick={() => handleStepChange('template-selection', { uploadedFiles })}
              >
                Continue ({uploadedFiles.length} file{uploadedFiles.length !== 1 ? 's' : ''})
              </button>
            </div>
          </div>
        );

      case 'template-selection':
        return (
          <TemplateSelectionStep
            onBack={() => handleStepChange('upload', {})}
            onSelectScratch={() => handleStepChange('editor', { initialTemplateHtml: '', reportTemplateCss: '' })}
            onSelectTemplate={(htmlContent, cssContent) => {
              handleStepChange('editor', {
                reportTemplate: htmlContent,
                reportTemplateCss: cssContent,
                initialTemplateHtml: htmlContent
              });
            }}
            onProcessingStart={() => {
              setTemplateUploadError(null);
              setIsProcessingTemplate(true);
            }}
            onProcessingEnd={() => setIsProcessingTemplate(false)}
            uploadError={templateUploadError}
            onUploadError={setTemplateUploadError}
          />
        );

      case 'editor':
        return (
          <EditorStep
            reportTemplate={currentStep.data.reportTemplate || ''}
            reportTemplateCss={currentStep.data.reportTemplateCss}
            initialTemplateHtml={currentStep.data.initialTemplateHtml}
            questions={currentStep.data.questions || []}
            onTemplateChange={(template) => {
              handleStepChange('editor', { reportTemplate: template });
            }}
            onTemplateCssChange={(css) => {
              handleStepChange('editor', { reportTemplateCss: css });
            }}
            onQuestionsChange={(questions) => {
              handleStepChange('editor', { questions });
            }}
            onBack={() => handleStepChange('template-selection', {})}
            onNext={() => handleStepChange('naming', {})}
          />
        );

      case 'naming':
        return (
          <div className="step-content">
            <h2>Name Your Agent</h2>
            <p>Give your custom agent a name and description so you can easily find and use it later.</p>

            <div className="naming-form">
              <div className="form-group">
                <label htmlFor="agentName">Agent Name *</label>
                <input
                  type="text"
                  id="agentName"
                  placeholder="e.g., Contract Analysis Agent"
                  value={currentStep.data.agentName || ''}
                  onChange={(e) => handleStepChange('naming', { agentName: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="agentDescription">Description</label>
                <textarea
                  id="agentDescription"
                  placeholder="Describe what this agent does and what types of documents it processes..."
                  rows={3}
                  value={currentStep.data.agentDescription || ''}
                  onChange={(e) => handleStepChange('naming', { agentDescription: e.target.value })}
                />
              </div>
            </div>

            <div className="step-actions">
              <button
                className="btn-secondary"
                onClick={() => handleStepChange('editor', {})}
              >
                Back
              </button>
              <button
                className="btn-primary"
                disabled={!currentStep.data.agentName}
                onClick={handleCreateAgent}
              >
                {isEditMode ? 'Update Agent' : 'Create Agent'}
              </button>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  // Show loading state while fetching agent data for editing
  if (loadingAgent) {
    return (
      <div className="create-agent-page">
        <div className="create-agent-header">
          <h1>Edit Custom Agent</h1>
        </div>
        <div className="create-agent-content">
          <div className="loading-state">
            <p>Loading agent data...</p>
          </div>
        </div>
      </div>
    );
  }

  // Show full-screen loading state when processing template upload
  if (isProcessingTemplate) {
    return <TemplateProcessingLoadingState />;
  }

  return (
    <div className="create-agent-page">
      <div className="create-agent-header">
        <h1>{isEditMode ? 'Edit Custom Agent' : 'Create Custom Agent'}</h1>
        {renderStepIndicator()}
      </div>

      <div className="create-agent-content">
        {renderCurrentStep()}
      </div>
    </div>
  );
};

export default CreateAgent;
