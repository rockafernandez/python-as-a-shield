#!/usr/bin/env python3
"""Provision 30 workshop participants, scoped roles, console logins and a CSV.
Python 3.10+, boto3. Read-only preflight by default; --apply enables provisioning.
See workshop_setup.md. No AWS credentials are embedded in this script.
"""
import argparse
import csv
import ipaddress
import json
import os
import re
import secrets
import string
from pathlib import Path

VERSION = '2012-10-17'
LAMBDA_ACTIONS = ['lambda:CreateFunction', 'lambda:GetFunction', 'lambda:GetFunctionConfiguration',
                  'lambda:UpdateFunctionCode', 'lambda:UpdateFunctionConfiguration',
                  'lambda:InvokeFunction', 'lambda:GetPolicy', 'lambda:TagResource',
                  'lambda:ListTags', 'lambda:GetFunctionConcurrency']
RULE_ACTIONS = ['events:PutRule', 'events:DescribeRule', 'events:EnableRule', 'events:DisableRule',
                'events:RemoveTargets', 'events:ListTargetsByRule', 'events:DeleteRule',
                'events:TagResource', 'events:ListTagsForResource']
DENY_ALL = {'Version': VERSION, 'Statement': [{'Effect': 'Deny', 'Action': '*', 'Resource': '*'}]}


def allow(actions, resource, condition=None):
    s = {'Effect': 'Allow', 'Action': actions, 'Resource': resource}
    if condition:
        s['Condition'] = condition
    return s


def bounded(statements):
    """Compact allowlist plus explicit resource/condition denies; used as boundary."""
    actions = sorted({a for stmt in statements for a in stmt['Action']})
    result = [allow(['*'], '*'), {'Effect': 'Deny', 'NotAction': actions, 'Resource': '*'}]
    by_action = {}
    for stmt in statements:
        resources = stmt['Resource'] if isinstance(stmt['Resource'], list) else [stmt['Resource']]
        for action in stmt['Action']:
            by_action.setdefault(action, set()).update(resources)
    groups = {}
    for action, resources in by_action.items():
        if '*' not in resources:
            groups.setdefault(tuple(sorted(resources)), []).append(action)
    for resources, acts in groups.items():
        result.append({'Effect': 'Deny', 'Action': acts, 'NotResource': list(resources)})
    inverse = {'StringEquals': 'StringNotEquals', 'ArnEquals': 'ArnNotEquals',
               'ArnLike': 'ArnNotLike', 'ForAllValues:ArnEquals': 'ForAnyValue:ArnNotEquals',
               'ForAllValues:StringEquals': 'ForAnyValue:StringNotEquals'}
    guards = {}
    for stmt in statements:
        for op, keys in stmt.get('Condition', {}).items():
            for key, value in keys.items():
                if op == 'Null':
                    inverted, expected = 'Null', 'true' if value == 'false' else 'false'
                else:
                    inverted, expected = inverse[op], value
                deny = {'Effect': 'Deny', 'Resource': stmt['Resource'],
                        'Condition': {inverted: {key: expected}}}
                identity = json.dumps(deny, sort_keys=True)
                guards.setdefault(identity, (deny, set()))[1].update(stmt['Action'])
    for deny, acts in guards.values():
        deny['Action'] = sorted(acts)
        result.append(deny)
    # IAM accepts scalar singleton actions/resources; save quota without changing scope.
    for stmt in result:
        for key in ('Action', 'Resource', 'NotResource'):
            if isinstance(stmt.get(key), list) and len(stmt[key]) == 1:
                stmt[key] = stmt[key][0]
    return {'Version': VERSION, 'Statement': result}

def names(entry, number):
    account, region = entry['account_id'], entry['region']
    username = entry['students'][number - 1]['username']
    prefix = username
    return {
        'user': username,
        'user_arn': f'arn:aws:iam::{account}:user/workshop/{username}',
        'function': prefix + '-Remediator',
        'function_arn': f'arn:aws:lambda:{region}:{account}:function:{prefix}-Remediator',
        'rule_arn': f'arn:aws:events:{region}:{account}:rule/{prefix}-*',
        'lambda_role': prefix + '-LambdaRole',
        'lambda_role_arn': f'arn:aws:iam::{account}:role/workshop-execution/{prefix}-LambdaRole',
        'event_role': prefix + '-EventRole',
        'event_role_arn': f'arn:aws:iam::{account}:role/workshop-execution/{prefix}-EventRole',
        'log_group': f'/aws/lambda/{prefix}-Remediator',
        'log_arn': f'arn:aws:logs:{region}:{account}:log-group:/aws/lambda/{prefix}-Remediator',
        'bucket': f'workshop-{account}-student-{number:02d}-pythonshield',
        'queue': prefix + '-Queue',
        'target': f'Workshop-Target-{number:02d}',
        # Root path allows creation through the IAM console, which cannot set paths.
        'target_arn': f'arn:aws:iam::{account}:user/Workshop-Target-{number:02d}',
        'target_boundary_arn': f'arn:aws:iam::{account}:policy/workshop/Workshop-Target-DenyAll',
    }


