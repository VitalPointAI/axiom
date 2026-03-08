import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';
import { createHash } from 'crypto';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

interface ParsedTransaction {
  timestamp: string;
  txType: string;
  asset: string;
  amount: number;
  quoteAsset?: string;
  quoteAmount?: number;
  pricePerUnit?: number;
  feeAmount?: number;
  description?: string;
  hash: string;
}

// Get or create a virtual wallet for an exchange
async function getOrCreateExchangeWallet(db: any, userId: number, exchange: string, chain: string = 'exchange'): Promise<number> {
  const accountId = `import:${exchange}`;
  
  const existing = await db.prepare(`
    SELECT id FROM wallets WHERE user_id = ? AND account_id = ?
  `).get(userId, accountId);
  
  if (existing) {
    return existing.id;
  }
  
  const result = await db.prepare(`
    INSERT INTO wallets (user_id, account_id, label, chain, is_owned, sync_status, created_at)
    VALUES (?, ?, ?, ?, 1, 'import', NOW())
  `).run(userId, accountId, `${exchange.charAt(0).toUpperCase() + exchange.slice(1)} Import`, chain);
  
  return Number(result.rows?.[0]?.id || 0);
}

// Map import tx type to transaction direction/action_type
function mapTxType(txType: string): { direction: string; actionType: string } {
  const mappings: Record<string, { direction: string; actionType: string }> = {
    'buy': { direction: 'IN', actionType: 'BUY' },
    'sell': { direction: 'OUT', actionType: 'SELL' },
    'deposit': { direction: 'IN', actionType: 'DEPOSIT' },
    'withdrawal': { direction: 'OUT', actionType: 'WITHDRAWAL' },
    'transfer_in': { direction: 'IN', actionType: 'TRANSFER' },
    'transfer_out': { direction: 'OUT', actionType: 'TRANSFER' },
    'reward': { direction: 'IN', actionType: 'REWARD' },
    'staking_reward': { direction: 'IN', actionType: 'STAKING_REWARD' },
    'interest': { direction: 'IN', actionType: 'INTEREST' },
    'airdrop': { direction: 'IN', actionType: 'AIRDROP' },
    'trade': { direction: 'IN', actionType: 'TRADE' },
    'fee': { direction: 'OUT', actionType: 'FEE' },
  };
  return mappings[txType] || { direction: 'IN', actionType: txType.toUpperCase() };
}

// Parse PDF using pdf2json
async function parsePdfText(buffer: Buffer): Promise<string> {
  return new Promise((resolve, reject) => {
    const PDFParser = require('pdf2json');
    const pdfParser = new PDFParser();
    
    pdfParser.on('pdfParser_dataError', (errData: any) => {
      reject(new Error(errData.parserError || 'PDF parse error'));
    });
    
    pdfParser.on('pdfParser_dataReady', (pdfData: any) => {
      try {
        let fullText = '';
        if (pdfData && pdfData.Pages) {
          for (const page of pdfData.Pages) {
            if (page.Texts) {
              for (const textItem of page.Texts) {
                if (textItem.R) {
                  for (const run of textItem.R) {
                    if (run.T) {
                      fullText += decodeURIComponent(run.T) + ' ';
                    }
                  }
                }
              }
            }
            fullText += '\n';
          }
        }
        resolve(fullText);
      } catch (e) {
        reject(e);
      }
    });
    
    pdfParser.parseBuffer(buffer);
  });
}

