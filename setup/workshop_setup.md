# AWS Python security workshop — student-created resources

This revision lets participants create their own subnets, S3 buckets, security groups,
SQS queues and assigned inert IAM test users. It keeps `Workshop=true`, enforces an individual `Owner` tag, and accepts
an existing federated administrator role. It does not connect to or deploy into AWS
until the instructor runs the script with `--apply`.

## 1. Instructor prerequisites

Use three dedicated **member accounts** in a Workshop OU, all in **us-east-1**.
Keep the management account outside this OU. IAM global API events are handled in
us-east-1. Check inherited SCPs: a deny in another SCP can prevent an intentional
violation even when this package allows it. These SCPs do not grant permissions.
Keep FullAWSAccess or another appropriate allow policy in the policy hierarchy.

Use your existing **AWSAdministrator federated role** in each member account.
A new WorkshopInstructorRole is not required. Configure three AWS CLI profiles for
those roles, and put each role's **exact IAM ARN**, including its path, into
`instructor_role_arn`. Never supply an STS assumed-role session ARN or a wildcard.
For example (illustrative, copy your actual role ARN):

```text
arn:aws:iam::123456789012:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_AWSAdministrator_0123456789abcdef
```

The script compares the actual assumed role to that ARN using IAM GetRole, including
the full path and RoleId. Instructor federation must permit IAM provisioning,
resource preflight reads, CloudWatch Logs provisioning, and optionally Lambda
reserved-concurrency changes. The SCP instructor exceptions apply to **anyone who
can assume those administrator roles**, not just the person running this workshop.
Participants must never be able to assume them. Protect administrator federation
with MFA. You can use a separate instructor role instead by configuring its exact ARN.

Create only the network foundation ahead of time:

- In the network account: one dedicated, non-default VPC tagged `Workshop=true`.
  Use `10.90.0.0/16` to match the supplied subnet CIDR plan, or adapt that plan
  to your existing workshop VPC. Students create the subnets themselves.
- CloudTrail management-event logging in all three accounts, using an existing
  organization trail or one instructor-managed trail per account.

Do not pre-create student subnets, SGs, buckets, queues or IAM test users. Keep account-level S3 Block Public
Access enabled. No EC2 instances, NAT gateways, databases, or customer-managed KMS
keys are needed. Keep production workloads and sensitive data out of these accounts.
Default-bus events and list/Describe operations can expose account metadata; shared
accounts are not a privacy boundary between mutually untrusted users.

## 2. Configuration and two SCPs

```bash
python -m pip install --upgrade boto3
python create_workshop_users.py --example > workshop_accounts.json
```

Edit all placeholders: management ID, member IDs, AWS profiles, exact instructor
role ARNs and network VPC ID. Each account already contains ten student records with
`username` values `user01` through `user10`; these are the actual participant logins.
Network records additionally contain `subnet_cidr` suggestions from `10.90.1.0/24`
through `10.90.10.0/24`. No subnet IDs are needed. Adjust those CIDRs to fit your VPC.
Other resource names are derived from the username, account ID or participant number.
Use the supplied `workshop_accounts.example.json` as the same configuration template.

```bash
python create_workshop_users.py --config workshop_accounts.json \
  --render-scp workshop_scp.json
```

This generates **two** files:

1. `workshop_scp.json`: service/Region limits and protection of IAM roles, users,
   policies, permissions boundaries and CloudTrail.
2. `workshop_scp-tags.json`: required creation tags and tag/ownership protection.

Review and attach **both** to the **Workshop OU only**, using the management account's
AWS Organizations console. Check available SCP attachment slots first. The script
does not attach policies. `workshop_scp.template.json` has instructor placeholders;
do not attach it unchanged. `workshop_tags_scp.json` is the accompanying tagging policy.
Each generated policy is checked against a conservative 5,120-character compact limit.

The tagging SCP targets workshop participant users and execution roles, not every
principal in the organization. It rejects subnet/SG/bucket/queue/test-user creation or tagging when
`Workshop` is not `true`, `Owner` does not equal the immutable principal `Owner` tag,
or the principal lacks that tag. Subnet/SG request-tag checks apply to the newly
created resource, not the pre-existing VPC authorization. Students cannot remove ownership tags,
replace S3 tags through legacy APIs, or tag an existing subnet/SG. Students can reapply the
same mandatory tags to their fixed-name bucket/queue; they cannot substitute another
owner. Test-user creation additionally requires the instructor's exact deny-all
boundary policy in the same account. The IAM boundaries supply the exact names,
resources, and service conditions.
Instructor exceptions in the main SCP permit necessary provisioning/cleanup.

