# Active Context: Attenly

## Current Work Focus

### Primary Development Phase
**Phase 2: Enhanced AI Processing and Template Expansion**

The project is currently in the second development phase, focusing on building out the core AI processing capabilities and expanding the template system beyond the initial proof-of-concept.

### Active Development Areas

#### 1. Document Classification & Processing System ✅ **COMPLETED**
- **Current State**: Intelligent document classification system implemented
- **Key Components**:
  - `DocumentClassifier` (`backend/app/services/document_classifier.py`): Analyzes file type and content type
  - Enhanced `DocumentProcessor` with classifier-based routing
  - Image-based PDF detection to prevent OCR-dependent files from failing processing
- **Capabilities**:
  - Early detection of image-based/scanned PDFs with clear error messages
  - Extensible architecture ready for future OCR integration
  - Content analysis (text-based, image-based, mixed, empty)
  - Intelligent processor routing based on document characteristics
- **Next Steps**: OCR processor integration when needed

#### 2. Agent Execution Pipeline
- **Current State**: Frontend UI for agent execution is implemented with mock processing
- **Active Work**: Building the actual AI processing backend that connects uploaded files to agent templates
- **Key Component**: `frontend/src/pages/AgentExecution.tsx` has placeholder functions for report generation

#### 3. Template System Expansion
- **Current State**: Two prebuilt agents defined in JSON format
  - Account Summary Report (27 data points)
  - Loss History Snapshot (28 data points)
- **Active Work**: Making the template system more flexible and user-configurable
- **Future**: Custom agent creation interface

## Recent Changes and Decisions

### Architecture Decisions
1. **Agent Template Structure**: Decided on JSON-based agent definitions with HTML templates and question arrays
2. **File Upload Strategy**: Implemented drag-and-drop interface with file validation
3. **State Management**: Using local React state with direct API calls (no global state management yet)
4. **Authentication**: Session-based authentication chosen over JWT for simplicity

### Implementation Patterns
1. **Component Organization**: Separated AgentExecution components into dedicated directory
2. **API Structure**: RESTful endpoints with clear separation between auth and agent operations
3. **Database Design**: UUID primary keys for agents, string IDs for users
4. **Error Handling**: Consistent error state management across components

## Current Technical Challenges

### 1. AI Integration Gap
- **Challenge**: Mock processing in frontend needs real AI backend implementation
- **Impact**: Core value proposition not yet functional
- **Priority**: High - this is the main product differentiator

### 2. File Processing Pipeline
- **Challenge**: PDF text extraction needs to connect to AI analysis
- **Current**: Basic PDF parsing exists but not integrated with agent processing
- **Next Step**: Build the data extraction pipeline

### 3. Template Population
- **Challenge**: HTML templates have placeholders but no substitution mechanism
- **Current**: Templates defined but not dynamically populated
- **Solution**: Need template engine integration

## Active Code Patterns and Preferences

### Frontend Patterns
- **Component Structure**: Functional components with TypeScript interfaces
- **State Management**: useState hooks for local state, no global state library
- **Styling**: Component-scoped CSS files with descriptive class names
- **API Calls**: Direct fetch calls through custom `api` utility function
- **Error Handling**: Loading/error states in component state

### Backend Patterns
- **Route Organization**: Separate routers for different functional areas
- **Database Access**: SQLAlchemy ORM with relationship mapping
- **Authentication**: Dependency injection for protected routes
- **Service Layer**: Business logic separated from API endpoints
- **Configuration**: Environment-aware settings (dev vs production)

### Code Quality Standards
- **TypeScript**: Strict mode enabled with proper interface definitions
- **File Organization**: Clear separation between components, pages, services
- **Naming Conventions**: Descriptive names for components and functions
- **Import Structure**: Organized imports with relative paths

## Current Development Workflow

### Development Environment
- **Backend**: FastAPI with auto-reload on file changes
- **Frontend**: Vite dev server with hot module replacement
- **Database**: SQLite with automatic table creation in dev mode
- **CORS**: Configured for local development (ports 5173 and 8000)

### Testing Strategy
- **Current**: Manual testing through UI
- **Needed**: Unit tests for core business logic
- **Future**: Integration tests for API endpoints

## Key Insights and Learnings

### User Experience Insights
1. **File Upload UX**: Drag-and-drop interface is intuitive and expected by users
2. **Progress Feedback**: Users need clear indication of processing status
3. **Agent Selection**: Prebuilt templates provide good starting point for users
4. **Report Preview**: Users want to review and edit extracted data before final export

### Technical Insights
1. **Template Flexibility**: HTML templates with placeholders provide good balance of structure and customization
2. **Agent Configuration**: JSON-based agent definitions are developer-friendly and version-controllable
3. **File Processing**: PDF parsing is complex and may need multiple strategies for different document types
4. **State Management**: Simple local state is sufficient for current complexity level

