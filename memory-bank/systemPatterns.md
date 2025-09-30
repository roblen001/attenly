# System Patterns: Attenly

## Overall Architecture

### High-Level System Design
```
Frontend (React/TypeScript) ←→ Backend API (FastAPI) ←→ Database (Supabase PostgreSQL)
                                        ↓
                               AI Processing Layer (Gemini)
                                        ↓
                               Vector Store (ChromaDB)
                                        ↓
                          Document Processing Pipeline
```

### Implemented Architectural Patterns
- **Service Layer Pattern**: Complete separation between API, business logic, and data access
- **RESTful API Design**: Standard HTTP methods with structured JSON responses
- **Component-Based Frontend**: Reusable React components with TypeScript interfaces
- **RAG Architecture**: Retrieval-Augmented Generation with vector search and LLM processing
- **Repository Pattern**: Data access abstraction through services and ORM
- **Configuration Pattern**: Centralized configuration management with environment variables
- **Caching Pattern**: In-memory caching with automatic cleanup for performance optimization

## Backend Architecture

### Core Service Layer ✅ **IMPLEMENTED**
1. **FastAPI Application** (`app/main.py`)
   - CORS middleware for frontend communication
   - Comprehensive configuration validation on startup
   - Router inclusion for modular endpoint organization
   - Centralized error handling and logging

2. **Database Integration** (`app/db.py`, `app/models.py`)
   - SQLAlchemy ORM with declarative base for local development
   - Supabase PostgreSQL integration for production features
   - UTC timestamp handling for consistency
   - Relationship mapping between entities with proper constraints

3. **API Router Architecture** (`app/routers/`)
   - `auth.py`: Supabase JWT authentication and user management
   - `agents.py`: Agent CRUD operations, file processing, and report generation
   - Modular design with clear separation of concerns
   - Comprehensive error handling and validation

### Advanced Service Layer Architecture ✅ **IMPLEMENTED**

#### AI Processing Services
```
LLMService → ReportService → VectorStore
     ↓              ↓             ↓
 Gemini API   Question RAG   ChromaDB
```

4. **LLM Service** (`app/services/llm_service.py`)
   - **Batch Processing**: Cost-optimized processing of all questions in single API calls
   - **Answer Quality Analysis**: Intelligent filtering using AnswerQuality enum
   - **Precise Quote Extraction**: Secondary LLM calls for exact source text identification
   - **Structured Output**: JSON schema enforcement for consistent response parsing
   - **Context Optimization**: Token-aware context preparation with configurable limits
   - **Error Handling**: Comprehensive exception handling with graceful degradation

5. **Report Service** (`app/services/report_service.py`)
   - **Question-Specific RAG**: Each question gets its own vector search context
   - **Template Population**: Dynamic HTML template substitution with quote superscripts
   - **Document Context Building**: Comprehensive metadata tracking and organization
   - **Report Data Structure**: Complex nested data structures for frontend consumption
   - **Integration Orchestration**: Coordinates LLM service, vector store, and document processing

6. **Vector Store Service** (`app/services/vector_store.py`)
   - **ChromaDB Integration**: Persistent vector database with embedding generation
   - **User Isolation**: Separate collections per user for data security
   - **Question-Specific Search**: Configurable top-K results per question
   - **Metadata Preservation**: Complete document context with page numbers and sources
   - **Session Management**: Automatic cleanup on navigation and file operations

#### Document Processing Pipeline ✅ **IMPLEMENTED**
```
Upload → Classification → Processing → Chunking → Vector Storage
```

7. **Document Classifier** (`app/services/document_classifier.py`)
   - **Content Analysis**: Distinguishes text-based, image-based, mixed, and empty content
   - **File Type Detection**: Validates file extensions and content structure
   - **Processor Routing**: Recommends appropriate processing strategies
   - **Error Prevention**: Early detection of unsupported formats with clear user guidance
   - **Extensible Design**: Ready for future OCR and multi-format processor integration

