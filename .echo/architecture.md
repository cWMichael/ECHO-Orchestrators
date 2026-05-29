# ECHO CONTEXT LAYER: ARCHITECTURE
LAYER_ID: architecture
APPLIES_TO: backend_task, frontend_task, ai_task

- Prefer modular architecture
- Avoid monolithic files and systems
- Separate UI, logic and orchestration layers
- Keep systems isolated where possible
- Prevent hidden dependencies
- Prefer readable structures over clever abstractions
- Use predictable naming conventions
- Design systems for future replacement and scaling
- Maintain clean project structures
- Keep functions focused and readable
- Respect existing project structures
- Avoid unnecessary complexity
- Use structured logging
- Handle failures explicitly
- Never silently ignore errors
- Avoid unnecessary dependencies

PROJECT_STRUCTURE:
/backend
/frontend
/workers
/connectors
/knowledge
/logs
/docs
/scripts
/config
