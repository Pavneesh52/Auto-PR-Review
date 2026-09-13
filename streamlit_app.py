"""PR Review Agent - API-based Testing & Monitoring Suite.

Interactive Streamlit interface for testing webhooks, HITL approvals,
feedback loops, and observability metrics.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any

import httpx
import streamlit as st

# Configure Streamlit page
st.set_page_config(
    page_title="PR Review Agent Console",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Styling & Theme
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #6b7280;
        margin-bottom: 1.5rem;
    }
    .metric-box {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .badge-critical { background-color: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }
    .badge-high { background-color: #ffedd5; color: #9a3412; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }
    .badge-medium { background-color: #fef9c3; color: #854d0e; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }
    .badge-low { background-color: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }
    .badge-status { padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions & API Client
# ─────────────────────────────────────────────────────────────────────────────


def compute_github_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute sha256 HMAC signature as GitHub does."""
    mac = hmac.new(secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


class APIClient:
    """Synchronous HTTP client for interacting with the PR Review Agent API."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_health(self) -> tuple[int, dict[str, Any] | str, float]:
        start = time.time()
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                res = client.get("/health")
                elapsed = (time.time() - start) * 1000
                return res.status_code, (res.json() if res.status_code == 200 else res.text), elapsed
        except Exception as e:
            return 0, str(e), (time.time() - start) * 1000

    def get_metrics(self) -> tuple[int, dict[str, Any] | str]:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                res = client.get("/metrics")
                return res.status_code, res.json() if res.status_code == 200 else res.text
        except Exception as e:
            return 0, str(e)

    def get_repo_metrics(self, repo: str) -> tuple[int, dict[str, Any] | str]:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                res = client.get(f"/repos/{repo}/metrics")
                return res.status_code, res.json() if res.status_code == 200 else res.text
        except Exception as e:
            return 0, str(e)

    def get_repo_feedback(self, repo: str) -> tuple[int, dict[str, Any] | str]:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                res = client.get(f"/repos/{repo}/feedback")
                return res.status_code, res.json() if res.status_code == 200 else res.text
        except Exception as e:
            return 0, str(e)

    def send_webhook(
        self,
        payload: dict[str, Any],
        secret: str,
        event_type: str = "pull_request",
        custom_signature: str | None = None,
    ) -> tuple[int, dict[str, Any] | str, float]:
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = custom_signature or compute_github_signature(raw_body, secret)
        delivery_id = str(uuid.uuid4())

        headers = {
            "Content-Type": "application/json",
            "X-GitHub-Event": event_type,
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": signature,
        }

        start = time.time()
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                res = client.post("/webhook", content=raw_body, headers=headers)
                elapsed = (time.time() - start) * 1000
                try:
                    data = res.json()
                except Exception:
                    data = res.text
                return res.status_code, data, elapsed
        except Exception as e:
            return 0, str(e), (time.time() - start) * 1000

    def list_reviews(
        self,
        status: str | None = None,
        repo: str | None = None,
        limit: int = 50,
    ) -> tuple[int, list[dict[str, Any]] | str]:
        try:
            params: dict[str, Any] = {"limit": limit}
            if status and status != "all":
                params["status"] = status
            if repo:
                params["repo"] = repo

            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                res = client.get("/reviews", params=params)
                return res.status_code, res.json() if res.status_code == 200 else res.text
        except Exception as e:
            return 0, str(e)

    def get_review(self, review_id: int) -> tuple[int, dict[str, Any] | str]:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                res = client.get(f"/reviews/{review_id}")
                return res.status_code, res.json() if res.status_code == 200 else res.text
        except Exception as e:
            return 0, str(e)

    def approve_review(
        self,
        review_id: int,
        approver: str,
        decision: str,
        comment: str = "",
        edited_findings_json: str | None = None,
    ) -> tuple[int, dict[str, Any] | str]:
        body = {
            "approver": approver,
            "decision": decision,
            "comment": comment,
            "edited_findings_json": edited_findings_json,
        }
        try:
            with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
                res = client.post(f"/reviews/{review_id}/approve", json=body)
                try:
                    data = res.json()
                except Exception:
                    data = res.text
                return res.status_code, data
        except Exception as e:
            return 0, str(e)

    def submit_feedback(
        self,
        finding_id: int,
        reviewer: str,
        is_positive: bool,
        comment: str = "",
    ) -> tuple[int, dict[str, Any] | str]:
        body = {
            "reviewer": reviewer,
            "is_positive": is_positive,
            "comment": comment,
        }
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                res = client.post(f"/findings/{finding_id}/feedback", json=body)
                return res.status_code, res.json() if res.status_code == 200 else res.text
        except Exception as e:
            return 0, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar Setup
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuration")

    api_url = st.text_input(
        "Backend API Base URL",
        value=os.getenv("API_BASE_URL", "http://localhost:8000"),
        help="Base URL where FastAPI is running",
    )

    webhook_secret = st.text_input(
        "GitHub Webhook Secret",
        value=os.getenv("GITHUB_WEBHOOK_SECRET", "dev_webhook_secret"),
        type="password",
        help="HMAC secret used to verify webhook signatures",
    )

    api_client = APIClient(base_url=api_url)

    st.markdown("---")
    st.subheader("📡 Server Status")

    status_code, health_resp, ping_ms = api_client.get_health()
    if status_code == 200:
        st.success(f"🟢 Connected ({ping_ms:.1f}ms)")
        st.caption(f"Health Response: `{health_resp}`")
    else:
        st.error(f"🔴 Offline (Status {status_code})")
        st.caption(f"Error: `{health_resp}`")

    st.markdown("---")
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Main Layout
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="main-title">🤖 PR Review Agent Testing Console</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Test, simulate, and observe the AI-powered PR Review Agent backend.</div>',
    unsafe_allow_html=True,
)

tab_metrics, tab_webhook, tab_reviews, tab_feedback = st.tabs([
    "🏥 Health & Metrics",
    "🚀 Webhook Simulator",
    "📋 Reviews & HITL Gate",
    "👍 Finding Feedback",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: Health & Observability Metrics
# ─────────────────────────────────────────────────────────────────────────────
with tab_metrics:
    st.header("System Metrics & Health Monitor")

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        refresh_metrics = st.button("📊 Fetch Latest Metrics")

    status_code, metrics_data = api_client.get_metrics()

    if status_code == 200 and isinstance(metrics_data, dict):
        db_m = metrics_data.get("database", {})
        queue_m = metrics_data.get("queue", {})
        rl_m = metrics_data.get("rate_limits", {})
        sys_m = metrics_data.get("system", {})

        # Top summary cards
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Total Reviews", db_m.get("total_reviews", 0))
        with c2:
            st.metric("Reviews (24h)", db_m.get("reviews_last_24h", 0))
        with c3:
            st.metric("Total Tokens", f"{db_m.get('total_tokens', 0):,}")
        with c4:
            st.metric("Est. Cost", f"${db_m.get('total_cost_usd', 0.0):.4f}")
        with c5:
            st.metric("Queue Pending", queue_m.get("pending", 0))

        st.markdown("---")

        # Findings breakdown & Rate limiter
        col_sev, col_rate = st.columns(2)

        with col_sev:
            st.subheader("Findings by Severity")
            sev_counts = db_m.get("findings_by_severity", {})
            if sev_counts:
                st.bar_chart(sev_counts)
            else:
                st.info("No findings recorded in database yet.")

            avg_conf = db_m.get("avg_confidence", 0.0)
            st.caption(f"Average Finding Confidence: **{avg_conf:.1%}**")

        with col_rate:
            st.subheader("Rate Limits & Queue Status")
            st.json({
                "queue": queue_m,
                "rate_limits": rl_m,
                "system": sys_m,
            })

        st.markdown("---")

        # Repo specific lookup
        st.subheader("🔍 Repository Deep Dive")
        repo_lookup = st.text_input("Enter Repository Full Name (e.g. `octocat/Hello-World`)", value="octocat/Hello-World")
        if st.button("Fetch Repo Metrics"):
            st_code, repo_res = api_client.get_repo_metrics(repo_lookup)
            if st_code == 200:
                st.json(repo_res)
            else:
                st.warning(f"Could not load repository metrics: {repo_res}")

    else:
        st.error(f"Could not fetch metrics from backend (Status: {status_code})")
        st.info("Ensure the FastAPI backend is running via `python -m uvicorn pr_review_agent.app:main` or `pr-review-agent serve`.")
        if metrics_data:
            st.code(str(metrics_data))


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: Webhook & PR Simulator
# ─────────────────────────────────────────────────────────────────────────────
with tab_webhook:
    st.header("GitHub Webhook Simulator")
    st.write("Send simulated GitHub Pull Request webhook payloads to test HMAC verification, Redis event queueing, and background processing.")

    # Preset templates
    st.subheader("1. Choose or Customize Payload")
    col_t1, col_t2, col_t3 = st.columns(3)

    action = "opened"
    repo_name = "octocat/Hello-World"
    pr_num = 42
    pr_title = "Add user authentication and password validation"
    pr_body = "Implements password hashing and session tokens."
    head_sha = "6dcb09b5b57875f334f61aebed695e2e4193db5e"
    base_branch = "main"
    head_branch = "feature/auth"

    sample_choice = st.selectbox(
        "Quick Presets",
        [
            "Custom PR Payload",
            "PR Opened - Security Risk (SQL Injection / Hardcoded Secret)",
            "PR Synchronize - Performance Optimization",
            "PR Reopened - Refactor",
        ],
    )

    if sample_choice == "PR Opened - Security Risk (SQL Injection / Hardcoded Secret)":
        action = "opened"
        pr_num = 101
        pr_title = "feat: Add user search endpoint"
        pr_body = "Adds direct database query endpoint for users."
    elif sample_choice == "PR Synchronize - Performance Optimization":
        action = "synchronize"
        pr_num = 102
        pr_title = "perf: Optimize caching for reviews"
        pr_body = "Adds Redis caching layer."
    elif sample_choice == "PR Reopened - Refactor":
        action = "reopened"
        pr_num = 103
        pr_title = "refactor: Cleanup orchestrator graph"
        pr_body = "Clean up redundant nodes in pipeline."

    with st.expander("🛠️ Customize Payload Details", expanded=(sample_choice == "Custom PR Payload")):
        c1, c2 = st.columns(2)
        with c1:
            action = st.selectbox("Action", ["opened", "synchronize", "reopened", "closed", "edited"], index=["opened", "synchronize", "reopened", "closed", "edited"].index(action) if action in ["opened", "synchronize", "reopened", "closed", "edited"] else 0)
            repo_name = st.text_input("Repository Full Name", value=repo_name)
            pr_num = st.number_input("PR Number", min_value=1, value=pr_num)
            author = st.text_input("Author Login", value="octocat")
        with c2:
            pr_title = st.text_input("PR Title", value=pr_title)
            head_sha = st.text_input("Head SHA", value=head_sha)
            base_branch = st.text_input("Base Branch", value=base_branch)
            head_branch = st.text_input("Head Branch", value=head_branch)

        pr_body = st.text_area("PR Body", value=pr_body, height=80)

    # Build GitHub Webhook Payload
    webhook_payload = {
        "action": action,
        "number": pr_num,
        "pull_request": {
            "number": pr_num,
            "title": pr_title,
            "body": pr_body,
            "state": "open",
            "user": {"login": author},
            "head": {"sha": head_sha, "ref": head_branch},
            "base": {"ref": base_branch},
            "draft": False,
        },
        "repository": {
            "full_name": repo_name,
            "name": repo_name.split("/")[-1] if "/" in repo_name else repo_name,
            "owner": {"login": repo_name.split("/")[0] if "/" in repo_name else "owner"},
            "private": False,
        },
    }

    with st.expander("📄 View JSON Payload Preview", expanded=False):
        st.json(webhook_payload)

    st.subheader("2. Security & Signature Options")
    col_sig1, col_sig2 = st.columns([2, 1])
    with col_sig1:
        test_invalid_sig = st.checkbox("Simulate Invalid Signature (Negative Test)", value=False)
    with col_sig2:
        event_header = st.text_input("X-GitHub-Event Header", value="pull_request")

    custom_sig = "sha256=invalid_signature_hash_test_123" if test_invalid_sig else None

    st.subheader("3. Send Webhook")
    if st.button("🚀 Fire Webhook to /webhook", type="primary"):
        with st.spinner("Posting webhook..."):
            status, res_body, elapsed = api_client.send_webhook(
                payload=webhook_payload,
                secret=webhook_secret,
                event_type=event_header,
                custom_signature=custom_sig,
            )

        if status == 200:
            st.success(f"✅ Webhook Accepted ({status}) in {elapsed:.1f}ms")
            st.json(res_body)
            st.info("The event has been enqueued to Redis and is being processed by the background processor.")
        elif status == 401:
            st.error(f"🔒 Unauthorized ({status}): Invalid HMAC signature")
            st.json(res_body)
        else:
            st.error(f"❌ Webhook Failed ({status}) in {elapsed:.1f}ms")
            if isinstance(res_body, dict):
                st.json(res_body)
            else:
                st.code(str(res_body))


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: Reviews & HITL Gate
# ─────────────────────────────────────────────────────────────────────────────
with tab_reviews:
    st.header("Reviews & Human-In-The-Loop Approval")
    st.write("Inspect reviews generated by the agent, review findings by severity, and test the HITL approval / edit / reject flow.")

    # Filter controls
    col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
    with col_f1:
        filter_status = st.selectbox(
            "Filter Status",
            ["all", "awaiting_approval", "pending", "in_progress", "completed", "failed", "skipped"],
        )
    with col_f2:
        filter_repo = st.text_input("Filter Repo (optional)", value="")
    with col_f3:
        st.write("")
        st.write("")
        refresh_reviews = st.button("🔄 Refresh Reviews List")

    status_code, reviews_list = api_client.list_reviews(status=filter_status, repo=filter_repo)

    if status_code == 200 and isinstance(reviews_list, list):
        if not reviews_list:
            st.info("No reviews found matching the filters.")
        else:
            st.subheader(f"Found {len(reviews_list)} Review(s)")

            # Format options for selectbox
            review_options = {
                f"ID #{r['id']} | PR #{r['pr_number']} - {r['repository']} [{r['status'].upper()}] - {r.get('title', '')}": r['id']
                for r in reviews_list
            }

            selected_label = st.selectbox("Select Review to Inspect", list(review_options.keys()))
            selected_id = review_options[selected_label]

            # Fetch detailed review
            r_status, review_detail = api_client.get_review(selected_id)

            if r_status == 200 and isinstance(review_detail, dict):
                st.markdown("---")

                # Review Header Information
                st.subheader(f"Review #{review_detail['id']} — {review_detail.get('repository')}")
                st.markdown(f"**PR #{review_detail.get('pr_number')}**: {review_detail.get('title') or 'No title'}")

                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    status_val = review_detail.get("status", "unknown")
                    color = "orange" if status_val == "awaiting_approval" else ("green" if status_val == "completed" else "gray")
                    st.markdown(f"**Status**: :{color}[{status_val.upper()}]")
                with col_m2:
                    st.metric("Total Findings", review_detail.get("total_comments", 0))
                with col_m3:
                    st.metric("Tokens Used", f"{review_detail.get('total_tokens', 0):,}")
                with col_m4:
                    st.metric("Estimated Cost", f"${review_detail.get('estimated_cost_usd', 0.0):.4f}")

                # Summary
                if review_detail.get("summary"):
                    st.markdown("### 📝 Review Summary")
                    st.markdown(review_detail["summary"])

                # Findings List
                findings = review_detail.get("findings", [])
                st.markdown(f"### 🔍 Findings ({len(findings)})")

                if not findings:
                    st.info("No findings reported for this review.")
                else:
                    for i, finding in enumerate(findings, start=1):
                        sev = finding.get("severity", "medium").lower()
                        sev_badge = f'<span class="badge-{sev}">{sev.upper()}</span>'

                        with st.expander(f"#{i} [{sev.upper()}] {finding.get('file', '')}:{finding.get('line', '')} — {finding.get('title', '')}", expanded=(i <= 3)):
                            st.markdown(f"**Category**: `{finding.get('category')}` | **Agent**: `{finding.get('source_agent')}` | **Confidence**: `{finding.get('confidence', 0.0):.0%}` | {sev_badge}", unsafe_allow_html=True)
                            st.write(finding.get("description", ""))

                            if finding.get("suggestion"):
                                st.markdown("**Suggested Fix:**")
                                st.code(finding.get("suggestion"), language="python")

                            # Quick feedback button inside finding
                            col_fb1, col_fb2, col_fb3 = st.columns([1, 1, 3])
                            with col_fb1:
                                if st.button("👍 Helpful", key=f"btn_up_{finding['id']}"):
                                    fb_code, fb_res = api_client.submit_feedback(finding["id"], reviewer="tester", is_positive=True)
                                    if fb_code == 200:
                                        st.success("Recorded positive feedback!")
                            with col_fb2:
                                if st.button("👎 Incorrect", key=f"btn_down_{finding['id']}"):
                                    fb_code, fb_res = api_client.submit_feedback(finding["id"], reviewer="tester", is_positive=False)
                                    if fb_code == 200:
                                        st.warning("Recorded negative feedback!")

                # HITL Approval Action Box
                st.markdown("---")
                st.subheader("🛡️ Human-In-The-Loop Approval Action")

                if review_detail.get("status") == "awaiting_approval":
                    st.warning("⚠️ This review is currently **awaiting operator approval** before posting to GitHub.")
                else:
                    st.info(f"Current Review Status: **{review_detail.get('status')}**")

                with st.form(key=f"hitl_form_{selected_id}"):
                    c_app1, c_app2 = st.columns(2)
                    with c_app1:
                        approver_name = st.text_input("Approver Name / Handle", value="security-lead")
                    with c_app2:
                        decision_choice = st.selectbox("Decision", ["approved", "rejected", "edited"])

                    approval_comment = st.text_area("Operator Comment (Optional)", value="")

                    edited_json = None
                    if decision_choice == "edited":
                        st.info("Edit the findings JSON below that will be posted to GitHub:")
                        default_json_str = json.dumps([
                            {
                                "file": f.get("file"),
                                "line": f.get("line"),
                                "severity": f.get("severity"),
                                "category": f.get("category"),
                                "title": f.get("title"),
                                "description": f.get("description"),
                                "suggestion": f.get("suggestion"),
                                "confidence": f.get("confidence"),
                                "source_agent": f.get("source_agent"),
                            }
                            for f in findings
                        ], indent=2)
                        edited_json = st.text_area("Edited Findings JSON Array", value=default_json_str, height=200)

                    submit_approval = st.form_submit_button("Submit Approval Decision", type="primary")

                    if submit_approval:
                        with st.spinner("Processing decision..."):
                            app_code, app_res = api_client.approve_review(
                                review_id=selected_id,
                                approver=approver_name,
                                decision=decision_choice,
                                comment=approval_comment,
                                edited_findings_json=edited_json,
                            )
                        if app_code == 200:
                            st.success(f"Decision recorded successfully! ({decision_choice})")
                            st.json(app_res)
                            st.rerun()
                        else:
                            st.error(f"Approval failed ({app_code}): {app_res}")

    else:
        st.error(f"Failed to retrieve reviews from backend (Status: {status_code})")
        if reviews_list:
            st.code(str(reviews_list))


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: Finding Feedback Tester
# ─────────────────────────────────────────────────────────────────────────────
with tab_feedback:
    st.header("Developer Feedback & Guidance Loop")
    st.write("Submit developer feedback (Phase 16) and inspect how negative feedback feeds back into prompt guidance to prevent recurring false positives.")

    col_fb_in, col_fb_stats = st.columns(2)

    with col_fb_in:
        st.subheader("Submit Finding Feedback")
        with st.form("feedback_form"):
            target_finding_id = st.number_input("Finding ID", min_value=1, value=1)
            reviewer_user = st.text_input("Reviewer Username", value="dev-user")
            fb_rating = st.radio("Was this finding accurate & helpful?", ["Positive (Accurate)", "Negative (False Positive / Unhelpful)"])
            fb_comment = st.text_area("Feedback Comment", placeholder="Explain why this finding was helpful or a false positive...")

            is_pos = (fb_rating == "Positive (Accurate)")
            btn_sub_fb = st.form_submit_button("Submit Feedback", type="primary")

            if btn_sub_fb:
                code_fb, res_fb = api_client.submit_feedback(
                    finding_id=target_finding_id,
                    reviewer=reviewer_user,
                    is_positive=is_pos,
                    comment=fb_comment,
                )
                if code_fb == 200:
                    st.success(f"Feedback successfully recorded for finding #{target_finding_id}!")
                    st.json(res_fb)
                else:
                    st.error(f"Error ({code_fb}): {res_fb}")

    with col_fb_stats:
        st.subheader("Repository Feedback Summary")
        fb_repo_input = st.text_input("Repository Name", value="octocat/Hello-World", key="fb_repo_stat")
        if st.button("Check Repository Feedback Stats"):
            code_fbs, res_fbs = api_client.get_repo_feedback(fb_repo_input)
            if code_fbs == 200 and isinstance(res_fbs, dict):
                st.json(res_fbs)

                tot = res_fbs.get("total_feedback", 0)
                pos = res_fbs.get("positive", 0)
                neg = res_fbs.get("negative", 0)
                rate = res_fbs.get("acceptance_rate", 0.0)

                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    st.metric("Total Feedback", tot)
                with col_s2:
                    st.metric("Positive Rate", f"{rate:.1%}")
                with col_s3:
                    st.metric("False Positives", neg)
            else:
                st.warning(f"Unable to load feedback stats: {res_fbs}")