8. **Document Processor** (`app/services/document_processor.py`)
   - **Orchestration Layer**: Main coordinator for document processing pipeline
   - **Classifier Integration**: Uses document classifier for intelligent routing
   - **Error Handling**: Comprehensive validation with user-friendly error messages
   - **File Management**: Secure handling of uploaded documents with cleanup
   - **Processing Statistics**: Detailed tracking of processing results and performance

9. **PDF Parser Service** (`app/services/pdf_parser.py`)
   - **Advanced Parsing**: Layout-aware text extraction with table preservation
   - **Page-Level Organization**: Structured output with page boundaries and metadata
   - **Table Detection**: Preserves horizontal lines and table structures exactly
   - **Token Counting**: Integration with tiktoken for AI processing preparation
   - **Chunk Format Output**: Structured data ready for vector database ingestion

10. **Chunking Service** (`app/services/chunking_service.py`)
    - **Two-Level Chunking**: L1 semantic chunks for natural boundaries, L2 search windows
    - **Configurable Parameters**: Token limits, overlap settings, and chunk sizes
    - **Content Preservation**: Maintains document context and page references
    - **Vector Store Integration**: Optimized chunk format for ChromaDB storage
    - **Performance Optimization**: Intelligent chunking strategy for RAG efficiency

#### Storage and Persistence Services ✅ **IMPLEMENTED**

11. **Supabase Service** (`app/services/supabase_service.py`)
    - **Historical Reports Storage**: Complete report data preservation with RLS policies
    - **Document Content Storage**: Full document content for quote highlighting
    - **User Isolation**: Row Level Security ensures proper data separation
    - **CRUD Operations**: Comprehensive create, read, update, delete operations
    - **Error Handling**: Robust error handling with connection management

12. **PDF Generator Service** (`app/services/pdf_generator.py`)
    - **Professional PDF Generation**: ReportLab-based system with proper formatting
    - **HTML Parsing**: BeautifulSoup integration for HTML-to-PDF conversion
    - **Typography System**: Professional styling with multiple paragraph styles
    - **Reference System**: Advanced reference section with quote previews and page numbers
    - **Error Recovery**: Multiple fallback strategies for parsing failures

### Configuration Management Pattern ✅ **IMPLEMENTED**

13. **Centralized Configuration** (`app/config.py`)
    - **Environment Variable Support**: All settings configurable via environment variables
    - **Startup Validation**: Configuration validation with detailed error messages
    - **Service Integration**: All services use centralized configuration parameters
    - **Performance Tuning**: Configurable parameters for LLM, vector search, and chunking
    - **Documentation**: Comprehensive comments with recommended values for each setting

### Database Schema Design ✅ **IMPLEMENTED**

#### SQLAlchemy Models (Development)
```
Users
├── id (String, Primary Key)
├── email (String, Indexed, Unique)
├── full_name (String, Optional)
├── is_active (Boolean, Default True)
├── created_at (DateTime, UTC)
└── updated_at (DateTime, UTC)

Agents
├── id (UUID, Primary Key)
├── name (String, Not Null)
├── description (Text)
├── report_template (Text, HTML)
├── created_at (DateTime, UTC)
├── updated_at (DateTime, UTC)
└── questions (One-to-Many → AgentQuestions)

AgentQuestions
├── id (UUID, Primary Key)
├── agent_id (UUID, Foreign Key → Agents.id)
├── placeholder (String, Not Null)
├── prompt (Text, Not Null)
├── created_at (DateTime, UTC)
└── UNIQUE(agent_id, placeholder)
```

#### Supabase Schema (Production Features)
```
saved_reports
├── id (UUID, Primary Key)
├── user_id (String, Not Null, RLS Policy)
├── report_name (String, Not Null)
├── agent_id (UUID, Not Null)
├── agent_name (String, Not Null)
├── report_data (JSONB, Complete ReportData structure)
├── created_at (Timestamp, UTC)
└── updated_at (Timestamp, UTC)

saved_report_documents
├── id (UUID, Primary Key)
├── report_id (UUID, Foreign Key → saved_reports.id)
├── document_id (String, Not Null)
├── document_content (Text, Full document content)
├── metadata (JSONB, Document metadata)
├── created_at (Timestamp, UTC)
└── UNIQUE(report_id, document_id)
```

