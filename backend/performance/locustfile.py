"""Representative, bounded load against deterministic or explicitly configured services."""

from uuid import uuid4

from locust import HttpUser, between, task

from performance.workload import REQUEST_NAMES, require_fake_llm_target


class AnalyticsUser(HttpUser):
    """One isolated browser/tab using only synthetic, non-sensitive inputs."""

    wait_time = between(0.2, 0.8)

    def on_start(self) -> None:
        require_fake_llm_target()
        self.headers = {"X-Tab-Id": f"perf-{uuid4().hex}"}
        self.client.post(
            "/chat/select-mode",
            json={"mode": "sql"},
            headers=self.headers,
            name=REQUEST_NAMES["session"],
        )
        self.client.post(
            "/chat",
            json={"message": "Count the synthetic claims"},
            headers=self.headers,
            name=REQUEST_NAMES["chat"],
        )

    @task(2)
    def health(self) -> None:
        self.client.get("/api/health", name=REQUEST_NAMES["health"])

    @task(3)
    def discovery(self) -> None:
        self.client.post(
            "/api/data-discovery/query",
            json={"question": "Find synthetic claims datasets"},
            headers=self.headers,
            name=REQUEST_NAMES["discovery"],
        )

    @task(3)
    def dashboard(self) -> None:
        self.client.get(
            "/api/dashboards/overview", headers=self.headers, name=REQUEST_NAMES["dashboard"]
        )

    @task(2)
    def chat(self) -> None:
        self.client.post(
            "/chat",
            json={"message": "Count the synthetic claims"},
            headers=self.headers,
            name=REQUEST_NAMES["chat"],
        )

    @task(2)
    def execute_sql(self) -> None:
        self.client.post("/chat/execute-sql", headers=self.headers, name=REQUEST_NAMES["sql"])
