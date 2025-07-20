import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import User
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Telegram Member Scraper API",
    description="API for scraping public Telegram group members",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Telegram client (will be initialized on startup)
telegram_client: Optional[TelegramClient] = None

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
    is_bot: bool
    is_verified: bool
    is_premium: bool
    status: str
    scraped_at: str

class ScrapeResponse(BaseModel):
    status: str
    contacts: List[ContactInfo]
    total_contacts: int
    processing_time: float
    message: str

# Global variables
authenticated_user = None

def get_user_status(user) -> str:
    """Get user's last seen status as a readable string."""
    if hasattr(user, 'status'):
        if hasattr(user.status, 'was_online'):
            delta = datetime.now() - user.status.was_online
            if delta.days > 30:
                return "Long Time Ago"
            elif delta.days > 7:
                return "Within A Month"
            elif delta.days > 1:
                return "Within A Week"
            elif delta.seconds > 3600:
                return "Recently"
            else:
                return "Online"
        elif str(user.status.__class__.__name__) == 'UserStatusOnline':
            return "Online"
        elif str(user.status.__class__.__name__) == 'UserStatusRecently':
            return "Recently"
        elif str(user.status.__class__.__name__) == 'UserStatusLastWeek':
            return "Within A Week"
        elif str(user.status.__class__.__name__) == 'UserStatusLastMonth':
            return "Within A Month"
        else:
            return "Long Time Ago"
    return "Unknown"

async def initialize_telegram_client():
    """Initialize Telegram client with session string."""
    global telegram_client, authenticated_user
    
    try:
        # Get credentials from environment
        session_string = os.getenv('TELEGRAM_SESSION_STRING')
        api_id = int(os.getenv('TELEGRAM_API_ID', '22420582'))
        api_hash = os.getenv('TELEGRAM_API_HASH', 'ddbb8fc720ea481bd9033f3cabb0518d')
        
        if not session_string:
            logger.error("TELEGRAM_SESSION_STRING environment variable not found")
            return False
            
        # Create client with session string
        telegram_client = TelegramClient(
            StringSession(session_string), 
            api_id, 
            api_hash
        )
        
        # Connect and verify
        await telegram_client.connect()
        
        if await telegram_client.is_user_authorized():
            # Get authenticated user info
            me = await telegram_client.get_me()
            authenticated_user = me.first_name or me.username or "Unknown"
            logger.info(f"✅ Successfully authenticated as: {authenticated_user}")
            return True
        else:
            logger.error("❌ Telegram client not authorized")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize Telegram client: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("🚀 Starting Telegram Member Scraper API on port 8000")
    success = await initialize_telegram_client()
    if not success:
        logger.error("⚠️ Telegram client initialization failed - API will have limited functionality")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown."""
    global telegram_client
    if telegram_client:
        await telegram_client.disconnect()
        logger.info("🔌 Telegram client disconnected")

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Telegram Member Scraper API",
        "version": "1.0.0",
        "status": "active"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    global telegram_client, authenticated_user
    
    telegram_connected = False
    if telegram_client:
        try:
            telegram_connected = await telegram_client.is_user_authorized()
        except:
            telegram_connected = False
    
    return {
        "status": "healthy",
        "telegram_connected": telegram_connected,
        "authenticated_user": authenticated_user or "Not authenticated"
    }

@app.post("/api/scrape", response_model=ScrapeResponse)
async def scrape_telegram_members(request: ScrapeRequest):
    """Scrape members from Telegram groups."""
    global telegram_client
    
    if not telegram_client:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")
    
    start_time = datetime.now()
    
    try:
        # Parse group links
        group_links = [link.strip() for link in request.group_links.replace('\n', ',').split(',') if link.strip()]
        
        if not group_links:
            raise HTTPException(status_code=400, detail="No valid group links provided")
        
        all_contacts = []
        processed_groups = 0
        
        for group_link in group_links:
            try:
                # Get the group entity
                entity = await telegram_client.get_entity(group_link)
                logger.info(f"📊 Processing group: {entity.title}")
                
                # Get group members
                participants = await telegram_client.get_participants(
                    entity,
                    limit=request.member_limit
                )
                
                # Process each participant
                for participant in participants:
                    if isinstance(participant, User) and not participant.bot:
                        contact_info = ContactInfo(
                            id=str(participant.id),
                            username=participant.username,
                            name=f"{participant.first_name or ''} {participant.last_name or ''}".strip() or "No Name",
                            phone=participant.phone,
                            is_bot=participant.bot or False,
                            is_verified=participant.verified or False,
                            is_premium=getattr(participant, 'premium', False),
                            status=get_user_status(participant),
                            scraped_at=datetime.now().isoformat()
                        )
                        all_contacts.append(contact_info)
                
                processed_groups += 1
                logger.info(f"✅ Processed group: {entity.title} ({len(participants)} members)")
                
            except Exception as group_error:
                logger.error(f"❌ Error processing group {group_link}: {group_error}")
                continue
        
        # Remove duplicates based on user ID
        unique_contacts = []
        seen_ids = set()
        for contact in all_contacts:
            if contact.id not in seen_ids:
                unique_contacts.append(contact)
                seen_ids.add(contact.id)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return ScrapeResponse(
            status="success",
            contacts=unique_contacts,
            total_contacts=len(unique_contacts),
            processing_time=processing_time,
            message=f"Successfully scraped {len(unique_contacts)} unique members from {processed_groups} groups"
        )
        
    except Exception as e:
        logger.error(f"❌ Scraping error: {e}")
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
