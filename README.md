# Tender Agent V3 🤖

An AI-powered tender monitoring system that automatically scrapes, categorizes, and notifies teams about relevant tenders.

## Features

- 🕷️ **Web Scraping**: Uses `crawl4ai` to scrape tender pages efficiently.
- 🤖 **AI Agents (Multi-Agent Workflow)**: Employs a sophisticated three-agent pipeline powered by Langchain and LangGraph for intelligent processing:
    - **Agent 1 (Screening extraction)**: Applies the Precise **screening checklist** (Steps 1–3), keeps opportunities that pass the Step 1 relevance rule (≥ 3 of 5 YES), and persists screening metadata.
    - **Agent 2 (Detail Agent)**: Scrapes individual tender pages for non-duplicate, filtered tenders, extracts comprehensive details, and validates dates, skipping expired or old items.
    - **Agent 3 (Email Composer Agent)**: Generates rich HTML notifications for successfully processed opportunities (screening-aligned).
- 📊 **Checklist-aligned keywords**: Keyword Manager uses **sector**, **activity_fit**, **geography**, and **source_tag** to support matching and reporting.
- 📧 **Rich Email Notifications**: Sends HTML notifications to a single **opportunity screening** recipient list configured in Settings.
- ⏰ **Scheduled Monitoring**: Runs periodically (configurable, default: every 3 hours) to check for new tenders.
- 💾 **Database Management**: Utilizes SQLAlchemy for robust interaction with a database (SQLite by default) to store and manage all system data.
- 🎯 **Keyword Management**: Configure checklist-aligned keywords (**sector**, **activity_fit**, **geography**, **source_tag**) via the dashboard.
- 🖥️ **Web Dashboard**: A React-based frontend application provides a user interface for:
    - Managing monitored pages and keywords.
    - Viewing extracted tenders and their details.
    - Monitoring system status and activity.
    - Configuring email notification settings.

## System Architecture

The system is composed of a Python FastAPI backend, a React frontend, and a multi-agent AI pipeline.

```mermaid
graph TD
    subgraph Frontend_React [Frontend (React)]
        A[Web Dashboard] -->|API Calls| B(FastAPI Backend)
    end

    subgraph Backend_FastAPI [Backend (FastAPI)]
        B --> C{Scheduler}
        B --> D[API Endpoints]
        D --> E[Database (SQLAlchemy)]
        C --> F[Scraper (crawl4ai)]
        F --> G(Agent 1 - Extraction)
        G --> E
        G --> H(Agent 2 - Detail Enrichment)
        H --> E
        H --> I(Agent 3 - Email Composition)
        I --> J[Email Service]
    end

    J --> K((User Inboxes))

    style A fill:#A2D2FF,stroke:#333,stroke-width:2px
    style B fill:#BDE0FE,stroke:#333,stroke-width:2px
    style C fill:#FFC8DD,stroke:#333,stroke-width:2px
    style D fill:#FFC8DD,stroke:#333,stroke-width:2px
    style E fill:#CDB4DB,stroke:#333,stroke-width:2px
    style F fill:#FFAFCC,stroke:#333,stroke-width:2px
    style G fill:#FFAFCC,stroke:#333,stroke-width:2px
    style H fill:#FFAFCC,stroke:#333,stroke-width:2px
    style I fill:#FFAFCC,stroke:#333,stroke-width:2px
    style J fill:#BDE0FE,stroke:#333,stroke-width:2px
    style K fill:#A2D2FF,stroke:#333,stroke-width:2px
```

**Workflow:**

