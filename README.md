# linkedIn
this a job application bot that apply linkedin easy apply jobs

# LinkedIn Easy Apply Bot 

Automate job applications on LinkedIn's "Easy Apply" postings. Securely applies to jobs while avoiding duplicates and blacklisted companies.

## Features 
-  **Secure login** (uses `.env` for credentials)
-  **Smart filtering** (experience level, blacklists)
-  **Auto-fill forms** (resume, cover letter, questions)
-  **CSV export** (tracks applications)
-  **Human-like delays** (avoids detection)
-  **Incognito mode** (optional)

## Prerequisites
- Python 3.8+
- Chrome/Firefox
- LinkedIn account

## Setup 
 **Clone the repo**
   ```bash
   git clone https://github.com/bramwelamud/linkedIn.git
   cd linkedIn

# Clone and enter repo
git clone https://github.com/yourusername/linkedin-easy-apply-bot.git
cd linkedin-easy-apply-bot

# Create virtual environment (optional)
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install packages
pip install selenium python-dotenv pyyaml pandas webdriver-manager
  
# Basic run
python bot.py

# Advanced options
python bot.py --max-applications 5 --incognito --slow-mode
