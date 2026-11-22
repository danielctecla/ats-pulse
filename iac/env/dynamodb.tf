# One table for two item types, both keyed by pk:
#   job#<source>#<job_id>  seen jobs (job_id, source, company, title, location,
#                          department, url, published_at, first_seen_at)
#   health#<company>       source health (consecutive_failures, last_error,
#                          last_success_at)
resource "aws_dynamodb_table" "this" {
  name         = var.project_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }
}
