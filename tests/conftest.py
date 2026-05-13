"""Pytest configuration — register custom markers."""


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: tests that require Neo4j or other external services")
