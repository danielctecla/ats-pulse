# ats-pulse

Serverless job tracker. Every 4 hours from 6:00 to 22:00 (Mexico City time), a Lambda polls company job boards, keeps the Mexico-based engineering openings it hasn't seen before, stores them in DynamoDB, and emails a digest through SES.

```
EventBridge Scheduler ──► Lambda (Python, stdlib + boto3) ──► DynamoDB (seen jobs, source health)
  every 4 h, 6:00 to 22:00      │
  Mexico City time              ├──► SES: job digest, alert when a source keeps failing
                                └──► CloudWatch alarm ──► SNS: email when the Lambda itself fails
```

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 1 | Infrastructure (Terraform, local state) | done |
| 2 | Fetch, filter, dedupe, source health, crash alarm | done |
| 3 | SES emails: HTML digest and plain alert | done |
| 4 | S3 remote state + GitHub Actions (OIDC) | pending |

## Requirements

- Terraform >= 1.10, AWS CLI v2, Python 3.14+ and GNU Make
- AWS credentials for `make plan` and deploys (e.g. `AWS_PROFILE`). Tests and `make run-local` need none.

## Quick start

```bash
make test        # creates .venv from requirements-dev.txt, runs pytest + moto
make run-local   # polls the real job boards, in-memory DynamoDB; prints the emails, writes preview.html
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
  emails.py                 digest (HTML + plain text) and alert content
  notify.py                 sends them through SES
  handler.py                Lambda entry point
tests/                      pytest + moto; fixtures/ holds real Ashby, Greenhouse, Workday and Oracle responses, trimmed
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

5. **Alert** for each source that has failed 2 or more runs in a row and hasn't been alerted yet in this outage.
6. **Digest** of all new jobs (no email when there's nothing new).
7. **Save** the new jobs, only after the digest is sent.

The alert and the digest are sent independently: if one fails, the other still goes out, then the run fails so the crash alarm fires. Nothing is lost:
- A failed digest: its jobs weren't saved, so the next run finds and sends them again.
- A failed alert: the source isn't marked as alerted, so the next run retries it.

The reverse can happen too: an email goes out but the save after it fails. Then the next run sends it again. A duplicate email is the trade-off for never losing one.

Behavior to know about:
- The first run against an empty table reports every current matching opening. Later runs only report new ones.
- When Mexico is only a secondary location, the job's location reads `Ciudad de México (also Palo Alto)`.
- The stored link is the job's posting page, which has the apply button.
- Greenhouse boards have no standard department in their job list, so the department is the board's `Career Site Category` field. Boards that don't use it are matched on the title only.
- Workday boards are filtered by the API itself, using the board's facets: only openings in Mexico are fetched, from the job categories that pass the department rule above, plus internships from any category (those then go through the title rule). Openings in other categories aren't matched on the title: on real data, "Solution Architect" and "Solution Engineer" there were sales roles. A board without categories gets all its Mexico openings, matched on the title only.
- Workday only says how long ago a job was posted (`Posted 3 Days Ago`), so the date is calculated from that, and left empty for `Posted 30+ Days Ago`.
- Oracle Recruiting Cloud boards are filtered by the API too: only openings in Mexico are fetched, including those where Mexico is only a secondary location. The department is the job family when the board fills it in; boards that don't are matched on the title only.

### Emails

Both are sent from and to the notification address, with the sender name `ats-pulse`.

| Email | Subject | Format |
|-------|---------|--------|
| Digest | `Openings at Acme and Globex` | HTML plus a plain-text part with the same content. The inbox preview says how many (`7 engineering openings in Mexico`). Jobs grouped by company (A–Z) under the company's logo, newest posting first, each with its title (linked to the posting), location, department, workplace and employment type when the board gives them, and posting date with its age (`Nov 19 · 3 days ago`). Ends with a credit line linking to the author. |
| Alert | `Job board failing: Acme` | Plain text: each failing source, failed runs in a row, last error. |

`make run-local` prints both as plain text and writes the digest's HTML to `preview.html` (gitignored) so you can open it in a browser.

### Adding a company

Add one entry to `sources.toml`:

```toml
[[sources]]
company = "Acme"         # display name, also the health key (must be unique)
ats     = "greenhouse"   # supported: ashby, greenhouse, oracle, workday
slug    = "acme"         # the company's board name in that ATS
logo    = "https://upload.wikimedia.org/.../330px-Acme_logo.svg.png"  # optional
```

The slug is the `<slug>` in `jobs.ashbyhq.com/<slug>` or `boards-api.greenhouse.io/v1/boards/<slug>/jobs`. For Workday it's `<tenant>.<wdN>/<site>`, taken from the careers site URL `https://<tenant>.<wdN>.myworkdayjobs.com/<site>` (e.g. `acme.wd5/External_Careers`). For Oracle Recruiting Cloud it's `<pod>/<site>`, from `https://<pod>.oraclecloud.com/hcmUI/CandidateExperience/en/sites/<site>` (e.g. `acme.fa.us2/CX_1`).

