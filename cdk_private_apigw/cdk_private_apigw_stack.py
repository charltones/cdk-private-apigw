from aws_cdk import (
    aws_iam as iam,
    aws_sns_subscriptions as subs,
    core,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_route53 as r53,
    aws_route53_targets as r53targets,
    aws_elasticloadbalancingv2 as elb,
    aws_elasticloadbalancingv2_targets as elbtargets
)

from aws_cdk.aws_ec2 import BastionHostLinux, InstanceType, AmazonLinuxImage, \
    SubnetSelection, SecurityGroup, SubnetType, InterfaceVpcEndpoint, \
    Vpc, Subnet, Peer, Port, CfnVPCPeeringConnection, CfnRoute, \
    IInterfaceVpcEndpointService, InterfaceVpcEndpointAwsService

class VpcPeeringHelper(core.Construct):

    def __init__(self, scope: core.Construct, id: str, client_vpc, peer_vpc, **kwargs):
        super().__init__(scope, id, **kwargs)
        
        vpc_peering = CfnVPCPeeringConnection (self, id,
          vpc_id=client_vpc.vpc_id,
          peer_vpc_id=peer_vpc.vpc_id
          )
        route = 1
        for (vpc1, vpc2) in [(client_vpc, peer_vpc), (peer_vpc, client_vpc)]:
          for subnet in vpc1.private_subnets:
            CfnRoute(self, 'Route-%s-%d' % (id, route),
              route_table_id= subnet.route_table.route_table_id,
              destination_cidr_block= vpc2.vpc_cidr_block,
              vpc_peering_connection_id= vpc_peering.ref )
            route += 1

class CdkPrivateApigwStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create three VPCs - two to host our private APIs, the other to act as a client
        api_vpc1 = Vpc(self, "API1VPC",
          cidr="10.0.0.0/16",
          )
        api_vpc2 = Vpc(self, "API2VPC",
          cidr="10.1.0.0/16",
        )
        client_vpc = Vpc(self, "ClientVPC",
          cidr="10.2.0.0/16",
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
        VpcPeeringHelper(self, 'PeerAPI1', api_vpc1, client_vpc)
        VpcPeeringHelper(self, 'PeerAPI2', api_vpc2, client_vpc)

        # Create VPC endpoints for API gateway        
        vpc_endpoint1 = InterfaceVpcEndpoint(self, 'API1VpcEndpoint',
          vpc=api_vpc1,
          service=InterfaceVpcEndpointAwsService.APIGATEWAY,
          private_dns_enabled=True,
        )
        vpc_endpoint1.connections.allow_from(bastion, Port.tcp(443))
        endpoint_id1 = vpc_endpoint1.vpc_endpoint_id
        vpc_endpoint2 = InterfaceVpcEndpoint(self, 'API2VpcEndpoint',
          vpc=api_vpc2,
          service=InterfaceVpcEndpointAwsService.APIGATEWAY,
          private_dns_enabled=True,
        )
        vpc_endpoint2.connections.allow_from(bastion, Port.tcp(443))
        endpoint_id2 = vpc_endpoint2.vpc_endpoint_id

        # Defines an AWS Lambda resource
        my_lambda1_1 = _lambda.Function(
            self, 'Handler1',
            runtime=_lambda.Runtime.PYTHON_3_7,
            code=_lambda.Code.asset('lambda'),
            handler='handler1.handler',
        )
        my_lambda1_2 = _lambda.Function(
            self, 'Handler2',
            runtime=_lambda.Runtime.PYTHON_3_7,
            code=_lambda.Code.asset('lambda'),
            handler='handler2.handler',
        )
        my_lambda2_1 = _lambda.Function(
            self, 'Handler3',
            runtime=_lambda.Runtime.PYTHON_3_7,
            code=_lambda.Code.asset('lambda'),
            handler='handler3.handler',
        )
        my_lambda2_2 = _lambda.Function(
            self, 'Handler4',
            runtime=_lambda.Runtime.PYTHON_3_7,
            code=_lambda.Code.asset('lambda'),
            handler='handler4.handler',
        )
        
        api_policy1 = iam.PolicyDocument(
            statements= [
              iam.PolicyStatement(
                principals= [iam.AnyPrincipal()],
                actions= ['execute-api:Invoke'],
                resources= ['execute-api:/*'],
                effect= iam.Effect.DENY,
                conditions= {
                  "StringNotEquals": {
                    "aws:SourceVpce": endpoint_id1
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
        api_policy2 = iam.PolicyDocument(
            statements= [
              iam.PolicyStatement(
                principals= [iam.AnyPrincipal()],
                actions= ['execute-api:Invoke'],
                resources= ['execute-api:/*'],
                effect= iam.Effect.DENY,
                conditions= {
                  "StringNotEquals": {
                    "aws:SourceVpce": endpoint_id2
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
        api1 = apigw.RestApi(self, 'PrivateLambdaRestApi1', 
          endpoint_configuration=apigw.EndpointConfiguration(
            types = [apigw.EndpointType.PRIVATE],
                     vpc_endpoints = [vpc_endpoint1]),
          policy= api_policy1
        )
        # Create two separate resources, to call separate Lambdas
        resource1 = api1.root.add_resource("my-api-1-1")
        resource1_integration = apigw.LambdaIntegration(my_lambda1_1)
        resource1.add_method("GET", resource1_integration)
        resource2 = api1.root.add_resource("my-api-1-2")
        resource2_integration = apigw.LambdaIntegration(my_lambda1_2)
        resource2.add_method("GET", resource2_integration)

        api2 = apigw.RestApi(self, 'PrivateLambdaRestApi2', 
          endpoint_configuration=apigw.EndpointConfiguration(
            types = [apigw.EndpointType.PRIVATE],
                     vpc_endpoints = [vpc_endpoint2]),
          policy= api_policy2
        )
        # Create two separate resources, to call separate Lambdas
        resource1 = api2.root.add_resource("my-api-2-1")
        resource1_integration = apigw.LambdaIntegration(my_lambda2_1)
        resource1.add_method("GET", resource1_integration)
        resource2 = api2.root.add_resource("my-api-2-2")
        resource2_integration = apigw.LambdaIntegration(my_lambda2_2)
        resource2.add_method("GET", resource2_integration)
        
        # Create a Route 53 private hosted zone
        '''
        my_zone = r53.PrivateHostedZone(
          self,
          'my-endpoint-zone',
          vpc = client_vpc, 
          zone_name = 'execute-api.eu-west-1.amazonaws.com')
        my_zone.add_vpc(api_vpc1)
        my_zone.add_vpc(api_vpc2)
        r53.ARecord(
          self,
          'my-endpoint-record', 
          target = r53.RecordTarget.from_alias(r53targets.InterfaceVpcEndpointTarget(vpc_endpoint1)),
          zone = my_zone)
        r53.ARecord(
          self,
          'my-endpoint-record-star', 
          target = r53.RecordTarget.from_alias(r53targets.InterfaceVpcEndpointTarget(vpc_endpoint1)),
          record_name = '*.execute-api.eu-west-1.amazonaws.com',
          zone = my_zone)
        '''
        
        my_lambda_proxy1 = _lambda.Function(
            self, 'Handler_Proxy1',
            runtime=_lambda.Runtime.PYTHON_3_7,
            code=_lambda.Code.asset('lambda'),
            handler='handler_proxy.handler',
            environment={
              'apihost': "%s.execute-api.eu-west-1.amazonaws.com" %
                (api1.rest_api_id)
            },
            vpc= api_vpc1,
            vpc_subnets=SubnetSelection(subnet_type=SubnetType.PRIVATE),
        )
        alb1 = elb.ApplicationLoadBalancer(self, "myALB1",
          vpc=api_vpc1,
          internet_facing=False,
          load_balancer_name="myALB1")
        listener1 = alb1.add_listener("Listener1", port=80)
        listener1.add_targets("Target1", 
          targets=[elbtargets.LambdaTarget(my_lambda_proxy1)])
        listener1.connections.allow_default_port_from_any_ipv4("Open to the world")

        my_lambda_proxy2 = _lambda.Function(
            self, 'Handler_Proxy2',
            runtime=_lambda.Runtime.PYTHON_3_7,
            code=_lambda.Code.asset('lambda'),
            handler='handler_proxy.handler',
            environment={
              'apihost': "%s.execute-api.eu-west-1.amazonaws.com" %
                (api2.rest_api_id)
            },
            vpc= api_vpc2,
            vpc_subnets=SubnetSelection(subnet_type=SubnetType.PRIVATE),
        )
        alb2 = elb.ApplicationLoadBalancer(self, "myALB2",
          vpc=api_vpc2,
          internet_facing=False,
          load_balancer_name="myALB2")
        listener2 = alb2.add_listener("Listener2", port=80)
        listener2.add_targets("Target2", 
          targets=[elbtargets.LambdaTarget(my_lambda_proxy2)])
        listener2.connections.allow_default_port_from_any_ipv4("Open to the world")