## 3. Provision users and credentials

```bash
python create_workshop_users.py --config workshop_accounts.json
python create_workshop_users.py --config workshop_accounts.json \
  --apply --csv workshop_credentials.csv
```

The first command is read-only preflight. The second creates:

- 30 participant users with unique console passwords and first-login reset;
- separate scoped access policies and immutable per-participant boundaries;
- 30 Lambda execution roles and 30 EventBridge invocation roles, with boundaries;
- 30 log groups with seven-day retention;
- one explicit deny-all boundary policy in the identity account; students create
  their own assigned test users later, with that boundary mandatory at creation;
- the final CSV: `account_id,account_kind,user,password,login_url,status`.

The instructor assigns `Workshop=true` and `Owner=userXX` to participant
users and execution roles. Students cannot change those principal tags, their own
permissions, or the test users' boundaries. Attached user permissions enumerate the
actual scoped operations; a separate boundary adds explicit action/resource/condition
denies. The boundary's broad Allow is limited by its explicit denies; it is not an
administrator grant. Lambda execution-role permissions allow repairs and logging,
not resource creation, EventBridge management, role assumption, or access-key creation.

The actual credential CSV is created locally when provisioning runs. The package's
example CSV contains a header only. Unix file mode is 0600; on Windows, restrict its
NTFS ACL to the instructor. Passwords are not printed. Distribute individual `ready`
rows only, not the complete CSV. A `pending` row means the login response failed or
was ambiguous; verify it before distribution. Passwords are persisted before the API
call so they can be recovered after a timeout. Do not commit/upload the real CSV.

The script refuses existing participant identities/policies/roles/log groups/functions
and refuses to overwrite a CSV. It does **not** reconcile an earlier deployment or
reset its passwords. If you already provisioned with the previous package, do not
simply rerun this version: inspect and migrate or clean that deployment first. A
partial failure leaves resources in place for instructor inspection; there is no
automatic destructive rollback.

## 4. Student resource creation

Each participant uses these mandatory tags on newly created resources:

```text
Workshop = true
Owner = user01
```

Replace `user01` with the student's configured username. The same login names are
used in each of the three accounts; the CSV includes account ID, account kind and
login URL so students can identify the correct account. Passwords are independently
generated for each login. Changing a username before provisioning also changes its
Lambda, rule, role, log-group and queue names.

| Account | What students create | Naming / access restriction |
|---|---|---|
| Network | Security groups | Only in the instructor's workshop VPC; request tags required. Suggested name `user01-SG`. Mutations require matching immutable Owner and Workshop tags. |
| Network | Subnets | Only in the instructor's workshop VPC; mandatory creation tags. Modify/delete requires matching ownership tags and VPC. Use the suggested CIDR in the student's record. |
| Identity | One assigned inert IAM test user, then policies / access keys on it | Exact name `Workshop-Target-01`, root path `/`, mandatory tags and deny-all boundary at creation. No other user or role creation; boundary cannot be changed. |
| Storage | One empty general-purpose S3 bucket | Exact name `workshop-ACCOUNT_ID-student-01-pythonshield`; mandatory tags on creation; later access uses exact ARN plus account ownership. |
| Storage | One empty standard SQS queue | Exact name `user01-Queue`; mandatory creation tags; mutations require matching tags. |

Fixed bucket/queue names prevent creation under arbitrary names and simplify role
permissions before those resources exist. A globally conflicting bucket name will
fail creation; do not bypass the policy. Ask the instructor to update and redeploy
the name restriction if a collision actually occurs. SG names are not an IAM resource
boundary, so ownership tags enforce isolation. There is no per-user count quota for
SGs in this package; monitor the dedicated VPC's security-group quota.

Subnets, security groups and SQS queues support tags at creation. S3 general-purpose buckets
also support creation tags with `s3:CreateBucket` plus `s3:TagResource`; use the current
console or an updated SDK/CLI. **Add tags in the creation request**, not afterwards:
a create-then-tag flow is denied. No S3 ABAC activation is required for this package,
because bucket access is enforced through the exact name and account ownership.
S3 tagging through legacy PutBucketTagging is not granted. Students cannot upload
objects, edit bucket policies or change account-level public-access blocking.

