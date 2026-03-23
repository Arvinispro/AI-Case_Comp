// Simple Gemini API call with Node.js
// 1) npm install @google/genai dotenv
// 2) cp .env.example .env
// 3) add your GEMINI_API_KEY to .env
// 4) node gemini-node.js

import 'dotenv/config';
import { GoogleGenAI } from '@google/genai';

const apiKey = process.env.GEMINI_API_KEY;

if (!apiKey) {
  console.error('Missing GEMINI_API_KEY. Put it in your .env file.');
  process.exit(1);
}

const ai = new GoogleGenAI({ apiKey });

async function main() {
  const response = await ai.models.generateContent({
    model: 'gemini-2.5-flash',
    contents: 'Give me 3 ideas for an AI case competition project in healthcare.'
  });

  console.log(response.text);
}

main().catch((error) => {
  console.error('Gemini request failed:', error.message || error);
  process.exit(1);
});
