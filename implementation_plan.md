# Implementation Plan

## Overview
Add the ability to edit custom built agents by extending the existing CreateAgent flow to support both create and edit modes, ensuring all existing schemas and components are reused to avoid duplication.

This implementation will leverage the existing 3-step agent creation flow (Upload Examples → Create Template → Name & Save) for editing, with all fields pre-populated from the existing agent data. Users will need to reupload example documents during editing, and the AI testing modal will be enhanced to pre-populate existing question data when clicking placeholders in both create and edit modes.

## Types
Extend existing TypeScript interfaces to support edit mode detection and agent data pre-population.

**Extended Types:**
- `AgentCreationStep` interface: Add optional `editingAgent` field to track edit mode
- `AITestingModalProps` interface: Add optional `existingQuestion` field for pre-population
- `CustomAgentCardProps` interface: Add `onEdit` callback function for edit navigation
- Route parameters: Add `agentId?` optional parameter for URL-based edit mode detection

**New Type Definitions:**
```typescript
interface EditModeContext {
  isEditing: boolean;
  agentId?: string;
  originalAgent?: CustomAgent;
}

interface PrePopulatedAIModal {
  existingQuestion?: Question;
  questionText?: string;
  existingAnswer?: string;
  existingQuotes?: Quote[];
}
```

## Files
Modify existing files to add edit functionality without creating new components.

**Files to Modify:**
- `frontend/src/components/dashboard/CustomAgentCard.tsx`: Add edit button and navigation handler
- `frontend/src/pages/CreateAgent.tsx`: Add edit mode detection, agent data fetching, and pre-population logic
- `frontend/src/components/agent-creation/EditorStep.tsx`: Handle pre-population of existing template and questions
- `frontend/src/components/agent-creation/AITestingModal.tsx`: Add pre-population support for existing questions
- `frontend/src/App.tsx`: Add new route with optional agentId parameter for edit mode

**No New Files Created:** All functionality implemented by extending existing components

**Configuration Changes:**
- Router configuration: Update CreateAgent route to accept optional `/:agentId` parameter

## Functions
Extend existing functions and add new helper functions for edit mode support.

**New Functions:**
- `CreateAgent.fetchAgentForEditing(agentId: string)`: Fetch existing agent data for edit mode
- `CreateAgent.isEditMode()`: Detect if component is in edit vs create mode based on URL
- `CustomAgentCard.handleEditClick()`: Navigate to edit mode with agent ID
- `AITestingModal.populateFromExisting()`: Pre-fill modal with existing question data
- `EditorStep.populateExistingTemplate()`: Load existing template and questions into editor

**Modified Functions:**
- `CreateAgent.handleCreateAgent()`: Use PUT request for updates vs POST for creation
- `CreateAgent.handleStepChange()`: Preserve existing agent data during step navigation
- `EditorStep.handleEditQuestion()`: Pass existing question data to AI testing modal
- `AITestingModal.handleAddToTemplate()`: Support both add new and update existing question flows

## Classes
No new classes required - all functionality implemented through functional component extensions.

**Modified Components:**
- `CreateAgent`: Extended to support dual create/edit modes with conditional logic
- `CustomAgentCard`: Enhanced with edit button and navigation handling
- `EditorStep`: Updated to handle pre-populated template and question data
- `AITestingModal`: Enhanced with pre-population support for existing questions

**Component State Extensions:**
- `CreateAgent`: Add `editMode` state and `originalAgent` state for tracking
- `AITestingModal`: Add state for pre-populated form values
- All components maintain existing functionality while adding edit capabilities

## Dependencies
No new dependencies required - all functionality implemented using existing libraries and APIs.

**Existing Dependencies Utilized:**
- React Router: Use existing `useParams()` hook for agentId extraction
- Existing API utilities: Reuse `api()` function for agent fetching
- Backend APIs: Use existing `GET /agents/{agent_id}` and `PATCH /agents/custom/{agent_id}` endpoints
- TinyMCE Editor: Leverage existing editor configuration and event handlers

**API Integration:**
- GET `/agents/{agent_id}`: Fetch existing agent data for editing
- PUT `/agents/custom/{agent_id}`: Update existing agent (backend endpoint already exists)
- All file upload and AI testing endpoints remain unchanged

## Testing
Extend existing testing approach to cover edit mode functionality.

**Test Scenarios:**
- Edit mode detection and agent data fetching
- Pre-population of all form fields during edit flow
- AI testing modal pre-population with existing question data
- Template editor handling of existing questions and placeholders
- Update API calls vs create API calls based on mode
- Navigation between edit and create modes

**Testing Strategy:**
- Manual testing through UI for all edit flow scenarios
- Verify pre-population works correctly for all agent fields
- Test AI modal enhancement in both create and edit contexts
- Ensure existing create flow remains unaffected

## Implementation Order
Implement changes in dependency order to minimize conflicts and ensure successful integration.

1. **Add Edit Button to CustomAgentCard**: Implement edit button UI and navigation handler to establish entry point
2. **Extend CreateAgent for Edit Mode Detection**: Add URL parameter parsing and edit mode state management
3. **Add Agent Data Fetching**: Implement API call to fetch existing agent data when in edit mode
4. **Implement Field Pre-population**: Pre-fill agent name, description, and step data from fetched agent
5. **Enhance EditorStep for Template Loading**: Load existing template and questions into TinyMCE editor
6. **Extend AITestingModal Pre-population**: Add support for pre-filling modal with existing question data
7. **Update API Integration**: Modify save handler to use PUT requests for updates vs POST for creation
8. **Add Route Configuration**: Update App.tsx routing to support optional agentId parameter
9. **Testing and Validation**: Comprehensive testing of edit flow and existing functionality preservation
10. **Documentation and Refinement**: Final polish and edge case handling
