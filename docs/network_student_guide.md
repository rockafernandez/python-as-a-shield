# Network group — Python remediation workshop

For students `user01`–`user10` in the **network account**. Follow only this group guide.

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

## 3. Create your security group and subnet

The instructor supplies the network account ID, workshop VPC ID and approved CIDR. The VPC already exists; students create the SG and subnet.

1. Open **VPC → Security groups → Create security group**. Name it `user01-SG`, add a description, select the workshop VPC and add both mandatory tags. Leave inbound rules empty; keep default outbound rules.
2. Record the new `sg-...` ID. Do not add tags to individual SG rules; rule tagging is not granted.
3. Open **VPC → Subnets → Create subnet**. Select the workshop VPC, an instructor-approved Availability Zone and your assigned CIDR. Name it `user01-Subnet`; include both mandatory tags. Create only one subnet in this request.
4. Record the `subnet-...` ID. Leave automatic public IPv4 assignment disabled initially.

Default example CIDRs are below. **The instructor's actual configuration overrides this table.** Do not reuse another student's range.

| Student | Example subnet CIDR |
|---|---|
| user01 | 10.90.1.0/24 |
| user02 | 10.90.2.0/24 |
| user03 | 10.90.3.0/24 |
| user04 | 10.90.4.0/24 |
| user05 | 10.90.5.0/24 |
| user06 | 10.90.6.0/24 |
| user07 | 10.90.7.0/24 |
| user08 | 10.90.8.0/24 |
| user09 | 10.90.9.0/24 |
| user10 | 10.90.10.0/24 |

Do not create instances, internet gateways, routes or NAT gateways. The lab uses configuration changes, with no servers attached.

## 4. Deploy the group remediation code

Set `OWNER`, `ACCOUNT_ID` and `VPC_ID` at the top. The three SG cases share one branch because they produce the same API event. This code removes public IPv4 ingress for TCP ranges covering SSH/RDP, and all-protocol public rules. It preserves unrelated rules. IPv6 public access and other services are outside these exercises.

```python
import json
import boto3

OWNER = "user01"
ACCOUNT_ID = "REPLACE_NETWORK_ACCOUNT_ID"
VPC_ID = "REPLACE_WORKSHOP_VPC_ID"
ec2 = boto3.client("ec2", region_name="us-east-1")


def owned(resource):
    tags = {t["Key"]: t["Value"] for t in resource.get("Tags", [])}
    return (resource.get("VpcId") == VPC_ID
            and tags.get("Workshop") == "true" and tags.get("Owner") == OWNER)


def lambda_handler(event, context):
    d = event.get("detail", {})
    caller = f"arn:aws:iam::{ACCOUNT_ID}:user/workshop/{OWNER}"
    if (event.get("account") != ACCOUNT_ID or event.get("region") != "us-east-1"
            or d.get("eventSource") != "ec2.amazonaws.com"
            or d.get("userIdentity", {}).get("arn") != caller or "errorCode" in d):
        return {"outcome": "out_of_scope"}
    p = d.get("requestParameters") or {}
    name = d.get("eventName")
    if name == "AuthorizeSecurityGroupIngress":
        resource_id = p.get("groupId")
        if not resource_id:
            return {"outcome": "missing_group_id"}
        sg = ec2.describe_security_groups(GroupIds=[resource_id])["SecurityGroups"][0]
        if not owned(sg):
            return {"outcome": "out_of_scope"}
        removed = 0
        pager = ec2.get_paginator("describe_security_group_rules")
        for page in pager.paginate(Filters=[{"Name": "group-id", "Values": [resource_id]}]):
            for rule in page["SecurityGroupRules"]:
                if rule["IsEgress"] or rule.get("CidrIpv4") != "0.0.0.0/0":
                    continue
                risky = rule["IpProtocol"] == "-1" or (
                    rule["IpProtocol"] in ("tcp", "6") and any(
                        rule.get("FromPort", -1) <= port <= rule.get("ToPort", -1)
                        for port in (22, 3389)))
                if risky:
                    ec2.revoke_security_group_ingress(
                        GroupId=resource_id, SecurityGroupRuleIds=[rule["SecurityGroupRuleId"]])
                    removed += 1
        outcome = f"removed_{removed}_rules" if removed else "already_compliant"
    elif name == "ModifySubnetAttribute":
        resource_id = p.get("subnetId")
        if not resource_id:
            return {"outcome": "missing_subnet_id"}
        subnet = ec2.describe_subnets(SubnetIds=[resource_id])["Subnets"][0]
        if not owned(subnet):
            return {"outcome": "out_of_scope"}
        if subnet["MapPublicIpOnLaunch"]:
            ec2.modify_subnet_attribute(SubnetId=resource_id,
                                       MapPublicIpOnLaunch={"Value": False})
            outcome = "repair_requested"
        else:
            outcome = "already_compliant"
    else:
        return {"outcome": "unsupported_event"}
    result = {"event_id": event.get("id"), "resource": resource_id, "outcome": outcome}
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
Create rule **`user01-Network`**. One rule can route this group’s API events to one function.

```json
{
  "source": [
    "aws.ec2"
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
      "ec2.amazonaws.com"
    ],
    "eventName": [
      "AuthorizeSecurityGroupIngress",
      "ModifySubnetAttribute"
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


### Exercise 1 — Public SSH

1. Select your SG → **Inbound rules → Edit inbound rules → Add rule**.
2. Choose SSH/TCP port **22**, source IPv4 **0.0.0.0/0**. Save without rule tags.
3. Refresh: the public SSH rule should disappear. Expect `removed_1_rules` if it was the only offending rule.

### Exercise 2 — Public RDP

1. Add TCP port **3389**, source **0.0.0.0/0**, to the same SG.
2. Save, then confirm the rule is removed.

### Exercise 3 — All-protocol public ingress

1. Add **All traffic**, source **0.0.0.0/0**.
2. Save, then confirm that rule is removed. Do not attach this SG to a workload.

### Exercise 4 — Subnet automatic public IPv4

1. Select your subnet → **Actions → Edit subnet settings**.
2. Enable **auto-assign public IPv4 address** and save.
3. Refresh and confirm the setting becomes disabled. It changes the subnet default; no instance or billable public IP is created.

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

After disabling rules, delete your empty subnet and your unused SG. Keep the workshop VPC intact.
## References

- https://docs.aws.amazon.com/vpc/latest/userguide/create-subnets.html
- https://docs.aws.amazon.com/boto3/latest/reference/services/ec2/client/revoke_security_group_ingress.html
- https://docs.aws.amazon.com/boto3/latest/reference/services/ec2/client/modify_subnet_attribute.html
