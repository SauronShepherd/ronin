provider "aws" {
  region                      = "us-east-1"
  access_key                  = "cloud-studio"
  secret_key                  = "cloud-studio"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true
  endpoints {
    s3 = "http://127.0.0.1:4566"
    lambda = "http://127.0.0.1:4566"
    sqs = "http://127.0.0.1:4566"
    dynamodb = "http://127.0.0.1:4566"
  }
}

resource "aws_s3_bucket" "api_smoke" {
  bucket = "api_smoke"
  force_destroy = true
}
