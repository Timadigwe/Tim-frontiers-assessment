output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "app_runner_service_url" {
  value = length(aws_apprunner_service.api) > 0 ? "https://${aws_apprunner_service.api[0].service_url}" : ""
}

output "app_runner_service_arn" {
  value = length(aws_apprunner_service.api) > 0 ? aws_apprunner_service.api[0].arn : ""
}

output "s3_frontend_bucket" {
  value = aws_s3_bucket.frontend.id
}

output "s3_frontend_website_url" {
  value = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}
