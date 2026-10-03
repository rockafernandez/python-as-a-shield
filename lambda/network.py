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