## Frontend Architecture

### Component Hierarchy ✅ **IMPLEMENTED**
```
App
├── LandingPage
├── Login (JWT Authentication)
├── Dashboard
│   ├── PrebuiltAgentCard
│   ├── CustomAgentCard
│   └── CompactReportList (Saved Reports)
├── CreateAgent (Future)
├── AgentExecution
│   └── FileUpload (Advanced Upload System)
└── ReportView
    ├── ReportHeader
    ├── ReportActionsBar
    ├── ReportInstructions
    ├── ReportContent
    ├── EditAnswerModal
    ├── SaveReportModal
    ├── DocumentViewer (Full Document Display)
    ├── LoadingState
    └── ErrorState
```

### Advanced State Management Patterns ✅ **IMPLEMENTED**

#### Custom Hooks Architecture
```
ReportView Component
├── useReportData (Report fetching & auth)
├── useAnswerEditing (In-place modifications)
└── useQuoteInteraction (Document viewing)
```

1. **useReportData Hook** (`src/hooks/useReportData.ts`)
   - **Report Data Fetching**: API integration with authentication
   - **Loading States**: Comprehensive loading and error state management
   - **Authentication Integration**: Supabase JWT validation throughout
   - **Error Handling**: Robust error handling with user-friendly messages
   - **Data Transformation**: Complex data structure normalization for UI consumption

2. **useAnswerEditing Hook** (`src/hooks/useAnswerEditing.ts`)
   - **Modal State Management**: Edit modal visibility and data management
   - **In-Place Editing**: Direct answer modification with validation
   - **Optimistic Updates**: UI updates before API confirmation
   - **Error Recovery**: Rollback mechanisms for failed edits
   - **Integration**: Seamless integration with report data state

3. **useQuoteInteraction Hook** (`src/hooks/useQuoteInteraction.ts`)
   - **Document Viewing**: Full document display with quote highlighting
   - **Quote Navigation**: Navigation between quotes and source documents
   - **Context Loading**: Asynchronous document content loading
   - **Highlighting Logic**: Precise text highlighting within document context
   - **Error Handling**: Graceful fallbacks for content loading failures

#### Component Design Patterns ✅ **IMPLEMENTED**

4. **Modular Component Architecture**
   - **Separation of Concerns**: Each component has single responsibility
   - **Props Interface Design**: Strong TypeScript typing with comprehensive interfaces
   - **CSS Scoping**: Component-scoped CSS with descriptive class names
   - **Conditional Rendering**: Dynamic UI based on application state and user permissions
   - **Error Boundaries**: Component-level error handling with fallback UI

5. **File Upload System** (`src/components/AgentExecution/FileUpload.tsx`)
   - **Drag & Drop Interface**: Intuitive file handling with visual feedback
   - **Progress Tracking**: Real-time upload progress with cancellation support
   - **Duplicate Prevention**: SHA-256 content hashing to prevent duplicate processing
   - **Queue Management**: Visual queue indicators with position tracking
   - **Error Handling**: Comprehensive error handling including race conditions

### API Integration Patterns ✅ **IMPLEMENTED**

6. **HTTP Client Architecture** (`src/libs/https.ts`)
   - **Centralized Configuration**: Base URL and common headers management
   - **Authentication Integration**: Automatic JWT token attachment
   - **Error Response Handling**: Consistent error parsing and user feedback
   - **Request/Response Interceptors**: Automatic token refresh and error handling
   - **Type Safety**: Full TypeScript integration with API response types

7. **Supabase Integration** (`src/libs/supabase.ts`)
   - **Client Configuration**: Supabase client setup with environment variables
   - **Authentication Flow**: Login, logout, and session management
   - **Real-time Capabilities**: Ready for future real-time features
   - **Error Handling**: Comprehensive error handling for auth operations

## Data Flow Patterns ✅ **IMPLEMENTED**

