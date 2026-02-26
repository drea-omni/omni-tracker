## 🔄 Omni Scraper Update Report
*2026-02-26T06:53:58Z*

### 📋 New Changelog Entries (36)
- `2026-02-20` Added Databricks Private Link support for both Azure and AWS infrastructure. You can now create private connections to Databricks workspaces using native Private Endpoints on Azure and VPC Interface Endpoints on AWS. See the PrivateLink documentation for setup details.
- `2026-02-20` Added an organization-wide MCP server setting to Settings > AI settings that controls whether users can authorize external AI tools to connect via OAuth. When disabled, new OAuth approval requests are rejected and existing MCP grants are blocked from making tool calls. This setting defaults to enabled.
- `2026-02-19` Added YAML views and copy buttons to the workbook inspector , making it easy to view and copy query and visualization configuration in the sample query YAML format. You can now toggle between JSON and YAML views in the Query structure and Visualization config sections, and use the Copy query and visualization YAML button in the inspector header to copy both configurations at once in the format needed for topic files in the model IDE.
- `2026-02-19` Added a Funnel visualization type, which you can now use to visualize data flowing through sequential steps. See the visualization documentation for details on configuration and use cases.
- `2026-02-19` Added the ability to select built-in color palettes (such as "Omni Blues", "Omni Threes", and "Omni") as default palettes in the dashboard theme editor, in addition to custom palettes. Learn more about theming in the documentation .
- `2026-02-18` Added a new GET /api/v1/uploads endpoint that allows you to list uploaded CSVs (data input tables). You can filter by upload type, connection, model, or file name, and the endpoint supports cursor-based pagination. See the API documentation for details.
- `2026-02-18` Added the ability for Blobby to search the official Omni docs. This new tool is available in the Query Helper, AI Assistant , and Dashboard Assistant.
- `2026-02-17` Added Australian Dollar (AUD) currency formatting options to the dimension and measure format parameter, allowing you to display numbers with the A$ symbol in standard, accounting, and financial formats.
- `2026-02-17` Added url fields to document, query, and folder API responses, giving you direct links to any piece of content in the Omni UI.
- `2025-12-04` Added an endpoint for removing a document from a user's favorites . If using an organization-scoped API key, requests can be made on behalf of a specific by including the userId query parameter ( DELETE /api/v1/documents/{documentId}/favorite?userId={membershipId} ).
- `2025-12-04` Added an endpoint for renaming documents . If the optional request body clearExistingDraft parameter is true , any existing draft will also be cleared.
- `2025-12-03` Added an endpoint for adding a document to a user's favorites . If using an organization-scoped API key, requests can be made on behalf of a specific by including the userId query parameter ( PUT /api/v1/documents/{documentId}/favorite?userId={membershipId} ).
- `2025-12-03` Renamed the group_by parameter to level_of_detail .
- `2025-12-02` Added support for a few Snowflake and Databricks AI functions, which can be used in Omni as table calculations: AI_SUMMARIZE(text) - Summarize text content AI_COMPLETE(prompt) - Generate text completions (model selected automatically) AI_EXTRACT(text, labels) - Extract structured data from text AI_CLASSIFY(text, categories) - Classify text into categories AI_SENTIMENT(text) - Analyze sentiment of text Note: These functions will only display as suggestions when workbooks are based on Snowflake or Databricks databases.
- `2025-12-02` AI_SUMMARIZE(text) - Summarize text content
- `2025-12-02` AI_COMPLETE(prompt) - Generate text completions (model selected automatically)
- `2025-12-02` AI_EXTRACT(text, labels) - Extract structured data from text
- `2025-12-02` AI_CLASSIFY(text, categories) - Classify text into categories
- `2025-12-02` AI_SENTIMENT(text) - Analyze sentiment of text
- `2025-11-17` Added scope prefix labels (e.g., "My Documents", "Shared with me") to document titles in folder breadcrumbs, improving navigation clarity by showing users the ownership context of documents. The changes support both personal and shared scope documents.
_...and 16 more_

### 🎬 Demos — No new weeks

### 📊 Totals
- Changelog entries: 676
- Demo weeks indexed: 108
- YouTube videos indexed: 460