def exercise_statements(entry, number, runtime=False):
    n = names(entry, number)
    account, region, kind = entry['account_id'], entry['region'], entry['kind']
    request_tags = {'StringEquals': {'aws:RequestTag/Workshop': 'true', 'aws:RequestTag/Owner': n['user']}}
    existing_tags = {'StringEquals': {'aws:ResourceTag/Workshop': 'true', 'aws:ResourceTag/Owner': n['user']}}
    if kind == 'network':
        sg = f'arn:aws:ec2:{region}:{account}:security-group/*'
        subnet = f'arn:aws:ec2:{region}:{account}:subnet/*'
        vpc = f'arn:aws:ec2:{region}:{account}:vpc/{entry["workshop_vpc_id"]}'
        owned_subnet = {**existing_tags, 'ArnEquals': {'ec2:Vpc': vpc}}
        # EC2 authorizes group creation on BOTH the new SG and the existing VPC.
        # Request-tag conditions apply only to the SG resource, not the VPC.
        operations = ['ec2:RevokeSecurityGroupIngress'] if runtime else [
            'ec2:AuthorizeSecurityGroupIngress', 'ec2:RevokeSecurityGroupIngress', 'ec2:DeleteSecurityGroup']
        rules = [allow(['ec2:DescribeSecurityGroups', 'ec2:DescribeSecurityGroupRules', 'ec2:DescribeSubnets', 'ec2:DescribeVpcs', 'ec2:DescribeAvailabilityZones'], '*'),
                 allow(operations, sg, existing_tags),
                 allow(['ec2:ModifySubnetAttribute'] if runtime else ['ec2:ModifySubnetAttribute', 'ec2:DeleteSubnet'],
                       subnet, owned_subnet)]
        if not runtime:
            # Each create API authorizes its own new resource type and the VPC.
            # The tagging SCP independently pairs each type with its CreateAction.
            rules += [allow(['ec2:CreateSecurityGroup', 'ec2:CreateSubnet'], [sg, subnet], request_tags),
                      allow(['ec2:CreateSecurityGroup', 'ec2:CreateSubnet'], vpc),
                      allow(['ec2:CreateTags'], [sg, subnet], {'StringEquals': {
                          'ec2:CreateAction': ['CreateSecurityGroup', 'CreateSubnet'],
                          'aws:RequestTag/Workshop': 'true', 'aws:RequestTag/Owner': n['user']}})]
        return rules
    if kind == 'identity':
        key_actions = ['iam:ListAccessKeys', 'iam:UpdateAccessKey', 'iam:DeleteAccessKey']
        if not runtime:
            key_actions.append('iam:CreateAccessKey')
        rules = [allow(['iam:GetUser', 'iam:ListAttachedUserPolicies', 'iam:ListUserPolicies', 'iam:GetUserPolicy', 'iam:ListUserTags'], n['target_arn']),
                allow(['iam:DetachUserPolicy'] if runtime else ['iam:AttachUserPolicy', 'iam:DetachUserPolicy'], n['target_arn'],
                      {'ArnEquals': {'iam:PolicyARN': 'arn:aws:iam::aws:policy/AdministratorAccess'}}),
                allow(['iam:PutUserPolicy', 'iam:DeleteUserPolicy'], n['target_arn']),
                allow(key_actions, n['target_arn'])]
        if not runtime:
            rules += [allow(['iam:CreateUser'], n['target_arn'], {'StringEquals': {
                          **request_tags['StringEquals'], 'iam:PermissionsBoundary': n['target_boundary_arn']}}),
                      allow(['iam:TagUser'], n['target_arn'], request_tags),
                      allow(['iam:GetPolicy', 'iam:GetPolicyVersion', 'iam:ListPolicyVersions'], n['target_boundary_arn'])]
        return rules
    if kind == 'storage':
        bucket = f'arn:aws:s3:::{n["bucket"]}'
        queue = f'arn:aws:sqs:{region}:{account}:{n["queue"]}'
        bucket_actions = ['s3:GetBucketPublicAccessBlock', 's3:PutBucketPublicAccessBlock']
        queue_actions = ['sqs:GetQueueAttributes', 'sqs:SetQueueAttributes', 'sqs:GetQueueUrl']
        if not runtime:
            bucket_actions += ['s3:GetBucketLocation', 's3:DeleteBucket', 's3:ListTagsForResource']
            queue_actions += ['sqs:DeleteQueue', 'sqs:ListQueueTags']
        # S3 access is enforced by exact name + account ownership, not S3 ABAC.
        rules = [allow(bucket_actions, bucket, {'StringEquals': {'s3:ResourceAccount': account}}),
                 allow(queue_actions, queue, existing_tags)]
        if not runtime:
            rules += [allow(['s3:CreateBucket', 's3:TagResource'], bucket, request_tags),
                      allow(['sqs:CreateQueue', 'sqs:TagQueue'], queue, request_tags),
                      allow(['s3:ListAllMyBuckets', 'sqs:ListQueues'], '*')]
        return rules
    raise ValueError('Unsupported account kind')

