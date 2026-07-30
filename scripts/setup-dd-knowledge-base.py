"""Setup Portfolio DD Knowledge Base — generates sample PDFs, uploads to S3, creates KB."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
ACCOUNT = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
BUCKET_NAME = f"dd-source-documents-{ACCOUNT}"

# Sample fund document content — realistic enough for KB retrieval
DOCUMENTS = {
    "pf_amp001": {
        "name": "AMP Growth Fund",
        "manager": "AMP Capital Investors",
        "afsl": "232030",
        "abn": "59 001 777 591",
        "benchmark": "CPI + 4.5% p.a.",
        "inception": "1 July 1998",
        "aum": "$2.84 billion",
        "mer": "0.67%",
        "key_person": "Anna Shelley (CIO, 12 years tenure)",
        "custodian": "NAB Asset Servicing (APRA-regulated)",
    },
    "pf_pendal001": {
        "name": "Pendal Australian Equities",
        "manager": "Pendal Group",
        "afsl": "228504",
        "abn": "28 126 385 822",
        "benchmark": "S&P/ASX 300 Accumulation Index",
        "inception": "1 April 1997",
        "aum": "$1.15 billion",
        "mer": "0.85%",
        "key_person": "Crispin Murray (Head of Equities, 18 years tenure)",
        "custodian": "J.P. Morgan Investor Services (APRA-regulated)",
    },
    "pf_macq001": {
        "name": "Macquarie Income Fund",
        "manager": "Macquarie Investment Management",
        "afsl": "237492",
        "abn": "66 002 867 003",
        "benchmark": "Bloomberg AusBond Bank Bill Index",
        "inception": "30 November 2000",
        "aum": "$4.2 billion",
        "mer": "0.28%",
        "key_person": "Ben Way (Division Head, 15 years tenure)",
        "custodian": "State Street Australia (APRA-regulated)",
    },
    "pf_aef001": {
        "name": "Australian Ethical Balanced",
        "manager": "Australian Ethical Investment",
        "afsl": "229949",
        "abn": "47 003 188 930",
        "benchmark": "CPI + 3.5% p.a.",
        "inception": "1 January 2002",
        "aum": "$870 million",
        "mer": "0.79%",
        "key_person": "Mark Simons (CIO, 8 years tenure)",
        "custodian": "BNP Paribas Securities Services (APRA-regulated)",
    },
    "pf_hyperion001": {
        "name": "Hyperion Australian Growth Companies",
        "manager": "Hyperion Asset Management",
        "afsl": "238380",
        "abn": "80 080 135 897",
        "benchmark": "S&P/ASX All Ordinaries Accumulation Index",
        "inception": "1 August 1996",
        "aum": "$5.1 billion",
        "mer": "1.10%",
        "key_person": "Mark Arnold (CIO & Managing Director, 28 years tenure)",
        "custodian": "NAB Asset Servicing (APRA-regulated)",
    },
}


def generate_pds_content(portfolio_id: str, fund: dict) -> str:
    return f"""
Product Disclosure Statement (PDS)
{fund['name']}
Issued by {fund['manager']} | AFSL {fund['afsl']} | ABN {fund['abn']}
Effective Date: 1 January 2026

1. INVESTMENT PHILOSOPHY & PROCESS

{fund['name']} employs a disciplined, research-driven investment process focused on identifying quality
companies with sustainable competitive advantages. Our investment philosophy is grounded in the belief
that superior long-term returns are generated through concentrated portfolios of high-quality businesses
purchased at reasonable valuations.

Alpha Sources: The fund seeks to generate alpha through bottom-up fundamental research, proprietary
scoring models, and active engagement with portfolio companies. We focus on earnings quality, balance
sheet strength, management capability, and industry structure.

Process Evolution: The investment process has been refined over {fund['inception'].split()[-1]} inception,
with enhancements to our ESG integration framework in 2023 and quantitative risk overlay in 2024.

2. PORTFOLIO CONSTRUCTION

Maximum single security weight: 8% at cost, 10% at market value
Maximum sector exposure: 35% (relative to benchmark ±15%)
Minimum number of holdings: 25
Typical portfolio concentration: Top 10 holdings represent 40-50% of portfolio
Cash allocation range: 0-10%

