# Implementation Plan

## Overview
Add custom agent creation functionality to Attenly, allowing users to create their own AI-powered document processing agents. Users will upload example documents, create professional report templates using a rich text editor, and define AI extraction points through an interactive modal system.

The implementation extends the existing agent system architecture by adding user-created agents alongside prebuilt ones. Custom agents follow the same execution flow as prebuilt agents but store questions in the database instead of JSON seed files. The feature integrates seamlessly with existing file processing, vector store, LLM services, and authentication systems.

## Types
Database model extensions for custom agent support.

**Extended Agent Model Fields:**
- `user_id: UUID` - Links custom agents to their creators (nullable for prebuilt agents)
- `is_custom: Boolean` - Distinguishes custom from prebuilt agents (default: False)
- `created_by_name: String` - User's display name for agent attribution (nullable)

**New TypeScript Interfaces:**
```typescript
interface CustomAgent extends Agent {
  user_id: string;
  is_custom: boolean;
  created_by_name?: string;
  can_delete: boolean; // Frontend computed property
}

interface AgentCreationStep {
  step: 'upload' | 'editor' | 'naming';
  data: {
    uploadedFiles?: UploadedFile[];
    reportTemplate?: string;
    questions?: AgentQuestion[];
    agentName?: string;
    agentDescription?: string;
  };
}

interface AIQuestionModal {
  isOpen: boolean;
  question: string;
  answer?: string;
  quotes?: Quote[];
  isLoading: boolean;
  cursorPosition?: number;
}
```

## Files
File modifications and new file creation for custom agent functionality.

**New Files to Create:**
- `frontend/src/pages/CreateAgent.tsx` - Multi-step agent creation wizard
- `frontend/src/pages/CreateAgent.css` - Styling for agent creation pages
- `frontend/src/components/agent-creation/FileUploadStep.tsx` - File upload step with instructions
- `frontend/src/components/agent-creation/EditorStep.tsx` - TinyMCE editor with AI modal
- `frontend/src/components/agent-creation/NamingStep.tsx` - Agent naming and finalization
- `frontend/src/components/agent-creation/AIQuestionModal.tsx` - Interactive AI question modal
- `frontend/src/components/agent-creation/AIQuestionModal.css` - Modal styling
- `frontend/src/components/dashboard/CustomAgentCard.tsx` - Custom agent card with delete
- `frontend/src/components/dashboard/CustomAgentCard.css` - Custom agent card styling

**Files to Modify:**
- `backend/app/models.py` - Add user_id, is_custom, created_by_name fields to Agent model
- `backend/app/schemas.py` - Add CustomAgentOut schema and creation request schemas
- `backend/app/routers/agents.py` - Add custom agent CRUD endpoints
- `frontend/src/pages/Dashboard.tsx` - Add "Create Agent" button and custom agent section
- `frontend/src/pages/Dashboard.css` - Styling for custom agent section
- `frontend/src/components/dashboard/PrebuiltAgentCard.tsx` - Add delete functionality for custom agents
- `frontend/package.json` - Add TinyMCE dependencies
- `backend/requirements.txt` - No new dependencies needed

**Configuration Updates:**
- Database migration for new Agent model fields
- Router registration for new custom agent endpoints

## Functions
Function modifications and new function creation.

**New Backend Functions:**
- `create_custom_agent(agent_data: CreateCustomAgentRequest, current_user)` - Create new custom agent in database
- `get_user_custom_agents(user_id: str)` - Retrieve user's custom agents
- `delete_custom_agent(agent_id: str, user_id: str)` - Delete user's custom agent with validation
- `update_custom_agent(agent_id: str, agent_data: UpdateCustomAgentRequest, user_id: str)` - Update custom agent
- `validate_agent_ownership(agent_id: str, user_id: str)` - Verify user owns the custom agent

**New Frontend Functions:**
- `useAgentCreation()` - Custom hook for managing agent creation state
- `useTinyMCE()` - Custom hook for TinyMCE editor integration
- `useAIQuestionModal()` - Custom hook for AI question modal state
- `insertAIPlaceholder(editor, placeholder: string)` - Insert AI placeholder at cursor
- `handleAIQuestionSubmit(question: string, uploadedFiles: UploadedFile[])` - Process AI question
- `saveCustomAgent(agentData: AgentCreationStep)` - Save completed custom agent
- `deleteCustomAgent(agentId: string)` - Delete custom agent with confirmation

**Modified Backend Functions:**
- `list_prebuilt_agents()` - Rename to `list_agents()` and include custom agents with user filtering
- `get_agent_by_id()` - Add custom agent support with ownership validation
- Agent model constructor - Handle new fields with proper defaults

