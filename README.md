
# CDK project to deploy private API gateway

This project deploys a pair of VPCs: an API VPC which contains a private API gateway accessed via an endpoint, and a client VPC which contains a test host that is used to access the API. The two VPCs are peered together to allow the API to be called from the client VPC.

I wanted to experiment with calling a private API from outside the VPC in which it is hosted.

You can connect to the test host using SSM as follows:

`export AWS_REGION=eu-west-1`

```
export BASTION_INSTANCE_ID=$(aws ec2 describe-instances \
                          --region=$AWS_REGION \
                          --filter "Name=tag:Name,Values=my-bastion" \
                          --query "Reservations[].Instances[?State.Name == 'running'].InstanceId[]" \
                          --output text)
```

`aws ssm start-session --target $BASTION_INSTANCE_ID --region=$AWS_REGION`