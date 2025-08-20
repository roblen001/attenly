# Attenly Memory Bank

This Memory Bank serves as the comprehensive knowledge base for the Attenly project. It contains all essential information needed to understand, develop, and maintain the project across development sessions.

## File Structure

### Core Files (Required)
1. **`projectbrief.md`** - Foundation document defining project mission, goals, and scope
2. **`productContext.md`** - Product vision, user experience goals, and business context
3. **`systemPatterns.md`** - Architecture, design patterns, and technical implementation details
4. **`techContext.md`** - Technology stack, development setup, and configuration
5. **`activeContext.md`** - Current work focus, recent changes, and active development areas
6. **`progress.md`** - Current status, completed features, remaining work, and milestones

## How to Use This Memory Bank

### For New Development Sessions
1. **Always read ALL memory bank files** at the start of any development work
2. Start with `projectbrief.md` to understand the core mission
3. Review `activeContext.md` to understand current priorities
4. Check `progress.md` to see what's completed and what needs work

### For Updates
- Update `activeContext.md` when changing focus areas or making architectural decisions
- Update `progress.md` when completing features or identifying new requirements
- Update other files when fundamental aspects of the project change

### File Dependencies
```
projectbrief.md (foundation)
├── productContext.md (why & how)
├── systemPatterns.md (architecture)
└── techContext.md (technology)
    └── activeContext.md (current work)
        └── progress.md (status & next steps)
```

## Key Information Summary

### Project: Attenly
- **Purpose**: AI-powered data extraction from insurance documents
- **Status**: Phase 2 - Core AI processing development
- **Tech Stack**: FastAPI (Python) + React (TypeScript)
- **Priority**: Implement real AI processing pipeline

### Current Focus
- Building AI processing pipeline to replace mock functionality
- Connecting PDF parsing to data extraction
- Implementing template population with extracted data
- Creating report generation system

### Next Steps
1. Choose and integrate AI/ML service
2. Implement file upload backend
3. Build template substitution engine
4. Create PDF report generation

## Maintenance Notes

- This Memory Bank is critical for project continuity
- All files should be kept up-to-date with project evolution
- When in doubt, read the entire Memory Bank to get full context
- Document all architectural decisions and learnings in appropriate files

---

*Last Updated: August 18, 2025*
*Memory Bank Version: 1.0*
