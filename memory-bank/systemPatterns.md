# System Patterns: Attenly

## Overall Architecture

### High-Level System Design
```
Frontend (React/TypeScript) ←→ Backend API (FastAPI) ←→ Database (SQLite/PostgreSQL)
                                        ↓
                                 AI Processing Layer
                                        ↓
                                 File Processing Service
```

### Architectural Patterns
- **MVC Pattern**: Clear separation between models, views, and controllers
- **RESTful API**: Standard HTTP methods for resource management
- **Component-Based Frontend**: Reusable React components with TypeScript
- **Service Layer Pattern**: Business logic separated from API endpoints
- **Repository Pattern**: Data access abstraction through SQLAlchemy ORM

## Backend Architecture

### Core Components
1. **FastAPI Application** (`app/main.py`)
   - CORS middleware for frontend communication
   - Session middleware for authentication
   - Router inclusion for modular endpoints

2. **Database Layer** (`app/db.py`, `app/models.py`)
   - SQLAlchemy ORM with declarative base
   - UTC timestamp handling for consistency
   - Relationship mapping between entities

3. **API Routers** (`app/routers/`)
   - `auth.py`: User authentication and session management
   - `agents.py`: Agent CRUD operations and execution

4. **Services Layer** (`app/services/`)
   - `document_classifier.py`: Intelligent document analysis and routing
   - `document_processor.py`: Main orchestrator with classifier integration
   - `pdf_parser.py`: Advanced PDF processing with table extraction
   - `chunking_service.py`: Document chunking for AI processing
   - `vector_store.py`: Vector database integration
   - Separation of business logic from API endpoints

### Database Schema Design
```
Users
├── id (String, Primary Key)
├── email (String, Indexed)
├── full_name (String, Optional)
├── hashed_password (String)
├── is_active (Boolean)
├── is_verified (Boolean)
└── timestamps (created_at, updated_at)

Agents
├── id (UUID, Primary Key)
├── name (String)
├── description (Text)
├── report_template (Text, HTML)
├── timestamps (created_at, updated_at)
└── questions (One-to-Many relationship)

AgentQuestions
├── id (UUID, Primary Key)
├── agent_id (UUID, Foreign Key)
├── placeholder (String)
├── prompt (Text)
└── unique constraint (agent_id, placeholder)
```

### Key Design Patterns

#### Agent Template Pattern
- **Template Method**: HTML templates with placeholder substitution
- **Strategy Pattern**: Different agents implement different extraction strategies
- **Configuration Pattern**: JSON-based agent definitions with questions array

#### Document Classification & Processing Pipeline
```
Document Upload → Document Classification → Processor Routing → Content Extraction → AI Analysis → Data Mapping → Template Population → Report Generation
```

**Classification Architecture:**
- **DocumentClassifier**: Analyzes file type and content characteristics
- **ProcessorType Enum**: Defines available processors (PDF, OCR, DOCX, etc.)
- **ContentType Analysis**: Distinguishes text-based, image-based, mixed, and empty content
- **Intelligent Routing**: Routes documents to appropriate processors based on analysis
- **Extensible Design**: Ready for future OCR and multi-format support

**Processing Flow:**
1. **File Type Detection**: Validates file extension and content structure
2. **Content Analysis**: Analyzes text density, word count, and image presence
3. **Processor Recommendation**: Determines best processing approach
4. **Early Validation**: Provides clear error messages for unsupported content
5. **Processor Routing**: Directs to appropriate handler (PDF, OCR, etc.)

#### Document Processor Pattern
- **Strategy Pattern**: Different processors for different document types
- **Factory Pattern**: Processor selection based on classification results
- **Plugin Architecture**: Extensible processor registration system
- **Error Handling**: Comprehensive validation with user-friendly messages

#### Authentication Pattern
- JWT token-based authentication with Supabase
- Token validation through Supabase Auth API
- User state management through FastAPI dependencies with JWT validation
- Frontend authentication state managed by Supabase client

## Frontend Architecture

### Component Hierarchy
```
App
├── LandingPage
├── Dashboard
│   └── PrebuiltAgentCard
├── AgentExecution
│   ├── FileUpload
│   └── ReportGeneration (planned)
└── ReportView
    ├── ReportHeader
    ├── ReportActionsBar
    ├── ReportInstructions
    ├── ReportContent
    ├── EditAnswerModal
    ├── DocumentViewer
    ├── LoadingState
    └── ErrorState
```