Documented deviation: In Q3 2025, the fund temporarily exceeded the technology sector cap (37% vs 35% limit)
due to market appreciation. This was rectified within 30 days per the compliance framework.

3. BENCHMARK

Benchmark: {fund['benchmark']}
Benchmark inception date: {fund['inception']}
No benchmark changes in the last 3 years.

4. RISK MANAGEMENT

The fund operates a three-lines-of-defence risk management framework with an independent Risk Committee
that meets monthly. Key risk limits include:
- Portfolio VaR (95%, 1-day): 2.5% of NAV
- Maximum drawdown trigger: 15% from peak (triggers CIO review)
- Tracking error budget: 4-8% p.a.
- Liquidity coverage: >90% portfolio liquidatable within 5 business days

5. KEY PERSONNEL

Lead Portfolio Manager: {fund['key_person']}
Deputy PM: [Assistant PM with 6+ years tenure]
The fund has key-person risk provisions requiring 90-day notice and a documented succession plan
reviewed annually by the Board.

6. REGULATORY COMPLIANCE

AFSL Number: {fund['afsl']}
The Responsible Entity confirms no material compliance breaches in the past 5 years. No ASIC
enforceable undertakings have been issued. The compliance framework includes daily automated
monitoring, quarterly compliance committee meetings, and annual independent audit.

7. CONFLICTS OF INTEREST

Related-party transactions: {fund['manager']} may use affiliated brokers for up to 15% of total
brokerage. All related-party transactions are disclosed in the annual report and monitored by
the Compliance team.
Soft-dollar arrangements: The fund does not accept soft-dollar commissions.
Personal trading policy: All investment staff are subject to a 30-day pre-clearance and holding
period for personal securities trading.

8. FEES AND COSTS

Management Fee (MER): {fund['mer']} p.a. of NAV
Performance Fee: None
Buy Spread: 0.10% | Sell Spread: 0.10%
Indirect Cost Ratio (ICR): 0.05%

9. FUND SIZE AND VIABILITY

Current AUM: {fund['aum']} (as at 31 December 2025)
3-year AUM trend: Positive net inflows in 8 of last 12 quarters
Parent company: {fund['manager']} (ASX-listed / independently owned)
Staff retention: 92% annual retention rate across investment team

10. CUSTODIAN

Custodian: {fund['custodian']}
"""


def generate_quarterly_content(portfolio_id: str, fund: dict) -> str:
    return f"""
Quarterly Investment Report — Q1 2026
{fund['name']}

PERFORMANCE SUMMARY

Period          Fund Return     Benchmark       Excess
1 Month         +1.8%           +1.5%          +0.3%
3 Months        +4.2%           +3.8%          +0.4%
1 Year          +12.5%          +11.2%         +1.3%
3 Years (p.a.)  +9.8%           +8.9%          +0.9%
Since Inception +8.4%           +7.6%          +0.8%

PERFORMANCE ATTRIBUTION (Brinson Model)

Sector              Allocation    Selection     Interaction    Total
Technology          +0.12%        +0.28%        +0.04%        +0.44%
Financials          -0.08%        +0.15%        -0.02%        +0.05%
Healthcare          +0.05%        -0.12%        +0.01%        -0.06%
Materials           -0.03%        +0.08%        -0.01%        +0.04%
Consumer Disc.      +0.02%        +0.06%        +0.00%        +0.08%
Other               -0.01%        -0.10%        +0.02%        -0.09%
Total               +0.07%        +0.35%        +0.04%        +0.46%

Tracking Error (realised, annualised): 3.8%
Information Ratio (12 months): 0.34

PORTFOLIO CHANGES

Additions: [Company A] (Technology, +2.5%), [Company B] (Healthcare, +1.8%)
Exits: [Company C] (Financials, sold on valuation), [Company D] (Consumer, earnings downgrade)

MARKET COMMENTARY

Australian equities delivered solid gains in Q1 2026, supported by resilient corporate earnings
and a more accommodative monetary policy stance from the RBA. The portfolio benefited from
overweight positions in quality technology companies and underweight in resources.

OUTLOOK

We remain constructive on the Australian equity market, with opportunities in technology and
healthcare offset by caution in materials given commodity price uncertainty. Portfolio
positioning remains focused on quality growth at reasonable valuations.