// Parse Coinsquare PDF statement
function parseCoinsquarePDF(text: string): ParsedTransaction[] {
  const transactions: ParsedTransaction[] = [];
  
  const dateTimeRegex = /(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}(?:\.\d+)?)/g;
  let match;
  const datePositions: {index: number, timestamp: string}[] = [];
  
  while ((match = dateTimeRegex.exec(text)) !== null) {
    datePositions.push({
      index: match.index,
      timestamp: `${match[1]}T${match[2]}Z`
    });
  }
  
  for (let i = 0; i < datePositions.length; i++) {
    const startIdx = datePositions[i].index;
    const endIdx = i + 1 < datePositions.length ? datePositions[i + 1].index : text.length;
    const chunk = text.substring(startIdx, endIdx);
    const timestamp = datePositions[i].timestamp;
    
    // Sale = buying crypto with CAD
    const saleMatch = chunk.match(/Sale\s+(?:Sale\s+)?of\s+\$?([\d,]+\.?\d*)\s*CAD\s+for\s+([\d,]+\.?\d*)\s*(\w+)/i);
    if (saleMatch) {
      const cadAmount = parseFloat(saleMatch[1].replace(/,/g, ''));
      const cryptoAmount = parseFloat(saleMatch[2].replace(/,/g, ''));
      const asset = saleMatch[3].toUpperCase();
      
      const feeMatch = chunk.match(/\$([\d,]+\.?\d*)\*/);
      const fee = feeMatch ? parseFloat(feeMatch[1].replace(/,/g, '')) : 0;
      
      const hashInput = `coinsquare|${timestamp}|${asset}|${cryptoAmount}|buy|${cadAmount}`;
      const hash = createHash('sha256').update(hashInput).digest('hex').slice(0, 32);
      
      transactions.push({
        timestamp,
        txType: 'buy',
        asset,
        amount: cryptoAmount,
        quoteAsset: 'CAD',
        quoteAmount: cadAmount,
        pricePerUnit: cadAmount / cryptoAmount,
        feeAmount: fee > 0 ? fee : undefined,
        description: `Sale of $${cadAmount} CAD for ${cryptoAmount} ${asset}`,
        hash,
      });
      continue;
    }
    
    // Purchase = selling crypto to get CAD
    const purchaseMatch = chunk.match(/Purchase\s+(?:Purchase\s+)?of\s+\$?([\d,]+\.?\d*)\s*CAD\s+for\s+([\d,]+\.?\d*)\s*(\w+)/i);
    if (purchaseMatch) {
      const cadAmount = parseFloat(purchaseMatch[1].replace(/,/g, ''));
      const cryptoAmount = parseFloat(purchaseMatch[2].replace(/,/g, ''));
      const asset = purchaseMatch[3].toUpperCase();
      
      const feeMatch = chunk.match(/\$([\d,]+\.?\d*)\*/);
      const fee = feeMatch ? parseFloat(feeMatch[1].replace(/,/g, '')) : 0;
      
      const hashInput = `coinsquare|${timestamp}|${asset}|${cryptoAmount}|sell|${cadAmount}`;
      const hash = createHash('sha256').update(hashInput).digest('hex').slice(0, 32);
      
      transactions.push({
        timestamp,
        txType: 'sell',
        asset,
        amount: cryptoAmount,
        quoteAsset: 'CAD',
        quoteAmount: cadAmount,
        pricePerUnit: cadAmount / cryptoAmount,
        feeAmount: fee > 0 ? fee : undefined,
        description: `Purchase of $${cadAmount} CAD for ${cryptoAmount} ${asset}`,
        hash,
      });
      continue;
    }
    
    // Deposit Cash
    if (/Deposit\s+Cash\s+\(CAD\)/i.test(chunk)) {
      const amountMatch = chunk.match(/([\d,]+\.?\d*)\s+1\.00\s+0\.00/);
      const amount = amountMatch ? parseFloat(amountMatch[1].replace(/,/g, '')) : 0;
      
      if (amount > 0) {
        const hashInput = `coinsquare|${timestamp}|CAD|${amount}|deposit`;
        const hash = createHash('sha256').update(hashInput).digest('hex').slice(0, 32);
        
        transactions.push({
          timestamp,
          txType: 'deposit',
          asset: 'CAD',
          amount,
          quoteAsset: 'CAD',
          quoteAmount: amount,
          description: `Deposit Cash (CAD) $${amount}`,
          hash,
        });
      }
      continue;
    }
    
    // Withdraw Cash
    if (/Withdraw\s+Cash\s+\(CAD\)/i.test(chunk)) {
      const amountMatch = chunk.match(/([\d,]+\.?\d*)\s+1\.00\s+0\.00/);
      const amount = amountMatch ? parseFloat(amountMatch[1].replace(/,/g, '')) : 0;
      
      if (amount > 0) {
        const hashInput = `coinsquare|${timestamp}|CAD|${amount}|withdrawal`;
        const hash = createHash('sha256').update(hashInput).digest('hex').slice(0, 32);
        
        transactions.push({
          timestamp,
          txType: 'withdrawal',
          asset: 'CAD',
          amount,
          quoteAsset: 'CAD',
          quoteAmount: amount,
          description: `Withdraw Cash (CAD) $${amount}`,
          hash,
        });
      }
      continue;
    }
  }
  
  return transactions;
}

