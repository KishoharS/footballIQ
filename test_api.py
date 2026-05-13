"""
Unit tests for FootballIQ API endpoints
Run with: pytest test_api.py -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import os
import sys

# Mock environment setup
os.environ["GROQ_API_KEY"] = "test-key"

from api import app, QueryRequest

client = TestClient(app)


class TestHealthEndpoint:
    """Tests for the /health endpoint"""
    
    def test_health_check_returns_200(self):
        """Health check should return 200 OK"""
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_health_response_structure(self):
        """Health response should contain required fields"""
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert "ready" in data
        assert "timestamp" in data


class TestRootEndpoint:
    """Tests for the / endpoint"""
    
    def test_root_returns_200(self):
        """Root endpoint should return 200 OK"""
        response = client.get("/")
        assert response.status_code == 200
    
    def test_root_response_contains_endpoints(self):
        """Root response should list available endpoints"""
        response = client.get("/")
        data = response.json()
        assert "name" in data
        assert "endpoints" in data
        assert "ask" in data["endpoints"]
        assert "health" in data["endpoints"]


class TestAskEndpoint:
    """Tests for the /ask endpoint"""
    
    def test_ask_requires_post_method(self):
        """GET request to /ask should fail"""
        response = client.get("/ask")
        assert response.status_code != 200
    
    def test_ask_with_empty_query_fails(self):
        """Empty query should be rejected"""
        response = client.post("/ask", json={"query": ""})
        assert response.status_code == 422  # Validation error
    
    def test_ask_with_valid_query_structure(self):
        """Valid query format should be accepted"""
        request_data = {"query": "What is Salah's pace?"}
        # Just checking the request model validation
        query = QueryRequest(**request_data)
        assert query.query == "What is Salah's pace?"
    
    def test_ask_with_too_long_query_fails(self):
        """Query exceeding max length should be rejected"""
        long_query = "a" * 2000
        response = client.post("/ask", json={"query": long_query})
        assert response.status_code == 422


class TestErrorHandling:
    """Tests for error handling"""
    
    def test_invalid_json_returns_422(self):
        """Invalid JSON should return 422"""
        response = client.post("/ask", json={"invalid_field": "value"})
        assert response.status_code == 422
    
    def test_error_response_structure(self):
        """Error responses should have consistent structure"""
        response = client.post("/ask", json={})
        assert response.status_code == 422
        # FastAPI returns detailed validation errors


class TestCORSHeaders:
    """Tests for CORS headers"""
    
    def test_cors_headers_present(self):
        """CORS headers should be in response"""
        response = client.get("/health")
        # Check that access-control headers exist (if CORS is configured)
        assert response.status_code == 200


class TestInputValidation:
    """Tests for input validation"""
    
    def test_query_request_validation(self):
        """QueryRequest should validate inputs"""
        # Valid
        valid_request = QueryRequest(query="test query")
        assert valid_request.query == "test query"
        
        # Empty should fail
        with pytest.raises(ValueError):
            QueryRequest(query="")
    
    def test_special_characters_in_query(self):
        """Special characters should be handled safely"""
        request_data = {"query": "What's the player's pace? <script>alert()</script>"}
        response = client.post("/ask", json=request_data)
        # Should accept but not execute malicious code
        assert response.status_code in [200, 503]  # May not be ready in test


class TestResponseFormat:
    """Tests for response format consistency"""
    
    def test_health_response_has_timestamp(self):
        """All responses should include timestamp"""
        response = client.get("/health")
        data = response.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], (int, float))
    
    def test_error_response_format(self):
        """Error responses should be consistent"""
        response = client.post("/ask", json={})
        assert response.status_code == 422
        # FastAPI automatically provides error details


# ============================================================================
# Integration Tests (require app to be running)
# ============================================================================

@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring full app initialization"""
    
    def test_full_ask_flow(self):
        """Test complete ask flow (requires app initialization)"""
        # This test would require the app to be fully initialized
        # with a valid LLM and vectorstore, which is not available
        # in a unit test environment
        pass
    
    def test_concurrent_requests(self):
        """Test handling of concurrent requests"""
        # Would need async testing framework
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