### Performance Considerations
1. **File Upload**: Need to handle large PDF files efficiently
2. **AI Processing**: May need async processing with progress updates for large documents
3. **Template Rendering**: HTML templates should render quickly in browser
4. **Database Queries**: Agent and question relationships need efficient loading

## Next Steps and Priorities

### Immediate Priorities (Next Sprint)
1. **Implement AI Processing**: Connect PDF parsing to actual data extraction
2. **Template Population**: Build mechanism to substitute placeholders with extracted data
3. **Report Generation**: Complete the mock-to-real processing pipeline
4. **Error Handling**: ✅ **COMPLETED** - Robust error handling for file processing failures

### Recently Completed Work
1. **Vector Store Clearing on Navigation** (January 2025):
   - **NEW FEATURE**: Implemented automatic vector store clearing when users navigate away from agent execution page
   - **Problem Solved**: Vector store was never cleared, causing data mixing between agent sessions and memory accumulation
   - **Solution**: Added cleanup effect in React component that triggers on navigation away
   - **Implementation**:
     - **Backend**: New `DELETE /agents/files/clear` endpoint that clears both vector store and uploaded files storage
     - **Frontend**: `useEffect` cleanup function in `AgentExecution.tsx` that calls clear endpoint on component unmount
     - **Vector Store**: Uses existing `cleanup_user_session()` method to delete entire user collection
   - **Benefits**:
     - Fresh start for each agent session
     - Prevents data mixing between different agent executions
     - Reduces memory usage in ChromaDB
     - Automatic cleanup (no user action required)
   - **Navigation Scenarios Covered**:
     - Back to Dashboard button clicks
     - Browser back/forward navigation
     - Direct URL navigation
     - Page refresh and tab close
   - **Technical Details**:
     - Non-blocking: Navigation continues even if cleanup fails
     - User-isolated: Each user's cleanup is independent
     - Idempotent: Safe to call multiple times

2. **File Deletion Race Condition Fix** (January 2025):
   - **ISSUE RESOLVED**: Fixed edge case where deleting uploaded files during concurrent processing caused 404 errors
   - **Root Cause**: Race condition between file deletion and ongoing upload processing created inconsistent UI/backend state
   - **Solution**: Enhanced frontend error handling to treat 404 responses as successful deletions
   - **Changes Made**:
     - Modified `removeFile()` function in `FileUpload.tsx` to handle 404 errors gracefully
     - Files are removed from UI regardless of whether backend deletion succeeds or file was already gone
     - Only shows error messages for genuine deletion failures (not 404s)
   - **User Experience**: Clicking delete on any file now consistently removes it from view
   - **Technical Details**:
     - Frontend-only solution requiring no backend changes
     - Maintains all existing upload/processing functionality
     - Zero risk implementation (only affects error handling paths)

2. **Document Classification System** (January 2025):
   - **NEW**: Implemented intelligent document classification system
   - Created `DocumentClassifier` service for content analysis and processor routing
   - Enhanced `DocumentProcessor` with classifier-based validation and processing
   - Added image-based PDF detection to prevent OCR-dependent files from failing
   - Implemented clear error messages with actionable guidance for users
   - Built extensible architecture ready for future OCR integration
   - Features:
     - File type detection (PDF, DOCX, TXT, etc.)
     - Content analysis (text-based, image-based, mixed, empty)
     - Intelligent processor routing recommendations
     - Configurable detection thresholds
     - Comprehensive test suite and documentation

2. **Chunk Processing Error Handling** (January 2025):
   - Enhanced `DocumentProcessor.process_document()` to properly detect chunk storage failures
   - Added validation in `ChunkingService.create_two_level_chunks()` for empty chunks and invalid data
   - Implemented proper error propagation when vector store fails to store chunks (returns 0)
   - Files now properly show failed status (❌ icon) when chunk processing fails
   - Error scenarios covered:
     - Vector store unavailable or fails to store chunks
     - Chunking service fails to create L1 or L2 chunks
     - Invalid PDF data with no extractable pages
     - Any exception during the chunking pipeline

3. **File Duplicate Prevention System** (January 2025):
   - **NEW**: Implemented content-based duplicate detection for file uploads
   - Added SHA-256 content hashing to prevent identical files from being processed twice
   - Enhanced upload endpoint with duplicate detection logic in `backend/app/routers/agents.py`
   - Features:
     - Content hash calculation using `calculate_content_hash()` utility function
     - Session-based duplicate detection with `find_duplicate_file()` lookup
     - Automatic reuse of existing processed chunks when duplicate detected
     - Clear user feedback with duplicate status and original filename reference
     - Enhanced response summary with duplicate count tracking
     - Prevents unnecessary vector database storage and processing overhead
   - Benefits:
     - Eliminates duplicate chunks in ChromaDB vector store
     - Faster upload response for repeated files (instant duplicate detection)
     - Reduced memory usage in session cache
     - Better user experience with clear duplicate messaging
     - Maintains processing statistics from original file