// Generic PDF parser
function parseGenericPDF(text: string): ParsedTransaction[] {
  const transactions: ParsedTransaction[] = [];
  
  const datePatterns = [
    /(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)?)/g,
    /(\w{3}\s+\d{1,2},?\s+\d{4})/g,
    /(\d{1,2}\/\d{1,2}\/\d{4})/g,
  ];
  
  const txTypeKeywords: Record<string, string> = {
    'buy': 'buy', 'bought': 'buy', 'purchase': 'buy',
    'sell': 'sell', 'sold': 'sell', 'sale': 'sell',
    'deposit': 'deposit', 'withdraw': 'withdrawal',
    'send': 'transfer_out', 'receive': 'transfer_in',
    'reward': 'reward', 'staking': 'staking_reward',
  };
  
  const cryptoSymbols = ['BTC', 'ETH', 'LTC', 'XRP', 'NEAR', 'SOL', 'DOT', 'USDT', 'USDC', 'DOGE', 'ADA'];
  
  const chunks = text.split(/\n|\r/).filter(c => c.trim().length > 10);
  
  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i];
    const chunkLower = chunk.toLowerCase();
    
    let date: string | null = null;
    for (const pattern of datePatterns) {
      pattern.lastIndex = 0;
      const match = pattern.exec(chunk);
      if (match) {
        date = match[1];
        break;
      }
    }
    if (!date) continue;
    
    let txType: string | null = null;
    for (const [keyword, type] of Object.entries(txTypeKeywords)) {
      if (chunkLower.includes(keyword)) {
        txType = type;
        break;
      }
    }
    if (!txType) continue;
    
    let asset: string | null = null;
    for (const symbol of cryptoSymbols) {
      if (chunk.toUpperCase().includes(symbol)) {
        asset = symbol;
        break;
      }
    }
    if (!asset) continue;
    
    const amounts = chunk.match(/(\d+\.?\d*)/g);
    let amount = 0;
    if (amounts) {
      for (const a of amounts) {
        const val = parseFloat(a);
        if (val > 0 && val < 1e9) {
          amount = val;
          break;
        }
      }
    }
    if (amount === 0) continue;
    
    let timestamp: string;
    try {
      const d = new Date(date);
      timestamp = isNaN(d.getTime()) ? new Date().toISOString() : d.toISOString();
    } catch {
      timestamp = new Date().toISOString();
    }
    
    const hashInput = `generic|${timestamp}|${asset}|${amount}|${txType}|${i}`;
    const hash = createHash('sha256').update(hashInput).digest('hex').slice(0, 32);
    
    transactions.push({
      timestamp,
      txType,
      asset,
      amount,
      description: chunk.trim().substring(0, 200),
      hash,
    });
  }
  
  return transactions;
}

// Detect PDF source
function detectPdfSource(text: string): 'coinsquare' | 'generic' {
  const textLower = text.toLowerCase();
  if (textLower.includes('coinsquare') || 
      textLower.includes('order execution only') ||
      (textLower.includes('settlement date') && textLower.includes('activity'))) {
    return 'coinsquare';
  }
  return 'generic';
}

// Trigger auto-categorization after import
async function triggerAutoCategorizationAsync(userId: number) {
  try {
    const cmd = `cd /home/deploy/neartax && python3 scripts/auto_categorize.py --user-id ${userId} 2>&1`;
    execAsync(cmd).catch(err => {
      console.error('Auto-categorization error:', err);
    });
  } catch (e) {
    console.error('Failed to trigger auto-categorization:', e);
  }
}

