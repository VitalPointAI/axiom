import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getAuthenticatedUser } from "@/lib/auth";

// GET /api/user/preferences - Get user preferences
export async function GET(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();
    
    // Get user preferences
    const user = await db.prepare(`
      SELECT display_currency, timezone, preferences 
      FROM users WHERE id = ?
    `).get(auth.userId) as { 
      display_currency: string | null; 
      timezone: string | null;
      preferences: string | null;
    } | undefined;

    const preferences = {
      displayCurrency: user?.display_currency || 'USD',
      timezone: user?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
      ...(user?.preferences ? JSON.parse(user.preferences) : {}),
    };

    return NextResponse.json({ preferences });
  } catch (error: any) {
    console.error('Get preferences error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

// PUT /api/user/preferences - Update user preferences
export async function PUT(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const { displayCurrency, timezone, ...otherPrefs } = body;

    const db = getDb();

    // Check if columns exist, add them if not
    try {
      db.exec(`ALTER TABLE users ADD COLUMN display_currency TEXT DEFAULT 'USD'`);
    } catch (e) { /* Column exists */ }
    
    try {
      db.exec(`ALTER TABLE users ADD COLUMN timezone TEXT`);
    } catch (e) { /* Column exists */ }
    
    try {
      db.exec(`ALTER TABLE users ADD COLUMN preferences TEXT`);
    } catch (e) { /* Column exists */ }

    // Update preferences
    await db.prepare(`
      UPDATE users 
      SET display_currency = ?, 
          timezone = ?,
          preferences = ?,
          updated_at = CURRENT_TIMESTAMP
      WHERE id = ?
    `).run(
      displayCurrency || 'USD',
      timezone || null,
      Object.keys(otherPrefs).length > 0 ? JSON.stringify(otherPrefs) : null,
      auth.userId
    );

    return NextResponse.json({ 
      success: true,
      preferences: {
        displayCurrency: displayCurrency || 'USD',
        timezone,
        ...otherPrefs,
      }
    });
  } catch (error: any) {
    console.error('Update preferences error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