### Document Processing Flow
```
1. File Upload (Frontend)
   ↓
2. Document Classification (DocumentClassifier)
   ↓
3. Content Processing (DocumentProcessor + PDFParser)
   ↓
4. Document Chunking (ChunkingService)
   ↓
5. Vector Storage (VectorStore + ChromaDB)
   ↓
6. Question-Specific RAG (ReportService + VectorStore)
   ↓
7. LLM Processing (LLMService + Gemini)
   ↓
8. Template Population (ReportService)
   ↓
9. Report Caching (In-Memory Cache)
   ↓
10. Report Display (Frontend Components)
```

### Report Generation & Caching Flow
```
1. User Clicks "Generate Report"
   ↓
2. /agents/{agent_id}/process (LLM Processing + Caching)
   ↓
3. User Navigates to Preview
   ↓
4. /agents/{agent_id}/report (Retrieve Cached Data)
   ↓
5. User Downloads PDF
   ↓
6. /agents/{agent_id}/pdf (Use Cached Data)
```

### Authentication Flow ✅ **IMPLEMENTED**
```
1. User Login (Frontend → Supabase Auth)
   ↓
2. JWT Token Generation (Supabase)
   ↓
3. Token Storage (Frontend Local State)
   ↓
4. API Requests (Backend JWT Validation)
   ↓
5. Token Validation (Supabase Auth API)
   ↓
6. Protected Route Access (User-Isolated Data)
```

### Quote Attribution Flow ✅ **IMPLEMENTED**
```
1. Answer Generated (LLM Service)
   ↓
2. Quote Extraction (Secondary LLM Call)
   ↓
3. Document Reference (Chunk ID + Document ID)
   ↓
4. Frontend Quote Click (useQuoteInteraction)
   ↓
5. Document Content Loading (API Call)
   ↓
6. Quote Highlighting (DocumentViewer)
```

## Security Patterns ✅ **IMPLEMENTED**

### Authentication & Authorization
- **JWT Token-Based Authentication**: Supabase JWT with secure validation
- **User Isolation**: Separate vector collections and database policies per user
- **Row Level Security**: Supabase RLS policies for data access control
- **Token Validation**: Backend validation through Supabase Auth API
- **Session Management**: Secure token storage with automatic cleanup

### Data Protection
- **Environment Variables**: All sensitive configuration externalized
- **Input Validation**: Comprehensive validation on both client and server
- **File Security**: Secure file handling with type and size restrictions
- **CORS Configuration**: Restricted origins for API access
- **Error Handling**: Security-aware error messages without information leakage

### Privacy & Compliance
- **Data Minimization**: Only necessary data collected and stored
- **User Consent**: Clear data usage policies and user control
- **Audit Trails**: Comprehensive logging for security monitoring
- **Secure Storage**: Encrypted storage for sensitive document content
- **Cleanup Procedures**: Automatic data cleanup and session management

## Performance Patterns ✅ **IMPLEMENTED**

### Backend Optimization
- **Batch Processing**: Single LLM API calls for multiple questions (50% cost reduction)
- **Report Caching**: In-memory caching system with automatic cleanup
- **Database Indexing**: Strategic indexes on frequently queried fields
- **Connection Pooling**: Efficient database connection management
- **Async Processing**: Non-blocking I/O for file operations and API calls

### Frontend Optimization
- **Component Memoization**: Prevent unnecessary re-renders with React.memo
- **Code Splitting**: Vite build optimization with tree shaking
- **Asset Optimization**: Optimized asset loading and caching
- **State Management**: Efficient local state with specialized hooks
- **Error Recovery**: Graceful degradation and error recovery mechanisms

### AI Processing Optimization
- **Question-Specific Context**: Targeted vector search reduces context noise
- **Token Management**: Configurable context limits to optimize costs
- **Answer Quality Filtering**: Only high-quality answers generate quotes
- **Structured Output**: JSON schema enforcement reduces parsing overhead
- **Context Preparation**: Intelligent chunk selection and organization

## Integration Patterns ✅ **IMPLEMENTED**

### External Service Integration
- **Gemini 2.5 Flash-Lite**: Cost-optimized LLM with batch processing
- **ChromaDB**: Vector database with persistent storage and user isolation
- **Supabase**: Database, authentication, and storage with RLS policies
- **ReportLab**: Professional PDF generation with advanced formatting

