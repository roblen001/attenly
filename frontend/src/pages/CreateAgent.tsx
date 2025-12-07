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

const L = {
  p: '[CreateAgent]',
  log: (...args: unknown[]) => console.log('[CreateAgent]', ...args),
  group: (name: string) => console.group(`[CreateAgent] ${name}`),
  end: () => console.groupEnd(),
};

const ids = (qs?: QuestionOut[]) => (qs ?? []).map(q => q.id);

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

        console.log('Agent loaded for editing:', agent.name);
        console.log('Template transformed for editing - placeholders restored:', mappedQuestions.length);
        console.log('Edit mode: skipping directly to editor step');

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
        console.log('Files cleared on leaving agent creation page');
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
    L.group('handleStepChange');
    L.log('IN:', { newStep, newData });
    setCurrentStep(prev => {
      const merged = {
        step: newStep,
        data: { ...prev.data, ...newData }
      };
      L.log('PREV:', {
        step: prev.step,
        reportTemplateLen: prev.data.reportTemplate?.length ?? 0,
        questionsLen: prev.data.questions?.length ?? 0,
        questionsIds: ids(prev.data.questions),
      });
      L.log('OUT:', {
        step: merged.step,
        reportTemplateLen: merged.data.reportTemplate?.length ?? 0,
        questionsLen: merged.data.questions?.length ?? 0,
        questionsIds: ids(merged.data.questions),
      });
      L.end();
      return merged;
    });
  };

  const handleCancel = async () => {
    // Clear files when user explicitly cancels agent creation
    try {
      await api('/agents/files/clear', { method: 'DELETE' });
      console.log('Files cleared on agent creation cancellation');
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

      L.group(isEditMode ? 'handleUpdateAgent' : 'handleCreateAgent');
      L.log('Original template length:', reportTemplate.length);
      L.log('Final template length:', finalTemplate.length);
      L.log('Has custom CSS:', !!reportTemplateCss);
      L.log('Original questions:', questions.map(q => ({ id: q.id, placeholder: q.placeholder })));
      L.log('Transformed questions:', cleanQuestions.map(q => ({ id: q.id, placeholder: q.placeholder })));
      L.log('payload:', {
        name: requestPayload.name,
        descriptionLen: (requestPayload.description || '').length,
        reportTemplateLen: requestPayload.report_template.length,
        reportTemplateCssLen: requestPayload.report_template_css?.length ?? 0,
        questionsLen: requestPayload.questions.length,
        questionsIds: ids(requestPayload.questions),
      });
      L.end();

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

      const resultAgent = await response.json();
      console.log(`Custom agent ${isEditMode ? 'updated' : 'created'} successfully:`, resultAgent);

      // Clear files after successful operation
      try {
        await api('/agents/files/clear', { method: 'DELETE' });
        console.log(`Files cleared after successful agent ${isEditMode ? 'update' : 'creation'}`);
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
            <p>Upload 1-3 example documents that represent the type of files your agent will process. These help the AI understand your document structure and content.</p>

            <FileUpload
              files={uploadedFiles}
              onFilesChange={(files) => {
                L.group('onFilesChange');
                L.log('files len=', files.length);
                L.end();
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
            onSelectTemplate={(htmlContent, cssContent, source) => {
              console.log(`Template uploaded via ${source}, CSS length: ${cssContent.length}`);
              handleStepChange('editor', { 
                reportTemplate: htmlContent,
                reportTemplateCss: cssContent,
                initialTemplateHtml: htmlContent 
              });
            }}
            onProcessingStart={() => setIsProcessingTemplate(true)}
            onProcessingEnd={() => setIsProcessingTemplate(false)}
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
              L.group('onTemplateChange (parent)');
              L.log('templateLen=', template?.length ?? 0);
              L.end();
              handleStepChange('editor', { reportTemplate: template });
            }}
            onTemplateCssChange={(css) => {
              L.group('onTemplateCssChange (parent)');
              L.log('cssLen=', css?.length ?? 0);
              L.end();
              handleStepChange('editor', { reportTemplateCss: css });
            }}
            onQuestionsChange={(questions) => {
              L.group('onQuestionsChange (parent)');
              L.log('questions len=', questions.length, 'ids=', ids(questions));
              L.end();
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

  // Top-level watcher to see final merged state after any change
  React.useEffect(() => {
    L.group('currentStep changed');
    L.log('step=', currentStep.step);
    L.log('reportTemplateLen=', currentStep.data.reportTemplate?.length ?? 0);
    L.log('questionsLen=', currentStep.data.questions?.length ?? 0, 'ids=', ids(currentStep.data.questions));
    L.end();
  }, [currentStep]);

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
