# Storage group — Python remediation workshop

For students `user01`–`user10` in the **storage account**. Follow only this group guide.

## 1. Sign in and identify your resources

1. Use only your own login URL, username and temporary password supplied by the instructor.
2. Change your password when prompted. Select **US East (N. Virginia), us-east-1**.
3. Confirm you are in your assigned account. Students use the console; no CLI profile, access key or CloudShell is needed.
4. Replace `user01` everywhere with your username, and `01` with your two-digit participant number.
5. Add these tags **in each resource creation request**, before submitting:

```text
Workshop = true
Owner = user01
```

Names and tags are case-sensitive. Use your own resources only. Do not change your login user, existing roles, policies, boundaries, CloudTrail or account settings.

## 2. Create your Lambda function

1. Open **Lambda → Functions → Create function → Author from scratch**.
2. Name it exactly `user01-Remediator`. Choose a currently supported Python runtime.
3. Expand **Change default execution role**; choose **Use an existing role → user01-LambdaRole**. Do not create a new role.
4. Add `Workshop=true` and `Owner=user01` in the creation options. Create the function. If the console cannot send required tags at creation, ask the instructor to assist.
5. Under **Configuration → General configuration**, use **128 MB** and a **10-second timeout** to start. Keep the function outside a VPC.
6. Paste the group code below into `lambda_function.py`. Replace every indicated value. Keep handler `lambda_function.lambda_handler`. Choose **Deploy** after each edit.
7. Leave concurrency settings unchanged. Network/storage quota increases are pending; the instructor will configure reservations later if approved.

The execution role allows repairs. The separate `user01-EventRole` allows EventBridge to invoke the function. Lambda obtains temporary credentials automatically; never paste AWS credentials into code.

The supplied code is an educational starting point aligned with the workshop permissions. It has not been tested in your AWS accounts. Pilot one case first. It deliberately repairs a narrow lab baseline rather than assessing every possible production misconfiguration.

## 3. Create your empty bucket and queue

Ask the instructor for the storage account ID and the **exact CloudTrail eventName for the bucket-level Block Public Access update**, verified in the pilot. API permission names and CloudTrail event names are not always identical.

1. Open **S3 → Create bucket**. Choose a general-purpose bucket in us-east-1.
2. Use exactly `workshop-ACCOUNT_ID-student-01-pythonshield`; substitute the storage account ID and your two-digit participant number.
3. Add both mandatory tags **before Create bucket**. Keep default Object Ownership, encryption and all four bucket Block Public Access settings enabled.
4. Create the bucket and leave it empty. Do not upload files or edit its bucket policy. If required tags are unavailable at creation, ask the instructor to assist rather than creating an untagged bucket.
5. Open **SQS → Create queue**. Choose **Standard**, name it exactly `user01-Queue`, and add both mandatory tags before submitting.
6. Keep **SSE-SQS** encryption enabled. Keep the default access policy; create the queue and leave it empty.
7. Copy your queue URL and ARN from its details. Keep a local copy of its original policy for restoration.

Account-level S3 Block Public Access remains enabled. Changing bucket-level protection alone will not make this empty bucket public. The queue public-policy exercise can introduce real exposure; enable the rule first and keep the queue empty.

## 4. Deploy the group remediation code

Set `OWNER`, `NUMBER`, `ACCOUNT_ID` and `S3_BPA_EVENT`. Use the instructor's observed eventName in both code and rule. The queue branch checks both policy and encryption on every SetQueueAttributes event. It removes only the named public exercise statement and preserves other policy statements. Ownership tags are enforced by the execution boundary; the runtime is not granted queue-tag listing.

If the pilot shows different CloudTrail request field names or missing queueUrl/bucketName, have the instructor adapt the extraction before class. Do not remove scope checks. The code retains existing KMS encryption; this lab starts with SSE-SQS and does not exercise KMS changes.