SQS SetQueueAttributes permits all editable attributes on the assigned queue. An
intentionally public queue policy can temporarily admit outsiders; keep it empty and
remediate promptly. Reapplying correct tags cannot claim a different queue because
IAM names are exact. SG tagging is allowed only as part of CreateSecurityGroup,
so students cannot take ownership of an existing group or subnet by relabeling it.
Students cannot tag individual SG rules; use plain ingress creation/removal without
rule TagSpecifications. SG rule edit APIs are intentionally not included: revoke the
old rule and add a new one. They can delete their own SG, empty bucket and queue for
cleanup; they cannot delete another participant's resources. They can also delete
their own empty subnets. Subnet attribute changes require the student's immutable
ownership tags and the workshop VPC; the attribute API is not restricted to a single attribute.

### Create the network subnet

In the network account, open **VPC → Subnets → Create subnet**. Select the workshop
VPC, choose an Availability Zone, and use the configured `subnet_cidr`. For `user01`,
the example is `10.90.1.0/24` and a suggested name is `user01-Subnet`. Include
`Workshop=true` and `Owner=user01` in the creation request. Create only one subnet
at a time in the console so the required tags accompany every resource.

Preflight verifies that the suggested CIDRs are canonical IPv4 ranges, do not
overlap each other, fit an associated VPC range, and do not overlap existing subnets.
**These suggestions are not IAM-enforced CIDR allocations or per-user count limits.**
Students could choose another free range within the workshop VPC; supervise the
address plan and subnet quota. VPC creation, routing changes, instances and NAT
gateways remain outside student permissions.

For the public-IP exercise, select the newly created subnet, choose **Actions →
Edit subnet settings**, and enable automatic public IPv4 assignment. The Lambda
must extract the subnet ID from the CloudTrail event, read its tags and VPC, and
verify `Workshop=true`, the student's Owner, and the workshop VPC before remediation.
Its execution boundary independently restricts modifications to those owned subnets.
Do not use hardcoded instructor-created subnet IDs in the remediation code.

### Create the identity test user

In the identity account, participant 01 creates `Workshop-Target-01` in IAM:

1. Open **IAM → Users → Create user** and enter the assigned name.
2. Leave **Provide user access to the AWS Management Console** unchecked.
3. Choose **Attach policies directly**, initially select no permissions policies,
   and set the permissions boundary to **Workshop-Target-DenyAll**.
4. Add `Workshop=true` and `Owner=user01` before submitting creation.
5. Review and create the user. Its root path is `/`; do not use another path.

Use your assigned number throughout. Missing/wrong tags or a missing/different
boundary cause AccessDenied. If the console changes and separates tagging or boundary
assignment into later calls, stop and ask the instructor: those values must be in
the **CreateUser request**. Never loosen the safeguards to make the wizard succeed.
Students can inspect the deny-all policy but cannot edit it, remove/replace the
boundary, create console credentials, add the user to groups, delete the user,
or create IAM roles. They can reapply the same mandatory tags to their own target.
The instructor handles target deletion during cleanup.

Next, attach AdministratorAccess, add the inline wildcard policy, or create an
access key for the three existing identity exercises. These policies cannot grant
effective access because the boundary explicitly denies every action. Keep key
secrets out of logs and delete/deactivate the test keys through remediation.
Test-user creation is preparation for those exercises; the scenario count stays ten.

**Earlier package deployments:** participant logins and execution resources previously used
`Workshop-Student-XX`; this revision uses the configured usernames such as `user01`.
Subnets previously required instructor-created IDs; they now use ownership and VPC
conditions. Existing policies and roles require instructor migration or cleanup and
fresh provisioning. The script does not rename or upgrade existing resources.

Test targets previously used `/workshop-targets/`.
This revision uses root-path targets for console creation, and both SCPs must be
updated. The main SCP still protects legacy targets. Existing participant policies
are not upgraded by rerunning the provisioning script; an instructor must migrate
their access policies/boundaries and Lambda target permissions or clean up and
provision again. Do not remove a target boundary during migration.

## 5. The 10 exercises

| Account | Exercises |
|---|---|
| Network | Public SSH (22), public RDP (3389), all-protocol public ingress, subnet automatic public IPv4 assignment |
| Identity | AdministratorAccess attachment, inline `Allow Action:* Resource:*`, access-key creation on the inert target |
| Storage | Disable bucket Block Public Access, public SQS SendMessage policy, disable queue encryption |