Benchmark: {fund['benchmark']}
Fund inception: {fund['inception']}
"""


def generate_ddq_content(portfolio_id: str, fund: dict) -> str:
    return f"""
Due Diligence Questionnaire (DDQ) Response
{fund['name']} — {fund['manager']}
Date: January 2026

SECTION 1: RISK MANAGEMENT FRAMEWORK

1.1 Risk Governance Structure
The fund operates under a three-lines-of-defence model:
- First line: Portfolio managers responsible for risk within mandated limits
- Second line: Independent Risk team (3 FTE) reporting to CRO
- Third line: Internal Audit (outsourced to KPMG, annual engagement)

Risk Committee meets monthly; chaired by independent non-executive director.

1.2 Risk Limits and Monitoring
- Value at Risk (VaR): 95% confidence, 1-day horizon, limit 2.5% of NAV
- Conditional VaR (CVaR): 97.5% confidence, limit 3.5% of NAV
- Maximum drawdown trigger: 15% from peak triggers mandatory CIO review and Board notification
- Counterparty exposure: Max 5% to any single counterparty
- Liquidity: >85% liquidatable within 3 business days

SECTION 2: OPERATIONAL INFRASTRUCTURE

2.1 Systems
- Order Management: Charles River IMS (enterprise licence)
- Portfolio Management: Bloomberg PORT+ with proprietary risk overlay
- Reconciliation: Automated daily NAV reconciliation (custodian vs. internal)
- Trade execution: Direct market access via Chi-X, ASX TradeMatch

2.2 Custodian
{fund['custodian']}
Independent APRA-regulated entity with >$500B assets under custody globally.

2.3 External Audit
Annual financial audit: PwC (engagement partner rotates every 5 years)
Last material audit finding: None in past 3 years
SOC 1 Type II report: Obtained annually (last: November 2025, unqualified)

SECTION 3: KEY PERSON RISK

3.1 Key Personnel
Lead Portfolio Manager: {fund['key_person']}
Investment Committee: 4 members (quorum 3)
Average tenure of investment team: 9 years

3.2 Succession Plan
Documented succession plan reviewed annually by the Board. Deputy PM has full authority
to manage the portfolio during any absence of the lead PM. Key-person clause in constituent
documents requires 90-day written notice.

SECTION 4: BUSINESS CONTINUITY

4.1 BCP Policy
Business Continuity Plan last tested: September 2025 (full simulation)
Recovery Time Objective (RTO): 4 hours
Recovery Point Objective (RPO): 1 hour (real-time replication to DR site)
DR Site: [Secondary location in different geographic zone]

4.2 Pandemic/Remote Working
100% remote-working capability demonstrated during 2024 DR test.
All critical systems accessible via VPN with MFA.

SECTION 5: COMPLIANCE

5.1 Regulatory Status
AFSL Number: {fund['afsl']} (current, no conditions)
ASIC enforceable undertakings: None
Material compliance breaches (last 5 years): None
Compliance monitoring: Daily automated + quarterly committee review

5.2 Breach Register
Total breaches (2025): 2 (both minor, operational — resolved within 24 hours)
- Breach 1: Late trade reporting (system error, no client impact)
- Breach 2: Temporary sector limit exceedance (market movement, rectified within 5 days)

SECTION 6: CONFLICTS OF INTEREST

6.1 Board and IC Independence
Board: 5 members, 3 independent non-executive directors (60% independent)
Investment Committee: 4 members, all investment professionals (no board overlap)

6.2 Personal Trading
All investment staff subject to pre-clearance (T+0) and 30-day holding period.
Compliance reviews personal trading quarterly; no material breaches in 2025.

SECTION 7: BUSINESS VIABILITY

7.1 AUM Trend (3 years)
- Dec 2023: {fund['aum'].replace('billion', 'B').replace('million', 'M')} (approx -8% from current)
- Dec 2024: {fund['aum'].replace('billion', 'B').replace('million', 'M')} (approx -3% from current)
- Dec 2025: {fund['aum']}
Net inflows: Positive in 8 of 12 quarters