```python
import json
import boto3

OWNER = "user01"
NUMBER = "01"
ACCOUNT_ID = "REPLACE_STORAGE_ACCOUNT_ID"
# Instructor supplies the exact eventName from a pilot CloudTrail event.
S3_BPA_EVENT = "REPLACE_WITH_OBSERVED_S3_EVENT_NAME"
BUCKET = f"workshop-{ACCOUNT_ID}-student-{NUMBER}-pythonshield"
QUEUE = f"{OWNER}-Queue"
QUEUE_ARN = f"arn:aws:sqs:us-east-1:{ACCOUNT_ID}:{QUEUE}"
s3 = boto3.client("s3", region_name="us-east-1")
sqs = boto3.client("sqs", region_name="us-east-1")


def lambda_handler(event, context):
    d = event.get("detail", {})
    p = d.get("requestParameters") or {}
    caller = f"arn:aws:iam::{ACCOUNT_ID}:user/workshop/{OWNER}"
    if (event.get("account") != ACCOUNT_ID or event.get("region") != "us-east-1"
            or d.get("userIdentity", {}).get("arn") != caller or "errorCode" in d):
        return {"outcome": "out_of_scope"}
    outcome = "already_compliant"
    if d.get("eventSource") == "s3.amazonaws.com" and d.get("eventName") == S3_BPA_EVENT:
        if p.get("bucketName") != BUCKET:
            return {"outcome": "out_of_scope"}
        resource = BUCKET
        settings = s3.get_public_access_block(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID)["PublicAccessBlockConfiguration"]
        desired = {k: True for k in ("BlockPublicAcls", "IgnorePublicAcls",
                                    "BlockPublicPolicy", "RestrictPublicBuckets")}
        if not all(settings.get(k) for k in desired):
            s3.put_public_access_block(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID,
                                      PublicAccessBlockConfiguration=desired)
            outcome = "bucket_protection_restored"
    elif d.get("eventSource") == "sqs.amazonaws.com" and d.get("eventName") == "SetQueueAttributes":
        url = sqs.get_queue_url(QueueName=QUEUE, QueueOwnerAWSAccountId=ACCOUNT_ID)["QueueUrl"]
        if p.get("queueUrl") != url:
            return {"outcome": "out_of_scope"}
        resource = QUEUE
        attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=[
            "QueueArn", "Policy", "SqsManagedSseEnabled", "KmsMasterKeyId"])["Attributes"]
        if attrs.get("QueueArn") != QUEUE_ARN:
            return {"outcome": "out_of_scope"}
        # IAM independently enforces the queue's immutable ownership tags.
        policy = json.loads(attrs.get("Policy") or '{"Version":"2012-10-17","Statement":[]}')
        statements = policy.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        def exercise_public(s):
            principal = s.get("Principal")
            actions = s.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            return (s.get("Sid") == "WorkshopPublicSend" and s.get("Effect") == "Allow"
                    and (principal == "*" or principal == {"AWS": "*"})
                    and "sqs:SendMessage" in actions and s.get("Resource") == QUEUE_ARN)
        kept = [s for s in statements if not exercise_public(s)]
        changes = {}
        if len(kept) != len(statements):
            policy["Statement"] = kept
            changes["Policy"] = json.dumps(policy)
        if attrs.get("SqsManagedSseEnabled") != "true" and not attrs.get("KmsMasterKeyId"):
            changes["SqsManagedSseEnabled"] = "true"
        if changes:
            sqs.set_queue_attributes(QueueUrl=url, Attributes=changes)
            outcome = "queue_repair_requested"
    else:
        return {"outcome": "unsupported_event"}
    result = {"event_id": event.get("id"), "resource": resource, "outcome": outcome}
    print(json.dumps(result))
    return result
```

## 5. Connect EventBridge to your function

1. Open **Amazon EventBridge → Rules → Create rule**. Use the **default event bus** and an **event-pattern rule**, not a schedule.
2. Name it with your username prefix as shown below. Use the Advanced Builder/custom JSON pattern editor if needed.
3. Paste the pattern below; replace `ACCOUNT_ID` and `user01`. For Storage, also replace `S3_BPA_EVENT` with the instructor's observed event name.
4. Choose target **AWS service → Lambda function → user01-Remediator**.
5. For target permissions, choose **Use existing role → user01-EventRole**. Pass the **entire matched event**, with no input transformation.
6. If the wizard proposes creating a role or adding a Lambda resource policy, choose the existing-role option. If that option is unavailable, ask the instructor; do not request broader permissions.
7. Add the mandatory Workshop/Owner tags if the rule creation form supports them. Review and enable the rule.

The caller filter excludes repairs made by the Lambda role, helping prevent loops. `errorCode` filtering ignores unsuccessful API calls. The handler repeats scope checks and reads current state because events can be duplicated or delayed.
Create rule **`user01-Storage`**. This rule routes both S3 and SQS API events to one function. Its `$or` branches pair each event name with the correct service. Test it against the instructor’s sample events.

