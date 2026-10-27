
import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.device_usage import DeviceUsage
from app.models.investigation import Investigation
from app.models.risk_assessment import RiskAssessment
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

CUSTOMER_ID_RE = re.compile(r"\b(CUST-[A-Za-z0-9_-]+)\b", re.IGNORECASE)
TRANSACTION_ID_RE = re.compile(r"\b(TXN-[A-Za-z0-9_-]+)\b", re.IGNORECASE)
DEVICE_ID_RE = re.compile(r"\b(dev-[A-Za-z0-9_-]+|device-[A-Za-z0-9_-]+)\b", re.IGNORECASE)
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")


def _value(value: Any, default: Any = None) -> Any:
    """Convert missing ORM values to a JSON-friendly default."""
    return default if value is None else value


def _id_prefix(value: Any, length: int = 8) -> str:
    value = str(value or "unknown")
    return value if len(value) <= length else f"{value[:length]}..."


def _retrieve_context(
    db: Session,
    query: str = "",
    customer_id: str | None = None,
    transaction_id: str | None = None,
    device_id: str | None = None,
    investigation_id: str | None = None,
) -> dict[str, Any]:
    """Retrieve database context relevant to a user's question."""
    context: dict[str, Any] = {}
    query = query or ""
    q_lower = query.lower()

    # Extract human-readable IDs from the question.
    if not customer_id:
        match = CUSTOMER_ID_RE.search(query)
        if match:
            customer_id = match.group(1)
        else:
            match = re.search(r"\bcustomer\s+([A-Za-z0-9_-]+)", query, re.IGNORECASE)
            ignored = {
                "is", "has", "profile", "activity", "suspicious", "records",
                "data", "history", "details", "flagged", "with", "who",
                "below", "under", "above", "over", "less", "more",
                "amount", "transaction", "txn", "money", "dollars",
            }
            if match and match.group(1).lower() not in ignored:
                # Only extract a customer ID if the query isn't about amount thresholds
                # for a group of customers (e.g. "customers below 5000$")
                if not q_lower.strip().startswith(("show", "list", "which", "every", "retrieve", "find")):
                    # Check if the query is asking about a specific transaction amount
                    has_amount_query = any(k in q_lower for k in ("below", "under", "above", "over", "less than", "greater than", "amount", "$", "transaction amount"))
                    if not has_amount_query:
                        customer_id = match.group(1)

    if not transaction_id:
        match = TRANSACTION_ID_RE.search(query)
        if match:
            transaction_id = match.group(1)

    if not device_id:
        match = DEVICE_ID_RE.search(query)
        if match:
            device_id = match.group(1)

    # Resolve UUIDs against known tables rather than assuming which entity it is.
    uuid_match = UUID_RE.search(query)
    if uuid_match:
        candidate = uuid_match.group(0)
        if not customer_id:
            customer = db.query(Customer).filter(
                (Customer.id == candidate) | (Customer.external_id == candidate)
            ).first()
            if customer:
                customer_id = candidate
        if not transaction_id:
            txn = db.query(Transaction).filter(
                (Transaction.id == candidate) | (Transaction.external_id == candidate)
            ).first()
            if txn:
                transaction_id = candidate
        if not investigation_id:
            investigation = db.query(Investigation).filter(
                Investigation.id == candidate
            ).first()
            if investigation:
                investigation_id = candidate
        if not device_id:
            device = db.query(DeviceUsage).filter(
                DeviceUsage.device_id == candidate
            ).first()
            if device:
                device_id = candidate

    # Avoid silently attaching an unrelated customer to collection/group queries.
    group_terms = ("all", "show", "list", "which", "every", "retrieve", "find")
    is_group_query = any(term in q_lower for term in group_terms)

    if not customer_id and not is_group_query and any(
        term in q_lower
        for term in ("customer", "suspicious", "unusual", "who", "account", "why", "flagged", "person")
    ):
        top_customer = (
            db.query(Customer)
            .order_by(
                Customer.suspicious_transactions.desc(),
                Customer.previous_fraud_reports.desc(),
            )
            .first()
        )
        if not top_customer or (
            (top_customer.suspicious_transactions or 0) == 0
            and (top_customer.previous_fraud_reports or 0) == 0
        ):
            latest_alert = (
                db.query(Alert)
                .filter(Alert.customer_id.isnot(None))
                .order_by(Alert.created_at.desc())
                .first()
            )
            if latest_alert and latest_alert.customer_id:
                top_customer = db.query(Customer).filter(
                    (Customer.id == latest_alert.customer_id)
                    | (Customer.external_id == latest_alert.customer_id)
                ).first()

        if not top_customer:
            flagged_txn = (
                db.query(Transaction)
                .filter(Transaction.status.in_(["review", "blocked"]))
                .order_by(Transaction.created_at.desc())
                .first()
            )
            if flagged_txn and flagged_txn.customer_id:
                top_customer = db.query(Customer).filter(
                    (Customer.id == flagged_txn.customer_id)
                    | (Customer.external_id == flagged_txn.customer_id)
                ).first()

        if not top_customer:
            top_customer = db.query(Customer).order_by(Customer.created_at.desc()).first()

        if top_customer:
            customer_id = top_customer.id

    if not device_id and any(
        term in q_lower for term in ("device", "hardware", "fingerprint", "connected")
    ):
        latest_device = (
            db.query(DeviceUsage.device_id)
            .order_by(DeviceUsage.last_seen_at.desc())
            .first()
        )
        if latest_device:
            device_id = latest_device[0]

    if not investigation_id and any(
        term in q_lower for term in ("investigation", "summarize", "summary", "case")
    ):
        latest_investigation = (
            db.query(Investigation).order_by(Investigation.created_at.desc()).first()
        )
        if latest_investigation:
            investigation_id = latest_investigation.id

    # Investigation details.
    if investigation_id:
        investigation = db.query(Investigation).filter(
            Investigation.id == investigation_id
        ).first()
        if investigation:
            context["investigation"] = {
                "id": investigation.id,
                "status": investigation.status,
                "notes": investigation.notes,
                "conclusion": investigation.conclusion,
                "created_at": str(investigation.created_at),
                "closed_at": str(investigation.closed_at),
                "analyst_id": investigation.analyst_id,
            }
            customer_id = customer_id or investigation.customer_id
            transaction_id = transaction_id or investigation.transaction_id

    # Transaction details and its risk assessment.
    if transaction_id:
        txn = db.query(Transaction).filter(
            (Transaction.id == transaction_id)
            | (Transaction.external_id == transaction_id)
        ).first()
        if txn:
            context["transaction"] = {
                "id": txn.id,
                "external_id": txn.txn_external_id,
                "amount": float(txn.amount or 0),
                "status": txn.status,
                "payment_method": txn.payment_method,
                "country": txn.country,
                "created_at": str(txn.created_at),
                "device_id": txn.device_id,
                "ip": getattr(txn, "ip_address_str", None),
            }
            customer_id = customer_id or txn.customer_id
            assessment = (
                db.query(RiskAssessment)
                .filter(RiskAssessment.transaction_id == txn.id)
                .order_by(RiskAssessment.created_at.desc())
                .first()
            )
            if assessment:
                context["risk_assessment"] = {
                    "risk_score": assessment.risk_score,
                    "risk_level": assessment.risk_level,
                    "decision": assessment.decision,
                    "explanation": assessment.ai_explanation,
                }

    # Customer details.
    if customer_id:
        customer = db.query(Customer).filter(
            (Customer.id == customer_id) | (Customer.external_id == customer_id)
        ).first()
        if customer:
            profile = (
                db.query(CustomerRiskProfile)
                .filter(CustomerRiskProfile.customer_id == customer.id)
                .first()
            )
            alerts = (
                db.query(Alert)
                .filter(Alert.customer_id == customer.id)
                .order_by(Alert.created_at.desc())
                .limit(5)
                .all()
            )
            recent_txns = (
                db.query(Transaction)
                .filter(Transaction.customer_id == customer.id)
                .order_by(Transaction.created_at.desc())
                .limit(5)
                .all()
            )
            context["customer"] = {
                "id": customer.id,
                "external_id": customer.external_id,
                "total_transactions": customer.total_transactions or 0,
                "suspicious_transactions": customer.suspicious_transactions or 0,
                "previous_fraud_reports": customer.previous_fraud_reports or 0,
                "avg_amount": float(customer.avg_amount or 0),
                "max_amount": float(customer.max_amount or 0),
                "risk_score": profile.risk_score if profile else None,
                "risk_level": profile.risk_level if profile else "LOW",
                "alerts_count": len(alerts),
                "recent_transactions": [
                    {
                        "id": t.id,
                        "amount": float(t.amount or 0),
                        "status": t.status,
                        "country": t.country,
                        "date": str(t.created_at),
                    }
                    for t in recent_txns
                ],
            }

            all_customer_txns = (
                db.query(Transaction)
                .filter(Transaction.customer_id == customer.id)
                .order_by(Transaction.created_at.desc())
                .limit(200)
                .all()
            )
            context["cust_txns_by_amount"] = {
                str(customer.id): [
                    {
                        "id": t.id,
                        "amount": float(t.amount or 0),
                        "status": t.status,
                        "country": t.country,
                        "created_at": str(t.created_at),
                    }
                    for t in all_customer_txns
                ]
            }
        else:
            context["customer_lookup_error"] = f"No customer found for ID {customer_id}."

    # Device details.
    if device_id:
        usages = db.query(DeviceUsage).filter(DeviceUsage.device_id == device_id).all()
        device_txns = (
            db.query(Transaction)
            .filter(Transaction.device_id == device_id)
            .order_by(Transaction.created_at.desc())
            .limit(10)
            .all()
        )
        context["device"] = {
            "device_id": device_id,
            "connected_accounts_count": len({u.customer_id for u in usages}),
            "connected_customer_ids": list({u.customer_id for u in usages}),
            "transaction_count": len(device_txns),
            "transactions": [
                {
                    "id": t.id,
                    "customer_id": t.customer_id,
                    "amount": float(t.amount or 0),
                    "status": t.status,
                    "date": str(t.created_at),
                }
                for t in device_txns
            ],
        }

    # Platform summary and recent alerts.
    total_transactions = db.query(Transaction).count()
    total_customers = db.query(Customer).count()
    active_alert_count = db.query(Alert).filter(Alert.status == "new").count()
    recent_alerts = (
        db.query(Alert).order_by(Alert.created_at.desc()).limit(5).all()
    )
    context["platform_summary"] = {
        "total_transactions": total_transactions,
        "total_customers": total_customers,
        "active_alerts_count": active_alert_count,
        "recent_alerts": [
            {
                "id": a.id,
                "title": a.title,
                "severity": a.severity,
                "status": a.status,
                "customer_id": a.customer_id,
                "created_at": str(a.created_at),
            }
            for a in recent_alerts
        ],
    }

    high_risk_profiles = (
        db.query(CustomerRiskProfile, Customer)
        .join(Customer, CustomerRiskProfile.customer_id == Customer.id)
        .filter(CustomerRiskProfile.risk_level == "HIGH")
        .order_by(CustomerRiskProfile.risk_score.desc())
        .limit(20)
        .all()
    )
    context["high_risk_customers"] = [
        {
            "customer_id": profile.customer_id,
            "customer_external_id": customer.external_id,
            "risk_score": profile.risk_score,
            "risk_level": profile.risk_level,
            "total_transactions": customer.total_transactions or 0,
        }
        for profile, customer in high_risk_profiles
    ]

    low_risk_profiles = (
        db.query(CustomerRiskProfile, Customer)
        .join(Customer, CustomerRiskProfile.customer_id == Customer.id)
        .filter(CustomerRiskProfile.risk_level == "LOW")
        .order_by(CustomerRiskProfile.risk_score.asc())
        .limit(20)
        .all()
    )
    context["low_risk_customers"] = [
        {
            "customer_id": profile.customer_id,
            "customer_external_id": customer.external_id,
            "risk_score": profile.risk_score,
            "risk_level": profile.risk_level,
            "total_transactions": customer.total_transactions or 0,
        }
        for profile, customer in low_risk_profiles
    ]

    high_risk_txns = (
        db.query(Transaction)
        .filter(Transaction.risk_level == "HIGH")
        .order_by(Transaction.created_at.desc())
        .limit(50)
        .all()
    )
    context["high_risk_transactions"] = [
        {
            "id": t.txn_external_id or t.id,
            "amount": float(t.amount or 0),
            "status": t.status,
            "country": t.country,
            "risk_level": t.risk_level,
        }
        for t in high_risk_txns
    ]

    recent_transactions = (
        db.query(Transaction).order_by(Transaction.created_at.desc()).limit(50).all()
    )
    context["recent_transactions"] = [
        {
            "id": t.txn_external_id or t.id,
            "amount": float(t.amount or 0),
            "status": t.status,
            "country": t.country,
            "risk_level": t.risk_level,
            "created_at": str(t.created_at),
        }
        for t in recent_transactions
    ]
    context["transaction_list"] = context["recent_transactions"]

    status_groups: dict[str, list[dict[str, Any]]] = {}
    for txn in recent_transactions:
        status = (txn.status or "other").lower()
        status_groups.setdefault(status, []).append(
            {
                "id": txn.txn_external_id or txn.id,
                "amount": float(txn.amount or 0),
                "status": txn.status,
                "country": txn.country,
                "created_at": str(txn.created_at),
            }
        )
    context["transactions_by_status"] = status_groups

    return context


