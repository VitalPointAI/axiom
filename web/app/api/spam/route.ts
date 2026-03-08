import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getAuthenticatedUser } from "@/lib/auth";

// GET - List all spam tokens
export async function GET() {
  try {
    const db = await getDb();
    const spamTokens = await db.prepare(`
      SELECT token_symbol, token_contract, reported_at
      FROM spam_tokens
      ORDER BY reported_at DESC
    `).all();
    
    return NextResponse.json({ spamTokens });
  } catch (error) {
    console.error('Error fetching spam tokens:', error);
    return NextResponse.json({ error: 'Failed to fetch spam tokens' }, { status: 500 });
  }
}

// POST - Report a token as spam
export async function POST(request: Request) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const { tokenSymbol, tokenContract, reason } = body;

    if (!tokenSymbol) {
      return NextResponse.json({ error: 'Token symbol is required' }, { status: 400 });
    }

    const db = await getDb();

    // Check if already reported
    const existing = await db.prepare(`
      SELECT id FROM spam_tokens WHERE token_symbol = ?
    `).get(tokenSymbol);

    if (existing) {
      return NextResponse.json({ 
        message: 'Token already reported as spam',
        alreadyReported: true 
      });
    }

    // Add to spam list
    await db.prepare(`
      INSERT INTO spam_tokens (token_symbol, token_contract, reported_by, reason)
      VALUES (?, ?, ?, ?)
    `).run(tokenSymbol, tokenContract || null, auth.userId, reason || 'User reported spam');

    return NextResponse.json({ 
      success: true,
      message: `${tokenSymbol} has been reported as spam and will be hidden from your portfolio`
    });

  } catch (error) {
    console.error('Error reporting spam token:', error);
    return NextResponse.json({ error: 'Failed to report spam token' }, { status: 500 });
  }
}

// DELETE - Remove a token from spam list (in case of mistake)
export async function DELETE(request: Request) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const tokenSymbol = await searchParams.get('symbol');

    if (!tokenSymbol) {
      return NextResponse.json({ error: 'Token symbol is required' }, { status: 400 });
    }

    const db = await getDb();
    await db.prepare(`
      DELETE FROM spam_tokens WHERE token_symbol = ?
    `).run(tokenSymbol);

    return NextResponse.json({ 
      success: true,
      message: `${tokenSymbol} has been removed from spam list`
    });

  } catch (error) {
    console.error('Error removing spam token:', error);
    return NextResponse.json({ error: 'Failed to remove spam token' }, { status: 500 });
  }
}
