# Production multi-clinic rollout runbook

Status: prepared from read-only AWS inspection on 2026-09-27. Not executed.
This is a planned-downtime migration. Do not onboard another clinic until all
verification passes.

## Verified live baseline

- Account 449952322520, us-east-1, profile dental-clinic-learning.
- ECS dental-clinic/dental-clinic-web: desired 1, running 1, revision 5,
  image dental-clinic-web:d0009a0d83f8, completed rollout.
- ECS deployment circuit breaker currently has automatic rollback enabled.
- RDS dental-clinic-db: PostgreSQL 16.14, db.t4g.micro, available, encrypted,
  private, deletion-protected, one-day backup retention and PITR available.
- No manual pre-migration snapshot existed when inspected.
- Reviewed feature commit: 42b1ed36fa40f8dfc251362ca67f98d004552d19.
- The rollout image uses the later synchronized HEAD that includes this runbook.
- Evidence: 273 tests passed; CodeRabbit follow-up raised 0 issues.

Re-run every read-only check on rollout day because AWS state can change.

## Why downtime and special rollback handling are required

The old application does not populate clinic ownership. Writers must stay stopped
while migrations add nullable ownership, backfill it, audit relationships, and
then make ownership mandatory.

After NOT NULL is applied, revision 5 is not a safe writer. It cannot supply the
new clinic fields. ECS automatic rollback must therefore be disabled temporarily:
a failed new deployment should remain in maintenance, not restart incompatible
code. Enable rollback again only after the new application is healthy.

The database snapshot does not back up Cloudinary objects. These migrations do
not delete media, but media recovery remains separate work.

## Variables

Run PowerShell from the authoritative repository:

```powershell
Set-Location "C:\Users\Shata\Desktop\Dental clinic claude\dental_clinic"
$AWS_PROFILE = "dental-clinic-learning"
$AWS_REGION = "us-east-1"
$AWS_ACCOUNT_ID = "449952322520"
$CLUSTER = "dental-clinic"
$SERVICE = "dental-clinic-web"
$DB_INSTANCE = "dental-clinic-db"
$ECR_REPOSITORY = "dental-clinic-web"
$ECR_URI = "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY"
$NETWORK_FILE = "file://aws/ecs-run-task-network.json"
```

Stop on any error or unexpected output.

## 1. Read-only preflight

```powershell
if (git status --porcelain) { throw "Working tree is not clean" }
if ((git branch --show-current) -ne "chore/aws-production-readiness") { throw "Wrong branch" }
git fetch origin chore/aws-production-readiness
$RELEASE_COMMIT = git rev-parse HEAD
$REMOTE_COMMIT = git rev-parse origin/chore/aws-production-readiness
if ($RELEASE_COMMIT -ne $REMOTE_COMMIT) { throw "Local and GitHub branch differ" }
$IMAGE_TAG = $RELEASE_COMMIT.Substring(0, 12)
aws sts get-caller-identity --profile $AWS_PROFILE --region $AWS_REGION
aws ecs describe-services --cluster $CLUSTER --services $SERVICE --profile $AWS_PROFILE --region $AWS_REGION --query "services[0].{Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount,TaskDefinition:taskDefinition,Rollout:deployments[0].rolloutState}" --output json
aws rds describe-db-instances --db-instance-identifier $DB_INSTANCE --profile $AWS_PROFILE --region $AWS_REGION --query "DBInstances[0].{Status:DBInstanceStatus,Version:EngineVersion,Encrypted:StorageEncrypted,Public:PubliclyAccessible,BackupDays:BackupRetentionPeriod,DeletionProtection:DeletionProtection,LatestRestorableTime:LatestRestorableTime}" --output json
curl.exe -sS https://app.dentomanager.com/health/
aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:us-east-1:449952322520:targetgroup/dental-clinic-web/82f42211a75e4a38 --profile $AWS_PROFILE --region $AWS_REGION --output json
aws logs tail /ecs/dental-clinic-web --since 30m --profile $AWS_PROFILE --region $AWS_REGION
$OLD_TASK_DEFINITION_ARN = aws ecs describe-services --cluster $CLUSTER --services $SERVICE --profile $AWS_PROFILE --region $AWS_REGION --query "services[0].taskDefinition" --output text
if (-not $OLD_TASK_DEFINITION_ARN) { throw "Cannot determine old revision" }
```

Require the correct account, one healthy task, completed rollout, available RDS,
encryption and deletion protection, recent restore time, and `{"status":"ok"}`.

## 2. Build, test, push and register without deploying

