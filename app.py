#!/usr/bin/env python3

from aws_cdk import core

from cdk_private_apigw.cdk_private_apigw_stack import CdkPrivateApigwStack


app = core.App()
CdkPrivateApigwStack(app, "cdk-private-apigw", env={'region': 'eu-west-1'})

app.synth()
