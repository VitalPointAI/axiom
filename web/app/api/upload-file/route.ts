import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';
import { createHash } from 'crypto';
import { writeFileSync, mkdirSync, readFileSync } from 'fs';
import { join } from 'path';

// Maximum file size: 50 MB
const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;

/**
 * POST /api/upload-file
 *
 * Accepts a multipart/form-data upload with a single `file` field.
 * Steps:
 * 1. Authenticate user
 * 2. Parse multipart form data
 * 3. Validate file size (max 50 MB)
 * 4. SHA-256 hash for deduplication
 * 5. Check file_imports for existing (user_id, file_hash) — 409 if duplicate
 * 6. Save file to uploads/{user_id}/{timestamp}_{filename}
 * 7. INSERT into file_imports (status='queued')
 * 8. Ensure an 'exchange_imports' virtual wallet exists for the user
 * 9. INSERT into indexing_jobs (job_type='file_import', cursor=file_imports.id)
 * 10. UPDATE file_imports.job_id with the created job id
 * 11. Return 201 { file_import_id, job_id, filename, status: 'queued' }
 */
export async function POST(request: NextRequest) {
  // 1. Authenticate
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const userId = auth.userId;

  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json({ error: 'Invalid multipart form data' }, { status: 400 });
  }

  // 2. Extract file
  const file = formData.get('file');
  if (!file || !(file instanceof File)) {
    return NextResponse.json({ error: 'No file provided in request' }, { status: 400 });
  }

  // 3. Validate file size
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return NextResponse.json(
      { error: `File too large. Maximum size is 50 MB (got ${Math.round(file.size / 1024 / 1024)} MB)` },
      { status: 413 }
    );
  }

  // Read file contents as Buffer
  const arrayBuffer = await file.arrayBuffer();
  const fileBuffer = Buffer.from(arrayBuffer);
  const filename = file.name;
  const mimeType = file.type || 'text/csv';

  // 4. SHA-256 content hash for deduplication
  const fileHash = createHash('sha256').update(fileBuffer).digest('hex');

  // 5. Check for duplicate upload
  try {
    const existing = await db.get(
      `SELECT id, status FROM file_imports WHERE user_id = $1 AND file_hash = $2`,
      [userId, fileHash]
    );
    if (existing) {
      return NextResponse.json(
        { error: 'File already imported', file_import_id: (existing as any).id },
        { status: 409 }
      );
    }
  } catch (err) {
    console.error('Duplicate check failed:', err);
    return NextResponse.json({ error: 'Database error during duplicate check' }, { status: 500 });
  }

  // 6. Save file to uploads/{user_id}/{timestamp}_{filename}
  const timestamp = Date.now();
  const safeFilename = filename.replace(/[^a-zA-Z0-9._-]/g, '_');
  const uploadDir = join(process.cwd(), '..', 'uploads', String(userId));
  const storagePath = join(uploadDir, `${timestamp}_${safeFilename}`);

  try {
    mkdirSync(uploadDir, { recursive: true });
    writeFileSync(storagePath, fileBuffer);
  } catch (err) {
    console.error('File save failed:', err);
    return NextResponse.json({ error: 'Failed to save uploaded file' }, { status: 500 });
  }

  // 7–10: DB operations in a transaction
  try {
    // 7. INSERT into file_imports
    const fileImportResult = await db.run(
      `INSERT INTO file_imports
         (user_id, filename, file_hash, file_size, mime_type, storage_path, status)
       VALUES ($1, $2, $3, $4, $5, $6, 'queued')`,
      [userId, filename, fileHash, file.size, mimeType, storagePath]
    );
    const fileImportId = fileImportResult.lastInsertRowid;

    if (!fileImportId) {
      throw new Error('file_imports INSERT did not return an id');
    }

    // 8. Ensure virtual exchange_imports wallet exists for this user.
    // account_id is globally UNIQUE so we use user-scoped name: exchange_imports_{userId}
    const exchangeAccountId = `exchange_imports_${userId}`;
    await db.run(
      `INSERT INTO wallets (user_id, account_id, chain)
       VALUES ($1, $2, 'exchange')
       ON CONFLICT (account_id) DO NOTHING`,
      [userId, exchangeAccountId]
    );

    // 9. Get wallet_id for the exchange_imports wallet
    const exchangeWallet = await db.get(
      `SELECT id FROM wallets WHERE user_id = $1 AND account_id = $2 AND chain = 'exchange'`,
      [userId, exchangeAccountId]
    ) as { id: number } | undefined;

    if (!exchangeWallet) {
      throw new Error('exchange_imports wallet not found after upsert');
    }
    const walletId = exchangeWallet.id;

    // 10. INSERT into indexing_jobs (cursor = file_imports.id so handler knows which file)
    const jobResult = await db.run(
      `INSERT INTO indexing_jobs
         (user_id, wallet_id, job_type, chain, status, priority, cursor)
       VALUES ($1, $2, 'file_import', 'exchange', 'queued', 5, $3)`,
      [userId, walletId, String(fileImportId)]
    );
    const jobId = jobResult.lastInsertRowid;

    if (!jobId) {
      throw new Error('indexing_jobs INSERT did not return an id');
    }

    // 11. Update file_imports with job_id
    await db.run(
      `UPDATE file_imports SET job_id = $1 WHERE id = $2`,
      [jobId, fileImportId]
    );

    return NextResponse.json(
      {
        file_import_id: fileImportId,
        job_id: jobId,
        filename,
        status: 'queued',
      },
      { status: 201 }
    );
  } catch (err) {
    console.error('Upload-file DB error:', err);
    return NextResponse.json({ error: 'Database error during file import setup' }, { status: 500 });
  }
}
