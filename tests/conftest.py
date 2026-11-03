import pytest

from app.ingestion import FixtureSource
from app.models import InvestigationInput


@pytest.fixture
async def snapshot():
    return (
        await FixtureSource().ingest(
            InvestigationInput(title="Architecture", body="Explain the limiter")
        )
    )[0]
