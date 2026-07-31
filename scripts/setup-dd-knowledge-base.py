"""Setup Portfolio DD Knowledge Base — uploads PDFs to S3, creates/syncs Bedrock KB.

Prerequisites:
  - CDK stack deployed (creates DDSourceDocsBucket)
  - PDFs generated in packages/portfolio_dd/source_docs/ (run: python scripts/generate_source_docs.py)

Usage:
  python scripts/setup-dd-knowledge-base.py [--bucket BUCKET_NAME] [--stack STACK_NAME]
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
ACCOUNT = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]

SCRIPT_DIR = Path(__file__).parent
SOURCE_DOCS_DIR = SCRIPT_DIR.parent / "packages" / "portfolio_dd" / "source_docs"

PORTFOLIO_DOC_METADATA = {
    "pf_amp001_pds.pdf": {"portfolio_id": "pf_amp001", "doc_type": "pds"},
    "pf_amp001_quarterly.pdf": {"portfolio_id": "pf_amp001", "doc_type": "quarterly_report"},
    "pf_amp001_ddq.pdf": {"portfolio_id": "pf_amp001", "doc_type": "ddq"},
    "pf_pendal001_pds.pdf": {"portfolio_id": "pf_pendal001", "doc_type": "pds"},
    "pf_pendal001_quarterly.pdf": {"portfolio_id": "pf_pendal001", "doc_type": "quarterly_report"},
    "pf_pendal001_ddq.pdf": {"portfolio_id": "pf_pendal001", "doc_type": "ddq"},
    "pf_macq001_pds.pdf": {"portfolio_id": "pf_macq001", "doc_type": "pds"},
    "pf_macq001_quarterly.pdf": {"portfolio_id": "pf_macq001", "doc_type": "quarterly_report"},
    "pf_aef001_pds.pdf": {"portfolio_id": "pf_aef001", "doc_type": "pds"},
    "pf_aef001_esg.pdf": {"portfolio_id": "pf_aef001", "doc_type": "esg_report"},
    "pf_aef001_ddq.pdf": {"portfolio_id": "pf_aef001", "doc_type": "ddq"},
    "pf_hyperion001_pds.pdf": {"portfolio_id": "pf_hyperion001", "doc_type": "pds"},
    "pf_hyperion001_quarterly.pdf": {"portfolio_id": "pf_hyperion001", "doc_type": "quarterly_report"},
    "pf_hyperion001_ddq.pdf": {"portfolio_id": "pf_hyperion001", "doc_type": "ddq"},
}


def discover_bucket_name(stack_name: str) -> str:
    """Discover DDSourceDocsBucket name from CloudFormation stack outputs."""
    cfn = boto3.client("cloudformation", region_name=REGION)
    try:
        resp = cfn.describe_stacks(StackName=stack_name)
        outputs = resp["Stacks"][0].get("Outputs", [])
        for output in outputs:
            if output["OutputKey"] == "DDSourceDocsBucketName":
                return output["OutputValue"]
    except Exception:
        pass
    raise RuntimeError(
        f"Could not find DDSourceDocsBucketName output in stack '{stack_name}'. "
        "Ensure the CDK stack has been deployed first."
    )


def upload_documents(bucket_name: str):
    """Upload pre-generated PDFs and metadata sidecars to S3."""
    s3 = boto3.client("s3", region_name=REGION)

    if not SOURCE_DOCS_DIR.exists():
        print(f"ERROR: Source docs directory not found: {SOURCE_DOCS_DIR}")
        print("Run 'python scripts/generate_source_docs.py' first.")
        raise SystemExit(1)

    pdf_files = sorted(SOURCE_DOCS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"ERROR: No PDF files found in {SOURCE_DOCS_DIR}")
        raise SystemExit(1)

    print(f"   Uploading {len(pdf_files)} PDFs to s3://{bucket_name}/source_docs/...")
    for pdf_path in pdf_files:
        filename = pdf_path.name
        s3_key = f"source_docs/{filename}"

        s3.upload_file(
            str(pdf_path),
            bucket_name,
            s3_key,
            ExtraArgs={"ContentType": "application/pdf"},
        )

        meta = PORTFOLIO_DOC_METADATA.get(filename)
        if meta:
            doc_id = filename.replace(".pdf", "")
            metadata_obj = {
                "metadataAttributes": {
                    "portfolio_id": meta["portfolio_id"],
                    "doc_id": doc_id,
                    "doc_type": meta["doc_type"],
                }
            }
            metadata_key = f"{s3_key}.metadata.json"
            s3.put_object(
                Bucket=bucket_name,
                Key=metadata_key,
                Body=json.dumps(metadata_obj),
                ContentType="application/json",
            )

        print(f"   Uploaded: {s3_key}")


def ensure_kb_role(bucket_name: str) -> str:
    """Create or reuse the IAM role for the Knowledge Base."""
    role_name = "AmazonBedrockExecutionRoleForKnowledgeBase_dd"
    role_arn = f"arn:aws:iam::{ACCOUNT}:role/{role_name}"

    iam = boto3.client("iam", region_name=REGION)
    try:
        iam.get_role(RoleName=role_name)
        print("   KB role exists")
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="BedrockKBPolicy",
            PolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:ListBucket"],
                        "Resource": [
                            f"arn:aws:s3:::{bucket_name}",
                            f"arn:aws:s3:::{bucket_name}/*",
                        ],
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["bedrock:InvokeModel"],
                        "Resource": ["arn:aws:bedrock:*::foundation-model/*"],
                    },
                ],
            }),
        )
        return role_arn
    except iam.exceptions.NoSuchEntityException:
        pass

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}},
        }],
    }
    iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        Description="Role for Portfolio DD Knowledge Base",
    )
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="BedrockKBPolicy",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:ListBucket"],
                    "Resource": [
                        f"arn:aws:s3:::{bucket_name}",
                        f"arn:aws:s3:::{bucket_name}/*",
                    ],
                },
                {
                    "Effect": "Allow",
                    "Action": ["bedrock:InvokeModel"],
                    "Resource": ["arn:aws:bedrock:*::foundation-model/*"],
                },
            ],
        }),
    )
    print("   Created KB role")
    time.sleep(10)
    return role_arn


def create_or_get_kb(role_arn: str) -> str:
    """Create or reuse the Bedrock Knowledge Base."""
    bedrock = boto3.client("bedrock-agent", region_name=REGION)

    existing_kbs = bedrock.list_knowledge_bases()["knowledgeBaseSummaries"]
    dd_kb = next((kb for kb in existing_kbs if kb["name"] == "PortfolioDDKnowledgeBase"), None)

    if dd_kb:
        kb_id = dd_kb["knowledgeBaseId"]
        print(f"   KB already exists: {kb_id}")
        return kb_id

    kb_response = bedrock.create_knowledge_base(
        name="PortfolioDDKnowledgeBase",
        description="Fund documents for Portfolio Due Diligence analysis",
        roleArn=role_arn,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0",
            },
        },
        storageConfiguration={"type": "OPENSEARCH_SERVERLESS"},
    )
    kb_id = kb_response["knowledgeBase"]["knowledgeBaseId"]
    print(f"   Created KB: {kb_id}")
    time.sleep(5)
    return kb_id


def setup_data_source_and_sync(kb_id: str, bucket_name: str):
    """Create/reuse the S3 data source and start ingestion."""
    bedrock = boto3.client("bedrock-agent", region_name=REGION)

    ds_list = bedrock.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]
    if ds_list:
        ds_id = ds_list[0]["dataSourceId"]
        print(f"   Data source exists: {ds_id}")
    else:
        ds_response = bedrock.create_data_source(
            knowledgeBaseId=kb_id,
            name="FundDocuments",
            dataSourceConfiguration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": f"arn:aws:s3:::{bucket_name}",
                    "inclusionPrefixes": ["source_docs/"],
                },
            },
        )
        ds_id = ds_response["dataSource"]["dataSourceId"]
        print(f"   Created data source: {ds_id}")

    print("   Starting ingestion sync...")
    bedrock.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    print("   Sync started (will complete in 2-5 minutes)")


def save_kb_id_to_ssm(kb_id: str):
    """Persist the KB ID to SSM for CDK to pick up on next deploy."""
    ssm = boto3.client("ssm", region_name=REGION)
    ssm.put_parameter(
        Name="/wealth-management-portal/dd-knowledge-base-id",
        Value=kb_id,
        Type="String",
        Overwrite=True,
    )
    print(f"   Saved to SSM: /wealth-management-portal/dd-knowledge-base-id = {kb_id}")


def main():
    parser = argparse.ArgumentParser(description="Setup Portfolio DD Knowledge Base")
    parser.add_argument("--bucket", help="S3 bucket name (overrides CloudFormation lookup)")
    parser.add_argument("--stack", default="wealth-management-portal-app", help="CloudFormation stack name")
    args = parser.parse_args()

    print("=" * 60)
    print("Portfolio DD Knowledge Base Setup")
    print("=" * 60)

    # 1. Discover bucket
    print("\n1. Discovering S3 bucket...")
    if args.bucket:
        bucket_name = args.bucket
        print(f"   Using provided bucket: {bucket_name}")
    else:
        bucket_name = discover_bucket_name(args.stack)
        print(f"   Found bucket from stack: {bucket_name}")

    # 2. Upload documents
    print("\n2. Uploading source documents...")
    upload_documents(bucket_name)

    # 3. Setup IAM role
    print("\n3. Setting up KB IAM role...")
    role_arn = ensure_kb_role(bucket_name)

    # 4. Create Knowledge Base
    print("\n4. Creating/verifying Knowledge Base...")
    kb_id = create_or_get_kb(role_arn)

    # 5. Data source and sync
    print("\n5. Setting up data source and starting sync...")
    setup_data_source_and_sync(kb_id, bucket_name)

    # 6. Save to SSM
    print("\n6. Saving KB ID to SSM...")
    save_kb_id_to_ssm(kb_id)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Knowledge Base ID: {kb_id}")
    print(f"S3 Bucket: {bucket_name}")
    print(f"{'=' * 60}")
    print(f"\nNext steps:")
    print(f"1. Wait for sync to complete (~2-5 minutes, check Bedrock console)")
    print(f"2. If this is first-time setup, redeploy to wire BEDROCK_KB_ID:")
    print(f"   The KB ID is now in SSM and will be picked up on next deploy.")


if __name__ == "__main__":
    main()