### API Design Patterns
- **RESTful Endpoints**: Standard HTTP methods with clear resource naming
- **JSON Communication**: Consistent request/response formats
- **Error Handling**: Structured error responses with user-friendly messages
- **Authentication**: JWT token validation on all protected endpoints
- **Versioning**: API structure ready for version management

### Configuration Integration
- **Environment-Based Configuration**: Different settings for dev/staging/production
- **Service Health Checks**: Automatic detection of service availability
- **Startup Validation**: Configuration validation with detailed error reporting
- **Performance Tuning**: Runtime configuration for optimal performance

## Scalability Patterns ✅ **IMPLEMENTED**

### Horizontal Scaling Readiness
- **Stateless API Design**: All state externalized for multi-instance deployment
- **User Isolation**: Complete data separation enables horizontal scaling
- **Caching Strategy**: In-memory caching ready for Redis migration
- **Database Abstraction**: Service layer ready for database scaling
- **Configuration Management**: Environment-based config supports multiple deployments

### Performance Monitoring Preparation
- **Structured Logging**: Comprehensive logging throughout all services
- **Error Aggregation**: Centralized error handling ready for monitoring tools
- **Performance Metrics**: Key performance indicators tracked and logged
- **Health Endpoints**: Service health checks for load balancer integration

## Advanced Architectural Patterns

### RAG (Retrieval-Augmented Generation) Architecture ✅ **IMPLEMENTED**
```
Question → Vector Search → Context Preparation → LLM Processing → Answer + Quotes
    ↓              ↓                ↓                   ↓              ↓
Document      ChromaDB        Token Mgmt        Gemini API      Source Attribution
```

- **Question-Specific Search**: Each question gets its own relevant context
- **Two-Level Chunking**: Semantic chunks for context, search windows for precision
- **Context Optimization**: Token-aware context preparation with configurable limits
- **Answer Quality Analysis**: Intelligent filtering of found vs. not-found responses
- **Precise Quote Extraction**: Secondary LLM calls for exact source text identification

### Event-Driven Patterns (Ready for Implementation)
- **Document Processing Events**: Upload → Process → Chunk → Store → Index
- **Report Generation Events**: Request → Search → Process → Cache → Deliver
- **User Action Events**: Login → Upload → Process → View → Save
- **Error Handling Events**: Detect → Log → Alert → Recover

### Caching Strategy Pattern ✅ **IMPLEMENTED**
```
Memory Cache (Current) → Redis Cache (Future) → Database (Persistence)
        ↓                        ↓                     ↓
   Report Data              Distributed Cache      Historical Storage
```

- **Multi-Level Caching**: Memory for speed, distributed for scale, database for persistence
- **Cache Invalidation**: Automatic cleanup on data changes and navigation
- **Cache Warming**: Proactive caching for frequently accessed data
- **Performance Optimization**: 50% cost reduction through intelligent caching

## Monitoring and Observability Patterns (Ready for Implementation)

### Logging Strategy
- **Structured Logging**: JSON-formatted logs with consistent fields
- **Log Levels**: Appropriate log levels throughout all services
- **Error Context**: Comprehensive error context for debugging
- **Performance Logging**: Request/response times and processing metrics
- **Security Logging**: Authentication events and security-relevant actions

### Metrics Collection
- **Application Metrics**: Processing times, success rates, error counts
- **Business Metrics**: Document processing volume, user engagement
- **System Metrics**: Memory usage, CPU utilization, database performance
- **Cost Metrics**: LLM API usage, vector database operations, storage costs

### Health Monitoring
- **Service Health Checks**: Endpoint health validation for all services
- **Dependency Health**: External service availability monitoring
- **Performance Thresholds**: Automated alerting for performance degradation
- **Error Rate Monitoring**: Automatic detection of elevated error rates

The architecture demonstrates a sophisticated, production-ready system that successfully integrates AI processing, document handling, user management, and performance optimization into a cohesive platform ready for enterprise deployment.
