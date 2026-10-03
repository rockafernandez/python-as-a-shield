import sys,types,runpy
from pathlib import Path
from unittest.mock import MagicMock
clients={name:MagicMock() for name in ('ec2','iam','s3','sqs')}
sys.modules['boto3']=types.SimpleNamespace(client=lambda name,**kwargs:clients[name])
root=Path(__file__).parent
mods={k:runpy.run_path(str(root.parent/'lambda'/f'{k}.py')) for k in ('network','identity','storage')}
def event(service,name,p,response=None):
 return {'id':'sample','account':'123456789012','region':'us-east-1','detail':{'eventSource':service,'eventName':name,'userIdentity':{'arn':'arn:aws:iam::123456789012:user/workshop/user01'},'requestParameters':p,'responseElements':response or {}}}
for m in mods.values():
 m['lambda_handler'].__globals__['ACCOUNT_ID']='123456789012'
 assert m['lambda_handler']({},None)['outcome']=='out_of_scope'
m=mods['network'];m['lambda_handler'].__globals__['VPC_ID']='vpc-lab'
ec2=clients['ec2'];s={'VpcId':'vpc-lab','Tags':[{'Key':'Workshop','Value':'true'},{'Key':'Owner','Value':'user01'}],'MapPublicIpOnLaunch':True}
ec2.describe_subnets.return_value={'Subnets':[s]}
e=event('ec2.amazonaws.com','ModifySubnetAttribute',{'subnetId':'subnet-lab'})
assert m['lambda_handler'](e,None)['outcome']=='repair_requested'
s['MapPublicIpOnLaunch']=False
assert m['lambda_handler'](e,None)['outcome']=='already_compliant'
assert ec2.modify_subnet_attribute.call_count==1
s['Tags'][1]['Value']='user02'
assert m['lambda_handler'](e,None)['outcome']=='out_of_scope'
ec2.describe_security_groups.return_value={'SecurityGroups':[{'VpcId':'vpc-lab','Tags':[{'Key':'Workshop','Value':'true'},{'Key':'Owner','Value':'user01'}]}]}
ec2.get_paginator.return_value.paginate.return_value=[{'SecurityGroupRules':[
 {'IsEgress':False,'CidrIpv4':'0.0.0.0/0','IpProtocol':'tcp','FromPort':20,'ToPort':25,'SecurityGroupRuleId':'r-ssh'},
 {'IsEgress':False,'CidrIpv4':'0.0.0.0/0','IpProtocol':'tcp','FromPort':443,'ToPort':443,'SecurityGroupRuleId':'r-web'}]}]
assert m['lambda_handler'](event('ec2.amazonaws.com','AuthorizeSecurityGroupIngress',{'groupId':'sg-lab'}),None)['outcome']=='removed_1_rules'
assert ec2.revoke_security_group_ingress.call_args.kwargs['SecurityGroupRuleIds']==['r-ssh']
m=mods['identity'];iam=clients['iam']
iam.get_user.return_value={'User':{'PermissionsBoundary':{'PermissionsBoundaryArn':'arn:aws:iam::123456789012:policy/workshop/Workshop-Target-DenyAll'}}}
iam.list_user_tags.return_value={'Tags':[{'Key':'Workshop','Value':'true'},{'Key':'Owner','Value':'user01'}]}
iam.list_access_keys.return_value={'AccessKeyMetadata':[{'AccessKeyId':'test-id','Status':'Active'}]}
e=event('iam.amazonaws.com','CreateAccessKey',{'userName':'Workshop-Target-01'},{'accessKey':{'accessKeyId':'test-id'}})
assert m['lambda_handler'](e,None)['outcome']=='key_deactivated'
iam.list_access_keys.return_value={'AccessKeyMetadata':[{'AccessKeyId':'test-id','Status':'Inactive'}]}
assert m['lambda_handler'](e,None)['outcome']=='already_compliant'
assert iam.update_access_key.call_count==1
m=mods['storage'];g=m['lambda_handler'].__globals__;g['QUEUE_ARN']='arn:aws:sqs:us-east-1:123456789012:user01-Queue'
sqs=clients['sqs'];url='https://sqs.us-east-1.amazonaws.com/123456789012/user01-Queue'
sqs.get_queue_url.return_value={'QueueUrl':url}
import json
private={'Sid':'KeepMe','Effect':'Allow','Principal':{'AWS':'arn:aws:iam::123456789012:root'},'Action':'sqs:*','Resource':g['QUEUE_ARN']}
public={'Sid':'WorkshopPublicSend','Effect':'Allow','Principal':'*','Action':'sqs:SendMessage','Resource':g['QUEUE_ARN']}
attrs={'QueueArn':g['QUEUE_ARN'],'Policy':json.dumps({'Version':'2012-10-17','Statement':[private,public]}),'SqsManagedSseEnabled':'false'}
sqs.get_queue_attributes.return_value={'Attributes':attrs}
e=event('sqs.amazonaws.com','SetQueueAttributes',{'queueUrl':url})
assert m['lambda_handler'](e,None)['outcome']=='queue_repair_requested'
changes=sqs.set_queue_attributes.call_args.kwargs['Attributes']
assert json.loads(changes['Policy'])['Statement']==[private]
assert changes['SqsManagedSseEnabled']=='true'
attrs['Policy']=changes['Policy'];attrs['SqsManagedSseEnabled']='true'
assert m['lambda_handler'](e,None)['outcome']=='already_compliant'
assert sqs.set_queue_attributes.call_count==1
print('Offline checks passed: scope rejection, subnet/keys/queue no-op, SG port range, preservation of unrelated rules/policy.')
