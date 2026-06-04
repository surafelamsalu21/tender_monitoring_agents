import asyncio
from unittest.mock import MagicMock, patch

from app.agents.agent2 import TenderDetailAgent


def test_un_careers_detail_api_fallback_builds_notice_text():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "status": 1,
        "data": {
            "jobId": 278616,
            "postingTitle": "Consultancy on Coordinator of the High-level Working Group",
            "dept": {"name": "Economic Commission for Africa"},
            "jc": {"name": "Consultants"},
            "jf": {"Name": "Economic Affairs"},
            "dutyStation": [{"description": "ADDIS ABABA"}],
            "startDate": "2026-06-03T04:00:00.000Z",
            "endDate": "2026-06-17T03:59:59.000Z",
            "inspiraURL": "https://inspira.un.org/apply/278616",
            "jobDescription": (
                "<div><div>Result of Service</div>"
                "<div>Provide substantive and coordination support.</div></div>"
            ),
        },
    }

    with patch("requests.get", return_value=response) as mock_get:
        agent = TenderDetailAgent.__new__(TenderDetailAgent)
        text = asyncio.run(
            agent._scrape_un_careers_detail_api(
                "https://careers.un.org/jobSearchDescription/278616?language=en"
            )
        )

    assert text is not None
    assert "Consultancy on Coordinator of the High-level Working Group" in text
    assert "ADDIS ABABA" in text
    assert "2026-06-17T03:59:59.000Z" in text
    assert "Provide substantive and coordination support." in text
    mock_get.assert_called_once_with(
        "https://careers.un.org/api/public/opening/joV2/278616/en",
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )


def test_eu_funding_detail_api_fallback_builds_detailed_info():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "totalResults": 1,
        "results": [
            {
                "reference": "98a56ee5-bec7-4944-9589-373d609cf350-CN",
                "summary": "AAP2022 Support Measures Regional MIP Sub-Saharan Africa",
                "metadata": {
                    "title": ["AAP2022 Support Measures Regional MIP Sub-Saharan Africa"],
                    "cftId": ["98a56ee5-bec7-4944-9589-373d609cf350-CN"],
                    "callIdentifier": ["EC-INTPA/JIB/2026/EA-RP/0070"],
                    "contractType": ["31095498"],
                    "startDate": ["2026-05-18T00:00:00.000+0000"],
                    "deadlineDate": ["2026-06-17T00:00:59.000+0000"],
                    "description": ["Strengthen IGAD institutional effectiveness."],
                },
            }
        ],
    }

    agent = TenderDetailAgent.__new__(TenderDetailAgent)
    with patch("requests.post", return_value=response) as mock_post:
        info = asyncio.run(
            agent._extract_eu_funding_detailed_info_api(
                "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
                "screen/opportunities/tender-details/98a56ee5-bec7-4944-9589-373d609cf350-CN",
                {
                    "title": "AAP2022 Support Measures Regional MIP Sub-Saharan Africa",
                    "url": "https://example.test/eu",
                },
            )
        )

    assert info is not None
    assert info["extraction_status"] == "api"
    assert info["detailed_title"] == "AAP2022 Support Measures Regional MIP Sub-Saharan Africa"
    assert info["deadline"].isoformat() == "2026-06-17"
    assert "Strengthen IGAD" in info["detailed_description"]
    mock_post.assert_called_once()
