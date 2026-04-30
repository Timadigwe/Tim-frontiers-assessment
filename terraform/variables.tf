variable "project_name" {
  type    = string
  default = "tim-frontiers"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "aws_region" {
  type    = string
  default = "us-west-2"
}

variable "create_app_runner" {
  type    = bool
  default = false
}

variable "app_runner_auto_deploy" {
  type    = bool
  default = false
}

variable "openrouter_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "openrouter_model" {
  type    = string
  default = "openai/gpt-4o-mini"
}

variable "openai_api_key" {
  type        = string
  sensitive   = true
  description = "Optional OpenAI API key for Agents SDK trace export (Traces dashboard). LLM still uses OpenRouter."
  default     = ""
}

variable "mcp_server_url" {
  type        = string
  sensitive   = true
  description = "MCP server URL (streamable HTTP; usually ends with /mcp). Override in CI via MCP_SERVER_URL secret."
  default     = "https://order-mcp-74afyau24q-uc.a.run.app/mcp"
}
