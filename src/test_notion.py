from typing import List
from uuid import UUID

import pytest

from apis.notion.notional.blocks import (
    Block,
    BulletedListItem,
    Divider,
    Heading1,
    Paragraph,
    Quote,
)
from apis.notion.notional.text import TextObject
from apis.notion.notional.types import (
    MentionObject,
    Title,
)
from apis.notion.page import Page
from apis.notion.session import session

from src.notion import (
    get_all_block_l_recursively,
    get_notion_blocks_from_html,
    replace_href_with_mention_page_in_notion_page,
)
from src.webpage import (
    NOTES_BASE_URL,
    get_title_and_html_from_page_id,
)


def test_get_notion_blocks_from_html_replaces_known_links_with_mention_page() -> None:
    child_notion_uuid = "2d2024dc-88c4-81a8-a441-da44f8ebb664"
    _, html = get_title_and_html_from_page_id("z9vSQjkBVL6dCVC6QhCu4Br")

    block_l = get_notion_blocks_from_html(
        html,
        page_id_to_notion_id_d={
            "z2D1qPwddPktBjpNuwYFVva": child_notion_uuid,
        },
    )

    assert len(block_l) == 10
    assert isinstance(block_l[0], Paragraph)
    assert isinstance(block_l[2], Quote)
    assert isinstance(block_l[6], Divider)
    assert isinstance(block_l[7], Heading1)
    assert block_l[7].plain_text_ == "References"

    mention_l = [
        rtf for rtf in block_l[0]("rich_text")
        if isinstance(rtf, MentionObject)
    ]
    assert len(mention_l) == 1
    assert mention_l[0].mention.page.id == UUID(child_notion_uuid)


def test_get_notion_blocks_from_html_queries_postgres_db() -> None:
    _, html = get_title_and_html_from_page_id("z9vSQjkBVL6dCVC6QhCu4Br")
    block_l = get_notion_blocks_from_html(html)

    mention_l = [
        rtf for rtf in block_l[0]("rich_text")
        if isinstance(rtf, MentionObject)
    ]
    assert len(mention_l) == 1
    assert mention_l[0].mention.page.id == UUID("2d2024dc-88c4-81a8-a441-da44f8ebb664")


@pytest.mark.asyncio
async def test_replace_href_with_mention_page_traverses_nested_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_para = Paragraph["Top-level intro:"]
    nested_bullet = BulletedListItem[
        TextObject[
            "Spaced repetition memory prompts should be concise",
            None,
            f"{NOTES_BASE_URL}/z9vSQjkBVL6dCVC6QhCu4Br",
        ]
    ]
    parent_para.append(nested_bullet)

    all_block_l = get_all_block_l_recursively([parent_para])
    assert len(all_block_l) == 2
    assert all_block_l[1] is nested_bullet

    fake_page = Page(
        id=UUID("36a024dc-88c4-8129-bffe-f46b337e243c"),
        properties={"Name": Title["Parent Page"]},
        content=[parent_para],
    )

    retrieved_uuid_l: List[UUID] = []
    updated_block_l: List[Block] = []

    async def fake_retrieve(
        page_id: UUID,
        do_dump: bool = False,
    ) -> Page:
        retrieved_uuid_l.append(page_id)
        return fake_page

    async def fake_block_update(
        block: Block,
    ) -> Block:
        updated_block_l.append(block)
        return block

    monkeypatch.setattr(Page, "retrieve", fake_retrieve)
    monkeypatch.setattr(session.blocks, "update", fake_block_update)

    parent_page_id_str = "36a024dc-88c4-8129-bffe-f46b337e243c"
    new_page_uuid = UUID("11111111-2222-3333-4444-555555555555")

    updated_count = await replace_href_with_mention_page_in_notion_page(
        parent_page_id_str,
        "z9vSQjkBVL6dCVC6QhCu4Br",
        new_page_uuid,
    )

    assert updated_count == 1
    assert retrieved_uuid_l == [UUID(parent_page_id_str)]
    assert updated_block_l == [nested_bullet]
    assert isinstance(nested_bullet.rich_text_[0], MentionObject)
    assert nested_bullet.rich_text_[0].mention.page.id == new_page_uuid
