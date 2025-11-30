from aws_cdk import (
    Stack,
    aws_ec2 as ec2
)
from constructs import Construct

class AwsCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(
            self,
            "SARNetworkVpc",
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public-subnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                )
            ],
        )

        sg = ec2.SecurityGroup(
            self,
            "InstanceSecurityGroup",
            vpc=vpc,
            description="Allow SSH from a single IP only",
            allow_all_outbound=True,
        )

        # for now allow ssh from all IPs (Change in the future)
        sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(22),
            description="Allow SSH from anywhere (NOT recommended)",
        )

        instance = ec2.Instance(
            self,
            "SARAgentEc2Instance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.LARGE,
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        100,
                        encrypted=True,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                    ),
                )
            ],
            security_group=sg,
            key_name="sar-agents",
        )