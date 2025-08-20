# Technical Context: Attenly

## Technology Stack

### Backend Technologies
- **Framework**: FastAPI (Python web framework)
- **Database**: SQLite (development) / PostgreSQL (production ready)
- **ORM**: SQLAlchemy with declarative base
- **Authentication**: Session-based with bcrypt password hashing
- **Security**: itsdangerous for session management
- **File Processing**: Custom PDF parsing service
- **Server**: Uvicorn ASGI server

### Frontend Technologies
- **Framework**: React 19.1.1
- **Language**: TypeScript 5.8.3
- **Build Tool**: Vite 5.0.12
- **Routing**: React Router DOM 7.8.0
- **Styling**: CSS with component-scoped styles
- **Development**: ESLint for code quality

### Development Tools
- **Package Management**: npm (frontend), pip (backend)
- **Code Quality**: ESLint with React hooks plugin
- **Type Checking**: TypeScript with strict configuration
- **Build System**: Vite with React plugin
- **Version Control**: Git with GitHub integration

## Development Environment Setup

### Backend Setup
```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Run development server
python -m app.main
# or
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend Setup
```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

### Database Configuration
- **Development**: SQLite database (`backend/app.db`)
- **Auto-migration**: Tables created automatically on startup (dev mode)
- **Connection**: SQLAlchemy engine with local file database

## Project Structure

### Backend Structure
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── db.py                # Database configuration
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── security.py          # Authentication utilities
│   ├── core/
│   │   └── deps.py          # Dependency injection
│   ├── routers/
│   │   ├── auth.py          # Authentication endpoints
│   │   └── agents.py        # Agent management endpoints
│   ├── services/
│   │   └── pdf_parser.py    # Document processing service
│   └── seeds/
│       └── prebuilt_agents.json  # Default agent templates
├── requirements.txt         # Python dependencies
└── app.db                  # SQLite database file
```

### Frontend Structure
```
frontend/
├── src/
│   ├── main.tsx            # Application entry point
│   ├── App.tsx             # Root component
│   ├── components/
│   │   ├── AgentExecution/
│   │   │   └── FileUpload.tsx
│   │   └── dashboard/
│   │       └── PrebuiltAgentCard.tsx
│   ├── pages/
│   │   ├── LandingPage.tsx
│   │   ├── Dashboard.tsx
│   │   └── AgentExecution.tsx
│   ├── libs/
│   │   ├── configs.ts      # Configuration constants
│   │   └── https.ts        # HTTP client utilities
│   └── types/
│       └── index.ts        # TypeScript type definitions
├── public/                 # Static assets
├── package.json           # Node.js dependencies
├── tsconfig.json          # TypeScript configuration
├── vite.config.ts         # Vite build configuration
└── eslint.config.js       # ESLint configuration
```

## Configuration Details

### Backend Configuration
- **CORS Origins**: `http://127.0.0.1:5173`, `http://localhost:5173`
- **Session Secret**: Configurable (currently hardcoded for dev)
- **Database URL**: SQLite file path (configurable for production)
- **Server Host**: 127.0.0.1:8000 (development)

### Frontend Configuration
- **Development Server**: Vite dev server on port 5173
- **API Base URL**: Configured in `libs/configs.ts`
- **Build Target**: Modern browsers with ES modules
- **TypeScript**: Strict mode enabled

### Build Configuration
- **Frontend Build**: `npm run build` → TypeScript compilation + Vite build
- **Backend Deployment**: Direct Python execution or containerization
- **Static Assets**: Vite handles optimization and bundling

## Dependencies Analysis

### Backend Dependencies
```
fastapi          # Web framework
bcrypt==4.0.1    # Password hashing
itsdangerous     # Session token security
sqlalchemy       # ORM (implicit dependency)
uvicorn          # ASGI server (implicit dependency)
```

### Frontend Dependencies
```
react@19.1.1              # UI framework
react-dom@19.1.1          # DOM rendering
react-router-dom@7.8.0    # Client-side routing
typescript@5.8.3          # Type system
vite@5.0.12              # Build tool
@vitejs/plugin-react@4.7.0 # Vite React integration
```

## Development Workflow

### Local Development
1. **Backend**: Run FastAPI server with auto-reload
2. **Frontend**: Run Vite dev server with hot module replacement
3. **Database**: SQLite file automatically created and managed
4. **API Communication**: CORS configured for local development

### Code Quality
- **TypeScript**: Strict type checking on frontend
- **ESLint**: Code linting with React-specific rules
- **File Organization**: Clear separation of concerns
- **Import Structure**: Organized imports with path aliases

## Deployment Considerations

### Production Requirements
- **Database**: PostgreSQL recommended for production
- **Environment Variables**: Externalize configuration
- **Session Security**: Use secure session keys
- **HTTPS**: SSL/TLS termination required
- **File Storage**: Consider cloud storage for uploaded files

### Scalability Preparation
- **Database Connection Pooling**: SQLAlchemy supports connection pools
- **Static Asset CDN**: Vite build outputs can be served from CDN
- **API Rate Limiting**: Consider adding rate limiting middleware
- **Caching**: Redis integration points identified

## Security Configuration

### Current Security Measures
- **Password Hashing**: bcrypt with salt
- **Session Management**: Secure session middleware
- **CORS Policy**: Restricted to development origins
- **Input Validation**: Pydantic schemas for API validation

### Production Security Checklist
- [ ] Environment-based configuration
- [ ] Secure session keys
- [ ] HTTPS enforcement
- [ ] Rate limiting
- [ ] Input sanitization
- [ ] File upload restrictions
- [ ] Database connection security

## Performance Considerations

### Current Optimizations
- **Frontend**: Vite's fast build and HMR
- **Backend**: FastAPI's async capabilities
- **Database**: SQLAlchemy's lazy loading
- **File Processing**: Async file operations

### Future Optimizations
- **Caching**: Redis for session and data caching
- **CDN**: Static asset delivery optimization
- **Database**: Query optimization and indexing
- **File Storage**: Cloud storage with streaming

## Integration Points

### External Service Integration
- **AI Services**: Modular design for AI provider integration
- **File Storage**: Abstracted file handling for cloud migration
- **Email Services**: User verification and notifications
- **Analytics**: Usage tracking and monitoring

### API Design
- **RESTful Endpoints**: Standard HTTP methods
- **JSON Communication**: Consistent data format
- **Error Handling**: Structured error responses
- **Documentation**: FastAPI automatic OpenAPI generation