def policies(entry, number, include_access=False):
    n = names(entry, number)
    s = exercise_statements(entry, number)
    s += [allow(['iam:ChangePassword', 'iam:GetUser'], n['user_arn']),
          allow(['iam:GetAccountPasswordPolicy', 'iam:ListRoles'], '*'),
          allow(['iam:GetRole'], [n['lambda_role_arn'], n['event_role_arn']]),
          allow(['iam:PassRole'], n['lambda_role_arn'], {'StringEquals': {'iam:PassedToService': 'lambda.amazonaws.com'}}),
          allow(['iam:PassRole'], n['event_role_arn'], {'StringEquals': {'iam:PassedToService': 'events.amazonaws.com'}}),
          allow(LAMBDA_ACTIONS, n['function_arn']),
          allow(['lambda:ListFunctions', 'lambda:GetAccountSettings', 'events:TestEventPattern', 'events:ListRules', 'events:ListEventBuses', 'logs:DescribeLogGroups'], '*'),
          allow(RULE_ACTIONS, n['rule_arn']),
          allow(['events:PutTargets'], n['rule_arn'],
                {'ForAllValues:ArnEquals': {'events:TargetArn': [n['function_arn']]},
                 'Null': {'events:TargetArn': 'false'}}),
          allow(['events:DescribeEventBus'], f'arn:aws:events:{entry["region"]}:{entry["account_id"]}:event-bus/default'),
          allow(['logs:DescribeLogStreams', 'logs:GetLogEvents', 'logs:FilterLogEvents'], n['log_arn'] + ':*')]
    if entry['kind'] == 'identity':
        s += [allow(['iam:ListUsers', 'iam:ListPolicies'], '*'),
              allow(['iam:GetPolicy'], 'arn:aws:iam::aws:policy/AdministratorAccess')]
    user = bounded(s)
    runtime = bounded(exercise_statements(entry, number, runtime=True) + [
        allow(['logs:CreateLogStream', 'logs:PutLogEvents'], n['log_arn'] + ':*')])
    # Event role gets only InvokeFunction; it cannot read or change resources.
    invoker = bounded([allow(['lambda:InvokeFunction'], n['function_arn'])])
    if include_access:
        return user, runtime, invoker, {'Version': VERSION, 'Statement': s}
    return user, runtime, invoker


def example():
    result = {'management_account_id': 'REPLACE_MANAGEMENT_ID', 'accounts': []}
    for kind in ('network', 'identity', 'storage'):
        students = [{'username': f'user{i:02d}', **({'subnet_cidr': f'10.90.{i}.0/24'}
                    if kind == 'network' else {})} for i in range(1, 11)]
        entry = {'kind': kind, 'profile': f'workshop-{kind}',
                 'account_id': 'REPLACE_ACCOUNT_ID', 'region': 'us-east-1',
                 'instructor_role_arn': 'arn:aws:iam::REPLACE_ACCOUNT_ID:role/REPLACE_EXACT_FEDERATED_ROLE_PATH_AND_NAME',
                 'students': students}
        if kind == 'network':
            entry['workshop_vpc_id'] = 'REPLACE_VPC_ID'
        result['accounts'].append(entry)
    return result

