from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient


def read_parameters(path: str, client: "SSMClient | None" = None) -> dict[str, str]:
    ssm = client or boto3.client("ssm")
    return {
        parameter["Name"].rsplit("/", 1)[-1]: parameter["Value"]
        for page in ssm.get_paginator("get_parameters_by_path").paginate(
            Path=path, WithDecryption=True
        )
        for parameter in page["Parameters"]
    }