**Modified Frontend Functions:**
- Dashboard component - Add custom agent section and create button
- Agent execution flow - Handle both prebuilt and custom agents seamlessly

## Classes
Class modifications and new class creation.

**Extended Classes:**
- `Agent` (SQLAlchemy model) - Add user_id, is_custom, created_by_name fields with proper relationships
- `AgentQuestion` (SQLAlchemy model) - No changes needed, existing foreign key relationship works

**New React Components (Functional):**
- `CreateAgent` - Main wizard component with step management
- `FileUploadStep` - File upload with clear example document instructions
- `EditorStep` - TinyMCE integration with AI question modal
- `NamingStep` - Agent naming and description form
- `AIQuestionModal` - Interactive modal for AI question processing
- `CustomAgentCard` - Agent card with delete functionality

**New Custom Hooks:**
- `useAgentCreation` - Manages multi-step creation state
- `useTinyMCE` - Handles TinyMCE editor lifecycle
- `useAIQuestionModal` - Manages AI question modal state and processing

## Dependencies
New package dependencies and integration requirements.

**Frontend Dependencies (package.json):**
```json
{
  "@tinymce/tinymce-react": "^4.3.2",
  "tinymce": "^6.8.2"
}
```

**TinyMCE Configuration:**
- Full Microsoft Word-like functionality (tables, formatting, fonts, colors)
- Custom toolbar with "Add AI Ability" button
- Cursor position tracking for placeholder insertion
- Rich text output compatible with existing report system

**Backend Dependencies:**
- No new dependencies required
- Utilizes existing FastAPI, SQLAlchemy, and authentication systems

**Integration Requirements:**
- TinyMCE CDN integration for editor assets
- Existing vector store and LLM services for AI question processing
- Existing file upload and document processing pipeline
- Existing authentication and user management system

## Testing
Testing approach and validation strategies.

**Unit Testing:**
- Custom agent CRUD operations with user ownership validation
- TinyMCE editor integration and placeholder insertion
- AI question modal functionality and state management
- Database model extensions and migrations

**Integration Testing:**
- Complete agent creation workflow from file upload to dashboard
- Custom agent execution flow matching prebuilt agent behavior
- File upload integration with existing document processing pipeline
- AI question processing using existing LLM and vector store services

**User Acceptance Testing:**
- Multi-step wizard navigation and state persistence
- TinyMCE editor functionality and user experience
- AI question modal with live preview and reference viewing
- Custom agent management (create, execute, delete) from dashboard

**Validation Strategies:**
- Custom agent ownership validation on all operations
- File upload validation using existing document classification
- Template HTML validation and placeholder syntax checking
- Database constraint validation for agent-question relationships

## Implementation Order
Logical sequence of implementation to minimize conflicts and ensure successful integration.

**Step 1: Database and Backend Foundation**
- Extend Agent model with new fields (user_id, is_custom, created_by_name)
- Create database migration for new fields
- Add custom agent schemas (CreateCustomAgentRequest, CustomAgentOut)
- Implement custom agent CRUD endpoints in agents router
- Add ownership validation and user filtering logic

**Step 2: Frontend Dependencies and Base Components**
- Add TinyMCE dependencies to package.json
- Create base CreateAgent page with routing
- Implement useAgentCreation hook for state management
- Create FileUploadStep component reusing existing FileUpload logic
- Add "Create Agent" button to Dashboard with navigation

**Step 3: TinyMCE Editor Integration**
- Implement EditorStep component with TinyMCE integration
- Create useTinyMCE hook for editor lifecycle management
- Add custom toolbar with "Add AI Ability" button
- Implement cursor position tracking and placeholder insertion
- Style editor to match existing application design

**Step 4: AI Question Modal System**
- Create AIQuestionModal component with form and preview
- Implement useAIQuestionModal hook for state management
- Integrate with existing LLM service for question processing
- Add DocumentViewer integration for reference clicking
- Implement answer insertion and placeholder generation

**Step 5: Agent Creation Completion**
- Implement NamingStep component for agent finalization
- Add agent creation API integration and error handling
- Implement navigation back to dashboard after creation
- Add success/error feedback and validation messages

**Step 6: Dashboard Integration and Management**
- Create CustomAgentCard component with delete functionality
- Add custom agent section to Dashboard
- Implement custom agent filtering and display logic
- Add delete confirmation modal and API integration
- Update existing agent execution flow to handle custom agents

**Step 7: Testing and Polish**
- Comprehensive testing of complete workflow
- UI/UX refinements and responsive design
- Error handling and edge case validation
- Performance optimization and code cleanup
- Documentation updates and deployment preparation