7.2 Staff Retention
Annual investment team retention: 92%
Average tenure: 9 years
Key departures (last 3 years): 1 (junior analyst, replaced within 60 days)
"""


def generate_esg_content(portfolio_id: str, fund: dict) -> str:
    return f"""
ESG Impact Report 2025
{fund['name']} — {fund['manager']}

1. UNPRI COMMITMENT

{fund['manager']} has been a signatory to the United Nations Principles for Responsible
Investment (UNPRI) since 2008. Our most recent UNPRI Assessment (2024) received a score
of 4 out of 5 stars across all modules.

2. EXCLUSION POLICY

The fund maintains a comprehensive exclusion list:
- Tobacco manufacturing (0% threshold)
- Controversial weapons (cluster munitions, landmines, biological/chemical weapons)
- Thermal coal mining (>10% revenue threshold)
- Gambling (>25% revenue threshold)
- Adult entertainment (>5% revenue threshold)

Current exclusion list: 47 companies screened out globally.

3. ESG SCORING METHODOLOGY

We employ a proprietary ESG scoring framework combining:
- Quantitative: MSCI ESG ratings, Sustainalytics risk scores, ISS quality scores
- Qualitative: Internal analyst assessment on material ESG factors
- Thematic: Climate transition alignment (TCFD-aligned scenario analysis)

Each holding receives an ESG composite score (1-10). Portfolio average: 7.2/10.

4. STEWARDSHIP & ENGAGEMENT

Active engagements in 2025: 28 companies (representing 65% of portfolio by weight)
Key engagement themes:
- Climate transition plans: 12 engagements
- Board diversity: 8 engagements
- Supply chain transparency: 5 engagements
- Executive remuneration: 3 engagements

Outcomes: 18 of 28 engagements resulted in improved disclosure or commitments.

5. PROXY VOTING

Proxy votes cast in 2025: 342 resolutions across 45 companies
Votes against management: 12% (primarily on executive remuneration and board composition)
Shareholder resolutions supported: 8 (climate-related and diversity-related)

All proxy voting records are publicly available on our website.

6. CLIMATE COMMITMENT

