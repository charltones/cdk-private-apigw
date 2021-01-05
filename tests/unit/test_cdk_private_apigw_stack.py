import json
import pytest

from aws_cdk import core
from cdk-private-apigw.cdk_private_apigw_stack import CdkPrivateApigwStack


def get_template():
    app = core.App()
    CdkPrivateApigwStack(app, "cdk-private-apigw")
    return json.dumps(app.synth().get_stack("cdk-private-apigw").template)


def test_sqs_queue_created():
    assert("AWS::SQS::Queue" in get_template())


def test_sns_topic_created():
    assert("AWS::SNS::Topic" in get_template())