// POST /api/import/pdf
export async function POST(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const formData = await request.formData();
    const file = await formData.get('file') as File;
    const preview = await formData.get('preview') === 'true';

    if (!file) {
      return NextResponse.json({ error: 'No file provided' }, { status: 400 });
    }

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      return NextResponse.json({ error: 'File must be a PDF' }, { status: 400 });
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    
    let text: string;
    try {
      text = await parsePdfText(buffer);
    } catch (e) {
      console.error('PDF parse error:', e);
      return NextResponse.json({ 
        error: 'Failed to parse PDF. Make sure it\'s a valid PDF file.',
        debug: e instanceof Error ? e.message : 'Unknown error'
      }, { status: 400 });
    }

    if (!text || text.trim().length === 0) {
      return NextResponse.json({ 
        error: 'PDF appears to be empty or image-based (no extractable text)'
      }, { status: 400 });
    }

    const source = detectPdfSource(text);
    let transactions: ParsedTransaction[];
    
    if (source === 'coinsquare') {
      transactions = parseCoinsquarePDF(text);
    } else {
      transactions = parseGenericPDF(text);
    }

    if (transactions.length === 0) {
      return NextResponse.json({ 
        error: 'No transactions found in PDF',
        source,
        textLength: text.length,
        textPreview: text.substring(0, 1500)
      }, { status: 400 });
    }

    if (preview) {
      // Return same structure as CSV for frontend compatibility
      return NextResponse.json({
        exchange: source,
        headers: [],
        totalRows: transactions.length,
        parsedCount: transactions.length,
        errorCount: 0,
        preview: transactions.slice(0, 20),
        errors: [],
      });
    }

    const db = getDb();

    // Get or create virtual wallet for this exchange
    const walletId = getOrCreateExchangeWallet(db, user.userId, source);

    // Create import batch
    const batchResult = await db.prepare(`
      INSERT INTO import_batches (user_id, filename, exchange, row_count, status, created_at)
      VALUES (?, ?, ?, ?, 'processing', NOW())
    `).run(user.userId, file.name, source, transactions.length);

    const batchId = batchResult.lastInsertRowid || 0;

    // Insert into main transactions table
    let imported = 0;
    let skipped = 0;

    const insertStmt = await db.prepare(`
      INSERT OR IGNORE INTO transactions (
        wallet_id, tx_hash, direction, action_type, amount, fee,
        block_timestamp, success, source, asset, quote_asset, quote_amount,
        price_at_tx, description, import_batch_id, exchange, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'import', ?, ?, ?, ?, ?, ?, ?, NOW())
    `);

    for (const tx of transactions) {
      const { direction, actionType } = mapTxType(tx.txType);
      
      let blockTimestamp: number;
      try {
        blockTimestamp = new Date(tx.timestamp).getTime();
      } catch {
        blockTimestamp = Date.now();
      }

      const result = await insertStmt.run(
        walletId,
        tx.hash,
        direction,
        actionType,
        tx.amount.toString(),
        tx.feeAmount?.toString() || null,
        blockTimestamp,
        tx.asset,
        tx.quoteAsset || null,
        tx.quoteAmount || null,
        tx.pricePerUnit || null,
        tx.description || null,
        batchId,
        source
      );
      
      if ((result.rowCount || 0) > 0) {
        imported++;
      } else {
        skipped++;
      }
    }

    await db.prepare(`
      UPDATE import_batches 
      SET status = 'completed', 
          imported_count = ?, 
          skipped_count = ?,
          completed_at = NOW()
      WHERE id = ?
    `).run(imported, skipped, batchId);

    // Trigger auto-categorization in background
    triggerAutoCategorizationAsync(user.userId);

    return NextResponse.json({
      success: true,
      batchId,
      source,
      walletId,
      totalTransactions: transactions.length,
      imported,
      skipped,
      message: `Imported ${imported} transactions into main transactions table. Auto-categorization triggered.`
    });

  } catch (error) {
    console.error('PDF import error:', error);
    return NextResponse.json({ 
      error: 'Failed to import PDF',
      details: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
}
