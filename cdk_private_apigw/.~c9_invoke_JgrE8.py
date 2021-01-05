from aws_cdk import (
    aws_iam as iam,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    core,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    InterfaceVpcEndpoint, Vpc, Subnet, ec2, Peer, Port
)

from aws_cdk.aws_ec2 import BastionHostLinux, InstanceType, AmazonLinuxImage, \
    SubnetSelection, SecurityGroup, SubnetType

class CdkPrivateApigwStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Defines an AWS Lambda resource
        my_lambda1 = _lambda.Function(
            self, 'Handler1',
            runtime=_lambda.Runtime.PYTHON_3_7,
            code=_lambda.Code.asset('lambda'),
            handler='handler1.handler',
        )
        my_lambda2 = _lambda.Function(
            self, 'Handler2',
            runtime=_lambda.Runtime.PYTHON_3_7,
            code=_lambda.Code.asset('lambda'),
            handler='handler2.handler',
        )
        
        api_vpc = ec2.Vpc(self, "APIVPC",
          cidr="10.42.0.0/16"
        )
        client_vpc = ec2.Vpc(self, "ClientVPC",
          cidr="10.42.1.0/16"
        )
        bastion = BastionHostLinux(
          self, "APIClient",
          vpc=client_vpc,
          instance_name='my-bastion',
          instance_type=InstanceType('t3.micro'),
          machine_image=AmazonLinuxImage(),
          subnet_selection=SubnetSelection(subnet_type=SubnetType.PRIVATE),
          security_group=SecurityGroup(
            scope=self,
            id='bastion-sg',
            security_group_name='bastion-sg',
            description='Security group for the bastion, no inbound open because we should access'
                        ' to the bastion via AWS SSM',
            vpc=client_vpc,
            allow_all_outbound=True
          )
        )

        vpcEndpoint = InterfaceVpcEndpoint(self, 'ApiVpcEndpoint',
          vpc=api_vpc,
          service=ec2.IInterfaceVpcEndpointService(
            name='com.amazonaws.eu-central-1.execute-api',
            port=443
          ),
          privateDnsEnabled=True,
        )
        vpcEndpoint.connections.allow_from(bastion, Port.tcp(443))
        
        vpc_peering = ec2.CfnVPCPeeringConnection (self, 'VPCPeer',
          vpc_id=api_vpc.ref,
          peer_vpc_id=client_vpc.ref
          )
        vpc_peering_id = vpc_peering.ref
        route = ec2.CfnRoute(self, 'PeerRoute',
          route_table_id= api_vpc.private_subnets[0]subnet.route_table.route_table_id,
          destination_cidr_block= vpc.vpc_cidr_block,
          vpc_peering_connection_id= peering.ref )
        
        apigateway.LambdaRestApi(self, 'PrivateLambdaRestApi', {
          endpointTypes: [apigateway.EndpointType.PRIVATE],
          handler: fn,
          policy: iam.PolicyDocument({
            statements: [
              iam.PolicyStatement({
                principals: [iam.AnyPrincipal],
                actions: ['execute-api:Invoke'],
                resources: ['execute-api:/*'],
                effect: iam.Effect.DENY,
                conditions: {
                  StringNotEquals: {
                    "aws:SourceVpce": vpcEndpoint.vpcEndpointId
                  }
                }
              }),
              iam.PolicyStatement({
                principals: [iam.AnyPrincipal],
                actions: ['execute-api:Invoke'],
                resources: ['execute-api:/*'],
                effect: iam.Effect.ALLOW
              })
            ]
          })
        })
        