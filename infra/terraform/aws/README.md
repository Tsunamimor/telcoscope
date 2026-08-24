# AWS Free-Tier deployment (optional)

> This is a placeholder for the Week 7 optional deployment work.

## Intent

A minimal, cost-bounded AWS deployment of `telcoscope` using only Free Tier
eligible services for the first 12 months of a new AWS account, and ≤ $5/month
thereafter if not torn down.

## Planned components

- **VPC** with public + private subnets
- **RDS PostgreSQL** (`db.t3.micro`, Free Tier eligible) — primary data store
  (TimescaleDB extension is supported on RDS via the `shared_preload_libraries`
  parameter group)
- **S3** bucket — landing zone for raw CSV / Parquet PM uploads
- **Lambda** function — triggered on S3 object-created, ingests files into RDS
- **EC2 `t3.micro`** OR **App Runner** — hosts Grafana + Streamlit
- **CloudWatch budget alarm** — alerts at $1, $3, $5 thresholds

## Why Terraform

- Reproducible — anyone can deploy the same stack
- Tear-down-able — `terraform destroy` removes everything
- Auditable — infrastructure changes go through git

## Cost guardrails

- All resources tagged `Project=telcoscope` for easy filtering
- `terraform destroy` script in `scripts/cloud-down.sh`
- Budget alarm wired to an SNS topic that emails the deployer
- Default stop-on-cost-threshold automation

## Status

Not implemented in v1. To be added in v1.1.
