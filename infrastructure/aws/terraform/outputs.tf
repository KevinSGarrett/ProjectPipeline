output "cloud_spine_enabled" { value = var.enable_cloud_spine }
output "director_witness_table" { value = var.enable_cloud_spine ? aws_dynamodb_table.director_witness[0].name : null }
output "durable_event_queue_url" { value = var.enable_cloud_spine ? aws_sqs_queue.durable_events[0].url : null }
output "recovery_bucket" { value = var.enable_cloud_spine ? aws_s3_bucket.recovery[0].id : null }
