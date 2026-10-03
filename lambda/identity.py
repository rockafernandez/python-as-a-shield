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
