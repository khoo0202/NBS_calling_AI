## Setup

### 1. Clone the repository
```bash
git clone https://github.com/khoo0202/NBS_calling_AI.git
cd NBS_calling_AI
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Create a `.env` file
In the project root, create a file named `.env` with the following content:
```dotenv
OPENAI_API_KEY=your_openai_api_key_here
LIVEKIT_URL=https://your-livekit-server-url
LIVEKIT_API_KEY=your_livekit_api_key_here
LIVEKIT_SECRET_KEY=your_livekit_secret_key_here
```

> **Note:** Make sure `.env` is listed in your `.gitignore` so that your secrets are not pushed to GitHub.