1.  **Scheduling**: The `TenderScheduler` periodically triggers the scraping process.
2.  **Scraping**: `TenderScraper` (using `crawl4ai`) fetches content from monitored web pages.
3.  **Agent 1 (Screening extraction)**: Parses scraped content against the screening checklist, extracts opportunities that pass Step 1, and saves basic rows (including screening JSON). Duplicates are filtered.
4.  **Agent 2 (Detail Enrichment)**: For new, valid tenders, this agent scrapes the individual tender URL, extracts detailed information (requirements, full description, contact info, etc.), and performs further date validation. Detailed info is saved to a secondary database (DB2 - `detailed_tenders` table).
5.  **Agent 3 (Email Composition)**: Composes professional HTML emails (individual or digest) for tenders successfully processed by Agent 2.
6.  **Notification**: The `EnhancedEmailService` sends composed emails to recipients on the **opportunity screening** list. Fallback notifications use the same list.
7.  **User Interaction**: Users interact with the system via the React Web Dashboard to manage pages, keywords, view tenders, and adjust settings.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```
2.  **Install Backend Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Install Frontend Dependencies**:
    ```bash
    cd react-frontend
    npm install
    cd ..
    ```
4.  **Configure Environment**:
    Create a `.env` file in the root directory by copying `.env.example` (if available) or by creating a new one. Update it with your credentials:
    ```env
    OPENAI_API_KEY=your_openai_api_key
    GEMINI_API_KEY=your_gemini_api_key # If used by any agent
    EMAIL_USER=your_email@example.com
    EMAIL_PASSWORD=your_email_app_password
    SCREENING_DEFAULT_TEST_EMAIL=you@example.com
    # Legacy alias still accepted: ESG_TEAM_EMAIL (same purpose as SCREENING_DEFAULT_TEST_EMAIL)
    DATABASE_URL=sqlite:///./tender_monitoring.db # Or your PostgreSQL/MySQL URL
    # Add any other necessary environment variables from app/core/config.py
    ```

### Docker (optional, recommended when Playwright fails on Windows)

The API runs in **Linux** inside the container, so **Playwright and asyncio behave like on macOS/Linux** (no Windows `SelectorEventLoop` / driver issues). Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Windows or Mac.

```bash
docker compose build
docker compose up
```

API: `http://localhost:8000`. Compose sets `DATABASE_URL` to a **named volume** (`/app/data/…`) so data survives image rebuilds; it is separate from a native `sqlite:///./tender_monitoring.db` on the host. Use either Docker or native Python for one environment, or point `DATABASE_URL` at PostgreSQL for shared dev.

## Usage

1.  **Run the Backend Server**:
    ```bash
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ```
    The backend API will be accessible at `http://localhost:8000`.

2.  **Run the Frontend Application**:
    In a new terminal:
    ```bash
    cd react-frontend
    npm start
    ```
    The frontend will typically be accessible at `http://localhost:3000`.

3.  **Access the Web Dashboard**:
    Open your browser and navigate to the frontend URL (e.g., `http://localhost:3000`).

### Component Testing

-   **Backend Tests**:
    ```bash
    pytest
    ```
    (Ensure you have `pytest` installed: `pip install pytest pytest-asyncio`)

-   **Frontend Tests**:
    ```bash
    cd react-frontend
    npm test
    ```

## Configuration

### Default Keywords

Default seeds use checklist-aligned categories (**sector**, **activity_fit**, **geography**, **source_tag**). See `app/core/init_data.py` and extend via the Keyword Manager.

### Email Configuration

-   Ensure `EMAIL_USER` and `EMAIL_PASSWORD` in `.env` match your SMTP provider (e.g. Gmail App Password).
-   Optional **`SCREENING_DEFAULT_TEST_EMAIL`**: default recipient for dev-only email smoke tests (legacy **`ESG_TEAM_EMAIL`** is still read as an alias).
-   Production recipients are stored in the database as **`opportunity_emails`** and managed under **Settings → Email Notifications** in the dashboard.

## Database Schema

The system uses SQLAlchemy and defines the following main tables:

-   **`monitored_pages`**: Stores URLs and settings for pages to be scraped.
-   **`keywords`**: Keywords by category (**sector**, **activity_fit**, **geography**, **source_tag**) and usage statistics.
-   **`tenders`**: Basic extracted opportunities, screening JSON (Steps 1–3), and links to source pages.
-   **`detailed_tenders`**: Comprehensive information for tenders processed by Agent 2 (full descriptions, requirements, contact details, validated dates, etc.). Linked one-to-one with the `tenders` table.
-   **`tender_keywords`**: An association table linking tenders to the keywords they matched.
-   **`crawl_logs`**: Logs each scraping attempt, its status, tenders found, and errors.
-   **`email_notification_settings`**: Recipient list (`opportunity_emails`), preferences, and related config keys.
-   **`email_notification_logs`**: Records notification attempts, including status and errors.

## AI Agent Workflow

The core AI processing is handled by a three-agent pipeline:

1.  **Agent 1 (`TenderExtractionAgent` in `app/agents/agent1.py`; exported as `ScreeningExtractionAgent` for compatibility)**:
    -   Receives markdown/content from the scraper.
    -   Applies the Precise screening checklist (Steps 1–3) via the LLM.
    -   Keeps opportunities that pass Step 1 (≥ 3 of 5 YES) unless configured otherwise.
    -   Outputs structured tender rows with `screening` metadata.