### State Management Patterns
- **Local State**: React useState for component-specific data
- **Props Drilling**: Data passed down through component hierarchy
- **API State**: Direct API calls with loading/error states
- **File State**: Centralized file upload state management
- **Custom Hooks**: Specialized hooks for complex state management
  - `useReportData`: Report data fetching and authentication
  - `useAnswerEditing`: In-place answer modification state
  - `useQuoteInteraction`: Quote-to-document viewing state
- **Hook Composition**: Multiple hooks working together in components

### Key Frontend Patterns

#### Component Design Pattern
- **Functional Components**: Using React hooks for state management
- **TypeScript Interfaces**: Strong typing for props and state
- **CSS Modules**: Scoped styling per component
- **Conditional Rendering**: Dynamic UI based on application state

#### API Integration Pattern
- **Custom HTTP Client**: Centralized API configuration (`libs/https.ts`)
- **Error Handling**: Consistent error state management
- **Loading States**: User feedback during async operations
- **Authentication Integration**: Supabase JWT validation in API calls
- **Report Data Fetching**: Complex data structures with nested relationships

#### Report Management Pattern
- **Data Flow**: ReportView → Custom Hooks → API → Backend
- **State Composition**: Multiple hooks managing different aspects of report state
- **Modal Management**: EditAnswerModal for in-place data modification
- **Document Interaction**: Quote clicking triggers document viewer
- **Error Boundaries**: Comprehensive error handling with fallback UI

#### File Upload Pattern
- **Drag & Drop Interface**: Intuitive file handling
- **File Validation**: Type and size checking
- **Progress Feedback**: Visual upload progress indicators

## Data Flow Patterns

### Agent Execution Flow
1. **Agent Selection**: User selects from prebuilt or custom agents
2. **File Upload**: Documents uploaded and validated
3. **Processing Trigger**: User initiates report generation
4. **AI Processing**: Backend extracts data using agent configuration
5. **Template Population**: Extracted data fills HTML template placeholders
6. **Report Delivery**: Generated report returned to frontend

### Authentication Flow
1. **Login Request**: User credentials sent to Supabase Auth
2. **Token Generation**: Supabase generates JWT token upon successful authentication
3. **Token Storage**: Frontend stores JWT token and manages auth state
4. **API Requests**: Backend validates JWT tokens via Supabase Auth API
5. **Protected Routes**: Frontend routes protected by Supabase auth state

### Error Handling Patterns
- **Backend**: HTTP status codes with descriptive error messages
- **Frontend**: Error boundaries and user-friendly error displays
- **Validation**: Input validation on both client and server sides

## Security Patterns

### Data Protection
- **Password Hashing**: bcrypt for secure password storage
- **Session Security**: Secure session middleware configuration
- **CORS Configuration**: Restricted origins for API access
- **Input Validation**: Sanitization of user inputs

### File Security
- **File Type Validation**: Restricted to supported formats
- **Size Limits**: Prevent large file uploads
- **Temporary Storage**: Secure handling of uploaded documents

## Performance Patterns

### Backend Optimization
- **Database Indexing**: Strategic indexes on frequently queried fields
- **Connection Pooling**: Efficient database connection management
- **Async Processing**: Non-blocking I/O for file operations

### Frontend Optimization
- **Component Memoization**: Prevent unnecessary re-renders
- **Lazy Loading**: Code splitting for better initial load times
- **Asset Optimization**: Vite build optimization

## Integration Patterns

### API Design
- **RESTful Endpoints**: Standard HTTP methods and status codes
- **JSON Communication**: Consistent data format
- **Versioning Strategy**: API version management (future consideration)

### External Service Integration
- **AI Service Integration**: Modular design for AI provider switching
- **File Processing**: Pluggable document processing services
- **Report Generation**: Template engine for flexible output formats

## Scalability Patterns

### Horizontal Scaling Considerations
- **Stateless API**: Session data externalized for multi-instance deployment
- **Database Scaling**: ORM abstraction allows database switching
- **File Storage**: Preparation for cloud storage integration
- **Caching Strategy**: Redis integration points identified

### Monitoring and Observability
- **Health Checks**: Basic health endpoint implemented
- **Logging Strategy**: Structured logging preparation
- **Error Tracking**: Error aggregation and monitoring hooks