```powershell
docker build --platform linux/amd64 --tag "${ECR_URI}:${IMAGE_TAG}" .
if ($LASTEXITCODE -ne 0) { throw "Build failed" }
docker run --rm -e DJANGO_SETTINGS_MODULE=dental_clinic.settings_pytest -e DATABASE_URL=sqlite:////tmp/release-test.sqlite3 "${ECR_URI}:${IMAGE_TAG}" pytest -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw "Image tests failed" }
aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE |
    docker login --username AWS --password-stdin $ECR_URI
if ($LASTEXITCODE -ne 0) { throw "ECR login failed" }
docker push "${ECR_URI}:${IMAGE_TAG}"
if ($LASTEXITCODE -ne 0) { throw "Push failed" }
aws ecr describe-images --repository-name $ECR_REPOSITORY --image-ids imageTag=$IMAGE_TAG --profile $AWS_PROFILE --region $AWS_REGION --query "imageDetails[0].{Tags:imageTags,Digest:imageDigest,Pushed:imagePushedAt}" --output json

$release = Get-Content -Raw -Encoding UTF8 aws/ecs-task-definition.json | ConvertFrom-Json
$release.containerDefinitions[0].image = "${ECR_URI}:${IMAGE_TAG}"
$releasePath = Join-Path ([System.IO.Path]::GetTempPath()) "dental-clinic-task-${IMAGE_TAG}.json"
[System.IO.File]::WriteAllText(
    $releasePath,
    ($release | ConvertTo-Json -Depth 100),
    [System.Text.UTF8Encoding]::new($false)
)
$registered = aws ecs register-task-definition --cli-input-json "file://$releasePath" --profile $AWS_PROFILE --region $AWS_REGION --query "taskDefinition.{Arn:taskDefinitionArn,Image:containerDefinitions[0].image}" --output json | ConvertFrom-Json
if ($registered.Image -ne "${ECR_URI}:${IMAGE_TAG}") { throw "Wrong image" }
$NEW_TASK_DEFINITION_ARN = $registered.Arn
$registered | ConvertTo-Json
```

ECR push and task registration do not change the running service.

## 3. One-off task helper

```powershell
function Invoke-DentalClinicTask {
    param([string]$OverridesFile, [string]$Label)
    $run = aws ecs run-task --cluster $CLUSTER --launch-type FARGATE --task-definition $NEW_TASK_DEFINITION_ARN --network-configuration $NETWORK_FILE --overrides "file://$OverridesFile" --profile $AWS_PROFILE --region $AWS_REGION --output json | ConvertFrom-Json
    if ($run.failures.Count -gt 0 -or $run.tasks.Count -ne 1) {
        $run | ConvertTo-Json -Depth 20
        throw "$Label did not start"
    }
    $taskArn = $run.tasks[0].taskArn
    aws ecs wait tasks-stopped --cluster $CLUSTER --tasks $taskArn --profile $AWS_PROFILE --region $AWS_REGION
    if ($LASTEXITCODE -ne 0) { throw "$Label wait failed" }
    $task = aws ecs describe-tasks --cluster $CLUSTER --tasks $taskArn --profile $AWS_PROFILE --region $AWS_REGION --output json | ConvertFrom-Json
    $container = $task.tasks[0].containers | Where-Object name -eq "web"
    $taskId = $taskArn.Split("/")[-1]
    aws logs get-log-events --log-group-name /ecs/dental-clinic-web --log-stream-name "web/web/$taskId" --start-from-head --profile $AWS_PROFILE --region $AWS_REGION --query "events[].message" --output text
    if ($container.exitCode -ne 0) {
        throw "$Label failed: exit $($container.exitCode), $($container.reason)"
    }
    Write-Host "$Label passed: $taskArn"
}
```

## 4. Stop writers and snapshot the exact cutover state

Confirm no imports or operator shells are running, then:

```powershell
aws ecs update-service --cluster $CLUSTER --service $SERVICE --desired-count 0 --profile $AWS_PROFILE --region $AWS_REGION --query "service.{Desired:desiredCount,TaskDefinition:taskDefinition}" --output json
aws ecs wait services-stable --cluster $CLUSTER --services $SERVICE --profile $AWS_PROFILE --region $AWS_REGION
$stopped = aws ecs describe-services --cluster $CLUSTER --services $SERVICE --profile $AWS_PROFILE --region $AWS_REGION --query "services[0].{Desired:desiredCount,Running:runningCount,Pending:pendingCount}" --output json | ConvertFrom-Json
if ($stopped.Desired -ne 0 -or $stopped.Running -ne 0 -or $stopped.Pending -ne 0) { throw "Writers still running" }

$CUTOVER_ID = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
$SNAPSHOT_ID = "dental-clinic-pre-multiclinic-$CUTOVER_ID"
aws rds create-db-snapshot --db-instance-identifier $DB_INSTANCE --db-snapshot-identifier $SNAPSHOT_ID --profile $AWS_PROFILE --region $AWS_REGION --query "DBSnapshot.{Id:DBSnapshotIdentifier,Status:Status}" --output json
aws rds wait db-snapshot-available --db-snapshot-identifier $SNAPSHOT_ID --profile $AWS_PROFILE --region $AWS_REGION
aws rds describe-db-snapshots --db-snapshot-identifier $SNAPSHOT_ID --profile $AWS_PROFILE --region $AWS_REGION --query "DBSnapshots[0].{Id:DBSnapshotIdentifier,Status:Status,Encrypted:Encrypted,Created:SnapshotCreateTime}" --output json
```

Require an available, encrypted snapshot. Record its ID. Manual snapshot storage
can cost money; retain it through observation, then review deletion deliberately.

