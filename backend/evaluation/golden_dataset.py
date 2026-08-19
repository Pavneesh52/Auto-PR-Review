from typing: List, Dict, Any
from dataclasses import dataclass
from uuid import UUID


@dataclass
class GoldenPR:
    id: str
    repo: str
    pr_number: int
    pr_title: str
    diff: str
    expected_findings: List[Dict[str, Any]]
    metadata: Dict[str, Any]


GOLDEN_DATASET = [
    GoldenPR(
        id="sql-injection-001",
        repo="test/repo",
        pr_number=1,
        pr_title="Add user search endpoint",
        diff="""
--- a/app/api/users.py
+++ b/app/api/users.py
@@ -10,7 +10,7 @@ def search_users(query: str):
     cursor = db.cursor()
-    cursor.execute(f"SELECT * FROM users WHERE name LIKE '%{query}%'")
+    cursor.execute("SELECT * FROM users WHERE name LIKE %s", (f"%{query}%",))
     return cursor.fetchall()
""",
        expected_findings=[
            {
                "agent_type": "security",
                "severity": "CRITICAL",
                "category": "injection",
                "file_path": "app/api/users.py",
                "line_start": 12,
            }
        ],
        metadata={"type": "security", "cwe": "CWE-89"},
    ),
    GoldenPR(
        id="missing-test-001",
        repo="test/repo",
        pr_number=2,
        pr_title="Add payment processing",
        diff="""
--- a/services/payment.py
+++ b/services/payment.py
@@ -0,0 +1,20 @@
+def process_payment(amount: float, currency: str) -> bool:
+    if amount <= 0:
+        raise ValueError("Amount must be positive")
+    return stripe.charge(amount, currency)
""",
        expected_findings=[
            {
                "agent_type": "tests",
                "severity": "HIGH",
                "category": "missing_test",
                "file_path": "services/payment.py",
                "line_start": 1,
            }
        ],
        metadata={"type": "tests"},
    ),
    GoldenPR(
        id="missing-docstring-001",
        repo="test/repo",
        pr_number=3,
        pr_title="Add user service",
        diff="""
--- a/services/user.py
+++ b/services/user.py
@@ -0,0 +1,10 @@
+class UserService:
+    def get_user(self, user_id: str):
+        return db.query(User).filter(User.id == user_id).first()
+
+    def create_user(self, name: str, email: str):
+        user = User(name=name, email=email)
+        db.add(user)
+        db.commit()
+        return user
""",
        expected_findings=[
            {
                "agent_type": "docs",
                "severity": "MEDIUM",
                "category": "missing_docstring",
                "file_path": "services/user.py",
                "line_start": 1,
            }
        ],
        metadata={"type": "docs"},
    ),
]


def get_golden_dataset() -> List[GoldenPR]:
    return GOLDEN_DATASET


def get_golden_pr(pr_id: str) -> GoldenPR:
    for pr in GOLDEN_DATASET:
        if pr.id == pr_id:
            return pr
    raise ValueError(f"Golden PR {pr_id} not found")