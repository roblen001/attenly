# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in Attenly, please report it responsibly:

### How to Report
- **Email**: Send details to security@attently.ca
- **Subject Line**: "Security Vulnerability Report - [Brief Description]"
- **Include**: 
  - Detailed description of the vulnerability
  - Steps to reproduce the issue
  - Potential impact assessment
  - Any suggested fixes (optional)

### What to Expect
- **Initial Response**: Within 24 hours of report
- **Status Update**: Within 72 hours with preliminary assessment  
- **Resolution Timeline**: Critical issues resolved within 7 days
- **Credit**: Security researchers will be credited (unless anonymity requested)

### Please Do Not
- Publicly disclose the vulnerability before we've addressed it
- Access or modify user data without explicit permission
- Perform testing that could disrupt our services
- Use social engineering against our team members

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Security Best Practices

### For Developers
- **Never commit secrets**: Use environment variables and `.env.example`
- **API Key Rotation**: Rotate all API keys if compromised
- **Input Validation**: Validate all user inputs on both client and server
- **Dependencies**: Keep all dependencies updated to latest secure versions
- **Authentication**: Use proper JWT validation for all protected routes
- **HTTPS Only**: All production traffic must use HTTPS
- **CORS Policy**: Restrict origins to known domains only

### For Users
- **Strong Passwords**: Use unique, strong passwords for your account
- **Document Security**: Be mindful of sensitive information in uploaded documents
- **Network Security**: Use secure networks when accessing the application
- **Regular Reviews**: Monitor your account for any unauthorized activity

## Security Architecture

### Authentication & Authorization
- JWT-based authentication via Supabase in the current default profile
- Row Level Security (RLS) policies for data isolation in the default profile
- User-specific vector store collections
- Server-side session validation
- Provider-neutral authentication is planned for future open-source profiles

### Data Protection
- Encryption at rest depends on the configured storage/database provider
- TLS encryption for all API communications
- User data isolation at database and vector store levels
- Automatic data cleanup and session management

### Infrastructure Security
- **Security Headers**: Comprehensive Content Security Policy (CSP), HSTS, X-Frame-Options
- **Request Size Limiting**: Application-level middleware with 50MB limits and intelligent filtering
- **Rate Limiting**: Per-IP protections use SlowAPI; Redis is not required by the current runtime
- **Input Validation**: Multi-layer validation at request, file, and content levels
- **File Security**: MIME validation, extension checks, content-based detection, malware scanning hooks
- **CORS Policy**: Strict enforcement limited to trusted domains only

### Container Security
- **Multi-stage Docker Build**: Optimized production images with security scanning
- **Non-root Execution**: Application runs as dedicated `appuser` with minimal privileges
- **Image Hardening**: Minimal base images with only required dependencies
- **Secret Management**: No secrets in container images, environment-based configuration only
- **Supply Chain Security**: All dependencies pinned to exact versions (==) for reproducible builds
- **Build Optimization**: Comprehensive `.dockerignore` preventing sensitive files in images

### AI/ML Security
- Prompt injection prevention
- Input validation before LLM processing
- Cost protection mechanisms
- User quota enforcement
- Vector store isolation per user

## Incident Response

In the event of a security incident:
1. **Immediate Response**: Contain and assess the incident
2. **User Notification**: Notify affected users within 24 hours
3. **Remediation**: Deploy fixes and security updates
4. **Documentation**: Document incident and lessons learned
5. **Prevention**: Update security measures to prevent recurrence

## Compliance

Attenly implements security measures consistent with:
- **OWASP Top 10** security guidelines
- **GDPR** privacy requirements
- **SOC 2 Type II** security standards (planned)
- Industry best practices for AI/ML security

## Contact

For general security questions: security@attently.ca
For vulnerability reports: security@attently.ca
For privacy concerns: privacy@attently.ca

---

*This security policy is reviewed and updated regularly. Last updated: October 2025*
