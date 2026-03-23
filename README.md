# AI-Case_Comp

Gemini API quick start for this workspace.

## 1) Get an API key

1. Go to Google AI Studio: https://aistudio.google.com/
2. Create an API key.
3. Copy `.env.example` to `.env` and paste your key:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
GEMINI_API_KEY=your_real_key_here
```

## 2) Node.js example

Install deps:

```bash
npm init -y
npm install @google/genai dotenv
```

Enable ESM in `package.json` by adding:

```json
"type": "module"
```

Run:

```bash
node gemini-node.js
```

## 3) Python example

Install deps:

```bash
pip install google-genai python-dotenv
```

Run:

```bash
python gemini-python.py
```

## Files

- `.env.example` - environment variable template.
- `gemini-node.js` - Node.js Gemini API example.
- `gemini-python.py` - Python Gemini API example.