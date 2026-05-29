# ECHO CONTEXT LAYER: CONNECTORS
LAYER_ID: connectors
APPLIES_TO: connector_task

- External integrations require explicit approval
- Use read-only access by default
- Log all connector activity
- Validate sources before indexing or synchronization
- Avoid uncontrolled synchronization
- Restrict automatic write access
- Preserve source-system integrity
- Keep integrations modular and individually disableable

SUPPORTED_TARGETS:
- Azure DevOps
- SharePoint
- CRM systems
- Adobe environments
- Internal file systems
- Knowledge bases

DATA_CLASSIFICATION:
- PUBLIC: no restrictions
- INTERNAL: local processing preferred
- CONFIDENTIAL: must stay local, no external APIs
- RESTRICTED: never leave local environment
