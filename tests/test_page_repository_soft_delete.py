"""PageRepository soft-delete behavior preserves existing tenders."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.page import MonitoredPage
from app.models.tender import Tender
from app.repositories.page_repository import PageRepository


def test_delete_page_soft_deletes_and_preserves_tenders(tmp_path):
    db_file = tmp_path / "page_repo_soft_delete.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        page = MonitoredPage(
            name="UN Careers",
            url="https://careers.un.org/jobopening",
            crawl_strategy="un_careers",
        )
        db.add(page)
        db.commit()
        db.refresh(page)

        tender = Tender(
            title="Existing Tender",
            url="https://careers.un.org/jobSearchDescription/123?language=en",
            page_id=page.id,
            category="consultancy",
        )
        db.add(tender)
        db.commit()
        db.refresh(tender)

        repo = PageRepository()
        deleted = repo.delete_page(db, page.id)
        assert deleted is True

        archived_page = db.query(MonitoredPage).filter(MonitoredPage.id == page.id).first()
        assert archived_page is not None
        assert archived_page.is_deleted is True
        assert archived_page.is_active is False
        assert archived_page.url.startswith("https://careers.un.org/jobopening#archived-")

        preserved_tender = db.query(Tender).filter(Tender.id == tender.id).first()
        assert preserved_tender is not None
        assert preserved_tender.page_id == page.id

        visible_pages = repo.get_all_pages(db)
        assert all(p.id != page.id for p in visible_pages)

        # Re-adding the same source URL should now be possible.
        recreated = repo.create_page(
            db,
            name="UN Careers New",
            url="https://careers.un.org/jobopening",
            crawl_strategy="un_careers",
        )
        assert recreated.id != page.id
    finally:
        db.close()