def _deterministic_assistant_answer(query: str, context: dict[str, Any]) -> str:
    """Answer questions from retrieved database context only."""
    q = (query or "").lower()
    platform = context.get("platform_summary", {})
    has_customer = "customer" in q
    has_transaction = "transaction" in q or "txn" in q
    has_device = "device" in q
    has_alert = "alert" in q
    has_investigation = "investigation" in q or "summarize" in q or "summary" in q or "case" in q
    has_risk = "risk" in q
    has_suspicious = "suspicious" in q or "flagged" in q or "why" in q
    has_amount = any(k in q for k in ("amount", "$"))
    has_less = any(k in q for k in ("less", "under", "below"))
    has_greater = any(k in q for k in ("greater", "over", "more", "above", ">"))
    has_blocked = "blocked" in q
    has_review = "review" in q
    has_approved = "approved" in q or "approve" in q
    has_failed = "failed" in q or "declined" in q
    has_high = "high" in q
    has_low = "low" in q
    has_recent = "recent" in q
    has_analytics = any(k in q for k in ("analytics", "statistics", "dashboard", "overview", "metrics", "system", "total", "how many", "how much", "summary", "platform"))
    has_explanation = "explain" in q or "why" in q or "reason" in q or "cause" in q

    # Alerts (highest priority)
    if has_alert:
        alerts = platform.get("recent_alerts", [])
        if alerts:
            lines = [
                f"• [{str(a.get('severity') or 'unknown').upper()}] {a.get('title') or 'Untitled alert'} "
                f"(Status: {a.get('status')}, ID: {_id_prefix(a.get('id'))})"
                for a in alerts
            ]
            return (
                f"Active alerts: {platform.get('active_alerts_count', 0)}\n"
                + "\n".join(lines)
            )
        return "No recent alerts were found."

    # Fraud intelligence overview (catch-all for "summary", "overview", "what", "tell me" questions)
    if has_analytics and not has_customer and not has_transaction and not has_device:
        customer = context.get("customer", {})
        return (
            f"Fraud Intelligence Brief:\n"
            f"Monitoring {platform.get('total_transactions', 0)} transactions across "
            f"{platform.get('total_customers', 0)} customers, with "
            f"{platform.get('active_alerts_count', 0)} new alert(s).\n\n"
            f"You can ask about a customer (e.g. 'CUST-DEMO-001'), device, "
            f"or recent activity directly in your prompt."
        )

    # Amount threshold queries (high priority for numeric questions)
    if has_amount or has_greater or has_less:
        threshold = None
        if has_less:
            numbers = NUMBER_RE.findall(q)
            if numbers:
                try:
                    threshold = float(numbers[-1].replace(",", ""))
                except ValueError:
                    threshold = None
        elif "$" in q:
            match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", q)
            if match:
                try:
                    threshold = float(match.group(1).replace(",", ""))
                except ValueError:
                    threshold = None
        if threshold is not None:
            txns = context.get("transaction_list", [])
            if has_less:
                matches = [t for t in txns if float(t.get("amount") or 0) < threshold]
                prefix = f"Transactions less than ${threshold:,.2f}"
            else:
                matches = [t for t in txns if float(t.get("amount") or 0) > threshold]
                prefix = f"Transactions greater than ${threshold:,.2f}"
            if matches:
                lines = [
                    f"• {t.get('id')} | ${float(t.get('amount') or 0):,.2f} | "
                    f"{str(t.get('status') or 'unknown').upper()} | {t.get('country') or 'N/A'}"
                    for t in matches
                ]
                return (
                    f"{prefix} ({len(matches)} shown from the latest {len(txns)} records):\n"
                    + "\n".join(lines)
                )
            return f"No transactions matching this threshold were found."

    # Customer-specific queries (with any amount/risk/activity related terms)
    if has_customer:
        # Handle 'low risk' / 'high risk' / 'medium risk' customer queries as collections
        if has_low and "risk" in q and not customer_id:
            low_custs = context.get("low_risk_customers", [])
            if low_custs:
                lines = []
                for c in low_custs:
                    lines.append(
                        f"• {c.get('customer_external_id') or c.get('customer_id')} | "
                        f"Risk Score: {c.get('risk_score', 'N/A')}/100 | Total Txns: {c.get('total_transactions', 0)}"
                    )
                return f"Low-risk customers ({len(low_custs)} shown):\n" + "\n".join(lines)
            return "No LOW risk customers were found."
        if has_high and "risk" in q and not customer_id:
            high_custs = context.get("high_risk_customers", [])
            if high_custs:
                lines = []
                for c in high_custs:
                    lines.append(
                        f"• {c.get('customer_external_id') or c.get('customer_id')} | "
                        f"Risk Score: {c.get('risk_score', 'N/A')}/100 | Total Txns: {c.get('total_transactions', 0)}"
                    )
                return f"High-risk customers ({len(high_custs)} shown):\n" + "\n".join(lines)
            return "No HIGH risk customers were found."

        customer_data = context.get("customer")
        if customer_data:
            # Customer risk explanation questions
            if has_suspicious or has_risk or has_explanation:
                # Only list risk indicators if the customer is actually HIGH risk or
                # the specific question is about suspicious/flagged status.
                if customer_data.get("risk_score", 0) >= 70 or "flagged" in q or "suspicious" in q:
                    reasons = []
                    if customer_data.get("suspicious_transactions", 0) > 0:
                        reasons.append(f"{customer_data['suspicious_transactions']} transaction(s) marked suspicious/blocked.")
                    if customer_data.get("previous_fraud_reports", 0) > 0:
                        reasons.append(f"{customer_data['previous_fraud_reports']} confirmed fraud incident(s) reported.")
                    if reasons:
                        reason_text = "\n".join(f"• {r}" for r in reasons)
                        return f"Customer {customer_data['external_id']} is flagged as suspected due to:\n{reason_text}"
                # For MEDIUM risk customers, explain the level without reporting as 'suspicious'
                # For HIGH risk customers, we already returned above. 
                # For LOW risk customers, use the default answer.
                if has_risk or has_explanation:
                    level = customer_data.get("risk_level", "LOW")
                    score = customer_data.get("risk_score", 0) or 0
                    if score == 0:
                        return f"Customer {customer_data['external_id']} has a {level} risk level with no severe suspicious fraud markers currently active."
                    return f"Customer {customer_data['external_id']} has a {level} risk level with a risk score of {score}/100. This means the customer has moderate indicators that do not meet the HIGH risk threshold (70 or above)."
                return f"Customer {customer_data['external_id']} has a {customer_data['risk_level']} risk level with no severe suspicious fraud markers currently active."
        elif context.get("customer_lookup_error"):
            return context["customer_lookup_error"]
    
    # Transaction-related queries
    if has_transaction:
        # Status queries
        if has_blocked or has_review or has_approved or has_failed:
            requested_status = None
            if has_blocked:
                requested_status = "blocked"
            elif has_review:
                requested_status = "review"
            elif has_approved:
                requested_status = "approved"
            elif has_failed:
                requested_status = "failed"
            if requested_status:
                txns = context.get("transaction_list", [])
                aliases = {"failed": {"failed", "declined", "failure"}}
                allowed = aliases.get(requested_status, {requested_status})
                status_txns = [t for t in txns if str(t.get("status") or "").lower() in allowed]
                if status_txns:
                    lines = [
                        f"• {t.get('id')} | ${t.get('amount', 0):,.2f} | {t.get('status').upper()} | {t.get('country') or 'N/A'}"
                        for t in status_txns
                    ]
                    return f"Transactions with status '{requested_status}':\n" + "\n".join(lines)
                return f"No transactions with status '{requested_status}' were found."
        
        # High-risk transactions
        if has_high:
            txns = context.get("high_risk_transactions", [])
            if txns:
                lines = [
                    f"• {t.get('id')} | ${t.get('amount', 0):,.2f} | {t.get('status').upper()} | {t.get('country') or 'N/A'} | Risk: {t.get('risk_level') or 'HIGH'}"
                    for t in txns
                ]
                return f"HIGH risk transactions ({len(txns)} shown):\n" + "\n".join(lines)
        
        # Recent transactions
        if has_recent:
            recent = context.get("recent_transactions", [])
            if recent:
                lines = [
                    f"• {t.get('id')} | ${t.get('amount', 0):,.2f} | {t.get('status').upper()} | {t.get('country') or 'N/A'} | {t.get('created_at', 'date unavailable')}"
                    for t in recent
                ]
                return f"Recent transactions:\n" + "\n".join(lines)

    # Device queries
    if has_device and context.get("device"):
        device = context["device"]
        txns = device.get("transactions", [])
        txn_list = "\n".join(
            f"• Txn {t.get('id')} | Amount: ${t.get('amount', 0):,.2f} | Status: {t.get('status')} | Customer: {t.get('customer_id')}"
            for t in txns
        ) if txns else "• No transactions recorded on this device."
        return (
            f"Device '{device['device_id']}' is linked to {device.get('connected_accounts_count', 0)} account(s) "
            f"and has processed {len(txns)} recorded transactions:\n\n{txn_list}"
        )

    # Investigation queries
    if has_investigation and context.get("investigation"):
        inv = context["investigation"]
        customer = context.get("customer", {})
        txn = context.get("transaction", {})
        assessment = context.get("risk_assessment", {})
        return (
            f"Investigation Dossier Summary (ID: {inv['id']}):\n"
            f"• Status: {inv['status'].upper()}\n"
            f"• Customer: {customer.get('external_id', 'Unknown')} (Risk Level: {customer.get('risk_level', 'Unknown')})\n"
            f"• Flagged Transaction: ${txn.get('amount', 0):,.2f} ({txn.get('status', 'Unknown')})\n"
            f"• Risk Score: {assessment.get('risk_score', 'N/A')} ({assessment.get('risk_level', 'N/A')})\n"
            f"• Analyst Notes: {inv.get('notes') or 'No notes recorded.'}\n"
            f"• Conclusion: {inv.get('conclusion') or 'Under active review.'}"
        )

    # Alert questions
    if has_alert:
        alerts = platform.get("recent_alerts", [])
        if alerts:
            lines = [
                f"• [{a.get('severity').upper()}] {a.get('title')} (Status: {a.get('status')}, ID: {a.get('id')})"
                for a in alerts
            ]
            return (
                f"Currently tracking {platform.get('active_alerts_count', 0)} open alert(s) on the platform:\n\n"
                f"{chr(10).join(lines)}\n\n"
                f"You can ask for details on any customer or transaction linked to these alerts."
            )
        return "There are currently no open or pending fraud alerts in the database."

    # Investigation summary (when not captured above)
    if has_investigation and context.get("investigation"):
        inv = context["investigation"]
        customer = context.get("customer", {})
        txn = context.get("transaction", {})
        assessment = context.get("risk_assessment", {})
        return (
            f"Investigation Dossier Summary (ID: {inv['id']}):\n"
            f"• Status: {inv['status'].upper()}\n"
            f"• Customer: {customer.get('external_id', 'Unknown')} (Risk Level: {customer.get('risk_level', 'Unknown')})\n"
            f"• Flagged Transaction: ${txn.get('amount', 0):,.2f} ({txn.get('status', 'Unknown')})\n"
            f"• Risk Score: {assessment.get('risk_score', 'N/A')} ({assessment.get('risk_level', 'N/A')})\n"
            f"• Analyst Notes: {inv.get('notes') or 'No notes recorded.'}\n"
            f"• Conclusion: {inv.get('conclusion') or 'Under active review.'}"
        )
    
    # Default answers based on context presence
    if context.get("customer"):
        c = context["customer"]
        return (
            f"Customer Profile: {c['external_id']} | Risk Level: {c['risk_level']} | "
            f"Total Txns: {c['total_transactions']} | Avg Spend: ${float(c.get('avg_amount', 0) or 0):,.2f}."
        )

    plat = context.get("platform_summary", {})
    return (
        f"Fraud Intelligence Brief:\n"
        f"Monitoring {plat.get('total_transactions', 0)} transactions across {plat.get('total_customers', 0)} accounts "
        f"with {plat.get('active_alerts_count', 0)} active alert(s).\n\n"
        f"You can ask about a customer, device, transaction, investigation, or fraud-related issues directly."
    )