`logo` is optional: an https URL of a PNG or JPEG, shown in the digest instead of the company name (the name still shows if the mail client blocks images). Gmail doesn't render SVG or embedded `data:` images, so use a hosted PNG. Wikimedia Commons serves PNG renders of most logos (`upload.wikimedia.org/wikipedia/commons/thumb/.../330px-<file>.svg.png`).

To support another ATS (e.g. Lever), add a module in `adapters/` with a `fetch_jobs(source)` function and register it in `adapters/__init__.py`.

## Data model

One DynamoDB table (on-demand), partition key `pk`:

| Item | `pk` | Attributes |
|------|------|------------|
| Job | `job#<ats>:<slug>#<job_id>` | job_id, source, company, title, location, department, url, published_at, first_seen_at |
| Source health | `health#<company>` | consecutive_failures, last_error, last_success_at, alert_sent (set after the alert email goes out; removed on recovery) |

Job descriptions aren't stored: they aren't needed, and DynamoDB items are limited to 400 KB.

## Alerts and monitoring

| Failure | Handled by | You get |
|---------|------------|---------|
| One source fails (HTTP error, timeout, invalid JSON) | Per-source error handling. The other sources still run. | One SES alert once it has failed 2 runs in a row (retried next run if that email fails). Not repeated while it keeps failing; re-armed once it recovers. |
| The whole Lambda fails (timeout, out of memory, import error, unhandled exception, failed digest or alert email) | CloudWatch alarm on the Lambda `Errors` metric | An SNS email for each failed run |

The crash alarm goes through SNS rather than SES, so it still arrives when the Lambda or SES is what's broken.

Each run logs one JSON line per source, plus a run summary:

```json
{"message": "source summary", "source": "greenhouse:acme", "company": "Acme", "fetched": 148, "mexico": 5, "engineering": 4, "new": 4, "errors": 0}
```

`errors` counts malformed postings skipped, plus 1 if the source failed; failed sources also carry an `error` field. For Workday and Oracle sources, `fetched` only counts what the API returned after its own filtering (Workday: Mexico, engineering categories, internships; Oracle: Mexico).

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
| `schedule_expression` | `cron(0 6,10,14,18,22 * * ? *)`: every 4 hours from 6:00 to 22:00, none overnight |
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
make run-local   # real job-board APIs, in-memory DynamoDB, emails printed
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

Then check it end to end with one manual run (use your `project_name` and `aws_region` if you changed them):

```bash
aws lambda invoke --function-name ats-pulse --region us-east-1 --cli-read-timeout 0 /dev/stdout
```

`--cli-read-timeout 0` waits for the whole run; otherwise the CLI retries after 60 s and could start a second run. The table starts empty, so this first run emails every current matching opening. If the digest arrives, fetching, DynamoDB and SES all work. Later runs only email when something is new. A `FunctionError` in the response means the run failed: the CloudWatch logs have the details, and the crash alarm emails you too.

**Using a Gmail (or other webmail) address:** SES sends "from" your own address but can't sign mail for gmail.com, so it fails Gmail's DMARC check. gmail.com's policy is `p=none`, so the mail is still delivered, but the first emails may land in spam. Mark them as not spam or add a filter. For reliable delivery, use an address on a domain you own and verify the domain in SES with Easy DKIM.

## Security

- **Least-privilege IAM:**
  - The Lambda can only use GetItem, PutItem, UpdateItem and BatchGetItem on its own table, `ses:SendEmail` from the verified identity, and write to its own log group.
  - The scheduler role can only invoke this function, and only from this account.
- **Notification email:**
  - It's a sensitive Terraform variable with no default, so it shows as `(sensitive value)` in plans.
  - It's never logged or output, and tests use `test@example.com`. SES error messages can contain it, so it's redacted from them before they're raised or logged.
  - It does end up in Terraform state in plaintext, so never share or commit state files.
- **Email content:** everything that comes from a job board is HTML-escaped, and only `http(s)` links are rendered.
- **No async retries:** the Lambda has async retries disabled, so a crash can't send the same digest twice. The next scheduled run picks up instead.

## Cost

Effectively zero at this volume:
- SES costs $0.10–0.16 per 1,000 emails.
- The alarm fits within CloudWatch's 10 free alarms.
- Lambda, DynamoDB on-demand, EventBridge Scheduler and SNS email stay within their free allowances.

## License

MIT
