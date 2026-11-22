# ats-pulse

Serverless job tracker. Every 3 hours a Lambda polls company job boards, keeps the Mexico-based engineering openings it hasn't seen before, stores them in DynamoDB, and emails a digest through SES.

```
EventBridge Scheduler ──► Lambda (Python, stdlib + boto3) ──► DynamoDB (seen jobs, source health)
  every 3 h, Mexico City        │
                                ├──► SES: job digest, alert when a source keeps failing
                                └──► CloudWatch alarm ──► SNS: email when the Lambda itself fails
```

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 1 | Infrastructure (Terraform, local state) | done |
| 2 | Fetch, filter, dedupe, source health, crash alarm | done |
| 3 | SES emails: HTML digest and plain alert | pending. Digests and alerts are only logged for now |
| 4 | S3 remote state + GitHub Actions (OIDC) | pending |

## Requirements

- Terraform >= 1.10, AWS CLI v2, Python 3.14+ and GNU Make
- AWS credentials for `make plan` and deploys (e.g. `AWS_PROFILE`). Tests and `make run-local` need none.

## Quick start

```bash
make test        # creates .venv from requirements-dev.txt, runs pytest + moto
make run-local   # polls the real job boards, in-memory DynamoDB, prints what a digest would contain
make test-infra  # terraform test with mocked providers
```

Nothing in these three commands touches AWS.

## Structure

```
src/ats_pulse/              Lambda code (stdlib + boto3, zipped as is)
  sources.toml              job boards to poll
  adapters/                 one module per ATS, normalizes jobs to a common schema
  filters.py                Mexico and engineering rules
  pipeline.py               per source: fetch -> filter -> dedupe; then notify and save
  store.py                  DynamoDB access (jobs and source health)
  notify.py                 digest and alert delivery
  handler.py                Lambda entry point
tests/                      pytest + moto; fixtures/ holds a real Ashby response, trimmed
scripts/run_local.py        backs make run-local
iac/env/                    Terraform: Lambda, DynamoDB, Scheduler, SES, alarm
iac/env/tests/              terraform test (mocked providers, no AWS calls)
```

## How it works

Each run, for every source in [sources.toml](src/ats_pulse/sources.toml):

1. **Fetch** the board through its ATS adapter and normalize the jobs to one schema.
2. **Mexico filter**: the location, a secondary location, the address country or the title mentions Mexico, México, CDMX or Ciudad de México. "New Mexico" (the US state) is excluded.
3. **Engineering filter**: matches if either is true:
   - the department or team contains engineer, machine learning, data, technology, security or infrastructure
   - the title has a role word: engineer, developer, SRE, devops, architect, tech lead, data scientist, machine learning or ML

   Bare "AI", "Data" and "Engineering" in titles are left out on purpose, because on real data they matched legal, design and L&D roles.
4. **Dedupe** against DynamoDB with BatchGetItem.

After all sources:

