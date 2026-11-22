# ats-pulse

Serverless job tracker. Every 3 hours a Lambda polls company job boards (Ashby, later Greenhouse and Lever), keeps the Mexico-based engineering openings it hasn't seen before, stores them in DynamoDB, and emails a digest through SES.

```
EventBridge Scheduler ──► Lambda (Python, stdlib + boto3) ──► DynamoDB (seen jobs, source health)
  every 3 h, Mexico City        │
                                └──► SES (digest / alert to yourself)
```

## Requirements

- Terraform >= 1.10, AWS CLI v2, Python 3.14+ and GNU Make
- AWS credentials for `make plan` and deploys (e.g. `AWS_PROFILE`). Tests need none.

## Structure

```
src/ats_pulse/   Lambda code
iac/env/         Terraform: Lambda, DynamoDB, Scheduler, SES, log group
iac/env/tests/   terraform test (mocked providers, no AWS calls)
```

## Configuration

| Name | Where | Required |
|------|-------|:--------:|
| `TF_VAR_notification_email` | environment variable, or a line in `.env` (gitignored) | yes |
| `AWS_PROFILE` | environment variable or `.env`, if you don't use the default profile | no |

Every other Terraform input has a default in [iac/env/variables.tf](iac/env/variables.tf) (region `us-east-1`, schedule, runtime, log retention, ...). `*.tfvars` files are gitignored; override with `TF_VAR_<name>` if needed.

The notification email is marked sensitive and is never committed, logged, or printed in plans. Terraform state does contain it in plaintext, so never share or commit state files.

## Commands

```bash
make help        # list targets
make fmt         # format Terraform
make validate    # fmt -check + terraform validate
make test-infra  # terraform test with mocked providers
make plan        # terraform plan (needs AWS credentials + TF_VAR_notification_email)
```

## Deploy

Terraform state is local for now (`iac/env/terraform.tfstate`, gitignored).

```bash
terraform -chdir=iac/env apply
```

After the first apply, AWS sends a verification email to the notification address. Click the link, or SES can't send.

## License

MIT
