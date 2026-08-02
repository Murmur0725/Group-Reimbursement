import unittest
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    ReimbursementRecord,
    ReimbursementStatusEvent,
    SyncRun,
)
from app.services.record_queries import search_by_amount
from app.services.notion_sync import apply_record_data, normalize_notion_page


def _settings():
    return SimpleNamespace(
        number_property_name="编号",
        name_property_name="名称",
        status_property_name="状态",
        amount_property_name="金额",
        applicant_property_name="申请人",
        reimburse_to_property_name="报销给谁",
        remark_property_name="备注",
        files_property_name="文件和媒体",
    )


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class BackendServiceTests(unittest.TestCase):
    def test_normalize_notion_page_handles_status_and_empty_fields(self):
        page = {
            "id": "page-1",
            "url": "https://notion.so/page-1",
            "created_time": "2026-07-01T00:00:00.000Z",
            "last_edited_time": "2026-07-02T00:00:00.000Z",
            "properties": {
                "编号": {"type": "rich_text", "rich_text": [{"plain_text": "A001"}]},
                "名称": {"type": "title", "title": [{"plain_text": "试剂"}]},
                "状态": {"type": "status", "status": {"name": "已提交"}},
                "金额": {"type": "number", "number": 182},
                "申请人": {"type": "people", "people": [{"name": "Alice"}]},
                "报销给谁": {"type": "people", "people": [{"name": "Bob"}]},
                "备注": {"type": "rich_text", "rich_text": []},
                "文件和媒体": {
                    "type": "files",
                    "files": [
                        {
                            "name": "invoice.pdf",
                            "type": "external",
                            "external": {"url": "https://example.com/invoice.pdf"},
                        }
                    ],
                },
            },
        }

        data = normalize_notion_page(page, _settings())

        self.assertEqual(data.notion_page_id, "page-1")
        self.assertEqual(data.status, "已提交")
        self.assertEqual(data.amount, 182.0)
        self.assertEqual(data.applicant, "Alice")
        self.assertEqual(len(data.attachments), 1)
        self.assertTrue(data.content_hash)

    def test_normalize_notion_page_falls_back_to_amount_prefixed_number(self):
        page = {
            "id": "page-amount",
            "properties": {
                "编号": {"type": "rich_text", "rich_text": []},
                "名称": {"type": "title", "title": []},
                "状态": {"type": "select", "select": None},
                "金额（含税）": {"type": "number", "number": 47.5},
                "申请人": {"type": "people", "people": []},
                "报销给谁": {"type": "people", "people": []},
                "备注": {"type": "rich_text", "rich_text": []},
                "文件和媒体": {"type": "files", "files": []},
            },
        }

        data = normalize_notion_page(page, _settings())

        self.assertEqual(data.amount, 47.5)

    def test_apply_record_data_creates_status_event_and_version(self):
        session = _session()
        sync_run = SyncRun(id=1, mode="test", status="running")
        session.add(sync_run)
        session.commit()

        page = {
            "id": "page-1",
            "properties": {
                "编号": {"type": "rich_text", "rich_text": [{"plain_text": "A001"}]},
                "名称": {"type": "title", "title": [{"plain_text": "试剂"}]},
                "状态": {"type": "select", "select": {"name": "已提交"}},
                "金额": {"type": "number", "number": 100},
                "申请人": {"type": "people", "people": []},
                "报销给谁": {"type": "people", "people": []},
                "备注": {"type": "rich_text", "rich_text": []},
                "文件和媒体": {"type": "files", "files": []},
            },
        }
        data = normalize_notion_page(page, _settings())

        result = apply_record_data(
            session,
            data,
            sync_run,
            now=datetime(2026, 7, 5),
            today=datetime(2026, 7, 5).date(),
        )
        session.commit()

        self.assertEqual(result, "created")
        self.assertEqual(session.scalar(select(ReimbursementRecord)).status, "已提交")
        event = session.scalar(select(ReimbursementStatusEvent))
        self.assertIsNone(event.old_status)
        self.assertEqual(event.new_status, "已提交")

    def test_amount_search_orders_by_distance(self):
        session = _session()
        now = datetime(2026, 7, 5)
        session.add_all(
            [
                ReimbursementRecord(
                    notion_page_id="a",
                    title="a",
                    amount=181.5,
                    content_hash="a",
                    first_synced_at=now,
                    last_synced_at=now,
                ),
                ReimbursementRecord(
                    notion_page_id="b",
                    title="b",
                    amount=182.0,
                    content_hash="b",
                    first_synced_at=now,
                    last_synced_at=now,
                ),
                ReimbursementRecord(
                    notion_page_id="c",
                    title="c",
                    amount=184.5,
                    content_hash="c",
                    first_synced_at=now,
                    last_synced_at=now,
                ),
            ]
        )
        session.commit()

        results = search_by_amount(session, 182.0, tolerance=1)

        self.assertEqual([item.notion_page_id for item in results], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
