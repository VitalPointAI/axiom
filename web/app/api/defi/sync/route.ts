import { NextResponse } from 'next/server';
import { getAuthenticatedUser } from '@/lib/auth';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

export async function POST() {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

    // Run the Burrow tracker for this user
    const { stdout, stderr } = await execAsync(
      `cd /home/deploy/neartax && python3 indexers/burrow_tracker.py ${auth.userId}`,
      { timeout: 60000 }
    );

    return NextResponse.json({ 
      success: true, 
      message: 'Positions synced',
      output: stdout 
    });
  } catch (error: any) {
    console.error('Sync error:', error);
    return NextResponse.json({ 
      error: 'Sync failed', 
      details: error.message 
    }, { status: 500 });
  }
}
