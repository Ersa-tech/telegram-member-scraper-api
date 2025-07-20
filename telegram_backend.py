#!/usr/bin/env python3
"""
FastAPI Backend for Telegram Member Scraping
Uses Telethon with authenticated session
"""

import asyncio
import os
import logging
from typing import List, Dict, Optional, Union
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    ChannelPrivateError, FloodWaitError, UserDeactivatedError,
    UserRestrictedError, AuthKeyUnregisteredError
)
from telethon.tl.types import (
    User, Channel, Chat, ChannelParticipantsRecent, 
    ChannelParticipantsSearch
)
from telethon.tl.functions.channels import GetParticipantsRequest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Configuration
API_ID = 22420582
API_HASH = "ddbb8fc720ea481bd9033f3cabb0518d"
SESSION_STRING = "1BVtsOHwBuzx8X2jjY6qmgXP2ypC4Y1T5nnrkEZTQWXYeLKje1Hu86wFW-NHcpwJ_qHFssrvt5VB73dIyK_HtAv-EO_tZP778IYmieHHr08BEmrNQzWn7f3vtnMdaNM3EysNzpJQq551GqQRvT_cwFVTLSrRGVaKMgfw60LlAEDhCcK7AEJYJCEULjs-WR5cttNr_kSHn6V4aJViEtXyJMkey_9_jMt0SgF0n6gUfRViADMvs0K6hi9gXHPpQ2lEagKbTHRrS2Hg8NOKcvUr6uFvUL4nlkVYdqjdJVJvqNu8sPyTyxWEOeqejXvtrWk3UBdO9dk_Sok0kVx8xQWLiQ0d7JbLastM="

# FastAPI app
app = FastAPI(title="Telegram Member Scraper API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class ScrapeRequest(BaseModel):
    group_links: str
    custom_filename: Optional[str] = ""
    member_limit: Optional[int] = None

class ContactInfo(BaseModel):
    id: str
    username: Optional[str]
    name: str
    phone: Optional[str]
    is_bot: bool = False
    is_verified: bool = False
    is_premium: bool = False
    status: str = "Unknown"
    scraped_at: str

class ScrapeResponse(BaseModel):
    status: str
    contacts: List[ContactInfo]
    total_contacts: int
    processing_time: float
    message: Optional[str] = None

# Global client instance
telegram_client: Optional[TelegramClient] = None

async def get_telegram_client():
    """Get or create Telegram client"""
    global telegram_client
    
    if telegram_client is None or not telegram_client.is_connected():
        try:
            # Use session string from environment or hardcoded
            session_str = os.getenv('TELEGRAM_SESSION_STRING', SESSION_STRING)
            telegram_client = TelegramClient(
                StringSession(session_str), 
                API_ID, 
                API_HASH
            )
            await telegram_client.start()
            
            if not await telegram_client.is_user_authorized():
                raise Exception("Session is not authorized")
                
            logger.info("✅ Telegram client connected successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Telegram: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to connect to Telegram: {e}")
    
    return telegram_client

def extract_user_info(user: User) -> ContactInfo:
    """Extract user information"""
    return ContactInfo(
        id=str(user.id),
        username=user.username,
        name=f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or f"User {user.id}",
        phone=user.phone,
        is_bot=user.bot or False,
        is_verified=user.verified or False,
        is_premium=getattr(user, 'premium', False),
        status=get_user_status(user),
        scraped_at=datetime.now().isoformat()
    )

def get_user_status(user: User) -> str:
    """Get user online status"""
    if hasattr(user, 'status'):
        status = user.status
        if hasattr(status, '__class__'):
            status_name = status.__class__.__name__
            if 'Online' in status_name:
                return 'Online'
            elif 'Recently' in status_name:
                return 'Recently'
            elif 'LastWeek' in status_name:
                return 'Last Week'
            elif 'LastMonth' in status_name:
                return 'Last Month'
            elif 'Offline' in status_name:
                return 'Long Time Ago'
    return 'Unknown'

async def get_group_entity(client: TelegramClient, group_identifier: str):
    """Get group entity from URL or username"""
    try:
        # Clean up the group identifier
        if group_identifier.startswith('https://t.me/'):
            group_identifier = group_identifier.replace('https://t.me/', '')
        if group_identifier.startswith('@'):
            group_identifier = group_identifier[1:]
        
        entity = await client.get_entity(group_identifier)
        return entity
        
    except ChannelPrivateError:
        raise HTTPException(status_code=403, detail="Group is private or you're not a member")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Group not found: {e}")

async def scrape_group_members(client: TelegramClient, group_entity, limit: Optional[int] = None) -> List[ContactInfo]:
    """Scrape members from a group"""
    members = []
    offset = 0
    total_scraped = 0
    
    group_name = getattr(group_entity, 'title', 'Unknown Group')
    logger.info(f"🔄 Scraping members from '{group_name}' (limit: {limit or 'no limit'})")
    
    try:
        while True:
            if limit and total_scraped >= limit:
                break
            
            batch_size = min(200, limit - total_scraped if limit else 200)
            
            # Get participants
            participants = await client(GetParticipantsRequest(
                channel=group_entity,
                filter=ChannelParticipantsRecent(),
                offset=offset,
                limit=batch_size,
                hash=0
            ))
            
            if not participants.users:
                break
            
            # Process users
            for user in participants.users:
                if isinstance(user, User):
                    contact = extract_user_info(user)
                    members.append(contact)
                    total_scraped += 1
                    
                    if limit and total_scraped >= limit:
                        break
            
            offset += len(participants.users)
            
            # Rate limiting
            await asyncio.sleep(1)
            
    except FloodWaitError as e:
        logger.warning(f"⏰ Rate limited for {e.seconds} seconds")
        raise HTTPException(status_code=429, detail=f"Rate limited. Try again in {e.seconds} seconds")
    except Exception as e:
        logger.error(f"❌ Error scraping group: {e}")
        raise HTTPException(status_code=500, detail=f"Error scraping group: {e}")
    
    logger.info(f"✅ Scraped {len(members)} members from '{group_name}'")
    return members

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "Telegram Member Scraper API"}

