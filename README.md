# Telegram Member Scraper API

A FastAPI-based service for scraping public Telegram group members with authenticated session management.

## Features

- 🔐 Authenticated Telegram session support
- 📊 Scrape public Telegram groups with visible member lists
- 🚀 Fast async processing with FastAPI
- 📈 Real-time member information (status, premium, verified)
- 🔄 Duplicate removal across multiple groups
- 📋 JSON API responses with detailed member data

## API Endpoints

### Health Check
```
GET /health
```
Returns API status and Telegram connection status.

### Scrape Members
```
POST /api/scrape
```

**Request Body:**
```json
{
  "group_links": "https://t.me/group1,https://t.me/group2",
  "custom_filename": "optional_filename",
  "member_limit": 100
}
```

**Response:**
```json
{
  "status": "success",
  "contacts": [
    {
      "id": "12345",
      "username": "user123",
      "name": "John Doe",
      "phone": null,
      "is_bot": false,
      "is_verified": false,
      "is_premium": true,
      "status": "Online",
      "scraped_at": "2025-07-20T08:30:00.000000"
    }
  ],
  "total_contacts": 1,
  "processing_time": 1.23,
  "message": "Successfully scraped 1 unique members from 1 groups"
}
```

## Environment Variables

Set these in your deployment environment (Render, etc.):

```
TELEGRAM_SESSION_STRING=your_session_string_here
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
PORT=8000
```

## Deployment

### Render
1. Create new Web Service
2. Connect this repository
3. Configure:
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python telegram_backend.py`
4. Add environment variables
5. Deploy

## Important Notes

- Only works with PUBLIC Telegram groups that have visible member lists
- Requires authenticated Telegram session (session string)
- Respects Telegram's rate limits
- Does not work with private groups or channels

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TELEGRAM_SESSION_STRING="your_session_string"
export TELEGRAM_API_ID="your_api_id"
export TELEGRAM_API_HASH="your_api_hash"

# Run server
python telegram_backend.py
```

The API will be available at `http://localhost:8000`

## License

This project is for educational and legitimate business purposes only. Please respect Telegram's Terms of Service and applicable privacy laws.
