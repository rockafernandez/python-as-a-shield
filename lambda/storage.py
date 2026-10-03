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