2.  **Agent 2 (TenderDetailAgent)**:
    -   Takes valid, non-duplicate tenders from Agent 1.
    -   Scrapes the individual tender URL for its full content.
    -   Uses an LLM to extract detailed information: full description, requirements, deadlines, contact information, tender value, project duration, etc.
    -   Performs rigorous date validation (publication, submission deadline) and determines urgency.
    -   Skips processing if a tender is found to be expired or too old based on detailed analysis.

3.  **Agent 3 (EmailComposerAgent)**:
    -   Receives successfully processed tenders with detailed information from Agent 2.
    -   Uses an LLM to compose professional, rich HTML email notifications for the **screening_opportunities** stream.
    -   Can generate individual emails or digest-style summaries.

## Email Notifications

-   Emails are composed by **Agent 3**, ensuring they are detailed and well-formatted.
-   Supports both individual tender alerts and digest emails (e.g., daily summary).
-   Includes key information such as title, screening summary, deadline, description, and a direct link to the original tender.
-   Notifications are sent only for new, unnotified tenders.
-   The system marks tenders as notified to prevent duplicate alerts.

## Monitoring

-   The scheduler runs at a configurable interval (default: every 3 hours).
-   All scraping attempts and their outcomes are logged in `crawl_logs`.
-   Email sending status is logged in `email_notification_logs`.
-   The Web Dashboard provides an overview of system status and recent activity.

## Troubleshooting

### Common Issues

1.  **OpenAI/Gemini API Errors**: Check your API keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`) in the `.env` file and ensure your account has sufficient quota.
2.  **Email Failures**: Verify SMTP settings (`SMTP_HOST`, `SMTP_PORT`, `EMAIL_USER`, `EMAIL_PASSWORD`) and ensure an App Password is used if required (e.g., for Gmail). Check `email_notification_logs` for error details.
3.  **Scraping Failures**: Check internet connectivity. Some websites might block automated scraping; ensure compliance with `robots.txt` and terms of service. Check `crawl_logs`.
4.  **Database Errors**: Ensure the `DATABASE_URL` is correct and the database server is running. For SQLite, ensure write permissions in the project directory.

### Logs

-   Application logs are typically output to the console where `uvicorn` is running. Configure `LOG_LEVEL` and `LOG_FILE` in `.env` for more persistent logging.
-   Specific activity logs are stored in the database (`crawl_logs`, `email_notification_logs`).

## Development

### Adding New Monitored Pages or Keywords

These are typically managed via the Web Dashboard. For programmatic additions (e.g., seeding initial data), you would use the respective repositories:

**Example: Adding a Monitored Page**
```python
# main.py or a dedicated script
from app.core.database import SessionLocal
from app.repositories.page_repository import PageRepository
from app.models.page import MonitoredPage # Ensure MonitoredPage is imported if not auto-loaded by Base

db = SessionLocal()
page_repo = PageRepository()

new_page = page_repo.create_page(
    db=db,
    name="Example Tender Source",
    url="https://example.com/tenders",
    description="Official tender portal for Example Corp."
)
print(f"Added page: {new_page.name}")
db.close()
```

**Example: Adding a Keyword**
```python
# main.py or a dedicated script
from app.core.database import SessionLocal
from app.repositories.keyword_repository import KeywordRepository
from app.models.keyword import Keyword # Ensure Keyword is imported

db = SessionLocal()
keyword_repo = KeywordRepository()

new_keyword = keyword_repo.create_keyword(
    db=db,
    keyword="carbon footprint",
    category="sector",
    description="Relates to carbon emissions and environmental impact"
)
print(f"Added keyword: {new_keyword.keyword}")
db.close()
```

## Future Enhancements

-   [ ] Advanced filtering and search capabilities on the Web Dashboard.
-   [ ] Multi-language support for tender content processing and UI.
-   [ ] Integration with more tender platforms or APIs.
-   [ ] Slack/Microsoft Teams notifications as an alternative or addition to email.
-   [ ] More sophisticated AI-driven trend analysis of tenders.
-   [ ] User authentication and role-based access control for the dashboard.
-   [ ] API endpoints for external integrations (e.g., feeding tender data into other systems).

## License

This project is for internal use. Please ensure compliance with target websites' `robots.txt` and terms of service when scraping.
# tender_monitoring_agents