def scp(config):
    instructors = [e['instructor_role_arn'] for e in config['accounts']]
    region = config['accounts'][0]['region']
    principals = ['arn:aws:iam::*:user/workshop/*',
                  'arn:aws:iam::*:role/workshop-execution/*']
    protected = ['arn:aws:iam::*:user/workshop/*', 'arn:aws:iam::*:role/workshop-execution/*',
                 'arn:aws:iam::*:policy/workshop/*', 'arn:aws:iam::*:policy/workshop-execution/*',
                 *instructors]
    not_instructor = {'ArnNotEquals': {'aws:PrincipalArn': instructors}}
    return {'Version': VERSION, 'Statement': [
        {'Sid': 'NeverLeaveOrganization', 'Effect': 'Deny', 'Action': 'organizations:LeaveOrganization', 'Resource': '*'},
        {'Sid': 'ProtectAuditUnlessInstructor', 'Effect': 'Deny',
         'Action': ['cloudtrail:StopLogging', 'cloudtrail:DeleteTrail', 'cloudtrail:UpdateTrail', 'cloudtrail:PutEventSelectors'],
         'Resource': '*', 'Condition': not_instructor},
        {'Sid': 'ProtectWorkshopIAMUnlessInstructor', 'Effect': 'Deny',
         'Action': ['iam:DeleteUser', 'iam:CreateAccessKey', 'iam:CreateLoginProfile', 'iam:UpdateLoginProfile',
                    'iam:DeleteLoginProfile', 'iam:AttachUserPolicy', 'iam:DetachUserPolicy', 'iam:PutUserPolicy',
                    'iam:DeleteUserPolicy', 'iam:PutUserPermissionsBoundary', 'iam:DeleteUserPermissionsBoundary',
                    'iam:DeleteRole', 'iam:UpdateAssumeRolePolicy', 'iam:AttachRolePolicy', 'iam:DetachRolePolicy',
                    'iam:PutRolePolicy', 'iam:DeleteRolePolicy', 'iam:PutRolePermissionsBoundary',
                    'iam:DeleteRolePermissionsBoundary', 'iam:CreatePolicyVersion', 'iam:SetDefaultPolicyVersion',
                    'iam:DeletePolicyVersion', 'iam:DeletePolicy', 'iam:TagUser', 'iam:UntagUser',
                    'iam:TagRole', 'iam:UntagRole', 'iam:TagPolicy', 'iam:UntagPolicy'],
         'Resource': protected, 'Condition': not_instructor},
        {'Sid': 'KeepTestTargetsInert', 'Effect': 'Deny',
         'Action': ['iam:DeleteUser', 'iam:PutUserPermissionsBoundary', 'iam:DeleteUserPermissionsBoundary',
                    'iam:CreateLoginProfile', 'iam:UpdateLoginProfile'],
         'Resource': ['arn:aws:iam::*:user/Workshop-Target-*',
                      'arn:aws:iam::*:user/workshop-targets/Workshop-Target-*'], 'Condition': not_instructor},
        {'Sid': 'WorkshopServicesOnly', 'Effect': 'Deny',
         'NotAction': ['iam:*', 'lambda:*', 'events:*', 'logs:*', 'ec2:Describe*',
                       'ec2:AuthorizeSecurityGroupIngress', 'ec2:RevokeSecurityGroupIngress',
                       'ec2:ModifySubnetAttribute', 'ec2:CreateSubnet', 'ec2:DeleteSubnet',
                       'ec2:CreateSecurityGroup', 'ec2:CreateTags', 'ec2:DeleteSecurityGroup',
                       's3:GetBucket*', 's3:PutBucketPublicAccessBlock', 's3:CreateBucket', 's3:TagResource',
                       's3:ListTagsForResource', 's3:ListAllMyBuckets', 's3:DeleteBucket',
                       'sqs:GetQueue*', 'sqs:SetQueueAttributes', 'sqs:CreateQueue', 'sqs:TagQueue',
                       'sqs:ListQueueTags', 'sqs:ListQueues', 'sqs:DeleteQueue', 'sts:GetCallerIdentity'],
         'Resource': '*', 'Condition': {'ArnLike': {'aws:PrincipalArn': principals}}},
        {'Sid': 'NoExtraLambdaOrEventBridgeInfrastructure', 'Effect': 'Deny',
         'Action': ['lambda:AddPermission', 'lambda:PutResourcePolicy', 'lambda:CreateFunctionUrlConfig',
                    'lambda:UpdateFunctionUrlConfig', 'lambda:CreateEventSourceMapping',
                    'lambda:PutProvisionedConcurrencyConfig', 'lambda:PutFunctionConcurrency',
                    'lambda:DeleteFunctionConcurrency', 'lambda:DeleteFunction', 'lambda:PublishVersion',
                    'lambda:PublishLayerVersion', 'lambda:CreateAlias', 'lambda:CreateCapacityProvider',
                    'events:CreateEventBus', 'events:PutPermission', 'events:CreateApiDestination',
                    'events:CreateConnection', 'events:CreateArchive', 'events:StartReplay', 'logs:PutResourcePolicy'],
         'Resource': '*', 'Condition': {'ArnLike': {'aws:PrincipalArn': principals}}},
        {'Sid': 'WorkshopRegionOnly', 'Effect': 'Deny', 'NotAction': ['iam:*', 'sts:GetCallerIdentity'], 'Resource': '*',
         'Condition': {'ArnLike': {'aws:PrincipalArn': principals}, 'StringNotEquals': {'aws:RequestedRegion': region}}}
    ]}


