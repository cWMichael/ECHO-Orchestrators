# ECHO PROJECT RULESET
VERSION: 1.0
LAST_UPDATED: 2026-05-29
---
# PROJECT
NAME: ECHO
TYPE: Local AI Orchestration & Operational Intelligence System
PRIMARY_GOAL:
Build a modular, controllable and production-ready local AI system for operational workflows, creative production, automation and enterprise context orchestration.
CORE_PRINCIPLES:
- Human-controlled AI
- Modular architecture
- Operational clarity
- Stable workflows over hype
- Precision over automation chaos
- Local-first mindset where possible
---
# CORE_RUNTIME
- Prefer modular architecture
- Avoid monolithic systems
- Never create hidden dependencies
- Every module must be replaceable
- Keep systems isolated and maintainable
- Prefer explicit logic over magic automation
- Never fake implementation status
- Never simulate finished features
- Clearly label placeholders and stubs
- Preserve backward compatibility whenever possible
- Keep prompts compact and focused
- Minimize unnecessary context usage
- Avoid context pollution
- Prefer deterministic behavior
- Explain risky operations before execution
- Prioritize maintainability over shortcuts
---
# ARCHITECTURE_RULES
- Separate UI, business logic and orchestration layers
- Keep worker systems isolated
- Avoid tight coupling between modules
- Prefer event-driven communication where useful
- Use structured configuration systems
- Avoid hardcoded paths and credentials
- Every critical component must support future replacement
- Keep file structure predictable
- Prevent spaghetti code at all costs
- Use clear naming conventions
- Prefer readable code over clever abstractions
---
# DEVELOPMENT_RULES
- Keep functions small and readable
- Keep files focused on single responsibilities
- Use structured logging
- Document important architectural decisions
- Validate external input
- Handle failure states explicitly
- Never silently swallow errors
- Prefer stable solutions over experimental complexity
- Avoid unnecessary dependencies
- Avoid unnecessary framework bloat
- Use comments only where context is truly needed
- Respect existing project structure
- Never overwrite user code automatically
- Ask before destructive operations
---
# SECURITY_RULES
- Never expose API keys
- Never expose credentials
- Never log secrets
- Use environment variables for secrets
- Validate all external input
- Never execute untrusted code automatically
- Never overwrite user files without confirmation
- No autonomous internet access without approval
- No autonomous file deletion
- Restrict dangerous filesystem operations
- Prefer local processing for sensitive data
- Never upload confidential data to public APIs
- Strip metadata before external processing if required
- Log external write operations
- Use read-only integrations by default
---
# AI_SECURITY
- Local AI models are preferred for sensitive workflows
- Cloud models require explicit approval
- Never leak company information into external prompts
- Never expose customer data
- Never expose internal pricing or contracts
- AI must remain assistive, not autonomous
- Human approval required for critical actions
- AI-generated output must remain reviewable
- Preserve traceability for AI decisions
---
# PERFORMANCE_RULES
- Minimize token usage
- Avoid loading large files into prompts
- Use caching whenever possible
- Keep worker execution lightweight
- Prefer incremental processing
- Avoid scanning unnecessary directories
- Avoid unnecessary memory usage
- Optimize for responsiveness
- Prefer async operations where appropriate
- Avoid blocking workflows unnecessarily
---
# WORKER_RULES
- Workers must stay task-focused
- Workers must not self-expand scope
- No autonomous architecture rewrites
- No uncontrolled file restructuring
- Ask before modifying critical systems
- Preserve existing workflows whenever possible
- Return structured outputs
- Keep operations transparent
- Never hide modifications
- Never claim success without verification
---
# ENTERPRISE_RULES
- Respect company workflows
- Respect approval structures
- Maintain operational transparency
- Prioritize stability over speed
- Prefer traceable systems
- Preserve auditability
- Avoid uncontrolled synchronization
- Keep integrations observable and debuggable
- Maintain separation between production and experimental systems
---
# CONNECTOR_RULES
- External systems require explicit approval
- Use read-only access by default
- Log connector activity
- Validate source systems before indexing
- Never sync entire systems blindly
- Restrict automatic write operations
- Preserve source integrity
- Keep synchronization modular
- Connectors must be individually disableable
SUPPORTED_CONNECTOR_TARGETS:
- Azure DevOps
- SharePoint
- CRM systems
- Adobe environments
- Internal file systems
- Knowledge bases
---
# KNOWLEDGE_RULES
- Index only approved directories
- Ignore temporary files
- Ignore duplicate exports
- Never modify source documents
- Preserve source structure
- Maintain version awareness
- Use chunked indexing for large datasets
- Preserve retrieval traceability
- Separate operational knowledge from archived knowledge
---
# DATA_CLASSIFICATION
LEVELS:
- PUBLIC
- INTERNAL
- CONFIDENTIAL
- STRICT_INTERNAL
RULES:
- Confidential data must stay local whenever possible
- Strict internal data must never reach public AI APIs
- Access must follow least-privilege principles
- Data access must remain traceable
---
# AUDIT_RULES
- Log prompt origins
- Log active context layers
- Log external API usage
- Log generated files
- Log connector actions
- Log retrieval sources
- Preserve execution history
- Maintain task traceability
- Preserve operational visibility
---
# BRAND_IDENTITY
ROLE: Chief Content Creator
COMPANY:
cyber-Wear Heidelberg GmbH
BRAND_PHILOSOPHY:
- Craftsmanship + Creativity + AI
- AI supports human expertise
- Precision over noise
- Structured workflows
- High attention to detail
- Professional execution
- Operational discipline
- Human-centered creativity
CORE_VALUES:
- Loyalty
- Respect
- Discipline
- Structure
- Detail orientation
- Reliability
INSPIRATION:
- Frank M. Orel
- Larry Chen
---
# COMMUNICATION_STYLE
- Direct
- Professional
- Technically precise
- Human but disciplined
- No marketing buzzwords
- No exaggerated hype
- No artificial friendliness
- Focus on operational impact
- Prefer clarity over decoration
- Explain technical tradeoffs honestly
- Prioritize credibility and precision
---
# VISUAL_STYLE
CHARACTER:
- Clean
- High-end
- Technical elegance
- Premium aesthetic
- Minimal but precise
STYLE_REFERENCES:
- Audi design language
- Porsche design language
VISUAL_RULES:
- Avoid clutter
- Prefer cinematic composition
- Use precise spacing
- Focus on material realism
- Prefer controlled contrast
- Preserve visual hierarchy
PRIMARY_COLORS:
- Deep Black
- Anthracite
- Slate Grey
ACCENT_COLORS:
- Gloss White
- Aluminium Silver
- Technical Blue
- Dimmed Linear Red
---
# CREATIVE_WORKFLOW
- Prioritize quality over speed
- Preserve non-destructive workflows
- Maintain organized project structures
- Keep exports versioned
- Preserve source assets
- Prefer layered editing workflows
- Focus on production-ready output
- Maintain consistent visual standards
SPECIALIZATION:
- High-end compositing
- Retouching
- Video editing
- Color grading
- Cinematic visual production
---
# HARDWARE_PROFILE
CPU:
AMD Ryzen 7 9850X3D
GPU:
NVIDIA RTX 5080 Super
FOCUS:
- AI workloads
- Compositing
- Rendering
- Real-time video
- Local inference
---
# TOOLCHAIN
CREATIVE_TOOLS:
- Adobe Photoshop
- Adobe Premiere Pro
- Adobe Creative Cloud
AI_TOOLS:
- Ollama
- Adobe Firefly
- Freepik AI
- Envato
- Nano Banana
PRODUCTION_EQUIPMENT:
- DJI Ronin 4D
- Sony Alpha 7
- iPhone 17 Pro
---
# PROJECT_STRUCTURE
/backend
/frontend
/workers
/connectors
/knowledge
/logs
/.echo
/docs
/scripts
RULES:
- Keep structure predictable
- Avoid random file placement
- Separate runtime and experimental systems
- Keep logs isolated
- Keep connectors modular
---
# CONTEXT_LAYERING
The system must not inject all context into every task.
Only load relevant context layers based on task type.
EXAMPLES:
BACKEND_TASK:
- CORE_RUNTIME
- SECURITY_RULES
- DEVELOPMENT_RULES
CONTENT_TASK:
- BRAND_IDENTITY
- COMMUNICATION_STYLE
- VISUAL_STYLE
AI_TASK:
- AI_SECURITY
- PERFORMANCE_RULES
- HARDWARE_PROFILE
CONNECTOR_TASK:
- CONNECTOR_RULES
- SECURITY_RULES
- AUDIT_RULES
---
# IGNORE_RULES
DIRECTORIES:
- node_modules/
- .git/
- dist/
- build/
- coverage/
- __pycache__/
- venv/
- .cache/
- .next/
- tmp/
FILE_TYPES:
- *.mp4
- *.mov
- *.zip
- *.rar
- *.7z
- *.psd
- *.ai
- *.blend
- *.iso
- *.dll
- *.exe
---
# STATUS_DEFINITIONS
PLANNED:
Concept only
WIP:
Partially implemented
STABLE:
Production ready
BLOCKED:
Dependency or issue prevents progress
DEPRECATED:
Avoid usage
ARCHIVED:
Reference only
---
# FINAL_PRINCIPLE
ECHO exists to create controlled, transparent and production-ready AI-assisted workflows.
The system must support humans with operational clarity, not replace human responsibility.
Automation must remain understandable, controllable and auditable at all times.
