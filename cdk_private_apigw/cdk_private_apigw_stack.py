from aws_cdk import (
    aws_iam as iam,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    core,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)

from aws_cdk.aws_ec2 import BastionHostLinux, InstanceType, AmazonLinuxImage, \
    SubnetSelection, SecurityGroup, SubnetType, InterfaceVpcEndpoint, \
    Vpc, Subnet, Peer, Port, CfnVPCPeeringConnection, CfnRoute, \
    IInterfaceVpcEndpointService, InterfaceVpcEndpointAwsService

class CdkPrivateApigwStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create two VPCs - one to host our private API, the other to act as a client
        api_vpc = Vpc(self, "APIVPC",
          cidr="10.0.0.0/16"
        )
        client_vpc = Vpc(self, "ClientVPC",
          cidr="10.1.0.0/16"
        )
        
        # Create a bastion host in the client API which will act like our client workstation
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

        # Set up a VPC peering connection between client and API VPCs, and adjust
        # the routing table to allow connections back and forth
        vpc_peering = CfnVPCPeeringConnection (self, 'VPCPeer',
          vpc_id=api_vpc.vpc_id,
          peer_vpc_id=client_vpc.vpc_id
          )
        route1 = CfnRoute(self, 'PeerRoute1',
          route_table_id= api_vpc.private_subnets[0].route_table.route_table_id,
          destination_cidr_block= client_vpc.vpc_cidr_block,
          vpc_peering_connection_id= vpc_peering.ref )
        route2 = CfnRoute(self, 'PeerRoute2',
          route_table_id= client_vpc.private_subnets[0].route_table.route_table_id,
          destination_cidr_block= api_vpc.vpc_cidr_block,
          vpc_peering_connection_id= vpc_peering.ref )
        route3 = CfnRoute(self, 'PeerRoute3',
          route_table_id= api_vpc.private_subnets[1].route_table.route_table_id,
          destination_cidr_block= client_vpc.vpc_cidr_block,
          vpc_peering_connection_id= vpc_peering.ref )
        route4 = CfnRoute(self, 'PeerRoute4',
          route_table_id= client_vpc.private_subnets[1].route_table.route_table_id,
          destination_cidr_block= api_vpc.vpc_cidr_block,
          vpc_peering_connection_id= vpc_peering.ref )

        # Create a VPC endpoint for API gateway        
        vpc_endpoint = InterfaceVpcEndpoint(self, 'ApiVpcEndpoint',
          vpc=api_vpc,
          service=InterfaceVpcEndpointAwsService.APIGATEWAY,
          private_dns_enabled=True,
        )
        vpc_endpoint.connections.allow_from(bastion, Port.tcp(443))
        id = vpc_endpoint.vpc_endpoint_id
        
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
        
        api_policy = iam.PolicyDocument(
            statements= [
              iam.PolicyStatement(
                principals= [iam.AnyPrincipal()],
                actions= ['execute-api:Invoke'],
                resources= ['execute-api:/*'],
                effect= iam.Effect.DENY,
                conditions= {
                  "StringNotEquals": {
                    "aws:SourceVpce": id
                  }
                }
              ),
              iam.PolicyStatement(
                principals= [iam.AnyPrincipal()],
                actions= ['execute-api:Invoke'],
                resources= ['execute-api:/*'],
                effect= iam.Effect.ALLOW
              )
            ]
          )
          
        # Create a private API GW in the API VPC
        api = apigw.RestApi(self, 'PrivateLambdaRestApi', 
          endpoint_configuration=apigw.EndpointConfiguration(
            types = [apigw.EndpointType.PRIVATE],
                     vpc_endpoints = [vpc_endpoint]),
          policy= api_policy
        )
        # Create two separate resources, to represent two separate APIs
        # first API
        resource1 = api.root.add_resource("my-api-1")
        resource1_integration = apigw.LambdaIntegration(my_lambda1)
        resource1.add_method("GET", resource1_integration);
        # second API
        resource2 = api.root.add_resource("my-api-2")
        resource2_integration = apigw.LambdaIntegration(my_lambda2)
        resource2.add_method("GET", resource2_integration);
        