def tagging_scp():
    principals = ['arn:aws:iam::*:user/workshop/*',
                  'arn:aws:iam::*:role/workshop-execution/*']
    who = {'ArnLike': {'aws:PrincipalArn': principals}}
    # Scope subnet/SG request-tag denies to the new resource, not the existing VPC.
    resources = ['arn:aws:ec2:*:*:security-group/*', 'arn:aws:ec2:*:*:subnet/*', 'arn:aws:s3:::*', 'arn:aws:sqs:*:*:*',
                 'arn:aws:iam::*:user/Workshop-Target-*']
    creation_and_tagging = ['ec2:CreateSecurityGroup', 'ec2:CreateSubnet', 'ec2:CreateTags', 's3:CreateBucket',
                           's3:TagResource', 'sqs:CreateQueue', 'sqs:TagQueue', 'iam:CreateUser', 'iam:TagUser']
    statements = []
    for key, expected in (('Workshop', 'true'), ('Owner', '${aws:PrincipalTag/Owner}')):
        statements.append({'Sid': 'Require' + key + 'OnCreationAndTagging', 'Effect': 'Deny',
                           'Action': creation_and_tagging, 'Resource': resources,
                           'Condition': {**who, 'StringNotEquals': {'aws:RequestTag/' + key: expected}}})
    statements.append({'Sid': 'RequirePrincipalOwner', 'Effect': 'Deny',
                       'Action': creation_and_tagging, 'Resource': resources,
                       'Condition': {**who, 'Null': {'aws:PrincipalTag/Owner': 'true'}}})
    # Removing either mandatory tag is forbidden. Legacy S3 tag replacement APIs
    # are deliberately unavailable, so students cannot remove tags through them.
    statements.append({'Sid': 'DoNotRemoveOrReplaceOwnershipTags', 'Effect': 'Deny',
                       'Action': ['ec2:DeleteTags', 's3:UntagResource', 's3:PutBucketTagging',
                                  'sqs:UntagQueue', 'iam:UntagUser'], 'Resource': '*', 'Condition': who})
    statements.append({'Sid': 'CreateTargetsWithDenyAllBoundary', 'Effect': 'Deny',
                       'Action': 'iam:CreateUser', 'Resource': 'arn:aws:iam::*:user/Workshop-Target-*',
                       'Condition': {**who, 'StringNotEquals': {'iam:PermissionsBoundary':
                           'arn:aws:iam::${aws:PrincipalAccount}:policy/workshop/Workshop-Target-DenyAll'}}})
    statements.append({'Sid': 'TagSecurityGroupsOnlyAtCreation', 'Effect': 'Deny',
                       'Action': 'ec2:CreateTags', 'Resource': 'arn:aws:ec2:*:*:security-group/*',
                       'Condition': {**who, 'StringNotEquals': {'ec2:CreateAction': 'CreateSecurityGroup'}}})
    statements.append({'Sid': 'TagSubnetsOnlyAtCreation', 'Effect': 'Deny',
                       'Action': 'ec2:CreateTags', 'Resource': 'arn:aws:ec2:*:*:subnet/*',
                       'Condition': {**who, 'StringNotEquals': {'ec2:CreateAction': 'CreateSubnet'}}})
    # Name restrictions for S3/SQS come from per-user explicit resource denies.
    # EC2 names cannot be used as IAM resource ARNs, so immutable Owner tags do it.
    for key, expected in (('Workshop', 'true'), ('Owner', '${aws:PrincipalTag/Owner}')):
        statements.append({'Sid': 'ManageOnlyMatching' + key, 'Effect': 'Deny',
                           'Action': ['ec2:AuthorizeSecurityGroupIngress', 'ec2:RevokeSecurityGroupIngress',
                                      'ec2:DeleteSecurityGroup', 'ec2:ModifySubnetAttribute', 'ec2:DeleteSubnet',
                                      'sqs:SetQueueAttributes', 'sqs:DeleteQueue'],
                           'Resource': ['arn:aws:ec2:*:*:security-group/*', 'arn:aws:ec2:*:*:subnet/*', 'arn:aws:sqs:*:*:*'],
                           'Condition': {**who, 'StringNotEquals': {'aws:ResourceTag/' + key: expected}}})
    return {'Version': VERSION, 'Statement': statements}