The fund is committed to achieving net-zero portfolio emissions by 2050, with an interim
target of 50% reduction (vs. 2020 baseline) by 2030.
Current portfolio weighted average carbon intensity: 85 tCO2e/$M revenue
(vs. benchmark: 120 tCO2e/$M revenue — 29% lower than benchmark)
"""


def text_to_pdf_bytes(text: str) -> bytes:
    """Convert text to PDF using fpdf2 (pure Python, no system deps)."""
    from fpdf import FPDF

    # Replace unicode chars that Courier can't handle
    text = text.replace("—", "--").replace("–", "-").replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"').replace("•", "*").replace("±", "+/-")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Courier", size=8)
    for line in text.split("\n"):
        safe_line = line[:120].encode("latin-1", errors="replace").decode("latin-1")
        pdf.cell(0, 4, safe_line, new_x="LMARGIN", new_y="NEXT")
    return pdf.output()


def main():
    s3 = boto3.client("s3", region_name=REGION)
    bedrock = boto3.client("bedrock-agent", region_name=REGION)

    # 1. Create S3 bucket if needed
    print(f"1. Ensuring S3 bucket: {BUCKET_NAME}")
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
        print("   Bucket exists")
    except Exception:
        s3.create_bucket(
            Bucket=BUCKET_NAME,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        print("   Created bucket")

    # 2. Generate and upload PDFs with metadata
    print("2. Generating and uploading sample documents...")
    for portfolio_id, fund in DOCUMENTS.items():
        docs = [
            (f"source_docs/{portfolio_id}_pds.pdf", generate_pds_content(portfolio_id, fund), "pds"),
            (f"source_docs/{portfolio_id}_quarterly.pdf", generate_quarterly_content(portfolio_id, fund), "quarterly_report"),
        ]
        if portfolio_id != "pf_macq001":
            docs.append((f"source_docs/{portfolio_id}_ddq.pdf", generate_ddq_content(portfolio_id, fund), "ddq"))
        if portfolio_id == "pf_aef001":
            docs.append((f"source_docs/{portfolio_id}_esg.pdf", generate_esg_content(portfolio_id, fund), "esg_report"))

        for key, content, doc_type in docs:
            pdf_bytes = text_to_pdf_bytes(content)
            s3.put_object(Bucket=BUCKET_NAME, Key=key, Body=pdf_bytes, ContentType="application/pdf")

            doc_id = key.replace("source_docs/", "").replace(".pdf", "")
            metadata = {
                "metadataAttributes": {
                    "portfolio_id": portfolio_id,
                    "doc_id": doc_id,
                    "doc_type": doc_type,
                }
            }
            metadata_key = key + ".metadata.json"
            s3.put_object(Bucket=BUCKET_NAME, Key=metadata_key, Body=json.dumps(metadata), ContentType="application/json")
            print(f"   Uploaded: {key}")

    # 3. Create Knowledge Base
    print("3. Creating Bedrock Knowledge Base...")

    kb_role_arn = f"arn:aws:iam::{ACCOUNT}:role/AmazonBedrockExecutionRoleForKnowledgeBase_dd"

    # Create IAM role for KB if needed
    iam = boto3.client("iam", region_name=REGION)
    try:
        iam.get_role(RoleName="AmazonBedrockExecutionRoleForKnowledgeBase_dd")
        print("   KB role exists")
    except iam.exceptions.NoSuchEntityException:
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
            RoleName="AmazonBedrockExecutionRoleForKnowledgeBase_dd",
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Role for Portfolio DD Knowledge Base",
        )
        iam.put_role_policy(
            RoleName="AmazonBedrockExecutionRoleForKnowledgeBase_dd",
            PolicyName="BedrockKBPolicy",
            PolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:ListBucket"],
                        "Resource": [f"arn:aws:s3:::{BUCKET_NAME}", f"arn:aws:s3:::{BUCKET_NAME}/*"],
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
        time.sleep(10)  # Wait for IAM propagation

    # Check if KB already exists
    existing_kbs = bedrock.list_knowledge_bases()["knowledgeBaseSummaries"]
    dd_kb = next((kb for kb in existing_kbs if kb["name"] == "PortfolioDDKnowledgeBase"), None)

    if dd_kb:
        kb_id = dd_kb["knowledgeBaseId"]
        print(f"   KB already exists: {kb_id}")
    else:
        kb_response = bedrock.create_knowledge_base(
            name="PortfolioDDKnowledgeBase",
            description="Fund documents for Portfolio Due Diligence analysis",
            roleArn=kb_role_arn,
            knowledgeBaseConfiguration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0",
                },
            },
            storageConfiguration={
                "type": "PINECONE_SERVERLESS" if False else "OPENSEARCH_SERVERLESS",
            },
        )
        kb_id = kb_response["knowledgeBase"]["knowledgeBaseId"]
        print(f"   Created KB: {kb_id}")
        time.sleep(5)

    # 4. Create/update data source
    print("4. Setting up S3 data source...")
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
                    "bucketArn": f"arn:aws:s3:::{BUCKET_NAME}",
                    "inclusionPrefixes": ["source_docs/"],
                },
            },
        )
        ds_id = ds_response["dataSource"]["dataSourceId"]
        print(f"   Created data source: {ds_id}")

    # 5. Sync the data source
    print("5. Starting data source sync...")
    bedrock.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    print("   Sync started (will complete in 2-5 minutes)")

    # 6. Output the KB ID
    print(f"\n{'='*60}")
    print(f"Knowledge Base ID: {kb_id}")
    print(f"S3 Bucket: {BUCKET_NAME}")
    print(f"{'='*60}")
    print(f"\nNext steps:")
    print(f"1. Wait for sync to complete (check in Bedrock console)")
    print(f"2. Add to CDK stack: DDEvidenceGatherer environmentVariables:")
    print(f"   BEDROCK_KB_ID: '{kb_id}'")
    print(f"3. Redeploy to wire the KB ID to the agent")

    # Save KB ID to SSM for later use
    ssm = boto3.client("ssm", region_name=REGION)
    ssm.put_parameter(
        Name="/wealth-management-portal/dd-knowledge-base-id",
        Value=kb_id,
        Type="String",
        Overwrite=True,
    )
    print(f"\nSaved KB ID to SSM: /wealth-management-portal/dd-knowledge-base-id")


if __name__ == "__main__":
    main()
