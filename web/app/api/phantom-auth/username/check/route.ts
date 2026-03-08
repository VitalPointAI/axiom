import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function POST(request: NextRequest) {
  try {
    const { username } = await request.json();

    if (!username || username.length < 3) {
      return NextResponse.json({ 
        available: false, 
        error: 'Username must be at least 3 characters' 
      });
    }

    if (!/^[a-z0-9_-]+$/.test(username)) {
      return NextResponse.json({ 
        available: false, 
        error: 'Username can only contain lowercase letters, numbers, underscore, and hyphen' 
      });
    }

    const db = getDb();

    // Check if username exists
    const existing = await db.prepare('SELECT id FROM users WHERE codename = ?').get(username);

    if (existing) {
      // Generate suggestion
      let suggestion = username;
      let counter = 1;
      while (await db.prepare('SELECT id FROM users WHERE codename = ?').get(suggestion + counter)) {
        counter++;
      }
      
      return NextResponse.json({ 
        available: false, 
        suggestion: suggestion + counter 
      });
    }

    return NextResponse.json({ available: true });
  } catch (error) {
    console.error('Username check error:', error);
    return NextResponse.json({ available: false, error: 'Check failed' }, { status: 500 });
  }
}
