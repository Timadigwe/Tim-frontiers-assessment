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
  default = "openai/gpt-4o"
}
