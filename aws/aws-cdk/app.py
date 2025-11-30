#!/usr/bin/env python3
import os

import aws_cdk as cdk

from sar_agent_cdk.aws_cdk_stack import AwsCdkStack


app = cdk.App()
AwsCdkStack(
    app, 
    "SARAgentAwsCdkStack",
    env=cdk.Environment(
        account=os.environ.get("AWS_ACCOUNT_ID"),
        region="us-west-2"
    ),
)

app.synth()
