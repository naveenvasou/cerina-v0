"""Debug script to check ChatHistory table contents"""
import asyncio
from backend.database import async_session_maker
from sqlmodel import select
from backend.models import ChatHistoryItem

async def main():
    if not async_session_maker:
        print("Database not configured")
        return
        
    async with async_session_maker() as db:
        result = await db.execute(
            select(ChatHistoryItem)
            .order_by(ChatHistoryItem.created_at.desc())
            .limit(30)
        )
        items = result.scalars().all()
        
        if not items:
            print("No items found in chat_history table")
            return
        
        # Get unique item_types
        item_types = set(i.item_type for i in items)
        print(f"Unique item_types found: {item_types}")
        print(f"\nFound {len(items)} items:")
        print("-" * 100)
        for i in items:
            content_preview = (i.content[:50].replace('\n', ' ') if i.content else 'N/A')
            print(f"SEQ {i.sequence:2}: {i.item_type:15} | role={i.role:10} | agent={str(i.agent_name)[:12]:12} | {content_preview}")

if __name__ == "__main__":
    asyncio.run(main())