async def ask_investigation_assistant(
    db: Session,
    query: str,
    customer_id: str | None = None,
    transaction_id: str | None = None,
    device_id: str | None = None,
    investigation_id: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Return (answer, mode, referenced_data) for a grounded assistant query."""
    context = _retrieve_context(
        db,
        query=query,
        customer_id=customer_id,
        transaction_id=transaction_id,
        device_id=device_id,
        investigation_id=investigation_id,
    )
    deterministic_answer = _deterministic_assistant_answer(query, context)

    if not (settings.GEMINI_API_KEY or settings.OPENAI_API_KEY):
        return deterministic_answer, "deterministic_engine", context

    prompt = (
        "You are an AI fraud investigation assistant. Answer accurately using ONLY "
        "the database context below. If the answer cannot be determined from these "
        "records, say so. Do not invent facts. Cite exact IDs, amounts, and dates.\n\n"
        f"Database Context:\n{json.dumps(context, indent=2, default=str)}\n\n"
        f"Analyst Question: {query}\n"
        "Give a concise, direct, professional answer."
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if settings.GEMINI_API_KEY:
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    "gemini-1.5-flash:generateContent"
                    f"?key={settings.GEMINI_API_KEY}"
                )
                response = await client.post(
                    url,
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                )
                if response.status_code == 200:
                    payload = response.json()
                    answer = (
                        payload.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                        .strip()
                    )
                    if answer:
                        return answer, "llm", context
                else:
                    logger.warning("Gemini returned HTTP %s", response.status_code)

            elif settings.OPENAI_API_KEY:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 300,
                    },
                )
                if response.status_code == 200:
                    payload = response.json()
                    answer = (
                        payload.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                    if answer:
                        return answer, "llm", context
                else:
                    logger.warning("OpenAI returned HTTP %s", response.status_code)
    except Exception:
        logger.exception("LLM assistant call failed; using deterministic answer")

    return deterministic_answer, "deterministic_engine", context