```json
{
  "detail-type": [
    "AWS API Call via CloudTrail"
  ],
  "account": [
    "ACCOUNT_ID"
  ],
  "region": [
    "us-east-1"
  ],
  "detail": {
    "errorCode": [
      {
        "exists": false
      }
    ],
    "userIdentity": {
      "arn": [
        "arn:aws:iam::ACCOUNT_ID:user/workshop/user01"
      ]
    }
  },
  "$or": [
    {
      "source": [
        "aws.s3"
      ],
      "detail": {
        "eventSource": [
          "s3.amazonaws.com"
        ],
        "eventName": [
          "S3_BPA_EVENT"
        ]
      }
    },
    {
      "source": [
        "aws.sqs"
      ],
      "detail": {
        "eventSource": [
          "sqs.amazonaws.com"
        ],
        "eventName": [
          "SetQueueAttributes"
        ]
      }
    }
  ]
}
```

## 6. Run the exercises, one at a time


### Exercise 8 — Bucket Block Public Access

1. Open your bucket → **Permissions → Block public access → Edit**.
2. Disable the bucket-level settings, save and acknowledge the confirmation.
3. Refresh: all four settings should return to enabled. Account-level protection stays enabled throughout.

### Exercise 9 — Public SQS SendMessage policy

1. Open your queue → **Edit → Access policy**.
2. Preserve its existing policy. Add the following object to its `Statement` array, replacing the account ID and username:

```json
{
  "Sid": "WorkshopPublicSend",
  "Effect": "Allow",
  "Principal": "*",
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:us-east-1:ACCOUNT_ID:user01-Queue"
}
```

3. Save while keeping encryption enabled. Do not send messages or disable encryption to test anonymous access; this exercise detects the policy configuration itself.
4. Refresh: **WorkshopPublicSend** should be removed and the original policy statements preserved. If repair fails, remove this statement manually immediately.

### Exercise 10 — Queue encryption

1. Open your queue → **Edit → Encryption**; disable server-side encryption and save.
2. Refresh: encryption should return to enabled with **Amazon SQS key (SSE-SQS)**.
3. Allow for SQS attribute propagation before judging the result. No KMS key is needed.

## 7. Verify and record evidence

For **each** exercise:

1. Refresh the resource configuration until the expected compliant state appears. Event delivery and attribute propagation are asynchronous; do not assume immediate repair.
2. Open your function's **Monitor → View CloudWatch logs**, or your pre-created `/aws/lambda/user01-Remediator` log group in CloudWatch. Find the event ID, resource and outcome.
3. Save a screenshot of the compliant state and a sanitized log entry. Do not include passwords, access-key secrets or entire IAM events.
4. With the instructor's sanitized EventBridge event, use **Lambda → Test → Create new event**. Keep its full EventBridge envelope and your own caller/resource values. Invoke it again after repair; expect `already_compliant` and no further writes.
5. Record the event name, resource identifier, repair result and duplicate/no-op result.

A logged `repair_requested` is not proof of completion: confirm the resource state separately. If no log arrives, check the enabled rule, exact caller ARN, account/Region, target and existing event role. Ask the instructor to verify active CloudTrail management-event logging. Students do not need permission to configure a trail or inspect every account event.

If logs show `AccessDenied`, check assigned names, creation tags and role selection. Do not remove a boundary or loosen an SCP. If the function reports missing event fields, show the instructor a sanitized event so its actual shape can be checked.

With shared concurrency, short delays may occur when many students test at once. Trigger one change, verify it, then move to the next. Ask the instructor to inspect **Errors, Throttles and Duration** if delays persist.
## 8. Finish and clean up

1. Disable your EventBridge rules first. Keep them disabled during cleanup.
2. Save your evidence and code. Restore any remaining exercise misconfiguration manually if remediation failed.
3. Remove only your allowed exercise resources, following the group notes below.
4. Notify the instructor. The instructor removes functions, log groups, protected IAM targets, participant identities, roles and policies; students cannot delete/recreate their Lambda functions.

After disabling the rule, restore the original private queue policy and encryption if necessary. Delete your empty queue and bucket. If the console needs an unrelated denied API, ask the instructor to perform cleanup without broadening your permissions.
## References

- https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-create-tag.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/configuring-block-public-access-bucket.html
- https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-add-permissions.html
- https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-sqs-sse-queue.html
- https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-create-pattern-operators.html