@app.get("/health")
async def health_check():
    """Detailed health check"""
    try:
        client = await get_telegram_client()
        me = await client.get_me()
        return {
            "status": "healthy",
            "telegram_connected": True,
            "authenticated_user": f"{me.first_name} {me.last_name or ''}".strip()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "telegram_connected": False,
            "error": str(e)
        }

@app.post("/api/scrape", response_model=ScrapeResponse)
async def scrape_telegram_members(request: ScrapeRequest):
    """Main endpoint for scraping Telegram members"""
    start_time = datetime.now()
    
    try:
        # Get Telegram client
        client = await get_telegram_client()
        
        # Parse group links
        group_links = [link.strip() for link in request.group_links.split('\n') if link.strip()]
        
        if not group_links:
            raise HTTPException(status_code=400, detail="No valid group links provided")
        
        all_contacts = []
        
        # Process each group
        for group_link in group_links:
            try:
                logger.info(f"📥 Processing group: {group_link}")
                
                # Get group entity
                group_entity = await get_group_entity(client, group_link)
                
                # Calculate remaining limit
                remaining_limit = None
                if request.member_limit:
                    remaining_limit = request.member_limit - len(all_contacts)
                    if remaining_limit <= 0:
                        break
                
                # Scrape members
                group_contacts = await scrape_group_members(client, group_entity, remaining_limit)
                all_contacts.extend(group_contacts)
                
                logger.info(f"✅ Got {len(group_contacts)} members from {group_link}")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"❌ Error processing {group_link}: {e}")
                continue
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Remove duplicates based on user ID
        unique_contacts = {}
        for contact in all_contacts:
            if contact.id not in unique_contacts:
                unique_contacts[contact.id] = contact
        
        final_contacts = list(unique_contacts.values())
        
        logger.info(f"🎉 Scraping completed: {len(final_contacts)} unique members")
        
        return ScrapeResponse(
            status="success",
            contacts=final_contacts,
            total_contacts=len(final_contacts),
            processing_time=processing_time,
            message=f"Successfully scraped {len(final_contacts)} unique members from {len(group_links)} groups"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment (for deployment)
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"🚀 Starting Telegram Member Scraper API on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