Creating an empty SG does not include an SSH/RDP rule. Trigger those events by adding
an ingress rule afterward. IAM access keys in the exercise belong to the deny-all
**test target**, not to participant logins. Do not use/distribute those key secrets.

## 6. Lambda and EventBridge authoring

Participant 01 creates exactly `user01-Remediator`, choosing Python and
**Use an existing role**: `user01-LambdaRole`. Each participant substitutes
their number. Edit Python in the Lambda console or upload a ZIP. The script does not
pre-create functions, because function creation is part of the hands-on exercise.

Create rules on the **default event bus** named `user01-*`. Use precise
`AWS API Call via CloudTrail` patterns, the right API event names and filters for the
assigned target/resources. Ignore failed calls and calls originating from the Lambda
execution role; read current state and return without writing if already compliant.
Do not log entire IAM events or sensitive request payloads. Remediation code obtains
new SG IDs from the event, reads tags, and checks ownership before correcting ingress;
the execution role independently denies repairs to unowned groups. Bucket/queue names
are fixed, so no privilege expansion is needed for resource discovery.

Use `user01-EventRole` as the EventBridge target invocation role. It can
invoke only that student's function, and its trust requires the same account and
student rule-name prefix. Participants cannot AddPermission or make Lambda public.
Choose an existing role if a console wizard tries to create one. API equivalent:

```python
boto3.client('events', region_name='us-east-1').put_targets(
    Rule='user01-SSH',
    Targets=[{
        'Id': 'Remediator',
        'Arn': 'arn:aws:lambda:us-east-1:ACCOUNT_ID:function:user01-Remediator',
        'RoleArn': 'arn:aws:iam::ACCOUNT_ID:role/workshop-execution/user01-EventRole'
    }]
)
```

Participants do not receive access keys or CloudShell permissions. Use the AWS console
for resource/API exercises and Python inside Lambda. The code above illustrates the
API call, not an instruction to create participant credentials. Read/list APIs needed
for console navigation expose metadata but do not grant writes. Some pages can show
AccessDenied for unrelated APIs; use direct links rather than broadening access.

## 7. Concurrency, cost, validation and cleanup

After all functions have been created, the instructor may cap concurrency:

```bash
python create_workshop_users.py --config workshop_accounts.json \
  --cap-concurrency --apply
```

This sets reserved concurrency to 1 per function; students cannot change/remove it
or delete/recreate a function. It can fail if account concurrency quotas leave too
little reservable capacity. Check Lambda Account settings first. It stops on failure;
earlier caps may already be applied. It is not a spending cap.

IAM/SCP here cannot enforce a Lambda memory/timeout maximum. Students can write loops,
increase function settings or create many rules/SGs. Use 128–256 MB and short timeouts,
idempotent repairs, exact event filters, AWS Budgets alerts and instructor supervision.
Alerts do not automatically stop charges. Python can access the public internet:
IAM limits AWS authorization, not network destinations. Restricting account metadata
or untrusted code execution requires stronger separation than these shared sandboxes.

Before the class, validate generated policies with IAM Access Analyzer ValidatePolicy,
then pilot participant 01 in each account. Check missing/wrong creation tags, spoofed
Owner, tag replacement, missing/wrong target boundary, cross-student IAM-user creation,
target console-credential/boundary edits, wrong VPC, another participant's subnet/bucket/queue/SG, unauthorized
role passing and all ten successful remediations. Local tests cover these policy
conditions, federated role-path/RoleId validation, size limits, provisioned Owner tags,
CSV handling and partial failures. **No live AWS integration test has been run.**

Clean up in this order: disable/delete rules and targets; remove functions/log groups;
remove student subnets/SGs/buckets/queues; remove IAM target credentials/policies/users;
remove participant login profiles/access policies/boundaries/users; remove execution
role inline policies/boundaries/roles and managed policies; remove network foundations.
Delete the credential CSV after secure distribution and cleanup. Keep both SCPs attached
while workshop principals remain. Removing a bucket name does not reserve that name;
remove related permissions during final cleanup.

Official references:

- https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-create-tag.html
- https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/supported-iam-actions-tagging.html
- https://docs.aws.amazon.com/vpc/latest/userguide/create-subnets.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html
- https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_CreateQueue.html
- https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-events-iam-roles.html
- https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html
- https://docs.aws.amazon.com/IAM/latest/APIReference/API_CreateUser.html
- https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_examples_iam-new-user-tag.html
