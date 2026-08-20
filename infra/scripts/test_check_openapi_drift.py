import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_openapi_drift import compare_operations, extract_client_operations, normalize_client_path


class OpenApiDriftTests(unittest.TestCase):
    def test_normalizes_template_path_to_openapi_shape(self) -> None:
        self.assertEqual(
            normalize_client_path("/agentic/workflows/${encodeURIComponent(workflowId)}/retry"),
            "/agentic/workflows/{param}/retry",
        )

    def test_extracts_method_and_path(self) -> None:
        source = """
        this.get('/today');
        this.post(`/agentic/workflows/${workflowId}/retry`, body);
        """
        self.assertEqual(
            extract_client_operations(source),
            {("GET", "/today"), ("POST", "/agentic/workflows/{param}/retry")},
        )

    def test_reports_client_operations_missing_from_openapi(self) -> None:
        missing = compare_operations(
            {("GET", "/today"), ("POST", "/agentic/workflows/{param}/retry")},
            {("GET", "/today")},
        )
        self.assertEqual(missing, [("POST", "/agentic/workflows/{param}/retry")])


if __name__ == "__main__":
    unittest.main()