def verify_instructor(iam, caller, entry):
    prefix = f'arn:aws:sts::{entry["account_id"]}:assumed-role/'
    if caller['Account'] != entry['account_id'] or not caller['Arn'].startswith(prefix):
        raise ValueError('Profile must assume the configured federated IAM role in this member account')
    role_name = caller['Arn'][len(prefix):].split('/')[0]
    role = iam.get_role(RoleName=role_name)['Role']
    if role['Arn'] != entry['instructor_role_arn']:
        raise ValueError('Federated session does not match instructor_role_arn, including IAM path')
    if caller.get('UserId', '').split(':')[0] != role['RoleId']:
        raise ValueError('STS role identity does not match current IAM role identity')


def check_config(config):
    entries = config['accounts']
    if not re.fullmatch(r'\d{12}', config['management_account_id']):
        raise ValueError('Replace management account ID')
    if len(entries) != 3 or {e['kind'] for e in entries} != {'network', 'identity', 'storage'}:
        raise ValueError('Exactly one network, identity and storage account required')
    if len({e['account_id'] for e in entries}) != 3 or {e['region'] for e in entries} != {'us-east-1'}:
        raise ValueError('Three distinct member accounts in us-east-1 required')
    for entry in entries:
        account = entry['account_id']
        if not re.fullmatch(r'\d{12}', account) or account == config['management_account_id']:
            raise ValueError('Invalid or management account ID')
        arn = entry['instructor_role_arn']
        if not re.fullmatch(r'arn:aws:iam::' + account + r':role/[A-Za-z0-9_+=,.@/-]+', arn):
            raise ValueError('Use the exact IAM role ARN, with path; STS session ARNs and wildcards are prohibited')
        if '/workshop-execution/' in arn or arn.rsplit('/', 1)[-1].startswith('Workshop-Student-'):
            raise ValueError('A participant execution role cannot be an instructor exception')
        if len(entry['students']) != 10 or 'REPLACE' in json.dumps(entry):
            raise ValueError('Ten participant records per account, no placeholders')
        usernames = [item.get('username', '') for item in entry['students']]
        if not all(isinstance(name, str) for name in usernames) or len({name.lower() for name in usernames}) != 10 or not all(
                re.fullmatch(r'[A-Za-z0-9_+=,.@-]{1,64}', name) for name in usernames):
            raise ValueError('Provide ten unique valid IAM usernames per account, such as user01 through user10')
        if any(name.lower().startswith('workshop-target-') for name in usernames):
            raise ValueError('Participant usernames must not conflict with workshop test targets')
        if entry['kind'] == 'network':
            if not re.fullmatch(r'vpc-[0-9a-f]{8,17}', entry['workshop_vpc_id']):
                raise ValueError('Set workshop_vpc_id')
            blocks = [ipaddress.ip_network(item['subnet_cidr'], strict=True) for item in entry['students']]
            if not all(block.version == 4 and 16 <= block.prefixlen <= 28 for block in blocks):
                raise ValueError('Suggested subnet CIDRs must be canonical IPv4 blocks between /16 and /28')
            if any(a.overlaps(b) for i, a in enumerate(blocks) for b in blocks[i + 1:]):
                raise ValueError('Suggested student subnet CIDRs must not overlap')
        for i in range(1, 11):
            for policy in policies(entry, i, include_access=True):
                if len(json.dumps(policy, separators=(',', ':'))) > 6144:
                    raise ValueError('Generated managed policy exceeds 6144 characters')
    for policy in (scp(config), tagging_scp()):
        if len(json.dumps(policy, separators=(',', ':'))) > 5120:
            raise ValueError('Generated SCP exceeds conservative 5120-character threshold')

def absent(client, method, key, value):
    from botocore.exceptions import ClientError
    try:
        getattr(client, method)(**{key: value})
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'NoSuchEntity':
            return
        raise
    raise ValueError(f'Refusing existing resource: {value}; do not overwrite existing identities')


def validate_resources(session, entry):
    if entry['kind'] != 'network':
        return  # Exercise resources will be created by participants.
    ec2 = session.client('ec2')
    vpc = ec2.describe_vpcs(VpcIds=[entry['workshop_vpc_id']])['Vpcs'][0]
    tags = {tag['Key']: tag['Value'] for tag in vpc.get('Tags', [])}
    if vpc.get('OwnerId') != entry['account_id'] or vpc.get('IsDefault') or tags.get('Workshop') != 'true':
        raise ValueError('Use a dedicated non-default VPC owned by this account, tagged Workshop=true')
    ranges = [ipaddress.ip_network(item['CidrBlock']) for item in vpc['CidrBlockAssociationSet']
              if item['CidrBlockState']['State'] == 'associated']
    existing = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [entry['workshop_vpc_id']]}])['Subnets']
    # Suggested CIDRs are validated here, not enforceable by these IAM conditions.
    for item in entry['students']:
        block = ipaddress.ip_network(item['subnet_cidr'])
        if not any(block.subnet_of(vpc_range) for vpc_range in ranges):
            raise ValueError('Suggested subnet CIDR must be within an associated workshop VPC IPv4 range')
        if any(block.overlaps(ipaddress.ip_network(subnet['CidrBlock'])) for subnet in existing):
            raise ValueError('Suggested subnet CIDR overlaps an existing subnet; choose an unused block')

