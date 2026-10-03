# Identity group — Python remediation workshop

For students `user01`–`user10` in the **identity account**. Follow only this group guide.

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

## 3. Create your inert IAM test user

Your console login is `user01`; your exercise target is **a different user**, `Workshop-Target-01`. Never apply exercise policies to your console login.

1. Open **IAM → Users → Create user**. Enter `Workshop-Target-01`, replacing `01` with your participant number.
2. Leave **Provide user access to the AWS Management Console** unchecked.
3. Choose direct policy attachment but select no permissions policies initially.
4. Select the existing permissions boundary **Workshop-Target-DenyAll**.
5. Include `Workshop=true` and `Owner=user01` before submitting creation. Use root path `/`.
6. Review and create. Confirm the deny-all boundary remains attached.

If tags or the boundary can only be added after creation in your console flow, ask the instructor for help. They must be included in the CreateUser request. Do not create a new role, group or boundary.

The deny-all boundary prevents the target's policies and access keys from authorizing AWS actions. Your participant login still has its own restricted workshop permissions.

## 4. Deploy the group remediation code

Set `OWNER`, `NUMBER` and `ACCOUNT_ID`. Keep the inline exercise name **WorkshopWildcardExercise**. The code verifies tags and the exact deny-all boundary, then modifies only your target and the specific exercise policy/key. It leaves other inline policies untouched. It recognizes the literal wildcard exercise, not every possible excessive-permission policy.

```python
import json
from urllib.parse import unquote
import boto3

OWNER = "user01"
NUMBER = "01"
ACCOUNT_ID = "REPLACE_IDENTITY_ACCOUNT_ID"
TARGET = f"Workshop-Target-{NUMBER}"
INLINE_POLICY = "WorkshopWildcardExercise"
ADMIN = "arn:aws:iam::aws:policy/AdministratorAccess"
iam = boto3.client("iam")


def lambda_handler(event, context):
    d = event.get("detail", {})
    p = d.get("requestParameters") or {}
    caller = f"arn:aws:iam::{ACCOUNT_ID}:user/workshop/{OWNER}"
    if (event.get("account") != ACCOUNT_ID or event.get("region") != "us-east-1"
            or d.get("eventSource") != "iam.amazonaws.com"
            or d.get("userIdentity", {}).get("arn") != caller
            or "errorCode" in d or p.get("userName") != TARGET):
        return {"outcome": "out_of_scope"}
    user = iam.get_user(UserName=TARGET)["User"]
    tags = {t["Key"]: t["Value"] for t in iam.list_user_tags(UserName=TARGET)["Tags"]}
    boundary = f"arn:aws:iam::{ACCOUNT_ID}:policy/workshop/Workshop-Target-DenyAll"
    if (tags.get("Workshop") != "true" or tags.get("Owner") != OWNER
            or user.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn") != boundary):
        raise ValueError("Target ownership or deny-all boundary mismatch")
    name = d.get("eventName")
    outcome = "already_compliant"
    if name == "AttachUserPolicy":
        if p.get("policyArn") != ADMIN:
            return {"outcome": "out_of_scope"}
        policies = []
        for page in iam.get_paginator("list_attached_user_policies").paginate(UserName=TARGET):
            policies.extend(page["AttachedPolicies"])
        if any(x["PolicyArn"] == ADMIN for x in policies):
            iam.detach_user_policy(UserName=TARGET, PolicyArn=ADMIN)
            outcome = "admin_policy_detached"
    elif name == "PutUserPolicy":
        if p.get("policyName") != INLINE_POLICY:
            return {"outcome": "out_of_scope"}
        try:
            doc = iam.get_user_policy(UserName=TARGET, PolicyName=INLINE_POLICY)["PolicyDocument"]
        except iam.exceptions.NoSuchEntityException:
            doc = {}
        if isinstance(doc, str):
            doc = json.loads(unquote(doc))
        statements = doc.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        def wildcard(value):
            return value == "*" or isinstance(value, list) and "*" in value
        if any(s.get("Effect") == "Allow" and wildcard(s.get("Action"))
               and wildcard(s.get("Resource")) for s in statements):
            iam.delete_user_policy(UserName=TARGET, PolicyName=INLINE_POLICY)
            outcome = "exercise_policy_deleted"
    elif name == "CreateAccessKey":
        key_id = ((d.get("responseElements") or {}).get("accessKey") or {}).get("accessKeyId")
        if not key_id:
            return {"outcome": "missing_key_id"}
        keys = iam.list_access_keys(UserName=TARGET)["AccessKeyMetadata"]
        if any(k["AccessKeyId"] == key_id and k["Status"] == "Active" for k in keys):
            iam.update_access_key(UserName=TARGET, AccessKeyId=key_id, Status="Inactive")
            outcome = "key_deactivated"
    else:
        return {"outcome": "unsupported_event"}
    result = {"event_id": event.get("id"), "resource": TARGET, "outcome": outcome}
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
Create rule **`user01-Identity`**. One rule can route this group’s API events to one function.

```json
{
  "source": [
    "aws.iam"
  ],
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
    "eventSource": [
      "iam.amazonaws.com"
    ],
    "eventName": [
      "AttachUserPolicy",
      "PutUserPolicy",
      "CreateAccessKey"
    ],
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
  }
}
```

## 6. Run the exercises, one at a time


### Exercise 5 — AdministratorAccess attachment

1. Open your **test target** → Permissions → Add permissions → Attach policies directly.
2. Select **AdministratorAccess** and attach it. Keep the deny-all boundary.
3. Refresh: AdministratorAccess should be detached automatically. The boundary remains.

### Exercise 6 — Wildcard inline policy

1. On your test target, create an inline policy using the JSON editor:

```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"*","Resource":"*"}]}
```

2. Name it exactly **WorkshopWildcardExercise** and save.
3. Refresh: that inline policy should disappear. The code removes this entire named exercise policy, so do not add unrelated statements to it.

### Exercise 7 — Access-key creation

1. Open your test target → **Security credentials → Create access key**. Select the appropriate test use-case option and acknowledge the prompt if required.
2. Create the key. Do not download, copy, use or distribute its secret.
3. Return to the target's key list. Confirm the new key becomes **Inactive**.
4. Delete the inactive test key after recording evidence. IAM permits at most two keys per user; do not accumulate them.

The key belongs to the inert target, not your participant login. The code uses the new key ID from the event and deactivates only that key.

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

Delete your test keys and remove any remaining exercise policies after disabling the rule. Do not remove the boundary. Ask the instructor to delete the target user; student target deletion is denied.
## References

- https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html
- https://docs.aws.amazon.com/IAM/latest/APIReference/API_CreateUser.html
- https://docs.aws.amazon.com/boto3/latest/reference/services/iam/client/update_access_key.html