4. **Enhanced Upload System with Cancellation** (January 2025):
   - **NEW**: Implemented comprehensive upload cancellation and queue management system
   - Added AbortController-based cancellation for individual file uploads
   - Enhanced TypeScript interfaces with new upload states: 'queued', 'cancelled'
   - Features:
     - **Individual File Cancellation**: Users can cancel specific files during upload
     - **Cancel All Button**: Batch cancellation of all pending uploads
     - **Queue Visualization**: Clear indication of upload queue position (#1, #2, etc.)
     - **Smart Button Controls**: Cancel button (⏹️) for uploading/queued files, Remove (✕) for completed files
     - **Immediate UI Feedback**: Cancelled files are removed from UI instantly (no "cancelled" status shown)
     - **AbortController Integration**: Proper HTTP request cancellation using native browser APIs
     - **Race Condition Prevention**: Handles cancellation during sequential upload processing
   - Benefits:
     - **Improved UX**: Users have full control over upload process
     - **No Orphaned Uploads**: Cancelled requests don't continue processing in background
     - **Clear Status Indicators**: Queue position, uploading status, and completion states
     - **Responsive Interface**: Upload controls adapt based on file status
     - **Resource Efficiency**: Cancelled uploads free up network and processing resources
   - Technical Implementation:
     - Updated `UploadedFile` interface with `abortController`, `queuePosition`, `progress` fields
     - Enhanced `FileUpload.tsx` with `cancelFileUpload()` and `cancelAllUploads()` functions
     - Improved status handling with queue position display and dynamic button controls
     - Proper cleanup of cancelled files from UI state management

5. **File Cancellation Bug Fix** (January 2025):
   - **ISSUE RESOLVED**: Fixed bug where cancelled files would reappear in UI with "cancelled" status
   - **Root Cause**: AbortError handling in `handleFileUpload()` was creating cancelled file objects and adding them back to UI
   - **Solution**: Modified error handling to completely remove cancelled files from UI without creating status objects
   - **Changes Made**:
     - Updated AbortError catch block to filter out cancelled files instead of updating their status
     - Removed 'cancelled' status from TypeScript `UploadedFile` interface
     - Cleaned up UI helper functions to remove cancelled status handling
     - Ensured cancelled files are excluded from error summary counts
   - **Result**: Cancelled files are now completely removed from both upload process and frontend view
   - **Files Modified**:
     - `frontend/src/components/AgentExecution/FileUpload.tsx`: Fixed AbortError handling
     - `frontend/src/types/index.ts`: Removed 'cancelled' from status union type
   - **Testing**: Verified that individual and batch cancellation properly removes files from UI

### Medium-term Goals
1. **Custom Agent Creation**: UI for users to create their own agents
2. **Batch Processing**: Handle multiple documents at once
3. **Report Editing**: Allow users to modify extracted data before export
4. **Template Marketplace**: Share and discover agent templates

### Technical Debt
1. **Environment Configuration**: Move hardcoded values to environment variables
2. **Database Migration**: Implement proper migration system for schema changes
3. **API Documentation**: Generate and maintain API documentation
4. **Testing Coverage**: Add comprehensive test suite

## Integration Points

### External Services Needed
1. **AI/ML Service**: For document analysis and data extraction
2. **File Storage**: Cloud storage for uploaded documents (future)
3. **Email Service**: For user notifications and verification (future)
4. **Analytics**: Usage tracking and performance monitoring (future)

### API Endpoints Status
- **Authentication**: ✅ Implemented
- **Agent Management**: ✅ Basic CRUD operations
- **File Upload**: 🔄 Frontend ready, backend integration needed
- **Report Generation**: ❌ Mock implementation only
- **Template Management**: ❌ Not yet implemented

## Current Blockers and Dependencies

### Technical Blockers
1. **AI Service Integration**: Need to choose and integrate AI/ML service for text analysis
2. **Template Engine**: Need to implement HTML template substitution mechanism
3. **File Storage**: Current file handling is temporary, need persistent storage strategy

### Decision Points
1. **AI Provider**: OpenAI, Anthropic, or local models for data extraction
2. **File Storage**: Local filesystem vs cloud storage (AWS S3, etc.)
3. **Template Engine**: Custom implementation vs existing library (Jinja2, etc.)
4. **Deployment Strategy**: Traditional hosting vs containerization vs serverless

## Development Environment Notes

### Local Setup Requirements
- Python 3.8+ for backend
- Node.js 18+ for frontend
- SQLite for development database
- Git for version control

### Common Development Commands
```bash
# Backend
cd backend && python -m app.main

# Frontend  
cd frontend && npm run dev

# Database reset (if needed)
rm backend/app.db
```

### IDE Configuration
- VSCode with Python and TypeScript extensions
- ESLint configuration for code quality
- TypeScript strict mode for type safety