## 5. Expand, backfill, audit, contract, audit

```powershell
Invoke-DentalClinicTask "aws/ecs-tenancy-backfill-overrides.json" "nullable fields and legacy backfill"
Invoke-DentalClinicTask "aws/ecs-tenancy-audit-overrides.json" "pre-constraint ownership audit"
```

Audit must report `{"ok":true,"issues":[]}`. Otherwise stop with service zero;
do not guess ownership.

```powershell
Invoke-DentalClinicTask "aws/ecs-migration-overrides.json" "remaining migrations"
Invoke-DentalClinicTask "aws/ecs-tenancy-audit-overrides.json" "post-migration ownership audit"
Invoke-DentalClinicTask "aws/ecs-tenancy-showmigrations-overrides.json" "migration-state verification"
```

Require a clean audit and all listed migrations applied. Revision 5 must no longer
be started against this database.

## 6. Deploy without incompatible automatic rollback

```powershell
aws ecs update-service --cluster $CLUSTER --service $SERVICE --deployment-configuration "maximumPercent=200,minimumHealthyPercent=100,deploymentCircuitBreaker={enable=true,rollback=false}" --profile $AWS_PROFILE --region $AWS_REGION --query "service.deploymentConfiguration" --output json
aws ecs update-service --cluster $CLUSTER --service $SERVICE --task-definition $NEW_TASK_DEFINITION_ARN --desired-count 1 --force-new-deployment --profile $AWS_PROFILE --region $AWS_REGION --query "service.{Desired:desiredCount,TaskDefinition:taskDefinition,Deployments:deployments[].{Status:status,Rollout:rolloutState,TaskDefinition:taskDefinition}}" --output json
aws ecs wait services-stable --cluster $CLUSTER --services $SERVICE --profile $AWS_PROFILE --region $AWS_REGION
$state = aws ecs describe-services --cluster $CLUSTER --services $SERVICE --profile $AWS_PROFILE --region $AWS_REGION --query "services[0].{Desired:desiredCount,Running:runningCount,Pending:pendingCount,TaskDefinition:taskDefinition,Deployments:deployments[].{Status:status,Rollout:rolloutState,TaskDefinition:taskDefinition},Events:events[0:8].[createdAt,message]}" --output json | ConvertFrom-Json
$state | ConvertTo-Json -Depth 10
if ($state.Desired -ne 1 -or $state.Running -ne 1 -or $state.Pending -ne 0 -or $state.TaskDefinition -ne $NEW_TASK_DEFINITION_ARN) { throw "New service is not steady" }
```

## 7. Verify production before enabling rollback

```powershell
curl.exe -I https://app.dentomanager.com/
curl.exe -sS https://app.dentomanager.com/health/
aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:us-east-1:449952322520:targetgroup/dental-clinic-web/82f42211a75e4a38 --profile $AWS_PROFILE --region $AWS_REGION --output json
aws logs tail /ecs/dental-clinic-web --since 15m --profile $AWS_PROFILE --region $AWS_REGION
Invoke-DentalClinicTask "aws/ecs-tenancy-audit-overrides.json" "live ownership audit"
```

Human login checks:

1. DentoManager Clinic is selected.
2. Existing users have expected roles.
3. Patient, appointment, financial and X-ray counts look correct.
4. Existing X-ray images load.
5. A harmless read/search works.
6. Do not create another clinic or modify real clinical data for smoke testing.

Only after all checks:

```powershell
aws ecs update-service --cluster $CLUSTER --service $SERVICE --deployment-configuration "maximumPercent=200,minimumHealthyPercent=100,deploymentCircuitBreaker={enable=true,rollback=true}" --profile $AWS_PROFILE --region $AWS_REGION --query "service.deploymentConfiguration" --output json
```

Record task definition ARN, image digest, snapshot ID, migration task ARNs, audit
outputs, completion time and verifier.

## Failure handling

- Before scale-down: fix the image or plan; production is unchanged.
- After scale-down but before migrations: revision 5 may be restored with desired
  count 1 after confirming the database is unchanged.
- After any migration begins: keep desired count zero on failure and preserve logs.
  Prefer fix-forward while writers remain stopped.
- After mandatory fields: never restart revision 5 on the upgraded database.
- If fix-forward is unsafe, restore the manual snapshot to a separate RDS instance
  and validate it before directing the old application to that new endpoint.
  Snapshot restore needs a deliberate endpoint, credential/secret, networking and
  task-definition change. Do not overwrite/delete the existing RDS instance during
  incident response. A separate AWS restore drill is still required before calling
  production rollback fully tested.
- If the new service fails, rollback remains disabled; inspect ECS events and its
  log stream, publish a compatible fix, or use snapshot restore.

## Post-deployment hold

Keep the snapshot during the observation period. Monitor CloudWatch errors, ECS
restarts, ALB target health and RDS metrics. Do not provision the first additional
clinic immediately. Verify RDS restore and Cloudinary recovery separately. Update
the tracked task-definition image and commit the deployment record only after the
live revision is verified.