def policy_arn(account, name, path):
    return f'arn:aws:iam::{account}:policy{path}{name}'


def preflight(config):
    import boto3
    prepared = []
    for entry in config['accounts']:
        session = boto3.Session(profile_name=entry['profile'], region_name=entry['region'])
        caller = session.client('sts').get_caller_identity()
        iam, logs = session.client('iam'), session.client('logs')
        verify_instructor(iam, caller, entry)
        validate_resources(session, entry)
        if entry['kind'] == 'identity':
            absent(iam, 'get_policy', 'PolicyArn', policy_arn(entry['account_id'], 'Workshop-Target-DenyAll', '/workshop/'))
        for i in range(1, 11):
            n = names(entry, i)
            absent(iam, 'get_user', 'UserName', n['user'])
            for suffix in ('-Access', '-Boundary'):
                absent(iam, 'get_policy', 'PolicyArn', policy_arn(entry['account_id'], n['user'] + suffix, '/workshop/'))
            for role in (n['lambda_role'], n['event_role']):
                absent(iam, 'get_role', 'RoleName', role)
                absent(iam, 'get_policy', 'PolicyArn', policy_arn(entry['account_id'], role + '-Access', '/workshop-execution/'))
            if entry['kind'] == 'identity':
                absent(iam, 'get_user', 'UserName', n['target'])
            if logs.describe_log_groups(logGroupNamePrefix=n['log_group']).get('logGroups'):
                raise ValueError('Existing workshop log group; inspect before reuse')
            # Refuse adopting an existing function, even if its IAM role is absent.
            from botocore.exceptions import ClientError
            try:
                session.client('lambda').get_function(FunctionName=n['function'])
            except ClientError as exc:
                if exc.response['Error']['Code'] != 'ResourceNotFoundException':
                    raise
            else:
                raise ValueError('Existing participant function; inspect before reuse')
        try:
            password_policy = iam.get_account_password_policy()['PasswordPolicy']
        except iam.exceptions.NoSuchEntityException:
            password_policy = {}
        prepared.append((entry, session, max(32, password_policy.get('MinimumPasswordLength', 8))))
        print(f'Preflight OK: {entry["account_id"]} ({entry["kind"]})')
    return prepared


def create_role(iam, role_name, policy, trust, tags):
    arn = iam.create_policy(PolicyName=role_name + '-Access', Path='/workshop-execution/',
                            PolicyDocument=json.dumps(policy), Tags=tags)['Policy']['Arn']
    iam.create_role(RoleName=role_name, Path='/workshop-execution/',
                    AssumeRolePolicyDocument=json.dumps(trust), PermissionsBoundary=arn,
                    MaxSessionDuration=3600, Tags=tags)
    # The role receives enumerated actions; its immutable boundary supplies exact
    # resource and condition restrictions, including explicit denies.
    actions = next(stmt['NotAction'] for stmt in policy['Statement'] if 'NotAction' in stmt)
    iam.put_role_policy(RoleName=role_name, PolicyName='WorkshopPermissions',
                        PolicyDocument=json.dumps({'Version': VERSION, 'Statement': [allow(actions, '*')]}))


def service_trust(service, condition=None):
    stmt = {'Effect': 'Allow', 'Principal': {'Service': service}, 'Action': 'sts:AssumeRole'}
    if condition:
        stmt['Condition'] = condition
    return {'Version': VERSION, 'Statement': [stmt]}


def password(length):
    # Fixed safe first character avoids spreadsheet formula interpretation.
    chars = string.ascii_letters + string.digits + '!@#$%_-'
    return 'Aa9!' + ''.join(secrets.choice(chars) for _ in range(length - 4))


CSV_FIELDS = ['account_id', 'account_kind', 'user', 'password', 'login_url', 'status']


def save_csv(stream, rows):
    stream.seek(0)
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
    writer.writeheader(); writer.writerows(rows)
    stream.truncate(); stream.flush(); os.fsync(stream.fileno())


