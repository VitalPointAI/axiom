import { NextRequest, NextResponse } from 'next/server';
import { getAuthenticatedUser } from '@/lib/auth';

const NEAR_AI_API_URL = 'https://cloud-api.near.ai/v1/chat/completions';

const SYSTEM_PROMPT = `You are Tally, a friendly and knowledgeable crypto tax assistant for NearTax - a cryptocurrency tax reporting application for Canadian users.

Your personality:
- Friendly, helpful, and slightly playful
- Expert in crypto taxation, especially Canadian rules (Schedule 3, T1135)
- Clear and concise explanations
- Use simple language, avoid jargon unless explaining it
- Occasionally use relevant emojis (📊 💰 🧮 ✅)

Your knowledge:
- Canadian crypto tax rules (capital gains, income, ACB method)
- How NearTax tracks transactions across chains (NEAR, Ethereum, etc.)
- DeFi activities: staking, lending, borrowing, liquidity provision
- Tax categories: transfers, swaps, staking rewards, airdrops, gifts
- Cost basis calculation methods (ACB - Adjusted Cost Base for Canada)
- Form requirements: Schedule 3 for capital gains, T1135 for foreign property over $100k CAD

Guidelines:
- Keep responses concise (2-4 short paragraphs max)
- If asked about specific transactions or data, explain what the user is seeing
- If you're unsure, say so and suggest they consult a tax professional
- Don't give specific tax advice - provide educational information
- Reference the current page context when relevant

Current page context will be provided. Use it to give contextually relevant answers.`;

export async function POST(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { message, pageContext, history } = await request.json();

    if (!message) {
      return NextResponse.json({ error: 'Message required' }, { status: 400 });
    }

    // Build messages array
    const messages = [
      { role: 'system', content: SYSTEM_PROMPT },
    ];

    // Add page context as a system message
    if (pageContext) {
      messages.push({
        role: 'system',
        content: `Current context:\n${pageContext}`
      });
    }

    // Add conversation history
    if (history && Array.isArray(history)) {
      for (const msg of history) {
        messages.push({
          role: msg.role,
          content: msg.content
        });
      }
    }

    // Add current user message
    messages.push({ role: 'user', content: message });

    // Call NEAR AI Cloud
    const apiKey = process.env.NEAR_AI_API_KEY;
    
    if (!apiKey) {
      // Fallback response if no API key
      return NextResponse.json({
        response: getFallbackResponse(message, pageContext)
      });
    }

    const response = await fetch(NEAR_AI_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: 'deepseek-ai/DeepSeek-V3.1',
        messages,
        max_tokens: 500,
        temperature: 0.7,
      }),
    });

    if (!response.ok) {
      console.error('NEAR AI API error:', await response.text());
      return NextResponse.json({
        response: getFallbackResponse(message, pageContext)
      });
    }

    const data = await response.json();
    const assistantMessage = data.choices?.[0]?.message?.content;

    if (!assistantMessage) {
      return NextResponse.json({
        response: getFallbackResponse(message, pageContext)
      });
    }

    return NextResponse.json({ response: assistantMessage });

  } catch (error) {
    console.error('Tally API error:', error);
    return NextResponse.json({ 
      response: "I'm having trouble connecting right now. Please try again in a moment! 🔄" 
    });
  }
}

// Fallback responses when AI is unavailable
function getFallbackResponse(message: string, pageContext?: string): string {
  const lowerMessage = message.toLowerCase();
  
  if (lowerMessage.includes('what is this page') || lowerMessage.includes('this page for')) {
    if (pageContext?.includes('dashboard/transactions')) {
      return "📊 This is your transaction history! Here you can see all your crypto transactions across all your wallets. Use the filters to narrow down by asset, chain, date, or tax category. Each transaction shows the type, amount, and current tax classification.";
    }
    if (pageContext?.includes('dashboard/assets')) {
      return "💰 This is your Assets page! It shows all your current crypto holdings across all chains, with their USD values. You can filter by asset or chain, and expand each row to see the breakdown by wallet.";
    }
    if (pageContext?.includes('dashboard/staking')) {
      return "🥩 This is your Staking Income tracker! It shows your validator rewards, stake deposits, and withdrawals. Staking rewards are typically taxed as income at the time you receive them.";
    }
    if (pageContext?.includes('dashboard/reports')) {
      return "📋 This is your Reports page! Generate tax documents like Schedule 3 (capital gains/losses), T1135 (foreign property over $100k CAD), and income summaries for your tax filing.";
    }
    return "This page is part of NearTax, helping you track and report your crypto taxes! Feel free to ask specific questions about what you're seeing.";
  }
  
  if (lowerMessage.includes('taxable') || lowerMessage.includes('tax event')) {
    return "🧮 In Canada, taxable crypto events include:\n\n• **Selling crypto for fiat** (CAD/USD)\n• **Trading one crypto for another** (swap)\n• **Using crypto to buy goods/services**\n• **Receiving staking rewards** (income)\n• **Airdrops** (income)\n\nSimply holding or transferring between your own wallets is NOT taxable!";
  }
  
  if (lowerMessage.includes('categorize') || lowerMessage.includes('category')) {
    return "📁 NearTax auto-categorizes transactions, but you can manually adjust them:\n\n• **Transfer** - Moving between your own wallets\n• **Swap** - Trading one token for another\n• **Staking** - Depositing to validators\n• **DeFi** - Lending, borrowing, LP tokens\n• **Income** - Airdrops, rewards, payments received";
  }
  
  if (lowerMessage.includes('staking') || lowerMessage.includes('reward')) {
    return "🥩 Staking rewards in Canada are generally treated as income at fair market value when received. NearTax tracks:\n\n• Your staked amounts per validator\n• Daily/epoch rewards earned\n• Historical prices for accurate valuation\n\nKeep records of when you received rewards and their value at that time!";
  }
  
  return "Hi! I'm Tally, your crypto tax assistant 🧮 I can help explain transactions, tax categories, and how NearTax works. What would you like to know?";
}
