# Attenly - AI-Powered Document Processing Platform

Attenly is a production-ready AI-powered document processing platform that transforms unstructured PDFs into structured, professional reports. Built specifically for insurance professionals, underwriters, and brokers who need to quickly extract and organize key information from complex documents.

## 🚀 Features

- **Advanced AI Processing**: Gemini 2.5 Flash-Lite integration with cost-optimized batch processing
- **Professional Report Generation**: Business-ready PDFs with ReportLab formatting
- **Quote Attribution**: Click quotes to view source documents with precise highlighting
- **Historical Reports**: Complete report storage and retrieval with Supabase
- **Advanced Security**: JWT authentication, rate limiting, and comprehensive security headers
- **Real-time Processing**: Live feedback during document processing
- **User Isolation**: Complete data separation with Row Level Security policies

## 🏗️ Architecture

- **Frontend**: React 19 + TypeScript + Vite
- **Backend**: FastAPI + Python with comprehensive middleware stack
- **Database**: Supabase PostgreSQL with RLS policies
- **AI Processing**: Gemini 2.5 Flash-Lite + ChromaDB vector store
- **Authentication**: Supabase JWT with secure session management
- **File Storage**: Supabase Storage with signed URLs
- **Rate Limiting**: Redis-based token bucket + SlowAPI

## 🔒 Security Features

### Production Security Stack
- **JWT Authentication**: Supabase-based with proper token validation
- **Row Level Security**: Database-level user isolation
- **Rate Limiting**: Both IP-based and user-based quota management
- **Security Headers**: CSP, HSTS, X-Frame-Options, and more
- **Input Validation**: Comprehensive validation on both client and server
- **Error Handling**: Security-aware error messages without information leakage
- **Correlation IDs**: Request tracing for security monitoring
- **Idempotency Keys**: Prevent duplicate operations

### Security Monitoring
- **Health Checks**: `/health`, `/ready`, `/metrics` endpoints
- **Audit Logging**: Security events and data access tracking
- **Structured Logging**: JSON logs with correlation IDs and security context

## 🛠️ Development Setup

### Prerequisites
- Python 3.9+
- Node.js 18+
- Redis (for rate limiting)
- Supabase account

### Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv attenly-backend
source attenly-backend/bin/activate  # On Windows: attenly-backend\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp ../.env.example .env
# Edit .env with your actual API keys and configuration

# Run development server
python -m app.main
```

### Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Configure environment variables
cp .env.example .env.local
# Edit .env.local with your configuration

# Run development server
npm run dev
```

### Database Setup
```bash
# Apply Supabase migrations
supabase migration up

# Or manually apply the SQL files:
# - supabase/migrations/001_user_quotas.sql
# - supabase/migrations/002_rls_policies.sql
```

## 🚀 Production Deployment

### Environment Configuration

#### Backend Environment Variables
```bash
# Required Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_service_role_key
GEMINI_API_KEY=your_gemini_api_key

# Production Settings
ENV=production
PORT=8000
CORS_ORIGINS=https://app.attently.ca
REDIS_URL=redis://your-redis-instance

# Optional Tuning
LLM_MAX_CONTEXT_TOKENS_PER_QUESTION=8000
VECTOR_SEARCH_TOP_K_PER_QUESTION=10
MAX_FILE_SIZE_MB=50
```

#### Frontend Environment Variables
```bash
VITE_API_BASE_URL=https://api.attently.ca
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

### Deployment Checklist

#### Pre-Deployment Security
- [ ] **Rotate API Keys**: Generate new production API keys
- [ ] **Environment Variables**: Ensure all secrets are in secure environment variables
- [ ] **Database Migrations**: Apply all SQL migrations to production database
- [ ] **SSL Certificates**: Ensure HTTPS is properly configured
- [ ] **Domain Configuration**: Update CORS origins and CSP policies

#### Infrastructure Requirements
- [ ] **Application Server**: Docker container or cloud hosting (Koyeb, Railway, etc.)
- [ ] **Redis Instance**: For rate limiting and caching
- [ ] **CDN**: CloudFlare or similar for static asset delivery
- [ ] **Monitoring**: Application monitoring (DataDog, New Relic, etc.)
- [ ] **Error Tracking**: Error aggregation service (Sentry, etc.)

#### Security Hardening
- [ ] **Rate Limiting**: Configure appropriate rate limits for production load
- [ ] **User Quotas**: Set up proper user quotas and billing integration
- [ ] **Monitoring**: Implement security monitoring and alerting
- [ ] **Backup Strategy**: Automated backups for database and file storage
- [ ] **Incident Response**: Prepare incident response procedures

### Docker Deployment

#### Backend Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "-m", "app.main"]
```

#### Frontend Dockerfile
```dockerfile
FROM node:18-alpine as build

WORKDIR /app
COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Cloud Deployment Examples

#### Koyeb (Recommended)
```yaml
# koyeb.yaml
services:
- name: attenly-backend
  git:
    url: https://github.com/your-username/attenly
    branch: main
    build_command: pip install -r backend/requirements.txt
    run_command: cd backend && python -m app.main
  instance_type: nano
  env:
    - key: ENV
      value: production
    - key: SUPABASE_URL
      value: your_supabase_url
    # Add other environment variables from secrets

- name: attently-frontend
  git:
    url: https://github.com/your-username/attenly
    branch: main
    build_command: cd frontend && npm install && npm run build
  instance_type: nano
  static: true
  static_path: frontend/dist
```

### Monitoring and Maintenance

#### Health Monitoring
- **Health Checks**: `/health` (basic), `/ready` (comprehensive)
- **Metrics**: `/metrics` (Prometheus format)
- **Log Aggregation**: Structured JSON logs with correlation IDs

#### Performance Monitoring
- **Response Times**: Track API response times and database query performance
- **Error Rates**: Monitor 4xx/5xx error rates and security violations  
- **Resource Usage**: Monitor CPU, memory, and Redis usage
- **Cost Tracking**: Monitor LLM API usage and processing costs

#### Security Monitoring
- **Authentication Events**: Failed login attempts and suspicious activity
- **Rate Limiting**: Track rate limit violations and potential abuse
- **Data Access**: Monitor data access patterns and unauthorized attempts
- **Error Patterns**: Watch for security-related errors and attack patterns

## 📊 Performance Optimization

### Current Performance
- **Processing Speed**: < 2 minutes for typical insurance documents
- **Page Load Time**: < 3 seconds for report viewing
- **PDF Generation**: Instant downloads using cached data
- **Cost Efficiency**: 50% LLM cost reduction through optimization

### Optimization Features
- **Batch Processing**: Single LLM API calls for multiple questions
- **Report Caching**: In-memory caching eliminates redundant processing
- **Vector Search**: Question-specific search reduces context noise
- **Connection Pooling**: Efficient database connection management

## 🤝 Contributing

### Development Guidelines
- **Security First**: All changes must maintain security standards
- **Testing**: Include tests for new features and security measures
- **Documentation**: Update documentation for any configuration changes
- **Code Quality**: Follow TypeScript strict mode and Python type hints

### Security Reporting
Please report security vulnerabilities to security@attently.ca following our [Security Policy](SECURITY.md).

## 📄 License

This project is proprietary software. All rights reserved.

## 🆘 Support

- **Documentation**: See `/docs` folder for detailed API documentation
- **Issues**: Create GitHub issues for bug reports and feature requests
- **Security**: Report security issues to security@attently.ca
- **General**: Contact support@attently.ca for general inquiries

---

*Last updated: October 2025*
