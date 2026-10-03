# AWS Python security workshop — student guide index

## Which guide should I use?

| Assigned account | Student guide | Exercises |
|---|---|---|
| Network | network_student_guide.md | SSH, RDP, all-protocol ingress, subnet public IPv4 default |
| Identity | identity_student_guide.md | AdministratorAccess, wildcard inline policy, access keys |
| Storage | storage_student_guide.md | Bucket public-access blocking, public SQS policy, SQS encryption |

Each guide is self-contained and applies to user01–user10. Each student creates **one Lambda in their assigned account**, handling that group's cases. Students work through the AWS console; credentials and CLI profiles are not required for their code.

Examples use user01 / participant 01. Replace them consistently with your assigned username and number. Same usernames in different accounts are separate logins.

## Instructor handoff before class

1. Share the student's individual ready credential row privately, plus the appropriate group guide. Do not distribute the full credentials CSV.
2. Supply the actual account ID and confirm us-east-1. For Network, supply the workshop VPC ID and each configured subnet CIDR.
3. Confirm both SCPs, roles, boundaries and CloudTrail management-event logging are in place.
4. Pilot user01 in each account using these guides. Verify console creation tags/boundary and EventBridge existing-role selection work under the actual permissions.
5. For Storage, provide the exact bucket BPA CloudTrail eventName, plus sanitized sample events for all cases. Confirm the request fields used by the handlers match those events.
6. Network/storage currently have a total concurrency quota of 10; quota requests are pending. Do not run the all-account concurrency cap until sufficient capacity exists. Proceed with short functions and one change per student at a time. Instructor monitors errors/throttles/duration.
7. These educational handlers have not been integration-tested in AWS. Validate the pilot end state and duplicate/no-op behavior before student delivery. They do not implement production approval, durable deduplication, dead-letter handling or atomic protection against concurrent external changes.

## Expected evidence

For each assigned case: resource identifier, compliant end-state screenshot, sanitized repair log, and a duplicate replay returning already_compliant. Keep secrets out of screenshots and logs.

## Cleanup ownership

Students disable their rules and delete only permitted owned exercise resources. Instructor removes protected IAM targets, Lambda functions, logs, participant identities, policies, roles and final network foundations. Keep both SCPs attached while workshop principals remain.

Baseline: current workshop_setup.md, revision 3. Prepared after participant provisioning; these guides do not rerun provisioning or alter existing permissions.