5. **Alert** if any source just reached 2 consecutive failures.
6. **Digest** of all new jobs (no email when there's nothing new).
7. **Save** the new jobs. This happens only after the digest is sent: if sending fails, the run fails, the crash alarm fires, and the same jobs are retried next run instead of being lost.

Behavior to know about:
- The first run against an empty table reports every current matching opening. Later runs only report new ones.
- When Mexico is only a secondary location, the job's location reads `Ciudad de México (also Palo Alto)`.
- The stored link is the job's posting page, which has the apply button.

### Adding a company

Add one entry to `sources.toml`:

```toml
[[sources]]
company = "Nubank"   # display name, also the health key
ats     = "ashby"    # supported: ashby
slug    = "nubank"   # the company's board name in that ATS
```

To support another ATS (Greenhouse, Lever), add a module in `adapters/` with a `fetch_jobs(source)` function and register it in `adapters/__init__.py`.

## Data model

One DynamoDB table (on-demand), partition key `pk`:

| Item | `pk` | Attributes |
|------|------|------------|
| Job | `job#<ats>:<slug>#<job_id>` | job_id, source, company, title, location, department, url, published_at, first_seen_at |
| Source health | `health#<company>` | consecutive_failures, last_error, last_success_at |

Job descriptions aren't stored: they aren't needed, and DynamoDB items are limited to 400 KB.

## Alerts and monitoring

| Failure | Handled by | You get |
|---------|------------|---------|
| One source fails (HTTP error, timeout, invalid JSON) | Per-source error handling. The other sources still run. | One SES alert when it reaches 2 consecutive failures. Not repeated while it keeps failing; re-armed once it recovers. |
| The whole Lambda fails (timeout, out of memory, import error, unhandled exception, failed digest send) | CloudWatch alarm on the Lambda `Errors` metric | An SNS email for each failed run |

The crash alarm goes through SNS rather than SES, so it still arrives when the Lambda or SES is what's broken.

Each run logs one JSON line per source, plus a run summary:

```json
{"message": "source summary", "source": "ashby:nubank", "company": "Nubank", "fetched": 111, "mexico": 21, "engineering": 7, "new": 7, "errors": 0}
```

`errors` counts malformed postings skipped, plus 1 if the source failed; failed sources also carry an `error` field.

## Configuration

Secrets and local settings (names only; values never go in the repo):

| Name | Where | Required |
|------|-------|:--------:|
| `TF_VAR_notification_email` | environment variable, or a line in `.env` (gitignored, no quotes) | yes |
| `AWS_PROFILE` | environment variable or `.env`, if you don't use the default profile | no |

Terraform inputs ([iac/env/variables.tf](iac/env/variables.tf)). `*.tfvars` files are gitignored, so override with `TF_VAR_<name>`:

| Variable | Default |
|----------|---------|
| `notification_email` | none (required, sensitive) |
| `aws_region` | `us-east-1` |
| `project_name` | `ats-pulse` (prefix for every resource name) |
| `schedule_expression` | `cron(0 0/3 * * ? *)`: every 3 hours on the hour |
| `schedule_timezone` | `America/Mexico_City` |
| `lambda_runtime` | `python3.15` |
| `lambda_memory_mb` | `256` |
| `lambda_timeout_seconds` | `180` |
| `log_retention_days` | `14` |
| `tags` | `{}` (extra tags on top of `Project` and `ManagedBy`) |

`schedule_expression` must stay a `cron()` expression: EventBridge Scheduler ignores the timezone for `rate()`.

## Commands

```bash
make help        # list targets
make test        # pytest + moto
make run-local   # real job-board APIs, in-memory DynamoDB
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

After the first apply AWS sends two emails to the notification address. Click both links:
1. **SES identity verification.** SES can't send until it's confirmed.
2. **SNS subscription confirmation.** Crash alarms aren't delivered until it's confirmed.

The account can stay in the SES sandbox: it only ever emails the verified address.

## Security

- **Least-privilege IAM:**
  - The Lambda can only use GetItem, PutItem, UpdateItem and BatchGetItem on its own table, `ses:SendEmail` from the verified identity, and write to its own log group.
  - The scheduler role can only invoke this function, and only from this account.
- **Notification email:**
  - It's a sensitive Terraform variable with no default, so it shows as `(sensitive value)` in plans.
  - It's never logged or output, and tests use `test@example.com`.
  - It does end up in Terraform state in plaintext, so never share or commit state files.
- **No async retries:** the Lambda has async retries disabled, so a crash can't send the same digest twice. The next scheduled run picks up instead.

## Cost

Effectively zero at this volume:
- SES costs $0.10–0.16 per 1,000 emails.
- The alarm fits within CloudWatch's 10 free alarms.
- Lambda, DynamoDB on-demand, EventBridge Scheduler and SNS email stay within their free allowances.

## License

MIT
