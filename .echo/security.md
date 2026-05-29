# ECHO CONTEXT LAYER: SECURITY
LAYER_ID: security
APPLIES_TO: all, connector_task, ai_task

- Never expose credentials or API keys
- Never log secrets
- Use environment variables for sensitive data
- Validate all external input
- Restrict dangerous filesystem operations
- Never execute untrusted code automatically
- No autonomous destructive actions
- Require confirmation before irreversible operations
- Prefer local processing for sensitive information
- Human approval required for critical operations
- AI must remain assistive, not autonomous
- Never leak confidential information into public systems
- Separate experimental and production environments