def provision(prepared, csv_path):
    # O_EXCL refuses overwrites; 0600 protects credentials on Unix. Windows users
    # must also apply an owner-only ACL. No credentials are ever printed.
    fd = os.open(csv_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    rows = []
    with os.fdopen(fd, 'w', encoding='utf-8', newline='') as out:
        save_csv(out, rows)
        for entry, session, minimum in prepared:
            iam, logs = session.client('iam'), session.client('logs')
            account = entry['account_id']
            tags = [{'Key': 'Workshop', 'Value': 'true'}, {'Key': 'WorkshopKind', 'Value': entry['kind']}]
            if entry['kind'] == 'identity':
                iam.create_policy(PolicyName='Workshop-Target-DenyAll', Path='/workshop/',
                    PolicyDocument=json.dumps(DENY_ALL), Tags=tags)['Policy']['Arn']
            for i in range(1, 11):
                n = names(entry, i)
                user_boundary, execution_policy, invocation_policy, user_policy = policies(entry, i, include_access=True)
                owned_tags = tags + [{'Key': 'Owner', 'Value': n['user']}]
                create_role(iam, n['lambda_role'], execution_policy, service_trust('lambda.amazonaws.com'), owned_tags)
                create_role(iam, n['event_role'], invocation_policy, service_trust('events.amazonaws.com', {
                    'StringEquals': {'aws:SourceAccount': account}, 'ArnLike': {'aws:SourceArn': n['rule_arn']}}), owned_tags)
                logs.create_log_group(logGroupName=n['log_group'], tags={'Workshop': 'true'})
                logs.put_retention_policy(logGroupName=n['log_group'], retentionInDays=7)
                arn = iam.create_policy(PolicyName=n['user'] + '-Access', Path='/workshop/',
                                        PolicyDocument=json.dumps(user_policy), Tags=owned_tags)['Policy']['Arn']
                boundary_arn = iam.create_policy(PolicyName=n['user'] + '-Boundary', Path='/workshop/',
                    PolicyDocument=json.dumps(user_boundary), Tags=owned_tags)['Policy']['Arn']
                iam.create_user(UserName=n['user'], Path='/workshop/', PermissionsBoundary=boundary_arn, Tags=owned_tags)
                iam.attach_user_policy(UserName=n['user'], PolicyArn=arn)
                record = {'account_id': account, 'account_kind': entry['kind'], 'user': n['user'],
                          'password': password(minimum), 'login_url': f'https://{account}.signin.aws.amazon.com/console/',
                          'status': 'pending'}
                rows.append(record)
                # Save before CreateLoginProfile: even an ambiguous API timeout
                # leaves the generated password recoverable without resetting it.
                save_csv(out, rows)
                iam.create_login_profile(UserName=n['user'], Password=record['password'], PasswordResetRequired=True)
                record['status'] = 'ready'
                save_csv(out, rows)
                print(f'Created {account}/{n["user"]}, scoped roles and log group')
    print('Complete: 30 participant logins. Distribute only the individual ready rows.')
    print('Identity students create their assigned inert test users with the pre-created deny-all boundary.')


def cap_concurrency(config):
    import boto3
    for entry in config['accounts']:
        session = boto3.Session(profile_name=entry['profile'], region_name=entry['region'])
        caller = session.client('sts').get_caller_identity()
        verify_instructor(session.client('iam'), caller, entry)
        client = session.client('lambda')
        for i in range(1, 11):
            # Fails on a missing function; only run when all 10 have been created.
            client.put_function_concurrency(FunctionName=names(entry, i)['function'], ReservedConcurrentExecutions=1)
            print(f'Concurrency capped at 1: {entry["account_id"]}/{names(entry, i)["function"]}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--example', action='store_true')
    p.add_argument('--config')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--csv', default='workshop_credentials.csv')
    p.add_argument('--render-scp', metavar='PATH', help='Generate SCP locally; does not attach it')
    p.add_argument('--cap-concurrency', action='store_true', help='Instructor: cap each existing function at 1')
    a = p.parse_args()
    if a.example:
        print(json.dumps(example(), indent=2)); return
    if not a.config:
        p.error('--config is required')
    config = json.loads(Path(a.config).read_text())
    check_config(config)
    if a.render_scp:
        base = Path(a.render_scp)
        tags_path = base.with_name(base.stem + '-tags' + base.suffix)
        if base.exists() or tags_path.exists():
            raise ValueError('SCP output already exists; refusing overwrite')
        for path, policy in ((base, scp(config)), (tags_path, tagging_scp())):
            with path.open('x') as f:
                json.dump(policy, f, separators=(',', ':'))
        print('Two SCPs generated. Review and attach BOTH only to the Workshop OU.'); return
    if a.cap_concurrency:
        if not a.apply:
            p.error('--cap-concurrency requires --apply')
        cap_concurrency(config); return
    if a.apply and Path(a.csv).exists():
        raise ValueError('CSV already exists; refusing to overwrite credentials')
    prepared = preflight(config)
    if not a.apply:
        print('Read-only preview complete. Use --apply to create users, roles, and CSV.'); return
    provision(prepared, a.csv)


if __name__ == '__main__':
    main()
